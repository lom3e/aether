"""
Aether Automation Subsystem.
Enables scheduled, triggered, and multi-agent workflow automations.
"""
from aether.automation.builder import AutomationBuilder, AutomationProposal
from aether.automation.engine import AutomationEngine
from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    AutomationSuggestion,
    OutputDestination,
    OutputType,
    PipelineStep,
    RunStatus,
    StepRunResult,
    SuggestionStatus,
    TriggerConfig,
    TriggerType,
)
from aether.automation.scheduler import AutomationScheduler
from aether.automation.store import AutomationStore
from aether.automation.suggestions import SuggestionEngine
from aether.automation.triggers import CronExpression, TriggerEvaluator
from aether.automation.watchers import (
    BaseWatcher,
    FilesystemWatcher,
    GitHubRepoWatcher,
    HttpPollingWatcher,
    WatcherManager,
)

__all__ = [
    "AutomationBuilder",
    "AutomationDefinition",
    "AutomationEngine",
    "AutomationProposal",
    "AutomationRunRecord",
    "AutomationScheduler",
    "AutomationStore",
    "AutomationSuggestion",
    "BaseWatcher",
    "CronExpression",
    "FilesystemWatcher",
    "GitHubRepoWatcher",
    "HttpPollingWatcher",
    "OutputDestination",
    "OutputType",
    "PipelineStep",
    "RunStatus",
    "StepRunResult",
    "SuggestionEngine",
    "SuggestionStatus",
    "TriggerConfig",
    "TriggerEvaluator",
    "TriggerType",
    "WatcherManager",
]
