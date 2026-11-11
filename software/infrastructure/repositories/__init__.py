"""Public repository API; lazy exports keep storage utilities independently usable."""
__all__ = ['JsonResultRepository','ResultRepository','ResultSummary','SaveRecord',
           'VerificationReport','RebuildReport','ExportRecord']


def __getattr__(name):
    if name == 'JsonResultRepository':
        from .json_repository import JsonResultRepository
        return JsonResultRepository
    if name == 'ResultRepository':
        from .base import ResultRepository
        return ResultRepository
    if name in __all__:
        from . import models
        return getattr(models,name)
    raise AttributeError(name)
