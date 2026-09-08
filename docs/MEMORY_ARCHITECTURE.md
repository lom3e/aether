# Workforce Memory Architecture

> Phase B — Slice 1: Persistent Workforce Memory Foundation  
> Status: **Implemented** — commit `feat(memory): add persistent workforce memory foundation`

---

## Overview

The Workforce Memory system gives every agent team a **persistent, workspace-isolated, provenance-verified memory layer** that accumulates operational intelligence from verified Mission events.

Memory is **never** auto-ingested from:
- Agent internal reasoning / Chain-of-Thought
- Conversation transcripts
- System prompts or API credentials
- Unverified LLM outputs

Memory **is** ingested exclusively from:
- Deliverables verified by the Quality Gate
- Human-approved stage gate decisions
- Quality Gate lessons (rework cycles and redlines)

---

## Domain Model

```
WorkforceMemory
├── id              (UUID, immutable)
├── workspace_id    (mandatory, enforces isolation)
├── category        (MemoryCategory — 8 canonical types)
├── summary         (short headline, ≤256 chars)
├── content         (full sanitized text)
├── provenance      (MemoryProvenance — verified source chain)
├── tags            (list[str])
├── agent_name      (producing agent, optional)
├── team_name       (producing team, optional)
├── mission_id      (source mission UUID, optional)
├── execution_id    (source execution UUID, optional)
├── confidence      (0.0–1.0 float)
├── is_archived     (soft delete flag)
├── created_at      (ISO-8601 UTC)
└── updated_at      (ISO-8601 UTC)
```

### MemoryCategory Taxonomy (8 categories)

| Category | Purpose |
|----------|---------|
| `fact` | Verified technical facts |
| `preference` | Operator / user preferences |
| `decision` | Approved decisions, gate overrides |
| `process` | Validated procedures, workflows |
| `person` | Stakeholder context, roles |
| `project` | Project goals, milestones |
| `outcome` | Verified deliverable records |
| `lesson` | Lessons from quality gate rework cycles |

---

## Storage

- **Backend**: SQLite (per-workspace)
- **Location**: `<aether_data_dir>/<workspace_name>/memory.db`
- **Isolation**: Every query is scoped by `workspace_id`

---

## Ingestion Pipeline

```
Mission Runtime
    │
    ├── approve_gate()
    │       ├── ingest_verified_deliverable(deliverable)
    │       └── ingest_approved_decision(approval_record)
    │
    └── _run_quality_gate() → PASS
            ├── ingest_verified_deliverable(deliverable, eval_result)
            └── ingest_quality_gate_lesson(eval_result, rework_count)
```

All ingestion is lazy-loaded inside `try/except` — memory failures never abort Mission execution.

---

## Privacy & Sanitization

- **CoT-stripped**: removes `<thought>`, `<thinking>`, `<reasoning>`, `System Prompt:` etc.
- **Secret-redacted**: API keys, tokens, passwords, private keys → `[REDACTED]`
- **Truncated**: max 50,000 characters

---

## Retrieval & Agent Injection

`WorkforceMemoryStore.retrieve_relevant()` uses deterministic term-overlap scoring (no vector embeddings required). Results are confidence-boosted and returned top-k.

`MemoryManager.load_context()` injects relevant memories as a `system` message into agent context:

```
Verified Workforce Intelligence & Compounding Memory:

[DECISION] All REST APIs require Bearer token validation with HMAC-SHA256
  Source: quality_gate | Author: SecurityReviewer | Confidence: 0.99
```

---

## REST API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/memories` | List (filterable) |
| `GET` | `/api/memories/{id}` | Get single |
| `POST` | `/api/memories` | Create manual |
| `PATCH` | `/api/memories/{id}` | Update |
| `POST` | `/api/memories/{id}/archive` | Toggle archive |
| `DELETE` | `/api/memories/{id}` | Soft delete |
| `POST` | `/api/memories/retrieve` | Scored retrieval |

---

## Key Invariants

1. No memory without provenance
2. No cross-workspace reads
3. No CoT or secrets stored
4. No mission abort on memory failure
5. No vector infrastructure required
