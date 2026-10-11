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


_INLINE_RULES = [
    (re.compile(r"\*\*([^\n*][^\n]*?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__([^\n_][^\n]*?)__"), r"<u>\1</u>"),
    (re.compile(r"~~([^\n~][^\n]*?)~~"), r"<s>\1</s>"),
    (re.compile(r"\|\|([^\n|][^\n]*?)\|\|"), r"<tg-spoiler>\1</tg-spoiler>"),
    (re.compile(r"(?<![\w*])\*(?![\s*])([^\n*]+?)(?<!\s)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"(?<![\w_])_(?![\s_])([^\n_]+?)(?<!\s)_(?![\w_])"), r"<i>\1</i>"),
    (re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def _inline(line: str) -> str:
    for rx, repl in _INLINE_RULES:
        line = rx.sub(repl, line)
    return line


def markdown_to_tg(md: str) -> str:
    """Markdown (as written by the AI) → Telegram HTML.

    Supports **bold**, *italic*/_italic_, __underline__, ~~strike~~, ||spoiler||, `code`,
    ```pre```, [links](https://…), "- " / nested bullets, "> " quotes (long ones expandable),
    and degrades #-headings, tables and rules into readable text.
    """
    # 1. pull code out so nothing inside it gets formatted
    stash: list[str] = []

    def keep(html_snippet: str) -> str:
        stash.append(html_snippet)
        return f"\x00{len(stash) - 1}\x00"

    text = re.sub(
        r"```[\w+-]*\n?(.*?)```",
        lambda m: keep(f"<pre>{html.escape(m.group(1).strip(), quote=False)}</pre>"),
        md,
        flags=re.S,
    )
    text = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    text = html.escape(text, quote=False)

    out: list[str] = []
    quote: list[str] = []

    def flush_quote():
        if quote:
            tag = "blockquote expandable" if len(quote) > 4 else "blockquote"
            out.append(f"<{tag}>" + "\n".join(quote) + "</blockquote>")
            quote.clear()

    for raw in text.split("\n"):
        line = raw.rstrip()
        m = re.match(r"^\s*&gt;\s?(.*)$", line)
        if m:
            quote.append(_inline(m.group(1)))
            continue
        flush_quote()
        if re.match(r"^\s*([-*_])\s*(\1\s*){2,}$", line):  # horizontal rule
            continue
        if re.match(r"^\s*\|?\s*:?-{2,}", line) and set(line.strip()) <= set("|-: "):  # table separator
            continue
        h = re.match(r"^#{1,6}\s+(.+)$", line)
        if h:
            line = "<b>" + _inline(h.group(1)).replace("<b>", "").replace("</b>", "") + "</b>"
            out.append(line)
            continue
        if line.strip().startswith("|") and line.strip().endswith("|"):  # table row
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = " · ".join(c for c in cells if c)
        b = re.match(r"^(\s*)[-*+•]\s+(.*)$", line)
        if b:
            nested = len(b.group(1).replace("\t", "    ")) >= 2
            line = ("    ◦ " if nested else "• ") + b.group(2)
        out.append(_inline(line))
    flush_quote()

    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], result)
