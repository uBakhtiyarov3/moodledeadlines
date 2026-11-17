"""Read-only SQL for the admin agent: one SELECT/WITH statement in a read-only transaction."""

import re
from datetime import datetime

from sqlalchemy import text

from app.db import Session, engine

MAX_ROWS = 200
WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum|reindex|pragma|grant|truncate)\b", re.I)


async def run(sql: str) -> dict:
    sql = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql) or ";" in sql or WRITE.search(re.sub(r"'[^']*'", "''", sql)):
        return {"error": "only a single read-only SELECT/WITH statement is allowed"}
    sqlite = engine.dialect.name == "sqlite"
    async with Session() as s:
        try:
            await s.execute(text("PRAGMA query_only = ON" if sqlite else "SET TRANSACTION READ ONLY"))
            res = await s.execute(text(sql))
            cols = list(res.keys())
            rows = res.fetchmany(MAX_ROWS + 1)
        except Exception as e:  # noqa: BLE001  (show the database's message so the agent can fix its SQL)
            return {"error": str(getattr(e, "orig", e))[:400]}
        finally:
            if sqlite:
                await s.execute(text("PRAGMA query_only = OFF"))
            await s.rollback()

    def cell(v):
        return v.isoformat() if isinstance(v, datetime) else v if isinstance(v, (int, float, str, type(None))) else str(v)

    return {"columns": cols, "rows": [[cell(v) for v in r] for r in rows[:MAX_ROWS]], "truncated": len(rows) > MAX_ROWS}
