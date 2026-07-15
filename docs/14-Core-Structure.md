# Aether Core Structure

## Version

0.1.0

## Status

Draft

## Last Updated

2026-07-15

---

# 1. Purpose

This document defines the initial internal structure of Aether Core.

Aether Core is the foundational runtime responsible for managing AI agents, their capabilities, communication, memory and external integrations.

The structure is designed to keep the system modular, scalable and independent from specific applications.

Applications such as:

* AI Office Web
* AI Office Desktop
* AI Office Mobile

will consume Aether Core as a platform.

---

# 2. Source Code Organization

The main source directory is:

```
src/aether/
```

Inside this package, every major capability has its own isolated module.

Current structure:

```
aether/
├── core/
├── agents/
├── skills/
├── tools/
├── memory/
├── bus/
└── providers/
```

---

# 3. Core Module

Location:

```
src/aether/core/
```

## Responsibility

The core module contains the fundamental runtime components of Aether.

It is responsible for:

* system initialization;
* configuration management;
* lifecycle management;
* common interfaces;
* shared abstractions.

The core should not contain business logic specific to applications.

---

# 4. Agents Module

Location:

```
src/aether/agents/
```

## Responsibility

The agents module manages digital agents.

An Aether agent is not a simple process.

An agent contains:

* identity;
* role;
* objectives;
* responsibilities;
* memory references;
* skills;
* tools;
* permissions;
* history;
* performance data.

Future components may include:

* Agent class;
* Agent lifecycle;
* Agent registry;
* Agent communication.

---

# 5. Skills Module

Location:

```
src/aether/skills/
```

## Responsibility

Skills represent reusable capabilities that can be assigned to agents.

Examples:

* Python programming;
* web development;
* data analysis;
* documentation;
* testing.

Skills define what an agent knows how to do.

Skills are independent from agents and can be reused.

---

# 6. Tools Module

Location:

```
src/aether/tools/
```

## Responsibility

Tools define external actions available to agents.

Examples:

* filesystem access;
* terminal commands;
* Git operations;
* APIs;
* calendars;
* databases.

Tools must operate through controlled permissions.

Agents should never directly access external resources without the tool layer.

---

# 7. Memory Module

Location:

```
src/aether/memory/
```

## Responsibility

The memory module provides persistent knowledge management.

Responsibilities:

* storing information;
* retrieving context;
* managing embeddings;
* searching knowledge;
* separating private and shared memory.

Memory is a fundamental capability of Aether agents.

---

# 8. Event Bus Module

Location:

```
src/aether/bus/
```

## Responsibility

The event bus enables communication between independent components.

Examples of events:

```
agent.created
task.created
task.assigned
work.started
work.completed
review.requested
```

The event system allows Aether to scale without tightly coupling components.

---

# 9. Providers Module

Location:

```
src/aether/providers/
```

## Responsibility

The providers module abstracts external AI services.

Supported providers may include:

* local models;
* cloud APIs;
* multiple AI vendors.

Examples:

* Ollama;
* llama.cpp;
* OpenAI API;
* future providers.

Aether agents should never depend directly on a specific provider.

---

# 10. Design Principles

## Modularity

Each module must have a clear responsibility.

## Replaceability

Components should be replaceable without rewriting the entire system.

## Provider Independence

AI models are implementation details, not core dependencies.

## Documentation First

Every architectural decision must be documented.

## Open Core Ready

The architecture must support future extensions, plugins and marketplace components.

---

# 11. Current Development Phase

Current state:

Foundation phase.

Completed:

* repository initialization;
* documentation structure;
* first architecture definition;
* initial package structure.

Next objectives:

* define core interfaces;
* create first minimal agent;
* implement provider abstraction;
* build first working example.
