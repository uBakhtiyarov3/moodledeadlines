"""Shell commands for the admin agent, inside the bot's container (as the bot's own, unprivileged user)."""

import asyncio
import os
import signal

MAX_OUT = 20_000
# keys stay out of the command's environment, so no output or script can print them by accident
SECRET_ENV = ("BOT_TOKEN", "SECRET_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "AWS_SECRET_ACCESS_KEY",
              "AWS_SESSION_TOKEN", "DATABASE_URL")


async def run(command: str, timeout: int = 60) -> dict:
    timeout = max(1, min(int(timeout), 300))
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    proc = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env,
        cwd=os.getcwd(), start_new_session=True)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        code = proc.returncode
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, code = (await proc.stdout.read()) if proc.stdout else b"", "timeout"
    text = out.decode(errors="replace")
    if len(text) > MAX_OUT:
        text = text[:MAX_OUT // 2] + "\n…[cut]…\n" + text[-MAX_OUT // 2:]
    return {"exit_code": code, "output": text}
