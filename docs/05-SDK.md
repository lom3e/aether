# Aether SDK Document

## Version

0.1.0

## Status

Draft

## Last Updated

2026-07-15

---

# 1. Overview

The Aether SDK is the official development framework for creating extensions inside the Aether ecosystem.

The SDK allows developers to build:

* custom agents;
* custom skills;
* custom tools;
* integrations;
* workflows;
* plugins.

The goal is to transform Aether from a single platform into an extensible ecosystem.

---

# 2. SDK Philosophy

Aether should not be limited to the capabilities created by the core team.

The platform must allow developers to extend it.

The SDK follows this principle:

> Everything that can be extended should be extendable.

---

# 3. SDK Components

The Aether SDK consists of:

```
Aether SDK

├── Agent SDK
├── Skill SDK
├── Tool SDK
├── Event SDK
├── Memory SDK
├── Integration SDK
└── Testing SDK
```

---

# 4. Agent SDK

The Agent SDK allows developers to create custom agents.

Example:

```python
from aether import Agent


class DeveloperAgent(Agent):

    name = "Developer Agent"

    role = "Software Engineer"

    skills = [
        "coding",
        "debugging"
    ]

    tools = [
        "filesystem",
        "git"
    ]
```

---

# 5. Agent Development Lifecycle

Creating an agent:

```
Create Agent

↓

Define Identity

↓

Assign Skills

↓

Configure Tools

↓

Test Agent

↓

Deploy Agent
```

---

# 6. Skill SDK

Skills represent reusable capabilities.

A skill defines:

* knowledge;
* instructions;
* behaviors;
* evaluation methods.

Example:

```
Skill:

Code Review

Contains:

- programming standards;
- security checks;
- quality rules;
- review workflow.
```

---

# 7. Tool SDK

Tools allow agents to interact with external systems.

Examples:

Development tools:

* GitHub;
* databases;
* terminals.

Productivity tools:

* Calendar;
* Email;
* Slack.

Business tools:

* CRM;
* ERP;
* analytics systems.

---

# 8. Tool Definition Example

Example:

```python
from aether import Tool


class CalendarTool(Tool):

    name = "calendar"

    description = """
    Creates and manages calendar events.
    """

    permissions = [
        "calendar.create",
        "calendar.read"
    ]
```

---

# 9. Event SDK

The Event SDK allows extensions to communicate through Aether Bus.

Example:

```python
event.emit(
    "task.completed",
    {
        "agent": "developer",
        "result": "success"
    }
)
```

---

# 10. Memory SDK

The Memory SDK allows developers to interact with the Aether Memory system.

Capabilities:

* store information;
* retrieve knowledge;
* create memories;
* search context.

Example:

```python
memory.store(
    key="project_architecture",
    value="Backend uses FastAPI"
)
```

---

# 11. Integration SDK

The Integration SDK allows connection with external platforms.

Examples:

* Slack;
* GitHub;
* Google Calendar;
* Microsoft services;
* APIs.

---

# 12. Workflow SDK

Developers can create reusable workflows.

Example:

```
Software Development Workflow


Planning Agent

↓

Developer Agent

↓

Testing Agent

↓

Review Agent
```

A workflow defines:

* agents involved;
* execution order;
* communication rules;
* required tools.

---

# 13. Local and Cloud Compatibility

The SDK must support different execution environments.

Supported:

```
Local Development

↓

Aether Core

↓

Local Models


or


Cloud Deployment

↓

Aether Core

↓

Cloud Models
```

Developers should not rewrite extensions depending on deployment.

---

# 14. CLI Integration

The SDK will include Aether CLI support.

Example commands:

```
aether create agent developer

aether create skill code-review

aether test agent

aether deploy agent
```

---

# 15. Testing Framework

The SDK should provide tools to test extensions.

Testing types:

## Unit Testing

Verify individual components.

---

## Agent Testing

Verify agent behavior.

---

## Workflow Testing

Verify collaboration between agents.

---

Example:

```
Input Task

↓

Agent Execution

↓

Expected Result

↓

Evaluation
```

---

# 16. Versioning System

Every extension should support semantic versioning.

Example:

```
developer-agent

v1.0.0
```

Rules:

```
Major:
Breaking changes

Minor:
New features

Patch:
Bug fixes
```

---

# 17. Security Model

Extensions must define permissions.

Example:

```yaml
permissions:

filesystem:
  read: true

filesystem:
  write: false

github:
  access: true
```

Users must approve sensitive permissions.

---

# 18. Marketplace Compatibility

The SDK is designed to support the future Aether Marketplace.

Developers can publish:

* agents;
* skills;
* tools;
* workflows;
* integrations.

Each package contains:

```
Extension

├── Metadata
├── Code
├── Documentation
├── Permissions
├── Version
└── Dependencies
```

---

# 19. Open Source Strategy

Possible strategy:

## Open Core

Aether Core:

Open source.

---

## Extensions

Community and commercial ecosystem.

---

## Marketplace

Optional monetization layer.

---

# 20. Future SDK Goals

Future versions may include:

* visual agent builder;
* no-code workflows;
* extension templates;
* cloud deployment;
* analytics;
* enterprise SDK.

---

# 21. Current SDK Status

Current phase:

Architecture definition.

Next priorities:

1. Define SDK interfaces.
2. Create first developer API.
3. Build first example agent.
4. Create extension template.
5. Prepare marketplace architecture.

---
