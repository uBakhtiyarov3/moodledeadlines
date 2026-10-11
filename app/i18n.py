"""Bot-side texts in Uzbek, Russian and English (Telegram HTML)."""

LANGS = ("uz", "ru", "en")

T: dict[str, dict[str, str]] = {
    "choose_lang": {
        "uz": "### 🌐 Tilni tanlang\n\nВыберите язык · Choose your language",
        "ru": "### 🌐 Выберите язык\n\nTilni tanlang · Choose your language",
        "en": "### 🌐 Choose your language\n\nTilni tanlang · Выберите язык",
    },
    "welcome": {
        "uz": "👋 Salom, <b>{name}</b>!\n\nMen <b>UWED Pulse</b> botiman:\n"
        "⏰ Moodle deadlinelaringizni kuzataman va o'z vaqtida eslataman\n"
        "🤖 Universitet haqidagi savollaringizga AI yordamida javob beraman\n\n"
        "Boshlash uchun pastdagi <b>Ilovani ochish</b> tugmasini bosing.",
        "ru": "👋 Привет, <b>{name}</b>!\n\nЯ бот <b>UWED Pulse</b>:\n"
        "⏰ слежу за дедлайнами в Moodle и вовремя напоминаю\n"
        "🤖 отвечаю на вопросы об университете с помощью ИИ\n\n"
        "Нажмите <b>Открыть приложение</b>, чтобы начать.",
        "en": "👋 Hi, <b>{name}</b>!\n\nI'm <b>UWED Pulse</b>:\n"
        "⏰ I track your Moodle deadlines and remind you on time\n"
        "🤖 I answer questions about the university with AI\n\n"
        "Tap <b>Open app</b> below to get started.",
    },
    "welcome_md": {
        "uz": "# 👋 Salom, {name}!\n\n**UWED Pulse** — UWED talabalari uchun shaxsiy yordamchi.\n\n"
        "- ⏰ **Deadlinelar** — Moodle'dagi vazifalaringizni kuzataman va o'z vaqtida eslataman\n"
        "- 🤖 **AI yordamchi** — o'qish, Moodle va universitet haqida savollarga javob beraman; "
        "matn, 🎤 ovoz, 🖼 rasm va 📄 PDF tushunaman\n"
        "- ⚙️ **Sozlamalar** — eslatma vaqtlari va tilni o'zingiz tanlaysiz\n\n"
        "Boshlash uchun pastdagi **Pulse** tugmasini bosing yoki savolingizni yozing.",
        "ru": "# 👋 Привет, {name}!\n\n**UWED Pulse** — личный помощник студентов UWED.\n\n"
        "- ⏰ **Дедлайны** — слежу за заданиями в Moodle и вовремя напоминаю\n"
        "- 🤖 **ИИ-помощник** — отвечаю на вопросы об учёбе, Moodle и университете; "
        "понимаю текст, 🎤 голос, 🖼 фото и 📄 PDF\n"
        "- ⚙️ **Настройки** — время напоминаний и язык выбираете сами\n\n"
        "Нажмите **Pulse** внизу или просто задайте вопрос.",
        "en": "# 👋 Hi, {name}!\n\n**UWED Pulse** — your personal assistant at UWED.\n\n"
        "- ⏰ **Deadlines** — I track your Moodle tasks and remind you on time\n"
        "- 🤖 **AI assistant** — I answer questions about studies, Moodle and the university; "
        "I understand text, 🎤 voice, 🖼 photos and 📄 PDFs\n"
        "- ⚙️ **Settings** — choose your reminder times and language\n\n"
        "Tap **Pulse** below or just ask a question.",
    },
    "dl_title": {"uz": "## ⏰ Yaqin deadlinelar", "ru": "## ⏰ Ближайшие дедлайны", "en": "## ⏰ Upcoming deadlines"},
    "dl_cols": {"uz": "| | Vazifa | Muddat | Qoldi |", "ru": "| | Задание | Срок | Осталось |", "en": "| | Task | Due | Left |"},
    "dl_legend": {
        "uz": "🔴 6 soatdan kam · 🟠 bugun-ertaga · 🟢 vaqt bor",
        "ru": "🔴 меньше 6 ч · 🟠 сегодня-завтра · 🟢 есть время",
        "en": "🔴 under 6 h · 🟠 within a day · 🟢 plenty of time",
    },
    "btn_support": {"uz": "💬 Admin bilan chat", "ru": "💬 Чат с админом", "en": "💬 Chat with admin"},
    "support_intro": {
        "uz": "### 💬 Admin bilan chat\n\nSavol, taklif yoki muammoingizni yozing — admin shu yerda javob beradi.\n\n"
        "- ✍️ Matn yoki 🖼 rasm yuborishingiz mumkin\n"
        "- 🔒 Chat ochiq turganda xabarlaringiz AI'ga emas, faqat adminga boradi\n\n"
        "<sub>Tugatish uchun «✖️ Chatni yopish» tugmasini bosing.</sub>",
        "ru": "### 💬 Чат с админом\n\nНапишите вопрос, предложение или проблему — админ ответит здесь.\n\n"
        "- ✍️ Можно отправлять текст или 🖼 фото\n"
        "- 🔒 Пока чат открыт, сообщения идут не ИИ, а только админу\n\n"
        "<sub>Чтобы завершить, нажмите «✖️ Закрыть чат».</sub>",
        "en": "### 💬 Chat with admin\n\nWrite your question, idea or problem — an admin will answer right here.\n\n"
        "- ✍️ You can send text or a 🖼 photo\n"
        "- 🔒 While the chat is open, your messages go to the admin, not the AI\n\n"
        "<sub>Tap «✖️ Close chat» to finish.</sub>",
    },
    "support_btn_close": {"uz": "✖️ Chatni yopish", "ru": "✖️ Закрыть чат", "en": "✖️ Close chat"},
    "support_btn_answer": {"uz": "✍️ Javob yozish", "ru": "✍️ Ответить", "en": "✍️ Reply"},
    "support_btn_app": {"uz": "💬 Chatni ochish", "ru": "💬 Открыть чат", "en": "💬 Open chat"},
    "support_reply_hint": {
        "uz": "Javob yozish uchun «✍️ Javob yozish» tugmasini bosing.",
        "ru": "Чтобы ответить, нажмите «✍️ Ответить».",
        "en": "Tap «✍️ Reply» to answer.",
    },
    "support_sent": {"uz": "✅ Adminga yuborildi", "ru": "✅ Отправлено админу", "en": "✅ Sent to the admin"},
    "support_closed": {
        "uz": "✖️ Admin bilan chat yopildi. Endi savollaringizga yana AI javob beradi.",
        "ru": "✖️ Чат с админом закрыт. На вопросы снова отвечает ИИ.",
        "en": "✖️ Admin chat closed. The AI answers your questions again.",
    },
    "support_text_only": {
        "uz": "💬 Admin chatiga matn yoki rasm yuboring.",
        "ru": "💬 В чат с админом отправьте текст или фото.",
        "en": "💬 Send text or a photo to the admin chat.",
    },
    "sup_reply_prompt": {
        "uz": "### ✍️ Javob: {name}\n\nKeyingi xabaringiz shu talabaga yuboriladi.\n\n<sub>Bekor qilish: /cancel</sub>",
        "ru": "### ✍️ Ответ: {name}\n\nСледующее сообщение уйдёт этому студенту.\n\n<sub>Отмена: /cancel</sub>",
        "en": "### ✍️ Reply to {name}\n\nYour next message goes to this student.\n\n<sub>Cancel: /cancel</sub>",
    },
    "sup_delivered": {"uz": "✅ Yuborildi → {name}", "ru": "✅ Отправлено → {name}", "en": "✅ Sent → {name}"},
    "sup_cancelled": {"uz": "Bekor qilindi.", "ru": "Отменено.", "en": "Cancelled."},
    "thinking": {"uz": "O‘ylayapman…", "ru": "Думаю…", "en": "Thinking…"},
    "open_app": {"uz": "📱 Ilovani ochish", "ru": "📱 Открыть приложение", "en": "📱 Open app"},
    "open_app_hint": {
        "uz": "📱 **Ilova** — deadlinelar, sozlamalar va admin bilan chat bir joyda.",
        "ru": "📱 **Приложение** — дедлайны, настройки и чат с админом в одном месте.",
        "en": "📱 **The app** — deadlines, settings and admin chat in one place.",
    },
    "admin_hint": {
        "uz": "### 🛠 Admin panel\n\nStatistika, foydalanuvchilar, xabar yuborish, murojaatlar va AI bilim bazasi.",
        "ru": "### 🛠 Админ-панель\n\nСтатистика, пользователи, рассылки, обращения и база знаний ИИ.",
        "en": "### 🛠 Admin panel\n\nStats, users, broadcasts, student chats and the AI knowledge base.",
    },
    "open_settings": {"uz": "⚙️ Sozlamalarni ochish", "ru": "⚙️ Открыть настройки", "en": "⚙️ Open settings"},
    "settings_hint": {
        "uz": "⚙️ Eslatmalar vaqti, til, fanlar va Moodle ulanishi — barchasi shu yerda:",
        "ru": "⚙️ Время напоминаний, язык, предметы и подключение Moodle — всё здесь:",
        "en": "⚙️ Reminder times, language, courses and the Moodle connection — all here:",
    },
    "open_admin": {"uz": "🛠 Admin panel", "ru": "🛠 Админ-панель", "en": "🛠 Admin panel"},
    "btn_deadlines": {"uz": "⏰ Deadlinelar", "ru": "⏰ Дедлайны", "en": "⏰ Deadlines"},
    "btn_ai": {"uz": "🤖 AI yordamchi", "ru": "🤖 ИИ-помощник", "en": "🤖 AI assistant"},
    "btn_settings": {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings"},
    "btn_lang": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "lang_set": {"uz": "✅ Til o'zgartirildi", "ru": "✅ Язык изменён", "en": "✅ Language updated"},
    "connect_hint": {
        "uz": "### 🔗 Moodle hali ulanmagan\n\nDeadlinelarni kuzatishim uchun Moodle kalendaringizni ulang:\n\n"
        "1. **Ilovani oching** — pastdagi tugma, qadam-baqadam ko'rsatma bor\n"
        "2. Yoki `export_execute.php` linkini shu chatga yuboring\n\n"
        "<sub>🔒 Parol kerak emas — link faqat kalendarni o'qiydi.</sub>",
        "ru": "### 🔗 Moodle ещё не подключён\n\nЧтобы я следил за дедлайнами, подключите календарь Moodle:\n\n"
        "1. **Откройте приложение** — кнопка ниже, там пошаговая инструкция\n"
        "2. Или пришлите в этот чат ссылку `export_execute.php`\n\n"
        "<sub>🔒 Пароль не нужен — ссылка даёт доступ только к календарю.</sub>",
        "en": "### 🔗 Moodle isn't connected yet\n\nConnect your Moodle calendar so I can track deadlines:\n\n"
        "1. **Open the app** — button below, with a step-by-step guide\n"
        "2. Or send the `export_execute.php` link to this chat\n\n"
        "<sub>🔒 No password needed — the link only reads your calendar.</sub>",
    },
    "linked_ok": {
        "uz": "### ✅ Moodle ulandi!\n\nTopilgan yaqin deadlinelar: **{n}** ta.\n\n"
        "- 🔔 Eslatmalar avtomatik yoqildi (3 kun → 1 soat oldin)\n"
        "- ⚙️ Vaqtlarni ilovadagi **Sozlamalar**da o'zgartirasiz\n"
        "- 📋 Ro'yxat: /deadlines",
        "ru": "### ✅ Moodle подключён!\n\nНайдено ближайших дедлайнов: **{n}**.\n\n"
        "- 🔔 Напоминания включены автоматически (от 3 дней до 1 часа)\n"
        "- ⚙️ Время меняется в **Настройках** приложения\n"
        "- 📋 Список: /deadlines",
        "en": "### ✅ Moodle connected!\n\nUpcoming deadlines found: **{n}**.\n\n"
        "- 🔔 Reminders are on automatically (3 days → 1 hour before)\n"
        "- ⚙️ Change the times in the app's **Settings**\n"
        "- 📋 List: /deadlines",
    },
    "err_wrong_host": {
        "uz": "❌ Bu link moodle.uwed.uz ga tegishli emas.",
        "ru": "❌ Ссылка не от moodle.uwed.uz.",
        "en": "❌ This link isn't from moodle.uwed.uz.",
    },
    "err_not_export": {
        "uz": "❌ Bu kalendar eksport linki emas. Moodle'da <b>Calendar → Export calendar → Get calendar URL</b> ni bosing va chiqqan linkni yuboring.",
        "ru": "❌ Это не ссылка экспорта календаря. В Moodle: <b>Календарь → Экспорт календаря → Получить URL календаря</b>.",
        "en": "❌ That's not a calendar export link. In Moodle: <b>Calendar → Export calendar → Get calendar URL</b>.",
    },
    "err_no_token": {
        "uz": "❌ Linkda <code>authtoken</code> yo'q. To'liq linkni nusxalang.",
        "ru": "❌ В ссылке нет <code>authtoken</code>. Скопируйте ссылку полностью.",
        "en": "❌ The link has no <code>authtoken</code>. Copy the whole link.",
    },
    "err_bad_token": {
        "uz": "❌ Moodle linkni qabul qilmadi (token eskirgan bo'lishi mumkin). Yangi link oling.",
        "ru": "❌ Moodle не принял ссылку (токен мог устареть). Получите новую ссылку.",
        "en": "❌ Moodle rejected the link (the token may be outdated). Generate a new one.",
    },
    "err_network": {
        "uz": "⚠️ Moodle hozir javob bermayapti. Birozdan so'ng qayta urinib ko'ring.",
        "ru": "⚠️ Moodle сейчас не отвечает. Попробуйте позже.",
        "en": "⚠️ Moodle isn't responding right now. Please try again later.",
    },
    "no_deadlines": {
        "uz": "### 🎉 Yaqin deadlinelar yo'q\n\nHamma vazifalar joyida — dam oling! Yangi vazifa paydo bo'lsa, o'zim xabar beraman.",
        "ru": "### 🎉 Ближайших дедлайнов нет\n\nВсё под контролем — отдыхайте! Появится новое задание — сообщу.",
        "en": "### 🎉 No upcoming deadlines\n\nAll clear — enjoy! I'll tell you when a new task appears.",
    },
    "deadlines_head": {
        "uz": "⏰ <b>Yaqin deadlinelar</b>",
        "ru": "⏰ <b>Ближайшие дедлайны</b>",
        "en": "⏰ <b>Upcoming deadlines</b>",
    },
    "btn_done": {"uz": "✅ Bajardim", "ru": "✅ Сделано", "en": "✅ Done"},
    "btn_open_moodle": {"uz": "🔗 Moodle'da ochish", "ru": "🔗 Открыть в Moodle", "en": "🔗 Open in Moodle"},
    "marked_done": {
        "uz": "✅ **Ajoyib!** Bu vazifa bo'yicha boshqa eslatma bo'lmaydi.",
        "ru": "✅ **Отлично!** Напоминаний по этому заданию больше не будет.",
        "en": "✅ **Great!** No more reminders for this task.",
    },
    "ai_intro": {
        "uz": "🤖 <b>UWED Pulse AI</b>\n\nShu yerga yozing yoki 🎤 ovozli xabar yuboring — UWED, o'qish, Moodle yoki "
        "deadlinelaringiz haqida so'rang (ovozli savolga ovoz bilan ham javob beraman). Vazifa sharti yoki o'z ishingizni 🖼 rasm / 📄 PDF qilib yuborsangiz, "
        "tushuntiraman va qayerni yaxshilash kerakligini aytaman.\n\n"
        "Masalan: <i>«Bu hafta qaysi deadlinelarim bor?»</i>\n\n🆕 Yangi mavzu: /new",
        "ru": "🤖 <b>UWED Pulse AI</b>\n\nНапишите или отправьте 🎤 голосовое — спросите об UWED, учёбе, Moodle "
        "или дедлайнах (на голосовое отвечу и голосом). Пришлите задание или свою работу 🖼 фото / 📄 PDF — объясню и подскажу, что улучшить.\n\n"
        "Например: <i>«Какие у меня дедлайны на этой неделе?»</i>\n\n🆕 Новая тема: /new",
        "en": "🤖 <b>UWED Pulse AI</b>\n\nType or send a 🎤 voice message — ask about UWED, studies, Moodle "
        "or your deadlines (voice questions get a voice reply too). Send an assignment or your own work as a 🖼 photo / 📄 PDF and I'll explain "
        "it and show what to improve.\n\n"
        "For example: <i>“What deadlines do I have this week?”</i>\n\n🆕 New topic: /new",
    },
    "ai_new": {
        "uz": "🆕 Yangi suhbat boshlandi. Savolingizni yozing!",
        "ru": "🆕 Начат новый разговор. Задайте вопрос!",
        "en": "🆕 New conversation started. Ask away!",
    },
    "btn_new_chat": {"uz": "🆕 Yangi suhbat", "ru": "🆕 Новый разговор", "en": "🆕 New chat"},
    "ai_busy": {
        "uz": "⏳ AI hozir band. Bir daqiqadan so'ng qayta yozing.",
        "ru": "⏳ ИИ сейчас занят. Попробуйте через минуту.",
        "en": "⏳ The AI is busy right now. Try again in a minute.",
    },
    "voice_too_long": {
        "uz": "🎤 Ovozli xabar juda uzun. {n} daqiqagacha bo'lsin.",
        "ru": "🎤 Голосовое слишком длинное. До {n} минут, пожалуйста.",
        "en": "🎤 That voice message is too long. Keep it under {n} minutes.",
    },
    "file_too_big": {
        "uz": "📦 Fayl juda katta (15 MB gacha).",
        "ru": "📦 Файл слишком большой (до 15 МБ).",
        "en": "📦 The file is too large (max 15 MB).",
    },
    "unsupported_file": {
        "uz": "📎 Bu turdagi faylni o'qiy olmayman. Matn, ovozli xabar, rasm yoki PDF yuboring.",
        "ru": "📎 Такой файл я не читаю. Отправьте текст, голосовое, фото или PDF.",
        "en": "📎 I can't read this file type. Send text, a voice message, a photo or a PDF.",
    },
    "app_unavailable": {
        "uz": "📱 Ilova (Mini App) hozircha ochilmaydi — tez orada ishga tushadi. "
        "Bot chatida AI yordamchi va deadlinelar ishlayapti.",
        "ru": "📱 Приложение (Mini App) пока недоступно — скоро заработает. "
        "В чате бота работают ИИ-помощник и дедлайны.",
        "en": "📱 The Mini App isn't available yet — coming soon. "
        "The AI assistant and deadlines work right here in the chat.",
    },
    "text_only": {
        "uz": "✍️ Hozircha faqat matnli xabarlarni tushunaman. Savolingizni yozib yuboring.",
        "ru": "✍️ Пока я понимаю только текст. Напишите вопрос сообщением.",
        "en": "✍️ For now I only understand text. Please type your question.",
    },
    "ai_disabled": {
        "uz": "🤖 AI yordamchi vaqtincha o'chirilgan.",
        "ru": "🤖 ИИ-помощник временно отключён.",
        "en": "🤖 The AI assistant is temporarily disabled.",
    },
    "ai_limit": {
        "uz": "⏳ Bugungi AI limiti tugadi. Ertaga davom etamiz!",
        "ru": "⏳ Дневной лимит ИИ исчерпан. Продолжим завтра!",
        "en": "⏳ Today's AI limit is reached. See you tomorrow!",
    },
    "ai_error": {
        "uz": "⚠️ AI hozir javob bera olmadi. Keyinroq urinib ko'ring.",
        "ru": "⚠️ ИИ сейчас не смог ответить. Попробуйте позже.",
        "en": "⚠️ The AI couldn't answer right now. Please try later.",
    },
    "banned": {
        "uz": "### ⛔ Hisob bloklangan\n\nSavollar bo'lsa, dekanatga murojaat qiling.",
        "ru": "### ⛔ Аккаунт заблокирован\n\nПо вопросам обратитесь в деканат.",
        "en": "### ⛔ Account blocked\n\nPlease contact the dean's office if you have questions.",
    },
    "maintenance": {
        "uz": "### 🛠 Texnik ishlar\n\nBotni yaxshilayapmiz — tez orada qaytamiz!",
        "ru": "### 🛠 Технические работы\n\nУлучшаем бота — скоро вернёмся!",
        "en": "### 🛠 Maintenance\n\nWe're improving the bot — back soon!",
    },
    "left": {"uz": "Qoldi", "ru": "Осталось", "en": "Left"},
}

# Reminder texts: escalating urgency, keyed by offset in minutes.
REMINDERS: dict[int, dict[str, str]] = {
    4320: {
        "uz": "📅 <b>3 kun qoldi</b> — rejalashtirishga ayni vaqt.",
        "ru": "📅 <b>Осталось 3 дня</b> — самое время спланировать.",
        "en": "📅 <b>3 days left</b> — a good time to plan.",
    },
    1440: {
        "uz": "🗓 <b>Ertaga muddat!</b> 1 kun qoldi.",
        "ru": "🗓 <b>Срок завтра!</b> Остался 1 день.",
        "en": "🗓 <b>Due tomorrow!</b> 1 day left.",
    },
    720: {
        "uz": "⏳ <b>12 soat qoldi.</b> Bugun tugatib qo'ysangiz bo'ladi.",
        "ru": "⏳ <b>Осталось 12 часов.</b> Лучше закончить сегодня.",
        "en": "⏳ <b>12 hours left.</b> Best to finish today.",
    },
    360: {
        "uz": "⚠️ <b>6 soat qoldi!</b>",
        "ru": "⚠️ <b>Осталось 6 часов!</b>",
        "en": "⚠️ <b>6 hours left!</b>",
    },
    180: {
        "uz": "🔥 <b>3 soat qoldi!</b> Hozir boshlang.",
        "ru": "🔥 <b>Осталось 3 часа!</b> Начинайте сейчас.",
        "en": "🔥 <b>3 hours left!</b> Start now.",
    },
    120: {
        "uz": "🔥🔥 <b>2 soat qoldi!</b>",
        "ru": "🔥🔥 <b>Осталось 2 часа!</b>",
        "en": "🔥🔥 <b>2 hours left!</b>",
    },
    60: {
        "uz": "🚨 <b>1 soat qoldi!</b> Topshirishni unutmang!",
        "ru": "🚨 <b>Остался 1 час!</b> Не забудьте сдать!",
        "en": "🚨 <b>1 hour left!</b> Don't forget to submit!",
    },
}


def t(key: str, lang: str = "uz", **kw) -> str:
    entry = T.get(key, {})
    text = entry.get(lang) or entry.get("uz") or key
    return text.format(**kw) if kw else text


def reminder_head(offset_min: int, lang: str) -> str:
    if offset_min in REMINDERS:
        return REMINDERS[offset_min].get(lang, REMINDERS[offset_min]["uz"])
    hours = offset_min // 60
    unit = {"uz": "soat qoldi", "ru": "ч. осталось", "en": "hours left"}[lang if lang in LANGS else "uz"]
    return f"⏰ <b>{hours} {unit}</b>"


def humanize_left(minutes: int, lang: str) -> str:
    units = {
        "uz": ("kun", "soat", "daqiqa"),
        "ru": ("дн", "ч", "мин"),
        "en": ("d", "h", "min"),
    }[lang if lang in LANGS else "uz"]
    minutes = max(minutes, 0)
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    if d:
        return f"{d} {units[0]} {h} {units[1]}"
    if h:
        return f"{h} {units[1]} {m} {units[2]}"
    return f"{m} {units[2]}"
