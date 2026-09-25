"""
Domain models for Aether Local Execution Fabric & Hardware Mesh (Layer 17).
Defines compute nodes, hardware capabilities, workload tiers, and telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import uuid


class NodeRole(StrEnum):
    CONTROLLER = "controller"      # Main orchestrator / desktop host
    WORKER = "worker"              # Background batch worker / daemon
    GPU_NODE = "gpu_node"          # High-performance inference / CUDA node
    CLOUD_GATEWAY = "cloud_gateway" # Cloud offload proxy / remote agent

    @classmethod
    def from_str(cls, val: str) -> NodeRole:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.WORKER


class NodeStatus(StrEnum):
    ONLINE = "online"
    BUSY = "busy"
    DRAINING = "draining"
    OFFLINE = "offline"

    @classmethod
    def from_str(cls, val: str) -> NodeStatus:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.OFFLINE


class WorkloadTier(StrEnum):
    LOCAL_FAST = "local_fast"          # Light planning, low-latency reasoning
    GPU_HEAVY = "gpu_heavy"            # Heavy embeddings, vision, 70B+ LLM inference
    BACKGROUND_BATCH = "background_batch" # Watchers, web scraping, content pipelines
    CLOUD_OFFLOAD = "cloud_offload"    # Cloud API scale-out, massive synthesis

    @classmethod
    def from_str(cls, val: str) -> WorkloadTier:
        try:
            return cls(val.lower().strip())
        except ValueError:
            return cls.LOCAL_FAST


@dataclass(slots=True)
class HardwareCapabilities:
    """Hardware specification and resource metrics for a compute node."""
    cpu_brand: str
    cpu_cores: int
    ram_total_gb: float
    ram_free_gb: float = 0.0
    gpu_name: str = "Integrated"
    gpu_vram_gb: float = 0.0
    accelerator_type: str = "cpu"  # 'metal', 'cuda', 'rocm', 'cpu'
    os_name: str = "darwin"
    architecture: str = "arm64"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_brand": self.cpu_brand,
            "cpu_cores": self.cpu_cores,
            "ram_total_gb": round(self.ram_total_gb, 1),
            "ram_free_gb": round(self.ram_free_gb, 1),
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": round(self.gpu_vram_gb, 1),
            "accelerator_type": self.accelerator_type,
            "os_name": self.os_name,
            "architecture": self.architecture,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HardwareCapabilities:
        return cls(
            cpu_brand=data.get("cpu_brand") or "Generic CPU",
            cpu_cores=int(data.get("cpu_cores", 1)),
            ram_total_gb=float(data.get("ram_total_gb", 16.0)),
            ram_free_gb=float(data.get("ram_free_gb", 8.0)),
            gpu_name=data.get("gpu_name") or "Integrated",
            gpu_vram_gb=float(data.get("gpu_vram_gb", 0.0)),
            accelerator_type=data.get("accelerator_type") or "cpu",
            os_name=data.get("os_name") or "unknown",
            architecture=data.get("architecture") or "x86_64",
        )


@dataclass(slots=True)
class MeshNode:
    """A registered compute node in the Aether Execution Fabric."""
    id: str
    workspace_id: str
    name: str
    role: NodeRole
    status: NodeStatus
    endpoint: str = "local://"
    is_local: bool = True
    capabilities: HardwareCapabilities = field(
        default_factory=lambda: HardwareCapabilities(cpu_brand="Local CPU", cpu_cores=4, ram_total_gb=16.0)
    )
    tags: list[str] = field(default_factory=list)
    ping_ms: float = 0.0
    active_workloads: int = 0
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "role": self.role.value if isinstance(self.role, NodeRole) else str(self.role),
            "status": self.status.value if isinstance(self.status, NodeStatus) else str(self.status),
            "endpoint": self.endpoint,
            "is_local": self.is_local,
            "capabilities": self.capabilities.to_dict(),
            "tags": self.tags,
            "ping_ms": round(self.ping_ms, 2),
            "active_workloads": self.active_workloads,
            "last_heartbeat": self.last_heartbeat,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MeshNode:
        caps_raw = data.get("capabilities") or {}
        caps = HardwareCapabilities.from_dict(caps_raw)
        return cls(
            id=data.get("id") or f"node-{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            name=data.get("name", "Compute Node"),
            role=NodeRole.from_str(data.get("role", "worker")),
            status=NodeStatus.from_str(data.get("status", "online")),
            endpoint=data.get("endpoint", "local://"),
            is_local=bool(data.get("is_local", True)),
            capabilities=caps,
            tags=list(data.get("tags") or []),
            ping_ms=float(data.get("ping_ms", 0.0)),
            active_workloads=int(data.get("active_workloads", 0)),
            last_heartbeat=data.get("last_heartbeat") or datetime.now(timezone.utc).isoformat(),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class WorkloadAssignment:
    """An active or completed assignment of a workload to a mesh node."""
    id: str
    workspace_id: str
    workload_name: str
    workload_tier: WorkloadTier
    assigned_node_id: str
    status: str = "running"  # 'running', 'completed', 'failed'
    allocated_cores: int = 1
    allocated_vram_gb: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "workload_name": self.workload_name,
            "workload_tier": self.workload_tier.value if isinstance(self.workload_tier, WorkloadTier) else str(self.workload_tier),
            "assigned_node_id": self.assigned_node_id,
            "status": self.status,
            "allocated_cores": self.allocated_cores,
            "allocated_vram_gb": round(self.allocated_vram_gb, 1),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkloadAssignment:
        return cls(
            id=data.get("id") or f"work-{uuid.uuid4().hex[:8]}",
            workspace_id=data.get("workspace_id", "default"),
            workload_name=data.get("workload_name", "General Workload"),
            workload_tier=WorkloadTier.from_str(data.get("workload_tier", "local_fast")),
            assigned_node_id=data.get("assigned_node_id", "local-node"),
            status=data.get("status", "running"),
            allocated_cores=int(data.get("allocated_cores", 1)),
            allocated_vram_gb=float(data.get("allocated_vram_gb", 0.0)),
            created_at=data.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )


@dataclass(slots=True)
class MeshTelemetrySnapshot:
    """Aggregated real-time hardware telemetry across all connected nodes."""
    workspace_id: str
    total_nodes: int
    online_nodes: int
    total_cores: int
    total_ram_gb: float
    total_vram_gb: float
    active_workloads: int
    nodes: list[MeshNode] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "total_nodes": self.total_nodes,
            "online_nodes": self.online_nodes,
            "total_cores": self.total_cores,
            "total_ram_gb": round(self.total_ram_gb, 1),
            "total_vram_gb": round(self.total_vram_gb, 1),
            "active_workloads": self.active_workloads,
            "nodes": [n.to_dict() for n in self.nodes],
            "timestamp": self.timestamp,
        }
