"""Per-session hypothesis registry (ADR-0008).

A hypothesis is a statement you intend to test. You can add them three ways: type one (added at once),
press `H` and say or type the next one (one-shot), or turn on *dictate* so that every sentence you
speak becomes a hypothesis until you stop. Each hypothesis then gets a verdict whenever you work it
out, in any order: `confirmed` (true), `refuted` (false), or `open` again.

Ids (h1, h2, ...) are stable within one session and never cross sessions: each AnnotationSession owns
its own registry. "Selected" means the one you're currently testing; it is only used to tag your
speech, and is time-stamped so an utterance is tagged with what was selected when it *began*:
transcription lags speech by seconds, and "no, it didn't" said about h1 must not be filed under h2
just because the selection moved before the text arrived.
"""

from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass

VERDICTS = ("confirmed", "refuted", "open")


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
        self._armed_since: int | None = None
        self._batch = False  # dictate mode: keep capturing every spoken sentence
        self._sel_ms: list[int] = [0]
        self._sel_hist: list[str | None] = [None]

    @property
    def pending(self) -> bool:
        """One-shot capture armed (H pressed), waiting for the next sentence or note."""
        return self._armed_since is not None and not self._batch

    @property
    def batch(self) -> bool:
        return self._batch

    def arm(self, now_ms: int) -> None:
        """Capture the next sentence or note as a hypothesis. Idempotent: arming twice never cancels
        (a toggle did, when a second keypress landed before the first sentence had been transcribed)."""
        if not self._batch and not self.pending:
            self._armed_since = now_ms
            self.version += 1

    def cancel(self, now_ms: int) -> None:
        """Stop waiting for a statement, and stop dictating."""
        if self._batch or self.pending:
            self.set_batch(False, now_ms)

    def set_batch(self, on: bool, now_ms: int) -> None:
        self._batch = on
        self._armed_since = now_ms if on else None
        self.version += 1

    def captures(self, end_ms: int, source: str) -> bool:
        """Would an utterance/note ending at `end_ms` become a hypothesis statement?

        An utterance already in progress when capture was armed still counts (its end is after the
        press). Dictate mode takes speech only: typed notes stay notes.
        """
        if self._armed_since is None or end_ms < self._armed_since:
            return False
        return source == "stt" or not self._batch

    def capture(self, statement: str, now_ms: int, step: int, level: int) -> Hypothesis:
        h = Hypothesis(f"h{len(self.items) + 1}", statement, "open", step, level)
        self.items[h.id] = h
        if not self._batch:
            self._armed_since = None
        self._select(h.id, now_ms)
        return h

    def select(self, hypothesis_id: str, now_ms: int) -> None:
        if hypothesis_id not in self.items:
            raise HypothesisError(f"unknown hypothesis {hypothesis_id!r}")
        self._select(hypothesis_id, now_ms)

    def verdict(
        self, verdict: str, now_ms: int, hypothesis_id: str | None = None
    ) -> tuple[Hypothesis, str]:
        """Give a hypothesis a verdict. Returns (hypothesis, previous status).

        With no id it applies to the selected hypothesis. Changing an already-closed hypothesis is
        allowed (you can change your mind); `previous` records what it was. `open` un-decides it.
        """
        if verdict not in VERDICTS:
            raise HypothesisError(f"unknown verdict {verdict!r}")
        target = hypothesis_id or self.selected
        if target is None:
            raise HypothesisError("no hypothesis selected: add one first, or click one in the list")
        if target not in self.items:
            raise HypothesisError(f"unknown hypothesis {target!r}")
        h = self.items[target]
        previous, h.status = h.status, verdict
        if verdict == "open":
            self._select(h.id, now_ms)
        elif h.id == self.selected:
            # The one you were testing is decided: move on to the latest other open hypothesis.
            others = [i for i, x in self.items.items() if x.status == "open" and i != h.id]
            self._select(others[-1] if others else None, now_ms)
        else:
            self.version += 1
        return h, previous

    def selected_at(self, ms: int) -> str | None:
        i = bisect.bisect_right(self._sel_ms, ms) - 1
        return self._sel_hist[max(i, 0)]

    def state(self) -> dict:
        return {
            "hypotheses": [asdict(h) for h in self.items.values()],
            "selected": self.selected,
            "pending": self.pending,
            "batch": self.batch,
        }

    def _select(self, hypothesis_id: str | None, now_ms: int) -> None:
        self.selected = hypothesis_id
        self._sel_ms.append(now_ms)
        self._sel_hist.append(hypothesis_id)
        self.version += 1
