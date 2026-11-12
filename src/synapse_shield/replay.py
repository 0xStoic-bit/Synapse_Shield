"""Replay your own recorded telemetry through the detection engine, offline.

Answers "how many of these real sessions would Synapse Shield have blocked?" without a server, a token or
any network access. Use it on recordings of real users (expect ~0% blocked) or of your own bots (expect
~100%), and look at *which rules* and *which cohorts* the blocks come from before you enable enforcement.

Accepted inputs (a file or a directory of files):
  * ``.json``  : one telemetry object, or a list of them
  * ``.jsonl`` : one telemetry object per line
  * each object may be the telemetry itself (``mouse_movements``, ``keystrokes``, ``clicks``, ``scrolls``,
    ``browser``) or an envelope with a ``telemetry`` key (the token payload the SDK sends)
"""

from __future__ import annotations

import collections
import json
import os
from collections.abc import Iterable, Iterator
from typing import Any

from .cohort import cohort_of
from .engine import analyze_behavior
from .rules import rule_codes

TELEMETRY_KEYS = ("mouse_movements", "keystrokes", "clicks", "scrolls", "browser")
DEFAULT_THRESHOLD = 50.0  # same default as max_risk_score in the server pipeline


def _as_telemetry(obj: Any) -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    inner = obj.get("telemetry")
    if isinstance(inner, dict):
        obj = inner
    if any(k in obj for k in TELEMETRY_KEYS):
        return obj
    return None


def _from_json_text(text: str, jsonl: bool) -> Iterator[dict[str, Any]]:
    docs: list[Any] = []
    if jsonl:
        for line in text.splitlines():
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    else:
        loaded = json.loads(text)
        docs = loaded if isinstance(loaded, list) else [loaded]
    for d in docs:
        t = _as_telemetry(d)
        if t is not None:
            yield t


def load_telemetry(path: str) -> list[dict[str, Any]]:
    """Load every telemetry object under ``path`` (file or directory, non-recursive into hidden dirs)."""
    files: list[str] = []
    if os.path.isdir(path):
        for root, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            files += [os.path.join(root, n) for n in sorted(names) if n.lower().endswith((".json", ".jsonl"))]
    else:
        files = [path]
    out: list[dict[str, Any]] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            out.extend(_from_json_text(fh.read(), f.lower().endswith(".jsonl")))
    return out


def replay(items: Iterable[dict[str, Any]], threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    """Run each telemetry through ``analyze_behavior`` and summarise. Stateless: no storage is touched."""
    total = blocked = 0
    rules: collections.Counter[str] = collections.Counter()
    cohorts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])  # label -> [sessions, blocked]
    scores: list[float] = []
    for tel in items:
        score, classification, reasons, details = analyze_behavior(tel)
        is_block = score >= threshold or classification == "Bot"
        feats = details.get("features", {}) if isinstance(details, dict) else {}
        c = cohort_of(feats)
        label = f"{c['input']}/{c['dpr']}"
        total += 1
        scores.append(float(score))
        cohorts[label][0] += 1
        if is_block:
            blocked += 1
            cohorts[label][1] += 1
            rules.update(rule_codes(reasons))
    scores.sort()
    median = scores[len(scores) // 2] if scores else 0.0
    return {
        "sessions": total,
        "blocked": blocked,
        "block_rate": (blocked / total) if total else 0.0,
        "median_score": median,
        "threshold": threshold,
        "rules": dict(rules.most_common()),
        "cohorts": {k: {"sessions": v[0], "blocked": v[1], "block_rate": v[1] / v[0]} for k, v in sorted(cohorts.items())},
    }


def format_report(result: dict[str, Any], label: str | None = None) -> str:
    n, b = result["sessions"], result["blocked"]
    lines = [f"Replayed {n} session(s); {b} would be blocked ({100 * result['block_rate']:.1f}%)."]
    if label == "human":
        lines.append(f"  Labelled human: false-positive rate = {100 * result['block_rate']:.1f}%")
    elif label == "bot":
        lines.append(f"  Labelled bot: detection rate (TPR) = {100 * result['block_rate']:.1f}%")
    if result["rules"]:
        lines.append("Rules behind the blocks (a session can trigger several):")
        lines += [f"  {count:5d}  {code}" for code, count in result["rules"].items()]
    if len(result["cohorts"]) > 1 or any(v["blocked"] for v in result["cohorts"].values()):
        lines.append("By cohort (input/dpr): sessions, blocked, rate")
        for k, v in result["cohorts"].items():
            lines.append(f"  {k:18s} {v['sessions']:5d} {v['blocked']:5d}  {100 * v['block_rate']:.1f}%")
    if n == 0:
        lines.append("No telemetry objects found (expected mouse_movements/keystrokes/clicks/scrolls/browser).")
    return "\n".join(lines)
