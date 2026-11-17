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


BACKUPS_KEPT = 15


def _backup() -> str | None:
    """Copy the SQLite file before a write (keeps the newest few)."""
    import shutil
    from pathlib import Path

    if engine.dialect.name != "sqlite":
        return None
    db = Path(engine.url.database or "")
    if not db.is_file():
        return None
    folder = db.parent / "backups"
    folder.mkdir(exist_ok=True)
    target = folder / f"{db.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    shutil.copy2(db, target)
    for old in sorted(folder.glob(f"{db.stem}-*.db"))[:-BACKUPS_KEPT]:
        old.unlink(missing_ok=True)
    return str(target)


async def write(sql: str) -> dict:
    """Any SQL, after a backup; all statements in one transaction."""
    statements = [x.strip() for x in re.split(r";\s*(?=(?:[^']*'[^']*')*[^']*$)", sql or "") if x.strip()]
    if not statements:
        return {"error": "empty SQL"}
    backup = _backup()
    async with Session() as s:
        try:
            counts = [(await s.execute(text(st))).rowcount for st in statements]
            await s.commit()
        except Exception as e:  # noqa: BLE001
            await s.rollback()
            return {"error": str(getattr(e, "orig", e))[:400], "backup": backup, "note": "nothing was changed"}
    from app.services import settings as rt

    await rt.load()  # in case the settings table changed
    return {"ok": True, "rows_affected": counts, "backup": backup}
