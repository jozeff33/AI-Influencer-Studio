"use client";
import {useCallback, useEffect, useRef, useState} from "react";

type Character={id:string,name:string,persona:string,language:string};
type Project={id:string,title:string,character_id:string,status:string};
type Identity={id:string,version:number,appearance:string,wardrobe:string,visual_style:string,created_at:string};
type Asset={id:string,kind:string,identity_id:string,description:string,url:string,preview?:string};
type GenerationJob={id:string,character_id:string,identity_id:string,reference_asset_id:string|null,media_type:"image"|"video",provider:string,model:string,scene:string,prompt:string,status:string,progress:number,output_asset_id:string|null,video_url:string|null,error_code:string|null};
type StoryBibleInput={origin:string,ambitions:string,relationships:string,habits:string,challenges:string,setting:string,tone:string,canon_notes:string,auto_enabled:boolean,ai_writer_enabled:boolean,paid_media_enabled:boolean,daily_paid_job_limit:number,cadence_hours:number,shots_per_reel:number};
type StoryStats={used_today:number,remaining_today:number,ai_writing_available:boolean,auto_paid_available:boolean,scheduler_enabled:boolean};
type StoryEpisode={id:string,number:number,chapter:string,title:string,hook:string,script:string,caption:string,memory_after:string,method:string,status:string,approved:boolean,reel_url:string|null,shots:{sequence:number,scene:string,narration:string,image_job_id:string,video_job_id:string|null}[]};
const blankStory:StoryBibleInput={origin:"",ambitions:"",relationships:"",habits:"",challenges:"",setting:"بغداد",tone:"درامي دافئ",canon_notes:"",auto_enabled:false,ai_writer_enabled:false,paid_media_enabled:false,daily_paid_job_limit:0,cadence_hours:24,shots_per_reel:3};
type ProviderInfo={image:{provider:string,model:string,configured:boolean,live_enabled:boolean},video:{provider:string,model:string,configured:boolean,live_enabled:boolean},notes:string};
const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";

export default function Home(){
 const [key,setKey]=useState(""); const [org,setOrg]=useState("demo");
 const [chars,setChars]=useState<Character[]>([]);const [projects,setProjects]=useState<Project[]>([]);
 const [name,setName]=useState("");const [persona,setPersona]=useState("");
 const [selected,setSelected]=useState("");const [title,setTitle]=useState("");const [script,setScript]=useState("");
 const [appearance,setAppearance]=useState("");const [wardrobe,setWardrobe]=useState("");const [visualStyle,setVisualStyle]=useState("صورة واقعية، إضاءة طبيعية، تصوير سينمائي");
 const [identity,setIdentity]=useState<Identity[]>([]);const [scene,setScene]=useState("الشخصية تقف في استوديو حديث وتنظر مباشرة إلى الكاميرا");
 const [prompt,setPrompt]=useState("");const [assets,setAssets]=useState<Asset[]>([]);const [generationEnabled,setGenerationEnabled]=useState(false);
 const [jobs,setJobs]=useState<GenerationJob[]>([]);
 const [providers,setProviders]=useState<ProviderInfo|null>(null);
 const [jobKind,setJobKind]=useState<"image"|"video">("image");
 const [jobIdentity,setJobIdentity]=useState("");
 const [jobReference,setJobReference]=useState("");
 const [jobScene,setJobScene]=useState("الشخصية تتحدث إلى الكاميرا في مشهد واقعي بإضاءة ناعمة");
 const [jobDuration,setJobDuration]=useState(5);
 const [jobRatio,setJobRatio]=useState("1280:720");
 const [reviewChecks,setReviewChecks]=useState({face:true,hair:true,wardrobe:true,style:true});
 const [reviewNotes,setReviewNotes]=useState("");
 const [storyForm,setStoryForm]=useState<StoryBibleInput>(blankStory);
 const [savedStory,setSavedStory]=useState(false);
 const [storyStats,setStoryStats]=useState<StoryStats|null>(null);
 const [episodes,setEpisodes]=useState<StoryEpisode[]>([]);
 const [episodeCount,setEpisodeCount]=useState(1);
 const [reelPreviews,setReelPreviews]=useState<Record<string,string>>({});
 const [reviewJob,setReviewJob]=useState("");
 const [videoPreviews,setVideoPreviews]=useState<Record<string,string>>({});
 const [error,setError]=useState("");const [info,setInfo]=useState("");const [busy,setBusy]=useState(false);
 const objectUrls=useRef<string[]>([]);
 const headers=useCallback(()=>({"X-API-Key":key,"X-Organization-ID":org}),[key,org]);
 const call=useCallback(async(path:string,method="GET",body?:unknown)=>{
  const resp=await fetch(API+path,{method,headers:{...headers(),"Content-Type":"application/json"},body:body!==undefined?JSON.stringify(body):undefined});
  if(!resp.ok){let detail=String(resp.status);try{const obj=await resp.json();detail=obj.detail||detail;}catch{}throw Error(`HTTP ${resp.status}: ${detail}`)}
  return resp.json();
 },[headers]);
 const refresh=useCallback(async()=>{
  if(!key.trim())return;
  try{setError("");const [c,p,providersData]=await Promise.all([call("/characters"),call("/projects"),call("/providers")]);setChars(c);setProjects(p);setProviders(providersData);
   if(c.length>0)setSelected(v=>c.some((x:Character)=>x.id===v)?v:c[0].id);
  }catch(e){setError(String(e));}
 },[key,call]);
 const loadCharacter=useCallback(async()=>{
  if(!selected||!key)return;
  try{setError("");setPrompt("");setInfo("");const [ids,files,jobList]=await Promise.all([call(`/characters/${selected}/identity`),call(`/characters/${selected}/assets`),call(`/characters/${selected}/jobs`)]);
    setJobs(jobList);setJobIdentity((before:string)=>ids.some((i:Identity)=>i.id===before)?before:(ids[0]?.id||""));
    setIdentity(ids);objectUrls.current.forEach(URL.revokeObjectURL);objectUrls.current=[];
    const previews:Asset[]=await Promise.all(files.map(async(a:Asset)=>{
     try{const r=await fetch(API+a.url,{headers:headers()});if(!r.ok)return a;
      const url=URL.createObjectURL(await r.blob());objectUrls.current.push(url);return {...a,preview:url};
     }catch{return a;}
    }));setAssets(previews);
  }catch(e){setError(String(e));}
 },[selected,key,call,headers]);
 useEffect(()=>{void loadCharacter();},[loadCharacter]);
 const loadStory=useCallback(async()=>{
  if(!selected||!key){setSavedStory(false);setEpisodes([]);setStoryStats(null);return;}
  try{
   const response=await fetch(API+`/characters/${selected}/story`,{headers:headers()});
   if(response.status===404){setSavedStory(false);setStoryForm({...blankStory});setEpisodes([]);setStoryStats(null);return;}
   if(!response.ok)throw Error("فشل تحميل السيرة: "+response.status);
   const data=await response.json();const eps=await call(`/characters/${selected}/story/episodes`);
   setSavedStory(true);setStoryForm(data.bible);setStoryStats(data.stats);setEpisodes(eps);
  }catch(e){setError(String(e));}
 },[selected,key,headers,call]);
 useEffect(()=>{void loadStory();},[loadStory]);
 useEffect(()=>()=>{objectUrls.current.forEach(URL.revokeObjectURL);},[]);
 const perform=async(fn:()=>Promise<void>)=>{setBusy(true);setError("");setInfo("");try{await fn();}catch(e){setError(String(e));}finally{setBusy(false);}};
 const addCharacter=()=>perform(async()=>{const c=await call("/characters","POST",{name,persona});setName("");setPersona("");await refresh();setSelected(c.id);setInfo("تم حفظ الشخصية");});
 const addProject=()=>perform(async()=>{await call("/projects","POST",{character_id:selected,title,script});setTitle("");setScript("");await refresh();setInfo("تم حفظ المسودة");});
 const addIdentity=()=>perform(async()=>{await call(`/characters/${selected}/identity`,"POST",{appearance,wardrobe,visual_style:visualStyle});setAppearance("");setWardrobe("");await loadCharacter();setInfo("تم حفظ إصدار هوية جديد دون حذف الإصدارات السابقة");});
 const preview=()=>perform(async()=>{const result=await call(`/characters/${selected}/prompt-preview`,"POST",{scene});setPrompt(result.prompt);setGenerationEnabled(result.generation_enabled);setInfo(`الهوية المستخدمة: الإصدار ${result.identity_version}`);});
 const generate=()=>perform(async()=>{await call(`/characters/${selected}/images`,"POST",{scene});await loadCharacter();setInfo("تم إنشاء الصورة وحفظها في المكتبة");});
 const upload=(file?:File)=>{if(!file)return;void perform(async()=>{
  const data=new FormData();data.append("file",file);
  const result=await fetch(API+`/characters/${selected}/references`,{method:"POST",headers:headers(),body:data});
  if(!result.ok){const body=await result.json().catch(()=>({detail:"تعذر الرفع"}));throw Error(body.detail||"تعذر الرفع");}
  await loadCharacter();setInfo("تم حفظ الصورة المرجعية");
 });};
 const prepareJob=()=>perform(async()=>{
  const job=await call(`/characters/${selected}/jobs`,"POST",{media_type:jobKind,scene:jobScene,identity_id:jobIdentity||null,reference_asset_id:jobReference||null,duration:jobDuration,ratio:jobRatio});
  await loadCharacter();setInfo(`تم تجهيز المهمة ${job.media_type} وربطها بإصدار هوية ثابت. لم يتم استهلاك رصيد مدفوع.`);
 });
 const submitJob=(id:string)=>{if(!window.confirm("هل توافق على إرسال مهمة التوليد إلى مزود خارجي؟ قد تترتب رسوم على الطلب."))return;
  void perform(async()=>{await call(`/jobs/${id}/submit`,"POST");await loadCharacter();setInfo("تم تنفيذ / إرسال المهمة، راقب حالتها بالأسفل.");});};
 const refreshJob=(id:string)=>perform(async()=>{await call(`/jobs/${id}/refresh`,"POST");await loadCharacter();setInfo("تم تحديث حالة الفيديو.");});
 const openVideo=(id:string)=>perform(async()=>{const r=await fetch(API+`/jobs/${id}/video`,{headers:headers()});if(!r.ok)throw Error("تعذر تحميل الفيديو");const blob=await r.blob();if(blob.size>125*1024*1024)throw Error("الفيديو أكبر من الحد المعروض");
  const url=URL.createObjectURL(blob);objectUrls.current.push(url);setVideoPreviews(v=>({...v,[id]:url}));});
 const reviewResult=(id:string)=>perform(async()=>{await call(`/jobs/${id}/review`,"POST",{...reviewChecks,notes:reviewNotes});setReviewJob("");setReviewNotes("");setInfo("تم حفظ تقييم بشري لثبات الملامح. لا يمثل هذا التقييم قياساً آلياً.");});
 const saveStory=()=>{
  if(storyForm.paid_media_enabled&&!window.confirm("تفعيل تجهيز/إرسال إنتاجات مدفوعة تلقائياً قد يستهلك رصيداً فعلياً عند تفعيل إعدادات الخادم. هل توافق؟"))return;
  void perform(async()=>{const result=await call(`/characters/${selected}/story`,"PUT",storyForm);setSavedStory(true);setStoryStats(result.stats);await loadStory();setInfo("تم حفظ عالم الشخصية. لن تبدأ المدفوعات تلقائياً دون مفاتيح الخدمة ومفاتيح تمكينها على الخادم.");});
 };
 const nextEpisode=()=>perform(async()=>{await call(`/characters/${selected}/story/episodes/next`,"POST",{count:episodeCount});await loadStory();setInfo("تم كتابة الحلقة وحفظ الذاكرة وتجهيز مشاهد الصور تلقائياً؛ لا توجد طلبات توليد مدفوعة.");});
 const storyTick=()=>perform(async()=>{const r=await call(`/characters/${selected}/story/autopilot/tick`,"POST");await loadStory();setInfo(r.created?"تم إنشاء حلقة تلقائياً":"لم تُنشأ حلقة: التأليف الآلي متوقف أو لم يحِن موعد الحلقة التالية.");});
 const approveStoryEpisode=(id:string)=>perform(async()=>{await call(`/story/episodes/${id}/approve`,"POST");await loadStory();setInfo("تمت الموافقة الداخلية على المسودة؛ لم تنشر على أي منصة.");});
 const openReel=(id:string)=>perform(async()=>{const r=await fetch(API+`/story/episodes/${id}/reel`,{headers:headers()});if(!r.ok)throw Error("تعذر فتح الريلز");const url=URL.createObjectURL(await r.blob());objectUrls.current.push(url);setReelPreviews(v=>({...v,[id]:url}));});
 const current=chars.find(c=>c.id===selected);
 const validRefs=assets.filter(a=>a.identity_id===(jobIdentity||identity[0]?.id)&&["reference","generated"].includes(a.kind));
 return <main><header><span className="logo">✦</span><div><h1>AI Influencer Studio</h1><p>استوديو الشخصيات الافتراضية — الإصدار التجريبي V0.4</p></div></header>
  <section className="card"><h2>مساحة العمل</h2><div className="fields"><label>رمز مساحة العمل<input value={org} onChange={e=>setOrg(e.target.value)}/></label><label>مفتاح التطوير المحلي<input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder="مفتاح الملف .env"/></label><button disabled={busy||!key.trim()} onClick={()=>void refresh()}>اتصال وتحديث</button></div>
  {error&&<p className="error" role="alert">{error}</p>}{info&&<p className="success" role="status">{info}</p>}</section>
  <div className="stats"><div>الشخصيات <strong>{chars.length}</strong></div><div>مشاريع المحتوى <strong>{projects.length}</strong></div><div>الصور المحفوظة <strong>{assets.length}</strong></div></div>
  <div className="columns"><section className="card"><h2>الشخصيات</h2><label>اسم شخصية جديدة<input value={name} onChange={e=>setName(e.target.value)} placeholder="مثال: قمر"/></label><label>وصف الشخصية<textarea value={persona} onChange={e=>setPersona(e.target.value)} placeholder="الهوايات وأسلوب الكلام"/></label><button disabled={busy||!key||!name.trim()} onClick={addCharacter}>إنشاء شخصية</button>
  <h3>اختيار الشخصية النشطة</h3><select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">اختر شخصية</option>{chars.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>
  {current&&<p className="muted">{current.persona||"لم يضاف وصف للشخصية بعد"}</p>}</section>
  <section className="card"><h2>مشروع محتوى جديد</h2><label>الشخصية الحالية<input readOnly value={current?.name||"اختر شخصية أولاً"}/></label><label>عنوان الفيديو<input value={title} onChange={e=>setTitle(e.target.value)}/></label><label>السيناريو<textarea value={script} onChange={e=>setScript(e.target.value)}/></label><button disabled={busy||!selected||!title.trim()} onClick={addProject}>حفظ مسودة</button><h3>مسودات المحتوى</h3>{projects.filter(p=>p.character_id===selected).map(p=><article key={p.id}><b>{p.title}</b><small>الحالة: {p.status}</small></article>)}</section></div>
  <section className="card studio"><h2>مختبر هوية الشخصية <span className="pill">Character Identity V0.3</span></h2><p className="muted">احفظ وصفاً بصرياً ثابتاً للشخصية وإصداراته. تغيير الوصف لا يؤثر على الإصدارات السابقة.</p>
   <div className="columns"><div><label>وصف الملامح والهوية البصرية<textarea rows={4} value={appearance} onChange={e=>setAppearance(e.target.value)} placeholder="شخصية افتراضية أصلية، وصف ثابت للوجه والشعر والملامح والعمر التقريبي..."/></label><label>الملابس المعتادة<textarea rows={2} value={wardrobe} onChange={e=>setWardrobe(e.target.value)} placeholder="ملابس وستايل ثابت"/></label><label>الأسلوب البصري<input value={visualStyle} onChange={e=>setVisualStyle(e.target.value)}/></label><button disabled={busy||!selected||appearance.trim().length<10} onClick={addIdentity}>حفظ نسخة هوية جديدة</button></div>
   <div><h3>إصدارات الهوية</h3>{identity.length===0?<p className="muted">لم تُضف هوية بصرية لهذه الشخصية بعد.</p>:identity.map(i=><article key={i.id}><b>الإصدار {i.version}</b><p>{i.appearance}</p><small>{i.visual_style}</small></article>)}
   <h3>صور مرجعية (للأرشفة)</h3><p className="muted">ارفع صوراً تمتلك حق استخدامها. يمكن ربط الصورة المرجعية بمهمة توليد محددة؛ ولا يُضمن التطابق المثالي بين الصور.</p><input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy||!selected||identity.length===0} onChange={e=>{upload(e.target.files?.[0]);e.currentTarget.value="";}}/></div></div>
  </section>
  <section className="card studio"><h2>استوديو الصور</h2><p className="muted">تجهيز السيناريو يعمل بلا مفتاح خارجي. التوليد الحقيقي يتطلب ضبط OPENAI_API_KEY في ملف .env وقد يكون مدفوعاً؛ اضغط توليد فقط عند الرغبة.</p>
   <label>وصف المشهد<textarea rows={3} value={scene} onChange={e=>setScene(e.target.value)}/></label><div className="actions"><button disabled={busy||!selected||identity.length===0||scene.length<5} onClick={preview}>تجهيز وصف الصورة</button><button className="secondary" disabled={busy||!selected||identity.length===0||!generationEnabled||!providers?.image.live_enabled||!prompt} onClick={generate}>{busy?"يرجى الانتظار...":"توليد صورة وحفظها"}</button></div>
   {prompt&&<div className="prompt"><h3>الوصف الجاهز للمحرك</h3><p dir="auto">{prompt}</p>{!generationEnabled&&<small>محرك الصور غير متاح. اضبط المفتاح وفعّل السماح الصريح بالطلبات المدفوعة إن رغبت.</small>}</div>}
   <h3>مكتبة صور {current?.name||"الشخصية"}</h3><div className="gallery">{assets.map(a=><figure key={a.id}>{a.preview?<img src={a.preview} alt={a.description||"صورة الشخصية"}/>:<div className="empty-preview">تعذر عرض الصورة</div>}<figcaption>{a.kind==="reference"?"مرجع بصري":"صورة مولّدة"}</figcaption></figure>)}{assets.length===0&&<p className="muted">لا توجد صور محفوظة بعد.</p>}</div>
  </section>
  <section className="card studio"><h2>محرك ثبات الشخصية وإنتاج الصور والفيديو <span className="pill">V0.3</span></h2>
   <p className="muted">اربط كل مشهد بإصدار هوية محدد وصورة مرجعية من نفس الإصدار. تجهيز المهمة مجاني؛ الإرسال لمزود خارجي منفصل ويتطلب تفعيل الخدمات وقد يترتب عليه رسوم.</p>
   <div className="columns"><div>
    <label>نوع الإنتاج<select value={jobKind} onChange={e=>setJobKind(e.target.value as "image"|"video")}><option value="image">صورة — OpenAI</option><option value="video">فيديو — Runway</option></select></label>
    <label>إصدار الهوية (يُثبّت لكل مهمة)<select value={jobIdentity} onChange={e=>{setJobIdentity(e.target.value);setJobReference("");}}><option value="">استخدم الأحدث</option>{identity.map(i=><option key={i.id} value={i.id}>الإصدار {i.version} — {i.appearance.slice(0,55)}</option>)}</select></label>
    <label>الصورة المرجعية (اختيارية)<select value={jobReference} onChange={e=>setJobReference(e.target.value)}><option value="">بدون مرجع — وصف نصي</option>{validRefs.map(a=><option value={a.id} key={a.id}>{a.kind==="reference"?"مرجع":"صورة مولدة"} — {a.id.slice(0,8)}</option>)}</select></label>
    {jobKind==="video"&&<div className="inline-controls"><label>مدة الفيديو<select value={jobDuration} onChange={e=>setJobDuration(Number(e.target.value))}><option value={5}>5 ثوانٍ</option><option value={10}>10 ثوانٍ</option></select></label><label>أبعاد الفيديو<select value={jobRatio} onChange={e=>setJobRatio(e.target.value)}><option value="1280:720">أفقي 16:9</option><option value="720:1280">عمودي 9:16</option></select></label></div>}
    <label>المشهد المراد إنتاجه<textarea value={jobScene} onChange={e=>setJobScene(e.target.value)} rows={4}/></label>
    <button disabled={busy||!selected||!identity.length||jobScene.trim().length<5} onClick={prepareJob}>تجهيز مهمة دون رسوم</button>
   </div><div><h3>حالة مزودي الخدمة</h3>
    {(["image","video"] as const).map(type=><article key={type}><b>{type==="image"?"الصور — OpenAI":"الفيديو — Runway"}</b><p>المحرك: {providers?.[type].model||"—"}</p><small>{providers?.[type].configured?"مفتاح API مضبوط":"مفتاح API غير مضبوط"} · {providers?.[type].live_enabled?"السماح بالطلبات المدفوعة مفعل":"الطلبات المدفوعة معطلة"}</small></article>)}
    <p className="muted">لا تتوفر واجهة Sora البرمجية بعد إيقافها في سبتمبر 2026. سجل الإنتاج يعرض المهمة والأخطاء دون تسريب مفاتيح الخدمات.</p>
   </div></div>
   <h3>مهام الإنتاج لهذه الشخصية ({jobs.length})</h3>
   {jobs.length===0?<p className="muted">لم يتم تجهيز أي مهمة بعد.</p>:jobs.map(job=><article className="job-card" key={job.id}>
    <div className="job-header"><div><b>{job.media_type==="image"?"صورة":"فيديو"} — {job.provider}</b><small>الحالة: {job.status} · {job.model} · {job.id.slice(0,8)}</small></div><span className="pill">{job.progress}%</span></div>
    <p>{job.scene}</p><details><summary>الوصف المحفوظ للمحرك (Snapshot)</summary><p dir="auto">{job.prompt}</p></details>
    {job.error_code&&<p className="error">رمز المشكلة: {job.error_code}</p>}
    <div className="actions">
     {job.status==="prepared"&&<button className="secondary" disabled={busy||!providers?.[job.media_type].configured||!providers?.[job.media_type].live_enabled} onClick={()=>submitJob(job.id)}>إرسال طلب توليد مدفوع</button>}
     {job.media_type==="video"&&["queued","processing","completed_unarchived"].includes(job.status)&&<button className="secondary" disabled={busy} onClick={()=>refreshJob(job.id)}>تحديث حالة الفيديو</button>}
     {job.video_url&&<button className="secondary" disabled={busy} onClick={()=>openVideo(job.id)}>عرض الفيديو المحفوظ</button>}
     {job.status==="completed"&&<button className="secondary" onClick={()=>setReviewJob(reviewJob===job.id?"":job.id)}>فحص الثبات البصري (بشري)</button>}
    </div>
    {videoPreviews[job.id]&&<video controls className="video-preview" src={videoPreviews[job.id]}/>}
    {reviewJob===job.id&&<div className="review-panel"><p>ضع علامة على الصفات التي بقيت ثابتة عند فحص النتيجة بصرياً:</p>
      {([['face','الوجه'],['hair','الشعر'],['wardrobe','الملابس'],['style','الأسلوب']] as const).map(([field,label])=><label key={field} className="review-option"><input type="checkbox" checked={reviewChecks[field]} onChange={e=>setReviewChecks(v=>({...v,[field]:e.target.checked}))}/>{label}</label>)}
      <label>ملاحظات<textarea rows={2} value={reviewNotes} onChange={e=>setReviewNotes(e.target.value)}/></label>
      <button disabled={busy} onClick={()=>reviewResult(job.id)}>حفظ التقييم البشري</button></div>}
   </article>)}
  </section>
  <section className="card studio story-section"><h2>مخرج القصص التلقائي <span className="pill">Story Autopilot V0.4</span></h2>
   <p className="muted">أنشئ سيرة خيالية متسلسلة من النشأة إلى التجارب والتعلّم والنجاح والحياة اليومية. يحتفظ النظام بذاكرة لكل حلقة ويربط مشاهد Reels بهوية الشخصية الحالية. يتم التحضير مجاناً؛ إنتاج الصور والفيديو فعلياً يحتاج إلى مزود خدمة وتفعيل مدفوعات اختياري.</p>
   {!selected?<p className="error">اختر الشخصية أولاً.</p>:<>
    <div className="columns"><div>
     <label>البداية والنشأة (قصة خيالية)<textarea rows={3} value={storyForm.origin} onChange={e=>setStoryForm(v=>({...v,origin:e.target.value}))} placeholder="من أين بدأت الشخصية؟ من أسرتها أو بيئتها؟ وما حدث عند نشأتها؟"/></label>
     <label>الأحلام والأهداف<textarea rows={2} value={storyForm.ambitions} onChange={e=>setStoryForm(v=>({...v,ambitions:e.target.value}))} placeholder="تطمح أن تصبح صانعة محتوى أو مصممة أو رائدة أعمال..."/></label>
     <label>العائلة والأصدقاء والشخصيات المساندة<textarea rows={2} value={storyForm.relationships} onChange={e=>setStoryForm(v=>({...v,relationships:e.target.value}))}/></label>
     <label>الحياة اليومية والغذاء والهوايات<textarea rows={2} value={storyForm.habits} onChange={e=>setStoryForm(v=>({...v,habits:e.target.value}))} placeholder="الفطور، الوجبة المفضلة، الدراسة، العمل، الرياضة، التسوق..."/></label>
     <label>التحديات والإخفاقات<textarea rows={2} value={storyForm.challenges} onChange={e=>setStoryForm(v=>({...v,challenges:e.target.value}))}/></label>
    </div><div>
     <label>الموقع الأساسي<input value={storyForm.setting} onChange={e=>setStoryForm(v=>({...v,setting:e.target.value}))}/></label>
     <label>طابع القصة<input value={storyForm.tone} onChange={e=>setStoryForm(v=>({...v,tone:e.target.value}))}/></label>
     <label>الحقائق التي يجب ألا تتغير<textarea rows={2} value={storyForm.canon_notes} onChange={e=>setStoryForm(v=>({...v,canon_notes:e.target.value}))} placeholder="صفات ثابتة، أسماء أفراد الأسرة الخياليين، أي أحداث غير قابلة للتغيير"/></label>
     <div className="inline-controls"><label>عدد مشاهد كل ريلز<select value={storyForm.shots_per_reel} onChange={e=>setStoryForm(v=>({...v,shots_per_reel:Number(e.target.value)}))}>{[2,3,4,5,6].map(n=><option key={n} value={n}>{n} مشاهد × 5 ثوانٍ</option>)}</select></label><label>فاصل الحلقات<select value={storyForm.cadence_hours} onChange={e=>setStoryForm(v=>({...v,cadence_hours:Number(e.target.value)}))}>{[1,6,12,24,48,72,168].map(n=><option value={n} key={n}>{n} ساعة</option>)}</select></label></div>
     <label className="check-setting"><input type="checkbox" checked={storyForm.auto_enabled} onChange={e=>setStoryForm(v=>({...v,auto_enabled:e.target.checked}))}/> تخطيط الحلقات تلقائياً في الخلفية (بعد تشغيل العامل)</label>
     <label className="check-setting"><input type="checkbox" checked={storyForm.ai_writer_enabled} onChange={e=>setStoryForm(v=>({...v,ai_writer_enabled:e.target.checked}))}/> استخدام كاتب الذكاء الاصطناعي عند السماح به من الخادم</label>
     <label className="check-setting"><input type="checkbox" checked={storyForm.paid_media_enabled} onChange={e=>setStoryForm(v=>({...v,paid_media_enabled:e.target.checked}))}/> السماح بإرسال توليد الصور والفيديو المدفوع تلقائياً (يحتاج تمكيناً مستقلاً من الخادم)</label>
     <label>الحد الأقصى لطلبات الذكاء المدفوعة يومياً (الكتابة + الصور + الفيديو؛ عدد لا مبلغ)<input type="number" min={0} max={20} value={storyForm.daily_paid_job_limit} onChange={e=>setStoryForm(v=>({...v,daily_paid_job_limit:Math.max(0,Math.min(20,Number(e.target.value)||0))}))}/></label>
     <button disabled={busy||storyForm.origin.trim().length<5||storyForm.ambitions.trim().length<3} onClick={saveStory}>حفظ عالم الشخصية وإعداد الأتمتة</button>
     {savedStory&&<div className="prompt"><b>حالة محرك القصص</b><p className="muted">التأليف الدوري: {storyStats?.scheduler_enabled?"مفعل في الإعدادات؛ يتطلب تشغيل العامل":"متوقف"} · الكاتب الذكي: {storyStats?.ai_writing_available?"متاح":"غير مفعل"} · الإنتاج المدفوع الآلي: {storyStats?.auto_paid_available?"مسموح ضمن الحدود":"متوقف"}</p><small>استخدام اليوم: {storyStats?.used_today??0} | المتبقي من سقف الطلبات: {storyStats?.remaining_today??0}. السقف بالعدد فقط ولا يضمن سقفاً نقدياً.</small></div>}
    </div></div>
    {savedStory&&<><div className="actions"><label>عدد الحلقات الآن<select value={episodeCount} onChange={e=>setEpisodeCount(Number(e.target.value))}><option value={1}>حلقة واحدة</option><option value={2}>حلقتان</option><option value={3}>3 حلقات</option></select></label><button disabled={busy} onClick={nextEpisode}>اكتب الحلقة التالية وجهز المشاهد</button><button className="secondary" disabled={busy||!storyForm.auto_enabled} onClick={storyTick}>اختبار دورة التأليف التلقائي</button></div>
    <h3>مسلسل {current?.name} — الحلقات ({episodes.length})</h3>
    {episodes.length===0?<p className="muted">لا توجد حلقات بعد. ابدأ بالحلقات الأولى لتوثيق نشأة الشخصية وبناء ذاكرة القصة.</p>:episodes.map(ep=><article className="story-episode" key={ep.id}>
     <div className="job-header"><b>الحلقة {ep.number}: {ep.title}</b><span className="pill">{ep.status} · {ep.method==="ai"?"كتابة AI":"قالب محلي"}</span></div>
     <p><strong>الخطاف:</strong> {ep.hook}</p><details><summary>نص الحلقة والحوار</summary><p>{ep.script}</p></details>
     <details><summary>الذاكرة واستمرار القصة</summary><p>{ep.memory_after}</p></details>
     <details><summary>خطة تصوير ريلز رأسي — {ep.shots.length} مشاهد</summary>{ep.shots.map(s=><p key={s.sequence}>المشهد {s.sequence}: {s.scene}</p>)}</details>
     <p className="muted">{ep.caption}</p>
     <div className="actions">{!ep.approved&&<button className="secondary" disabled={busy} onClick={()=>approveStoryEpisode(ep.id)}>اعتماد السيناريو للمراجعة الداخلية</button>}{ep.reel_url&&<button disabled={busy} onClick={()=>openReel(ep.id)}>معاينة الريلز المجمع</button>}</div>
     {reelPreviews[ep.id]&&<video className="video-preview" controls src={reelPreviews[ep.id]}/>}
    </article>)}
    </>}
    <p className="muted">كل شخصية واضحة بأنها افتراضية. لا يحدث نشر تلقائي في Instagram، ولا تصدر طلبات مدفوعة إلا بعد تفعيلها صراحةً في إعدادات الشخصية والخادم. تتطلب النتيجة البصرية النهائية مراجعة جودة وثبات الهوية.</p>
   </>}
  </section>
  <footer>نسخة تطوير محلية V0.4 — المهام المحضرة لا تولّد وسائط تلقائياً، ولا توجد ضمانات لثبات الهوية — لا تُنشر على الإنترنت قبل ترقية الأمان والمصادقة. التأليف آلي اختياري، والنشر الاجتماعي يتطلب مراجعة منفصلة.</footer>
 </main>;
}
