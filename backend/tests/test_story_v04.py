"""No real API calls. All organizations, paid gates and episodic continuity tested."""
import os
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///./test_studio.db')
os.environ.setdefault('STUDIO_DEV_API_KEY', 'test-secret')
from fastapi.testclient import TestClient
from app.main import app, SessionLocal, IdentityVersion, MediaAsset, Project
from app.story import StoryBible, StoryEpisode, StoryShot, PaidUsage, worker_cycle
from app import story
from sqlalchemy import select

client=TestClient(app)

def auth(org):return {'X-Organization-ID':org,'X-API-Key':'test-secret'}

def new_story(**settings):
    org='v04-'+str(uuid.uuid4())
    r=client.post('/characters',headers=auth(org),json={'name':'قمر','persona':'فتاة افتراضية تحب تصميم الأعمال الفنية والقراءة'})
    assert r.status_code==201,r.text
    cid=r.json()['id']
    i=client.post(f'/characters/{cid}/identity',headers=auth(org),json={'appearance':'Original adult fictional woman with short wavy dark hair and warm smile'})
    assert i.status_code==201,i.text
    cfg={'origin':'نشأت قمر في بيئة خيالية بمدينة بغداد، وبدأت تحب الرسم باكراً',
         'ambitions':'تصميم معرض لوحات افتراضي يضم فنوناً عراقية',
         'relationships':'صديقتها الافتراضية ليلى وأختها نور',
         'habits':'تتناول فطوراً عراقياً وتحب المشي والقراءة',
         'challenges':'تتعلم من إخفاقها في ترتيب معرضها الأول',
         'cadence_hours':24,'shots_per_reel':3}
    cfg.update(settings)
    put=client.put(f'/characters/{cid}/story',headers=auth(org),json=cfg)
    assert put.status_code==200,put.text
    return org,cid,i.json()['id']

def test_story_episodes_memory_scenes_snapshots_and_existing_projects(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    org,cid,ident=new_story()
    result=client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':3})
    assert result.status_code==201,result.text
    eps=result.json()
    assert [e['number'] for e in eps]==[1,2,3]
    assert [e['chapter'] for e in eps]==['النشأة','البيت والعائلة','عادات اليوم']
    assert all(len(e['shots'])==3 for e in eps)
    assert all(e['method']=='template' for e in eps)
    assert eps[0]['memory_after'] in eps[1]['memory_before']
    assert all(s['video_job_id'] is None for e in eps for s in e['shots'])
    assert all(s['identity_id']==ident for e in eps for s in e['shots'])
    projects=client.get('/projects',headers=auth(org)).json()
    assert len(projects)==3 and all(p['status']=='draft' for p in projects)
    assert client.get(f'/characters/{cid}/story/episodes',headers=auth(org)).json()[0]['number']==3
    assert client.post(f'/story/episodes/{eps[0]["id"]}/approve',headers=auth(org)).json()['approved']
    assert client.get(f'/story/episodes/{eps[0]["id"]}/reel',headers=auth(org)).status_code==404
    assert client.get(f'/story/episodes/{eps[0]["id"]}/reel',headers=auth('intruder')).status_code==404
    assert client.get(f'/characters/{cid}/story',headers=auth('intruder')).status_code==404
    assert client.post(f'/characters/{cid}/story/episodes/next',headers=auth('intruder'),json={'count':1}).status_code==404


def test_autopilot_cadence_and_no_charges_by_default(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    org,cid,_=new_story(auto_enabled=True)
    first=client.post(f'/characters/{cid}/story/autopilot/tick',headers=auth(org))
    assert first.status_code==200 and first.json()['created']['number']==1
    second=client.post(f'/characters/{cid}/story/autopilot/tick',headers=auth(org))
    assert second.status_code==200 and second.json()['created'] is None
    with SessionLocal() as session:
        worker_cycle(session)
    assert len(client.get(f'/characters/{cid}/story/episodes',headers=auth(org)).json())==1
    with SessionLocal() as session:
        assert not session.scalars(select(PaidUsage).where(PaidUsage.organization_id==org)).all()


def test_manual_episode_does_not_depend_on_autopilot(monkeypatch):
    org,cid,_=new_story(auto_enabled=False)
    assert client.post(f'/characters/{cid}/story/autopilot/tick',headers=auth(org)).json()['created'] is None
    assert client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':1}).status_code==201
    assert client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':4}).status_code==422


def test_ai_writer_limit_consumes_one_slot_and_falls_back(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','fake-not-real')
    monkeypatch.setenv('ENABLE_PAID_GENERATION','true')
    monkeypatch.setenv('STORY_AI_WRITER_ENABLED','true')
    org,cid,_=new_story(ai_writer_enabled=True,daily_paid_job_limit=1)
    calls=[]
    def fake(*args):
        calls.append(args)
        return story.StoryScriptResult(title='البداية والتجربة الأولى',hook='ماذا حدث حين خرجت قمر للمرة الأولى؟',script='قمر تبدأ رحلتها في بغداد، وتتحدث عن حلمها، وتلتقي صديقتها. ثم تتعلم شيئاً جديداً وتتطلع للمستقبل.',caption='قصة قمر الافتراضية المصنوعة بالذكاء الاصطناعي',lasting_event='بدأت قمر رحلتها في مدينة بغداد والتقت صديقتها ليلى.',shots=['افتتاح المشهد في بغداد','لقطة في حديقة','المشهد الأخير في المنزل'])
    monkeypatch.setattr(story,'ai_script',fake)
    first=client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':1})
    assert first.status_code==201,first.text
    assert first.json()[0]['method']=='ai'
    second=client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':1})
    assert second.status_code==201 and second.json()[0]['method']=='template'
    assert len(calls)==1
    stats=client.get(f'/characters/{cid}/story',headers=auth(org)).json()['stats']
    assert stats['used_today']==1 and stats['remaining_today']==0


def test_paid_autopilot_requires_three_distinct_optins_and_does_not_repeat(monkeypatch):
    org,cid,_=new_story(auto_enabled=True,paid_media_enabled=True,daily_paid_job_limit=1)
    monkeypatch.setenv('OPENAI_API_KEY','fake')
    monkeypatch.setenv('ENABLE_PAID_GENERATION','false')
    monkeypatch.setenv('STORY_AUTO_PAID_MEDIA_ENABLED','true')
    with SessionLocal() as session:worker_cycle(session)
    assert len(client.get(f'/characters/{cid}/story/episodes',headers=auth(org)).json())==1
    with SessionLocal() as session:
        assert not session.scalars(select(PaidUsage).where(PaidUsage.organization_id==org)).all()
    monkeypatch.setenv('ENABLE_PAID_GENERATION','true')
    monkeypatch.setenv('STORY_AUTO_PAID_MEDIA_ENABLED','false')
    with SessionLocal() as session:worker_cycle(session)
    with SessionLocal() as session:
        assert not session.scalars(select(PaidUsage).where(PaidUsage.organization_id==org)).all()
    monkeypatch.setenv('STORY_AUTO_PAID_MEDIA_ENABLED','true')
    processed=[]
    def fake_generate(session,job):
        processed.append(job.id);job.status='completed';job.output_asset_id='fake-output-image'
    monkeypatch.setattr(story,'image_generate',fake_generate)
    with SessionLocal() as session:worker_cycle(session)
    with SessionLocal() as session:worker_cycle(session)
    assert len(processed)==1
    with SessionLocal() as session:
        assert len(session.scalars(select(PaidUsage).where(PaidUsage.organization_id==org)).all())==1


def test_bible_edit_keeps_older_episodes_and_identity(monkeypatch):
    org,cid,ident=new_story()
    ep=client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':1}).json()[0]
    new_ident=client.post(f'/characters/{cid}/identity',headers=auth(org),json={'appearance':'An original fictional person with silver wavy hair and warm smile'}).json()
    update={'origin':'بدأت قمر قصتها في منزل مختلف، في عالمها الخيالي',
            'ambitions':'أن تتعلم الموسيقى وتصبح رسامة رقمية','shots_per_reel':2}
    assert client.put(f'/characters/{cid}/story',headers=auth(org),json=update).status_code==200
    old=client.get(f'/characters/{cid}/story/episodes',headers=auth(org)).json()[0]
    assert old['memory_after']==ep['memory_after']
    assert old['shots'][0]['identity_id']==ident
    newer=client.post(f'/characters/{cid}/story/episodes/next',headers=auth(org),json={'count':1}).json()[0]
    assert newer['shots'][0]['identity_id']==new_ident['id']
    assert len(newer['shots'])==2
