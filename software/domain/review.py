"""Review events are append-only; original algorithm decision is immutable."""
from dataclasses import dataclass, replace
from .enums import ReviewStatus
from .common import FrozenRecord


@dataclass(frozen=True, kw_only=True)
class ReviewEvent(FrozenRecord):
    review_status: ReviewStatus
    reviewer_decision: str | None = None
    reviewer: str | None = None
    review_time: str | None = None
    comment: str | None = None


@dataclass(frozen=True, kw_only=True)
class ReviewInfo(FrozenRecord):
    algorithm_decision: str = "UNSPECIFIED"
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    reviewer_decision: str | None = None
    reviewer: str | None = None
    review_time: str | None = None
    comment: str | None = None
    history: tuple[ReviewEvent, ...] = ()

    def reviewed(self, *, status: ReviewStatus, decision: str | None = None,
                 reviewer: str | None = None, review_time: str | None = None,
                 comment: str | None = None) -> "ReviewInfo":
        if not isinstance(status, ReviewStatus):
            raise ValueError("status must be a ReviewStatus")
        event = ReviewEvent(review_status=status, reviewer_decision=decision,
                            reviewer=reviewer, review_time=review_time, comment=comment)
        updated = replace(self, review_status=status, reviewer_decision=decision,
                          reviewer=reviewer, review_time=review_time, comment=comment,
                          history=self.history + (event,))
        object.__setattr__(updated, "_unknown_fields", dict(self._unknown_fields))
        return updated
