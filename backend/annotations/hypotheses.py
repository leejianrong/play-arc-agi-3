"""Per-session hypothesis registry (ADR-0008).

`H` arms a pending hypothesis; the next utterance or typed note becomes its statement. `Y`/`N` mark
the *selected* hypothesis confirmed/refuted. Ids (h1, h2, ...) are stable within one session and
never cross sessions: each AnnotationSession owns its own registry.

Selection is time-stamped so an utterance can be tagged with the hypothesis that was selected when
it *began*: transcription lags speech by seconds, and "no, it didn't" said about h1 must not be
filed under h2 just because the player pressed N before the text arrived.
"""

from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass

Verdict = str  # "confirmed" | "refuted"
VERDICTS = ("confirmed", "refuted")


class HypothesisError(ValueError):
    """A hypothesis action that makes no sense right now (user-facing message)."""


@dataclass(slots=True)
class Hypothesis:
    id: str
    statement: str
    status: str  # open | confirmed | refuted
    step: int  # step the hypothesis was stated at
    level: int


class HypothesisRegistry:
    def __init__(self) -> None:
        self.items: dict[str, Hypothesis] = {}
        self.selected: str | None = None
        self.version = 0  # bumped on every change, so callers can tell if state moved
        self._pending_since: int | None = None
        self._sel_ms: list[int] = [0]
        self._sel_hist: list[str | None] = [None]

    @property
    def pending(self) -> bool:
        return self._pending_since is not None

    def toggle_pending(self, now_ms: int) -> bool:
        """H pressed: arm the next statement, or cancel if already armed. Returns the new state."""
        self._pending_since = None if self.pending else now_ms
        self.version += 1
        return self.pending

    def captures(self, end_ms: int) -> bool:
        """Would an utterance/note ending at `end_ms` become the pending statement?

        An utterance already in progress when H was pressed still counts (its end is after the press),
        which is what you want when you hit H halfway through saying the idea.
        """
        return self._pending_since is not None and end_ms >= self._pending_since

    def capture(self, statement: str, now_ms: int, step: int, level: int) -> Hypothesis:
        h = Hypothesis(f"h{len(self.items) + 1}", statement, "open", step, level)
        self.items[h.id] = h
        self._pending_since = None
        self._select(h.id, now_ms)
        return h

    def select(self, hypothesis_id: str, now_ms: int) -> None:
        if hypothesis_id not in self.items:
            raise HypothesisError(f"unknown hypothesis {hypothesis_id!r}")
        self._select(hypothesis_id, now_ms)

    def verdict(self, verdict: Verdict, now_ms: int) -> tuple[Hypothesis, str]:
        """Apply a verdict to the selected hypothesis. Returns (hypothesis, previous status).

        Giving a verdict to an already-closed hypothesis is allowed only because you explicitly
        selected it (clicked its chip): that is the "explicit reopen" case, and `previous` records it.
        """
        if verdict not in VERDICTS:
            raise HypothesisError(f"unknown verdict {verdict!r}")
        if self.selected is None:
            raise HypothesisError("no hypothesis selected: press H and state one first")
        h = self.items[self.selected]
        previous, h.status = h.status, verdict
        open_others = [i for i, x in self.items.items() if x.status == "open" and i != h.id]
        self._select(open_others[-1] if open_others else None, now_ms)
        return h, previous

    def selected_at(self, ms: int) -> str | None:
        i = bisect.bisect_right(self._sel_ms, ms) - 1
        return self._sel_hist[max(i, 0)]

    def state(self) -> dict:
        return {
            "hypotheses": [asdict(h) for h in self.items.values()],
            "selected": self.selected,
            "pending": self.pending,
        }

    def _select(self, hypothesis_id: str | None, now_ms: int) -> None:
        self.selected = hypothesis_id
        self._sel_ms.append(now_ms)
        self._sel_hist.append(hypothesis_id)
        self.version += 1
