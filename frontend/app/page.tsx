"use client";
import {useCallback, useEffect, useRef, useState} from "react";

type Character={id:string,name:string,persona:string,language:string};
type Project={id:string,title:string,character_id:string,status:string};
type Identity={id:string,version:number,appearance:string,wardrobe:string,visual_style:string,created_at:string};
type Asset={id:string,kind:string,identity_id:string,description:string,url:string,preview?:string};
const API=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";

export default function Home(){
 const [key,setKey]=useState(""); const [org,setOrg]=useState("demo");
 const [chars,setChars]=useState<Character[]>([]);const [projects,setProjects]=useState<Project[]>([]);
 const [name,setName]=useState("");const [persona,setPersona]=useState("");
 const [selected,setSelected]=useState("");const [title,setTitle]=useState("");const [script,setScript]=useState("");
 const [appearance,setAppearance]=useState("");const [wardrobe,setWardrobe]=useState("");const [visualStyle,setVisualStyle]=useState("صورة واقعية، إضاءة طبيعية، تصوير سينمائي");
 const [identity,setIdentity]=useState<Identity[]>([]);const [scene,setScene]=useState("الشخصية تقف في استوديو حديث وتنظر مباشرة إلى الكاميرا");
 const [prompt,setPrompt]=useState("");const [assets,setAssets]=useState<Asset[]>([]);const [generationEnabled,setGenerationEnabled]=useState(false);
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
  try{setError("");const [c,p]=await Promise.all([call("/characters"),call("/projects")]);setChars(c);setProjects(p);
   if(c.length>0)setSelected(v=>c.some((x:Character)=>x.id===v)?v:c[0].id);
  }catch(e){setError(String(e));}
 },[key,call]);
 const loadCharacter=useCallback(async()=>{
  if(!selected||!key)return;
  try{setError("");setPrompt("");setInfo("");const [ids,files]=await Promise.all([call(`/characters/${selected}/identity`),call(`/characters/${selected}/assets`)]);
    setIdentity(ids);objectUrls.current.forEach(URL.revokeObjectURL);objectUrls.current=[];
    const previews:Asset[]=await Promise.all(files.map(async(a:Asset)=>{
     try{const r=await fetch(API+a.url,{headers:headers()});if(!r.ok)return a;
      const url=URL.createObjectURL(await r.blob());objectUrls.current.push(url);return {...a,preview:url};
     }catch{return a;}
    }));setAssets(previews);
  }catch(e){setError(String(e));}
 },[selected,key,call,headers]);
 useEffect(()=>{void loadCharacter();},[loadCharacter]);
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
 const current=chars.find(c=>c.id===selected);
 return <main><header><span className="logo">✦</span><div><h1>AI Influencer Studio</h1><p>استوديو الشخصيات الافتراضية — الإصدار التجريبي V0.2</p></div></header>
  <section className="card"><h2>مساحة العمل</h2><div className="fields"><label>رمز مساحة العمل<input value={org} onChange={e=>setOrg(e.target.value)}/></label><label>مفتاح التطوير المحلي<input type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder="مفتاح الملف .env"/></label><button disabled={busy||!key.trim()} onClick={()=>void refresh()}>اتصال وتحديث</button></div>
  {error&&<p className="error" role="alert">{error}</p>}{info&&<p className="success" role="status">{info}</p>}</section>
  <div className="stats"><div>الشخصيات <strong>{chars.length}</strong></div><div>مشاريع المحتوى <strong>{projects.length}</strong></div><div>الصور المحفوظة <strong>{assets.length}</strong></div></div>
  <div className="columns"><section className="card"><h2>الشخصيات</h2><label>اسم شخصية جديدة<input value={name} onChange={e=>setName(e.target.value)} placeholder="مثال: قمر"/></label><label>وصف الشخصية<textarea value={persona} onChange={e=>setPersona(e.target.value)} placeholder="الهوايات وأسلوب الكلام"/></label><button disabled={busy||!key||!name.trim()} onClick={addCharacter}>إنشاء شخصية</button>
  <h3>اختيار الشخصية النشطة</h3><select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">اختر شخصية</option>{chars.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select>
  {current&&<p className="muted">{current.persona||"لم يضاف وصف للشخصية بعد"}</p>}</section>
  <section className="card"><h2>مشروع محتوى جديد</h2><label>الشخصية الحالية<input readOnly value={current?.name||"اختر شخصية أولاً"}/></label><label>عنوان الفيديو<input value={title} onChange={e=>setTitle(e.target.value)}/></label><label>السيناريو<textarea value={script} onChange={e=>setScript(e.target.value)}/></label><button disabled={busy||!selected||!title.trim()} onClick={addProject}>حفظ مسودة</button><h3>مسودات المحتوى</h3>{projects.filter(p=>p.character_id===selected).map(p=><article key={p.id}><b>{p.title}</b><small>الحالة: {p.status}</small></article>)}</section></div>
  <section className="card studio"><h2>مختبر هوية الشخصية <span className="pill">Character Identity V0.2</span></h2><p className="muted">احفظ وصفاً بصرياً ثابتاً للشخصية وإصداراته. تغيير الوصف لا يؤثر على الإصدارات السابقة.</p>
   <div className="columns"><div><label>وصف الملامح والهوية البصرية<textarea rows={4} value={appearance} onChange={e=>setAppearance(e.target.value)} placeholder="شخصية افتراضية أصلية، وصف ثابت للوجه والشعر والملامح والعمر التقريبي..."/></label><label>الملابس المعتادة<textarea rows={2} value={wardrobe} onChange={e=>setWardrobe(e.target.value)} placeholder="ملابس وستايل ثابت"/></label><label>الأسلوب البصري<input value={visualStyle} onChange={e=>setVisualStyle(e.target.value)}/></label><button disabled={busy||!selected||appearance.trim().length<10} onClick={addIdentity}>حفظ نسخة هوية جديدة</button></div>
   <div><h3>إصدارات الهوية</h3>{identity.length===0?<p className="muted">لم تُضف هوية بصرية لهذه الشخصية بعد.</p>:identity.map(i=><article key={i.id}><b>الإصدار {i.version}</b><p>{i.appearance}</p><small>{i.visual_style}</small></article>)}
   <h3>صور مرجعية (للأرشفة)</h3><p className="muted">ارفع صوراً تمتلك حق استخدامها. في V0.2 تُحفظ المراجع لكنها لا تُمرر تلقائياً لمحرك التوليد.</p><input type="file" accept="image/png,image/jpeg,image/webp" disabled={busy||!selected||identity.length===0} onChange={e=>{upload(e.target.files?.[0]);e.currentTarget.value="";}}/></div></div>
  </section>
  <section className="card studio"><h2>استوديو الصور</h2><p className="muted">تجهيز السيناريو يعمل بلا مفتاح خارجي. التوليد الحقيقي يتطلب ضبط OPENAI_API_KEY في ملف .env وقد يكون مدفوعاً؛ اضغط توليد فقط عند الرغبة.</p>
   <label>وصف المشهد<textarea rows={3} value={scene} onChange={e=>setScene(e.target.value)}/></label><div className="actions"><button disabled={busy||!selected||identity.length===0||scene.length<5} onClick={preview}>تجهيز وصف الصورة</button><button className="secondary" disabled={busy||!selected||identity.length===0||!generationEnabled||!prompt} onClick={generate}>{busy?"يرجى الانتظار...":"توليد صورة وحفظها"}</button></div>
   {prompt&&<div className="prompt"><h3>الوصف الجاهز للمحرك</h3><p dir="auto">{prompt}</p>{!generationEnabled&&<small>محرك الصور غير مفعّل. أضف OPENAI_API_KEY للخادم ثم أعد تشغيله.</small>}</div>}
   <h3>مكتبة صور {current?.name||"الشخصية"}</h3><div className="gallery">{assets.map(a=><figure key={a.id}>{a.preview?<img src={a.preview} alt={a.description||"صورة الشخصية"}/>:<div className="empty-preview">تعذر عرض الصورة</div>}<figcaption>{a.kind==="reference"?"مرجع بصري":"صورة مولّدة"}</figcaption></figure>)}{assets.length===0&&<p className="muted">لا توجد صور محفوظة بعد.</p>}</div>
  </section>
  <footer>نسخة تطويرية محلية — الهوية النصية وحدها لا تضمن ثبات الملامح — لا تنشر على الإنترنت دون ترقية المصادقة والأمان</footer>
 </main>;
}
