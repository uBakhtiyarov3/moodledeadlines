"""The whole Telegram Bot API for the admin agent, described from aiogram's own method models.

aiogram ships a typed model for every Bot API method (with Telegram's docs), so the agent can call
any method by its API name with JSON params, and look up exact parameters before it does.
"""

import inspect
import json
import re
import types
import typing
from functools import cache

import aiogram.methods as methods
from aiogram import Bot
from aiogram.methods.base import TelegramMethod
from pydantic import BaseModel, ValidationError

# Would break the running bot (it receives updates by long polling) or log it out.
FORBIDDEN = {"logOut", "close", "setWebhook", "deleteWebhook", "getUpdates"}
MAX_RESULT = 12000


@cache
def _methods() -> dict[str, type[TelegramMethod]]:
    found = {}
    for _, cls in inspect.getmembers(methods, inspect.isclass):
        if issubclass(cls, TelegramMethod) and cls is not TelegramMethod and getattr(cls, "__api_method__", None):
            found[cls.__api_method__] = cls
    return found


def names() -> list[str]:
    return sorted(n for n in _methods() if n not in FORBIDDEN)


def _type_name(tp) -> str:
    origin = typing.get_origin(tp)
    if origin is typing.Annotated:
        return _type_name(typing.get_args(tp)[0])
    if origin in (typing.Union, types.UnionType):
        return " | ".join(_type_name(a) for a in typing.get_args(tp) if a is not type(None))
    if origin in (list, typing.List):  # noqa: UP006
        args = typing.get_args(tp)
        return f"list[{_type_name(args[0]) if args else 'any'}]"
    if origin is typing.Literal:
        return " | ".join(repr(a) for a in typing.get_args(tp))
    return getattr(tp, "__name__", str(tp)).replace("Default", "default")


def _models_in(tp) -> list[type[BaseModel]]:
    out = []
    for a in typing.get_args(tp) or (tp,):
        if typing.get_args(a):
            out += _models_in(a)
        elif inspect.isclass(a) and issubclass(a, BaseModel) and not issubclass(a, TelegramMethod):
            out.append(a)
    return out


def _doc(cls) -> str:
    text = (cls.__doc__ or "").split("Source:")[0]
    return re.sub(r":class:`[\w.]*?(\w+)`", r"\1", " ".join(text.split()))


def _fields(model: type[BaseModel]) -> list[str]:
    return [f"{k}: {_type_name(f.annotation)}{'' if f.is_required() else ' (optional)'}"
            for k, f in model.model_fields.items()]


def reference(query: str) -> dict:
    """Exact signature of a method (and of the object types it takes), or methods matching a word."""
    by_lower = {n.lower(): n for n in _methods()}
    name = by_lower.get(query.strip().lower())
    if name:
        cls = _methods()[name]
        nested = {}
        for f in cls.model_fields.values():
            for m in _models_in(f.annotation):
                if m.__name__ not in nested and len(nested) < 8:
                    nested[m.__name__] = {"doc": _doc(m)[:300], "fields": _fields(m)}
        return {"method": name, "doc": _doc(cls)[:900], "params": _fields(cls), "types": nested,
                "forbidden": name in FORBIDDEN}
    q = query.lower()
    hits = [n for n in names() if q in n.lower()]
    hits += [n for n in names() if n not in hits and q in _doc(_methods()[n]).lower()]
    return {"matches": [{"method": n, "doc": _doc(_methods()[n])[:160]} for n in hits[:25]]}


def _jsonable(result):
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json", exclude_none=True)
    if isinstance(result, list):
        return [_jsonable(r) for r in result]
    return result


async def call(bot: Bot, method: str, params: dict) -> dict:
    by_lower = {n.lower(): n for n in _methods()}
    name = by_lower.get((method or "").strip().lower())
    if not name:
        return {"error": f"unknown method {method}; use telegram_api_reference"}
    if name in FORBIDDEN:
        return {"error": f"{name} would stop the bot, so it is not allowed"}
    try:
        request = _methods()[name].model_validate(params or {})
    except ValidationError as e:
        return {"error": "bad params: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:6])}
    try:
        result = await bot(request)
    except Exception as e:  # noqa: BLE001  (Telegram's own error text helps the agent fix the call)
        return {"error": f"{type(e).__name__}: {str(e)[:500]}"}
    text = json.dumps(_jsonable(result), ensure_ascii=False)
    return {"ok": True, "result": json.loads(text) if len(text) <= MAX_RESULT else text[:MAX_RESULT] + "…"}
