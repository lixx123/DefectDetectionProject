"""Explainable admission, O(candidates + indexed geometry queries), without I/O."""
from collections import Counter, defaultdict
from types import MappingProxyType
from .model import ReviewBucket as B,ReviewPriority as P,ReviewObjectKey as K,ReviewAdmissionDecision as Decision,ReviewTask,ReviewAdmissionResult
from .policy import ReviewAdmissionConfig
from .rules import candidate_risk,has_flag,near_threshold,grade
from ui.models.audit_view_model import AuditViewModel,key


PRIORITY={P.HIGH:0,P.MEDIUM:1,P.LOW:2}


class FinalGeometryIndex:
    """BBox overlap is risk evidence only, never a claimed lineage identity."""
    def __init__(self,defects):
        self.grid=defaultdict(list);self.wide=[];self.boxes={}
        for d in defects:
            b=d.geometry.bbox
            if b is None:continue
            fid=d.identity.defect_id;self.boxes[fid]=b;cells=self.cells(b)
            if cells is None:self.wide.append(fid)
            else:
                for cell in cells:self.grid[cell].append(fid)
    @staticmethod
    def cells(b):
        xs=range(b.x0//512,(b.x1-1)//512+1);ys=range(b.y0//512,(b.y1-1)//512+1)
        if len(xs)*len(ys)>256:return None
        return tuple((x,y) for x in xs for y in ys)
    def overlaps(self,b):
        if b is None:return ()
        cells=self.cells(b)
        ids=set(self.boxes) if cells is None else set(self.wide).union(*(self.grid.get(cell,()) for cell in cells))
        return tuple(sorted(fid for fid in ids if (f:=self.boxes[fid]).x0<b.x1 and b.x0<f.x1 and f.y0<b.y1 and b.y0<f.y1))


class ReviewAdmissionEngine:
    def evaluate(self,result,config=None):
        cfg=config or ReviewAdmissionConfig()
        audit=AuditViewModel(result);spatial=FinalGeometryIndex(result.defects)
        by_final={d.identity.defect_id:d for d in result.defects}
        shared=defaultdict(set)
        for c in audit.records:
            g=c.initial_geometry;b=g.bbox if g else None
            if b:shared[(b.x0,b.y0,b.x1,b.y1)].add(c.source)
        candidate_decisions=[];promote=defaultdict(set);warnings=[];limitations=0
        for c in sorted(audit.records,key=key):
            obj=K('CANDIDATE',candidate_source=c.source,candidate_id=c.candidate_id)
            g=c.initial_geometry;b=g.bbox if g else None
            area=g.area_px if g else None;feret=g.length_px if g else None
            high,medium,promising,boundary,conflict=candidate_risk(c,cfg)
            overlaps=spatial.overlaps(b)
            coincidence=bool(b and len(shared[(b.x0,b.y0,b.x1,b.y1)])>1)
            # Matching bboxes alone do not establish independent detector support.
            multiple=coincidence and c.extensions.get('independent_source_evidence') is True
            valid=c.final_defect_id in by_final
            invalid=c.final_defect_id is not None and not valid
            duplicate=audit.by_key.get(key(c)) is None
            missing=g is None or b is None or area is None
            target=audit.merged_target(c) if c.merged_into else None
            historical_merge=(str(c.disposition)=='MERGED' and valid and c.merged_into==c.final_defect_id and not audit.by_id.get(c.merged_into))
            merge_issue=str(c.disposition)=='MERGED' and not historical_merge and (not c.merged_into or target is None)
            reverse_issue=valid and bool(audit.reverse_issues[c.final_defect_id])
            linked_conflict=valid and str(c.disposition) in ('FILTERED','PENDING')
            hard=[]
            if invalid:hard.extend(('INVALID_FINAL_LINK','LINEAGE_INCONSISTENT'))
            if duplicate or conflict or reverse_issue or linked_conflict:hard.append('LINEAGE_INCONSISTENT')
            if str(c.disposition)=='RETAINED' and c.final_defect_id is None:hard.extend(('RETAINED_WITHOUT_FINAL_LINK','LINEAGE_INCONSISTENT'))
            if target is not None and valid:
                target_record=audit.candidate(target)
                if target_record is not None and target_record.final_defect_id not in (None,c.final_defect_id):hard.append('LINEAGE_INCONSISTENT')
            if merge_issue:hard.append('MERGE_TARGET_AMBIGUOUS' if len(audit.by_id.get(c.merged_into,()))>1 else 'MERGE_TARGET_UNRESOLVED')
            if str(c.disposition)=='FILTERED' and c.filter_reason is None:hard.append('MISSING_FILTER_REASON')
            bucket=B.AUDIT_ONLY;priority=None;reasons=[]
            if hard:
                bucket=B.MANUAL_REVIEW;priority=P.HIGH;reasons.extend(hard)
            elif valid:
                reasons.append('LINKED_TO_ACCEPTED_DEFECT')
                if historical_merge:reasons.append('DATA_LIMITATION');limitations+=1
            elif str(c.disposition)=='FILTERED' and str(c.filter_reason)=='OUTSIDE_WORK_REGION' and not overlaps and not conflict and not multiple and not promising and not boundary:
                bucket=B.AUTO_REJECT;reasons.append('OUTSIDE_WORK')
            elif c.current_stage=='HISTORICAL_ARCHIVE_NOT_RESCANNED' and c.extensions.get('reference_reason_category')=='OUTSIDE_WORK_REGION':
                reasons.extend(('HISTORICAL_AUDIT_ONLY','HISTORICAL_OUTSIDE_WORK_EVIDENCE'))
            elif high or promising or medium or multiple or overlaps or boundary:
                bucket=B.MANUAL_REVIEW;priority=P.HIGH if high or promising or multiple else P.MEDIUM
                reasons.append('WEAK_EVIDENCE_HIGH_RISK')
                if high or medium:reasons.append('CANDIDATE_SIZE_RISK')
                if high:reasons.append('LARGE_CANDIDATE_GEOMETRY')
                if promising:reasons.append('PROMISING_DARK_EVIDENCE')
                if boundary:reasons.append('WORK_BOUNDARY_UNCERTAINTY')
                if multiple:reasons.append('MULTI_SOURCE_COINCIDENCE')
                if overlaps:reasons.append('SPATIAL_FINAL_ASSOCIATION')
                if c.current_stage=='FINAL_SELECTION':reasons.append('UNRESOLVED_FINAL_SELECTION')
            elif str(c.disposition)=='FILTERED' and str(c.filter_reason) in ('BACKGROUND_NOISE','LOW_EVIDENCE') and not missing:
                bucket=B.AUTO_REJECT;reasons.append('BACKGROUND_NOISE' if str(c.filter_reason)=='BACKGROUND_NOISE' else 'LOW_EVIDENCE_LOW_RISK')
            elif missing:
                bucket=B.MANUAL_REVIEW;priority=P.HIGH;reasons.append('MISSING_GEOMETRY')
                if c.current_stage=='FINAL_SELECTION':reasons.append('UNRESOLVED_FINAL_SELECTION')
            elif c.current_stage=='HISTORICAL_ARCHIVE_NOT_RESCANNED':
                reasons.append('HISTORICAL_AUDIT_ONLY')
            elif str(c.disposition)=='REVIEW' and c.current_stage=='FINAL_SELECTION' and any(has_flag(c,x) for x in ('MICRO_HIDE_SUGGESTION','MICRO_REVIEW','J5_J5_WORK_SMALL','EXISTING_FIXED_H_SHARES','DARK_SPOT_EVIDENCE_NOT_SUFFICIENT')):
                reasons.append('PROVISIONAL_LOW_RISK_AUDIT_ONLY')
            else:
                bucket=B.MANUAL_REVIEW;priority=P.LOW
                reasons.append('UNRESOLVED_FINAL_SELECTION' if c.current_stage=='FINAL_SELECTION' else 'UNRESOLVED_CANDIDATE')
            reasons=tuple(sorted(set(reasons)))
            evidence=dict(area_px=area,feret_px=feret,size_grade=None,band=None,source=c.source,current_stage=c.current_stage,
                disposition=str(c.disposition),filter_reason=str(c.filter_reason) if c.filter_reason is not None else None,
                final_defect_id=c.final_defect_id,lineage_issue_count=len(set(hard)),spatial_final_ids=overlaps,
                multi_source_coincidence=coincidence,independent_source_support=multiple,initial_geometry_available=not missing,
                reference_decision=c.extensions.get('reference_decision') if isinstance(c.extensions.get('reference_decision'),str) else None,
                reference_reason_category=c.extensions.get('reference_reason_category') if isinstance(c.extensions.get('reference_reason_category'),str) else None)
            decision=Decision(obj,bucket,priority,reasons,evidence);candidate_decisions.append(decision)
            if valid and bucket==B.MANUAL_REVIEW:promote[c.final_defect_id].update(reasons)
        defect_decisions=[]
        for d in sorted(result.defects,key=lambda d:d.identity.defect_id):
            fid=d.identity.defect_id;g=d.geometry;reasons=set(promote[fid]);high=False
            if not result.audit_log.lineage_complete or result.audit_log.source_candidate_count!=len(audit.records) or audit.reverse_issues[fid] or audit.duplicate_count:
                reasons.add('LINEAGE_INCONSISTENT');high=True
            if g.bbox is None or g.area_px is None or g.length_px is None:reasons.add('MISSING_GEOMETRY');high=True
            if near_threshold(g.area_px,g.length_px,cfg):reasons.add('NEAR_SIZE_THRESHOLD')
            if g.area_px is not None and g.length_px is not None and str(d.classification.size_grade) not in ('UNKNOWN',('SMALL','MEDIUM','LARGE')[grade(g.area_px,g.length_px)]):
                reasons.add('SIZE_GRADE_EVIDENCE_CONFLICT');high=True
            if str(d.review.review_status) in ('UNCERTAIN','FALSE_POSITIVE'):
                reasons.add('EXISTING_REVIEW_REQUIRES_ATTENTION');high=True
            if cfg.review_when_missing_photometry and d.photometry.mean_gray_dn is None:reasons.add('MISSING_PHOTOMETRY')
            if promote[fid]:high=True
            bucket=B.MANUAL_REVIEW if reasons else B.AUTO_ACCEPT
            priority=(P.HIGH if high else P.MEDIUM) if reasons else None
            if not reasons:reasons.add('FINAL_ALGORITHM_ACCEPTED')
            evidence=dict(area_px=g.area_px,feret_px=g.length_px,size_grade=str(d.classification.size_grade),band=d.location.band_id,
                source=tuple(sorted(d.detection.source_channels)),current_stage=d.detection.detection_stage,disposition=None,
                filter_reason=None,final_defect_id=fid,lineage_issue_count=len(audit.reverse_issues[fid]),
                review_status=str(d.review.review_status),photometry_available=d.photometry.mean_gray_dn is not None)
            defect_decisions.append(Decision(K('DEFECT',defect_id=fid),bucket,priority,tuple(sorted(reasons)),evidence))
        decisions=tuple(defect_decisions+candidate_decisions)
        tasks=[];unrepresented=[]
        for decision in decisions:
            if decision.bucket!=B.MANUAL_REVIEW:continue
            obj=decision.object_key;e=decision.evidence
            if obj.kind=='DEFECT':
                related=tuple(sorted(audit.candidates_for_final_defect(obj.defect_id)))
                tasks.append(ReviewTask('DEFECT:'+obj.token,'DEFECT_REVIEW',obj,related,decision.priority,decision.reasons,e))
            elif e['final_defect_id'] is None:
                tasks.append(ReviewTask('CANDIDATE:'+obj.token,'ORPHAN_CANDIDATE_REVIEW',obj,(),decision.priority,decision.reasons,e))
            elif 'INVALID_FINAL_LINK' in decision.reasons:
                tasks.append(ReviewTask('CONSISTENCY:'+obj.token,'CANDIDATE_CONSISTENCY',obj,(),P.HIGH,decision.reasons,e))
            # Valid linked candidates are evidence for the promoted Defect task.
        # Coalesce only identical identities (not image geometry, ID substrings, or top-N).
        unique={}
        for task in tasks:
            if task.task_key in unique:
                previous=unique[task.task_key]
                task=ReviewTask(task.task_key,task.task_kind,task.primary_object,task.related_candidates,
                    min((previous.priority,task.priority),key=PRIORITY.get),tuple(sorted(set(previous.reasons+task.reasons))),task.evidence)
            unique[task.task_key]=task
        tasks=tuple(sorted(unique.values(),key=lambda t:(PRIORITY[t.priority],t.primary_object)))
        counts={b.value:dict(DEFECT=0,CANDIDATE=0) for b in B}
        for decision in decisions:counts[decision.bucket][decision.object_key.kind]+=1
        audit_review=audit.dispositions['REVIEW'];manual=len(tasks);preferred_met=manual<=cfg.preferred_max_per_result
        if not preferred_met:warnings.append(f'TARGET_NOT_MET: {manual} > preferred_max {cfg.preferred_max_per_result}; 全部保留，无截断')
        if limitations:warnings.append(f'DATA_LIMITATION: {limitations} merged_into values identify final defects; valid final links retained')
        if unrepresented:warnings.append(f'UNQUEUED_INVALID_FINAL_LINK: {len(unrepresented)}; policy disables consistency tasks')
        if not result.audit_log.lineage_complete:warnings.append('LINEAGE_INCOMPLETE: stored audit chain is incomplete')
        if result.audit_log.source_candidate_count!=len(audit.records):warnings.append('SOURCE_COUNT_MISMATCH')
        summary=dict(result_id=result.result_id,final_defect_count=len(result.defects),audit_candidate_count=len(audit.records),
            audit_review_count=audit_review,bucket_counts=counts,auto_accept_count=sum(counts[B.AUTO_ACCEPT].values()),
            auto_reject_count=sum(counts[B.AUTO_REJECT].values()),manual_review_object_count=sum(counts[B.MANUAL_REVIEW].values()),
            audit_only_count=sum(counts[B.AUDIT_ONLY].values()),manual_review_task_count=manual,
            manual_review_defect_tasks=sum(t.primary_object.kind=='DEFECT' for t in tasks),
            manual_review_candidate_tasks=sum(t.primary_object.kind=='CANDIDATE' for t in tasks),
            candidate_consistency_tasks=sum(t.task_kind=='CANDIDATE_CONSISTENCY' for t in tasks),
            manual_review_priority_counts={p.value:sum(t.priority==p for t in tasks) for p in P},
            manual_review_reason_counts=dict(sorted(Counter(reason for t in tasks for reason in t.reasons).items())),
            audit_review_to_manual_task_compression_ratio=(audit_review/manual if manual else None),
            audit_review_to_manual_task_reduction_fraction=(1-manual/audit_review if audit_review else None),
            compression_definition='audit REVIEW candidates / all manual tasks (including Defect tasks); zero tasks => ratio unavailable',
            preferred_max=cfg.preferred_max_per_result,preferred_max_met=preferred_met,
            decision_count=len(decisions),unrepresented_invalid_links=tuple(unrepresented),data_limitations=limitations,
            warnings=tuple(warnings),policy_id=cfg.policy_id,policy_version=cfg.policy_version,policy_hash=cfg.policy_hash)
        return ReviewAdmissionResult(decisions,tasks,MappingProxyType(summary),tuple(warnings),cfg.policy_id,cfg.policy_version,cfg.policy_hash)
