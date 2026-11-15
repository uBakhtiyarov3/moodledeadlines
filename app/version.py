"""The one place the UWED Pulse version lives. Bump it (and add to CHANGES) with every release."""

VERSION = "3.0.2"
RELEASED = "2026-11-15"

# What's new, shown in the Mini App (tap the version): this release first, then the previous big one.
CHANGES = {
    "uz": [
        "🎓 Baholarda faqat joriy öquv dasturi kurslari (Moodle 330-kategoriya)",
        "⭕ Eng yaqin deadline uçun aylana taymer",
        "🎨 Butunlay yangi dizayn: yangi şrift, toza kartalar, gradientli bosh ekran",
        "⏱ Bosh ekranda katta taymer, tez amallar va kurs belgili rangli kartalar",
        "🎓 Baholar: doira diagrammalar, örtaça ball, rangli baholar",
        "✨ Yangi dizayn: silliq animatsiyalar, sirpanuvçi menyu, sahifalar yön böyiça almaşadi",
        "👆 Oynalarni pastga tortib yopiş, bosganda jonli javob, vazifa bajarilganda konfetti",
        "🎓 Baholar bölimi: Moodle'dagi har bir kurs böyiça baholar, ustoz izohlari va jami ball",
        "🙈 Keraksiz kurslarni yaşiriş — baholari, deadlinelari va eslatmalari körinmaydi",
        "📛 Kurs nomlari töliq körsatiladi",
        "🤖 AI endi agent: eslatma qöyadi, deadlinelarni belgilaydi, sozlamalarni özgartiradi, adminga yozadi",
        "📝 Moodle Pro: ustoz baho qöysa xabar keladi, AI topşirigingizni mezonlar böyiça tekşiradi",
        "📎 Word, PowerPoint, Excel, video va matn fayllarni tuşunadi",
        "🔘 Javoblar ostida tugmalar: tez javob, test, havolalar",
        "👤 Profil va AI xotirasi — AI sizni taniydi",
        "⚡ Gemini 4 Hydrogen modeli",
        "🔤 Yangi özbek lotin alifbosi",
    ],
    "ru": [
        "🎓 В оценках только курсы текущей программы (категория Moodle 330)",
        "⭕ Кольцевой таймер до ближайшего дедлайна",
        "🎨 Полностью новый дизайн: новый шрифт, чистые карточки, градиентный главный экран",
        "⏱ Большой таймер, быстрые действия и цветные карточки курсов на главной",
        "🎓 Оценки: круговые диаграммы, средний балл, цветные оценки",
        "✨ Новый дизайн: плавные анимации, скользящее меню, страницы листаются по направлению",
        "👆 Окна закрываются свайпом вниз, живой отклик на нажатия, конфетти за выполненное задание",
        "🎓 Раздел «Оценки»: оценки по каждому курсу Moodle, комментарии преподавателей и итог",
        "🙈 Ненужные курсы можно скрыть — без их оценок, дедлайнов и напоминаний",
        "📛 Названия курсов показываются полностью",
        "🤖 ИИ стал агентом: ставит напоминания, отмечает дедлайны, меняет настройки, пишет админу",
        "📝 Moodle Pro: уведомления об оценках и проверка ваших работ ИИ по критериям",
        "📎 Понимает Word, PowerPoint, Excel, видео и текстовые файлы",
        "🔘 Кнопки под ответами: быстрые ответы, тесты, ссылки",
        "👤 Профиль и память ИИ — он вас узнаёт",
        "⚡ Модель Gemini 4 Hydrogen",
        "🔤 Новый узбекский латинский алфавит",
    ],
    "en": [
        "🎓 Grades show only the current programme's courses (Moodle category 330)",
        "⭕ A ring countdown to the next deadline",
        "🎨 A completely new design: new typeface, clean cards, gradient home screen",
        "⏱ Big countdown, quick actions and colour-coded course cards on the home screen",
        "🎓 Grades: progress rings, average score, colour-coded grades",
        "✨ New design: smooth animations, a sliding tab bar, pages that move the way you navigate",
        "👆 Swipe sheets down to close, lively touch feedback, confetti when a task is done",
        "🎓 Grades: every Moodle course with its grades, teacher feedback and total",
        "🙈 Hide courses you don't need — their grades, deadlines and reminders go away",
        "📛 Full course names",
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
