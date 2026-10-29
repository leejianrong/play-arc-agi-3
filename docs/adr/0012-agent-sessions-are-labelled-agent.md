# ADR-0012: Agent sessions are labelled `agent` and kept apart from human data

- Status: Accepted
- Date: 2026-10-30
- Deciders: Jian (user), agent (recommendation)
- Extends: ADR-0009 (data-use policy)

## Context

ADR-0009 labels sessions `train-ok`, `reference-only` or `heldout` to protect two things: the human dataset
(the point of the annotation work) and the solver's held-out evaluation games. An agent playing through the MCP
server (ADR-0011) writes the same files. Its reasoning is model output, not human reasoning, so mixing the two
would corrupt the dataset, and an agent that plays held-out games and then informs a training or design
decision could leak the evaluation set.

## Decision

- A session played through the MCP server has `data_use: "agent"`, `actor: "agent"`, and `agent: "claude-code"`
  in `session_start`, and its files start with `agent.`. The human policy class of the game is still recorded as
  `game_policy` (`train-ok`, `reference-only`, `heldout`) so agent results can be grouped by game kind.
- Agent sessions are **never** exported as human training data. The exporter (V7, ARC-89) refuses them unless
  `--include-agent` is passed, and then marks every example `actor: "agent"`.
- **Held-out games** are refused to the agent unless `start_game(..., allow_heldout=true)` is passed
  explicitly. The session records that it was allowed. Using agent traces from held-out games to design or train
  anything is the solver project's call (its ADR-0012), not this repo's.
- Agent play is annotatable like human play: `note`, `hypothesis_*` and `set_phase` write the same events with
  `source: "agent"`, so `make timeline` and the decision-point format (ADR-0010) apply unchanged.
- Distilling agent traces into training data is a different pipeline (teacher-labelled data, solver ADR-0012)
  and is out of scope here.

## Alternatives considered

| Option | Why not |
|--------|---------|
| Treat agent play as `reference-only` | That label means "human baseline on a public game"; it would let agent traces into human exports by default. |
| A separate recordings directory | The prefix and label are enough, and one directory keeps `make timeline` and `latest` simple. |
| No held-out guard for the agent | Cheap to forget; an explicit flag makes the exception visible in the data. |

## Consequences

- Adds a fourth `data_use` value everywhere the policy is read (policy loader, export, timeline header).
- Agent-vs-human comparisons need both to be read together, which the shared format allows.
- The guard is a convention enforced by one flag, not a sandbox: an agent with repo access could bypass it by
  other means. Evaluation integrity still relies on how the agent is run (ADR-0011, Consequences).
