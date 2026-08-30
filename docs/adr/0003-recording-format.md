# ADR-0003: Recording format — versioned JSONL, one line per step, full frame captured

- Status: Accepted
- Date: 2026-08-30
- Deciders: Jian (user), agent (recommendation)

## Context

The stated end goal, beyond this MVP, is an annotation tool: loading a past
session and recording the human's thought process against it, frame by
frame. Whatever the MVP records becomes that tool's only input — there is no
opportunity to "record more" retroactively for a session that already
happened, and remote sessions are not guaranteed replayable later (`guid`s
can expire, and there is no confirmed API for re-fetching a past session's
frame history).

The project has one user, one machine, no concurrent writers, and a strong
preference (matched by the official `ARC-AGI-3-Agents` repo's own
`Recorder`) for something the user can `cat`, `grep`, and diff without
tooling.

## Decision

Every play session writes one file:
`recordings/{source}.{game_id}.{guid}.{started_at}.recording.jsonl`. Every
step — including the initial `RESET` — appends exactly one JSON line:

```json
{"schema_version": 1, "step_index": 0, "timestamp": "2026-08-30T12:00:00Z",
 "source": "remote", "game_id": "ls20", "guid": "...",
 "action_id": 0, "action_input": null,
 "frame": [[...64x64...]], "state": "NOT_FINISHED",
 "levels_completed": 0, "win_levels": 3, "available_actions": [1,2,3,4,5,6]}
```

`schema_version` is carried on every line (not just a file header) so a
single line is always self-describing, and a future reader can branch on it
without first locating a header record.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Actions-only log, reconstruct frames later by replay | Blocks the stated future goal outright if a `guid` has expired or the remote game state isn't bit-for-bit reproducible from actions alone — there is no confirmed replay endpoint for arbitrary past sessions. |
| SQLite or another embedded database | No query or concurrency need justifies it for one user on one machine; flat files are directly readable, `git diff`-able, and greppable, which JSONL already gives for free. |
| One JSON array per file instead of JSONL | Requires the whole file to be valid to read any of it, and can't be tailed/appended cheaply while a session is still in progress. JSONL degrades gracefully — a crash mid-session still leaves every completed step readable. |

## Consequences

- Cost is disk space only: a few MB per session at 64×64×1 cell-int grids,
  trivial on a laptop, not worth compressing at this scale.
- The recording is the only contract the eventual annotation tool needs to
  honor; changing it later is a schema_version bump plus conditional
  parsing, not a migration of existing files.
- Recording every frame, not just actions, means the Recorder must be wired
  to receive every `FrameData` a `GameSource` produces, including the one
  from `reset()` — a gap here would silently produce sessions with an
  off-by-one step count.
