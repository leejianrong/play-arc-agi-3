# ARC Play (play-arc-agi-3): Plan

Status: agreed · Milestone: MVP (done) + Annotation (planned 2026-10-13, slices V3-V6)

## Problem

The official ARC-AGI-3 web UI is laggy and unresponsive, which gets in the
way of actually playing the games. **Correction (2026-08-30, ADR-0004):**
this plan originally assumed the real games' logic runs exclusively on ARC's
servers with no offline path. That was wrong — ARC's own `arc_agi` toolkit
downloads a game's real source once and runs every subsequent action
locally. The actual fix is local execution, not just a leaner client.

There's also no way today to record a play session as you go: what you saw,
what you did, and when. That matters because the longer-term goal is an
annotation tool for capturing a human's thought process while solving these
puzzles, and that tool needs something to load.

**Annotation milestone (2026-10-13).** The MVP records what you did but not
why. The goal now is a dataset of human reasoning on ARC-AGI-3 puzzles --
spoken think-aloud (or typed notes) aligned to game steps, with an explicit
phase (observe, probe, plan, execute, reflect) and optional hypothesis tags --
good enough to inspect, to compare against the solver's hypothesis ledger in
`solve-arc-agi-3`, and eventually to fine-tune a small model. The part that is
hardest to get right is not the plumbing but the data: what you say, when, and
whether it can legally and sensibly be used for training (ADR-0009).

## Solution

A local web app you start with one command. It opens in your browser, lists
the real ARC-AGI-3 games (and, once slice V2 lands, any custom puzzles you've
authored yourself), and lets you play one with keyboard and mouse against a
fast Canvas-rendered grid. Every action you take and every frame you see is
recorded automatically to a plain file on disk — nothing to remember to save.

With annotation on, you also think aloud. A mic stream is transcribed locally
and appears as live text beside the grid; you can type a note instead at any
time. A phase chip shows where you are in the loop (it starts at OBSERVE on
each level and flips to PROBE the moment you touch the game); keys declare the
other phases and tag hypotheses as confirmed or refuted. Afterwards, a CLI
turns a session into a readable timeline and verifies that replaying your moves
reproduces what you saw.

### Human play protocol

The tool exists to make this protocol cheap to follow. Per level:

1. **OBSERVE** (hands off): describe objects, colours, symmetries, what looks
   controllable, what looks like the goal; state at least one hypothesis.
2. **PROBE** (touch): say "prediction: ..." before each probe, act, then say
   "result: matched / not, because ...". Cheap, reversible probes first; one
   variable at a time.
3. **PLAN**: state the rule you concluded and your confidence, then the plan in
   chunks, before executing.
4. **EXECUTE**: narrate only surprises. A surprise returns you to OBSERVE or
   PROBE, and you say which hypothesis died.
5. **REFLECT** (1-3 sentences after each level): the rule, what misled you,
   what would have been faster.

Habits that matter more than the phases: keep dead ends in; prediction before
outcome; say decisions, not play-by-play; use the same vocabulary every time;
play unfamiliar games, since first contact is where reasoning is most visible.
Which games to annotate is governed by ADR-0009.

## Users and actors

Single primary user: you, playing solo, locally. No multi-user story, no
accounts beyond your own ARC API key. No non-human actors in this milestone
(no agent play, no CI). Nothing to arbitrate — there's only one actor.

## Scope

**In this milestone.**
- Play any real ARC-AGI-3 game through a local, low-latency client
  (R0-R5, R7).
- Automatic, complete recording of every session to a local file (R3, R8).
- Play locally-authored custom puzzle environments through the same UI,
  sequenced after the above (R6).

**In the annotation milestone (V3-V6).**
- Live speech capture, local transcription, typed notes (R9, R10).
- Phase and hypothesis tagging (R11).
- A sidecar annotation file aligned to recorded steps, with frame hashes for
  replay verification (R12).
- A timeline CLI with replay verification (R13).
- A data-use label and a held-out game list (R14).

**Out.**
- An in-app replay viewer or transcript editor. Review is by the timeline CLI
  and hand-editing the annotations file; revisit after real sessions.
- Any fine-tuning run (gated by `solve-arc-agi-3` ADR-0012). The training-format exporter is planned as
  slice V7 (ADR-0010: a training example is a decision point).
- Cloud speech-to-text, speaker diarization, multi-person sessions.
- Agent play, scorecards, or anything competition-submission-related — this
  is a human-play tool.
- Multi-user, cloud sync, mobile. Single laptop, single user.
- Packaging as an installable desktop app (see ADR-0001) — you run a local
  command, not double-click an icon, for now.
- A live online scorecard or shareable replay for real games. Local
  execution (ADR-0004) tracks scoring locally only, by design.

## Requirements

| ID | Requirement | Status |
|----|-------------|--------|
| R0 | Play any real ARC-AGI-3 game from a local, responsive UI, authenticated with your own API key | Core goal |
| R1 | The on-screen grid updates on every response with no perceptible client-side rendering delay | Must-have |
| R2 | Support every action type: ACTION1-5 (keyboard), ACTION6 (mouse click with x,y), ACTION7 (undo, when offered), and RESET | Must-have |
| R3 | Recording is opt-in (off/lean/full, chosen per session before it starts) — superseded by ADR-0005, which found "automatic, no explicit save step" made every throwaway session pile up a large file | Must-have |
| R4 | List available games — the real catalog, plus discovered local custom envs once R6 lands — and let the user pick one | Must-have |
| R5 | Show live game state: score/levels_completed, win_levels, GameState, available actions | Must-have |
| R6 | Support locally-authored custom puzzle environments through the same play+record flow | Must-have |
| R7 | The API key and any secrets never leave the local machine, and never appear in recordings or logs | Must-have |
| R8 | Recordings are self-contained: a future annotation tool can load one without recontacting any API | Nice-to-have |
| R9 | Speak while playing and see a live transcript; final segments are stored aligned to game steps, with no audio sent off the machine | Core goal (annotation) |
| R10 | Type a note at any time as an equivalent alternative to speech; the session works fully with no mic or model | Must-have |
| R11 | Every annotation carries an explicit phase; hypotheses can be opened and marked confirmed or refuted with single keys, without blocking game input | Must-have |
| R12 | Annotations live in a sidecar file aligned to steps; each recorded step carries a frame hash so replay can be verified | Must-have |
| R13 | A CLI renders a session as a readable timeline and verifies a replay against the recorded frame hashes | Must-have |
| R14 | Every annotated session is labelled `train-ok`, `reference-only` or `heldout`; annotating a held-out game is refused | Must-have |

## Shape

| Part | Mechanism | ADR |
|------|-----------|-----|
| S1 | `ArcadeGameSource`, one implementation wrapping `arc_agi.Arcade` — `NORMAL` mode for real games (downloads once, executes locally), `OFFLINE` mode for hand-authored custom envs (V2) — producing a normalized `FrameData` | ADR-0004 |
| S2 | FastAPI backend, one WebSocket session endpoint: client sends `start`/`action` messages, server replies with `FrameData` after every `GameSource` call | ADR-0001 |
| S3 | Vanilla JS + Canvas single-page frontend: renders `FrameData.frame` as a colored grid, captures keyboard/mouse, sends WS messages | ADR-0001 |
| S4 | `Recorder`, opt-in per session (off/lean/full, chosen in the picker): subscribes to every `FrameData` a `GameSource` produces (including from `reset()`), appends one versioned JSONL line per step; lean mode omits the frame grid | ADR-0003, ADR-0005 |
| S5 | `.env`-based `ARC_API_KEY` loaded server-side only; server binds `127.0.0.1` only | — |
| S6 | Audio path: browser AudioWorklet (16 kHz mono PCM16) → binary frames on `/ws/audio` → VAD → `Transcriber` (faster-whisper `small.en`) → interim and final text back to the UI; `MediaRecorder` opus kept beside the session | ADR-0006 |
| S7 | `AnnotationWriter`: append-only sidecar JSONL (`session_start`, `speech`, `text`, `phase_change`, `hypothesis`, `hypothesis_verdict`, `mute`), each event stamped with `step_at_start/end`, level, phase | ADR-0007 |
| S8 | Phase state machine (observe → probe auto on first action; hotkeys for the rest) and hypothesis registry with stable IDs | ADR-0008 |
| S9 | `Recorder` gains `frame_sha256` (schema 3); `make timeline` CLI merges recording + annotations and replays with `--verify` | ADR-0007 |
| S10 | `data_policy.json` + `data_use` label on `session_start`; annotation refused for held-out games | ADR-0009 |

## Affordances

**UI.**

| Affordance | Place | Wires to |
|------------|-------|----------|
| Game picker, with a per-game swatch and a Recording (off/lean/full) control | Landing screen | WS `start {game_id, record}` → `GameSource.reset()` |
| Canvas grid | Play screen | Renders latest `FrameData.frame` |
| Keyboard: arrows/WASD, space, backspace, R | Play screen | WS `action {id}` → `GameSource.step()` |
| Mouse click on grid | Play screen | WS `action {id: 6, data: {x,y}}`, coordinates scaled to 0-63 |
| Status/state header (score, levels, GameState) | Play screen | Renders latest `FrameData` metadata fields |
| Error banner (an overlay, so it never moves the grid) | Any screen | WS error events (API failures, missing key, local env exceptions) |
| Two-column play screen: grid left, annotation panel right (scrolls inside itself) at >= 1000px; stacked below that; grid steps 512/448/384px by window height so cells stay whole pixels | Play screen | CSS only; `make e2e` flow `layout` |
| Annotate toggle in the picker (default off; requires Lean or Full, promotes Off to Lean) | Landing screen | WS `start {…, annotate: true}` |
| Live transcript panel: interim text greyed, finals appended, mic level meter, muted indicator | Play screen | `/ws/audio` interim/final messages |
| Phase chip (observe / probe / plan / execute / reflect), keys `1-5` | Play screen | Phase state machine; `phase_change` events |
| Hypothesis chips with status; keys `H`, `Y`, `N`, click to select | Play screen | `hypothesis` / `hypothesis_verdict` events |
| Typed-note box, `T` to focus, Enter to send, Esc to cancel | Play screen | `text` events |
| Mute key `M`; banner when mic or model is unavailable | Play screen | `mute` events; session continues with typed notes |

**Non-UI.**

| Affordance | Kind | Wires to |
|------------|------|----------|
| `Recorder.append()` | handler, fired on every `FrameData` | Writes one JSONL line under `recordings/` |
| `ArcadeGameSource` | local process wrapper | `arc_agi.Arcade` (`NORMAL`/`OFFLINE`), `environment_files/` |
| `Transcriber` (faster-whisper) | optional-extra service | Utterance audio buffers → text; fake implementation in tests |
| `AnnotationWriter` | handler | Appends to `*.annotations.jsonl` |
| `make timeline FILE=… [--verify]` | CLI | Recording + annotations → markdown; replay against `frame_sha256` |

## Implementation decisions

Backend modules: `backend/game_sources/{base.py,arcade.py}` (the
`GameSource` protocol and its one implementation, ADR-0004),
`backend/config.py` (`ARC_API_KEY` loading), `backend/recorder.py`
(ADR-0003), `backend/server.py` (FastAPI app + the one WebSocket route).
Frontend is a single `frontend/index.html` + `frontend/app.js`, no build
step, no framework — matches ADR-0001's bias toward minimal toolchain.

`FrameData` is the one normalized shape everything downstream depends on:
`game_id, guid, source, frame, state, levels_completed, win_levels,
action_input, available_actions`. `source` is always `"local"` now
(ADR-0004) — kept as a field rather than dropped, since it's still a useful
tag if a third execution path ever shows up.

One `Arcade` (and its scorecard) is constructed per WebSocket connection,
not per game — switching games mid-session reuses the same catalog fetch.
A second browser tab connecting mid-session is a known MVP limitation, not
handled gracefully — surfacing this cleanly (reject vs. take over) is
deferred, since it's cheap to add a lock later without touching the rest of
the design.

Annotation modules (ADR-0006 to ADR-0009): `backend/annotations/`
(`writer.py`, `phases.py`, `policy.py`), `backend/stt/` (`base.py` with the
`Transcriber` protocol and a fake, `whisper.py`, `vad.py`), a second WebSocket
route `/ws/audio` tied to the active session, and frontend modules
`audio_worklet.js`, `annotation_ui.js`. `faster-whisper` is an optional
dependency group (`uv sync --extra stt`) so CI and `make check` don't pull it.
Annotated sessions write the sidecar and audio next to the recording
(ADR-0007); `Recorder` only gains `frame_sha256`. All annotation events share
one server clock with the recording's `timestamp`, and the audio client stamps
its offset at stream open so speech maps to `step_at_start/end`.

Recording filenames: `recordings/{source}.{game_id}.{guid}.{started_at}.recording.jsonl`,
one file per session, matching the pattern the official `ARC-AGI-3-Agents`
repo already uses for its own recordings.

`make run` is the one-command entry point (dev-playbook principle: runnable
in one command). It defaults to port 8000 (`PORT` env var to prefer another)
but auto-falls back to an OS-assigned free port if the preferred one is
taken, rather than refusing to start — a local dev machine routinely has
something else already bound to a common port. `make test` runs the full
fast layer (pytest + the frontend's `node --test` unit tests); nothing in
this project needs real infra, so there's no separate slow layer yet.

## Testing approach

The seams worth testing: `ArcadeGameSource`'s normalization from
`arcengine.FrameDataRaw` to our own `FrameData` (exercised against a real,
tiny fixture game in `OFFLINE` mode — no network, no mocking of `arc_agi`
internals), the WebSocket session loop (message in → correct `GameSource`
call → correct message out → correct recording line), and the Recorder in
isolation (given a sequence of `FrameData`, does the file on disk match). UI
behavior (rendering, input mapping) is covered by a manual end-to-end pass
per slice, since this is a human-play tool and the actual acceptance test is
"does it feel responsive to play" — not something a headless test can
assert.

## Assumed defaults

| ID | Assumed | Cost if wrong |
|----|---------|----------------|
| Q6 | Flat JSONL files, no database | Low — migrating to a DB later is a straight import of existing files |
| Q7 | One active session per server process | Low — add a session lock/registry later without touching `GameSource` or `Recorder` |
| Q8 | Depend on `arc_agi` directly (not the higher-level `ARC-AGI-3-Agents` agent-competition framework) — superseded by ADR-0004, which uses `arc_agi.Arcade` for real games too, not just custom envs | Low — already paid off; `arc_agi` alone pulls no LangGraph/AgentOps surface |
| Q9 | Canvas rendering, not DOM | Low — isolated to the frontend renderer |
| Q10 | Specific keyboard/mouse mapping | Low — a config-level remap, not a redesign |
| Q17 | 16-color palette guessed from ARC-AGI convention, confirmed empirically | Low — visually obvious and fixed in slice V1 the moment a real game is rendered |
| Q30 | Sidecar file rather than inline annotations; additive `frame_sha256` on `Recorder` | Low — a reader can merge either shape |
| Q31 | Annotated sessions at least Lean; raw audio kept locally | Low — one flag each |
| Q32 | Typed-note focus on `T`; hotkeys `1-5/H/Y/N/M` | Low — config-level remap |
| Q33 | Initial held-out list is every third public game in sorted order | Medium — if it disagrees with the solver's eval split, the file must be edited before annotating those games |

## Open risks

- **Usable training data is gated on custom games.** Under ADR-0009 only
  custom environments produce `train-ok` data; public-game sessions are
  reference-only. Until V2 is used to author a set of custom puzzles, the
  annotation milestone yields a protocol and tooling more than a training set.
  Surfaces as soon as the first `train-ok` session is wanted.
- **Mic path through WSL2.** The browser is expected to run on Windows and
  capture audio itself; if it runs under WSLg instead, device access may be
  the problem. Slice V3 confronts this first.
- **Whisper on continuous, noisy audio.** Key clatter and silence produce junk
  or hallucinated segments, and CPU latency may exceed the 1-3 s estimate.
  Slice V3 measures it; mitigations are VAD tuning, a smaller or GPU model,
  and the review step.
- **Habit drift.** The protocol only helps if followed; phase labels and
  prediction/result phrasing degrade as you tire. The timeline CLI is how this
  gets noticed.

- **Exact 0-15 color palette** wasn't confirmed from an authoritative source
  during planning. Low risk, immediately visible and fixable in slice V1.
- **`Arcade.close_scorecard()`'s local `ScorecardManager` behavior under
  real extended play** (many games, many hours) hasn't been observed beyond
  a short smoke test. Low risk — worst case is stale local state, not a
  crash, since gameplay no longer routes through scorecard-keyed lookups
  (ADR-0004).

Resolved during V1 build-plan research (2026-08-30), by reading
`arcprize/ARC-AGI`'s own client source (`arc_agi/remote_wrapper.py`,
`arc_agi/api.py`) rather than the hosted docs, which proved incomplete: the
remote API requires a scorecard (`POST /api/scorecard/open` → `card_id`,
passed into the first `RESET`) that earlier research had missed entirely;
the list-games endpoint is confirmed as `GET /api/games`; and the rate limit
is a generous 600 requests/minute. That research is now mostly of historical
interest — see ADR-0004: after the user reported real, live lag,
`RemoteGameSource` was retired in favor of local execution via `arc_agi`'s
own `NORMAL` mode, which resolved both the lag (0.5ms/action measured
locally, vs. a full HTTP round trip before) and the 400-error report
(caused by the remote server's 15-minute scorecard idle-timeout evicting a
cached session — structurally impossible once actions no longer route
through that cache).
