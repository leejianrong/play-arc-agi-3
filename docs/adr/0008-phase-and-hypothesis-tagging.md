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
