"""Session timeline and replay verification (ADR-0007).

    make timeline FILE=recordings/<session>.recording.jsonl [ARGS="--verify"]
    make timeline                    # the most recent annotated session

Merges a recording (what you did) with its annotations sidecar (what you thought) into a readable
markdown timeline, grouped by level. `--verify` replays the recorded actions against the same game
locally and compares every step with what was recorded, which is what justifies lean recordings
(ADR-0005: games are deterministic). The CLI never rewrites the annotations file: fix a transcript or
drop a line by editing the sidecar by hand (see docs/ANNOTATION-WORKFLOW.md).

Read-tolerant by design: truncated final lines, unknown event kinds, a missing sidecar and v1/v2/v3
recordings all load; recordings are the one thing you can't regenerate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .recorder import frame_hash, recordings_dir_from_env

GLYPHS = {0: "RESET", 1: "↑", 2: "↓", 3: "←", 4: "→", 5: "ACT", 7: "UNDO"}
VERDICT_LABEL = {"confirmed": "TRUE", "refuted": "FALSE", "open": "open"}
MAX_RUN_GLYPHS = 40


# --- loading -----------------------------------------------------------------------------------


def load_jsonl(path: Path) -> tuple[list[dict], int]:
    """Parse a JSONL file, skipping lines that don't parse (a crash can truncate the last one)."""
    rows, skipped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(row, dict):
            rows.append(row)
        else:
            skipped += 1
    return rows, skipped


def sidecar_path(recording: Path) -> Path:
    return recording.with_name(recording.name.removesuffix(".recording.jsonl") + ".annotations.jsonl")


def latest_recording(directory: Path) -> Path | None:
    """The newest recording, preferring sessions that have annotations (those are the interesting ones)."""
    recordings = sorted(directory.glob("*.recording.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    annotated = [p for p in recordings if sidecar_path(p).exists()]
    return (annotated or recordings or [None])[0]


# --- rendering ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Item:
    key: tuple
    kind: str  # "step" | "event"
    data: dict


def _glyph(row: dict) -> str:
    action = row.get("action_id")
    if action == 6:
        data = row.get("action_input") or {}
        return f"click({data.get('x', '?')},{data.get('y', '?')})"
    return GLYPHS.get(action, f"A{action}")


def _fmt_steps(event: dict) -> str:
    start, end = event.get("step_at_start"), event.get("step_at_end")
    if start is None or start == end:
        return f"step {end}"
    return f"steps {start}→{end}"


def _event_line(e: dict) -> str:
    kind = e.get("kind")
    tag = f"[{e['hypothesis_id']}] " if e.get("hypothesis_id") and kind in ("speech", "text") else ""
    if kind in ("speech", "text"):
        label = "said" if kind == "speech" else "note"
        phase = e.get("phase") or "?"
        end_phase = e.get("phase_at_end")
        phases = phase if not end_phase or end_phase == phase else f"{phase}→{end_phase}"
        return f"- **{label}** ({phases}, {_fmt_steps(e)}): {tag}{e.get('text', '')}"
    if kind == "phase_change":
        return f"- phase: {e.get('previous') or 'start'} → **{e.get('phase')}** ({e.get('reason')})"
    if kind == "hypothesis":
        return f"- **{e.get('hypothesis_id')} proposed**: {e.get('statement', '')}"
    if kind == "hypothesis_verdict":
        label = VERDICT_LABEL.get(e.get("verdict"), e.get("verdict"))
        return f"- **{e.get('hypothesis_id')} → {label}** (was {e.get('previous')})"
    if kind == "dictate":
        return f"- dictate {'on' if e.get('on') else 'off'}"
    if kind == "mute":
        return f"- mic {'muted' if e.get('muted') else 'unmuted'}"
    detail = {k: v for k, v in e.items() if k not in ("schema_version", "event_id", "t")}
    return f"- [{kind}] {json.dumps(detail)}"


def _run_line(run: list[dict]) -> str:
    first, last = run[0]["step_index"], run[-1]["step_index"]
    span = f"step {first}" if first == last else f"steps {first}–{last}"
    glyphs = [_glyph(r) for r in run]
    shown = " ".join(glyphs[:MAX_RUN_GLYPHS]) + (
        f" … (+{len(glyphs) - MAX_RUN_GLYPHS})" if len(glyphs) > MAX_RUN_GLYPHS else ""
    )
    ends = run[-1].get("state")
    state = f" → **{ends}**" if ends and ends != "NOT_FINISHED" else ""
    return f"- `{span}`: {shown}{state}"


def _hypothesis_summary(events: list[dict]) -> list[str]:
    table: dict[str, dict] = {}
    for e in events:
        if e.get("kind") == "hypothesis":
            table[e["hypothesis_id"]] = {
                "text": e.get("statement", ""),
                "status": "open",
                "stated": e.get("step_at_end"),
                "decided": None,
            }
        elif e.get("kind") == "hypothesis_verdict" and e.get("hypothesis_id") in table:
            row = table[e["hypothesis_id"]]
            row["status"] = e.get("verdict")
            row["decided"] = e.get("step_at_end") if e.get("verdict") != "open" else None
    if not table:
        return []
    lines = [
        "## Hypotheses",
        "",
        "| id | verdict | stated at step | decided at step | hypothesis |",
        "|---|---|---|---|---|",
    ]
    for hid, r in table.items():
        text = r["text"].replace("|", "\\|")
        verdict = VERDICT_LABEL.get(r["status"], r["status"])
        decided = r["decided"] if r["decided"] is not None else ""
        lines.append(f"| {hid} | {verdict} | {r['stated']} | {decided} | {text} |")
    return lines + [""]


def render_timeline(steps: list[dict], events: list[dict], title: str = "session", skipped: int = 0) -> str:
    """Markdown for one session. Thoughts are placed *after* the step they reacted to
    (`step_at_end`) and before the next action, so a sentence spoken over steps 12-14 reads as a
    reaction to step 14 that precedes step 15."""
    ignored = sum(1 for e in events if e.get("ignore"))
    events = [e for e in events if not e.get("ignore")]
    start = next((e for e in events if e.get("kind") == "session_start"), None)

    items = [Item((s.get("step_index", 0), 0, s.get("timestamp", "")), "step", s) for s in steps]
    for e in events:
        if e.get("kind") == "session_start":
            continue
        at = e.get("step_at_end")
        items.append(Item((at if isinstance(at, int) else -1, 1, e.get("t", "")), "event", e))
    items.sort(key=lambda i: i.key)

    out = [f"# Timeline: {title}", ""]
    meta = []
    if steps:
        meta.append(f"{len(steps)} steps")
        meta.append(f"furthest level {max(s.get('levels_completed', 0) for s in steps) + 1}")
    if start:
        meta += [
            f"game `{start.get('game_id')}`",
            f"data use: **{start.get('data_use')}**",
            f"stt: {start.get('stt')}",
        ]
    spoken = sum(1 for e in events if e.get("kind") == "speech")
    typed = sum(1 for e in events if e.get("kind") == "text")
    if events:
        meta.append(f"{spoken} spoken, {typed} typed")
    out += [" · ".join(meta), ""] if meta else []
    if not events:
        out += ["_No annotations file for this recording: showing moves only._", ""]
    if ignored:
        out += [f"_{ignored} annotation event(s) marked `ignore` are hidden._", ""]
    if skipped:
        out += [f"_{skipped} unreadable line(s) skipped (truncated file?)._", ""]
    out += _hypothesis_summary(events)

    run: list[dict] = []
    prev_levels: int | None = None

    def flush() -> None:
        if run:
            out.append(_run_line(run))
            run.clear()

    for item in items:
        if item.kind == "step":
            row = item.data
            levels = row.get("levels_completed", 0)
            reset = row.get("action_id") == 0 and row.get("step_index", 0) > 0
            cleared = prev_levels is not None and levels > prev_levels and not reset
            if cleared:
                run.append(row)  # the clearing step belongs to the level it cleared
                flush()
                out += ["", f"## Level {levels + 1} \u2014 level {prev_levels + 1} cleared", ""]
                prev_levels = levels
                continue
            if prev_levels is None or levels != prev_levels or reset:
                flush()
                out += ["", f"## Level {levels + 1}{' (after reset)' if reset else ''}", ""]
                prev_levels = levels
            run.append(row)
        else:
            flush()
            out.append(_event_line(item.data))
    flush()
    return "\n".join(out).rstrip() + "\n"


def timeline_for(recording: Path) -> str:
    steps, skipped = load_jsonl(recording)
    sidecar = sidecar_path(recording)
    events: list[dict] = []
    if sidecar.exists():
        events, more = load_jsonl(sidecar)
        skipped += more
    return render_timeline(
        steps, events, title=recording.name.removesuffix(".recording.jsonl"), skipped=skipped
    )


# --- replay verification ------------------------------------------------------------------------


@dataclass
class Divergence:
    step_index: int
    what: str
    recorded: object
    replayed: object


@dataclass
class VerifyResult:
    checked: int
    hashed: int  # steps compared by frame hash (the rest by state and level only)
    divergence: Divergence | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.divergence is None


def _recorded_hash(row: dict) -> str | None:
    if row.get("frame_sha256"):
        return row["frame_sha256"]
    if row.get("frame"):  # a full-mode recording from before v3 still carries the grid
        return frame_hash(row["frame"])
    return None


async def verify_replay(steps: list[dict], arcade) -> VerifyResult:
    """Replay every recorded action locally; report the first step that differs from the recording."""
    from .game_sources.arcade import ArcadeGameSource

    if not steps:
        return VerifyResult(0, 0, note="empty recording")
    source = ArcadeGameSource(arcade, steps[0]["game_id"])
    hashed = 0
    for row in steps:
        action = row["action_id"]
        data = row.get("action_input") or {}
        if row["step_index"] == 0 or action == 0:
            frame = await source.reset()
        else:
            frame = await source.step(action, x=data.get("x"), y=data.get("y"))
        checks = [
            ("state", row.get("state"), str(frame.state)),
            ("levels_completed", row.get("levels_completed"), frame.levels_completed),
        ]
        recorded = _recorded_hash(row)
        if recorded is not None:
            hashed += 1
            checks.append(("frame_sha256", recorded, frame_hash(frame.frame)))
        for what, was, now in checks:
            if was != now:
                return VerifyResult(
                    row["step_index"] + 1, hashed, Divergence(row["step_index"], what, was, now)
                )
    note = (
        ""
        if hashed
        else "no frame hashes in this recording (schema < 3, lean): compared state and levels only"
    )
    return VerifyResult(len(steps), hashed, note=note)


def _offline_arcade(environments_dir: str):
    from arc_agi import Arcade, OperationMode

    return Arcade(operation_mode=OperationMode.OFFLINE, environments_dir=environments_dir)


# --- CLI ----------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a session as a timeline; optionally verify a replay."
    )
    parser.add_argument("file", nargs="?", help="a *.recording.jsonl (default: the latest annotated session)")
    parser.add_argument(
        "--verify", action="store_true", help="replay the actions locally and compare every step"
    )
    parser.add_argument("--env-dir", default=os.environ.get("ARC_ENVIRONMENTS_DIR", "environment_files"))
    parser.add_argument("--out", help="write the markdown here instead of stdout")
    args = parser.parse_args(argv)

    recording = Path(args.file) if args.file else latest_recording(recordings_dir_from_env())
    if recording is None or not recording.exists():
        print("no recording found (pass a path, or record a session first)", file=sys.stderr)
        return 2

    markdown = timeline_for(recording)
    if args.out:
        Path(args.out).write_text(markdown, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(markdown)

    if not args.verify:
        return 0
    steps, _ = load_jsonl(recording)
    try:
        result = asyncio.run(verify_replay(steps, _offline_arcade(args.env_dir)))
    except Exception as exc:  # game source missing, engine error, ...
        print(f"VERIFY ERROR: could not replay ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2
    when = datetime.now().strftime("%H:%M:%S")
    if result.ok:
        print(
            f"VERIFY OK [{when}]: {result.checked} steps replayed, {result.hashed} matched by frame hash."
            + (f" Note: {result.note}." if result.note else ""),
            file=sys.stderr,
        )
        return 0
    d = result.divergence
    print(
        f"VERIFY FAILED at step {d.step_index} ({d.what}): recorded {d.recorded!r}, replayed {d.replayed!r}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
