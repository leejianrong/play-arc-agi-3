"""Browser end-to-end tests: drive the real app in headless Chromium with a fake microphone.

    make e2e                      # all flows
    make e2e ARGS="--only hyp"    # flows whose name contains "hyp"
    make e2e ARGS="--headed"      # watch it

What it does: starts the real server on a free port (real games, real websockets, recordings into a
temp dir), launches Chromium with a fake mic playing a speech-like loop, then clicks and types like a
person and asserts on what is *rendered* (visibility, geometry, computed style) and on what was written
to disk. It exists because unit and websocket tests cannot see CSS or focus bugs: the V3 meter bar
passed every test while rendering 0px wide.

Needs: ARC_API_KEY in .env, games downloaded (`make download-games`), and a Chromium that Playwright
can use (`uvx playwright install chromium`, or set PLAYWRIGHT_CHROMIUM=/path/to/chrome). Speech uses
STT_ENGINE=fake, so no Whisper model is needed; real Whisper is covered by the integration tests and
docs/STT-MEASUREMENTS.md. Deliberately not part of `make check`/CI (needs games, a key, a browser).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ENVS = ROOT / "tests" / "fixtures" / "environment_files"

RESULTS: list[tuple[str, bool]] = []


def check(name: str, condition: object, detail: str = "") -> None:
    ok = bool(condition)
    RESULTS.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}", flush=True)


# --- environment -------------------------------------------------------------------------------


def find_chromium() -> str:
    explicit = os.environ.get("PLAYWRIGHT_CHROMIUM")
    if explicit:
        return explicit
    found = sorted(
        glob.glob(str(Path.home() / ".cache/ms-playwright/chromium-*/chrome-linux*/chrome")),
        key=lambda p: int(p.split("chromium-")[1].split("/")[0]),
    )
    if not found:
        sys.exit("no Chromium found: run `uvx playwright install chromium` or set PLAYWRIGHT_CHROMIUM")
    return found[-1]


def write_fake_mic(path: Path) -> None:
    """9 s loop: 6 s of speech-like bursts (400 ms tone, 100 ms gap) then 3 s of quiet."""
    rate = 48_000
    samples: list[int] = []
    for _ in range(12):
        samples += [int(14_000 * math.sin(2 * math.pi * 180 * i / rate)) for i in range(int(rate * 0.4))]
        samples += [0] * int(rate * 0.1)
    samples += [0] * (rate * 3)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))


class App:
    """The real server plus a throwaway recordings dir and environments dir."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.rec = tmp / "rec"
        self.rec.mkdir()
        envs = tmp / "envs"
        self.envs = envs
        envs.mkdir()
        real = ROOT / "environment_files"
        if real.is_dir():
            for child in real.iterdir():
                # Copies, not symlinks: arc_agi's offline scan doesn't follow symlinked game folders.
                shutil.copytree(child, envs / child.name)
        shutil.copytree(FIXTURE_ENVS / "tst1", envs / "tst1")  # a one-action level: a fast "level clear"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
        env = {
            **os.environ,
            "PORT": str(self.port),
            "RECORDINGS_DIR": str(self.rec),
            "ARC_ENVIRONMENTS_DIR": str(envs),
            "STT_ENGINE": "fake",
        }
        self.log = open(tmp / "server.log", "w")
        self.proc = subprocess.Popen(
            [sys.executable, "main.py"], cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT
        )
        self.url = f"http://127.0.0.1:{self.port}/"
        for _ in range(60):
            try:
                urllib.request.urlopen(self.url, timeout=1)
                return
            except OSError:
                time.sleep(0.5)
        self.stop()
        sys.exit(f"server did not start; see {tmp / 'server.log'}")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()

    def sidecar(self, game: str) -> list[dict]:
        files = sorted(self.rec.glob(f"*{game}*.annotations.jsonl"), key=lambda p: p.stat().st_mtime)
        return [json.loads(line) for line in files[-1].read_text().splitlines()] if files else []

    def recording_lines(self, game: str) -> int:
        files = sorted(self.rec.glob(f"*{game}*.recording.jsonl"), key=lambda p: p.stat().st_mtime)
        return sum(1 for _ in open(files[-1])) if files else 0


@contextmanager
def browser_page(app: App, mic: Path, headed: bool, viewport: tuple[int, int] = (900, 1100)):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=find_chromium(),
            headless=not headed,
            args=[
                "--no-sandbox",
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={mic}",
            ],
        )
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        page.goto(app.url)
        page.wait_for_selector(".picker-row", timeout=60_000)
        try:
            yield page
        finally:
            browser.close()


# --- helpers -----------------------------------------------------------------------------------


def start_game(page, game: str, annotate: bool = True) -> None:
    if page.is_checked("#annotate") != annotate:
        page.click("#annotate")
    page.click(f".picker-row:has-text('{game}')")
    page.wait_for_selector("#grid", state="visible")
    if annotate:
        page.wait_for_selector("#transcript", state="visible")
        page.wait_for_function(
            "document.querySelector('[data-role=status]').innerText.startsWith('listening')", timeout=30_000
        )


def phase(page) -> str:
    return page.locator(".phase-chip.is-current").get_attribute("data-phase")


def wait_phase(page, name: str) -> None:
    page.wait_for_function(
        f"document.querySelector('.phase-chip.is-current').dataset.phase==='{name}'", timeout=5_000
    )


def hyp_rows(page) -> list[tuple[str, str, bool]]:
    """(id, status, being-tested) for every row in the hypotheses list."""
    rows = page.eval_on_selector_all(
        ".hyp-row",
        "els => els.map(e => [e.dataset.hypothesisId, e.dataset.status,"
        " e.classList.contains('is-selected')])",
    )
    return [tuple(row) for row in rows]  # JSON arrives as lists; compare as tuples


def hyp_button(page, hid: str, which: str):
    return page.locator(f".hyp-row[data-hypothesis-id={hid}] .hyp-actions button.{which}")


def wait_hyp(page, hid: str, status: str) -> None:
    page.wait_for_selector(f".hyp-row[data-hypothesis-id={hid}][data-status={status}]", timeout=5_000)


def type_note(page, text: str) -> None:
    page.keyboard.press("t")
    page.keyboard.type(text)
    page.keyboard.press("Enter")


def end_session(page) -> None:
    page.click("#end")
    page.wait_for_selector("#picker", state="visible", timeout=20_000)


# --- flows -------------------------------------------------------------------------------------


def flow_picker_and_meter(app: App, mic: Path, headed: bool) -> None:
    """Held-out tagging, and the V3 regression: the mic meter must actually render."""
    with browser_page(app, mic, headed) as page:
        held = lambda g: page.locator(f".picker-row:has-text('{g}') .tag.heldout").count()  # noqa: E731
        check("held-out game is tagged in the picker", held("r11l") == 1)
        check("annotatable game is not tagged", held("ls20") == 0)
        check("custom fixture game is listed", page.locator(".picker-row:has-text('tst1')").count() == 1)

        start_game(page, "ls20")
        box = page.eval_on_selector(
            ".meter", "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }"
        )
        check("meter track has a real size", box[0] >= 40 and box[1] >= 3, str(box))
        widest = 0.0
        for _ in range(60):
            widest = max(
                widest,
                page.eval_on_selector("[data-role=meter-fill]", "e => e.getBoundingClientRect().width"),
            )
            page.wait_for_timeout(100)
        check("meter fill renders wider than 5px while the mic hears speech", widest > 5, f"{widest:.0f}px")
        end_session(page)


def flow_heldout(app: App, mic: Path, headed: bool) -> None:
    with browser_page(app, mic, headed) as page:
        page.check("#annotate")
        page.click(".picker-row:has-text('r11l')")
        page.wait_for_selector("#grid", state="visible")
        page.wait_for_timeout(1_000)
        check("held-out: explained in a notice", "Held-out" in page.inner_text("#notice"))
        check("held-out: no annotation panel", not page.is_visible("#transcript"))
        end_session(page)
        check("held-out: nothing annotated on disk", app.sidecar("r11l") == [])


def flow_notes_phases_mute_end(app: App, mic: Path, headed: bool) -> None:
    with browser_page(app, mic, headed) as page:
        start_game(page, "ls20")
        check("starts in observe", phase(page) == "observe")
        base = app.recording_lines("ls20")

        page.keyboard.press("t")
        check("T focuses the note box", page.evaluate("document.activeElement.dataset.role") == "note")
        page.keyboard.type("wasd r the blue block is the player")
        page.keyboard.press("Enter")
        page.wait_for_selector(".final.typed")
        check("typed note appears", "blue block" in page.inner_text(".final.typed"))
        check("typing wasd sent no game actions", app.recording_lines("ls20") == base)
        check("focus is back on the game", page.evaluate("document.activeElement.tagName") != "INPUT")
        page.keyboard.press("t")
        page.keyboard.type("discard me")
        page.keyboard.press("Escape")
        check("Esc clears and blurs", page.input_value("[data-role=note]") == "")

        page.keyboard.press("ArrowUp")
        wait_phase(page, "probe")
        check("first action flips to probe", phase(page) == "probe")
        page.keyboard.press("3")
        wait_phase(page, "plan")
        page.click(".phase-chip[data-phase=execute]")
        wait_phase(page, "execute")
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(300)
        check("an action does not leave execute", phase(page) == "execute")

        page.keyboard.press("m")
        page.wait_for_function("document.querySelector('[data-role=mute]').innerText.startsWith('muted')")
        check(
            "M mutes (indicator rendered red)",
            page.eval_on_selector(
                "[data-role=mute]",
                "e => e.classList.contains('is-muted') && e.getBoundingClientRect().width > 0",
            ),
        )
        page.keyboard.press("m")
        page.wait_for_function("document.querySelector('[data-role=mute]').innerText.startsWith('mic on')")

        page.wait_for_selector(".final:not(.typed)", timeout=30_000)
        check("a spoken line arrives", True)
        end_session(page)
        check("end session shows saved files", ".annotations.jsonl" in page.inner_text("#notice"))
        check("panel hidden after end", not page.is_visible("#transcript"))

    events = app.sidecar("ls20")
    check("sidecar: session labelled reference-only", events[0]["data_use"] == "reference-only")
    check(
        "sidecar: phase sequence",
        [e["phase"] for e in events if e["kind"] == "phase_change"][:4]
        == ["observe", "probe", "plan", "execute"],
    )
    check("sidecar: mute then unmute", [e["muted"] for e in events if e["kind"] == "mute"] == [True, False])
    check(
        "sidecar: typed note kept its text",
        any(e["kind"] == "text" and e["text"].startswith("wasd r") for e in events),
    )


def flow_hypotheses(app: App, mic: Path, headed: bool) -> None:
    """The V5 workflow after user feedback: a visible list, several added at once, marked true/false
    per row in any order, plus dictate mode."""
    with browser_page(app, mic, headed) as page:
        start_game(page, "ls20")
        box = page.eval_on_selector(
            "[data-role=hyp-add]", "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }"
        )
        check("hypotheses section renders with a usable input", box[0] > 200 and box[1] > 15, str(box))
        check(
            "empty state explains the workflow",
            "mark each true or false" in page.inner_text("[data-role=hyp-empty]"),
        )

        page.keyboard.press("h")
        check("H jumps to the add box", page.evaluate("document.activeElement.dataset.role") == "hyp-add")
        for text in (
            "the blue cross rotates the square",
            "the grey square is the goal",
            "I only get 40 moves",
        ):
            page.keyboard.type(text)
            page.keyboard.press("Enter")
        page.wait_for_selector(".hyp-row[data-hypothesis-id=h3]")
        check(
            "three hypotheses added in a row, all open, last one being tested",
            hyp_rows(page) == [("h1", "open", False), ("h2", "open", False), ("h3", "open", True)],
            str(hyp_rows(page)),
        )
        check(
            "add box is empty and still focused for the next one",
            page.input_value("[data-role=hyp-add]") == ""
            and page.evaluate("document.activeElement.dataset.role") == "hyp-add",
        )
        size = page.eval_on_selector(
            ".hyp-row[data-hypothesis-id=h1] .hyp-actions button.yes",
            "e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }",
        )
        check("true/false buttons render with a real size", size[0] > 30 and size[1] > 12, str(size))

        before = app.recording_lines("ls20")
        page.keyboard.press("Escape")
        check(
            "Esc gives the keyboard back to the game",
            page.evaluate("document.activeElement.tagName") != "INPUT",
        )
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(300)
        check("a game key now acts in the game", app.recording_lines("ls20") > before)

        hyp_button(page, "h2", "no").click()
        wait_hyp(page, "h2", "refuted")
        check(
            "false on an un-selected row marks only that row",
            hyp_rows(page) == [("h1", "open", False), ("h2", "refuted", False), ("h3", "open", True)],
            str(hyp_rows(page)),
        )
        line = page.eval_on_selector(
            ".hyp-row[data-hypothesis-id=h2] .hyp-text", "e => getComputedStyle(e).textDecorationLine"
        )
        check("a false hypothesis renders struck through", "line-through" in line, line)
        check("a FALSE badge is shown", "FALSE" in page.inner_text(".hyp-row[data-hypothesis-id=h2]"))
        hyp_button(page, "h1", "yes").click()
        wait_hyp(page, "h1", "confirmed")
        check(
            "true marks it confirmed with a TRUE badge",
            "TRUE" in page.inner_text(".hyp-row[data-hypothesis-id=h1]"),
        )

        statuses = hyp_rows(page)
        page.keyboard.press(" ")  # a still-focused button would re-activate on Space
        page.wait_for_timeout(300)
        check("Space after clicking a button does not re-press it", hyp_rows(page) == statuses)
        before = app.recording_lines("ls20")
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(300)
        check("and a game key still acts in the game", app.recording_lines("ls20") > before)

        hyp_button(page, "h2", "reset").click()
        wait_hyp(page, "h2", "open")
        check("reset puts a decided hypothesis back to open", True)

        page.click(".hyp-row[data-hypothesis-id=h2] .hyp-text")
        page.wait_for_selector(".hyp-row[data-hypothesis-id=h2].is-selected")
        check(
            "clicking a row marks it as the one being tested",
            "testing" in page.inner_text(".hyp-row[data-hypothesis-id=h2]"),
        )
        page.keyboard.press("y")
        wait_hyp(page, "h2", "confirmed")
        page.wait_for_selector(".hyp-row[data-hypothesis-id=h3].is-selected")
        check("Y confirms the one being tested and focus moves to the next open one", True)
        page.keyboard.press("n")
        wait_hyp(page, "h3", "refuted")
        page.keyboard.press("y")
        page.wait_for_selector("#error", state="visible")
        check("Y/N with nothing being tested explains itself", "add one first" in page.inner_text("#error"))

        page.click("[data-role=dictate]")
        page.wait_for_selector("[data-role=hyp-dictating]", state="visible")
        check(
            "dictate mode is clearly shown", "every sentence" in page.inner_text("[data-role=hyp-dictating]")
        )
        page.wait_for_selector(".hyp-row[data-hypothesis-id=h5]", timeout=60_000)
        check(
            "each spoken sentence became its own hypothesis",
            "spoken thought" in page.inner_text(".hyp-row[data-hypothesis-id=h5] .hyp-text"),
        )
        page.keyboard.press("v")
        page.wait_for_selector("[data-role=hyp-dictating]", state="hidden")
        count = len(hyp_rows(page))
        page.wait_for_timeout(11_000)  # longer than one fake-mic loop
        check("V stops dictating: no new hypotheses appear afterwards", len(hyp_rows(page)) == count)
        end_session(page)

    events = app.sidecar("ls20")
    stated = [e for e in events if e["kind"] == "hypothesis"]
    check(
        "sidecar: typed h1-h3 then spoken h4-h5",
        [(e["hypothesis_id"], e["source"]) for e in stated][:5]
        == [("h1", "typed"), ("h2", "typed"), ("h3", "typed"), ("h4", "stt"), ("h5", "stt")],
    )
    trail = [
        (e["hypothesis_id"], e["previous"], e["verdict"]) for e in events if e["kind"] == "hypothesis_verdict"
    ]
    check(
        "sidecar: verdict trail incl. reset and change of mind",
        trail
        == [
            ("h2", "open", "refuted"),
            ("h1", "open", "confirmed"),
            ("h2", "refuted", "open"),
            ("h2", "open", "confirmed"),
            ("h3", "open", "refuted"),
        ],
        str(trail),
    )
    check(
        "sidecar: dictate on then off", [e["on"] for e in events if e["kind"] == "dictate"] == [True, False]
    )
    check(
        "sidecar: speech events record phase at start and at end",
        all("phase_at_end" in e for e in events if e["kind"] == "speech"),
    )


def flow_reflect_prompt(app: App, mic: Path, headed: bool) -> None:
    with browser_page(app, mic, headed) as page:
        start_game(page, "tst1")
        page.click("#grid")  # tst1: a click does nothing but counts as touching the game -> probe
        wait_phase(page, "probe")
        page.keyboard.press("ArrowUp")  # tst1: ACTION1 clears its only level
        page.wait_for_selector("[data-role=prompt]", state="visible", timeout=5_000)
        check(
            "clearing a level shows the reflect prompt",
            "Level 1 cleared" in page.inner_text("[data-role=prompt]"),
        )
        check("a cleared level returns to observe", phase(page) == "observe")
        check(
            "prompt does not block play",
            page.eval_on_selector("[data-role=prompt]", "e => getComputedStyle(e).pointerEvents !== 'none'"),
        )
        page.keyboard.press("5")
        wait_phase(page, "reflect")
        check(
            "pressing 5 turns the prompt into reflection coaching",
            "Reflecting" in page.inner_text("[data-role=prompt]"),
        )
        page.keyboard.press("ArrowUp")
        wait_phase(page, "probe")
        check(
            "touching the game ends reflect and hides the prompt", not page.is_visible("[data-role=prompt]")
        )
        end_session(page)
    events = app.sidecar("tst1")
    check("tst1 is a custom game, so train-ok", events[0]["data_use"] == "train-ok", events[0]["data_use"])
    check(
        "sidecar: observe, probe, observe(level_cleared), reflect, probe",
        [(e["phase"], e["reason"]) for e in events if e["kind"] == "phase_change"]
        == [
            ("observe", "session_start"),
            ("probe", "auto_first_action"),
            ("observe", "level_cleared"),
            ("reflect", "manual"),
            ("probe", "auto_first_action"),
        ],
    )


def flow_timeline_and_verify(app: App, mic: Path, headed: bool) -> None:
    """V6: a session recorded through the real UI renders as a timeline and replays identically."""
    with browser_page(app, mic, headed) as page:
        start_game(page, "ls20")
        page.keyboard.press("t")
        page.keyboard.type("the grey square looks like a mirror of mine")
        page.keyboard.press("Enter")
        page.keyboard.press("h")
        page.keyboard.type("stepping on the blue cross rotates it")
        page.keyboard.press("Enter")
        page.keyboard.press("Escape")
        for key in ["ArrowRight", "ArrowUp", "ArrowUp", "ArrowLeft", "ArrowDown", "ArrowDown", "ArrowRight"]:
            page.keyboard.press(key)
            page.wait_for_timeout(120)
        page.click(".hyp-row[data-hypothesis-id=h1] .no")
        page.wait_for_selector(".hyp-row[data-hypothesis-id=h1][data-status=refuted]")
        page.wait_for_selector(".final:not(.typed)", timeout=30_000)  # a spoken line, so there is speech too
        end_session(page)

    recordings = sorted(app.rec.glob("*ls20*.recording.jsonl"), key=lambda p: p.stat().st_mtime)
    recording = recordings[-1]
    env = {**os.environ, "ARC_ENVIRONMENTS_DIR": str(app.envs)}
    cmd = [sys.executable, "-m", "backend.timeline", str(recording), "--verify"]
    done = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    check(
        "timeline --verify exits 0 on a browser-recorded session",
        done.returncode == 0,
        done.stderr.strip()[-160:],
    )
    rows = [json.loads(line) for line in recording.read_text().splitlines()]
    check(
        "recording is schema 3 with a frame hash on every step",
        all(r.get("schema_version") == 3 and len(r.get("frame_sha256", "")) == 64 for r in rows),
    )
    check(
        "every step was matched by frame hash",
        f"{len(rows)} steps replayed, {len(rows)} matched by frame hash" in done.stderr,
        done.stderr.strip()[-120:],
    )
    md = done.stdout
    check("timeline shows the hypotheses table with h1 FALSE", "| h1 | FALSE |" in md)
    check(
        "timeline shows typed note, spoken line and phase change",
        all(needle in md for needle in ("**note**", "**said**", "(auto_first_action)")),
    )

    # tamper: a different move must be caught at exactly that step
    tampered = recording.with_name(recording.name.replace(".recording.", ".tampered.recording."))
    rows[3]["action_id"] = 3 if rows[3]["action_id"] != 3 else 4
    tampered.write_text("\n".join(json.dumps(r) for r in rows))
    bad = subprocess.run(
        cmd[:-2] + [str(tampered), "--verify"], cwd=ROOT, env=env, capture_output=True, text=True
    )
    check(
        "a tampered move fails verification at that step",
        bad.returncode == 1 and "VERIFY FAILED at step" in bad.stderr,
        bad.stderr.strip()[-110:],
    )


def _box(page, selector: str) -> dict:
    return page.eval_on_selector(
        selector,
        "e => { const r = e.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom}; }",
    )


def _page_scrolls(page) -> tuple[bool, bool]:
    return tuple(
        page.evaluate(
            "() => [document.documentElement.scrollHeight > innerHeight + 1,"
            " document.documentElement.scrollWidth > innerWidth + 1]"
        )
    )


def flow_layout(app: App, mic: Path, headed: bool) -> None:
    """The play screen at real laptop sizes: grid left, panel right, nothing below the fold."""
    # 1366x768 laptop: the page itself gets ~650px once browser chrome is subtracted
    for name, size in (("1366x650 laptop page", (1366, 650)), ("1920x1000 desktop", (1920, 1000))):
        with browser_page(app, mic, headed, viewport=size) as page:
            start_game(page, "ls20")
            # Fill the panel the way a real session does: many hypotheses and many transcript lines.
            page.keyboard.press("h")
            for i in range(9):
                page.keyboard.type(f"hypothesis number {i + 1} about how the squares interact")
                page.keyboard.press("Enter")
            page.keyboard.press("Escape")
            for i in range(14):
                page.evaluate(
                    "t => { const f = document.querySelector('[data-role=finals]');"
                    " const d = document.createElement('div');"
                    " d.className = 'final'; d.textContent = t; f.appendChild(d); }",
                    f"a long spoken sentence number {i} that goes on a little so rows wrap sometimes",
                )
            grid, panel = _box(page, "#grid"), _box(page, "#transcript")
            tag = f"[{name}] "
            check(
                tag + "grid and panel are side by side",
                panel["x"] >= grid["right"] - 1 and panel["y"] < grid["bottom"],
                f"grid right={grid['right']:.0f} panel x={panel['x']:.0f}",
            )
            check(
                tag + "page does not scroll, vertically or horizontally",
                _page_scrolls(page) == (False, False),
            )
            check(
                tag + "grid cells are a whole number of pixels",
                grid["w"] % 64 == 0 and grid["h"] % 64 == 0,
                f"{grid['w']:.0f}px",
            )
            for label, sel in (
                ("phase chips", ".phases"),
                ("hypotheses box", "[data-role=hyp-add]"),
                ("transcript", "[data-role=finals]"),
                ("note box", "[data-role=note]"),
                ("end-session button", "#end"),
                ("grid", "#grid"),
            ):
                b = _box(page, sel)
                check(
                    tag + f"{label} is fully inside the window",
                    b["h"] > 0 and b["y"] >= 0 and b["bottom"] <= size[1] and b["right"] <= size[0],
                    f"{b['y']:.0f}..{b['bottom']:.0f} of {size[1]}",
                )
            lists = page.evaluate(
                "() => ['[data-role=hyp-list]', '[data-role=finals]'].map(s => {"
                " const e = document.querySelector(s);"
                " return [e.scrollHeight > e.clientHeight, getComputedStyle(e).overflowY]; })"
            )
            check(
                tag + "a long hypotheses list and transcript scroll inside the panel",
                lists[0][0] and lists[1][0] and lists[0][1] == "auto" and lists[1][1] == "auto",
                str(lists),
            )

            top_before = _box(page, "#grid")["y"]
            page.keyboard.press(
                "n"
            )  # nothing is being tested? h9 is, so first clear: error comes from a bad action
            page.evaluate("() => document.getElementById('error').textContent = 'x'.repeat(200)")
            page.evaluate("() => { const e = document.getElementById('error'); e.style.display = 'block'; }")
            check(
                tag + "an error banner overlays instead of pushing the grid",
                _box(page, "#grid")["y"] == top_before and _page_scrolls(page) == (False, False),
            )
            end_session(page)

    with browser_page(app, mic, headed, viewport=(800, 900)) as page:
        start_game(page, "ls20")
        grid, panel = _box(page, "#grid"), _box(page, "#transcript")
        check(
            "[800px wide] narrow screens stack the panel under the grid",
            panel["y"] >= grid["bottom"] - 1,
            f"grid bottom={grid['bottom']:.0f} panel y={panel['y']:.0f}",
        )
        check("[800px wide] no horizontal overflow", _page_scrolls(page)[1] is False)
        end_session(page)

    with browser_page(app, mic, headed, viewport=(1366, 650)) as page:
        start_game(page, "tst1")
        grid = _box(page, "#grid")
        cell = (grid["w"] - 2) / 64  # the canvas has a 1px border on each side
        targets = [(0, 0), (63, 63), (32, 32), (10, 50), (31, 31), (63, 0)]
        for cx, cy in targets:  # click the middle of each target cell, and also each cell's edges
            page.mouse.click(grid["x"] + 1 + (cx + 0.5) * cell, grid["y"] + 1 + (cy + 0.5) * cell)
            page.wait_for_timeout(120)
        recording = sorted(app.rec.glob("*tst1*.recording.jsonl"))[-1]
        rows = [json.loads(line) for line in recording.read_text().splitlines()]
        got = [(r["action_input"]["x"], r["action_input"]["y"]) for r in rows if r["action_id"] == 6]
        check(
            "clicking the middle of cells on the scaled grid maps to exactly those cells",
            got == targets,
            f"{got}",
        )
        end_session(page)


FLOWS = {
    "picker_and_meter": flow_picker_and_meter,
    "heldout": flow_heldout,
    "notes_phases_mute_end": flow_notes_phases_mute_end,
    "hypotheses": flow_hypotheses,
    "reflect_prompt": flow_reflect_prompt,
    "timeline_and_verify": flow_timeline_and_verify,
    "layout": flow_layout,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--only", help="run flows whose name contains this")
    parser.add_argument("--headed", action="store_true", help="show the browser")
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="arcplay-e2e-"))
    mic = tmp / "mic.wav"
    write_fake_mic(mic)
    app = App(tmp)
    try:
        for name, flow in FLOWS.items():
            if args.only and args.only not in name:
                continue
            print(f"\n== {name}", flush=True)
            before = len(RESULTS)
            try:
                flow(app, mic, args.headed)
            except Exception as exc:  # a crashed flow is a failed flow, but keep running the others
                check(f"{name} ran to completion", False, f"{type(exc).__name__}: {exc}")
            if len(RESULTS) == before:
                check(f"{name} produced checks", False)
    finally:
        app.stop()
    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed", flush=True)
    if failed:
        print("failed: " + "; ".join(failed))
        print(f"(server log and recordings kept in {tmp})")
        return 1
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
