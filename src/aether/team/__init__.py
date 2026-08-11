"""
Aether Team System — configure and run a team of persistent AI agents.

This package provides:

- :class:`~aether.team.config.TeamConfig` — declarative team configuration
  loaded from ``team.yaml`` or constructed in code.
- :class:`~aether.team.team.Team` — the runtime that assembles agents from
  config, wires delegation, knowledge, and HITL, and runs tasks.
- :class:`~aether.team.loader.TeamLoader` — parses ``team.yaml`` into a
  :class:`~aether.team.config.TeamConfig`.
- :class:`~aether.team.feed.ActivityFeed` — readable real-time activity
  output for end users (wraps :class:`~aether.coordination.events.EventEmitter`).

Quick start::

    from aether.team import Team

    team = Team.from_yaml("team.yaml")
    result = team.run("Draft a proposal for client Nexo regarding GDPR compliance")
    print(result.output)
"""
from __future__ import annotations

from aether.team.config import TeamConfig, AgentConfig, Relationship
from aether.team.loader import TeamLoader
from aether.team.team import Team
from aether.team.feed import ActivityFeed

__all__ = [
    "Team",
    "TeamConfig",
    "AgentConfig",
    "Relationship",
    "TeamLoader",
    "ActivityFeed",
]
