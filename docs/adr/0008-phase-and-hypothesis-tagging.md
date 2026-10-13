# ADR-0008: Explicit play phases with auto-advance, and sparse hypothesis tags

- Status: Accepted
- Date: 2026-10-13
- Deciders: Jian (user), agent (recommendation)

## Context

The data is only useful for training if a reader can tell what kind of thinking
a thought is (looking, testing, planning, executing) and which belief it
supports or kills. Inferring that later from free text is cheap to capture but
mislabels data in ways that cannot be corrected afterwards. Forcing structure on
every utterance would kill the think-aloud flow, so the structure has to cost
the player almost nothing.

The intended human protocol, per level: OBSERVE (hands off, describe and
hypothesize), PROBE (predict, act, compare), PLAN (state the rule and the
action plan), EXECUTE (narrate only surprises), REFLECT (1-3 sentences after
the level). Surprises send the player back to OBSERVE or PROBE.

## Decision

**Phase** is a field on every annotation event (ADR-0007) with a small state
machine in the backend:

- Each level starts in `observe` (session start, and when `levels_completed`
  increases).
- The first game action while in `observe` auto-switches to `probe`, since
  touching the game is the signal. No other automatic transitions.
- Hotkeys declare the rest: `1` observe, `2` probe, `3` plan, `4` execute,
  `5` reflect. Every change is stored as a `phase_change` event.
- Phase is never enforced; input is never blocked in any phase.

**Hypothesis tags** are optional and sparse: `H` opens a new hypothesis (the
next utterance or typed note becomes its statement, ID `h1`, `h2`, ... stable
within the session), `Y` marks the selected hypothesis confirmed, `N` marks it
refuted. Selection defaults to the most recent open hypothesis; clicking a chip
in the side panel selects another. Tags are separate events
(`hypothesis`, `hypothesis_verdict`) so free text stays free, and the
`hypothesis_id` field on other events is set to the currently selected
hypothesis. Verdict events carry `step_at_end`, so evidence is linked to the
step it was tested on. This lines up with the hypothesis ledger in
`solve-arc-agi-3` (statement, evidence, counterexample, status).

Hotkeys avoid the existing game keys (arrows, WASD, space, Enter, Backspace,
R): digits `1-5`, `H`, `Y`, `N`, `M` (mute), and `T` (focus the typed-note box;
Enter sends, Esc cancels, both return focus to the game).

## Alternatives considered

| Option | Why not |
|--------|---------|
| Infer phase afterwards from text and actions | Cheapest capture, but wrong labels are unrecoverable and ground truth is the main value of this dataset. |
| Block game input outside PROBE/EXECUTE | Enforces discipline but fights the player; discipline is a habit, not a lock. |
| Mandatory structured entry for every hypothesis (form fields for prediction, evidence) | Adds friction to every thought; speech is primary and prediction/result phrasing is covered by the protocol, not the UI. |
| Free text only | Loses the link between a belief and the step that tested it, and the mapping onto the solver's ledger. |

## Consequences

- Phase labels will be imperfect (the player forgets a hotkey); auto-advance to
  `probe` and the timeline CLI keep the common case right and the rest
  fixable by editing the sidecar.
- New global key handling must not fire while the note box has focus.
- Hotkeys are the only UI cost; no extra screens.

## Implementation notes (V4, 2026-10-14)

- Notes, phase changes and the end of a session travel on the session socket (`note`, `phase`, `end`);
  mute and `audio_end` travel on the audio socket, because they act on the audio pipeline.
- Muting flushes the sentence in progress, then drops PCM **and** the raw audio retention until
  unmuted: a muted session records nothing. Each toggle is a `mute` event.
- A speech event's `phase` is the phase at the moment the utterance **began**, so a prediction spoken
  just before touching the game stays `observe`/`probe` as spoken, not whatever it became afterwards.
- A level clear takes precedence over the auto-probe, so the clearing action does not flip the new
  level straight to `probe`.
- Held-out games remain playable. The picker tags them and starts them without annotation; the server
  refuses annotation for them regardless (ADR-0009).
- "End session" stops the mic, has the server finish the open sentence (`audio_end` -> `flushed`),
  closes the annotation session and returns to the picker, showing the saved file names.

## Implementation notes (V5, 2026-10-14)

- **Hypothesis capture.** `H` arms a pending hypothesis (pressing `H` again cancels). The next typed note, or
  the next spoken sentence that *ends* after the press, becomes its statement, so a sentence already under
  way when you hit `H` still counts. The statement is also stored as a normal `text`/`speech` event, tagged
  with the new id; a separate `hypothesis` event links to it by `source_event_id`.
- **Verdicts.** `Y`/`N` act on the selected hypothesis and write `hypothesis_verdict` with `previous`
  (`open`, or the earlier verdict). Selection then falls back to the most recent other open hypothesis, or
  to none. Giving a verdict to an already-closed hypothesis requires clicking its chip first, which is the
  explicit reopen; `previous` records it.
- **Tagging uses selection at utterance start.** Transcripts arrive seconds after speech, so "no, it
  didn't" said about h1 stays filed under h1 even if `N` was pressed (and selection moved) before the text
  landed.
- **Reflect (amends the "no other automatic transitions" rule).** A level clear sends `level_cleared` and
  the UI shows a non-blocking prompt inviting `5` (reflect). Because reflect is between-level talk, the first
  game action while in `reflect` now flips to `probe` (like `observe`); otherwise a forgotten `1` would
  leave the next level mislabelled `reflect`.
- A first action that itself clears a level never passes through `probe`: the level clear wins.

## Revision after first use (2026-10-14): hypotheses are a list, not a hotkey ritual

The V5 design (`H`, say it, `Y`/`N`) failed in a real session: no hypothesis was ever recorded. `H` was a
toggle, a statement only arrives 2-3 s after you stop talking, and a second `H` press (to "finish") cancelled
the capture before the sentence landed. There was also no visible list and no way to enter several ideas, test
them, and mark them as the game is worked out. Superseding the V5 notes above:

- **A visible list** of hypotheses under the grid, each row with `true`, `false` and reset buttons that act on
  *that* row, in any order, any time. A row can be un-decided or changed (`previous` records it).
- **Several at once:** a type-and-Enter box that stays focused for the next one (`H` jumps to it, Esc returns to
  the game), and **dictate** mode (button or `V`) in which every spoken sentence becomes a hypothesis until you
  stop. Typed notes stay notes while dictating.
- **"Being tested" is a focus**, not a gate: click a row to set it; `Y`/`N` act on it and then move on to the
  latest other open hypothesis. Marking another row never steals the focus. It is used to tag your speech.
- **Arming is idempotent** (`hypothesis_open`), cancelling is explicit (`hypothesis_cancel`). The UI no longer
  exposes the one-shot path, only the list, dictate, and the shortcuts.
- Speech events now also store `phase_at_end` next to `phase` (at start): a deliberate phase key is usually
  pressed *after* saying the sentence, so the start phase mislabels it.
- Lone hesitations ("Um...", "Hmm") are dropped at transcription time.
