# UWED Pulse — doimiy ishga tushirish (Google Cloud)

Natija: bot 24/7 ishlaydi, Mini App va Admin panel HTTPS orqali ochiladi, server qayta yuklansa
bot o'zi qayta turadi. Taxminiy vaqt: 20–30 daqiqa.

| Narsa | Qayerda | Narx |
|---|---|---|
| Server (e2-micro, 30 GB disk) | Google Cloud, `uwedpulse-host` loyihasi | Always Free |
| Statik tashqi IP (~$3.6/oy, ishlatilayotganda) | o'sha loyiha | Developer Program kreditlaridan |
| AI (Gemini 3.8 Flash + ovoz) | `uwedpulse` loyihasi | Prepay kreditlaridan |
| HTTPS sertifikat | Caddy + sslip.io | bepul |

---

## 0. Kalitlarni yangilash (xavfsizlik)

Token va Gemini kaliti chatda ochiq yozilgan — serverga **yangilarini** qo'ying:

1. **Telegram:** @BotFather → `/mybots` → `@uwedpulsebot` → **API Token** → **Revoke current token** →
   yangi tokenni saqlab qo'ying.
2. **Gemini:** <https://aistudio.google.com/apikey> → `uwedpulse` loyihasida **Create API key** →
   yangisini saqlang → eski kalitni **Delete**.
3. **Telegram ID:** `2076925033` (o'zgarmaydi).

Bu qiymatlarni faqat 4-qadamda serverdagi `.env` fayliga yozasiz.

---

## 1. Server uchun loyiha

1. <https://console.cloud.google.com/projectcreate> → **Project name:** `uwedpulse-host` → **Create**.
2. <https://console.cloud.google.com/billing/projects> → `uwedpulse-host` → **⋮ → Change billing** →
   **My Billing Account 1** → **Set account**.
3. **Billing → Budgets & alerts → Create budget** → loyiha `uwedpulse-host`, summa **$5**,
   ogohlantirish 50% / 90% / 100% → **Finish**.

## 2. Serverni yaratish

Console'ning yuqori o'ng burchagidagi **`>_` (Activate Cloud Shell)** ni bosing. Pastda terminal ochiladi.
Quyidagilarni nusxalab, ketma-ket qo'ying (har biridan keyin **Enter**):

```bash
gcloud config set project uwedpulse-host
gcloud services enable compute.googleapis.com
```

Doimiy (statik) IP — server to'xtab-yonsa ham manzil o'zgarmaydi:

```bash
gcloud compute addresses create uwed-ip --region=us-central1
```

```bash
gcloud compute instances create uwed-bot \
  --zone=us-central1-a --machine-type=e2-micro --address=uwed-ip \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=30GB --boot-disk-type=pd-standard \
  --tags=web
```

```bash
gcloud compute firewall-rules create uwed-web --allow=tcp:80,tcp:443 --target-tags=web
```

> Always Free faqat **us-west1 / us-central1 / us-east1** zonalarida, **e2-micro** va **pd-standard** diskda.
> Boshqa zona yoki turini tanlamang.

## 3. Serverga kirish va o'rnatish

```bash
gcloud compute ssh uwed-bot --zone=us-central1-a
```
(Kalit yaratishni so'rasa — 2 marta **Enter**.) Endi terminal server ichida.

```bash
curl -fsSL https://raw.githubusercontent.com/uBakhtiyarov3/moodledeadlines/claude/confident-goldberg-upnif2/deploy/setup-vm.sh \
  | BRANCH=claude/confident-goldberg-upnif2 bash
```

Skript: swap qo'shadi (1 GB RAM uchun), Docker o'rnatadi, kodni yuklaydi va `.env` yaratadi —
`PUBLIC_URL` (`https://<ip>.sslip.io`), `DOMAIN` va `SECRET_KEY` ni o'zi to'ldiradi.
Oxirida `.env created with PUBLIC_URL=https://...` yozuvi chiqadi.

> Branch `main` ga birlashtirilgach, URL va `BRANCH=` dagi `claude/confident-goldberg-upnif2` o'rniga `main` yoziladi.

## 4. Kalitlarni yozish

```bash
nano ~/uwed-bot/.env
```

Faqat shu uch qatorni to'ldiring (strelkalar bilan yuring):

```
BOT_TOKEN=<0-qadamdagi yangi token>
ADMIN_IDS=2076925033
GEMINI_API_KEY=<0-qadamdagi yangi Gemini kaliti>
```

Saqlash: **Ctrl+O → Enter**, chiqish: **Ctrl+X**.
⚠️ `SECRET_KEY` ni keyin hech qachon o'zgartirmang — talabalarning Moodle linklari u bilan shifrlangan.

## 5. Ishga tushirish

```bash
cd ~/uwed-bot && sudo docker compose up -d --build
```

Birinchi marta 3–6 daqiqa davom etadi (image yig'iladi). Keyin:

```bash
sudo docker compose logs -f bot
```

Kutiladigan qatorlar: `bot polling started` va `Start polling`. Chiqish: **Ctrl+C** (bot ishlashda davom etadi).

## 6. Tekshirish

1. Brauzerda `https://<ip>.sslip.io/healthz` → `{"ok":true}` (HTTPS sertifikat 1–2 daqiqada chiqadi).
2. Telegram → @uwedpulsebot → `/start` → til → pastda **Pulse** menyu tugmasi → Mini App ochiladi.
3. `/admin` → **Admin panel** → Dashboard ko'rinadi.
4. AI'ga matn va 🎤 ovozli savol yuboring.
5. Admin panel → **AI** → UWED haqida birinchi hujjatlarni qo'shing (kontaktlar, to'lov, imtihon tartibi).

---

## Kundalik boshqaruv

Serverga kirish: Cloud Shell → `gcloud compute ssh uwed-bot --zone=us-central1-a`, keyin `cd ~/uwed-bot`.

| Vazifa | Buyruq |
|---|---|
| Loglarni ko'rish | `sudo docker compose logs -f --tail=100 bot` |
| Qayta ishga tushirish | `sudo docker compose restart bot` |
| Yangi versiyaga yangilash | `git pull && sudo docker compose up -d --build` |
| `.env` o'zgargach | `sudo docker compose up -d` |
| To'xtatish | `sudo docker compose down` |
| Holat | `sudo docker compose ps` |
| Zaxira nusxa (DB) | `cp data/bot.db ~/bot-$(date +%F).db` |

Zaxirani kompyuterga yuklab olish (Cloud Shell'da):
`gcloud compute scp uwed-bot:~/uwed-bot/data/bot.db ./bot-backup.db --zone=us-central1-a` →
Cloud Shell menyusi **⋮ → Download**.

Server o'chib-yonsa ham bot o'zi ko'tariladi (`restart: unless-stopped`).

## Muammolar

| Belgi | Sabab / yechim |
|---|---|
| `unable to open database file` | `sudo chown -R 1000:1000 data && sudo docker compose restart bot` (yangi image'da o'zi tuzatiladi) |
| `Conflict: terminated by other getUpdates` | Bot boshqa joyda ham ishlayapti — bitta joyda qoldiring |
| Mini App ochilmaydi / HTTPS xato | Firewall (2-qadam) yaratilganini tekshiring; `sudo docker compose logs caddy` |
| AI "band" deydi | AI Studio → Spend/Billing: kredit tugaganmi; `logs bot` da `gemini 402/429` |
| `Unauthorized` (bot) | `BOT_TOKEN` noto'g'ri — `.env` ni tuzating, `docker compose up -d` |
| Server sekin / xotira | `free -h`; swap borligini tekshiring (`swapon --show`) |
| Server o'chirib qayta yaratildi | Statik IP (`uwed-ip`) saqlanadi — `--address=uwed-ip` bilan yarating; IP o'zgarsa `.env` da `PUBLIC_URL` va `DOMAIN` ni yangilang |

## Xarajatni kuzatish

- **Server:** <https://console.cloud.google.com/billing> → **Reports** (loyiha `uwedpulse-host`).
- **AI:** <https://aistudio.google.com> → **Spend** (loyiha `uwedpulse`). Kunlik talaba limitini
  Admin panel → Sozlamalar → *Kunlik limit* bilan boshqaring.
