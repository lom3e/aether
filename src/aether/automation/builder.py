"""
AutomationBuilder — Natural Language Automation Builder for Aether.
Parses natural language prompts (Italian & English) into structured, multi-step
AutomationDefinition workflows with schedule derivation, step generation, and preview synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re
from typing import Any
import uuid

from aether.automation.models import (
    AutomationDefinition,
    OutputDestination,
    OutputType,
    PipelineStep,
    TriggerConfig,
    TriggerType,
)

logger = logging.getLogger(__name__)


@dataclass
class AutomationProposal:
    automation: AutomationDefinition
    human_summary: str
    recurrence_text: str


class AutomationBuilder:
    """Creates draft automations from conversational or natural language prompts."""

    DAY_MAP_IT = {
        "lunedì": 1, "lunedi": 1,
        "martedì": 2, "martedi": 2,
        "mercoledì": 3, "mercoledi": 3,
        "giovedì": 4, "giovedi": 4,
        "venerdì": 5, "venerdi": 5,
        "sabato": 6,
        "domenica": 0,
    }

    DAY_MAP_EN = {
        "monday": 1, "mon": 1,
        "tuesday": 2, "tue": 2,
        "wednesday": 3, "wed": 3,
        "thursday": 4, "thu": 4,
        "friday": 5, "fri": 5,
        "saturday": 6, "sat": 6,
        "sunday": 0, "sun": 0,
    }

    @classmethod
    def parse_time(cls, text: str) -> tuple[int, int]:
        """Extracts hour (0-23) and minute (0-59) from text, defaulting to 9:00."""
        t_lower = text.lower()

        # Check Italian "alle HH:MM" or "alle HH"
        m_it = re.search(r"\balle\s+(\d{1,2})(?::(\d{2}))?", t_lower)
        if m_it:
            hour = int(m_it.group(1))
            minute = int(m_it.group(2)) if m_it.group(2) else 0
            return hour % 24, minute % 60

        # Check English "at HH(:MM)?\s*(am|pm)?"
        m_en = re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t_lower)
        if m_en:
            hour = int(m_en.group(1))
            minute = int(m_en.group(2)) if m_en.group(2) else 0
            ampm = m_en.group(3)
            if ampm == "pm" and hour < 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            return hour % 24, minute % 60

        # Check standalone "HH:MM"
        m_time = re.search(r"\b(\d{1,2}):(\d{2})\b", t_lower)
        if m_time:
            return int(m_time.group(1)) % 24, int(m_time.group(2)) % 60

        # Default 09:00
        return 9, 0

    @classmethod
    def parse_recurrence(cls, text: str) -> tuple[str | None, int | None, str]:
        """
        Parses recurrence schedule from natural language.
        Returns: (cron_expression, interval_seconds, human_readable_description)
        """
        p_lower = text.lower()
        hour, minute = cls.parse_time(text)
        time_str = f"{hour:02d}:{minute:02d}"

        # 1. Minute intervals (e.g., "ogni 15 minuti", "every 15 minutes")
        m_min = re.search(r"(?:ogni|every)\s+(\d+)\s*(?:minuti|minutes|min)\b", p_lower)
        if m_min:
            mins = int(m_min.group(1))
            if mins in [1, 2, 3, 5, 10, 15, 20, 30]:
                return f"*/{mins} * * * *", mins * 60, f"Every {mins} minutes"
            return None, mins * 60, f"Every {mins} minutes"

        # 2. Hour intervals (e.g., "ogni 2 ore", "every 2 hours")
        m_hr = re.search(r"(?:ogni|every)\s+(\d+)\s*(?:ore|hours|ora|hour)\b", p_lower)
        if m_hr:
            hrs = int(m_hr.group(1))
            if hrs == 1:
                return "0 * * * *", 3600, "Every hour"
            elif hrs in [2, 3, 4, 6, 8, 12]:
                return f"0 */{hrs} * * *", hrs * 3600, f"Every {hrs} hours"
            return None, hrs * 3600, f"Every {hrs} hours"

        if "ogni ora" in p_lower or "every hour" in p_lower or "hourly" in p_lower:
            return "0 * * * *", 3600, "Every hour"

        # 3. Day of week (Italian)
        for day_name, day_num in cls.DAY_MAP_IT.items():
            if f"ogni {day_name}" in p_lower or f"tutti i {day_name}" in p_lower:
                return f"{minute} {hour} * * {day_num}", None, f"Ogni {day_name.capitalize()} alle {time_str}"

        # 4. Day of week (English)
        for day_name, day_num in cls.DAY_MAP_EN.items():
            if f"every {day_name}" in p_lower or f"on {day_name}" in p_lower:
                return f"{minute} {hour} * * {day_num}", None, f"Every {day_name.capitalize()} at {time_str}"

        # 5. Weekdays (1-5)
        if any(k in p_lower for k in ["giorni feriali", "giorno feriale", "weekdays", "every weekday"]):
            return f"{minute} {hour} * * 1-5", None, f"Weekdays at {time_str}"

        # 6. Daily / Every day
        if any(k in p_lower for k in ["ogni giorno", "tutti i giorni", "every day", "daily", "ogni mattina", "every morning"]):
            return f"{minute} {hour} * * *", None, f"Every day at {time_str}"

        # 7. Weekly
        if "ogni settimana" in p_lower or "every week" in p_lower or "weekly" in p_lower:
            return f"{minute} {hour} * * 1", None, f"Weekly on Monday at {time_str}"

        # Default fallback if recurring intent detected
        return f"{minute} {hour} * * 1", None, f"Weekly on Monday at {time_str}"

    @classmethod
    def _extract_title_and_objective(cls, prompt: str) -> tuple[str, str]:
        """Derives a concise title and clean objective from the raw prompt."""
        cleaned = re.sub(
            r"^(?:crea\s+(?:un'?)?automazione\s+(?:per|che)?|create\s+(?:an?\s+)?automation\s+(?:to|for)?|"
            r"schedula\s+(?:un\s+)?controllo\s+|programma\s+|automatizza\s+|schedule\s+)?",
            "",
            prompt,
            flags=re.IGNORECASE,
        ).strip()

        # Remove schedule prefix/suffix phrases for cleaner title
        cleaned = re.sub(r"\b(?:ogni\s+[a-zA-Z0-9_]+(?:\s+alle\s+\d{1,2}(?::\d{2})?)?|every\s+[a-zA-Z0-9_]+(?:\s+at\s+\d{1,2}(?::\d{2})?(?:am|pm)?)?)\b", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = cleaned.strip(",;.- ")

        if not cleaned:
            cleaned = "Automated Operational Workflow"

        # Capitalize first letter of words for title
        words = cleaned.split()
        short_title = " ".join(words[:6]).title()
        if len(words) > 6:
            short_title += "..."

        return short_title, cleaned

    @classmethod
    def build_from_natural_language(
        cls,
        prompt: str,
        workspace: Any = None,
    ) -> AutomationDefinition:
        """Parses a natural language instruction and constructs an AutomationDefinition."""
        p_lower = prompt.lower()
        title, objective = cls._extract_title_and_objective(prompt)

        # Trigger detection
        if any(k in p_lower for k in ["webhook", "su richiesta http", "endpoint"]):
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", title.lower()).strip("-")
            trigger = TriggerConfig(
                type=TriggerType.WEBHOOK,
                webhook_slug=slug,
                webhook_secret=uuid.uuid4().hex[:16],
            )
            human_sched = f"Webhook triggered at /api/automations/webhooks/{slug}"
        elif any(k in p_lower for k in ["quando un file", "on new file", "watch directory", "monitora cartella", "monitora file"]):
            path_m = re.search(r"(?:cartella|directory|path|folder)\s+['\"]?([a-zA-Z0-9_\-\./]+)['\"]?", prompt, re.IGNORECASE)
            watch_path = path_m.group(1).strip() if path_m else "inputs"
            trigger = TriggerConfig(
                type=TriggerType.FILE_WATCHER,
                watch_path=watch_path,
                watch_pattern="*.*",
                watch_events=["created", "modified"],
            )
            human_sched = f"File watcher on '{watch_path}'"
        else:
            cron, interval, human_sched = cls.parse_recurrence(prompt)
            trigger = TriggerConfig(
                type=TriggerType.SCHEDULE,
                cron=cron,
                interval_seconds=interval,
            )

        # Pipeline Steps generation based on objective
        steps: list[PipelineStep] = []
        is_italian = any(k in p_lower for k in ["ogni", "lunedì", "martedì", "report", "controlla", "mandami", "crea"])

        if is_italian:
            steps.append(
                PipelineStep(
                    id="step_investigate",
                    name="Raccolta e Analisi Dati",
                    agent_name="Researcher",
                    prompt_template=f"Indaga ed esegui la verifica operativa per: {objective}. Considera input: {{input}}",
                )
            )
            steps.append(
                PipelineStep(
                    id="step_synthesize",
                    name="Sintesi e Report Operativo",
                    agent_name="Writer",
                    prompt_template="Sintetizza i risultati emersi in un report chiaro e azionabile basandoti su: {step_investigate_output}",
                    depends_on=["step_investigate"],
                )
            )
        else:
            steps.append(
                PipelineStep(
                    id="step_investigate",
                    name="Investigate & Collect Data",
                    agent_name="Researcher",
                    prompt_template=f"Investigate and gather operational data for: {objective}. Context input: {{input}}",
                )
            )
            steps.append(
                PipelineStep(
                    id="step_synthesize",
                    name="Synthesize Operational Report",
                    agent_name="Writer",
                    prompt_template="Consolidate findings into a concise, actionable report based on: {step_investigate_output}",
                    depends_on=["step_investigate"],
                )
            )

        # Output destination
        out_type = OutputType.NOTIFICATION
        target_path = None
        if "file" in p_lower or "salva" in p_lower or "documento" in p_lower or ".md" in p_lower or "save to" in p_lower:
            out_type = OutputType.FILE
            file_m = re.search(r"([a-zA-Z0-9_\-\./]+\.(?:md|txt|json|csv))", prompt)
            target_path = file_m.group(1) if file_m else "reports/automation_report.md"

        output_dest = OutputDestination(
            type=out_type,
            target_path=target_path,
            notify_title=f"Deliverable: {title}",
        )

        auto = AutomationDefinition(
            id=f"auto_{uuid.uuid4().hex[:8]}",
            name=title,
            description=f"Generated from request: '{prompt}'",
            enabled=False,  # Drafts start disabled awaiting user confirmation
            is_draft=True,
            requires_approval=True,
            human_schedule=human_sched,
            trigger=trigger,
            steps=steps,
            output_destination=output_dest,
            metadata={"origin_prompt": prompt, "created_via": "nl_builder"},
        )
        return auto

    @classmethod
    def build_proposal(
        cls,
        prompt: str,
        workspace: Any = None,
    ) -> AutomationProposal:
        """Constructs an automation proposal with a formatted human summary."""
        auto = cls.build_from_natural_language(prompt, workspace)

        steps_summary = "\n".join(
            f"- **Step {i+1} ({s.agent_name})**: {s.name}" for i, s in enumerate(auto.steps)
        )

        dest_summary = (
            f"Write to file `{auto.output_destination.target_path}`"
            if auto.output_destination and auto.output_destination.type == OutputType.FILE
            else "Send Notification to Aether Companion"
        )

        summary = (
            f"### Proposed Automation: {auto.name}\n\n"
            f"- **Schedule / Trigger**: {auto.human_schedule} ({auto.trigger.cron or auto.trigger.type.value})\n"
            f"- **Steps**:\n{steps_summary}\n"
            f"- **Destination**: {dest_summary}\n"
            f"- **Status**: Draft (requires your approval to activate)\n\n"
            f"Would you like me to activate and schedule this automation?"
        )

        return AutomationProposal(
            automation=auto,
            human_summary=summary,
            recurrence_text=auto.human_schedule or "",
        )

    @classmethod
    def build_and_save(
        cls,
        prompt: str,
        workspace: Any,
    ) -> AutomationDefinition:
        """Builds and persists a draft automation to the workspace store."""
        auto = cls.build_from_natural_language(prompt, workspace)
        if hasattr(workspace, "automations"):
            return workspace.automations.save_automation(auto)
        return auto
