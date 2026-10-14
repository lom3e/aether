"""
Deterministic intent contract for coding requests.

``assess_coding_prompt`` turns a prompt into a typed ``CodingAssessment``: which operational signals fired,
which informational/negative signals vetoed them, and whether the result is ambiguous enough that a human
(or an advisory LLM) should settle it. It never grants consent or authority: its only output is a
classification, and an operational classification still has to go through proposal, consent, authority and
policy before anything runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class CodingAssessment:
    operational: bool
    informational: bool
    ambiguous: bool
    has_actionable_directive: bool
    has_mutation_mandate: bool
    has_coding_trigger: bool
    has_agent_coding: bool
    informational_reasons: tuple[str, ...] = field(default_factory=tuple)
    # The request edits a document (a note, a report, a text file), not code: it must never reach a coding agent.
    document_operation: bool = False


_HEDGE_RE = re.compile(
    r"\b(?:forse|magari|potrei|potremmo|sto\s+pensando|stavo\s+pensando|maybe|perhaps|might|i(?:'m| am)\s+thinking|"
    r"non\s+so\s+se|dovrei\s+forse|what\s+if|e\s+se)\b"
)


_PATH_PREFIX = (
    r"(?:in|su|nel progetto|nel repository|nel percorso|directory|folder|path|workspace|repo)\s+"
    r"(?:(?:locale|local|corrente|attuale|esistente)\s+)?"
)
_PATH_PATTERNS = (
    # POSIX path after a "where" word (historical behaviour)
    re.compile(_PATH_PREFIX + r"""[`"'(]?(/[^\s`"')]+)[`"')]?""", re.IGNORECASE),
    # Windows drive path after a "where" word: quoted (may contain spaces) or bare
    re.compile(_PATH_PREFIX + r"""[`"']([A-Za-z]:[\\/][^`"']+)[`"']""", re.IGNORECASE),
    re.compile(_PATH_PREFIX + r"""[(]?([A-Za-z]:[\\/][^\s`"')<>|?*]+)""", re.IGNORECASE),
    # Bare deep POSIX path anywhere
    re.compile(r"""[`"'(]?(/[\w.\-]+(?:/[\w.\-]+)+)[`"')]?"""),
    # Bare Windows path anywhere
    re.compile(r"""(?:^|[\s`"'(])([A-Za-z]:[\\/][^\s`"')<>|?*]+)"""),
)



# --- Object-of-the-verb evidence -------------------------------------------------------------------------------------
# "Update the file X" is a coding request only when X is code. Instead of listing verbs, the classifier looks at WHAT the
# verb acts on: code evidence (a code file, a code vocabulary, a coding agent) versus document evidence (a document file).
_DOCUMENT_EXTENSIONS = r"(?:md|markdown|txt|rtf|docx?|odt|pdf|csv|tsv|xlsx?)"
_CODE_EVIDENCE_RE = re.compile(
    r"\.(?:py|pyi|ts|tsx|js|jsx|mjs|rs|go|java|kt|swift|c|cc|cpp|h|hpp|cs|rb|php|sh|css|scss|html|json|ya?ml|toml|ini|sql)\b"
    r"|\b(?:codice|code|codebase|funzione|function|metodo|method|classe|class|bug|refactor\w*|repository|repo|branch|commit|"
    r"pull\s+request|api|endpoint|script|programma|software|backend|frontend|database|query\s+sql|componente|component|"
    r"modulo|libreria|library|compil\w+|dipendenz\w+|unit\s+test|test\s+automatic\w+|antigravity|claude\s+code|codex)\b",
    re.IGNORECASE,
)
_DOCUMENT_TARGET_RE = re.compile(
    r"(?P<file>[\w.\-]+\." + _DOCUMENT_EXTENSIONS + r")\b|\b(?:documento|document|nota|note|appunti|report|relazione|verbale|lettera|testo)\b",
    re.IGNORECASE,
)
_DOCUMENT_FILE_RE = re.compile(r"(?P<file>[\w.\-]+\." + _DOCUMENT_EXTENSIONS + r")\b", re.IGNORECASE)
_DOCUMENT_EDIT_VERB_RE = re.compile(
    r"\b(?:modifica|modificare|aggiorna|aggiornare|riscrivi|riscrivere|rielabora|correggi|correggere|integra|integrare|"
    r"completa|completare|aggiungi|aggiungere|accorcia|riassumi|traduci|sistema|edit|update|rewrite|revise|append|shorten|"
    r"translate|fix|amend)\b",
    re.IGNORECASE,
)


def has_code_evidence(prompt: str) -> bool:
    """True when the request is about software: a code file, code vocabulary or a coding agent is named."""
    return bool(_CODE_EVIDENCE_RE.search(prompt or ""))


@dataclass(frozen=True)
class DocumentOperation:
    filename: str
    instruction: str


def assess_document_operation(prompt: str) -> DocumentOperation | None:
    """
    A request to edit a named document ("aggiorna il file report_finale.md con i dati di vendita"): an edit verb, a document
    file as the object and NO code evidence. It is routed to the document actions, never to a coding agent.
    """
    text = (prompt or "").strip()
    if not text or text.endswith("?") and not re.match(r"^(?:puoi|potresti|can\s+you|could\s+you)\b", text, re.IGNORECASE):
        return None
    if has_code_evidence(text) or not _DOCUMENT_EDIT_VERB_RE.search(text):
        return None
    match = _DOCUMENT_FILE_RE.search(text)
    if not match:
        return None
    return DocumentOperation(filename=match.group("file"), instruction=text)


def extract_project_path_mention(text: str) -> str | None:
    """First filesystem path mentioned in ``text``: POSIX ('/a/b') or Windows ('C:\a\b', 'C:/a/b')."""
    for pattern in _PATH_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return match.group(1)
    return None


def assess_coding_prompt(prompt: str) -> CodingAssessment:
    p_lower = (prompt or "").lower().strip()
    actionable_coding_patterns = [
        # App / CLI / Project creation
        r"\b(?:crea|creare|realizza|realizzare|sviluppa|sviluppare|costruisci|costruire|build|create|implementa|implementare|implement)\s+(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:piccol[oa]\s+|nuov[oa]\s+|semplice\s+)?(?:applicazione|app|cli|progetto|modulo|script|servizio|tool|package)\b",
        # Function / Component / Code implementation or creation
        r"\b(?:implementa|implementare|scrivi|scrivere|crea|creare|sviluppa|sviluppare|aggiungi|aggiungere|write|implement|create|add)\s+(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:nuov[oaie]\s+)?(?:codice|funzione|metodo|classe|componente|algoritmo|endpoint|modulo|middleware|parser|libreria|plugin|handler|decoratore|code|function|method|class|component|algorithm|library|decorator)\b",
        r"\b(?:implementa|implementare|scrivi|scrivere|crea|creare|sviluppa|sviluppare|aggiungi|aggiungere|write|implement|create|add)\s+.*?\b(?:nel\s+file|in\s+file|su\s+file|nel\s+progetto|in\s+project|\.py|\.ts|\.js|\.rs|\.go|\.java)\b",
        # Test writing / creation / addition
        r"\b(?:scrivi|scrivere|crea|creare|aggiungi|aggiungere|implementa|implementare|write|create|add|implement)\s+(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:test|test_[\w]+|unit test|test automatic[io]|suite)\b",
        # Bug fixing / code modification / refactoring
        r"\b(?:risolvi|risolvere|correggi|correggere|fixa|fixare|fix|resolve)\s+(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:bug|errore|problema|error|issue)\b",
        r"\b(?:modifica|modificare|aggiorna|aggiornare|modify|update)\s+(?:il\s+|la\s+|i\s+|le\s+|questo\s+)?(?:codice|file|funzione|test|script|code)\b",
        r"\b(?:fai|esegui|perform|do|applica)\s+(?:il\s+)?(?:refactoring|refactor)\b",
        # Explicit delegation to coding agent
        r"(?<!\bla\s)(?<!\bdella\s)(?<!\bsulla\s)(?<!\bthe\s)\b(?:delega|delegare|delegate)\s+(?:il\s+lavoro|il\s+task|il\s+compito|lo\s+sviluppo|il\s+codice|questo|a\s+google\s+antigravity|ad\s+antigravity|a\s+claude|a\s+codex)\b",
        r"\b(?:usa|utilizza|use)\s+(?:esplicitamente\s+)?(?:google\s+)?(?:antigravity|claude code|codex)\b",
        r"\b(?:richiesta operativa diretta|esegui direttamente il lavoro)\b",
        # Imperative opening verb aimed at a concrete filesystem location: "Implement parser in /tmp/x",
        # "Refactor files in /Library" are work orders even without an explicit noun like "function".
        r"^\s*(?:per\s+favore\s+|please\s+)?(?:implement|implementa|refactor|rifattorizza|refattorizza|fix|correggi|risolvi|build|costruisci)\b[^?\n]{0,80}?\s(?:in|su|nel|nella|inside|within)\s+[`'\"(]?(?:/[\w.\-]+|[a-z]:[\\/][\w.\-])",
    ]

    has_actionable_coding_directive = any(re.search(pat, p_lower) for pat in actionable_coding_patterns)

    # Generic nouns ("progetto", "servizio", "script", "modulo", "tool") are ambiguous: "crea un progetto per
    # organizzare un viaggio" is not a coding request. They count only with a technical signal in the prompt.
    generic_creation_only = bool(re.search(
        r"\b(?:crea|creare|realizza|realizzare|sviluppa|sviluppare|costruisci|costruire|build|create|implementa|implementare|implement)\s+"
        r"(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:piccol[oa]\s+|nuov[oa]\s+|semplice\s+)?"
        r"(?:progetto|modulo|script|servizio|tool)\b", p_lower
    ))
    has_technical_context = bool(re.search(
        r"(?:\b(?:python|javascript|typescript|java|rust|golang|django|flask|fastapi|react|node|npm|pip|sql|database|backend|frontend|"
        r"api|cli|codice|code|software|programma|repository|repo|github|git|test|funzione|function|classe|class|endpoint|"
        r"antigravity|claude\s+code|codex)\b|\.(?:py|ts|tsx|js|jsx|rs|go|java|c|cpp|h|json|md)\b|(?:^|\s)/[\w.\-]+/[\w.\-/]+|(?:^|[\s`'\"(])[a-z]:[\\/][\w.\-]+)", p_lower
    ))
    if generic_creation_only and not has_technical_context:
        # Only the generic-noun pattern matched: re-evaluate the remaining, more specific patterns.
        has_actionable_coding_directive = any(
            re.search(pat, p_lower) for i, pat in enumerate(actionable_coding_patterns) if i != 0
        )

    # Opinions and questions about tools ("secondo te Codex è meglio…?") are not work orders,
    # even if they mention a verb like "scrivere test".
    is_opinion_inquiry = bool(re.search(
        r"\b(?:secondo\s+te|che\s+ne\s+pensi|cosa\s+ne\s+pensi|(?:è|e')\s+meglio|meglio\s+(?:usare|di|se)|quale\s+(?:è|e'|tra|dei|delle)|"
        r"dovrei|conviene|what\s+do\s+you\s+think|which\s+(?:is|one)\s+better|should\s+i)\b", p_lower
    ))

    # Explicit code mutation mandate (imperative directives to write, modify, fix, or build code)
    code_mutation_patterns = [
        r"\b(?:crea|creare|realizza|realizzare|costruisci|costruire|build|create)\s+(?:un[’'\s]|una\s+|a\s+|an\s+|the\s+|il\s+|la\s+|l[’'\s]|lo\s+|i\s+|le\s+|gli\s+)?(?:piccol[oa]\s+|nuov[oa]\s+|semplice\s+)?(?:applicazione|app|cli|progetto|modulo|script|servizio|tool|package|funzione|componente)\b",
        r"\b(?:implementa|implementare|scrivi|scrivere|aggiungi|aggiungere|write|implement|add)\s+.*(?:codice|funzione|metodo|classe|test|code|function)\b",
        r"\b(?:risolvi|risolvere|correggi|correggere|fixa|fixare|fix|resolve)\s+.*(?:bug|errore|problema|error)\b",
        r"\b(?:modifica|modificare|aggiorna|aggiornare)\s+.*(?:codice|file|funzione|test)\b",
        r"\b(?:fai|esegui|applica)\s+(?:il\s+)?(?:refactoring|refactor)\b",
        r"\b(?:richiesta operativa diretta|esegui direttamente il lavoro)\b",
        r"(?<!\bla\s)(?<!\bdella\s)(?<!\bsulla\s)(?<!\bthe\s)\b(?:delega|delegare|delegate)\s+(?:il\s+lavoro|il\s+task|il\s+compito|lo\s+sviluppo|il\s+codice|a\s+google\s+antigravity|ad\s+antigravity)\b",
    ]
    has_code_mutation_mandate = any(re.search(pat, p_lower) for pat in code_mutation_patterns)

    # Standalone coding triggers (fallback list - compound phrases to prevent false positives on conversational words)
    coding_triggers = [
        "implementa il codice", "scrivi codice", "scrivi il codice", "crea codice", "sviluppa la funzione",
        "crea una funzione", "crea la funzione", "crea funzione", "creare una funzione", "creare la funzione", "creare funzione",
        "aggiungi una funzione", "aggiungi la funzione", "aggiungi funzione", "aggiungi un metodo", "aggiungi metodo",
        "aggiungi un test", "aggiungi il test", "aggiungi i test", "aggiungi test", "scrivi test", "scrivi i test",
        "crea un test", "crea test", "creare un test", "creare test",
        "sviluppa il componente", "crea componente", "crea il componente", "crea un componente",
        "creare il componente", "creare componente", "creare un componente",
        "modifica il codice", "modifica codice",
        "fai refactoring", "fai il refactoring",
        "risolvi il bug", "risolvi bug", "fixa il bug", "fix bug",
        "correggi il bug", "correggi bug", "correggi il codice", "correggi codice",
        "implement function", "write code", "create code", "add tests", "write tests",
        "add a function", "add function", "add a test", "add test",
        "fix the bug", "implement component", "create component", "make tests pass",
    ]
    has_coding_trigger = has_actionable_coding_directive or any(re.search(r"\b" + re.escape(t) + r"\b", p_lower) for t in coding_triggers)

    has_agent_mention = any(k in p_lower for k in ["antigravity", "claude code", "codex"])
    agent_coding_words = ["codice", "code", "file", "sviluppa", "crea", "creare", "implementa", "fix", "test", "funzione", "componente", "component", "refactor", "bug"]
    has_agent_coding = has_agent_mention and any(re.search(r"\b" + re.escape(w) + r"\b", p_lower) for w in agent_coding_words)

    # Purely explanatory / informational / non-coding inquiry detection
    explanation_inquiry_patterns = [
        r"\b(?:spiegami|spiega|spiegarmi|spiegare|puoi spiegarmi|potresti spiegarmi|vorrei capire|fammi capire|aiutami a capire|dimmi come funziona|cosa fa|explain|explain why|tell me how|how does|what does)\b",
        r"\b(?:perché|perche|why)\b\s+(?:quest[oaie]|il|la|l[’']|lo|i|le|non|doesn't|does|is|are|it)\b",
        r"\b(?:qual è il motivo per cui|come mai)\b",
    ]
    is_explanation_inquiry = any(re.search(pat, p_lower) for pat in explanation_inquiry_patterns)
    is_definition_inquiry = bool(re.search(r"\b(?:cosa\s+(?:significa|vuol\s+dire|intendi)|che\s+(?:significa|vuol\s+dire)|definizione\s+di|what\s+does\s+.*mean|what\s+is\s+(?:the\s+meaning\s+of|a\s+refactor|refactoring))\b", p_lower))
    is_difference_inquiry = bool(re.search(r"\b(?:qual\s+[eè]\s+la\s+differenza|che\s+differenza|cosa\s+cambia|differenza\s+tra|difference\s+between)\b", p_lower))
    is_pricing_inquiry = bool(re.search(r"\b(?:quanto\s+costa|prezzo|costo|costi|how\s+much\s+(?:is|does\s+.*cost)|pricing)\b", p_lower))
    is_safety_or_scope_gate = bool(re.search(r"\b(?:finch[eé]|until|altri\s+file|other\s+files|prima\s+di\s+approvare|senza\s+approvazione)\b", p_lower))
    has_negative_coding_directive = False
    if not is_safety_or_scope_gate:
        has_negative_coding_directive = bool(re.search(
            r"\b(?:non\s+(?:fare|eseguire|applicare|implementare|modificare|lanciare|avviare|procedere|creare|toccare)\b(?:\s+(?:ora|adesso|il|la|alcun|alcuna|questo|nulla|niente))?.*?\b(?:solo|soltanto|dimmi|spiega|spiegami|rispondi|rischio|rischi|just|only|tell\s+me)\b|"
            r"don['’]?t\s+(?:do|perform|refactor|implement|modify|create|touch)\b.*?\b(?:just|only|tell\s+me|explain)\b|"
            r"non\s+(?:fare\s+refactoring|modificare|implementare)\s+(?:adesso|ora)\b)",
            p_lower
        ))
    is_fitness_context = bool(re.search(r"\b(?:allenament[oi]|workout|palestra|fitness|dieta|eserciz[io]|sport)\b", p_lower))

    is_purely_informational = (
        is_opinion_inquiry
        or is_definition_inquiry
        or is_difference_inquiry
        or is_pricing_inquiry
        or has_negative_coding_directive
        or is_fitness_context
        or (is_explanation_inquiry and not has_code_mutation_mandate)
    )


    reasons = tuple(
        name for name, flag in (
            ("definition", is_definition_inquiry), ("difference", is_difference_inquiry), ("pricing", is_pricing_inquiry),
            ("negative_directive", has_negative_coding_directive), ("fitness_context", is_fitness_context),
            ("opinion", is_opinion_inquiry), ("explanation", is_explanation_inquiry and not has_code_mutation_mandate),
        ) if flag
    )
    operational = (not is_purely_informational) and bool(has_coding_trigger or has_agent_coding)
    document_operation = False
    if operational and assess_document_operation(prompt) is not None:
        # The patterns above match "aggiorna il file": with a document as the object and no code anywhere, it is not coding.
        operational = False
        has_actionable_coding_directive = False
        has_coding_trigger = False
        document_operation = True
    # Operational by the rules, yet phrased as a question or a hesitation: settle it with a person/LLM, never by default.
    ambiguous = operational and (p_lower.rstrip().endswith("?") or bool(_HEDGE_RE.search(p_lower))) \
        and not re.match(r"^(?:puoi|potresti|riesci\s+a|can\s+you|could\s+you|please|per\s+favore)\b", p_lower)
    return CodingAssessment(
        operational=operational and not ambiguous,
        informational=bool(is_purely_informational),
        ambiguous=ambiguous,
        has_actionable_directive=bool(has_actionable_coding_directive),
        has_mutation_mandate=bool(has_code_mutation_mandate),
        has_coding_trigger=bool(has_coding_trigger),
        has_agent_coding=bool(has_agent_coding),
        informational_reasons=reasons,
        document_operation=document_operation,
    )
