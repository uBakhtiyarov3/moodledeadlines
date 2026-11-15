"""Turn any file a student sends into something the AI can read.

Gemini reads images, PDF, audio and video directly. Office documents (Word, PowerPoint, Excel and
their OpenDocument twins) are unpacked to plain text here with the standard library; text and code
files are passed as text.
"""

import html
import io
import re
import zipfile

MAX_TEXT = 200_000  # characters of extracted text sent to the AI
MAX_UNZIPPED = 60 * 1024 * 1024  # zip-bomb guard

NATIVE = {
    "image/jpeg": "image", "image/png": "image", "image/webp": "image", "image/heic": "image", "image/heif": "image",
    "application/pdf": "document",
    "audio/ogg": "audio", "audio/mpeg": "audio", "audio/mp3": "audio", "audio/wav": "audio", "audio/x-wav": "audio",
    "audio/aac": "audio", "audio/mp4": "audio", "audio/x-m4a": "audio", "audio/flac": "audio",
    "video/mp4": "video", "video/quicktime": "video", "video/webm": "video", "video/mpeg": "video", "video/3gpp": "video",
}
EXT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "heic": "image/heic",
    "pdf": "application/pdf", "ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg", "wav": "audio/wav",
    "m4a": "audio/mp4", "aac": "audio/aac", "flac": "audio/flac", "mp4": "video/mp4", "mov": "video/quicktime",
    "webm": "video/webm",
}
OFFICE = {"docx", "pptx", "xlsx", "odt", "odp", "ods"}
TEXT_EXT = {
    "txt", "md", "csv", "tsv", "json", "xml", "html", "htm", "rtf", "tex", "log", "yaml", "yml", "ini", "srt",
    "py", "js", "ts", "java", "c", "cpp", "h", "cs", "go", "rs", "php", "rb", "kt", "swift", "sql", "sh", "r", "m",
    "ipynb",
}
OLD_BINARY = {"doc", "ppt", "xls"}


class UnsupportedFile(ValueError):
    """code: unsupported | old_format | empty"""


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in (name or "") else ""


def prepare(name: str, mime: str, data: bytes) -> tuple[str, str, bytes]:
    """(kind, mime, data) ready for the AI. Office/text files become text/plain."""
    ext, mime = _ext(name), (mime or "").lower()
    if mime in ("", "application/octet-stream") and ext in EXT_MIME:
        mime = EXT_MIME[ext]
    if mime in NATIVE:
        return NATIVE[mime], mime, data
    if ext in OFFICE:
        text = office_text(ext, data)
    elif ext in TEXT_EXT or mime.startswith("text/") or mime in ("application/json", "application/xml"):
        text = decode(data)
    elif ext in OLD_BINARY:
        raise UnsupportedFile("old_format")
    else:
        raise UnsupportedFile("unsupported")
    text = text.strip()
    if not text:
        raise UnsupportedFile("empty")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + "\n…[truncated]"
    return "document", "text/plain", f"=== File: {name} ===\n{text}".encode()


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# ---------------------------------------------------------------- Office Open XML / OpenDocument

def _read(z: zipfile.ZipFile, member: str) -> str:
    info = z.getinfo(member)
    if info.file_size > MAX_UNZIPPED:
        raise UnsupportedFile("unsupported")
    return z.read(member).decode("utf-8", errors="ignore")


def _num(name: str) -> int:
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def _flow(xml: str, text_tag: str, breaks: dict[str, str]) -> str:
    """Walk the XML once: keep text of `text_tag` elements, turn the given closing/empty tags into separators."""
    pattern = re.compile(rf"<{text_tag}(?:\s[^>]*)?>(.*?)</{text_tag}>|<(/?)([\w:]+)[^>]*?(/?)>", re.S)
    out = []
    for m in pattern.finditer(xml):
        if m.group(1) is not None:
            out.append(html.unescape(m.group(1)))
            continue
        closing, tag, empty = m.group(2), m.group(3), m.group(4)
        key = ("/" if closing else "") + tag + ("/" if empty else "")
        if key in breaks:
            out.append(breaks[key])
    text = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", text)


def office_text(ext: str, data: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise UnsupportedFile("unsupported") from e
    names = z.namelist()
    if ext == "docx":
        parts = ["word/document.xml"] + sorted(n for n in names if re.match(r"word/(footnotes|endnotes)\.xml$", n))
        text = "\n".join(_flow(_read(z, p), "w:t", {"/w:p": "\n", "w:tab/": "\t", "w:br/": "\n", "/w:tc": " | ", "/w:tr": "\n"})
                          for p in parts if p in names)
        return re.sub(r" \| *\n", "\n", re.sub(r"\n \| ", " | ", text))  # table cells on one line
    if ext == "pptx":
        slides = sorted((n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)), key=_num)
        return "\n\n".join(f"--- Slide {_num(s)} ---\n" + _flow(_read(z, s), "a:t", {"/a:p": "\n", "a:br/": "\n"}).strip()
                           for s in slides)
    if ext == "xlsx":
        return _xlsx(z, names)
    # OpenDocument: odt / odp / ods
    if "content.xml" not in names:
        raise UnsupportedFile("unsupported")
    return _odf(_read(z, "content.xml"))


def _odf(xml: str) -> str:
    xml = re.sub(r"<text:tab\s*/>", "\t", xml)
    xml = re.sub(r"<text:line-break\s*/>", "\n", xml)
    xml = re.sub(r"<text:s(?:\s+text:c=\"(\d+)\")?\s*/>", lambda m: " " * int(m.group(1) or 1), xml)
    xml = re.sub(r"</(text:p|text:h|table:table-row|draw:page)>", "\n", xml)
    xml = re.sub(r"</table:table-cell>", " | ", xml)
    text = html.unescape(re.sub(r"<[^>]+>", "", xml))
    return re.sub(r"\n{3,}", "\n\n", text)


def _xlsx(z: zipfile.ZipFile, names: list[str], max_rows: int = 2000) -> str:
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in re.findall(r"<si>(.*?)</si>", _read(z, "xl/sharedStrings.xml"), re.S):
            shared.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    sheet_names = re.findall(r'<sheet [^>]*name="([^"]+)"', _read(z, "xl/workbook.xml")) if "xl/workbook.xml" in names else []
    out = []
    for i, sheet in enumerate(sorted((n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n)), key=_num)):
        title = html.unescape(sheet_names[i]) if i < len(sheet_names) else f"Sheet {i + 1}"
        rows = []
        for row in re.findall(r"<row[^>]*>(.*?)</row>", _read(z, sheet), re.S)[:max_rows]:
            cells = []
            for attrs, body in re.findall(r"<c([^>]*)>(.*?)</c>", row, re.S):
                v = re.search(r"<v>(.*?)</v>", body, re.S)
                if 't="s"' in attrs and v:
                    idx = int(v.group(1))
                    cells.append(shared[idx] if idx < len(shared) else "")
                elif 't="inlineStr"' in attrs:
                    cells.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", body, re.S))))
                else:
                    cells.append(html.unescape(v.group(1)) if v else "")
            rows.append(" | ".join(cells))
        out.append(f"--- {title} ---\n" + "\n".join(rows))
    return "\n\n".join(out)
