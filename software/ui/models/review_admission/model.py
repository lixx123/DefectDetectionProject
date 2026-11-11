"""Immutable runtime projections, deliberately separate from domain serialization."""
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
import json


class ReviewBucket(StrEnum):
    AUTO_ACCEPT='AUTO_ACCEPT'
    AUTO_REJECT='AUTO_REJECT'
    MANUAL_REVIEW='MANUAL_REVIEW'
    AUDIT_ONLY='AUDIT_ONLY'


class ReviewPriority(StrEnum):
    HIGH='HIGH'
    MEDIUM='MEDIUM'
    LOW='LOW'


@dataclass(frozen=True, order=True)
class ReviewObjectKey:
    kind: str
    defect_id: str = ''
    candidate_source: str = ''
    candidate_id: str = ''

    def __post_init__(self):
        if self.kind not in ('DEFECT','CANDIDATE'):raise ValueError('unknown object kind')
        if self.kind=='DEFECT' and (not self.defect_id or self.candidate_id or self.candidate_source):raise ValueError('invalid Defect key')
        if self.kind=='CANDIDATE' and (self.defect_id or not self.candidate_id or not self.candidate_source):raise ValueError('invalid Candidate key')

    @property
    def object_id(self):return self.defect_id if self.kind=='DEFECT' else self.candidate_id

    @property
    def token(self):
        return json.dumps((self.kind,self.defect_id,self.candidate_source,self.candidate_id),ensure_ascii=False,separators=(',',':'))


@dataclass(frozen=True)
class ReviewAdmissionDecision:
    object_key: ReviewObjectKey
    bucket: ReviewBucket
    priority: ReviewPriority | None
    reasons: tuple[str,...]
    evidence: Mapping[str,object]

    def __post_init__(self):
        if not self.reasons:raise ValueError('decision reasons required')
        if (self.bucket==ReviewBucket.MANUAL_REVIEW)!=(self.priority is not None):raise ValueError('manual decision requires priority')
        if self.object_key.kind=='DEFECT' and self.bucket not in (ReviewBucket.AUTO_ACCEPT,ReviewBucket.MANUAL_REVIEW):raise ValueError('final Defect must be protected')
        if self.object_key.kind=='CANDIDATE' and self.bucket==ReviewBucket.AUTO_ACCEPT:raise ValueError('acceptance belongs to final Defect')
        object.__setattr__(self,'evidence',MappingProxyType(dict(self.evidence)))


@dataclass(frozen=True)
class ReviewTask:
    task_key: str
    task_kind: str
    primary_object: ReviewObjectKey
    related_candidates: tuple[tuple[str,str],...]
    priority: ReviewPriority
    reasons: tuple[str,...]
    evidence: Mapping[str,object]


@dataclass(frozen=True)
class ReviewAdmissionResult:
    decisions: tuple[ReviewAdmissionDecision,...]
    tasks: tuple[ReviewTask,...]
    summary: Mapping[str,object]
    warnings: tuple[str,...]
    policy_id: str
    policy_version: str
    policy_hash: str
