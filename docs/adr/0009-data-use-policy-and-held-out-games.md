# ADR-0009: Annotated sessions carry a data-use label; some public games are held out

- Status: Accepted
- Date: 2026-10-13
- Deciders: Jian (user), agent (recommendation; the "your call" on game split)

## Context

The sibling `solve-arc-agi-3` project gates fine-tuning (its ADR-0012) and
rejects training data that encodes solutions to public demonstration games, and
it evaluates on held-out public games. Human think-aloud traces on those same
games would be exactly such solution traces, and a player who has annotated a
game can no longer produce an honest first-contact trace of it either. Without
a rule, the dataset could be quietly unusable under the project's own policy.

## Decision

Every annotated session's `session_start` event (ADR-0007) carries
`data_use`:

- `train-ok`: custom environments (V2) and any game not in ARC's public catalog.
- `reference-only`: public ARC-AGI-3 games. Valuable as a human baseline and
  for validating the protocol and tooling, but excluded from any training
  export by default, matching `solve-arc-agi-3` ADR-0012.
- `heldout`: annotation is refused. These games can be played unrecorded, but
  the app will not capture annotations for them, so the evaluation set stays
  clean of human traces.

The assignment lives in `data_policy.json` at the repo root, not in code. The
initial held-out set is every third game in sorted order of the 25 downloaded
public games: `ar25, cn04, g50t, lp85, r11l, sb26, sp80, tr87, wa30`. This
selection is arbitrary on purpose; it should be reconciled with whatever
evaluation split `solve-arc-agi-3` actually uses, and the file edited to match.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Annotate every public game, sort it out at export time | The player's knowledge of a game can't be un-leaked, and held-out games would be burned. |
| Annotate only custom games | Safest, but there are no custom games yet and nothing to calibrate the protocol or tools against. `reference-only` data on public games gives that without feeding training. |
| Hash-based random split in code | Opaque, and changing it means a code change; a JSON file is visible and editable. |

## Consequences

- Real training data initially has to come from custom environments, so V2 (and
  authoring custom games) becomes the bottleneck for usable data. That is a
  real constraint on this milestone's value and is recorded as a risk.
- The restriction is a policy of this repo, not a rule from the competition
  (which permits public external data); it can be relaxed by editing the file
  and `solve-arc-agi-3` ADR-0012 together.
