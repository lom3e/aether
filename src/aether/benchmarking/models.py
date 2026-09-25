"""Data models for Workforce Benchmarking, Quality Scoring, Regression Detection, and Skill Evolution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class BenchmarkTargetType(str, Enum):
    """Target entity being evaluated."""
    AGENT = "agent"
    TEAM = "team"
    MODEL_ROUTE = "model_route"
    WORKFLOW = "workflow"


class ProposalStatus(str, Enum):
    """Status of an evolution proposal."""
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class AlertSeverity(str, Enum):
    """Severity of a detected regression."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BenchmarkMetrics:
    """Quantitative performance and quality metrics."""
    completion_rate: float = 1.0  # 0.0 to 1.0
    error_rate: float = 0.0  # 0.0 to 1.0
    avg_latency_ms: float = 1200.0
    avg_tokens_per_task: int = 1500
    quality_score: float = 85.0  # 0 to 100 (or 0.0 to 1.0)
    safety_compliance_score: float = 100.0  # 0 to 100 (or 0.0 to 1.0)
    human_intervention_rate: float = 0.05
    total_evaluations: int = 10

    def __init__(
        self,
        completion_rate: float = 1.0,
        error_rate: float = 0.0,
        avg_latency_ms: Optional[float] = None,
        latency_ms: Optional[float] = None,
        avg_tokens_per_task: Optional[int] = None,
        tokens_used: Optional[int] = None,
        quality_score: float = 85.0,
        safety_compliance_score: Optional[float] = None,
        safety_compliance: Optional[float] = None,
        human_intervention_rate: float = 0.05,
        total_evaluations: int = 10,
        **kwargs: Any,
    ):
        self.completion_rate = float(completion_rate)
        self.error_rate = float(error_rate)
        self.avg_latency_ms = float(latency_ms if latency_ms is not None else (avg_latency_ms if avg_latency_ms is not None else 1200.0))
        self.avg_tokens_per_task = int(tokens_used if tokens_used is not None else (avg_tokens_per_task if avg_tokens_per_task is not None else 1500))
        self.quality_score = float(quality_score)
        self.safety_compliance_score = float(safety_compliance if safety_compliance is not None else (safety_compliance_score if safety_compliance_score is not None else 100.0))
        self.human_intervention_rate = float(human_intervention_rate)
        self.total_evaluations = int(total_evaluations)

    def calculate_composite_score(self) -> float:
        q = self.quality_score / 100.0 if self.quality_score > 1.0 else self.quality_score
        s = self.safety_compliance_score / 100.0 if self.safety_compliance_score > 1.0 else self.safety_compliance_score
        comp = self.completion_rate
        err = self.error_rate
        score = (comp * 0.4) + (q * 0.4) + (s * 0.2) - (err * 0.3)
        return round(max(0.0, min(1.0, score)), 3)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "completion_rate": self.completion_rate,
            "error_rate": self.error_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "latency_ms": self.avg_latency_ms,
            "avg_tokens_per_task": self.avg_tokens_per_task,
            "tokens_used": self.avg_tokens_per_task,
            "quality_score": self.quality_score,
            "safety_compliance_score": self.safety_compliance_score,
            "safety_compliance": self.safety_compliance_score,
            "human_intervention_rate": self.human_intervention_rate,
            "total_evaluations": self.total_evaluations,
            "composite_score": self.calculate_composite_score(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BenchmarkMetrics:
        return cls(**data)



@dataclass
class BenchmarkRun:
    """A benchmark execution record for an agent, team, or workflow."""
    id: str = field(default_factory=lambda: f"bm-{uuid.uuid4().hex[:10]}")
    suite_name: str = "general_capability_v1"
    target_type: BenchmarkTargetType = BenchmarkTargetType.AGENT
    target_id: str = ""
    target_name: str = ""
    metrics: BenchmarkMetrics = field(default_factory=BenchmarkMetrics)
    overall_score: float = 85.0
    status: str = "completed"  # running, completed, failed
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["target_type"] = self.target_type.value if isinstance(self.target_type, BenchmarkTargetType) else self.target_type
        data["metrics"] = self.metrics.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BenchmarkRun:
        copied = dict(data)
        if "target_type" in copied and isinstance(copied["target_type"], str):
            copied["target_type"] = BenchmarkTargetType(copied["target_type"])
        if "metrics" in copied and isinstance(copied["metrics"], dict):
            copied["metrics"] = BenchmarkMetrics.from_dict(copied["metrics"])
        return cls(**copied)


@dataclass
class EvolutionProposal:
    """An automated optimization proposal for an agent's prompts, tools, or routing."""
    id: str = field(default_factory=lambda: f"evo-{uuid.uuid4().hex[:10]}")
    target_agent: str = ""
    benchmark_run_id: str = ""
    title: str = "Optimize System Prompt for Deterministic Tool Execution"
    rationale: str = ""
    suggested_prompt_addition: str = ""
    suggested_preferred_model: Optional[str] = None
    expected_quality_delta: float = 5.0
    status: ProposalStatus = ProposalStatus.PENDING
    applied_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value if isinstance(self.status, ProposalStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EvolutionProposal:
        copied = dict(data)
        if "status" in copied and isinstance(copied["status"], str):
            copied["status"] = ProposalStatus(copied["status"])
        return cls(**copied)


@dataclass
class RegressionAlert:
    """An alert triggered when benchmark metrics degrade below safety thresholds."""
    id: str = field(default_factory=lambda: f"alt-{uuid.uuid4().hex[:10]}")
    benchmark_run_id: str = ""
    target_id: str = ""
    metric_name: str = "error_rate"
    baseline_value: float = 0.05
    current_value: float = 0.22
    delta_percentage: float = 340.0
    severity: AlertSeverity = AlertSeverity.HIGH
    message: str = "Error rate increased by 340% compared to baseline."
    resolved: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value if isinstance(self.severity, AlertSeverity) else self.severity
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RegressionAlert:
        copied = dict(data)
        if "severity" in copied and isinstance(copied["severity"], str):
            copied["severity"] = AlertSeverity(copied["severity"])
        return cls(**copied)
