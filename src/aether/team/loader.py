"""
TeamLoader — parses ``team.yaml`` into :class:`~aether.team.config.TeamConfig`.

The YAML schema is intentionally simple and forward-compatible. Unknown
keys are preserved in ``metadata`` dicts so future fields don't cause
parse errors.

Minimal example::

    team:
      name: agency-ai
      knowledge: ./knowledge/

    agents:
      - name: triage
        role: coordinator
        relationships:
          - delegates_to: knowledge
          - delegates_to: writer

      - name: knowledge
        role: researcher

      - name: writer
        role: writer

The loader requires PyYAML (``pyyaml``), which is already a transitive
dependency of many AI SDKs. If not available, a helpful error is raised.
"""
from __future__ import annotations

from pathlib import Path

from aether.team.config import AgentConfig, Relationship, TeamConfig


def _require_yaml():
    try:
        import yaml
        return yaml
    except ImportError as exc:
        raise ImportError(
            "PyYAML is required to load team.yaml files. "
            "Install it with: pip install pyyaml"
        ) from exc


class TeamLoader:
    """
    Loads a :class:`~aether.team.config.TeamConfig` from a YAML file or
    a Python dict.

    Usage::

        config = TeamLoader.from_yaml("team.yaml")
        config = TeamLoader.from_dict({...})
    """

    @staticmethod
    def from_yaml(path: str | Path) -> TeamConfig:
        """
        Parse *path* (a ``team.yaml`` file) into a :class:`TeamConfig`.

        The ``knowledge`` path in the YAML, if relative, is resolved
        relative to the directory containing the YAML file.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If the file is empty or the ``agents`` list is missing.
        """
        yaml = _require_yaml()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"team.yaml not found: {p}")

        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not raw:
            raise ValueError(f"team.yaml is empty: {p}")

        config = TeamLoader.from_dict(raw)

        # Resolve relative knowledge path against the YAML's directory
        if config.knowledge_path and not Path(config.knowledge_path).is_absolute():
            config.knowledge_path = str(p.parent / config.knowledge_path)

        return config

    @staticmethod
    def from_dict(data: dict) -> TeamConfig:
        """
        Build a :class:`TeamConfig` from a plain Python dict.

        This is the canonical parser: ``from_yaml`` delegates here after
        loading the YAML.
        """
        team_section = data.get("team", {})
        agents_section = data.get("agents", [])

        if not isinstance(agents_section, list):
            raise ValueError("'agents' must be a list in team.yaml")

        # ------------------------------------------------------------------
        # Parse team-level config
        # ------------------------------------------------------------------
        name = team_section.get("name", "aether-team")
        knowledge_path = team_section.get("knowledge") or team_section.get("knowledge_path")
        default_provider = team_section.get("provider", "openai")
        default_model = team_section.get("model")
        team_metadata = {
            k: v for k, v in team_section.items()
            if k not in ("name", "knowledge", "knowledge_path", "provider", "model")
        }

        # ------------------------------------------------------------------
        # Parse agents
        # ------------------------------------------------------------------
        agents: list[AgentConfig] = []
        for raw_agent in agents_section:
            if not isinstance(raw_agent, dict):
                continue
            agent_name = raw_agent.get("name", "")
            if not agent_name:
                continue

            agent_role = raw_agent.get("role", "assistant")
            instructions = raw_agent.get("instructions", "")
            model = raw_agent.get("model")
            skills = raw_agent.get("skills") or []
            if isinstance(skills, str):
                skills = [skills]

            # Relationships — support multiple notations:
            #   relationships:
            #     - delegates_to: knowledge       (simple shorthand)
            #     - type: collaborates_with
            #       target: writer                (explicit)
            relationships: list[Relationship] = []
            raw_rels = raw_agent.get("relationships") or []
            for rel in raw_rels:
                if isinstance(rel, dict):
                    # Explicit: { type: ..., target: ... }
                    if "type" in rel and "target" in rel:
                        relationships.append(Relationship(
                            type=rel["type"],
                            target=rel["target"],
                        ))
                    else:
                        # Shorthand: { delegates_to: "agent_name" }
                        for rel_type, target in rel.items():
                            if isinstance(target, str):
                                relationships.append(Relationship(
                                    type=rel_type,
                                    target=target,
                                ))

            # Known keys — everything else goes to metadata
            known = {"name", "role", "instructions", "model", "skills", "relationships"}
            agent_metadata = {k: v for k, v in raw_agent.items() if k not in known}

            agents.append(AgentConfig(
                name=agent_name,
                role=agent_role,
                instructions=instructions,
                relationships=relationships,
                skills=skills,
                model=model,
                metadata=agent_metadata,
            ))

        return TeamConfig(
            name=name,
            agents=agents,
            knowledge_path=knowledge_path,
            default_provider=default_provider,
            default_model=default_model,
            metadata=team_metadata,
        )

    @staticmethod
    def to_yaml_str(config: TeamConfig) -> str:
        """
        Serialize a :class:`TeamConfig` back to YAML string.
        Useful for ``aether init`` scaffolding.
        """
        yaml = _require_yaml()

        data: dict = {
            "team": {
                "name": config.name,
            },
            "agents": [],
        }

        if config.knowledge_path:
            data["team"]["knowledge"] = config.knowledge_path
        if config.default_provider != "openai":
            data["team"]["provider"] = config.default_provider
        if config.default_model:
            data["team"]["model"] = config.default_model
        if config.metadata:
            data["team"].update(config.metadata)

        for agent in config.agents:
            raw: dict = {"name": agent.name, "role": agent.role}
            if agent.instructions:
                raw["instructions"] = agent.instructions
            if agent.model:
                raw["model"] = agent.model
            if agent.skills:
                raw["skills"] = agent.skills
            if agent.relationships:
                raw["relationships"] = [
                    {r.type: r.target} for r in agent.relationships
                ]
            if agent.metadata:
                raw.update(agent.metadata)
            data["agents"].append(raw)

        return yaml.dump(data, default_flow_style=False, allow_unicode=True)
