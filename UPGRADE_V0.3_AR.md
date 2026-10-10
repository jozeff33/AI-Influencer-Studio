# ترقية آمنة من V0.2 إلى V0.3 — Windows / VS Code

> تنبيه: **لا تحذف ملف `.env`، ولا تنفذ `docker compose down -v`، ولا تنقل قاعدة البيانات يدوياً.** النسخة الحالية تحتفظ بشخصية «قمر» وكل محتوياتها لأنها تستخدم نفس مجلد المشروع ونفس Docker volumes.

## 1) افتح مجلد GitHub الأصلي

في VS Code، افتح `C:\Users\MASTER\AI-Influencer-Studio`، وليس مجلد الملفات المضغوطة على سطح المكتب.

```powershell
cd "C:\Users\MASTER\AI-Influencer-Studio"
git status
```

يفضل أن تكون الحالة نظيفة قبل التحديث. إذا لم تكن كذلك، احتفظ بالتغييرات قبل المتابعة.

## 2) خذ نسخة احتياطية من البيانات والوسائط

بينما Docker قيد التشغيل:

```powershell
New-Item -ItemType Directory -Force ".\backups" | Out-Null
docker compose exec -T db pg_dump -U studio -d studio -f /tmp/studio-before-v03.sql
docker compose cp db:/tmp/studio-before-v03.sql ".\backups\studio-before-v03.sql"
docker compose cp backend:/app/media ".\backups\media-before-v03"
```

احتفظ بمجلد `backups` خارج GitHub (مستثنى من Git). تحقق أن ملف SQL موجود وأن صورك موجودة في نسخة الوسائط. إذا احتوى مجلد الوسائط على بيانات شخصية، احفظ النسخة الاحتياطية في موقع آمن محلي.

## 3) فرع احتياطي وتحديث الكود

```powershell
git switch -c feat/identity-video-v0.3
```

إذا كان الفرع موجوداً، استخدم `git switch feat/identity-video-v0.3` بعد التأكد من حالته.

فك ضغط V0.3 على سطح المكتب، ثم انسخ محتويات مجلد `ai_influencer_studio` إلى `C:\Users\MASTER\AI-Influencer-Studio` مع الإبقاء على `.git` و`.env` وملفات الوسائط الحالية.

مثال إن كان اسم المجلد المستخرج مطابقاً:

```powershell
Copy-Item -Path "C:\Users\MASTER\Desktop\ai_influencer_studio\*" -Destination "C:\Users\MASTER\AI-Influencer-Studio" -Recurse -Force
```

**انتبه:** قد يكون مجلدك المستخرج باسم مختلف. لا تنفذ المثال إلا بعد مراجعة المسار.

## 4) لا تستبدل `.env`

أضف الأسطر التالية إلى `.env` المحلي (بدون إدراج مفاتيح حقيقية في المحادثة أو GitHub):

```dotenv
OPENAI_API_KEY=
IMAGE_MODEL=gpt-image-1-mini
RUNWAYML_API_SECRET=
RUNWAY_VIDEO_MODEL=gen4.5
ENABLE_PAID_GENERATION=false
```

احتفظ بقيم `STUDIO_DEV_API_KEY` و`DATABASE_URL` الحالية دون تغيير.

## 5) تشغيل وفحص

```powershell
docker compose up -d --build
docker compose ps
```

افتح `http://localhost:3000` وسجّل دخولك بمساحة `demo`. تأكد من بقاء شخصية «قمر»، إصدار هويتها، وصورها. جهز مهمة صورة وفيديو (لا رسوم) واختبر أن كليهما يظهر بالحالة `prepared`.

## 6) رفع الفرع بعد نجاح الاختبارات

```powershell
git status
git add -A
git diff --cached --name-only
git commit -m "feat: identity consistency and video adapters V0.3"
git push -u origin feat/identity-video-v0.3
```

لا ترفع `.env` أو أي مفاتيح أو النسخ الاحتياطية. **لا تدمج الفرع بـ main قبل التأكد من ظهور بيانات V0.2 بعد الترقية.**
