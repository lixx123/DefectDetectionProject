"""Independent human-review protocol. No Qt, detector or formal repository writes."""
from dataclasses import dataclass, asdict, fields, is_dataclass, field
from enum import StrEnum, Enum
from datetime import datetime, timezone
from uuid import uuid4
import hashlib
import json
import re

POLICY_HASH = '63edae3c40966768f907360a377ad7847ebbf477121afb54c1595b69c80f2327'
PROTOCOL = 'human_review_v1'

class HumanReviewDecision(StrEnum):
    CONFIRMED_DEFECT='CONFIRMED_DEFECT'
    FALSE_POSITIVE='FALSE_POSITIVE'
    DUPLICATE_OF_EXISTING_DEFECT='DUPLICATE_OF_EXISTING_DEFECT'
    NEW_MISSED_DEFECT='NEW_MISSED_DEFECT'
    UNCERTAIN='UNCERTAIN'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def source_payload(value):
    """Read-only wire-shaped snapshot, including anomalous runtime lineage.

    The frozen formal serializer rejects dangling links. Review must still be able
    to bind such an in-memory consistency task, without repairing or serializing
    it back into a formal result. For valid results this equals result.to_dict().
    """
    if isinstance(value,Enum):return value.value
    if is_dataclass(value):
        result=dict(getattr(value,'_unknown_fields',{}))
        result.update({f.name:source_payload(getattr(value,f.name)) for f in fields(value) if not f.name.startswith('_')})
        return result
    if isinstance(value,dict):return {k:source_payload(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [source_payload(v) for v in value]
    return value


def now():
    return datetime.now(timezone.utc).isoformat()


def privacy(value):
    """Reject machine absolute paths, including values supplied as free text."""
    if isinstance(value, str) and (re.search(r'(?i)[a-z]:[\\/]', value) or '\\\\' in value or value.startswith('/')):
        raise ValueError('审核协议禁止持久化绝对机器路径')
    if isinstance(value, dict):
        for k,v in value.items(): privacy(k); privacy(v)
    elif isinstance(value, (list,tuple)):
        for v in value: privacy(v)


def allowed_decisions(kind):
    if kind not in ('DEFECT','CANDIDATE'): raise ValueError('unknown object kind')
    return tuple(d for d in HumanReviewDecision if kind=='CANDIDATE' or d!=HumanReviewDecision.NEW_MISSED_DEFECT)


@dataclass(frozen=True)
class HumanReviewRecord:
    review_record_id: str
    result_id: str
    review_task_key: str
    object_kind: str
    object_key: tuple
    decision: str
    target_defect_id: str | None
    reviewer: str
    reviewed_at: str
    comment: str | None
    policy_id: str
    policy_version: str
    policy_hash: str
    source_result_digest: str
    task_digest: str
    revision: int
    geometry_evidence: str  # canonical immutable snapshot; JSON on disk

    def to_dict(self):
        value=asdict(self);value['object_key']=list(self.object_key)
        value['geometry_evidence']=json.loads(self.geometry_evidence)
        return value


def snapshot_task(task, result, candidates):
    k=task.primary_object
    obj=next((d for d in result.defects if d.identity.defect_id==k.defect_id),None) if k.kind=='DEFECT' else candidates.get((k.candidate_source,k.candidate_id))
    g=(obj.geometry if k.kind=='DEFECT' else obj.initial_geometry) if obj else None
    geometry=source_payload(g) if g else {}
    return dict(task_key=task.task_key,task_kind=task.task_kind,object_kind=k.kind,
        object_key=[k.kind,k.defect_id,k.candidate_source,k.candidate_id],object_id=k.object_id,
        source=k.candidate_source,priority=str(task.priority),reasons=list(task.reasons),
        evidence=dict(task.evidence),related_candidates=[list(x) for x in task.related_candidates],geometry=geometry)


@dataclass(frozen=True)
class ReviewContext:
    """Canonical JSON strings keep all nested task snapshots immutable."""
    result_id: str
    source_result_digest: str
    policy_id: str
    policy_version: str
    policy_hash: str
    tasks_json: str
    final_ids: tuple
    access: object = field(default=None,compare=False,repr=False)

    @property
    def tasks(self): return json.loads(self.tasks_json)
    @property
    def task_digest(self): return digest(self.tasks)

    @classmethod
    def from_result(cls,result,admission,access=None):
        candidates={}
        for c in result.audit_log.candidates:
            key=(str(c.source),c.candidate_id)
            candidates[key]=c if key not in candidates else None
        tasks=[snapshot_task(t,result,candidates) for t in admission.tasks]
        tasks.sort(key=lambda t:(['HIGH','MEDIUM','LOW'].index(t['priority']),t['object_kind']!='DEFECT',t['task_key']))
        privacy(tasks)
        return cls(result.result_id,digest(source_payload(result)),admission.policy_id,admission.policy_version,
                   admission.policy_hash,canonical(tasks),tuple(sorted(d.identity.defect_id for d in result.defects)),access)


def latest(state):
    return {r['review_task_key']:r for r in state['records']}


def mismatch(state, context):
    if state['result_id']!=context.result_id or state['source_result_digest']!=context.source_result_digest or state['final_ids']!=list(context.final_ids):return 'RESULT_MISMATCH'
    if (state['policy_id'],state['policy_version'],state['policy_hash'])!=(context.policy_id,context.policy_version,context.policy_hash):return 'POLICY_MISMATCH'
    if context.policy_hash!=POLICY_HASH:return 'POLICY_MISMATCH'
    if state['task_digest']!=context.task_digest:return 'STALE'
    return None


def task_status(task, records, stale=None):
    if stale:return 'STALE'
    r=records.get(task['task_key'])
    return 'PENDING' if r is None else ('UNCERTAIN' if r['decision']=='UNCERTAIN' else 'REVIEWED')


def summary(state, stale=None):
    records=latest(state);tasks=state['tasks'];total=len(tasks)
    def counts(group):
        out={d.value:0 for d in HumanReviewDecision};out.update(total=len(group),pending=0)
        for t in group:
            r=records.get(t['task_key']) if not stale else None
            if r:out[r['decision']]+=1
            else:out['pending']+=1
        return out
    result=counts(tasks);result['completed']=total-result['pending'];result['uncertain']=result['UNCERTAIN']
    result['percent']=100*result['completed']/total if total else 100
    result['historical_record_count']=len(state['records']);result['stale']=stale
    result['by_dimension']={}
    for dimension in ('object_kind','priority','source','reason','band'):
        groups={}
        for t in tasks:
            values=t['reasons'] if dimension=='reason' else [t.get(dimension) if dimension!='band' else t['evidence'].get('band','UNKNOWN')]
            for value in values:groups.setdefault(str(value or 'UNKNOWN'),[]).append(t)
        if dimension=='reason':
            for reason in ('SPATIAL_FINAL_ASSOCIATION','WORK_BOUNDARY_UNCERTAINTY','NEAR_SIZE_THRESHOLD','CANDIDATE_SIZE_RISK','PROMISING_DARK_EVIDENCE'):groups.setdefault(reason,[])
        result['by_dimension'][dimension]={k:counts(v) for k,v in sorted(groups.items())}
    return result


def query_tasks(tasks, records, *, stale=None, filters=None, sort='priority', descending=False):
    filters=filters or {}
    def matches(t):
        for key,value in filters.items():
            if value in (None,'','全部'):continue
            actual=task_status(t,records,stale) if key=='status' else (records.get(t['task_key'],{}).get('decision') if key=='decision' else t.get(key))
            if key=='reason':
                if value not in t['reasons']:return False
            elif actual!=value:return False
        return True
    def key(t):
        tie=(t['object_kind']!='DEFECT',t['task_key'])
        values={'priority':['HIGH','MEDIUM','LOW'].index(t['priority']),'status':task_status(t,records,stale),
                'area':t['geometry'].get('area_px') or 0,'id':t['object_id'],'reason':','.join(t['reasons'])}
        return (values.get(sort,values['priority']),*tie)
    return sorted((t for t in tasks if matches(t)),key=key,reverse=descending)
