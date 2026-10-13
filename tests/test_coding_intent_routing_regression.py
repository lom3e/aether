"""
Regression test suite for Coding Intent Routing and Execution Truthfulness.
Verifies Phase 3 requirements:
1. The full original FocusList prompt containing "perché" routes to coding.delegate.
2. Genuine explanatory inquiries remain informational (tier ANSWER).
3. Coding requests without explanatory terms route to coding.delegate.
4. Purely informational questions are not converted into coding executions.
5. If no real execution is created, Aether never represents the task as delegated or waiting for an agent.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from aether.core.execution import ExecutionResult
from aether.missions.models import ExecutionStatus
from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService
from aether.workspace.workspace import Workspace

FOCUSLIST_ORIGINAL_PROMPT = """Voglio realizzare una piccola applicazione Python chiamata **FocusList** nel progetto locale `__PROJECT_DIR__`.  **Usa esplicitamente Google Antigravity come coding agent ed esegui direttamente il lavoro.** Questa è una richiesta operativa diretta: ti sto autorizzando a implementare le funzionalità descritte qui sotto nel progetto indicato. Non chiedermi di approvare preventivamente il piano e non fermarti dopo aver generato una proposta. Pianifica e verifica internamente, quindi avvia la delega senza conferme ridondanti, nel rispetto delle policy applicabili.  ## Funzionalità  Crea una piccola applicazione CLI per gestire una lista di attività personali.  L'utente deve poter:  1. Aggiungere un'attività specificando il titolo. 2. Elencare tutte le attività, distinguendo quelle da completare da quelle completate. 3. Contrassegnare un'attività come completata tramite il suo ID. 4. Conservare le attività in un file JSON locale per mantenerle tra esecuzioni successive. 5. Ricevere messaggi comprensibili per input non valido o ID inesistenti.  Usa soltanto la libreria standard di Python, salvo che una dipendenza aggiuntiva sia davvero indispensabile.  ## File autorizzati  Lavora esclusivamente nel progetto `__PROJECT_DIR__`.  Puoi creare o modificare: - `focuslist.py` - `test_focuslist.py` - `README.md` - Un eventuale file JSON locale utilizzato dall'applicazione, se necessario.  Non modificare altri file, non lavorare sul repository Aether e non intervenire su altri progetti.  ## Test e qualità  Scrivi ed esegui test reali che verifichino:  - Aggiunta di attività. - Elenco delle attività. - Completamento tramite ID. - Gestione degli ID inesistenti. - Persistenza dei dati tra più operazioni. - Gestione degli input non validi.  I test devono utilizzare dati isolati e non dipendere da file personali. Esegui effettivamente i test con pytest, se disponibile, o con un runner Python appropriato.  ## Esecuzione tramite Google Antigravity  Delega il lavoro a Google Antigravity. Non simulare l'esecuzione e non considerare sufficiente la generazione di un piano o di un elenco di modifiche previste.  Monitora la sessione fino a quando il lavoro è realmente terminato. Se Antigravity richiede un'autorizzazione tecnica indispensabile, Aether deve mostrarmi quale operazione la richiede e perché; non dichiarare il task completato mentre l'agente è in attesa.  Non sostituire automaticamente Google Antigravity con un altro provider.  ## Verifica del completamento  Prima di dichiarare il successo:  1. Controlla che i file previsti esistano davvero. 2. Verifica il diff Git e i file effettivamente modificati. 3. Verifica che l'applicazione implementi le funzionalità richieste. 4. Esegui i test e controlla il loro risultato effettivo. 5. Verifica che nessun file fuori dal perimetro sia stato modificato. 6. Raccogli le evidenze reali restituite dall'agente.  Se il codice non è stato modificato o le verifiche falliscono, segnala correttamente il problema. Il successo dei soli test preesistenti non dimostra che la nuova funzionalità sia stata implementata.  ## Risultato finale  Mostrami un unico riepilogo chiaro con: - Stato effettivo della missione. - Conferma del provider utilizzato. - File creati o modificati realmente. - Sintesi delle funzionalità implementate. - Comando di test eseguito e risultato. - Eventuali errori o verifiche non completate.  Non ripetere il piano iniziale nel riepilogo finale, non mostrare istruzioni di attesa approvazione se il lavoro è terminato e non dichiarare verificato ciò che non è stato controllato.  Non creare commit e non eseguire push.  **Obiettivo: completare davvero FocusList attraverso Aether e Google Antigravity, senza conferme generiche superflue e con evidenze verificabili del risultato.**"""


@pytest.fixture
def service():
    return PersonalAgentService(workspace=MagicMock(), store=MagicMock())


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Workspace.init(Path(tmp_dir), name="test_routing_ws")
        yield ws
        ws.close()


def test_focuslist_original_prompt_classified_as_operational_coding(service, tmp_path):
    """1. The full original FocusList prompt containing 'perché' is classified as coding.delegate."""
    project_dir = tmp_path / "aether-e2e-smoke"  # a real directory on every platform (the original used a macOS /private/tmp path)
    project_dir.mkdir()
    intent = service.classify_intent(FOCUSLIST_ORIGINAL_PROMPT.replace("__PROJECT_DIR__", str(project_dir)))

    assert intent.tier == IntentTier.ACT
    assert intent.action_id == "coding.delegate"
    assert getattr(intent, "intent_type", None) == "coding"
    assert intent.action_args.get("provider_id") == "antigravity"
    assert Path(intent.action_args.get("project_path")) == project_dir.resolve()

    ctx_files = intent.action_args.get("context_files") or []
    assert "focuslist.py" in ctx_files
    assert "test_focuslist.py" in ctx_files
    assert "README.md" in ctx_files


def test_true_explanation_inquiry_remains_informational(service):
    """2. Genuine explanatory inquiries remain informational (tier ANSWER) without coding action."""
    explanatory_prompts = [
        "Spiegami perché questo codice non funziona",
        "Perché il test in test_calculator.py fallisce?",
        "Nel file calculator.py, puoi spiegarmi cosa fa la funzione add?",
        "Come funziona l'algoritmo in focuslist.py?",
        "Spiegami perché Antigravity non completa il task",
        "Vorrei capire perché la funzione restituisce None invece di un intero",
        "Why does this function throw an IndexError?",
    ]

    for p in explanatory_prompts:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ANSWER, f"Prompt '{p}' should be ANSWER tier, got {intent.tier}"
        assert intent.action_id != "coding.delegate", f"Prompt '{p}' should not be coding.delegate"
        assert getattr(intent, "intent_type", None) in ("informational", "conversation")


def test_coding_request_without_explanation_terms_routes_to_coding(service):
    """3. Direct coding requests without explanatory terms route to coding.delegate."""
    coding_prompts = [
        "Nel progetto locale /tmp/demo crea una funzione subtract(a, b) in calculator.py e aggiungi i test in test_calculator.py",
        "Risolvi il bug in calculator.py",
        "Aggiungi un test per la divisione per zero in test_calculator.py",
        "Implementa un'applicazione CLI per gestire le note nel repository /tmp/notes",
        "Modifica il codice di auth.py per supportare token JWT",
        "Fai refactoring del modulo parser.py",
    ]

    for p in coding_prompts:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ACT, f"Prompt '{p}' should be ACT tier, got {intent.tier}"
        assert intent.action_id == "coding.delegate", f"Prompt '{p}' should be coding.delegate, got {intent.action_id}"


def test_subordinate_perche_in_coding_request_does_not_block_delegation(service):
    """Subordinate clauses with 'perché' inside operational requests must not block delegation."""
    prompts_with_perche = [
        "Crea una funzione subtract in calculator.py perché attualmente manca l'operazione di sottrazione",
        "Nel progetto /tmp/app realizza una CLI per le attività perché ho bisogno di organizzarmi",
        "Risolvi il bug in parser.py perché il json non viene decodificato correttamente",
        "Aggiungi i test per math_utils.py perché la copertura attuale è insufficiente",
    ]

    for p in prompts_with_perche:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ACT, f"Prompt '{p}' should be ACT tier, got {intent.tier}"
        assert intent.action_id == "coding.delegate", f"Prompt '{p}' should be coding.delegate, got {intent.action_id}"


def test_purely_informational_question_not_transformed_into_coding(service):
    """4. Purely general informational queries must never be transformed into coding executions."""
    informational_prompts = [
        "Chi è Ada Lovelace?",
        "Qual è la capitale dell'Italia?",
        "Come si installa Python su macOS?",
        "Cos'è una closure nella programmazione funzionale?",
    ]

    for p in informational_prompts:
        intent = service.classify_intent(p)
        assert intent.tier == IntentTier.ANSWER
        assert intent.action_id is None
        assert getattr(intent, "intent_type", None) == "informational"


def test_no_execution_cannot_claim_delegation_or_waiting_for_agent(temp_workspace):
    """5. When no real action execution is created, Aether cannot represent the request as delegated or waiting for an agent."""
    personal_svc = temp_workspace.personal

    # Mock runtime to simulate an internal LLM hallucinating active delegation text
    fake_hallucinated_text = (
        "Ho ricevuto l'autorizzazione operativa. Inizio immediatamente la delega a Google Antigravity per lo sviluppo "
        "della tua applicazione. L'agente è stato attivato per creare i file. Attendo il feedback dell'agente..."
    )
    mock_runtime = MagicMock()
    mock_runtime.execute.return_value = ExecutionResult(
        success=True,
        status=ExecutionStatus.COMPLETED,
        output=fake_hallucinated_text,
    )
    personal_svc.runtime = mock_runtime

    # Send an informational prompt (e.g. asking for explanation)
    res = personal_svc.process_prompt(
        workspace_id=temp_workspace.name,
        prompt="Spiegami perché la delega ad Antigravity potrebbe impiegare molto tempo",
    )

    # 1. Action execution ID must be None
    assert res.action_execution_id is None
    assert res.mission_id is None

    # 2. Content must be sanitized and NEVER contain deceptive waiting strings
    assert "Inizio immediatamente la delega" not in res.content
    assert "Attendo il feedback dell'agente" not in res.content
    assert "L'agente è stato attivato" not in res.content
    assert "informativa e non ha avviato un task di esecuzione reale" in res.content
