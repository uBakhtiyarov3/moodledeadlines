"""The one place the UWED Pulse version lives. Bump it (and add to CHANGES) with every release."""

VERSION = "2.0.0"
RELEASED = "2026-11-15"

# What's new in this version, shown in the Mini App (tap the version) — newest release only.
CHANGES = {
    "uz": [
        "🤖 AI endi agent: eslatma qöyadi, deadlinelarni belgilaydi, sozlamalarni özgartiradi, adminga yozadi",
        "📝 Moodle Pro: ustoz baho qöysa xabar keladi, AI topşirigingizni mezonlar böyiça tekşiradi",
        "📎 Word, PowerPoint, Excel, video va matn fayllarni tuşunadi",
        "🔘 Javoblar ostida tugmalar: tez javob, test, havolalar",
        "👤 Profil va AI xotirasi — AI sizni taniydi",
        "⚡ Gemini 4 Hydrogen modeli",
        "🔤 Yangi özbek lotin alifbosi",
    ],
    "ru": [
        "🤖 ИИ стал агентом: ставит напоминания, отмечает дедлайны, меняет настройки, пишет админу",
        "📝 Moodle Pro: уведомления об оценках и проверка ваших работ ИИ по критериям",
        "📎 Понимает Word, PowerPoint, Excel, видео и текстовые файлы",
        "🔘 Кнопки под ответами: быстрые ответы, тесты, ссылки",
        "👤 Профиль и память ИИ — он вас узнаёт",
        "⚡ Модель Gemini 4 Hydrogen",
        "🔤 Новый узбекский латинский алфавит",
    ],
    "en": [
        "🤖 The AI is now an agent: sets reminders, marks deadlines, changes settings, messages the admins",
        "📝 Moodle Pro: grade alerts and AI review of your submissions against the criteria",
        "📎 Understands Word, PowerPoint, Excel, video and text files",
        "🔘 Buttons under answers: quick replies, quizzes, links",
        "👤 Profile and AI memory — it knows who you are",
        "⚡ Gemini 4 Hydrogen model",
        "🔤 The new Uzbek Latin alphabet",
    ],
}


def changes(lang: str) -> list[str]:
    return CHANGES.get(lang) or CHANGES["en"]
