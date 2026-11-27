"""Shared minute-profile costing for the native and compatibility planners."""
try:
    from ..legacy.minute_profile import segments
except ImportError:  # Dependency-free planner tools import optimizer at top level.
    from legacy.minute_profile import segments

__all__ = ['segments']
