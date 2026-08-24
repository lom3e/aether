"""
Aether Automation Subsystem.
Enables scheduled, triggered, and multi-agent workflow automations.
"""
from aether.automation.engine import AutomationEngine
from aether.automation.models import (
    AutomationDefinition,
    AutomationRunRecord,
    OutputDestination,
    OutputType,
    PipelineStep,
    RunStatus,
    StepRunResult,
    TriggerConfig,
    TriggerType,
)
from aether.automation.scheduler import AutomationScheduler
from aether.automation.store import AutomationStore
from aether.automation.triggers import CronExpression, TriggerEvaluator

__all__ = [
    "AutomationDefinition",
    "AutomationEngine",
    "AutomationRunRecord",
    "AutomationScheduler",
    "AutomationStore",
    "CronExpression",
    "OutputDestination",
    "OutputType",
    "PipelineStep",
    "RunStatus",
    "StepRunResult",
    "TriggerConfig",
    "TriggerEvaluator",
    "TriggerType",
]
