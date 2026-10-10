import os
from io import BytesIO
from PIL import Image
import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_studio.db')
os.environ.setdefault('STUDIO_DEV_API_KEY', 'test-secret')
from fastapi.testclient import TestClient
from app.main import app
from app import production

client = TestClient(app)

def auth(org='v03-test'):
    return {'X-Organization-ID': org, 'X-API-Key': 'test-secret'}

def new_character(org='v03-test'):
    res = client.post('/characters', headers=auth(org), json={'name':'قمر'})
    assert res.status_code == 201, res.text
    cid = res.json()['id']
    res = client.post(f'/characters/{cid}/identity', headers=auth(org), json={'appearance':'An original imaginary female adult character with red hair'})
    assert res.status_code == 201, res.text
    return cid, res.json()['id']

def test_prepare_snapshot_and_tenant_isolation(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('RUNWAYML_API_SECRET', raising=False)
    monkeypatch.delenv('ENABLE_PAID_GENERATION', raising=False)
    cid, ident = new_character('snapshots')
    r = client.post(f'/characters/{cid}/jobs', headers=auth('snapshots'), json={'media_type':'image','scene':'A sunny Baghdad street'})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job['status'] == 'prepared' and job['identity_id'] == ident
    assert 'red hair' in job['prompt']
    newest = client.post(f'/characters/{cid}/identity', headers=auth('snapshots'), json={'appearance':'A new fictional character with blue hair'})
    assert newest.status_code == 201
    old = client.get(f'/jobs/{job["id"]}', headers=auth('snapshots')).json()
    assert old['identity_id'] == ident and 'red hair' in old['prompt'] and 'blue hair' not in old['prompt']
    assert client.get(f'/jobs/{job["id"]}', headers=auth('other')).status_code == 404
    assert client.get(f'/characters/{cid}/jobs', headers=auth('other')).status_code == 404
    assert client.post(f'/jobs/{job["id"]}/submit', headers=auth('snapshots')).status_code == 503
    assert client.get(f'/jobs/{job["id"]}', headers=auth('snapshots')).json()['status'] == 'prepared'


def test_reference_restricted_to_identity_version(tmp_path,monkeypatch):
    monkeypatch.setattr(production, 'MEDIA_DIR', tmp_path)
    import app.main as main
    monkeypatch.setattr(main, 'MEDIA_DIR', tmp_path)
    cid, ident = new_character('ref-org')
    img = Image.new('RGB',(64,64),'red'); bio=BytesIO();img.save(bio,format='PNG')
    response=client.post(f'/characters/{cid}/references',headers=auth('ref-org'),files={'file':('ref.png',bio.getvalue(),'image/png')})
    assert response.status_code==201, response.text
    ref_id=response.json()['id']
    okay=client.post(f'/characters/{cid}/jobs', headers=auth('ref-org'),json={'media_type':'video','scene':'Moves in a simple studio','reference_asset_id':ref_id,'duration':5})
    assert okay.status_code==201,okay.text
    assert okay.json()['reference_asset_id']==ref_id
    client.post(f'/characters/{cid}/identity',headers=auth('ref-org'),json={'appearance':'Another version with a different costume'})
    invalid=client.post(f'/characters/{cid}/jobs',headers=auth('ref-org'),json={'media_type':'video','scene':'Moves in a simple studio','reference_asset_id':ref_id})
    assert invalid.status_code==404
    assert client.post(f'/characters/{cid}/jobs',headers=auth('ref-org'),json={'media_type':'video','scene':'Moves in a simple studio','duration':7}).status_code==422


def test_paid_submission_explicit_and_idempotent(monkeypatch,tmp_path):
    monkeypatch.setattr(production,'MEDIA_DIR',tmp_path)
    import app.main as main
    monkeypatch.setattr(main,'MEDIA_DIR',tmp_path)
    cid,_=new_character('pay-org')
    job=client.post(f'/characters/{cid}/jobs',headers=auth('pay-org'),json={'media_type':'image','scene':'A sunny urban park'}).json()
    monkeypatch.setenv('ENABLE_PAID_GENERATION','true')
    monkeypatch.setenv('OPENAI_API_KEY','example-not-real-secret')
    calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):
            import base64
            image=Image.new('RGB',(64,64),'blue');f=BytesIO();image.save(f,format='PNG')
            return {'data':[{'b64_json':base64.b64encode(f.getvalue()).decode()}]}
    def fake_post(url,**kwargs):
        calls.append(url)
        assert 'Authorization' in kwargs['headers']
        return Response()
    monkeypatch.setattr(production.httpx,'post',fake_post)
    first=client.post(f'/jobs/{job["id"]}/submit',headers=auth('pay-org'))
    assert first.status_code==200,first.text
    assert first.json()['status']=='completed' and first.json()['output_asset_id']
    assert len(calls)==1
    assert client.post(f'/jobs/{job["id"]}/submit',headers=auth('pay-org')).status_code==409
    review=client.post(f'/jobs/{job["id"]}/review',headers=auth('pay-org'),json={'face':True,'hair':True,'wardrobe':False,'style':True,'notes':'Looks similar'})
    assert review.status_code==201 and review.json()['score']==75
    assert review.json()['method']=='human_checklist'
    assert client.get(f'/jobs/{job["id"]}/reviews',headers=auth('other')).status_code==404


def test_video_runway_job_lifecycle_with_no_real_provider_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(production,'MEDIA_DIR',tmp_path)
    monkeypatch.setenv('ENABLE_PAID_GENERATION','true')
    monkeypatch.setenv('RUNWAYML_API_SECRET','test-placeholder')
    cid,_=new_character('runway-org')
    job=client.post(f'/characters/{cid}/jobs',headers=auth('runway-org'),json={'media_type':'video','scene':'Walking in a city','duration':5}).json()
    class Response:
        def __init__(self, payload):self.payload=payload
        def raise_for_status(self):pass
        def json(self):return self.payload
    monkeypatch.setattr(production.httpx,'post',lambda url,**kwargs:Response({'id':'fake-task-1'}))
    queued=client.post(f'/jobs/{job["id"]}/submit',headers=auth('runway-org'))
    assert queued.status_code==200 and queued.json()['status']=='queued'
    monkeypatch.setattr(production.httpx,'get',lambda url,**kwargs:Response({'status':'RUNNING'}))
    assert client.post(f'/jobs/{job["id"]}/refresh',headers=auth('runway-org')).json()['status']=='processing'
    monkeypatch.setattr(production.httpx,'get',lambda url,**kwargs:Response({'status':'FAILED'}))
    failed=client.post(f'/jobs/{job["id"]}/refresh',headers=auth('runway-org'))
    assert failed.status_code==200 and failed.json()['status']=='failed'
    assert client.get(f'/jobs/{job["id"]}/video',headers=auth('runway-org')).status_code==404


def test_trusted_output_host_filter():
    assert production.trusted_runway_output('https://abc.cloudfront.net/file.mp4?signature=abc')
    assert not production.trusted_runway_output('http://abc.cloudfront.net/file.mp4')
    assert not production.trusted_runway_output('https://cloudfront.net.attacker.example/file.mp4')
    assert not production.trusted_runway_output('https://127.0.0.1/file.mp4')
    assert not production.trusted_runway_output('https://user:pass@abc.cloudfront.net/file.mp4')
