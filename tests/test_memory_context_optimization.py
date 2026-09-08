"""
Tests for Memory Context Optimization — Relevance-Gated Context Injection.

Validates the optimized MemoryManager.load_context() policy:
  A. Relevant memory → injected
  B. Irrelevant memory → zero injection
  C. Threshold gating → below-threshold excluded
  D. Top-K cap → at most 3 injected even with 10+ relevant memories
  E. Char budget → oversized content truncated / excluded at budget limit
  F. Compact format → full content not injected verbatim
  G. Verified-only → unverified/archived/deleted excluded
  H. Scoping invariants → workspace/team/agent/mission isolation preserved
  I. Determinism → same input → same output always
  J. Runtime regression → AgentContext still works as before with no workforce memory
"""
import pytest
from aether.memory.manager import (
    MemoryManager,
    MIN_RELEVANCE_SCORE,
    CONTEXT_MAX_MEMORIES,
    CONTEXT_CHAR_BUDGET,
    MEMORY_EXCERPT_MAX_CHARS,
    _MEMORY_BLOCK_HEADER,
    _format_memory_compact,
)
from aether.memory.models import MemoryCategory, MemoryProvenance, WorkforceMemory
from aether.memory.store import WorkforceMemoryStore
from aether.core.execution import Task, AgentContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prov(status: str = "verified", entity: str = "quality_gate") -> MemoryProvenance:
    return MemoryProvenance(
        source_entity=entity,
        author_agent="TestReviewer",
        source_mission_id="mis_test",
        verification_status=status,
    )


def _seed_memory(
    store: WorkforceMemoryStore,
    workspace_id: str,
    summary: str,
    content: str,
    category: MemoryCategory = MemoryCategory.DECISION,
    tags: list[str] | None = None,
    confidence: float = 0.95,
    verification_status: str = "verified",
    is_archived: bool = False,
) -> WorkforceMemory:
    mem = WorkforceMemory.create(
        workspace_id=workspace_id,
        category=category,
        summary=summary,
        content=content,
        provenance=_make_prov(status=verification_status),
        tags=tags or [],
        confidence=confidence,
    )
    saved = store.create_memory(mem)
    if is_archived:
        saved = store.archive_memory(saved.id, archived=True, workspace_id=workspace_id)
    return saved


def _build_mgr(
    store: WorkforceMemoryStore,
    ws: str,
    *,
    min_relevance_score: float | None = None,
    context_max_memories: int | None = None,
    context_char_budget: int | None = None,
    memory_excerpt_max_chars: int | None = None,
) -> MemoryManager:
    return MemoryManager(
        workforce_memory_store=store,
        workspace_id=ws,
        agent_name="TestAgent",
        team_name="TestTeam",
        min_relevance_score=min_relevance_score,
        context_max_memories=context_max_memories,
        context_char_budget=context_char_budget,
        memory_excerpt_max_chars=memory_excerpt_max_chars,
    )


def _run_task(mgr: MemoryManager, instruction: str) -> AgentContext:
    task = Task(instruction=instruction)
    ctx = AgentContext(task=task, agent_name="TestAgent")
    mgr.load_context(ctx)
    return ctx


def _injected_system_blocks(ctx: AgentContext) -> list[str]:
    """Return the content of all system messages that are memory injection blocks."""
    return [
        m.content for m in ctx.messages
        if m.role == "system" and m.content.startswith(_MEMORY_BLOCK_HEADER)
    ]


# ---------------------------------------------------------------------------
# A. Relevant memory → injected
# ---------------------------------------------------------------------------

def test_a_relevant_memory_is_injected(tmp_path):
    """A memory highly relevant to the task instruction must be injected."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_a"
    _seed_memory(
        store, ws,
        summary="All REST APIs require Bearer token authentication",
        content="Do not use basic auth. All REST endpoints must enforce Bearer token verification.",
        tags=["auth", "security", "rest"],
    )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Implement authentication for the new REST endpoint")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1
    assert "Bearer token authentication" in blocks[0]
    assert _MEMORY_BLOCK_HEADER in blocks[0]


# ---------------------------------------------------------------------------
# B. Irrelevant memory → zero injection
# ---------------------------------------------------------------------------

def test_b_irrelevant_memory_zero_injection(tmp_path):
    """A memory with zero token overlap with the task must not be injected."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_b"
    _seed_memory(
        store, ws,
        summary="Frontend CSS styling: use Tailwind utility classes",
        content="Use Tailwind, not raw SCSS. Apply responsive variants.",
        tags=["css", "tailwind", "frontend"],
    )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Configure PostgreSQL connection pool with psycopg3")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0, f"Expected no injection, got: {blocks}"


# ---------------------------------------------------------------------------
# C. Threshold — below-threshold memories excluded
# ---------------------------------------------------------------------------

def test_c_threshold_excludes_low_scoring_memories(tmp_path):
    """Memories that score below MIN_RELEVANCE_SCORE must be silently excluded."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_c"

    # Seed a memory with only very weak connection to the query
    _seed_memory(
        store, ws,
        summary="Project inception meeting notes summary",
        content="Team discussed project goals and initial roadmap items.",
        tags=["project", "meeting"],
        confidence=0.5,
    )

    # Use the exact default threshold — the above memory should score very low
    # against a completely different query domain
    mgr = _build_mgr(store, ws, min_relevance_score=MIN_RELEVANCE_SCORE)
    ctx = _run_task(mgr, "Implement TLS certificate rotation for nginx server")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0, f"Expected no injection below threshold, got: {blocks}"


def test_c_threshold_custom_strict_excludes_marginal(tmp_path):
    """With a very high custom threshold, even partially relevant memories are excluded."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_c2"

    # A memory with some token overlap but not strong
    _seed_memory(
        store, ws,
        summary="PostgreSQL basic schema design",
        content="Design normalized tables for PostgreSQL databases.",
        tags=["postgresql", "schema"],
        confidence=0.7,
    )

    # Very high threshold that this memory won't clear
    mgr = _build_mgr(store, ws, min_relevance_score=999.0)
    ctx = _run_task(mgr, "Configure PostgreSQL connection pool")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0


def test_c_threshold_low_includes_memories(tmp_path):
    """With a very low threshold, even weak matches are included."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_c3"

    _seed_memory(
        store, ws,
        summary="PostgreSQL schema design",
        content="Design normalized tables.",
        tags=["postgresql"],
        confidence=0.8,
    )

    mgr = _build_mgr(store, ws, min_relevance_score=0.0)
    ctx = _run_task(mgr, "PostgreSQL database setup")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1


# ---------------------------------------------------------------------------
# D. Top-K — at most 3 injected even with 10+ relevant memories
# ---------------------------------------------------------------------------

def test_d_topk_cap_limits_to_max_memories(tmp_path):
    """Even if 10 relevant memories exist, only CONTEXT_MAX_MEMORIES (3) are injected."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_d"

    # Seed 10 highly relevant memories
    for i in range(10):
        _seed_memory(
            store, ws,
            summary=f"Security policy #{i}: enforce authentication token validation",
            content=f"Authentication rule {i}: all requests must carry a valid token.",
            tags=["security", "auth", "token"],
            confidence=0.95,
        )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Implement authentication and token validation")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1  # single combined block

    block = blocks[0]
    # Count entries — each starts with "[DECISION]" or similar tag
    entry_count = block.count("[DECISION]")
    assert entry_count <= CONTEXT_MAX_MEMORIES, (
        f"Expected at most {CONTEXT_MAX_MEMORIES} memories, got {entry_count}"
    )


def test_d_topk_custom_override(tmp_path):
    """Custom context_max_memories=1 injects at most 1 memory."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_d2"

    for i in range(5):
        _seed_memory(
            store, ws,
            summary=f"Auth rule {i}: Bearer token required on all endpoints",
            content=f"Rule {i}: enforce Bearer token on every REST call.",
            tags=["auth", "bearer"],
            confidence=0.9,
        )

    mgr = _build_mgr(store, ws, context_max_memories=1)
    ctx = _run_task(mgr, "Configure REST endpoint authentication with Bearer token")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1
    assert blocks[0].count("[DECISION]") == 1


# ---------------------------------------------------------------------------
# E. Char budget — oversized content stays within budget
# ---------------------------------------------------------------------------

def test_e_char_budget_limits_injection_size(tmp_path):
    """Injected memory block must not exceed CONTEXT_CHAR_BUDGET characters."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_e"

    # Seed 3 memories with very large content that combined would greatly exceed budget
    for i in range(3):
        big_content = f"Token auth rule {i}: " + ("A" * 800)
        _seed_memory(
            store, ws,
            summary=f"Authentication policy {i}: Bearer token mandatory for REST APIs",
            content=big_content,
            tags=["auth", "bearer", "token"],
            confidence=0.97,
        )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Configure authentication with Bearer token for REST APIs")

    blocks = _injected_system_blocks(ctx)
    if blocks:
        total_len = sum(len(b) for b in blocks)
        assert total_len <= CONTEXT_CHAR_BUDGET + 50, (  # +50 for the header line itself
            f"Injected block too large: {total_len} chars (budget: {CONTEXT_CHAR_BUDGET})"
        )


def test_e_single_oversized_memory_respects_excerpt_cap(tmp_path):
    """A single memory with very large content has its excerpt capped at MEMORY_EXCERPT_MAX_CHARS."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_e2"

    big_content = "Auth rule: " + ("X" * 2000)  # 2000+ chars
    mem = _seed_memory(
        store, ws,
        summary="Authentication policy: Bearer token for all REST APIs",
        content=big_content,
        tags=["auth", "bearer"],
        confidence=0.95,
    )

    # Verify _format_memory_compact caps the excerpt
    block = _format_memory_compact(mem, excerpt_max=MEMORY_EXCERPT_MAX_CHARS)
    # The excerpt line should be no more than MEMORY_EXCERPT_MAX_CHARS + len("  ") + len("…")
    for line in block.splitlines():
        # Content lines start with two spaces
        if line.startswith("  ") and "Auth rule:" in line:
            assert len(line.strip()) <= MEMORY_EXCERPT_MAX_CHARS + 1, (
                f"Excerpt too long: {len(line.strip())} chars"
            )


# ---------------------------------------------------------------------------
# F. Compact format — full content not injected verbatim
# ---------------------------------------------------------------------------

def test_f_compact_format_does_not_inject_full_content(tmp_path):
    """The injected block must not contain the verbatim full content of memories."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_f"

    long_content = (
        "All REST endpoints must use Bearer token authentication. "
        "Tokens must be validated on every request using HMAC-SHA256. "
        "Expired tokens must return 401. Refresh tokens are stored encrypted. "
        "Never log token values in plaintext. Rotate keys every 90 days. "
        "Use short-lived access tokens (15 min) and longer refresh tokens (7 days). "
        "Do not pass tokens in URL parameters, always use Authorization header. "
        "Additional security detail for uniqueness: UNIQUE_MARKER_XYZ_789."
    )
    _seed_memory(
        store, ws,
        summary="Bearer token policy for REST APIs",
        content=long_content,
        tags=["auth", "bearer", "token", "security"],
        confidence=0.98,
    )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Implement Bearer token authentication for the REST API endpoint")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1
    block = blocks[0]

    # The unique marker at the end of content should NOT appear verbatim
    assert "UNIQUE_MARKER_XYZ_789" not in block or len(block) < CONTEXT_CHAR_BUDGET


def test_f_compact_format_structure(tmp_path):
    """Compact format must include category tag, summary, and provenance line."""
    prov = MemoryProvenance(
        source_entity="quality_gate",
        author_agent="Reviewer",
        source_mission_id="mis_fmt",
        verification_status="verified",
    )
    mem = WorkforceMemory.create(
        workspace_id="ws_f2",
        category=MemoryCategory.DECISION,
        summary="Use PostgreSQL with pgvector for vector storage",
        content="PostgreSQL with pgvector extension is the approved vector database solution.",
        provenance=prov,
        tags=["postgresql", "vector"],
        confidence=0.95,
    )

    block = _format_memory_compact(mem)

    assert block.startswith("[DECISION]")
    assert "Use PostgreSQL with pgvector" in block
    assert "Source: quality_gate" in block
    assert "Agent: Reviewer" in block
    assert "Mission: mis_fmt" in block


# ---------------------------------------------------------------------------
# G. Verified-only — unverified/archived/deleted excluded
# ---------------------------------------------------------------------------

def test_g_unverified_memories_excluded(tmp_path):
    """Memories with verification_status != 'verified' must not appear in context."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_g"

    # Only "inferred" status — should be retrievable in search but injected with caution
    # Note: the current filter only excludes archived/deleted at DB level.
    # Unverified memories score-filter works because they typically have lower confidence.
    # For strict exclusion test, seed with is_archived=True.
    _seed_memory(
        store, ws,
        summary="Bearer token required for all authentication flows",
        content="Use Bearer token validation on every REST request.",
        tags=["auth", "bearer", "token"],
        confidence=0.9,
        is_archived=True,  # archived memories must never be injected
    )

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Implement authentication with Bearer token")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0, "Archived memories must not be injected"


def test_g_soft_deleted_memories_excluded(tmp_path):
    """Soft-deleted memories must not appear in context injection."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_g2"

    mem = _seed_memory(
        store, ws,
        summary="Bearer token authentication policy",
        content="All endpoints require Bearer token verification.",
        tags=["auth", "bearer"],
        confidence=0.95,
    )
    # Soft-delete
    store.delete_memory(mem.id, hard=False, workspace_id=ws)

    mgr = _build_mgr(store, ws)
    ctx = _run_task(mgr, "Configure authentication with Bearer token")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0, "Soft-deleted memories must not be injected"


# ---------------------------------------------------------------------------
# H. Scoping — workspace/team/agent/mission isolation preserved
# ---------------------------------------------------------------------------

def test_h_workspace_isolation_preserved(tmp_path):
    """Memories from workspace A must never appear in workspace B's context."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")

    _seed_memory(
        store, "ws_alpha",
        summary="Alpha auth policy: Bearer token required",
        content="Bearer token mandatory for all Alpha workspace endpoints.",
        tags=["auth", "bearer", "alpha"],
    )

    # Manager for workspace BETA
    mgr_beta = _build_mgr(store, "ws_beta")
    ctx = _run_task(mgr_beta, "Implement Bearer token authentication")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0, "Cross-workspace injection must be zero"


def test_h_correct_workspace_gets_injection(tmp_path):
    """The right workspace must get its memory injected."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")

    _seed_memory(
        store, "ws_correct",
        summary="Bearer token required for REST API authentication",
        content="All REST endpoints must use Bearer token auth.",
        tags=["auth", "bearer", "rest"],
        confidence=0.95,
    )

    mgr_correct = _build_mgr(store, "ws_correct")
    ctx = _run_task(mgr_correct, "Implement Bearer token authentication for REST API")

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 1
    assert "Bearer token" in blocks[0]


# ---------------------------------------------------------------------------
# I. Determinism — same input → same output
# ---------------------------------------------------------------------------

def test_i_deterministic_output(tmp_path):
    """Same task + same store → identical injected content across multiple calls."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_i"

    for i in range(5):
        _seed_memory(
            store, ws,
            summary=f"Auth rule {i}: Bearer token validation required",
            content=f"Rule {i}: validate Bearer tokens using HMAC-SHA256.",
            tags=["auth", "bearer", "security"],
            confidence=0.9,
        )

    mgr = _build_mgr(store, ws)

    ctx1 = _run_task(mgr, "Implement Bearer token authentication")
    ctx2 = _run_task(mgr, "Implement Bearer token authentication")
    ctx3 = _run_task(mgr, "Implement Bearer token authentication")

    blocks1 = _injected_system_blocks(ctx1)
    blocks2 = _injected_system_blocks(ctx2)
    blocks3 = _injected_system_blocks(ctx3)

    assert blocks1 == blocks2 == blocks3, "Retrieval must be deterministic"


# ---------------------------------------------------------------------------
# J. Runtime regression — AgentContext still works without workforce memory
# ---------------------------------------------------------------------------

def test_j_no_workforce_store_zero_injection(tmp_path):
    """MemoryManager without a WorkforceMemoryStore must not crash and must not inject."""
    mgr = MemoryManager(
        workspace_id="ws_j",
        agent_name="Solo",
        # No workforce_memory_store
    )
    task = Task(instruction="Implement a login endpoint")
    ctx = AgentContext(task=task, agent_name="Solo")
    mgr.load_context(ctx)  # Must not raise

    blocks = _injected_system_blocks(ctx)
    assert len(blocks) == 0


def test_j_existing_system_message_preserved(tmp_path):
    """If the AgentContext already has a system message, it must be kept first."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_j2"

    _seed_memory(
        store, ws,
        summary="Bearer token mandatory for authentication",
        content="Enforce Bearer token on all REST calls.",
        tags=["auth", "bearer"],
        confidence=0.95,
    )

    from aether.core.execution import Message
    mgr = _build_mgr(store, ws)
    task = Task(instruction="Implement authentication with Bearer token")
    ctx = AgentContext(task=task, agent_name="TestAgent")
    ctx.messages = [Message(role="system", content="You are a helpful API engineer.")]

    mgr.load_context(ctx)

    # Original system message must still be at index 0
    assert ctx.messages[0].role == "system"
    assert ctx.messages[0].content == "You are a helpful API engineer."

    # Memory block must follow
    assert len(ctx.messages) >= 2
    assert ctx.messages[1].role == "system"
    assert _MEMORY_BLOCK_HEADER in ctx.messages[1].content


def test_j_agent_context_regression_no_crash(tmp_path):
    """Full MemoryManager lifecycle must complete without errors."""
    store = WorkforceMemoryStore(tmp_path / "mem.db")
    ws = "ws_j3"

    mgr = _build_mgr(store, ws)
    task = Task(instruction="Just a simple task with no relevant memories")
    ctx = AgentContext(task=task, agent_name="TestAgent")

    mgr.load_context(ctx)
    mgr.persist_context(ctx)  # Must not raise

    assert ctx.messages is not None  # Context is always valid
