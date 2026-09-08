# Aether Explain Cards & Deliverables Dossier Architecture
## Slice 8 — Deliverables Dossier Viewer & Observable Explainability Cards

**Status:** Completed Engineering Specification  
**Module:** `aether.missions.explain`, `aether.missions.store`, `aether.server.routes`, `ui/src/DeliverablesViewer.tsx`  
**Phase:** Phase A (Core Operational Experience)

---

## 1. Executive Summary & Design Law

Aether Explain Cards and the Deliverables Dossier Viewer provide deterministic, observable explainability and rich in-cockpit deliverable inspection for autonomous missions.

### The Fundamental Rule: Observable Evidence, Zero Chain-of-Thought
Explain Cards **strictly forbid** raw LLM Chain-of-Thought (CoT), internal system prompts, speculative reasoning, or private conversation scratchpads. 

Instead, an Explain Card is composed exclusively of **auditable, factual runtime artifacts**:
1. **Result:** Observable outcome statement, artifact format, file size, stage, run number, and cryptographic hash.
2. **Verification & Quality Gate:** Real Reviewer Agent identity, numerical quality score (e.g. 95/100), and deterministic validation checks (`disk_file_integrity`, `requirement_coverage`, `citation_grounding`, `structural_integrity`).
3. **Observable Evidence:** Disk file presence and size verification, milestone lineage, and factual facts derived from execution records.
4. **Contributors:** Explicit list of executing workforce agents and specialized tools involved in producing the deliverable.
5. **Conclusion & Decision:** Factual summary of whether the deliverable was accepted, overridden, or requires rework.
6. **Limitations & Governance:** Workspace execution boundaries, human override availability, and audit traceability.

---

## 2. Deliverables Dossier Viewer Architecture

### 2.1 File Format Detection & Rendering Modes
The Dossier Viewer implements progressive disclosure in an ergonomic slide-over modal/drawer with content preview and format-specific renderers:

| Format | File Extensions / Heuristics | Renderer Component |
| :--- | :--- | :--- |
| **Markdown** | `.md`, `.markdown`, UTF-8 text with Markdown syntax | Styled typography renderer with headers, bullet points, and code snippets |
| **JSON** | `.json` or valid JSON text payload | Structured, syntax-colored, indented JSON view |
| **CSV** | `.csv`, `.tsv` | Scrollable tabular grid with sticky headers and bordered cells |
| **Code** | `.py`, `.ts`, `.tsx`, `.js`, `.yaml`, `.yml`, `.sh`, `.toml`, `.sql`, etc. | Monospace code block with line numbering |
| **Text** | `.txt`, `.log` | Clean pre-formatted monospace text viewer |
| **Binary / Fallback** | `.png`, `.pdf`, `.zip`, `.tar.gz`, or non-UTF-8 | Informational fallback card with Open, Reveal in Finder, and Download actions |

### 2.2 Security & Sandbox Boundary Guarantees
All deliverable file accesses strictly enforce workspace boundary checks:
* **Anti-Traversal Protection:** File paths are validated via `_resolve_and_validate_deliverable_file(ws, path)` or `resolve_safe_path()`. Paths referencing `..`, absolute paths outside the workspace root, or symlink escapes trigger HTTP 403 Forbidden.
* **Large File Safeguard:** Files exceeding 512 KB have their preview content withheld (`truncated = True`, `preview_available = False`) to preserve client performance and memory safety, while presenting a clear message and providing direct Download and Open buttons.
* **UTF-8 Resilience:** Non-UTF-8 bytes or decode errors fall back seamlessly to binary mode without raising unhandled exceptions or crashing the server process.

---

## 3. Explain Data Model

The domain models are defined in `src/aether/missions/explain.py`:

```python
@dataclass
class VerificationCheck:
    name: str
    passed: bool
    score: int
    reason: str

@dataclass
class VerificationSummary:
    reviewer_agent: str | None
    quality_score: int | None
    verified_at: str | None
    status: str
    checks: list[VerificationCheck]

@dataclass
class Contributor:
    name: str
    role: str

@dataclass
class EvidenceItem:
    category: str
    detail: str

@dataclass
class ExplainCard:
    deliverable_id: str
    deliverable_name: str
    mission_id: str
    execution_id: str | None
    run_number: int | None
    stage_name: str
    file_type: str
    size_bytes: int
    sha256: str | None
    result: str
    verification: VerificationSummary
    evidence: list[EvidenceItem]
    contributors: list[Contributor]
    decision: str
    limitations: str

@dataclass
class MissionExplainSummary:
    mission_id: str
    mission_title: str
    execution_id: str | None
    run_number: int | None
    overall_status: str
    quality_score: int | None
    completed_milestones: int
    total_milestones: int
    deliverables_count: int
    verified_deliverables_count: int
    deliverable_cards: list[ExplainCard]
    summary_text: str
```

---

## 4. Multi-Run Scope & Lifecycle Isolation

Explain Cards strictly respect the active execution run context:
* When `execution_id` is supplied (e.g. Run #1 vs Run #2), the Explain card derives contributors, stage names, and verification scores strictly from that run context.
* Quality Gate rework cycles produce distinct evaluation scores and reviewer notes across runs, preventing cross-run state pollution.
* The frontend Dossier reflects the selected execution run pill, updating deliverables and explain cards reactively upon execution switching.

---

## 5. API Endpoints

1. **`GET /api/missions/{mission_id}/deliverables/{deliverable_id}/preview`**
   - Returns preview content, format, size, and truncation status.
2. **`GET /api/missions/{mission_id}/deliverables/{deliverable_id}/explain`**
   - Returns `ExplainCard` serialization for a specific deliverable.
3. **`GET /api/missions/{mission_id}/explain?execution_id={optional}`**
   - Returns `MissionExplainSummary` synthesizing overall outcome and individual deliverable cards.
