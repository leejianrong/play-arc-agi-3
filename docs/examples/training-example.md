# Worked example: one real session as decision points

Companion to ADR-0010. The session is the first real annotated play (ls20, a public game, so it is
`reference-only` and **not** training data; it is used here only to show the shape and the numbers). The
observation text is a placeholder until ARC-87 defines it.

## What the rule does to a real session

Rule: group every content event (speech, typed note, hypothesis, verdict) by the step it was said at; the
moves from that step until the next group are the action chunk.

| | ls20 (10 min) | r11l (first test, 9 steps) |
|---|---|---|
| steps | 142 | 9 |
| content events | 71 | 39 |
| **decision points** | **24** | 6 |
| moves per chunk (mean / median / max) | 5.9 / 4 / 33 | 1.3 / 1 / 3 |
| words of reasoning per decision (mean / median / max) | 42 / 16 / 333 | 99 / 70 / 325 |
| steps covered by a chunk | 141 of 141 | 8 of 8 |

Most steps carry no speech of their own; the rule attaches them to the decision that planned them.

## One decision, step 1 of ls20

The player had just pressed right (the first move). They said three things, then moved up four times and left once.

```json
{
  "schema_version": 1,
  "example_id": "local.ls20-9607627b.lean.20261013T173934Z#2",
  "game_id": "ls20-9607627b",
  "data_use": "reference-only",
  "input": {
    "game": {"id": "ls20-9607627b", "win_levels": 7, "available_actions": [1, 2, 3, 4]},
    "level": {"index": 1, "attempt": 1, "levels_completed": 0},
    "observation": {
      "step": 1,
      "text": "<compact text rendering of the frame after step 1: ARC-87>",
      "frame_sha256": "<from the recording>"
    },
    "since_last": {"actions": [{"id": 4}], "text": "<what changed after RIGHT: ARC-87>"},
    "ledger": [],
    "history": [
      {
        "reasoning": "What do I observe? I observe a yellow background ... Okay, so now I'm gonna try to press some arrow keys first, trying an arrow key to the right ...",
        "actions": [{"id": 4}]
      }
    ]
  },
  "output": {
    "phase": "probe",
    "reasoning": "Okay, that worked\nIt did move to the right, so...\nI'm gonna see if I can move up",
    "ledger_ops": [],
    "actions": [{"id": 1}, {"id": 1}, {"id": 1}, {"id": 1}, {"id": 3}]
  },
  "meta": {"steps": [1, 6], "event_ids": ["e23", "e24", "e25"], "sources": ["stt"], "stt": "small.en"}
}
```

The next decision (step 6) starts from the observation after those five moves, with `since_last.actions` equal
to this chunk. That is how a few spoken lines drive many moves, and why "per step" would have been mostly empty.

## What ledger operations look like

This session predates the hypothesis list, so there are none in the data. The schema is (illustrative):

```json
"ledger_ops": [
  {"op": "propose", "id": "h1", "statement": "stepping on the blue cross rotates the grey square"},
  {"op": "verdict", "id": "h1", "verdict": "confirmed"}
]
```

and the `ledger` in a later example's input would list `h1` with status `confirmed`.
