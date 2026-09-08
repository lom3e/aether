# Learning & Correction Loop — Architecture & Technical Reference

**Document Version:** `1.0.0`  
**Phase:** Phase B — Macro Slice 4  
**Status:** Implemented & Verified  
**Branch:** `development`

---

## 1. Overview & Problem Statement

Prior to Phase B Slice 4, when missions or tasks encountered errors or failed quality gates:
1. **Transient Fixes:** Rework solved the immediate error in the current execution context, but the knowledge of *why* it failed and *how* to prevent it was lost upon mission completion.
2. **Repetitive Failures (Regressions):** Subsequent missions or other agents on the workforce had no structured, durable memory of past failures and would commit the exact same architectural or configuration mistakes.
3. **Hallucinated / Unverified "Lessons":** Naive LLM reflection systems frequently hallucinate ungrounded conclusions or attempt to promote raw, unverified failures directly into permanent knowledge, polluting agent memory with bad advice.
4. **Leakage Risks:** Raw agent execution transcripts containing reasoning chains (CoT), internal system prompts, API keys, or raw intermediate tokens could easily leak into durable memory.

**The Learning & Correction Loop** solves this by establishing a persistent, evidence-first, deterministic closed loop:
- **Observable Failure Capture:** Quality Gate evaluations and human checkpoints capture structured failures with explicit expected standards and evidence.
- **Strict Verification Lifecycle:** Transitions through `OBSERVED` → `PROPOSED` → `VERIFIED` (or `REJECTED`). Only verified corrections are distilled into durable lessons.
- **Multi-Store Automatic Compilation:** Verified lessons are compiled both into `WorkforceMemoryStore` (category=`lesson`, `status=verified`) and `KnowledgeGraphStore` (`node_type=lesson`, linked via `derived_from` and `applies_to` edges).
- **Unified Context Injection:** Future agent task executions automatically retrieve verified lessons via `UnifiedIntelligenceService`, preventing recurring errors before they happen.
- **Deterministic Regression Detection:** If a Quality Gate fails on a rule that matches a previously verified lesson, it is flagged as a regression, incrementing counters and emitting high-visibility alerts.

---

## 2. Architecture & The Closed Loop

```text
                     Mission Execution / Quality Gate
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼ (Gate Rejected)                       ▼ (Gate Passed)
      ┌─────────────────────────────┐         ┌─────────────────────────────┐
      │     record_gate_failure     │         │      record_gate_pass       │
      │  - Extract Rule Failures    │         │  - Check previous rework    │
      │  - Detect Regressions       │         │  - Distill Verified Lesson  │
      └──────────────┬──────────────┘         └──────────────┬──────────────┘
                     │                                       │
                     ▼                                       ▼
      ┌─────────────────────────────┐         ┌─────────────────────────────┐
      │   Proposed Correction       │         │      Distilled Lesson       │
      │ (status=PROPOSED, evidence) │         │ (status=VERIFIED, clean)    │
      └──────────────┬──────────────┘         └──────────────┬──────────────┘
                     │                                       │
                     ▼                                       ▼
      ┌─────────────────────────────┐         ┌─────────────────────────────┐
      │  Human / Evaluator Review   │         │  Multi-Store Compilation    │
      │  - verify_correction()      ├────────►│  1. WorkforceMemoryStore    │
      │  - reject_correction()      │         │  2. KnowledgeGraphStore     │
      └─────────────────────────────┘         └──────────────┬──────────────┘
                                                             │
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │ UnifiedIntelligenceService  │
                                              │  - Gated Retrieval          │
                                              │  - Ranked Context Injection │
                                              └──────────────┬──────────────┘
                                                             │
                                                             ▼
                                                  Future Agent Tasks
                                              (Zero Regression Standard)
```

---

## 3. Data Models & Storage Schema

### 3.1 Domain Models (`aether.learning.models`)

1. **`LearningEvent`**:
   - `id`: Deterministic/unique event ID (`le-...`).
   - `workspace_id`: Strict isolation identifier.
   - `event_type`: `FAILURE`, `CORRECTION`, `REWORK_SUCCESS`, `LESSON_CREATED`, `REGRESSION`, `HUMAN_FEEDBACK`, `HUMAN_APPROVAL`.
   - `observed_behavior`: Sanitized description of the actual observed behavior.
   - `expected_behavior`: Sanitized standard or contract expected by the system.
   - `correction`: The actionable corrective measure.
   - `evidence`: Dictionary of key-value parameters demonstrating the failure without sensitive data.
   - `verification_status`: `OBSERVED`, `PROPOSED`, `VERIFIED`, `REJECTED`.
   - `mission_id`, `execution_id`, `milestone_id`, `agent_name`, `team_name`: Traceability identifiers.

2. **`Correction`**:
   - `id`: `corr-...`
   - `target_scope`: `AGENT`, `TEAM`, `PROJECT`, `PROCESS`, `WORKSPACE`.
   - `target_identifier`: Specific target (e.g., `sre-team`, `DBAgent`, `workspace`).
   - `problem`: Clear statement of the failed constraint.
   - `correction`: Proposed remedial implementation.
   - `rationale`: Justification or architectural standard.
   - `evidence`: Structured failure data.
   - `source_mission_id`, `source_execution_id`: Provenance links.
   - `verification_status`: `PROPOSED` (initial) → `VERIFIED` / `REJECTED`.

3. **`DistilledLesson`**:
   - `id`: `lsn-...`
   - `title`: Canonical title of the distilled rule or lesson.
   - `lesson_text`: Compact, actionable operational guideline.
   - `scope`: Granular scope (`agent`, `team`, `project`, `process`, `workspace`).
   - `target_identifier`: Target entity name.
   - `quality_gate_rule`: The evaluated quality gate rule ID.
   - `verification_status`: `VERIFIED`.
   - `memory_id`: Pointer to corresponding `WorkforceMemory` entry.
   - `node_id`: Pointer to corresponding `GraphNode` in `KnowledgeGraphStore`.
   - `is_regression`: Flag indicating if this lesson experienced repeat violations.
   - `regression_count`: Integer counter of detected regressions.

---

## 4. Deterministic Regression Detection

When `LearningService.record_quality_gate_failure()` is invoked:
1. It queries `distilled_lessons` for any existing lessons matching `(workspace_id, quality_gate_rule)`.
2. If an existing verified lesson exists for this rule:
   - Increments `regression_count` by 1.
   - Sets `is_regression = True`.
   - Records a `LearningEventType.REGRESSION` event with full mission provenance.
   - Marks the newly created proposed `Correction` as `is_regression = True`.
3. Ensures immediate visibility across the UI with high-visibility alert cards and badges.

---

## 5. Multi-Store Ingestion & Provenance

When a lesson is distilled (via rework completion or explicit verification):
1. **WorkforceMemoryStore:**
   - Saved with `category = MemoryCategory.LESSON`.
   - `provenance.verification_status = "verified"`.
   - `provenance.author_agent = reviewer_agent` or operator name.
   - Sanitized using `sanitize_memory_text()` and `sanitize_memory_data()`.
2. **KnowledgeGraphStore:**
   - Upserted as a `GraphNode` with `node_type = KnowledgeNodeType.LESSON`.
   - Directed `GraphEdge` created with `relation_type = KnowledgeRelationType.DERIVED_FROM` pointing to `mission:{mission_id}`.
   - Directed `GraphEdge` created with `relation_type = KnowledgeRelationType.APPLIES_TO` pointing to target entity node (`agent:{name}` or `team:{name}`).

---

## 6. Privacy, Security & Sanitization

- **Zero CoT Policy:** Persistent learning models explicitly prohibit and strip chain-of-thought, reasoning steps, internal thinking, and prompt templates.
- **Zero Secret Leakage:** Regex-based sanitization automatically masks API keys, bearer tokens, AWS credentials, and connection strings before persistence.
- **Workspace Isolation:** All SQLite tables enforce `workspace_id` scoping on indexes and transactions. Cross-workspace data leakage is strictly impossible.

---

## 7. REST API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/learning/events` | `GET` | List filtered learning events (pagination, scope, event_type). |
| `/api/learning/events/{id}` | `GET` | Retrieve single learning event with evidence. |
| `/api/learning/corrections` | `GET` | List corrections with status and scope filtering. |
| `/api/learning/corrections` | `POST` | Create a new proposed correction. |
| `/api/learning/corrections/{id}/verify` | `POST` | Verify a proposed correction and distill it into a lesson. |
| `/api/learning/corrections/{id}/reject` | `POST` | Reject a proposed correction. |
| `/api/learning/lessons` | `GET` | List distilled verified lessons. |
| `/api/learning/lessons/{id}` | `GET` | Retrieve a single distilled lesson with relational IDs. |
| `/api/learning/distill` | `POST` | Explicitly distill a correction into a verified lesson. |
