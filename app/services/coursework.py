"""Moodle coursework through the student's own web-service token ("Pro" connection).

- the student's assignments, and everything needed to review a submission: the brief, its attached
  files, the grading criteria (rubric / marking guide when Moodle exposes them), the submitted files
  and online text, and the teacher's grade and feedback;
- new grades and teacher feedback → a Telegram notification (checked periodically).
"""

import hashlib
import html
import logging
import re
from datetime import datetime, timezone

import httpx
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.config import get_settings
from app.db import Session
from app.models import GradeSeen, HiddenCourse, User
from app.moodle import ws
from app.security import decrypt
from app.services import coursenames, files

log = logging.getLogger(__name__)

MAX_REVIEW_TEXT = 150_000  # characters of files handed to the AI in one review


class NotConnected(Exception):
    pass


def token_of(user: User) -> str:
    token = decrypt(user.ws_token_enc) if user else None
    if not token:
        raise NotConnected("Moodle account is not connected: the student connects it in the app "
                           "(Settings → Moodle → Pro, Moodle login once; the password is not stored).")
    return token


def plain(htmltext: str | None, limit: int = 20000) -> str:
    text = re.sub(r"<(br|/p|/li|/h\d|/tr)\s*/?>", "\n", htmltext or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()[:limit]


def _local(ts: int | None) -> str | None:
    if not ts:
        return None
    from app.services.tasks import local_str

    return local_str(datetime.fromtimestamp(int(ts), timezone.utc))


async def assignments(token: str) -> list[dict]:
    data = await ws.call(token, "mod_assign_get_assignments")
    await coursenames.remember(data.get("courses", []) if isinstance(data, dict) else [])
    out = []
    for course in data.get("courses", []) if isinstance(data, dict) else []:
        for a in course.get("assignments", []):
            out.append({"assignment_id": a["id"], "name": a.get("name"), "course": course.get("fullname") or course.get("shortname"),
                        "due": _local(a.get("duedate")), "max_grade": a.get("grade"),
                        "_intro": a.get("intro"), "_attachments": a.get("introattachments") or [], "_cmid": a.get("cmid")})
    return out


async def _file_texts(token: str, items: list[dict], budget: list[int]) -> list[dict]:
    """Download Moodle files and turn them into text for the AI (within a shared size budget)."""
    out = []
    for f in items[:10]:
        name, url = f.get("filename") or "file", f.get("fileurl") or ""
        entry = {"file": name}
        if budget[0] <= 0:
            entry["note"] = "skipped: too much text already"
        else:
            data = await ws.download(token, url) if url else None
            text = files.as_text(name, f.get("mimetype") or "", data) if data else None
            if text:
                entry["text"] = text[: budget[0]]
                budget[0] -= len(entry["text"])
            else:
                entry["note"] = "could not be read as text (image, scan or unsupported format)"
        out.append(entry)
    return out


async def _criteria(token: str, cmid: int | None) -> list[dict]:
    """Rubric / marking guide, when Moodle lets the student see it (often hidden until graded)."""
    if not cmid:
        return []
    try:
        data = await ws.call(token, "core_grading_get_definitions", **{"cmids[0]": cmid, "areaname": "submissions"})
    except (ws.MoodleAuthError, httpx.HTTPError):
        return []
    out = []
    for area in data.get("areas", []) if isinstance(data, dict) else []:
        for d in area.get("definitions", []):
            rubric = (d.get("rubric") or {}).get("rubric_criteria") or []
            for c in rubric:
                out.append({"criterion": plain(c.get("description"), 1000),
                            "levels": [f"{lv.get('score')}: {plain(lv.get('definition'), 400)}" for lv in c.get("levels", [])]})
            guide = (d.get("guide") or {}).get("guide_criteria") or []
            for c in guide:
                out.append({"criterion": c.get("shortname"), "max_score": c.get("maxscore"),
                            "description": plain(c.get("description"), 1000),
                            "markers": plain(c.get("descriptionmarkers"), 1000)})
    return out


async def review_bundle(user: User, assignment_id: int) -> dict:
    """Everything the AI needs to review the student's submission for one assignment."""
    token = token_of(user)
    found = next((a for a in await assignments(token) if a["assignment_id"] == int(assignment_id)), None)
    if not found:
        return {"error": "assignment not found among the student's courses"}
    budget = [MAX_REVIEW_TEXT]
    bundle = {
        "assignment": found["name"], "course": found["course"], "due": found["due"], "max_grade": found["max_grade"],
        "brief": plain(found["_intro"]),
        "brief_files": await _file_texts(token, found["_attachments"], budget),
        "criteria": await _criteria(token, found["_cmid"]),
    }
    status = await ws.call(token, "mod_assign_get_submission_status", assignid=int(assignment_id))
    attempt = (status or {}).get("lastattempt") or {}
    sub = attempt.get("submission") or attempt.get("teamsubmission") or {}
    submitted_files, online_text = [], ""
    for plugin in sub.get("plugins", []):
        for area in plugin.get("fileareas", []):
            submitted_files += area.get("files", [])
        for field in plugin.get("editorfields", []):
            online_text += plain(field.get("text"), 60000) + "\n"
    bundle["submission_status"] = sub.get("status") or "nothing submitted"
    bundle["submitted_at"] = _local(sub.get("timemodified"))
    bundle["submitted_text"] = online_text.strip() or None
    bundle["submitted_files"] = await _file_texts(token, submitted_files, budget)
    fb = (status or {}).get("feedback") or {}
    if fb:
        comments = " ".join(plain(f.get("text"), 4000) for p in fb.get("plugins", []) for f in p.get("editorfields", []))
        bundle["teacher_feedback"] = {"grade": plain(fb.get("gradefordisplay")), "graded_at": _local(fb.get("gradeddate")),
                                      "comments": comments or None}
    if not bundle["criteria"]:
        bundle["criteria_note"] = "Moodle shows no rubric to the student; take the criteria from the brief and its files."
    return bundle


# ---------------------------------------------------------------- grades page (Mini App)

_overview_cache: dict[int, tuple[float, list[dict]]] = {}
OVERVIEW_TTL = 600  # seconds; Moodle is asked at most every 10 minutes per student unless refreshed


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_category_cache: dict[tuple, tuple[float, set[int]]] = {}


async def allowed_categories(token: str) -> set[int] | None:
    """The grades page's Moodle categories (admin setting) plus all their subcategories; None = no filter."""
    import time

    from app.services import settings as rt

    roots = tuple(sorted(int(c) for c in rt.get("grades_categories") or []))
    if not roots:
        return None
    cached = _category_cache.get(roots)
    if cached and time.monotonic() - cached[0] < 3600:
        return cached[1]
    ids = set(roots)
    for root in roots:
        try:
            cats = await ws.call(token, "core_course_get_categories", **{
                "criteria[0][key]": "id", "criteria[0][value]": root, "addsubcategories": 1})
        except (ws.MoodleAuthError, httpx.HTTPError):
            continue  # can't read the tree: the category itself still works
        for cat in cats if isinstance(cats, list) else []:
            path = [int(x) for x in str(cat.get("path") or "").split("/") if x.isdigit()]
            if root in path or cat.get("id") == root:
                ids.add(int(cat["id"]))
    _category_cache[roots] = (time.monotonic(), ids)
    return ids


async def overview(user: User, refresh: bool = False) -> list[dict]:
    """Every enrolled course with its full name, course total and graded items."""
    import time

    cached = _overview_cache.get(user.id)
    if cached and not refresh and time.monotonic() - cached[0] < OVERVIEW_TTL:
        return cached[1]
    token = token_of(user)
    userid = user.moodle_userid or await ws.site_userid_safe(token)
    base = get_settings().moodle_base.rstrip("/")
    courses = await ws.call(token, "core_enrol_get_users_courses", userid=userid)
    await coursenames.remember(courses if isinstance(courses, list) else [])
    allowed = await allowed_categories(token)
    if allowed is not None and isinstance(courses, list):  # only the university's current study programme
        courses = [c for c in courses if c.get("category") is None or int(c["category"]) in allowed]
    out = []
    for c in courses if isinstance(courses, list) else []:
        entry = {"id": c["id"], "fullname": plain(c.get("fullname"), 255) or c.get("shortname") or "—",
                 "shortname": c.get("shortname") or "", "url": f"{base}/grade/report/user/index.php?id={c['id']}",
                 "total": None, "items": []}
        try:
            data = await ws.call(token, "gradereport_user_get_grade_items", courseid=c["id"], userid=userid)
        except ws.MoodleAuthError:
            data = {}
        for ug in data.get("usergrades", []) if isinstance(data, dict) else []:
            for gi in ug.get("gradeitems", []):
                raw, gmax, gmin = _num(gi.get("graderaw")), _num(gi.get("grademax")), _num(gi.get("grademin")) or 0
                pct = round((raw - gmin) / (gmax - gmin) * 100) if raw is not None and gmax and gmax > gmin else None
                shown = plain(gi.get("gradeformatted"), 40)
                row = {"name": gi.get("itemname") or "", "grade": shown if shown and shown != "-" else None,
                       "max": gmax, "percent": pct, "feedback": plain(gi.get("feedback"), 600) or None,
                       "graded_at": _local(gi.get("gradedategraded"))}
                if gi.get("itemtype") == "course":
                    entry["total"] = {k: row[k] for k in ("grade", "max", "percent")}
                elif gi.get("itemtype") != "category":
                    if gi.get("cmid") and gi.get("itemmodule"):
                        row["url"] = f"{base}/mod/{gi['itemmodule']}/view.php?id={gi['cmid']}"
                    entry["items"].append(row)
        out.append(entry)
    _overview_cache[user.id] = (time.monotonic(), out)
    return out


async def hidden(user_id: int) -> list[HiddenCourse]:
    async with Session() as s:
        return (await s.execute(select(HiddenCourse).where(HiddenCourse.user_id == user_id))).scalars().all()


async def hidden_names(user_id: int) -> set[str]:
    return {n for h in await hidden(user_id) for n in (h.fullname, h.shortname) if n}


async def set_hidden(user: User, course_id: int, hide: bool, fullname: str = "", shortname: str = "") -> None:
    """Hide/show a course: grades page, deadlines list, reminders and grade alerts follow."""
    async with Session() as s:
        row = (await s.execute(select(HiddenCourse).where(HiddenCourse.user_id == user.id,
                                                          HiddenCourse.course_id == course_id))).scalar_one_or_none()
        u = await s.get(User, user.id)
        names = {n for n in ((row.fullname, row.shortname) if row else (fullname, shortname)) if n}
        muted = [m for m in (u.muted_courses or []) if m not in names]
        if hide:
            if not row:
                s.add(HiddenCourse(user_id=user.id, course_id=course_id, fullname=fullname[:255], shortname=shortname[:255]))
            muted += sorted(names)
        elif row:
            await s.delete(row)
        u.muted_courses = muted[:100]
        await s.commit()


# ---------------------------------------------------------------- grade notifications

async def _grade_items(token: str, userid: int) -> list[dict]:
    courses = await ws.call(token, "core_enrol_get_users_courses", userid=userid)
    await coursenames.remember(courses if isinstance(courses, list) else [])
    allowed = await allowed_categories(token)
    if allowed is not None and isinstance(courses, list):
        courses = [c for c in courses if c.get("category") is None or int(c["category"]) in allowed]
    items = []
    for course in courses if isinstance(courses, list) else []:
        try:
            data = await ws.call(token, "gradereport_user_get_grade_items", courseid=course["id"], userid=userid)
        except ws.MoodleAuthError:
            continue
        for ug in data.get("usergrades", []) if isinstance(data, dict) else []:
            for gi in ug.get("gradeitems", []):
                if gi.get("itemtype") == "course" or gi.get("graderaw") is None and not gi.get("feedback"):
                    continue
                items.append({"key": f"{course['id']}:{gi.get('id')}", "course": course.get("fullname") or course.get("shortname"),
                              "name": gi.get("itemname") or "—", "grade": gi.get("gradeformatted") or "",
                              "max": gi.get("grademax"), "feedback": plain(gi.get("feedback"), 1500),
                              "cmid": gi.get("cmid"), "module": gi.get("itemmodule")})
    return items


def _fingerprint(item: dict) -> str:
    return hashlib.sha1(f"{item['grade']}|{item['feedback']}".encode()).hexdigest()


async def check_user(bot: Bot, user: User) -> int:
    """Notify the student about new or changed grades/feedback. Returns how many were sent."""
    from app.bot import rich
    from app.i18n import t

    token = token_of(user)
    userid = user.moodle_userid or await ws.site_userid_safe(token)
    if not userid:
        return 0
    skip = {h.course_id for h in await hidden(user.id)}
    items = [i for i in await _grade_items(token, userid) if int(i["key"].split(":")[0]) not in skip]
    async with Session() as s:
        seen = {g.item_key: g for g in (await s.execute(select(GradeSeen).where(GradeSeen.user_id == user.id))).scalars()}
        first_run = "*" not in seen
        if first_run:  # remember that the baseline is taken, even if nothing is graded yet
            s.add(GradeSeen(user_id=user.id, item_key="*", fingerprint="-"))
        sent = 0
        for item in items:
            fp = _fingerprint(item)
            old = seen.get(item["key"])
            if old and old.fingerprint == fp:
                continue
            if old:
                old.fingerprint, old.name, old.updated_at = fp, item["name"][:255], datetime.now(timezone.utc)
            else:
                s.add(GradeSeen(user_id=user.id, item_key=item["key"], name=item["name"][:255], fingerprint=fp))
            if first_run:
                continue  # the first look only records what's already there
            grade = f"**{rich.esc(item['grade'])}**" + (f" / {float(item['max']):g}" if item.get("max") else "")
            text = (f"### 📝 {t('grade_new', user.lang)}\n**{rich.esc(item['name'])}**\n<sub>{rich.esc(item['course'] or '')}</sub>\n\n"
                    f"> {grade}")
            if item["feedback"]:
                text += f"\n\n💬 **{t('grade_feedback', user.lang)}**\n> " + rich.esc(item["feedback"]).replace("\n", "\n> ")
            row = [InlineKeyboardButton(text=t("grade_analyse", user.lang), callback_data=f"grade:{item['key']}"[:64],
                                        style="primary")]
            if item.get("cmid") and item.get("module"):
                url = f"{get_settings().moodle_base.rstrip('/')}/mod/{item['module']}/view.php?id={item['cmid']}"
                row.append(InlineKeyboardButton(text="🔗 Moodle", url=url))
            await rich.send(bot, user.id, text, InlineKeyboardMarkup(inline_keyboard=[row]))
            sent += 1
        await s.commit()
    return sent


async def check_all(bot: Bot) -> None:
    async with Session() as s:
        users = (await s.execute(select(User).where(User.ws_token_enc.is_not(None), User.is_banned.is_(False),
                                                    User.blocked_bot.is_(False)))).scalars().all()
    for u in users:
        try:
            await check_user(bot, u)
        except NotConnected:
            continue
        except ws.MoodleAuthError as e:
            log.info("grades for %s: %s", u.id, e.code)
        except httpx.HTTPError:
            log.info("grades for %s: network", u.id)
        except Exception:  # noqa: BLE001
            log.exception("grades for %s failed", u.id)
