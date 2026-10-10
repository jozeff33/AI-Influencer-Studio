"""V0.4 Story Engine: additive, tenant-scoped story bibles, serialized episodes,
reel shot boards, opt-in unattended preparation and explicit paid media caps.

IMPORTANT: Local prototype only. Run exactly one autopilot worker.  API-key / tenant
headers are NOT production authentication. Never auto-publish to social networks.
"""
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import Base, Character, IdentityVersion, MediaAsset, Project, MEDIA_DIR, app, checked_character, db, engine, make_prompt, tenant
from .production import GenerationJob, find_identity, image_generate, video_submit, paid_enabled
from . import production

router = APIRouter()

class StoryBible(Base):
    __tablename__ = 'story_bibles'
    __table_args__ = (UniqueConstraint('organization_id', 'character_id', name='uq_story_bible_character'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey('characters.id'), index=True)
    origin: Mapped[str] = mapped_column(Text, default='')
    ambitions: Mapped[str] = mapped_column(Text, default='')
    relationships: Mapped[str] = mapped_column(Text, default='')
    habits: Mapped[str] = mapped_column(Text, default='')
    challenges: Mapped[str] = mapped_column(Text, default='')
    setting: Mapped[str] = mapped_column(Text, default='بغداد')
    tone: Mapped[str] = mapped_column(String(40), default='درامي دافئ')
    canon_notes: Mapped[str] = mapped_column(Text, default='')
    auto_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_writer_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_media_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_paid_job_limit: Mapped[int] = mapped_column(Integer, default=0)
    cadence_hours: Mapped[int] = mapped_column(Integer, default=24)
    shots_per_reel: Mapped[int] = mapped_column(Integer, default=3)
    last_advanced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class StoryEpisode(Base):
    __tablename__ = 'story_episodes'
    __table_args__ = (UniqueConstraint('story_id', 'number', name='uq_story_episode_number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey('story_bibles.id'), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey('characters.id'))
    number: Mapped[int] = mapped_column(Integer)
    chapter: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(180))
    hook: Mapped[str] = mapped_column(Text)
    script: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text)
    memory_before: Mapped[str] = mapped_column(Text, default='')
    memory_after: Mapped[str] = mapped_column(Text, default='')
    method: Mapped[str] = mapped_column(String(30), default='template')
    status: Mapped[str] = mapped_column(String(30), default='storyboard')
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey('content_projects.id'))
    reel_file_name: Mapped[str | None] = mapped_column(String(90), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class StoryShot(Base):
    __tablename__ = 'story_shots'
    __table_args__ = (UniqueConstraint('episode_id', 'sequence', name='uq_story_shot_sequence'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    episode_id: Mapped[str] = mapped_column(String(36), ForeignKey('story_episodes.id'), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    scene: Mapped[str] = mapped_column(Text)
    narration: Mapped[str] = mapped_column(Text)
    identity_id: Mapped[str] = mapped_column(String(36), ForeignKey('identity_versions.id'))
    image_job_id: Mapped[str] = mapped_column(String(36), ForeignKey('generation_jobs.id'))
    video_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

class PaidUsage(Base):
    __tablename__ = 'story_paid_usage'
    __table_args__ = (UniqueConstraint('job_id', name='uq_story_paid_job'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    story_id: Mapped[str] = mapped_column(String(36), ForeignKey('story_bibles.id'), index=True)
    job_id: Mapped[str] = mapped_column(String(36))
    utc_date: Mapped[str] = mapped_column(String(10), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

# Add only new tables: keeps all V0.1–V0.3 rows, UUIDs, media, and Docker volumes.
Base.metadata.create_all(engine, checkfirst=True)

class StoryConfig(BaseModel):
    origin: str = Field(min_length=5, max_length=2500)
    ambitions: str = Field(min_length=3, max_length=1800)
    relationships: str = Field(default='', max_length=1800)
    habits: str = Field(default='', max_length=1800)
    challenges: str = Field(default='', max_length=1800)
    setting: str = Field(default='بغداد', max_length=180)
    tone: str = Field(default='درامي دافئ', max_length=40)
    canon_notes: str = Field(default='', max_length=1800)
    auto_enabled: bool = False
    ai_writer_enabled: bool = False
    paid_media_enabled: bool = False
    daily_paid_job_limit: int = Field(default=0, ge=0, le=20)
    cadence_hours: int = Field(default=24, ge=1, le=168)
    shots_per_reel: int = Field(default=3, ge=2, le=6)

class CreateEpisodes(BaseModel):
    count: int = Field(default=1, ge=1, le=3)

class StoryScriptResult(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    hook: str = Field(min_length=8, max_length=300)
    script: str = Field(min_length=30, max_length=6000)
    caption: str = Field(min_length=10, max_length=1200)
    lasting_event: str = Field(min_length=12, max_length=500)
    shots: list[str] = Field(min_length=2, max_length=6)

CHAPTERS = [
 ('النشأة', 'أول أيامها واكتشاف العالم من حولها', 'أريد أن أعرف من أين تبدأ قصتي'),
 ('البيت والعائلة', 'الذكريات الأولى والعلاقات التي تشكّلها', 'بعض الأشياء الصغيرة تصبح أعظم الذكريات'),
 ('عادات اليوم', 'المائدة والطعام والهوايات والروتين', 'تبدأ القصص الكبيرة بتفاصيل يوم عادي'),
 ('أول حلم', 'اختيار حلم قد يبدو بعيد المنال', 'ماذا لو أعطيت الحلم فرصة واحدة؟'),
 ('أول محاولة', 'خطوة عملية نحو تحقيق الحلم', 'الخطوة الأولى لا تبدو مثالية أبداً'),
 ('العقبة', 'ظهور تحدٍ واقعي غير مؤذٍ يعقّد الطريق', 'ظننت أن الأمور ستكون أسهل من ذلك'),
 ('الإخفاق', 'تجربة لا تنجح وتمنحها شيئاً لتتعلمه', 'لم يحدث ما خططت له... ولكن القصة لم تنتهِ'),
 ('التعلّم', 'تغيير أسلوبها والاستفادة من الخطأ', 'اكتشفت أن الخطأ قد يعلمني شيئاً جديداً'),
 ('النجاح الصغير', 'تحقيق تقدم محدود لكنه مهم', 'أحياناً تكفي خطوة واحدة لنرى الفرق'),
 ('تحدٍ جديد', 'بداية فصل جديد بعد النجاح والتغيير', 'كل نهاية جميلة يمكن أن تصبح بداية أخرى'),
]

def story_out(s: StoryBible):
    return {k: getattr(s,k) for k in ('id','character_id','origin','ambitions','relationships','habits','challenges','setting','tone','canon_notes','auto_enabled','ai_writer_enabled','paid_media_enabled','daily_paid_job_limit','cadence_hours','shots_per_reel')}

def checked_story(session:Session,org:str,cid:str):
    checked_character(session,org,cid)
    obj=session.scalar(select(StoryBible).where(StoryBible.character_id==cid, StoryBible.organization_id==org))
    if obj is None: raise HTTPException(404,'Create the character story bible first')
    return obj

def episode_out(e:StoryEpisode, shots:list[StoryShot]):
    return {'id':e.id,'character_id':e.character_id,'number':e.number,'chapter':e.chapter,'title':e.title,'hook':e.hook,
            'script':e.script,'caption':e.caption,'memory_before':e.memory_before,'memory_after':e.memory_after,
            'method':e.method,'status':e.status,'approved':e.approved,'project_id':e.project_id,
            'reel_url': f'/story/episodes/{e.id}/reel' if e.reel_file_name else None,
            'created_at':e.created_at.isoformat(),
            'shots':[{'sequence':x.sequence,'scene':x.scene,'narration':x.narration,'identity_id':x.identity_id,
                      'image_job_id':x.image_job_id,'video_job_id':x.video_job_id} for x in shots]}

def episode_with_shots(session,e):
    shots=session.scalars(select(StoryShot).where(StoryShot.episode_id==e.id,StoryShot.organization_id==e.organization_id).order_by(StoryShot.sequence)).all()
    return episode_out(e, shots)

def usage_today(session:Session, story:StoryBible)->int:
    today=datetime.now(timezone.utc).date().isoformat()
    return session.scalar(select(func.count()).select_from(PaidUsage).where(PaidUsage.story_id==story.id,PaidUsage.utc_date==today)) or 0

def llm_allowed(story:StoryBible, session:Session | None=None)->bool:
    enabled=(story.ai_writer_enabled and story.daily_paid_job_limit>0 and
             os.getenv('STORY_AI_WRITER_ENABLED','false').lower()=='true' and paid_enabled() and
             bool(os.getenv('OPENAI_API_KEY','').strip()))
    return enabled and (session is None or usage_today(session,story)<story.daily_paid_job_limit)

def ai_script(story:StoryBible, character:Character, number:int, chapter:str, topic:str, memory:str) -> StoryScriptResult:
    count=story.shots_per_reel
    prompt=(f'اسم شخصية افتراضية خيالية: {character.name}. الهوية: {character.persona}. '
      f'قصة حياتها: {story.origin}. هدفها: {story.ambitions}. علاقاتها: {story.relationships}. '
      f'العادات والطعام: {story.habits}. العقبات: {story.challenges}. موقع القصة: {story.setting}. '
      f'الطابع: {story.tone}. حقائق ثابتة: {story.canon_notes}. '
      f'الذاكرة السابقة: {memory[-4000:]}. رقم الحلقة: {number}، عنوان الفصل: {chapter}، موضوعه: {topic}. '
      f'اكتب حلقة Reels قصيرة متسلسلة لها خطاف في البداية، حدث، عائق أو تغير، نتيجة مشوقة وخاتمة تدعو للمتابعة. '
      f'أضف لحظات يومية متنوعة وطعام وهوايات وعلاقات، وراعِ اتساق الأحداث وعدم تكرار الحلقات. '
      f'أرجع JSON فقط بمفاتيح title,hook,script,caption,lasting_event,shots. '
      f'في shots عدد عناصر بالضبط {count}، كل عنصر وصف مشهد تصوير رأسي 9:16 مع حركة كاميرا لطيفة. '
      'لا تنسب الشخصية إلى شخص واقعي، لا تستخدم أحداثاً مفزعة أو تفاصيل بالغة، ولا توهم بأنها بشرية حقيقية. '
      'اختم الوصف بأن الشخصية افتراضية مُنشأة بالذكاء الاصطناعي.')
    response=httpx.post('https://api.openai.com/v1/chat/completions',
      headers={'Authorization':'Bearer '+os.getenv('OPENAI_API_KEY',''),'Content-Type':'application/json'},
      json={'model':os.getenv('STORY_TEXT_MODEL','gpt-4.1-mini'), 'temperature':0.75,
            'response_format':{'type':'json_object'},'messages':[
              {'role':'system','content':'أنت كاتب حلقات أصلية قصيرة لشخصية افتراضية. أرجع JSON صالحاً فقط ولا تغيّر حقائق الذاكرة.'},
              {'role':'user','content':prompt}]},timeout=55)
    response.raise_for_status()
    parsed=StoryScriptResult.model_validate_json(response.json()['choices'][0]['message']['content'])
    if len(parsed.shots)!=count: raise ValueError('Script produced wrong number of shots')
    return parsed

def template_script(story:StoryBible, c:Character, number:int, chapter:str, topic:str, memory:str)->StoryScriptResult:
    """Offline draft writer for free previews; AI writer makes more natural variations."""
    ambition=story.ambitions.strip();setting=story.setting.strip() or 'بغداد'
    habit=story.habits.strip() or 'فطور بسيط وقراءة قصيرة'
    friends=story.relationships.strip() or 'مجموعة من الأصدقاء الخياليين'
    challenge=story.challenges.strip() or 'الخوف من خوض تجربة جديدة'
    stages=[
      ('المنزل الأول',f'تتذكر بدايتها في {setting}، وكيف بدأت اهتماماتها الأولى.',f'كانت تفاصيل نشأتها: {story.origin}', 'اختارت أن تسرد ذكرياتها بالتفصيل'),
      ('وجوه مألوفة',f'تقضي وقتاً مع {friends}.', 'تكتشف كيف تؤثر العلاقات على قراراتها.', 'تتعلم أن الاستماع جزء من الصداقة'),
      ('صباح عادي',f'تبدأ صباحها مع {habit}.', 'تلاحظ أن الروتين يمكن أن يخفي فرصة جديدة.', 'تقرر أن تغير شيئاً صغيراً في يومها'),
      ('ورقة أحلام',f'تكتب هدفها الواضح: {ambition}.', 'تخشى أن يكون الحلم أكبر من إمكانياتها الحالية.', 'تقسم الحلم إلى أول خطوة قابلة للتنفيذ'),
      ('المحاولة الأولى',f'تجرب خطوة فعلية في اتجاه {ambition}.', f'تواجه صعوبة مرتبطة بـ {challenge}.', 'تستمر رغم عدم كمال التجربة'),
      ('اللحظة الصعبة',f'تسير الأمور بعكس الخطة في {setting}.', f'يصبح {challenge} عائقاً جدياً.', 'تبدأ البحث عن رأي ومساعدة'),
      ('يوم لم ينجح', 'تعترف بأن نتيجتها الأولى لم تحقق ما تريد.', 'لا تتسرع في لوم نفسها أو الاستسلام.', 'تسجل الخطأ لتستفيد منه في المحاولة الجديدة'),
      ('الدروس الجديدة', f'تعود إلى {friends} وتحاول فهم سبب التعثر.', 'تغير طريقة العمل وتعيد ترتيب أولوياتها.', 'تجرب حلولاً أصغر وأكثر واقعية'),
      ('أول إنجاز', f'تنجز جزءاً صغيراً من {ambition}.', 'تحتفل بتقدمها من دون ادعاء الكمال.', 'تفكر في الخطوة التالية وكيف تساعد غيرها'),
      ('فصل قادم',f'توازن بين {habit} والعمل على {ambition}.', 'تظهر لها فرصة جديدة مختلفة عن السابقة.', 'تقرر توثيق فصل جديد في حياتها'),
    ]
    place,action,conflict,outcome=stages[(number-1)%len(stages)]
    previous_hint='وفي الحلقة السابقة، تعلمت شيئاً جديداً...' if number>1 else 'هذه هي بداية حكايتها الخيالية.'
    hook=f'هل ستنجح {c.name} في {chapter}؟'
    script=(f'مشهد افتتاحي: {previous_hint} اليوم: {chapter}. '
       f'{c.name} تبدأ من {place}. {action} {conflict} {outcome}. '
       f'تسأل المتابعين: كيف ستتغير حياتي في الحلقة القادمة؟ '
       'تنويه: هذه شخصية افتراضية وقصتها من صنع الخيال والذكاء الاصطناعي.')
    base=[
      f'فيديو عمودي 9:16، لقطة افتتاحية لشخصية {c.name} في {place} بمدينة {setting}، بداية فصل {chapter}، ثبات الوجه، تصوير سينمائي واقعي',
      f'فيديو عمودي 9:16، لقطة متوسطة من يوم {c.name}: {action}، تفاعل طبيعي مع البيئة وإضاءة مناسبة',
      f'فيديو عمودي 9:16، لقطة تعبيرية للموقف المحوري: {conflict}، نفس الملامح والهوية البصرية',
      f'فيديو عمودي 9:16، لقطة تقدم وحل صغير: {outcome}، حركة كاميرا هادئة وبقاء الشخصية ثابتة',
      f'فيديو عمودي 9:16، تفاصيل الطعام والروتين والعلاقات: {habit}، {friends}، دون تغيير الشخصية الرئيسية',
      f'فيديو عمودي 9:16، نهاية مشوقة لحلقة {number} في {setting}، وتلميح إلى الخطوة القادمة',
    ]
    # Distribute additional shots without losing opening/conflict/conclusion at lower counts.
    chosen=[base[0],base[2],base[-1]] if story.shots_per_reel==3 else ([base[0],base[-1]] if story.shots_per_reel==2 else base[:story.shots_per_reel])
    return StoryScriptResult(title=f'{chapter}: {place} — الحلقة {number}',hook=hook,script=script,
      caption=f'الحلقة {number} | {chapter} ✨ قصة شخصية افتراضية بالذكاء الاصطناعي. الحكاية مستمرة... #قصة_افتراضية #AI',
      lasting_event=f'الحلقة {number}: {action[:200]} {outcome[:170]}',
      shots=chosen)

def create_episode(session:Session,story:StoryBible, use_ai:bool=True):
    c=checked_character(session,story.organization_id,story.character_id)
    ident=find_identity(session,story.organization_id,c.id,None)
    number=(session.scalar(select(func.max(StoryEpisode.number)).where(StoryEpisode.story_id==story.id)) or 0)+1
    chapter,topic,_=CHAPTERS[(number-1)%len(CHAPTERS)]
    prev=session.scalar(select(StoryEpisode).where(StoryEpisode.story_id==story.id).order_by(StoryEpisode.number.desc()).limit(1))
    memory=(prev.memory_after if prev else f'الأصل: {story.origin}. الهدف: {story.ambitions}. الثوابت: {story.canon_notes}')
    method='template'; result=None
    if use_ai and llm_allowed(story,session):
        # Debit the daily CALL cap before requesting the provider; crashes must not retry/bill twice.
        session.add(PaidUsage(id=str(uuid.uuid4()),organization_id=story.organization_id,
                   story_id=story.id,job_id='writing-'+str(uuid.uuid4()),
                   utc_date=datetime.now(timezone.utc).date().isoformat()))
        session.commit()
        try:
            result=ai_script(story,c,number,chapter,topic,memory)
            method='ai'
        except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError):
            method='template_fallback'
    if result is None: result=template_script(story,c,number,chapter,topic,memory)
    # Keep context bounded without deleting older episode records.
    after=(memory+'\n'+result.lasting_event)[-4500:]
    eid=str(uuid.uuid4()); pid=str(uuid.uuid4())
    e=StoryEpisode(id=eid,organization_id=story.organization_id,story_id=story.id,character_id=c.id,
                   number=number,chapter=chapter,title=result.title,hook=result.hook,
                   script=result.script,caption=result.caption,memory_before=memory[-4500:],
                   memory_after=after,method=method,project_id=pid)
    session.add(Project(id=pid,organization_id=story.organization_id,character_id=c.id,
                        title=f'ريلز {number}: {result.title}',script=result.script,status='draft'))
    session.add(e)
    # Prefer previously-uploaded reference bound to exactly this version.
    asset=session.scalar(select(MediaAsset).where(MediaAsset.organization_id==story.organization_id,
      MediaAsset.character_id==c.id,MediaAsset.identity_id==ident.id,
      MediaAsset.kind=='reference').order_by(MediaAsset.created_at.desc()).limit(1))
    for ix,scene in enumerate(result.shots,1):
        jid=str(uuid.uuid4()); full_scene=f'حلقة {number} — فصل {chapter}. {scene}. {result.hook}'
        session.add(GenerationJob(id=jid,organization_id=story.organization_id,
                character_id=c.id,identity_id=ident.id,reference_asset_id=asset.id if asset else None,
                media_type='image',provider='openai',model=os.getenv('IMAGE_MODEL','gpt-image-1-mini'),
                scene=full_scene,prompt_snapshot=make_prompt(c,ident,full_scene),status='prepared',duration=5,ratio='720:1280'))
        session.add(StoryShot(id=str(uuid.uuid4()),organization_id=story.organization_id,episode_id=eid,
                 sequence=ix,scene=scene,narration=result.script,identity_id=ident.id,image_job_id=jid))
    story.last_advanced_at=datetime.now(timezone.utc)
    session.commit()
    return episode_with_shots(session,e)

def story_stats(session:Session,story:StoryBible):
    used=usage_today(session,story)
    return {'used_today':used,'remaining_today':max(0,story.daily_paid_job_limit-used),
      'ai_writing_available':llm_allowed(story,session),
      'auto_paid_available':can_autopay(story),
      'scheduler_enabled':story.auto_enabled}

def can_autopay(story:StoryBible):
    return (story.paid_media_enabled and story.daily_paid_job_limit>0 and paid_enabled()
            and os.getenv('STORY_AUTO_PAID_MEDIA_ENABLED','false').lower()=='true')

@router.get('/characters/{character_id}/story')
def get_story(character_id:str,org:str=Depends(tenant),session:Session=Depends(db)):
    s=checked_story(session,org,character_id)
    return {'bible':story_out(s),'stats':story_stats(session,s)}

@router.put('/characters/{character_id}/story')
def upsert_story(character_id:str,data:StoryConfig,org:str=Depends(tenant),session:Session=Depends(db)):
    checked_character(session,org,character_id)
    s=session.scalar(select(StoryBible).where(StoryBible.character_id==character_id,StoryBible.organization_id==org))
    if s is None:
        s=StoryBible(id=str(uuid.uuid4()),organization_id=org,character_id=character_id)
        session.add(s)
    for k,v in data.model_dump().items(): setattr(s,k,v)
    session.commit()
    return {'bible':story_out(s),'stats':story_stats(session,s)}

@router.get('/characters/{character_id}/story/episodes')
def list_episodes(character_id:str,org:str=Depends(tenant),session:Session=Depends(db)):
    s=checked_story(session,org,character_id)
    eps=session.scalars(select(StoryEpisode).where(StoryEpisode.story_id==s.id,StoryEpisode.organization_id==org)
            .order_by(StoryEpisode.number.desc()).limit(100)).all()
    return [episode_with_shots(session,e) for e in eps]

@router.post('/characters/{character_id}/story/episodes/next',status_code=201)
def next_episodes(character_id:str,data:CreateEpisodes,org:str=Depends(tenant),session:Session=Depends(db)):
    s=checked_story(session,org,character_id)
    return [create_episode(session,s) for _ in range(data.count)]

@router.post('/characters/{character_id}/story/autopilot/tick')
def manual_tick(character_id:str,org:str=Depends(tenant),session:Session=Depends(db)):
    s=checked_story(session,org,character_id)
    # This endpoint performs one local tick, never pays or publishes.
    return {'created': maybe_advance(session,s,require_enabled=True),'stats':story_stats(session,s)}

@router.post('/story/episodes/{episode_id}/approve')
def approve_episode(episode_id:str,org:str=Depends(tenant),session:Session=Depends(db)):
    e=checked_episode(session,org,episode_id)
    e.approved=True;session.commit()
    return episode_with_shots(session,e)

@router.get('/story/episodes/{episode_id}/reel')
def get_reel(episode_id:str,org:str=Depends(tenant),session:Session=Depends(db)):
    e=checked_episode(session,org,episode_id)
    if not e.reel_file_name: raise HTTPException(404,'Reel not assembled yet')
    file=MEDIA_DIR/e.reel_file_name
    if not file.is_file(): raise HTTPException(404,'Reel file missing')
    return FileResponse(file,media_type='video/mp4',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

def checked_episode(session,org,episode_id):
    e=session.scalar(select(StoryEpisode).where(StoryEpisode.id==episode_id,StoryEpisode.organization_id==org))
    if e is None: raise HTTPException(404,'Episode not found')
    return e

def maybe_advance(session,s:StoryBible,require_enabled:bool=True):
    if require_enabled and not s.auto_enabled: return None
    now=datetime.now(timezone.utc)
    last=s.last_advanced_at
    if last is not None:
        if last.tzinfo is None: last=last.replace(tzinfo=timezone.utc)
        if now-last<timedelta(hours=s.cadence_hours): return None
    return create_episode(session,s)

def prepare_next_video(session,story:StoryBible,shot:StoryShot):
    if shot.video_job_id: return
    img=session.scalar(select(GenerationJob).where(GenerationJob.id==shot.image_job_id,GenerationJob.organization_id==story.organization_id))
    if not img or img.status!='completed' or not img.output_asset_id:return
    c=checked_character(session,story.organization_id,story.character_id)
    ident=find_identity(session,story.organization_id,c.id,shot.identity_id)
    prompt=make_prompt(c,ident,shot.scene)+' Vertical short cinematic reel; consistent face, natural continuous movement.'
    job=GenerationJob(id=str(uuid.uuid4()),organization_id=story.organization_id,
       character_id=c.id,identity_id=ident.id,reference_asset_id=img.output_asset_id,
       media_type='video',provider='runway',model=os.getenv('RUNWAY_VIDEO_MODEL','gen4.5'),
       scene=shot.scene,prompt_snapshot=prompt,status='prepared',ratio='720:1280',duration=5)
    session.add(job);shot.video_job_id=job.id;session.commit()

def submit_one_paid_job(session:Session,story:StoryBible):
    """Single provider request per tick. Track quota BEFORE request to avoid charge-creating retries."""
    if not can_autopay(story):return None
    today=datetime.now(timezone.utc).date().isoformat()
    if usage_today(session,story)>=story.daily_paid_job_limit:return None
    eps=session.scalars(select(StoryEpisode).where(StoryEpisode.story_id==story.id).order_by(StoryEpisode.number)).all()
    for e in eps:
        shots=session.scalars(select(StoryShot).where(StoryShot.episode_id==e.id).order_by(StoryShot.sequence)).all()
        for sh in shots:
            for jid in (sh.image_job_id,sh.video_job_id):
                if not jid:continue
                j=session.scalar(select(GenerationJob).where(GenerationJob.id==jid,GenerationJob.organization_id==story.organization_id))
                if not j or j.status!='prepared':continue
                if not os.getenv('OPENAI_API_KEY' if j.media_type=='image' else 'RUNWAYML_API_SECRET','').strip():continue
                session.add(PaidUsage(id=str(uuid.uuid4()),organization_id=story.organization_id,
                                      story_id=story.id,job_id=j.id,utc_date=today))
                j.status='submitting';session.commit()
                try:
                    if j.media_type=='image':image_generate(session,j)
                    else:video_submit(session,j)
                    session.commit()
                except Exception:
                    # Provider exceptions must not auto-repeat a request that could have billed.
                    j.status='failed';j.error_code='AUTOPILOT_PROVIDER_FAILED';session.commit()
                return j.id
    return None

def refresh_story_videos(session,story):
    """Poll at most one pending video per cycle."""
    eps=session.scalars(select(StoryEpisode).where(StoryEpisode.story_id==story.id)).all()
    for e in eps:
        shots=session.scalars(select(StoryShot).where(StoryShot.episode_id==e.id)).all()
        for sh in shots:
            if sh.video_job_id:
                j=session.scalar(select(GenerationJob).where(GenerationJob.id==sh.video_job_id,GenerationJob.organization_id==story.organization_id))
                if j and j.status in ('queued','processing','completed_unarchived'):
                    try:production.refresh_job(j.id,org=story.organization_id,session=session)
                    except Exception:pass
                    return

def assemble_reel(session:Session,story:StoryBible,e:StoryEpisode):
    if e.reel_file_name:return
    shots=session.scalars(select(StoryShot).where(StoryShot.episode_id==e.id).order_by(StoryShot.sequence)).all()
    if not shots:return
    clips=[]
    for sh in shots:
        if not sh.video_job_id:return
        j=session.scalar(select(GenerationJob).where(GenerationJob.id==sh.video_job_id,GenerationJob.organization_id==story.organization_id))
        if not j or j.status!='completed' or not j.output_file_name:return
        clip=MEDIA_DIR/j.output_file_name
        if not clip.is_file():return
        clips.append(clip)
    # Every clip is generated in-house and has a validated, restricted file name.
    final=MEDIA_DIR/(e.id+'-reel.mp4')
    with tempfile.TemporaryDirectory() as tmp:
        concat_file=Path(tmp)/'clips.txt'
        concat_file.write_text(''.join("file '"+str(p).replace("'", "'\\''")+"'\n" for p in clips),encoding='utf-8')
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat_file),
             '-an','-vf','scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2',
             '-c:v','libx264','-preset','veryfast','-pix_fmt','yuv420p','-movflags','+faststart',str(final)]
        try:subprocess.run(cmd,timeout=180,check=True,capture_output=True)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,FileNotFoundError):
            final.unlink(missing_ok=True);return
    if final.is_file() and final.stat().st_size>0:
        e.reel_file_name=final.name;e.status='reel_ready';session.commit()

def worker_cycle(session:Session):
    """Called by dedicated opt-in single worker, never by the web server startup."""
    stories=session.scalars(select(StoryBible).where(StoryBible.auto_enabled.is_(True))).all()
    for story in stories:
        try:
            maybe_advance(session,story)
            episodes=session.scalars(select(StoryEpisode).where(StoryEpisode.story_id==story.id)).all()
            for e in episodes:
                shots=session.scalars(select(StoryShot).where(StoryShot.episode_id==e.id)).all()
                for shot in shots:prepare_next_video(session,story,shot)
            if can_autopay(story):
                submit_one_paid_job(session,story)
                refresh_story_videos(session,story)
            for e in episodes:assemble_reel(session,story,e)
        except Exception:
            session.rollback()
            # Don't let one character's error stop other stories; log without secrets.
            import logging
            logging.getLogger(__name__).exception('Story worker cycle failed for story %s', story.id)

app.include_router(router)
