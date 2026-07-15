# Aether Development Guide

## Version

0.1.0

## Status

Draft

## Purpose

This document defines the development standards, workflows and conventions used to build Aether.

The goal is to keep the project organized, maintainable and scalable as the platform grows.

---

# 1. Development Philosophy

Aether follows a foundation-first development approach.

Before implementing complex features, the project prioritizes:

* clear architecture;
* documented decisions;
* modular components;
* testable code;
* maintainable solutions.

Every important technical choice should be documented inside the project.

---

# 2. Technology Stack

## Core Language

Aether Core is initially developed using:

* Python 3.12+

Python is chosen because of:

* strong AI ecosystem;
* compatibility with local and cloud AI providers;
* rapid development;
* extensive library availability.

---

## Package Management

The project uses:

* pyproject.toml
* uv

Dependencies should always be explicitly managed and reproducible.

---

## Testing

Testing framework:

* pytest

Every important component should include automated tests.

---

## Code Quality

Code quality tools:

* ruff

Ruff is used for:

* linting;
* formatting;
* static checks.

---

# 3. Repository Structure

Current repository structure:

aether/

├── docs/
│   Documentation and project decisions

├── src/
│   Source code

├── tests/
│   Automated tests

├── examples/
│   Usage examples

├── README.md
│   Project overview

└── CONTRIBUTING.md
Contribution guidelines

---

# 4. Git Workflow

Aether uses a branch-based development workflow.

The main branch:

main

contains stable and reviewed code.

Development happens through dedicated branches.

Examples:

feature/agent-runtime

feature/memory-system

feature/event-bus

fix/provider-error

docs/update-architecture

chore/project-structure

---

# 5. Commit Convention

Commits should follow this format:

type: short description

Examples:

feat: add agent runtime

fix: correct memory storage bug

docs: update architecture documentation

test: add agent tests

chore: update dependencies

Commit messages should clearly describe the purpose of the change.

---

# 6. Pull Requests

Changes should be introduced through Pull Requests.

A Pull Request should contain:

* clear title;
* description of changes;
* related issues;
* tests when required.

The objective is to keep changes reviewable, understandable and traceable.

---

# 7. Development Principles

## Modularity

Every component should have a clear responsibility.

Modules should avoid unnecessary dependencies.

---

## Independence

Components should communicate through interfaces and contracts.

Replacing an implementation should not require rewriting the whole system.

---

## Documentation

Important architectural and technical decisions must be documented.

Documentation is considered part of the product.

---

## Testing

New functionality should include appropriate tests.

Tests are required to maintain reliability as Aether grows.

---

## Simplicity

Prefer simple and understandable solutions before introducing complex abstractions.

---

# 8. Local Development

The initial development environment is local.

Developers should be able to:

* install dependencies;
* run tests;
* execute examples;
* experiment with local AI models.

Cloud services are optional integrations.

---

# 9. Future Development

Future versions may introduce:

* Aether SDK;
* plugin system;
* marketplace;
* cloud deployment;
* enterprise features;
* web interfaces.

The development process must support long-term scalability and collaboration.
