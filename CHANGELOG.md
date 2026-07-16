# Changelog

All notable changes to Aether will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [v0.8.0] - 2026-07-16

### Added
- **ExecutionEngine Orchestration**: The engine now owns the execution loop, dispatch mechanism, fail-fast implementation, and execution plan building.
- **ExecutionPlan & ExecutionPlanState**: Standardized contracts representing an ordered set of actions to run, enabling dry-runs, introspection, and future LLM planning support.
- **UnitType Enum**: Type-safe discriminator (`SKILL`, `TOOL`) replacing unsafe string comparisons.
- **SkillUnit & ToolUnit**: Wrappers representing specific capability types as executable units in a plan.
- **Dependency Injection**: `ExecutionEngine` can now be injected into the `Agent` during initialization.

### Changed
- **Agent Simplification**: Extracted the runtime loop, fail-fast logic, and tool routing from `Agent.execute()`, delegating them to the `ExecutionEngine`.
- **Graceful Error Trapping**: Unregistered tool requests now return a `UnitExecutionResult` with status `FAILED` and error type `ToolNotFoundError` instead of raising a raw `KeyError`.

### Breaking Changes
- `UnitExecutionResult.unit_type` is now a `UnitType` enum instead of a `str`. Comparers must be updated to use `UnitType.SKILL` or `UnitType.TOOL`.
- Task execution metadata was updated: instead of reporting failed skills under `incompatible_skills`, the runtime metadata now flags the failed execution unit under `failed_unit`.

### Migration Notes
Update tests and code performing string comparison on execution unit types:
```python
# Before
assert result.unit_type == "skill"

# After
from aether.engine.units import UnitType
assert result.unit_type == UnitType.SKILL
```

---

## [v0.7.0] - 2026-07-16

### Added
- **Unified Execution Engine**: Introduced the initial `ExecutionEngine` class to bridge skill execution and tool execution.
- **UnitExecutionResult**: Standardized the return schema of both skills and tools, with unified status properties.
- **ToolExecutor**: Encapsulated execution of functional tools.
- **Backward Compatibility**: Aliased legacy `SkillResult` to `UnitExecutionResult`.

---

## [v0.6.1] - 2026-07-16

### Added
- **SkillResult Runtime Contract**: Standardized contract for skill execution outputs.
- **Fail-Fast Semantics**: Loop terminates immediately at the first skill failure.

---

## [v0.6.0] - 2026-07-15

### Added
- **Skill Execution Runtime**: Integrated `SkillExecutor` in the agent execution flow.
