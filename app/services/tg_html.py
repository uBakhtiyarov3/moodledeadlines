"""Convert rich-text editor HTML into the subset Telegram accepts (parse_mode=HTML)."""

import html
import re
from html.parser import HTMLParser

INLINE = {
    "b": "b", "strong": "b",
    "i": "i", "em": "i",
    "u": "u", "ins": "u",
    "s": "s", "strike": "s", "del": "s",
    "code": "code", "pre": "pre",
    "tg-spoiler": "tg-spoiler",
    "blockquote": "blockquote",
}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4"}
SAFE_URL = re.compile(r"^(https?://|tg://|mailto:)", re.I)


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[tuple[str, str | None]] = []  # (source tag, emitted telegram tag)

    def _newline(self):
        if self.out and not self.out[-1].endswith("\n"):
            self.out.append("\n")

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        mapped = None
        if tag == "br":
            self.out.append("\n")
            return
        if tag in ("img", "hr", "input", "meta", "link", "wbr"):
            return
        if tag in BLOCK:
            self._newline()
            if tag == "li":
                self.out.append("• ")
            if tag.startswith("h"):
                mapped = "b"
        elif tag in INLINE:
            mapped = INLINE[tag]
        elif tag == "span" and "tg-spoiler" in (attrs.get("class") or ""):
            mapped = "tg-spoiler"
        elif tag == "a" and SAFE_URL.match(attrs.get("href") or ""):
            self.out.append(f'<a href="{html.escape(attrs["href"], quote=True)}">')
            self.stack.append((tag, "a"))
            return
        if mapped:
            self.out.append(f"<{mapped}>")
        self.stack.append((tag, mapped))

    def handle_endtag(self, tag):
        if tag == "br" or not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            src, mapped = self.stack.pop()
            if mapped:
                self.out.append(f"</{mapped}>")
            if src == tag:
                if tag in BLOCK or tag in ("blockquote", "pre"):
                    self._newline()
                break

    def handle_data(self, data):
        self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            _, mapped = self.stack.pop()
            if mapped:
                self.out.append(f"</{mapped}>")
        text = "".join(self.out)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def sanitize(editor_html: str) -> str:
    p = _Sanitizer()
    p.feed(editor_html or "")
    p.close()
    return p.result()


def markdown_to_tg(md: str) -> str:
    """Minimal Markdown → Telegram HTML for AI answers (**bold**, *italic*, `code`, lists, links)."""
    text = html.escape(md, quote=False)
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", lambda m: f"<pre>{m.group(1).strip()}</pre>", text, flags=re.S)
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)
    return text
