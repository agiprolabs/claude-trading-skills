"""Documented public client contracts for FXMacroData integrations."""
from .client import FXMacroDataClient, FXMacroDataError, Operation, Result, list_operations
from .pagination import IncompleteHistoryError, DatasetChangedError
from .research import align_macro, macro_events, macro_updates, prepare_events, PointInTimeError

__all__ = ["FXMacroDataClient", "FXMacroDataError", "Operation", "Result", "list_operations",
           "IncompleteHistoryError", "DatasetChangedError", "align_macro", "macro_events",
           "macro_updates", "prepare_events", "PointInTimeError"]
