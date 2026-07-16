# Aether

Aether is an open-core AI agent platform designed to orchestrate intelligent agents, skills, tools and memory into collaborative digital teams.

## Execution Pipeline

The core execution flow in Aether follows this pipeline:

```text
Runtime
  ↓
Agent
  ↓
ExecutionEngine
  ↓
ExecutionPlan
  ↓
Execution Units (Skill / Tool)
  ↓
UnitExecutionResult
  ↓
ExecutionResult
```

### Responsibilities

**Agent** is responsible for:
- agent lifecycle management
- managing ExecutionContext
- LLM provider coordination and reasoning
- final ExecutionResult generation

**ExecutionEngine** is responsible for:
- plan construction (`build_plan()`)
- sequential execution loop with fail-fast semantics (`run()`)
- routing execution units (`_dispatch()`) to specific executors
- runtime error trapping and wrapping

**ExecutionPlan** represents the declared sequence of execution steps.

**UnitExecutionResult** represents the unified outcome of a single execution unit (Skill or Tool).

## Project Status

- **v0.6.0**: Skill Execution Runtime
- **v0.6.1**: SkillResult Runtime Contract
- **v0.7.0**: Unified Execution Runtime
- **v0.8.0**: Execution Orchestration Foundation

