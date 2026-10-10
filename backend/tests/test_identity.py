import os
from io import BytesIO
from PIL import Image
from fastapi.testclient import TestClient

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_studio.db')
os.environ.setdefault('STUDIO_DEV_API_KEY', 'test-secret')
from app.main import app
client = TestClient(app)

def auth(tenant='identity-org'):
    return {'X-Organization-ID':tenant, 'X-API-Key':'test-secret'}

def test_identity_versions_and_tenant_isolation():
    created = client.post('/characters', headers=auth(), json={'name':'قمر','persona':'شخصية افتراضية'}); assert created.status_code==201
    cid=created.json()['id']
    assert client.post(f'/characters/{cid}/prompt-preview',headers=auth(),json={'scene':'A city portrait'}).status_code==409
    ids=[]
    for appearance in ('Original fictional character with silver hair', 'Original fictional character with dark red hair'):
        res=client.post(f'/characters/{cid}/identity',headers=auth(),json={'appearance':appearance,'visual_style':'cinematic'})
        assert res.status_code==201, res.text
        ids.append(res.json()['id'])
    versions=client.get(f'/characters/{cid}/identity',headers=auth()).json()
    assert [v['version'] for v in versions]==[2,1]
    preview=client.post(f'/characters/{cid}/prompt-preview',headers=auth(),json={'scene':'A city portrait'})
    assert preview.status_code==200
    assert 'dark red hair' in preview.json()['prompt']
    assert preview.json()['identity_version']==2
    assert client.get(f'/characters/{cid}/identity',headers=auth('other-org')).status_code==404
    assert client.post(f'/characters/{cid}/identity',headers=auth('other-org'),json={'appearance':'A completely different person'}).status_code==404
    assert client.post(f'/characters/{cid}/images',headers=auth(),json={'scene':'A city portrait'}).status_code==503

def test_reference_validation_and_media_security(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'MEDIA_DIR',tmp_path)
    cid=client.post('/characters',headers=auth('media-org'),json={'name':'نور'}).json()['id']
    client.post(f'/characters/{cid}/identity',headers=auth('media-org'),json={'appearance':'An original fictional virtual influencer with warm brown hair'})
    bad=client.post(f'/characters/{cid}/references',headers=auth('media-org'),files={'file':('bad.png',b'not-an-image','image/png')})
    assert bad.status_code==415
    img=Image.new('RGB',(40,40),'navy'); buffer=BytesIO();img.save(buffer,format='PNG')
    good=client.post(f'/characters/{cid}/references',headers=auth('media-org'),files={'file':('reference.png',buffer.getvalue(),'image/png')})
    assert good.status_code==201,good.text
    aid=good.json()['id'];assert good.json()['kind']=='reference'
    assert client.get(f'/assets/{aid}',headers=auth('another')).status_code==404
    served=client.get(f'/assets/{aid}',headers=auth('media-org'))
    assert served.status_code==200 and served.headers['content-type']=='image/png'
    assert served.content==buffer.getvalue()
    assert len(client.get(f'/characters/{cid}/assets',headers=auth('media-org')).json())==1
