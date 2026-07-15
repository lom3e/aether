# Aether Naming Convention Document

## Version

0.1.0

## Status

Draft

## Last Updated

2026-07-15

---

# 1. Overview

This document defines the naming strategy of the Aether ecosystem.

The objective is to create a consistent naming system across:

* repositories;
* software components;
* products;
* SDK packages;
* internal services;
* future marketplace extensions.

Naming decisions should prioritize:

* clarity;
* scalability;
* professional perception;
* developer experience.

---

# 2. Brand Structure

The Aether ecosystem is divided into:

## Core Platform

The infrastructure layer.

Name:

```text
Aether
```

Purpose:

The engine that powers autonomous AI agents.

---

## Applications

Products built on top of Aether.

Example:

```text
AIOffice Web

AIOffice Desktop

AIOffice Mobile
```

These are not the engine.

They are user-facing applications.

---

# 3. Main Brand

## Aether

Meaning:

Aether represents the invisible infrastructure that connects intelligence, memory and communication.

The concept represents:

* connection;
* intelligence;
* distributed systems;
* autonomous workflows.

---

# 4. Core Components

The main internal modules follow:

Aether + Component Name

---

# 4.1 Aether Core

Repository:

```text
aether
```

Purpose:

The main runtime engine.

Responsibilities:

* agent execution;
* orchestration;
* provider management;
* system lifecycle.

---

# 4.2 Aether Memory

Purpose:

Persistent knowledge system.

Responsibilities:

* memory storage;
* retrieval;
* embeddings;
* knowledge management.

---

# 4.3 Aether Bus

Purpose:

Communication infrastructure.

Responsibilities:

* event management;
* agent communication;
* workflow triggers.

---

# 4.4 Aether SDK

Purpose:

Developer ecosystem.

Responsibilities:

* create agents;
* create skills;
* create tools;
* extend Aether.

---

# 4.5 Aether CLI

Purpose:

Developer command line interface.

Example:

```bash
aether init

aether create agent

aether run
```

---

# 4.6 Aether Marketplace

Purpose:

Extension ecosystem.

Users can publish:

* agents;
* skills;
* tools;
* integrations.

---

# 5. Application Naming

Applications use independent names.

Structure:

```text
Product + Platform
```

Current products:

```text
AIOffice Web

AIOffice Desktop

AIOffice Mobile
```

---

# 6. Repository Naming

Repositories should represent ownership and responsibility.

---

## Core Repository

Official:

```text
aether
```

Contains:

* engine;
* SDK;
* CLI;
* core infrastructure.

---

## Web Application

Repository:

```text
aioffice-web
```

Purpose:

Browser-based interface.

---

## Desktop Application

Repository:

```text
aioffice-desktop
```

Purpose:

Native desktop experience.

---

## Mobile Application

Repository:

```text
aioffice-mobile
```

Purpose:

Mobile clients.

---

# 7. Repository Philosophy

Repositories should be separated by responsibility.

Avoid:

```text
aether-everything
```

because:

* difficult maintenance;
* unclear ownership;
* slower development.

Prefer:

```text
aether

aioffice-web

aioffice-desktop

aioffice-mobile
```

---

# 8. Internal Package Naming

Code packages should use lowercase naming.

Examples:

Python:

```text
aether_core

aether_memory

aether_bus
```

JavaScript:

```text
@aether/sdk

@aether/core
```

---

# 9. Agent Naming

Agents should have descriptive professional names.

Examples:

```text
Developer Agent

Testing Agent

Documentation Agent

Planning Agent

Security Agent

Research Agent
```

Future versions may support custom names.

Example:

```text
Atlas

Nova

Orion
```

---

# 10. Skill Naming

Skills use:

```text
category-name
```

Examples:

```text
python-development

frontend-react

security-analysis

technical-writing
```

---

# 11. Tool Naming

Tools use:

```text
service-action
```

Examples:

```text
github-manager

slack-messenger

calendar-manager

filesystem-access
```

---

# 12. Event Naming

Events use:

```text
object.action
```

Examples:

```text
agent.created

task.completed

code.generated

test.failed

memory.updated
```

---

# 13. Version Naming

All Aether components follow Semantic Versioning.

Format:

```text
MAJOR.MINOR.PATCH
```

Example:

```text
1.4.2
```

Meaning:

Major:

Breaking changes.

Minor:

New features.

Patch:

Bug fixes.

---

# 14. Future Naming Candidates

Possible future product names:

## Neuron

Concept:

Intelligence and connections.

Possible use:

Agent intelligence layer.

---

## Atlas

Concept:

Knowledge and navigation.

Possible use:

Knowledge management system.

---

## Aether

Current preferred brand.

Reason:

Strong connection to infrastructure and intelligence.

---

# 15. Naming Rules

New names should:

* be easy to pronounce internationally;
* avoid unnecessary complexity;
* represent the function;
* fit the Aether ecosystem.

Avoid:

* random abbreviations;
* unclear acronyms;
* names without meaning.

---

# 16. Current Naming Decisions

Approved:

```text
Brand:

Aether


Core:

Aether Core


Memory:

Aether Memory


Communication:

Aether Bus


Developer Platform:

Aether SDK


CLI:

Aether CLI


Marketplace:

Aether Marketplace


Applications:

AIOffice Web
AIOffice Desktop
AIOffice Mobile
```

---

# 17. Naming Status

Current phase:

Foundation.

These names are considered stable but can evolve through documented decisions.

Future changes require a Decision Log entry.

---
