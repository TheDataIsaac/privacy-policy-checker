"""Write every step of a run to a JSON Lines file, so a wrong answer can be traced back.

One line per event: the run starting, each model call, each tool call, and the run ending. Read
a trace with `policy trace <file>`.
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

PREVIEW_CHARS = 300  # tool outputs can be long; the trace keeps the start of each one


class Tracer:
    def __init__(self, folder: Path, website: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        name = re.sub(r"[^a-z0-9]+", "-", website.lower()).strip("-")[:40]
        self.path = folder / f"{stamp}-{name}.jsonl"

    def log(self, event: str, **fields) -> None:
        line = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line, ensure_ascii=False) + "\n")


def ms_since(start: float) -> int:
    """Milliseconds since `start`, a value from time.perf_counter()."""
    return round((time.perf_counter() - start) * 1000)


def show(path: Path) -> str:
    """A trace file as a readable timeline."""
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        e = json.loads(raw)
        if e["event"] == "run_start":
            lines.append(f"Run: {e['website']}  (model {e['model']})")
        elif e["event"] == "model_call":
            calls = ", ".join(e["tool_calls"]) or "no tool call"
            lines.append(
                f"step {e['step']:>2}  model  {e['ms']:>6} ms  "
                f"{e['input_tokens']:>6} in / {e['output_tokens']:>5} out  -> {calls}"
            )
        elif e["event"] == "tool_call":
            status = f"ERROR {e['error']}" if e.get("error") else e["output"][:90]
            lines.append(f"         tool   {e['ms']:>6} ms  {e['name']}({e['args']})  {status}")
        elif e["event"] == "run_end":
            lines.append(
                f"End: {e['stopped']} after {e['steps']} steps, "
                f"{e['input_tokens']} input and {e['output_tokens']} output tokens"
            )
    return "\n".join(lines)
