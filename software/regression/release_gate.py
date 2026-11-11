"""Explicit release decision. Missing real evidence can never become PASS."""
def release_decision(*,fast_status,golden_status,repository_status,schema_status,
                     auto_status,protection_status,real_required=False,real_executed=False,real_status='NOT_RUN'):
    statuses=(fast_status,golden_status,repository_status,schema_status,auto_status,protection_status)
    if any(status not in ('PASS','PASS_WITH_WARNINGS') for status in statuses): return 'FAIL'
    if real_status=='FAIL' and (real_required or real_executed): return 'FAIL'
    if real_required and (not real_executed or real_status=='NOT_RUN'): return 'NOT_COMPLETE'
    if real_required and real_status not in ('PASS','PASS_WITH_WARNINGS'): return 'FAIL'
    return 'PASS_WITH_WARNINGS' if 'PASS_WITH_WARNINGS' in statuses or real_required and real_status=='PASS_WITH_WARNINGS' else 'PASS'
