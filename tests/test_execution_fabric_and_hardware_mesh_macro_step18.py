"""
Tests for Macro-Step 18: Local Execution Fabric & Hardware Mesh (Layer 17).
Verifies native hardware probing, SQLite persistence, execution fabric engine,
workload routing heuristics, action registry & executor, personal agent intents,
and FastAPI routes.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

import pytest
from starlette.requests import Request

from aether.actions.models import ActionExecutionStatus
from aether.actions.registry import ActionRegistry
from aether.fabric.engine import ExecutionFabricEngine, probe_native_hardware
from aether.fabric.models import (
    HardwareCapabilities,
    MeshNode,
    MeshTelemetrySnapshot,
    NodeRole,
    NodeStatus,
    WorkloadAssignment,
    WorkloadTier,
)
from aether.fabric.store import FabricStore
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    FabricHeartbeatPayload,
    RegisterFabricNodePayload,
    RouteWorkloadPayload,
    delete_fabric_node,
    fabric_node_heartbeat,
    get_fabric_node,
    get_fabric_telemetry,
    list_fabric_nodes,
    list_fabric_workloads,
    register_fabric_node,
    route_fabric_workload,
)
from aether.workspace.workspace import Workspace


@pytest.fixture
def temp_workspace(tmp_path: Path):
    ws_dir = tmp_path / "test_fabric_ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return Workspace(root=ws_dir)


class DummyAppState:
    def __init__(self, workspace: Any) -> None:
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace: Any) -> None:
        self.state = DummyAppState(workspace)


def create_dummy_request(workspace: Any, body: dict[str, Any] | None = None) -> Request:
    scope = {"type": "http", "app": DummyApp(workspace), "headers": []}
    req = Request(scope=scope)
    if body is not None:
        async def fake_json():
            return body
        req.json = fake_json  # type: ignore[method-assign]
    return req


def test_models_and_enums_roundtrip():
    """Verifies dataclass model serialization and enum conversions."""
    caps = HardwareCapabilities(
        cpu_brand="Apple M3 Max",
        cpu_cores=16,
        ram_total_gb=128.0,
        ram_free_gb=64.0,
        gpu_name="Apple M3 Max 40-core GPU",
        gpu_vram_gb=96.0,
        accelerator_type="metal",
        os_name="darwin",
        architecture="arm64",
    )
    caps_d = caps.to_dict()
    assert caps_d["cpu_cores"] == 16
    assert caps_d["accelerator_type"] == "metal"

    rehydrated = HardwareCapabilities.from_dict(caps_d)
    assert rehydrated.cpu_brand == "Apple M3 Max"
    assert rehydrated.gpu_vram_gb == 96.0

    node = MeshNode(
        id="node-test-1",
        workspace_id="ws-1",
        name="Host Alpha",
        role=NodeRole.CONTROLLER,
        status=NodeStatus.ONLINE,
        endpoint="local://",
        is_local=True,
        capabilities=caps,
        tags=["local", "controller"],
    )
    node_d = node.to_dict()
    assert node_d["role"] == "controller"
    assert node_d["status"] == "online"

    node_rev = MeshNode.from_dict(node_d)
    assert node_rev.id == "node-test-1"
    assert node_rev.capabilities.cpu_cores == 16

    assignment = WorkloadAssignment(
        id="work-1",
        workspace_id="ws-1",
        workload_name="Agent Batch",
        workload_tier=WorkloadTier.GPU_HEAVY,
        assigned_node_id="node-test-1",
        status="running",
        allocated_cores=8,
        allocated_vram_gb=24.0,
    )
    assert assignment.to_dict()["workload_tier"] == "gpu_heavy"
    rev_assign = WorkloadAssignment.from_dict(assignment.to_dict())
    assert rev_assign.allocated_vram_gb == 24.0


def test_native_hardware_probing_zero_simulation():
    """Verifies genuine host hardware inspection without mocks."""
    caps = probe_native_hardware()
    assert caps.cpu_cores > 0
    assert caps.ram_total_gb > 0
    assert caps.ram_free_gb >= 0
    assert caps.os_name in ("darwin", "linux", "win32")
    assert caps.accelerator_type in ("metal", "cuda", "cpu")
    assert len(caps.cpu_brand) > 0


def test_fabric_store_lifecycle(tmp_path: Path):
    """Verifies SQLite persistence for mesh nodes and workload allocations."""
    db_path = tmp_path / "fabric_test.db"
    store = FabricStore(db_path=db_path)

    caps = HardwareCapabilities(
        cpu_brand="Intel Xeon",
        cpu_cores=32,
        ram_total_gb=64.0,
        ram_free_gb=32.0,
        gpu_name="NVIDIA A100",
        gpu_vram_gb=80.0,
        accelerator_type="cuda",
        os_name="linux",
        architecture="x86_64",
    )

    local_node = MeshNode(
        id="local-1",
        workspace_id="ws-mesh",
        name="Local Host",
        role=NodeRole.CONTROLLER,
        status=NodeStatus.ONLINE,
        endpoint="local://",
        is_local=True,
        capabilities=caps,
    )
    store.save_node(local_node)

    remote_node = MeshNode(
        id="remote-1",
        workspace_id="ws-mesh",
        name="Remote Worker Alpha",
        role=NodeRole.WORKER,
        status=NodeStatus.ONLINE,
        endpoint="http://10.0.0.5:8000",
        is_local=False,
        capabilities=caps,
    )
    store.save_node(remote_node)

    nodes = store.list_nodes("ws-mesh")
    assert len(nodes) == 2
    assert nodes[0].is_local is True  # local node sorted first

    # Test record heartbeat
    assert store.record_heartbeat("remote-1", ping_ms=14.2, status=NodeStatus.ONLINE) is True
    updated = store.get_node("ws-mesh", "remote-1")
    assert updated is not None
    assert updated.ping_ms == 14.2

    # Local node cannot be deleted
    assert store.delete_node("ws-mesh", "local-1") is False
    # Remote node can be deleted
    assert store.delete_node("ws-mesh", "remote-1") is True
    assert len(store.list_nodes("ws-mesh")) == 1

    # Workload assignment
    w = WorkloadAssignment(
        id="w-100",
        workspace_id="ws-mesh",
        workload_name="Fine-tuning Job",
        workload_tier=WorkloadTier.GPU_HEAVY,
        assigned_node_id="local-1",
        status="running",
        allocated_cores=16,
        allocated_vram_gb=40.0,
    )
    store.save_workload_assignment(w)
    assignments = store.list_workload_assignments("ws-mesh")
    assert len(assignments) == 1
    assert assignments[0].workload_name == "Fine-tuning Job"


def test_fabric_engine_topology_and_routing(temp_workspace: Workspace):
    """Verifies ExecutionFabricEngine node management and constraint routing."""
    engine = temp_workspace.fabric_engine
    ws_id = temp_workspace.name

    # 1. Discover local host node automatically
    local_node = engine.ensure_local_node(ws_id)
    assert local_node.is_local is True
    assert local_node.role == NodeRole.CONTROLLER
    assert local_node.status == NodeStatus.ONLINE

    # 2. Register remote dedicated GPU node
    gpu_node = engine.register_remote_node(
        workspace_id=ws_id,
        name="Cluster-H100-Node",
        role=NodeRole.GPU_NODE,
        endpoint="http://10.0.1.20:8000",
        capabilities={
            "cpu_brand": "AMD EPYC 9654",
            "cpu_cores": 64,
            "ram_total_gb": 256.0,
            "ram_free_gb": 200.0,
            "gpu_name": "NVIDIA H100 80GB",
            "gpu_vram_gb": 80.0,
            "accelerator_type": "cuda",
            "os_name": "linux",
            "architecture": "x86_64",
        },
        tags=["gpu", "cuda", "h100"],
    )
    assert gpu_node.role == NodeRole.GPU_NODE

    # 3. Register background worker node
    worker_node = engine.register_remote_node(
        workspace_id=ws_id,
        name="Background-Worker-Fleet",
        role=NodeRole.WORKER,
        endpoint="http://10.0.1.30:8000",
        capabilities={
            "cpu_brand": "Intel Xeon Gold",
            "cpu_cores": 32,
            "ram_total_gb": 64.0,
            "ram_free_gb": 48.0,
            "gpu_name": "Integrated",
            "gpu_vram_gb": 0.0,
            "accelerator_type": "cpu",
            "os_name": "linux",
            "architecture": "x86_64",
        },
        tags=["worker", "batch"],
    )

    # 4. Route workloads across tiers
    # Tier: LOCAL_FAST -> should route to local controller
    w_local = engine.route_workload(
        workspace_id=ws_id,
        workload_name="Fast Interactive Chat Inference",
        tier=WorkloadTier.LOCAL_FAST,
    )
    assert w_local.assigned_node_id == local_node.id

    # Tier: GPU_HEAVY with 40GB min VRAM -> should route to H100 GPU node
    w_gpu = engine.route_workload(
        workspace_id=ws_id,
        workload_name="DeepSeek Large Model Inference",
        tier=WorkloadTier.GPU_HEAVY,
        min_vram_gb=40.0,
    )
    assert w_gpu.assigned_node_id == gpu_node.id
    assert w_gpu.allocated_vram_gb == 40.0

    # Tier: BACKGROUND_BATCH -> should route to background worker
    w_batch = engine.route_workload(
        workspace_id=ws_id,
        workload_name="Massive Dataset Ingestion",
        tier=WorkloadTier.BACKGROUND_BATCH,
        min_cores=8,
    )
    assert w_batch.assigned_node_id == worker_node.id

    # 5. Telemetry snapshot consolidation
    snapshot = engine.get_telemetry_snapshot(ws_id)
    assert snapshot.total_nodes == 3
    assert snapshot.online_nodes == 3
    assert snapshot.total_cores >= 96
    assert snapshot.total_vram_gb >= 80.0
    assert snapshot.active_workloads == 3


def test_action_registry_and_executor(temp_workspace: Workspace):
    """Verifies all 6 fabric actions registered in ActionRegistry and executed."""
    ws = temp_workspace
    ws_id = ws.name

    # Action 1: fabric.list_nodes
    res_list = ws.actions.execute("fabric.list_nodes", ws_id, {})
    assert res_list.status == ActionExecutionStatus.SUCCESS or res_list.output_data is not None
    nodes = res_list.output_data["nodes"]
    assert len(nodes) >= 1
    assert nodes[0]["is_local"] is True

    # Action 2: fabric.get_telemetry
    res_tel = ws.actions.execute("fabric.get_telemetry", ws_id, {})
    assert res_tel.output_data is not None
    snapshot = res_tel.output_data["telemetry"]
    assert snapshot["total_nodes"] >= 1
    assert snapshot["total_cores"] > 0

    # Action 3: fabric.register_node
    res_reg = ws.actions.execute("fabric.register_node", ws_id, {
        "name": "Edge-Orin-Nano",
        "role": "worker",
        "endpoint": "http://192.168.1.80:8000",
        "capabilities": {
            "cpu_brand": "ARM Cortex-A78AE",
            "cpu_cores": 6,
            "ram_total_gb": 8.0,
            "ram_free_gb": 4.0,
            "gpu_name": "NVIDIA Ampere (1024 cores)",
            "gpu_vram_gb": 8.0,
            "accelerator_type": "cuda",
            "os_name": "linux",
            "architecture": "aarch64",
        },
        "tags": ["jetson", "edge"],
    })
    assert res_reg.output_data is not None
    edge_node = res_reg.output_data["node"]
    edge_id = edge_node["id"]
    assert edge_node["name"] == "Edge-Orin-Nano"

    # Action 4: fabric.node_heartbeat
    res_hb = ws.actions.execute("fabric.node_heartbeat", ws_id, {
        "node_id": edge_id,
        "ping_ms": 5.4,
    })
    assert res_hb.output_data is not None

    # Action 5: fabric.route_workload
    res_route = ws.actions.execute("fabric.route_workload", ws_id, {
        "workload_name": "Edge Sensor Telemetry Filter",
        "tier": "background_batch",
        "min_cores": 2,
    })
    assert res_route.output_data is not None
    assert "assignment" in res_route.output_data

    # Action 6: fabric.delete_node
    res_del = ws.actions.execute("fabric.delete_node", ws_id, {
        "node_id": edge_id,
    })
    assert res_del.output_data is not None


def test_personal_agent_fabric_intents(temp_workspace: Workspace):
    """Verifies Personal Agent natural language intent parsing for hardware fabric."""
    service = temp_workspace.personal
    ws_id = temp_workspace.name

    # 1. Intent 3e37: list nodes and telemetry
    intent_tel = service.classify_intent("Show connected compute nodes and hardware mesh telemetry")
    assert intent_tel.action_id == "fabric.list_nodes"
    assert intent_tel.tier == IntentTier.ANSWER

    # 2. Intent 3e38: route workload
    intent_route = service.classify_intent("Route workload 'Speech Processing' to GPU cluster")
    assert intent_route.action_id == "fabric.route_workload"
    assert intent_route.tier == IntentTier.DO


@pytest.mark.asyncio
async def test_fastapi_fabric_routes(temp_workspace: Workspace):
    """Verifies all REST API routes for mesh nodes, telemetry, and workload routing."""
    ws = temp_workspace
    ws_id = ws.name

    # 1. List nodes
    req_list = create_dummy_request(ws)
    nodes = await list_fabric_nodes(req_list, workspace_id=ws_id)
    assert len(nodes) >= 1
    local_node_id = nodes[0]["id"]

    # 2. Register remote node
    req_reg = create_dummy_request(ws)
    payload_reg = RegisterFabricNodePayload(
        name="API-Remote-Node",
        role="gpu_node",
        endpoint="http://192.168.1.99:8000",
        capabilities={
            "cpu_brand": "AMD Ryzen 9",
            "cpu_cores": 16,
            "ram_total_gb": 64.0,
            "ram_free_gb": 32.0,
            "gpu_name": "RTX 4090",
            "gpu_vram_gb": 24.0,
            "accelerator_type": "cuda",
            "os_name": "linux",
            "architecture": "x86_64",
        },
        tags=["api", "remote", "gpu"],
    )
    reg_result = await register_fabric_node(req_reg, payload_reg, workspace_id=ws_id)
    remote_id = reg_result["id"]
    assert reg_result["name"] == "API-Remote-Node"

    # 3. Get node
    req_get = create_dummy_request(ws)
    single_node = await get_fabric_node(req_get, remote_id, workspace_id=ws_id)
    assert single_node["id"] == remote_id

    # 4. Heartbeat node
    req_hb = create_dummy_request(ws)
    hb_res = await fabric_node_heartbeat(
        req_hb,
        remote_id,
        FabricHeartbeatPayload(ping_ms=8.8),
        workspace_id=ws_id,
    )
    assert hb_res["status"] == "ok"

    # 5. Get telemetry snapshot
    req_tel = create_dummy_request(ws)
    tel_res = await get_fabric_telemetry(req_tel, workspace_id=ws_id)
    assert tel_res["total_nodes"] >= 2
    assert tel_res["online_nodes"] >= 2
    assert tel_res["total_vram_gb"] >= 24.0

    # 6. Route workload
    req_route = create_dummy_request(ws)
    route_payload = RouteWorkloadPayload(
        workload_name="API-Test-Workload",
        tier="gpu_heavy",
        min_cores=4,
        min_vram_gb=12.0,
    )
    route_res = await route_fabric_workload(req_route, route_payload, workspace_id=ws_id)
    assert route_res["workload_name"] == "API-Test-Workload"
    assert route_res["assigned_node_id"] == remote_id

    # 7. List workloads
    req_workloads = create_dummy_request(ws)
    workloads = await list_fabric_workloads(req_workloads, workspace_id=ws_id)
    assert len(workloads) >= 1
    assert workloads[0]["workload_name"] == "API-Test-Workload"

    # 8. Delete remote node
    req_del = create_dummy_request(ws)
    del_res = await delete_fabric_node(req_del, remote_id, workspace_id=ws_id)
    assert del_res["status"] == "deleted"
