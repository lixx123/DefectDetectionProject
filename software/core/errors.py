"""Explicit boundaries between input, engine, mapping, and quality failures."""
class InspectionError(RuntimeError):
    pass


class InputValidationError(InspectionError):
    pass


class EngineExecutionError(InspectionError):
    pass


class EngineOutputError(InspectionError):
    pass


class MappingError(InspectionError):
    pass


class ExecutionQAError(InspectionError):
    pass


class ResultQCError(InspectionError):
    pass


class InspectionCancelled(InspectionError):
    pass
