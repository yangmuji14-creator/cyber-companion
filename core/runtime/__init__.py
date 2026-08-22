"""Runtime lifecycle utilities shared by application components."""

from .tasks import BackgroundTaskManager
from .metrics import RuntimeMetrics, runtime_metrics
from .paths import RuntimePaths, bootstrap_example_config, ensure_user_directories, resolve_runtime_paths
from .commands import resolve_runtime_command
from .diagnostics import run_diagnostics, sanitize_settings

__all__ = [
    "BackgroundTaskManager", "RuntimeMetrics", "runtime_metrics",
    "RuntimePaths", "resolve_runtime_paths", "ensure_user_directories",
    "bootstrap_example_config", "resolve_runtime_command",
    "run_diagnostics", "sanitize_settings",
]
