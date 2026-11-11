"""Read-only audit indexes. Keys always include source; no resource I/O here."""
from collections import Counter, defaultdict
from dataclasses import dataclass


def value(item):
    return None if item is None else str(item)


def key(record):
    return record.source, record.candidate_id


@dataclass(frozen=True)
class AuditQuery:
    disposition: str | None = None
    reason: str | None = None
    source: str | None = None
    stage: str | None = None
    linked: bool | None = None
    search: str = ''
    final_id: str | None = None
    sort_column: int = 1
    descending: bool = False


class AuditViewModel:
    def __init__(self, result):
        self.result = result
        self.records = tuple(result.audit_log.candidates)  # immutable references, no record copies
        self.by_key, self.by_id, self.by_final = {}, defaultdict(list), defaultdict(list)
        self.dispositions = dict.fromkeys(('PENDING','RETAINED','FILTERED','MERGED','REVIEW'), 0)
        self.reasons, self.sources, self.stages = Counter(), Counter(), Counter()
        self.issues = []
        self.duplicate_count = self.invalid_links = self.ambiguous_targets = 0
        self.unresolved_targets = 0
        self.final_ids = {d.identity.defect_id for d in result.defects}
        for i, c in enumerate(self.records):
            if key(c) in self.by_key:
                self.duplicate_count += 1
                self.issues.append(f'重复 CandidateKey：{key(c)}')
                self.by_key[key(c)] = None  # fail closed rather than select one duplicate
            else:
                self.by_key[key(c)] = i
            self.by_id[c.candidate_id].append(i)
            self.dispositions[str(c.disposition)] += 1
            self.sources[c.source] += 1
            self.stages[c.current_stage] += 1
            if str(c.disposition) == 'FILTERED':
                self.reasons[value(c.filter_reason)] += 1
                if c.filter_reason is None:
                    self.issues.append(f'协议异常：FILTERED 缺少 FilterReason：{key(c)}')
            if str(c.disposition) == 'MERGED' and not c.merged_into:
                self.issues.append(f'协议异常：MERGED 缺少目标：{key(c)}')
            if c.final_defect_id:
                self.by_final[c.final_defect_id].append(i)
                if c.final_defect_id not in self.final_ids:
                    self.invalid_links += 1
                    self.issues.append(f'最终疵病不存在：{key(c)} → {c.final_defect_id}')
        for c in self.records:
            if c.merged_into and len(self.by_id.get(c.merged_into, ())) != 1:
                self.unresolved_targets += 1
                if len(self.by_id.get(c.merged_into, ())) > 1:
                    self.ambiguous_targets += 1
                self.issues.append(f'目标候选无法唯一解析：{key(c)} → {c.merged_into}')
        if result.audit_log.source_candidate_count != len(self.records):
            self.issues.append('来源候选声明数量与实际审计记录数不一致')
        if not result.audit_log.lineage_complete:
            self.issues.append('来源候选审计链不完整，本结果不应被视为完整正式审计记录。')
        if self.dispositions['PENDING']:
            self.issues.append(f"仍有 {self.dispositions['PENDING']} 条 PENDING 候选")
        self.reverse_issues = {}
        for d in result.defects:
            issues = []
            fid = d.identity.defect_id
            declared = set(d.detection.candidate_ids)
            for cid in declared:
                rows = self.by_id.get(cid, ())
                if len(rows) > 1:
                    issues.append(f'无法唯一反向匹配：{cid}')
                elif not rows:
                    issues.append(f'反向来源候选不存在：{cid}')
                elif self.records[rows[0]].final_defect_id != fid:
                    issues.append(f'反向来源关联不一致：{cid}')
            for row in self.by_final.get(fid, ()):
                if self.records[row].candidate_id not in declared:
                    issues.append(f'最终疵病未声明关联候选：{key(self.records[row])}')
            self.reverse_issues[fid] = issues
            self.issues.extend(f'{fid}：{issue}' for issue in issues)

    def candidate(self, candidate_key):
        row = self.by_key.get(candidate_key)
        return None if row is None else self.records[row]

    def merged_target(self, c):
        rows = self.by_id.get(c.merged_into, ())
        if len(rows) != 1:
            return None
        target = self.records[rows[0]]
        return key(target) if self.by_key.get(key(target)) is not None else None

    def candidates_for_final_defect(self, fid):
        return tuple(key(self.records[i]) for i in self.by_final.get(fid, ()))

    def summary(self):
        linked = sum(len(rows) for rows in self.by_final.values())
        return dict(result_id=self.result.result_id, candidate_count=len(self.records),
            source_candidate_count=self.result.audit_log.source_candidate_count,
            lineage_complete=self.result.audit_log.lineage_complete,
            disposition_counts=self.dispositions, filter_reason_counts={value(k) if k is not None else 'MISSING_REASON':v for k,v in self.reasons.items()},
            source_counts=dict(self.sources), stage_counts={k if k is not None else '—':v for k,v in self.stages.items()},
            linked_to_final_count=linked, unlinked_count=len(self.records)-linked,
            final_defect_count=len(self.final_ids), reverse_lineage_defects_checked=len(self.final_ids),
            candidate_key_duplicate_count=self.duplicate_count, invalid_final_defect_links=self.invalid_links,
            ambiguous_merged_targets=self.ambiguous_targets, unresolved_merged_targets=self.unresolved_targets,
            consistency_issues=list(self.issues))

    def query(self, q):
        search = q.search.casefold()
        indexes = []
        for i, c in enumerate(self.records):
            if q.disposition is not None and str(c.disposition) != q.disposition: continue
            if q.reason is not None and value(c.filter_reason) != q.reason: continue
            if q.source is not None and c.source != q.source: continue
            if q.stage is not None and (c.current_stage or '—') != q.stage: continue
            if q.linked is not None and bool(c.final_defect_id) != q.linked: continue
            if q.final_id is not None and c.final_defect_id != q.final_id: continue
            if search and search not in c.candidate_id.casefold(): continue
            indexes.append(i)
        def sort_key(i):
            c = self.records[i]
            g = c.initial_geometry
            fields = (i, c.candidate_id, c.source, c.current_stage, str(c.disposition), value(c.filter_reason),
                      c.merged_into, c.final_defect_id, g.area_px if g else None, g.length_px if g else None)
            v = fields[q.sort_column]
            return (v is None, v if v is not None else '', key(c), i)
        indexes.sort(key=sort_key, reverse=q.descending)
        return tuple(indexes)

    def execution_attempts(self):
        return self.result.execution_info.attempts
