# Aether

Aether is an open-core AI agent platform designed to orchestrate intelligent agents, skills, tools and memory into collaborative digital teams.

## Execution Pipeline

The core execution flow in Aether follows this pipeline:

```text
Runtime
  ↓
Agent
  ↓
SkillExecutor
  ↓
SkillResult
  ↓
ExecutionResult
```

### Responsibilities

**Agent** is responsible for:
- orchestration
- agent lifecycle
- managing ExecutionContext
- interaction with LLM providers
- generating the final ExecutionResult

**SkillExecutor** is responsible for:
- canonical skill resolution
- validation
- hooks
- skill lifecycle handling
- generating the SkillResult

**SkillResult** represents the standardized contract for the result of a single skill execution.

## Project Status

- **v0.6.0**: Skill Execution Runtime
- **v0.6.1**: SkillResult Runtime Contract
