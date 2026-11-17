"""Fetch a public URL for the agent — never the server's own network (no private, loopback or metadata IPs)."""

import asyncio
import html
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.services import files

MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT = 40_000


class Blocked(ValueError):
    pass


async def _check(url: str) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise Blocked("only public http(s) URLs")
    infos = await asyncio.get_running_loop().getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                                          type=socket.SOCK_STREAM)
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:  # private, loopback, link-local (cloud metadata), reserved…
            raise Blocked("that address is not public")


def html_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<(br|/p|/div|/li|/h\d|/tr|/section|/article)[^>]*>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


async def fetch(url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False,
                                     headers={"User-Agent": "UWED-Pulse-bot/1.0"}) as c:
            for _ in range(5):  # follow redirects ourselves so every hop is checked
                await _check(url)
                async with c.stream("GET", url) as r:
                    if r.is_redirect and r.headers.get("location"):
                        url = urljoin(url, r.headers["location"])
                        continue
                    chunks, size = [], 0
                    async for chunk in r.aiter_bytes():
                        size += len(chunk)
                        if size > MAX_BYTES:
                            return {"error": "file too large (8 MB max)"}
                        chunks.append(chunk)
                    data, ctype = b"".join(chunks), r.headers.get("content-type", "").split(";")[0].strip().lower()
                    status = r.status_code
                break
            else:
                return {"error": "too many redirects"}
    except Blocked as e:
        return {"error": str(e)}
    except (httpx.HTTPError, OSError) as e:
        return {"error": f"could not fetch: {type(e).__name__}"}
    name = urlparse(url).path.rsplit("/", 1)[-1] or "page"
    if "html" in ctype or (not ctype and data.lstrip()[:1] == b"<"):
        text = html_text(files.decode(data))
        title = re.search(r"(?is)<title[^>]*>(.*?)</title>", files.decode(data[:200_000]))
    else:
        text = files.as_text(name, ctype, data) or ""
        title = None
    if not text:
        return {"url": url, "status": status, "content_type": ctype, "error": "no readable text (image, video or binary)"}
    return {"url": url, "status": status, "title": html.unescape(title.group(1).strip()) if title else None,
            "text": text[:MAX_TEXT] + ("…" if len(text) > MAX_TEXT else "")}
