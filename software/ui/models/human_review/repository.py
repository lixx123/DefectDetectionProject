"""Atomic, locked, checksummed review state, independent of result packages."""
from contextlib import contextmanager
from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from uuid import UUID,uuid4
import csv
import json
import os
import re
import tempfile
from .model import (PROTOCOL,POLICY_HASH,HumanReviewRecord,HumanReviewDecision,canonical,digest,now,
                    privacy,allowed_decisions,latest,mismatch,summary)

class ReviewError(ValueError):pass
class ReviewConflict(ReviewError):pass


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',value):raise ReviewError('unsafe identifier')
    return value


def reviewer(value):
    if not isinstance(value,str) or not value.strip() or len(value)>160:raise ReviewError('reviewer必填且最多160字')
    privacy(value);return value.strip()


def zoned(value):
    try:
        if datetime.fromisoformat(value).utcoffset() is None:raise ValueError()
    except (TypeError,ValueError):raise ReviewError('timestamp必须包含时区') from None


class HumanReviewRepository:
    def __init__(self,root):self.root=Path(root).resolve()

    def _dir(self,result_id):
        directory=self.root/identifier(result_id)
        if directory.is_symlink() or (directory.exists() and directory.resolve().parent!=self.root):raise ReviewError('unsafe review directory')
        return directory

    @contextmanager
    def _lock(self,result_id):
        directory=self._dir(result_id);directory.mkdir(parents=True,exist_ok=True)
        path=directory/'.review.lock'
        if path.is_symlink():raise ReviewError('unsafe lock')
        with path.open('a+b') as stream:
            stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
            try:yield
            finally:
                stream.seek(0)
                if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
                else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

    def _atomic(self,path,data):
        if path.is_symlink():raise ReviewError('unsafe destination')
        payload=(canonical(data)+'\n').encode('utf-8');temp=None
        try:
            fd,temp=tempfile.mkstemp(prefix='.review-',suffix='.tmp',dir=path.parent)
            with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path);temp=None
        finally:
            if temp is not None:Path(temp).unlink(missing_ok=True)

    def _write(self,state):
        self.validate(state)
        self._atomic(self._dir(state['result_id'])/(state['session_id']+'.json'),dict(checksum=digest(state),state=state))

    @staticmethod
    def validate(state):
        try:
            privacy(state)
            if state['protocol_version']!=PROTOCOL:raise ReviewError('unknown review protocol')
            identifier(state['result_id']);UUID(state['session_id']);reviewer(state['reviewer'])
            zoned(state['started_at']);zoned(state['updated_at'])
            if not re.fullmatch('[0-9a-f]{64}',state['source_result_digest']) or not re.fullmatch('[0-9a-f]{64}',state['policy_hash']):raise ReviewError('invalid digest')
            tasks={t['task_key']:t for t in state['tasks']}
            if len(tasks)!=len(state['tasks']) or len(tasks)!=state['task_count'] or digest(state['tasks'])!=state['task_digest']:raise ReviewError('task snapshot corrupt')
            revisions={};ids=set()
            for t in tasks.values():
                if t['object_kind'] not in ('DEFECT','CANDIDATE') or t['object_key'][0]!=t['object_kind']:raise ReviewError('invalid object key')
                if t['object_kind']=='CANDIDATE' and (not t['object_key'][2] or not t['object_key'][3]):raise ReviewError('Candidate source required')
                if t['priority'] not in ('HIGH','MEDIUM','LOW'):raise ReviewError('invalid priority')
            for r in state['records']:
                UUID(r['review_record_id'])
                if r['review_record_id'] in ids:raise ReviewError('duplicate record UUID')
                ids.add(r['review_record_id']);t=tasks[r['review_task_key']]
                for k in ('result_id','policy_id','policy_version','policy_hash','source_result_digest','task_digest'):
                    if r[k]!=state[k]:raise ReviewError('record binding mismatch: '+k)
                if r['object_key']!=t['object_key'] or r['object_kind']!=t['object_kind'] or r['geometry_evidence']!=t['geometry']:raise ReviewError('object snapshot mismatch')
                HumanReviewRepository._decision(t,r['decision'],r['target_defect_id'],state['final_ids'])
                reviewer(r['reviewer']);zoned(r['reviewed_at'])
                if r['comment'] is not None and (not isinstance(r['comment'],str) or len(r['comment'])>10000):raise ReviewError('invalid comment')
                key=t['task_key'];expected=revisions.get(key,0)+1
                if type(r['revision']) is not int or r['revision']!=expected:raise ReviewError('revision sequence broken')
                revisions[key]=expected
            if not state['events'] or state['events'][0]['event']!='CREATE_SESSION':raise ReviewError('missing session audit')
            for event in state['events']:zoned(event['at'])
        except (KeyError,TypeError,ValueError,IndexError) as exc:
            if isinstance(exc,ReviewError):raise
            raise ReviewError('审核数据损坏或协议非法: '+str(exc)) from exc

    @staticmethod
    def _decision(task,decision,target,final_ids):
        try:decision=HumanReviewDecision(decision)
        except ValueError:raise ReviewError('illegal decision') from None
        if decision not in allowed_decisions(task['object_kind']):raise ReviewError('Defect禁止NEW_MISSED_DEFECT')
        if decision==HumanReviewDecision.DUPLICATE_OF_EXISTING_DEFECT:
            if not target or target not in final_ids:raise ReviewError('duplicate target必须是现有Defect')
            if task['object_kind']=='DEFECT' and target==task['object_id']:raise ReviewError('duplicate target不能是自身')
        elif target is not None:raise ReviewError('只有DUPLICATE允许target')

    def load(self,result_id,session_id=None):
        directory=self._dir(result_id)
        if session_id is None:
            pointer=directory/'active.json'
            if not pointer.exists():return None
            if pointer.is_symlink():raise ReviewError('unsafe active pointer')
            try:session_id=json.loads(pointer.read_text(encoding='utf-8'))['session_id']
            except (ValueError,KeyError):raise ReviewError('active pointer corrupt') from None
        identifier(session_id);path=directory/(session_id+'.json')
        if path.is_symlink():raise ReviewError('unsafe session path')
        try:
            envelope=json.loads(path.read_text(encoding='utf-8'));state=envelope['state']
            if digest(state)!=envelope['checksum']:raise ReviewError('审核文件校验失败')
            self.validate(state)
            if state['result_id']!=result_id or state['session_id']!=session_id:raise ReviewError('session identity mismatch')
            return state
        except (ValueError,KeyError,OSError) as exc:
            if isinstance(exc,ReviewError):raise
            raise ReviewError('审核文件无法读取: '+str(exc)) from exc

    @staticmethod
    def _require_access(context,*,submit=False):
        from .evidence import ReviewAccess
        if not isinstance(context.access,ReviewAccess):raise ReviewConflict("TEMPORARY_RESULT: formal binding required")
        context.access.require(context,submit=submit)

    def create(self,context,reviewer_name,*,new_session=False):
        self._require_access(context)
        name=reviewer(reviewer_name)
        if context.policy_hash!=POLICY_HASH:raise ReviewError('POLICY_MISMATCH')
        with self._lock(context.result_id):
            old=self.load(context.result_id)
            if old is not None and not new_session:return old
            stamp=now()
            state=dict(protocol_version=PROTOCOL,session_id=str(uuid4()),result_id=context.result_id,reviewer=name,
                started_at=stamp,updated_at=stamp,policy_id=context.policy_id,policy_version=context.policy_version,
                policy_hash=context.policy_hash,source_result_digest=context.source_result_digest,task_digest=context.task_digest,
                task_count=len(context.tasks),tasks=context.tasks,final_ids=list(context.final_ids),records=[],
                events=[dict(event='CREATE_SESSION',at=stamp,reviewer=name)])
            self._write(state)
            self._atomic(self._dir(context.result_id)/'active.json',dict(session_id=state['session_id']))
            return state

    def submit(self,context,session_id,task_key,decision,reviewer_name,*,selected_task_key,expected_revision,
               target_defect_id=None,comment=None,acknowledge_previous_reviewer=False,acknowledge_special=False,guard=None):
        self._require_access(context,submit=True)
        name=reviewer(reviewer_name)
        if task_key!=selected_task_key:raise ReviewConflict('selected task identity changed')
        with self._lock(context.result_id):
            self._require_access(context,submit=True)
            if guard:guard()
            active=self.load(context.result_id)
            if active is None or active['session_id']!=session_id:raise ReviewConflict('active session changed')
            state=active;problem=mismatch(state,context)
            if problem:raise ReviewConflict(problem)
            tasks={t['task_key']:t for t in state['tasks']}
            if task_key not in tasks:raise ReviewConflict('task not in frozen session')
            previous=latest(state).get(task_key);revision=previous['revision'] if previous else 0
            if expected_revision!=revision:raise ReviewConflict('revision conflict; reload first')
            if previous and previous['reviewer']!=name and not acknowledge_previous_reviewer:raise ReviewConflict('另一审核者已有结论，需明确确认追加revision')
            self._decision(tasks[task_key],decision,target_defect_id,state['final_ids'])
            if decision in ('DUPLICATE_OF_EXISTING_DEFECT','NEW_MISSED_DEFECT') and not acknowledge_special:raise ReviewError('请明确确认重复目标或新增漏检语义')
            stamp=now();task=tasks[task_key]
            record=HumanReviewRecord(str(uuid4()),context.result_id,task_key,task['object_kind'],tuple(task['object_key']),
                str(decision),target_defect_id,name,stamp,comment,context.policy_id,context.policy_version,context.policy_hash,
                context.source_result_digest,context.task_digest,revision+1,canonical(task['geometry'])).to_dict()
            before=summary(state)['pending'];state['records'].append(record);state['updated_at']=stamp
            state['events'].append(dict(event='REVISE_REVIEW' if previous else 'SUBMIT_REVIEW',at=stamp,reviewer=name,
                                        review_record_id=record['review_record_id'],review_task_key=task_key,revision=revision+1))
            if before and summary(state)['pending']==0:state['events'].append(dict(event='COMPLETE_SESSION',at=stamp,reviewer=name))
            self._write(state)
            return state

    def export(self,state,path,format):
        self.validate(state);path=Path(path)
        if format=='json':self._atomic(path,dict(state=state,summary=summary(state)));return
        if format!='csv':raise ReviewError('only CSV / JSON supported')
        # Derived export; state remains authoritative. Quote formula-like free text.
        fields=['result_id','review_task_key','object_kind','source','object_id','priority','admission_reasons','human_decision',
                'target_defect_id','reviewer','reviewed_at','comment','revision']
        rows=[];records=latest(state)
        for t in state['tasks']:
            r=records.get(t['task_key'],{});row=dict(result_id=state['result_id'],review_task_key=t['task_key'],object_kind=t['object_kind'],
                source=t['source'],object_id=t['object_id'],priority=t['priority'],admission_reasons=';'.join(t['reasons']),
                human_decision=r.get('decision','PENDING'),**{k:r.get(k,'') for k in fields[8:]})
            rows.append({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
        import io
        text=io.StringIO(newline='');writer=csv.DictWriter(text,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        temp=None
        try:
            fd,temp=tempfile.mkstemp(prefix='.export-',dir=path.parent)
            with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as stream:stream.write(text.getvalue());stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path);temp=None
        finally:
            if temp:Path(temp).unlink(missing_ok=True)
