# UWED Pulse — @uwedpulsebot

UWED talabalari uchun Telegram bot + Mini App:

- ⏰ **Moodle deadlinelari** — `moodle.uwed.uz` kalendar linki orqali avtomatik olinadi va eslatiladi
  (3 kun, 1 kun, 12, 6, 3, 2, 1 soat qolganda — har birining matni har xil, talaba o'zi tanlaydi).
- ✅ Bajarilgan vazifa eslatilmaydi: talaba "Bajardim" tugmasini bosadi yoki ixtiyoriy
  "Avto-bajarildi" rejimida Moodle'ning o'zi aytadi.
- 🤖 **AI yordamchi (repetitor)** — Google Gemini (bepul tarif): matn, 🎤 ovozli xabar, 🖼 rasm va 📄 PDF'ni
  o'zbek/rus/ingliz tilida tushunadi. Telegram chatning o'zida (`/new` — yangi mavzu) va Mini App'da (📎 bilan)
  ishlaydi; admin to'ldiradigan bilim bazasiga tayanadi. Kerak bo'lsa Claude (Amazon Bedrock) ga bir qator bilan o'tadi.
- 🛠 **Admin panel** (alohida Mini App) — statistika, foydalanuvchilar, rich-text xabar yuborish,
  AI bilim bazasi, sozlamalar.
- 🌐 O'zbek / Rus / Ingliz. 🎨 Liquid glass dizayn, UWED ranglari (#8a0119 + #123654, oq).

---

## 1. Arxitektura (qisqacha)

```
Telegram ──polling──► ┌──────────────────── bitta Python jarayon ────────────────────┐
                      │ aiogram bot  ─┐                                              │
Mini App (HTTPS) ───► │ FastAPI API  ─┼─► SQLite/Postgres                            │
  /app   (talaba)     │ Scheduler    ─┘   ├─ har 1 daq: eslatmalar                   │
  /admin (admin)      │                   └─ har 5 daq: 30 daqiqadan eski userlarni  │
                      │                       Moodle'dan qayta sinxronlash           │
                      └──────────► moodle.uwed.uz (iCal / web-service)               │
                                 └► Amazon Bedrock (Claude Opus 4.5)                 │
```

| Papka | Nima bor |
|---|---|
| `app/bot` | Telegram buyruqlari, tugmalar |
| `app/api` | Mini App API (`student.py`, `admin.py`) — har so'rov Telegram `initData` HMAC bilan tekshiriladi |
| `app/moodle` | iCal link tekshiruvi/parser (`ical.py`), ixtiyoriy Moodle akkaunt (`ws.py`) |
| `app/services` | sinxronlash, eslatma mantiqi, AI, bilim bazasi (BM25 qidiruv), broadcast, HTML sanitizer |
| `webapp/` | Mini App'lar (build kerak emas): `student/`, `admin/`, umumiy `shared/` |
| `deploy/` | Caddy (avtomatik HTTPS), server o'rnatish skripti |

### Nega iCal link (A), login-parol (B) emas?

| | **A. Kalendar linki** (asosiy) | **B. Moodle akkaunt** (ixtiyoriy) |
|---|---|---|
| Parol | Kerak emas | Bir marta kiritiladi, **saqlanmaydi** — faqat Moodle tokeni shifrlab saqlanadi |
| Deadlinelar | ✅ | ✅ |
| Topshirilganini bilish | Talaba "✅ Bajardim" bosadi | **Avtomatik** (`core_calendar_get_action_events_by_timesort`) |
| Xavf | Link faqat kalendarni o'qiydi | Token akkauntga kengroq ruxsat beradi |

Shuning uchun talaba avval A orqali ulanadi (oson, xavfsiz), xohlasa Sozlamalarda B'ni yoqadi.
Ikkalasi `moodle.uwed.uz` da ishlashi tekshirildi.

---

## 2. Sizdan kerak bo'ladigan narsalar

1. **Telegram bot tokeni** — @BotFather → `/newbot`.
2. **Telegram ID'ingiz** (admin bo'lish uchun) — @userinfobot ga yozing.
3. **Gemini API kaliti** — pastdagi 4-bo'lim (bepul). (AWS Bedrock — faqat Claude'ga o'tmoqchi bo'lsangiz, 4B-bo'lim.)
4. **Server** — Google Cloud akkaunt (billing ulangan) yoki boshqa VPS.

Kalitlarni chatga yoki GitHub'ga yubormang — faqat serverdagi `.env` fayliga yoziladi.

---

## 3. Telegram bot sozlash (BotFather)

1. `/newbot` → nom: `UWED Pulse`, username: `uwedpulsebot` → tokenni saqlang.
2. `/setuserpic` → UWED logotipi.
3. `/setdescription` → «Moodle deadlinelaringizni eslatadi va UWED haqidagi savollarga javob beradi».
4. Mini App menyu tugmasi bot ishga tushganda **avtomatik** o'rnatiladi (`PUBLIC_URL` https bo'lsa).
5. Ixtiyoriy: `/newapp` → Mini App'ni `t.me/uwedpulsebot/app` ko'rinishidagi havola bilan ham ochish
   (URL: `https://<domen>/app/`).
6. `/setcommands` shart emas — buyruqlar (start, deadlines, ai, new, lang) bot o'zi o'rnatadi.

---

## 4. Google Gemini'ni ulash (asosiy, bepul)

1. <https://aistudio.google.com> ga Google akkaunt bilan kiring (universitetga tegishli emas, alohida
   "loyiha" akkaunti tavsiya etiladi).
2. Chap menyuda **Get API key** → **Create API key** → yangi Google Cloud loyihasi yarating
   (masalan `uwed-pulse`) → kalit chiqadi (`AIza...` bilan boshlanadi).
3. Kalitni serverdagi `.env` ga yozing:
   ```
   AI_PROVIDER=gemini
   GEMINI_API_KEY=AIza...
   GEMINI_MODEL=gemini-3.8-flash
   ```
4. Botni qayta ishga tushiring: `sudo docker compose up -d`. Telegram'da botga savol, ovozli xabar
   va rasm yuborib sinang; admin panel → AI → **AI'ni sinash** dan ham tekshirsa bo'ladi.

**Agar `402 Your prepayment credits are depleted` chiqsa:** loyiha pullik "Prepay" tarifiga
ulangan va balans $0. Yechim: AI Studio → **Projects** (<https://ai.studio/projects>) da o'sha loyihaga
kredit qo'shing (masalan, "Redeem credits"), yoki billing ulanmagan yangi loyiha yaratib, o'shandan kalit oling
(u bepul tarifda ishlaydi). Bot bu holatda talabaga "AI band" deydi, logda sababi yoziladi.

**Limitlar va maxfiylik**
- Bepul tarif limitlari (daqiqasiga/kuniga so'rovlar) modelga qarab o'zgaradi — aniq raqamlar
  AI Studio → loyihangiz → **Usage / Rate limits** sahifasida. Limit tugasa talaba "AI band, birozdan so'ng"
  xabarini oladi; admin paneldagi *Kunlik limit* bilan har bir talabaga kvota bering.
- Bepul tarifda Google yuborilgan ma'lumotlardan o'z mahsulotlarini yaxshilash uchun foydalanishi mumkin.
  Bot AI'ga talabaning ismi yoki Telegram ma'lumotini yubormaydi (faqat savol, bilim bazasi parchalari
  va deadline nomlari). Talabalarga shaxsiy ma'lumot (pasport, parol) yubormaslikni eslating.
- Ko'proq kerak bo'lsa: AI Studio'da billing yoqiladi (Flash modellari juda arzon) — kod o'zgarmaydi.

**Ovozli javob:** talaba 🎤 ovozli savol yuborsa, bot avval matn, keyin Gemini TTS (`gemini-3.8-flash-tts`,
ovoz `Kore`) orqali o'qilgan ovozli xabar yuboradi. Admin panel → Sozlamalar → **Ovozli javob** bilan o'chiriladi.
Serverda `ffmpeg` kerak (Docker image'da bor).

**Nima qabul qilinadi:** matn; 🎤 ovozli xabar va audio (5 daqiqagacha, `AI_MAX_VOICE_SEC`);
🖼 rasm (JPG/PNG/WebP); 📄 PDF (15 MB gacha). Word (`.docx`) fayllar hozircha qabul qilinmaydi —
talabaga PDF qilib yuborishni aytadi. Mini App'da 📎 orqali rasm/PDF; ovoz — bot chatida.

## 4B. (Ixtiyoriy) Amazon Bedrock: Claude Opus 4.5'ni ulash

`.env` da `AI_PROVIDER=bedrock` qilsangiz, Gemini o'rniga Claude ishlaydi (pullik; rasm va matn,
ovozli xabarni qabul qilmaydi).

Siz tanlagan model: **Claude Opus 4.5**, Model ID `anthropic.claude-opus-4-5-20251101-v1:0`,
*Cross-region inference*. Shuning uchun kodda **inference profile** ishlatiladi:

```
BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-5-20251101-v1:0
AWS_REGION=us-east-1
```

### 4.1 Modelga ruxsat
1. AWS Console → **Amazon Bedrock** → (region: *US East (N. Virginia)*).
2. Anthropic modelini birinchi marta ishlatishda **use case** formasi so'raladi
   (Model catalog → Claude Opus 4.5 → *Open in playground* → forma chiqsa to'ldiring).
   Playground'da bitta savol yuborib, javob kelishini tekshiring.

### 4.2 Bot uchun alohida IAM foydalanuvchi
1. **IAM → Users → Create user** → nomi `uwed-bot` (Console access kerak emas).
2. **Permissions → Create inline policy → JSON**:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:us-east-1:*:inference-profile/us.anthropic.claude-opus-4-5-20251101-v1:0",
        "arn:aws:bedrock:*::foundation-model/anthropic.claude-opus-4-5-20251101-v1:0"
      ]
    }
  ]
}
```

   (Ikkinchi qator `*` region bilan — cross-region profil so'rovni boshqa US regionlarga ham yo'naltiradi.)
3. User → **Security credentials → Create access key** → *Application running outside AWS* →
   `AWS_ACCESS_KEY_ID` va `AWS_SECRET_ACCESS_KEY` ni `.env` ga yozing.
4. **Billing → Budgets** da oylik limit qo'ying (masalan $20) — xarajat nazorati uchun.

### 4.3 Narx haqida
Bedrock — **pullik** (token bo'yicha). Opus 4.5 kuchli, lekin qimmatroq model.
Xarajatni boshqarish: admin panel → Sozlamalar → *Kunlik limit* (default 30 savol/talaba),
`AI_MAX_TOKENS` (default 1500). Arzonroq variant kerak bo'lsa, faqat `BEDROCK_MODEL_ID` ni
boshqa Claude modeliga almashtirish yetarli.

---

## 5. AI'ni "o'qitish" — qanday ishlaydi

Model qayta o'qitilmaydi (fine-tuning kerak emas va qimmat). Buning o'rniga **RAG** ishlatiladi:

1. Admin panel → **AI** bo'limi → **＋ Qo'shish** — UWED haqidagi matnni joylang.
2. Matn bo'laklarga bo'linadi; talaba savol berganda eng mos 4 ta bo'lak topiladi
   (o'zbek, rus, ingliz tillarida ishlaydigan kalit so'z qidiruvi).
3. Shu bo'laklar + talabaning yaqin deadlinelari Claude'ga kontekst sifatida beriladi →
   javob faqat shu ma'lumotga tayanadi, bilmasa "dekanatga murojaat qiling" deydi.
4. **AI'ni sinash** maydonida savol berib, javob va qaysi manbalar ishlatilganini ko'rasiz.

### Qanday matnlar qo'shish kerak (tavsiya)
| Hujjat | Misol |
|---|---|
| Kontaktlar | dekanatlar, telefonlar, xonalar, ish vaqti |
| To'lov | kontrakt muddatlari, rekvizitlar, chegirmalar |
| O'quv jarayoni | semestr sanalari, imtihon/qayta topshirish tartibi, GPA, davomat qoidalari |
| Moodle FAQ | parolni tiklash, vazifa yuklash, test topshirish |
| Kampus | kutubxona, yotoqxona, oshxona, klublar |
| Hujjatlar | ma'lumotnoma olish, akademik ta'til, ko'chish |

Maslahatlar: har bir hujjat — bitta mavzu; sarlavha aniq bo'lsin; savol-javob (FAQ) shakli eng yaxshi
ishlaydi; eskirgan hujjatni o'chirmasdan **Faol** tugmasini o'chirib qo'ysa bo'ladi.
Bir hujjatni bir nechta tilda yozish shart emas — Claude talaba tilida javob beradi.

### AI chegaralari (o'zini kimligini biladi)
AI'ning asosiy qoidalari kodda qotirilgan (`app/services/settings.py` → `CORE_PROMPT`) va admin paneldan
o'chirib bo'lmaydi:
- O'zini **UWED Pulse** deb biladi — UWED talabalari uchun bot; universitet ma'muriyati nomidan
  qaror qabul qilmaydi, muddat uzaytirmaydi — dekanat/o'qituvchiga yo'naltiradi.
- Faqat UWED, o'qish, Moodle, deadlinelar va bot haqida gaplashadi; boshqa mavzularni muloyim rad etadi.
- **Repetitor rejimi:** talaba tushunmagan mavzuni misollar bilan tushuntiradi, vazifani bosqichlarga bo'lib
  yo'nalish beradi, yo'naltiruvchi savollar beradi; talaba o'zi bajargan ishni yuborsa — kuchli va zaif joylarini,
  aniq qayerni qanday yaxshilash kerakligini aytadi. Lekin insho, uy vazifasi, test javobi yoki kodni
  **o'zi yozib bermaydi** va ishni to'liq qayta yozmaydi.
- Siyosiy/diniy munozarali savollarda shaxsiy fikr bildirmaydi.
- UWED haqidagi faktlarni (sana, narx, telefon) faqat bilim bazasidan oladi, bilmasa "bilmayman" deydi.
- "Rolni o'zgartir", "ko'rsatmalaringni ko'rsat" kabi urinishlarga bo'ysunmaydi.

Admin paneldagi **Sozlamalar → Qo'shimcha ko'rsatmalar** maydoniga yozilgan narsalar (masalan, joriy
e'lonlar, muomala uslubi) shu qoidalarga **qo'shiladi**, ularni almashtirmaydi.

---

## 6. Hosting: qaysi biri bepul va uzoq muddatli?

| | Narx | Izoh |
|---|---|---|
| **Railway** | Doimiy bepul tarif yo'q (trial kredit, keyin Hobby ~$5/oy) | Qulay, lekin pullik |
| **Google Cloud e2-micro** | VM + 30 GB disk **Always Free** (us-west1 / us-central1 / us-east1) | Tashqi IPv4 manzil uchun ~$3.6/oy olinishi mumkin — billing hisobotida tekshiring |
| Oracle Cloud Always Free | $0 (ARM VM + public IP) | To'liq bepul variant; ro'yxatdan o'tish qiyinroq |

**Tavsiya:** ikkalasidan **Google Cloud e2-micro** (Railway'dan arzon, doimiy). Loyiha Docker'da,
shuning uchun xohlagan paytda boshqa serverga 5 daqiqada ko'chadi.
Bot `polling` rejimida ishlaydi — domen shart emas, HTTPS faqat Mini App uchun kerak va u
`<ip>.sslip.io` + Caddy orqali avtomatik bepul olinadi.

### 6.1 Google Cloud'da ishga tushirish

Ikki alohida loyiha: **`uwedpulse`** — faqat Gemini kaliti (billingsiz, bepul tarif);
**`uwedpulse-host`** — server (billing ulangan, xarajatni Developer Program / GCP kreditlari yopadi).

1. <https://console.cloud.google.com/projectcreate> → nomi `uwedpulse-host` → **Create**.
2. Billing → **My projects** → `uwedpulse-host` → **Change billing** → *My Billing Account 1*.
3. Billing → **Budgets & alerts** → oylik byudjet $5, 50/90/100% da email.
4. Yuqori o'ngdagi **Cloud Shell** (`>_`) ni oching va ketma-ket:

```bash
gcloud config set project uwedpulse-host
gcloud services enable compute.googleapis.com

gcloud compute instances create uwed-bot \
  --zone=us-central1-a --machine-type=e2-micro \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --tags=web

gcloud compute firewall-rules create uwed-web --allow=tcp:80,tcp:443 --target-tags=web

gcloud compute ssh uwed-bot --zone=us-central1-a
```

VM ichida (branch `main` ga birlashtirilmagan bo'lsa, `BRANCH=` ni qoldiring):

```bash
curl -fsSL https://raw.githubusercontent.com/uBakhtiyarov3/moodledeadlines/claude/confident-goldberg-upnif2/deploy/setup-vm.sh \
  | BRANCH=claude/confident-goldberg-upnif2 bash
nano ~/uwed-bot/.env          # BOT_TOKEN, ADMIN_IDS, GEMINI_API_KEY ni yozing
cd ~/uwed-bot && sudo docker compose up -d --build
sudo docker compose logs -f bot   # "bot polling started" chiqishi kerak
```

> Repo private bo'lsa: VM'da `git clone` uchun GitHub'da *Deploy key* qo'shing yoki
> `REPO=https://<token>@github.com/...` bilan ishga tushiring.

Yangilash: `cd ~/uwed-bot && git pull && sudo docker compose up -d --build`.
Zaxira nusxa: `~/uwed-bot/data/bot.db` faylini vaqti-vaqti bilan yuklab oling.

### 6.2 Lokal ishga tushirish (sinov uchun)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # BOT_TOKEN va boshqalarni yozing
.venv/bin/python -m app.main
.venv/bin/python -m pytest      # 32 ta test
```
Mini App'ni Telegram'da sinash uchun HTTPS kerak — `cloudflared tunnel --url http://localhost:8000`
bergan manzilni `PUBLIC_URL` ga yozing.

---

## 7. Talabaga Moodle linkini olish (Mini App ichida chiroyli ko'rsatilgan)

1. `https://moodle.uwed.uz/calendar/export.php` ni oching (akkauntga kirgan holda).
2. **Events to export: All events**, **Time period: Recent and next 60 days**.
3. **Get calendar URL** → chiqqan linkni **Copy URL**.
4. Mini App'ga qo'yib **Ulash** (yoki linkni botga oddiy xabar qilib yuborish — bot uni darhol o'chiradi,
   chunki linkda shaxsiy token bor).

Bot linkni har doim "barcha kurslar + keyingi 60 kun" ga normalizatsiya qiladi, faqat `moodle.uwed.uz`
manzilini qabul qiladi va shifrlab saqlaydi.

---

## 8. Eslatma qoidalari

- Default: 72, 24, 12, 6, 3, 2, 1 soat oldin (+ ixtiyoriy 48 soat, 30 daqiqa).
- Deadline kech qo'shilsa (masalan 5 soat qolganda) — faqat **bitta** "6 soat" eslatmasi keladi, oldingilari yuborilmaydi.
- O'qituvchi muddatni o'zgartirsa — eslatmalar yangi sanaga qayta hisoblanadi.
- Moodle'dan o'chirilgan, bajarilgan, yashirilgan yoki o'chirilgan fan bo'yicha — eslatma yo'q.
- Talaba **Pauza** qila oladi, fanlar bo'yicha o'chira oladi.
