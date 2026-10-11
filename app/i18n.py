"""Bot-side texts in Uzbek, Russian and English (Telegram HTML)."""

LANGS = ("uz", "ru", "en")

T: dict[str, dict[str, str]] = {
    "choose_lang": {
        "uz": "🌐 Tilni tanlang",
        "ru": "🌐 Выберите язык",
        "en": "🌐 Choose your language",
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
    "open_app": {"uz": "📱 Ilovani ochish", "ru": "📱 Открыть приложение", "en": "📱 Open app"},
    "open_admin": {"uz": "🛠 Admin panel", "ru": "🛠 Админ-панель", "en": "🛠 Admin panel"},
    "btn_deadlines": {"uz": "⏰ Deadlinelar", "ru": "⏰ Дедлайны", "en": "⏰ Deadlines"},
    "btn_ai": {"uz": "🤖 AI yordamchi", "ru": "🤖 ИИ-помощник", "en": "🤖 AI assistant"},
    "btn_settings": {"uz": "⚙️ Sozlamalar", "ru": "⚙️ Настройки", "en": "⚙️ Settings"},
    "btn_lang": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "lang_set": {"uz": "✅ Til o'zgartirildi", "ru": "✅ Язык изменён", "en": "✅ Language updated"},
    "connect_hint": {
        "uz": "🔗 Moodle hali ulanmagan. Ilovada <b>Moodle'ni ulash</b> bo'limida qadam-baqadam ko'rsatma bor.\n"
        "Yoki <code>export_execute.php</code> linkini shu yerga yuboring.",
        "ru": "🔗 Moodle ещё не подключён. В приложении есть пошаговая инструкция <b>Подключить Moodle</b>.\n"
        "Или просто пришлите сюда ссылку <code>export_execute.php</code>.",
        "en": "🔗 Moodle isn't connected yet. The app has a step-by-step <b>Connect Moodle</b> guide.\n"
        "Or just send the <code>export_execute.php</code> link here.",
    },
    "linked_ok": {
        "uz": "✅ Moodle ulandi! <b>{n}</b> ta yaqin deadline topildi. Eslatmalar avtomatik yoqildi.",
        "ru": "✅ Moodle подключён! Найдено дедлайнов: <b>{n}</b>. Напоминания включены.",
        "en": "✅ Moodle connected! Found <b>{n}</b> upcoming deadlines. Reminders are on.",
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
        "uz": "🎉 Yaqin deadlinelar yo'q. Dam oling!",
        "ru": "🎉 Ближайших дедлайнов нет. Отдыхайте!",
        "en": "🎉 No upcoming deadlines. Enjoy!",
    },
    "deadlines_head": {
        "uz": "⏰ <b>Yaqin deadlinelar</b>",
        "ru": "⏰ <b>Ближайшие дедлайны</b>",
        "en": "⏰ <b>Upcoming deadlines</b>",
    },
    "btn_done": {"uz": "✅ Bajardim", "ru": "✅ Сделано", "en": "✅ Done"},
    "btn_open_moodle": {"uz": "🔗 Moodle'da ochish", "ru": "🔗 Открыть в Moodle", "en": "🔗 Open in Moodle"},
    "marked_done": {
        "uz": "✅ Ajoyib! Bu vazifa bo'yicha boshqa eslatma bo'lmaydi.",
        "ru": "✅ Отлично! Напоминаний по этому заданию больше не будет.",
        "en": "✅ Great! No more reminders for this task.",
    },
    "ai_intro": {
        "uz": "🤖 <b>UWED Pulse AI</b>\n\nShu yerga yozing yoki 🎤 ovozli xabar yuboring — UWED, o'qish, Moodle yoki "
        "deadlinelaringiz haqida so'rang. Vazifa sharti yoki o'z ishingizni 🖼 rasm / 📄 PDF qilib yuborsangiz, "
        "tushuntiraman va qayerni yaxshilash kerakligini aytaman.\n\n"
        "Masalan: <i>«Bu hafta qaysi deadlinelarim bor?»</i>\n\n🆕 Yangi mavzu: /new",
        "ru": "🤖 <b>UWED Pulse AI</b>\n\nНапишите или отправьте 🎤 голосовое — спросите об UWED, учёбе, Moodle "
        "или дедлайнах. Пришлите задание или свою работу 🖼 фото / 📄 PDF — объясню и подскажу, что улучшить.\n\n"
        "Например: <i>«Какие у меня дедлайны на этой неделе?»</i>\n\n🆕 Новая тема: /new",
        "en": "🤖 <b>UWED Pulse AI</b>\n\nType or send a 🎤 voice message — ask about UWED, studies, Moodle "
        "or your deadlines. Send an assignment or your own work as a 🖼 photo / 📄 PDF and I'll explain "
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
        "uz": "⛔ Sizning hisobingiz bloklangan.",
        "ru": "⛔ Ваш аккаунт заблокирован.",
        "en": "⛔ Your account is blocked.",
    },
    "maintenance": {
        "uz": "🛠 Botda texnik ishlar olib borilmoqda. Tez orada qaytamiz!",
        "ru": "🛠 Идут технические работы. Скоро вернёмся!",
        "en": "🛠 Maintenance in progress. We'll be back soon!",
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
