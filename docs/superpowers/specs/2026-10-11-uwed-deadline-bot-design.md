# UWED Pulse (@uwedpulsebot) — Design (v0.1)

## Maqsad
UWED talabalari uchun Telegram bot + Mini App:
1. Moodle deadlinelarini avtomatik kuzatish va eslatish.
2. uwed.uz bilimlariga asoslangan AI chat (Amazon Bedrock, Claude).
3. To'liq boshqaruvli admin panel (alohida Mini App).
Tillar: o'zbek / rus / ingliz. Dizayn: "liquid glass".

## Moodle ulash — ikki variant va tanlov

| | A. Calendar export (iCal) URL | B. Moodle akkaunt (login → token) |
|---|---|---|
| Parol | Kerak emas | Bir marta kiritiladi, **saqlanmaydi** (faqat `login/token.php` dan olingan token, shifrlangan) |
| Deadlinelar | Ha (`preset_what=all`, `preset_time=recentupcoming` ≈ oldingi 5 kun + keyingi 60 kun) | Ha |
| Topshirilganini bilish | Yo'q — talaba "✅ Bajardim" tugmasini bosadi | **Avtomatik**: `core_calendar_get_action_events_by_timesort` topshirilgan vazifani qaytarmaydi |
| Xavfsizlik | Link faqat kalendar o'qiydi | Token akkauntga keng ruxsat beradi |

**Qaror:** A — asosiy (default, xavfsiz, oson). B — ixtiyoriy "Pro" rejim, talaba o'zi yoqadi.
Ikkalasi bir vaqtda ishlaydi: A deadline manbai, B faqat "bajarilgan" holatini aniqlash va
qo'shimcha manba. Ikkala endpoint `moodle.uwed.uz` da tekshirildi (`login/token.php`
`invalidlogin` qaytaradi — demak mobil web-servis yoqilgan).

## Eslatmalar
- Default offsetlar: 72h, 24h, 12h, 6h, 3h, 2h, 1h. Talaba Mini App'da har birini yoqib/o'chiradi,
  umumiy pauza qo'yadi, alohida kursni o'chiradi.
- Har bir offset uchun alohida matn (shoshilinchlik darajasiga qarab) va tilga mos.
- Kech qo'shilgan deadline: faqat qolgan vaqtga eng yaqin (eng kichik mos) eslatma yuboriladi,
  kattaroqlari "skipped" deb belgilanadi — spam bo'lmaydi.
- Bajarilgan (qo'lda yoki B orqali), o'chirilgan yoki feeddan yo'qolgan deadline — eslatilmaydi.
- `reminder_log(user, event, offset)` unique — takror yuborish yo'q.
- Scheduler: har 1 daqiqada eslatmalar; har `SYNC_INTERVAL_MIN` (30) daqiqada sinxronlash.

## AI chat
- `AsyncAnthropicBedrock` (bedrock-runtime), model **Claude Opus 4.5** — cross-region profil
  `us.anthropic.claude-opus-4-5-20251101-v1:0` (foydalanuvchi tanlovi).
- "O'rgatish" = RAG: admin bilim bazasiga matn qo'shadi (FAQ, nizomlar, jadval), bo'laklanadi,
  savolga eng mos bo'laklar (BM25 kalit so'z qidiruvi, uz/ru/en uchun ishlaydi) system promptga qo'shiladi.
  Talabaning yaqin deadlinelari ham kontekstga beriladi.
- Kunlik limit per user, admin yoqib/o'chiradi, system promptni tahrirlaydi.

## Admin panel (Mini App `/admin`)
UWED brend ranglari: #8a0119 va #123654 teng vaznda, oq — ikkinchi rang.
Dashboard (statistika), foydalanuvchilar (qidiruv, ban, admin qilish, shaxsiy xabar),
rich-text broadcast (B/I/U/S, link, code, spoiler, quote → Telegram HTML; segment: til, Moodle
ulanganlar; preview + o'zimga test), bilim bazasi CRUD, AI sozlamalari, bot sozlamalari
(default offsetlar, sinx intervali, texnik ishlar rejimi).
Kirish: `ADMIN_IDS` env + DB'dagi adminlar. Har bir API so'rov Telegram `initData` HMAC bilan tekshiriladi.

## Arxitektura
Bitta Python jarayon: aiogram 3 (polling) + FastAPI (API + statik Mini App) + APScheduler.
SQLAlchemy async — SQLite (default) yoki Postgres (`DATABASE_URL`). Sirlar Fernet bilan shifrlangan.
Frontend — build bosqichisiz vanilla JS (tez, yengil, e2-micro'ga mos).

## Deploy
Google Cloud **e2-micro Always Free** (us-west1/us-central1/us-east1, 30 GB disk) — VM doimiy bepul,
tashqi IPv4 uchun ~$3.6/oy olinishi mumkin. Railway doimiy bepul tarif bermaydi (Hobby ~$5/oy).
To'liq $0 muqobil: Oracle Cloud Always Free. Docker tufayli ko'chirish oson. HTTPS: Caddy + `<ip>.sslip.io`
(domen shart emas). Bedrock — pullik (token bo'yicha), qolgan hammasi bepul.

## Test
pytest: iCal parser, reminder rejalashtirish mantiqi, initData tekshiruvi, Telegram HTML sanitizer, KB qidiruv.
