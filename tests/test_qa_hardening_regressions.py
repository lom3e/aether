"""
Regressions for the QA pass on the personal assistant: route shadowing, explicit memory, question-vs-mission routing,
client entity extraction and goal-specific proposals. All deterministic (no network, no real provider).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.routing import Match

from aether.personal.models import IntentTier
from aether.personal.service import PersonalAgentService, extract_memory_statement, is_information_question
from aether.personal.store import PersonalStore


@pytest.fixture
def service(tmp_path: Path) -> PersonalAgentService:
    return PersonalAgentService(store=PersonalStore(db_path=str(tmp_path / "personal.db")))


def _first_matching_route(router, method: str, path: str):
    scope = {"type": "http", "method": method, "path": path, "root_path": "", "headers": []}
    for route in router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    return None


class TestRouteOrder:
    @pytest.mark.parametrize("path", [
        "/automations/suggestions",
        "/automations/history",
        "/automations/watchers",
        "/automations/scheduler/health",
    ])
    def test_static_automation_paths_are_not_shadowed_by_the_id_route(self, path):
        from aether.server.routes import router

        route = _first_matching_route(router, "GET", path)
        assert route is not None
        assert "{automation_id}" not in route.path, f"{path} is captured by {route.path}"


class TestExplicitMemory:
    @pytest.mark.parametrize("prompt,fact", [
        ("Ricorda che il mio cliente principale si chiama Rossi e vuole report settimanali", "il mio cliente principale si chiama Rossi e vuole report settimanali"),
        ("Ricordati che il referente è Laura Verdi", "il referente è Laura Verdi"),
        ("remember that my favourite format is PDF", "my favourite format is PDF"),
        ("Per favore, tieni a mente: il venerdì non lavoro", "il venerdì non lavoro"),
    ])
    def test_explicit_memory_statements_are_extracted(self, prompt, fact):
        assert extract_memory_statement(prompt) == fact

    @pytest.mark.parametrize("prompt", [
        "Ricordami di chiamare Rossi domani",       # a reminder, not a fact
        "Ti ricordi cosa ho detto ieri?",
        "Cosa ricordi del cliente Rossi?",
        "Ricorda",
    ])
    def test_reminders_and_questions_are_not_memory_statements(self, prompt):
        assert extract_memory_statement(prompt) is None

    def test_a_memory_statement_is_an_answer_not_a_mission(self, service):
        intent = service.classify_intent("Ricorda che il mio cliente principale si chiama Rossi e vuole report ogni settimana")
        assert intent.tier == IntentTier.ANSWER
        assert intent.action_id == "memory.save"
        assert intent.intent_type == "memory_save"


class TestQuestionsAreNotMissions:
    @pytest.mark.parametrize("prompt", [
        "Quando riceve il report il cliente Bianchi?",
        "In che formato e quando devo mandare il report al cliente Bianchi?",
        "Chi è il referente del cliente Bianchi?",
        "What does the client report contain?",
        "Cosa dice la procedura clienti su Bianchi?",
    ])
    def test_informational_questions_stay_answers(self, service, prompt):
        assert is_information_question(prompt)
        intent = service.classify_intent(prompt)
        assert intent.tier == IntentTier.ANSWER, intent.summary
        assert intent.intent_type == "informational"

    @pytest.mark.parametrize("prompt", [
        "Prepara un report su Lume & Miele",
        "Fai un'analisi di mercato per un negozio di candele",
        "Puoi preparare un report di sicurezza per il sistema?",
        "Vorrei un'analisi di mercato per le candele artigianali",
        "Analizza il mercato delle candele",
        "Research the competitive landscape for scented candles",
    ])
    def test_real_work_requests_are_still_delegated(self, service, prompt):
        intent = service.classify_intent(prompt)
        assert intent.tier == IntentTier.DELEGATE, intent.summary

    def test_sentence_that_merely_mentions_a_report_is_not_delegated(self, service):
        intent = service.classify_intent("Il report di ieri era chiaro")
        assert intent.tier == IntentTier.ANSWER


class TestClientEntityExtraction:
    def _resolve(self, prompt):
        from aether.planning.contracts import IntentRequest
        from aether.planning.resolver import ContextResolver

        resolver = ContextResolver(workspace=SimpleNamespace(client_store=None), intelligence_service=None, connection_service=None)
        refs, ambig, resolved = [], [], []
        resolver._resolve_client(
            IntentRequest(id="i1", workspace_id="w", raw_input=prompt, source_surface="test"),
            resolved, [], refs, ambig, [],
        )
        return resolved, refs, ambig

    def test_a_relative_pronoun_is_not_a_client(self):
        resolved, refs, ambig = self._resolve("Prepara un report per un cliente che vuole aggiornamenti settimanali")
        assert resolved == [] and refs == [] and ambig == []

    def test_a_named_client_is_recorded_but_never_blocks_the_plan(self):
        resolved, refs, ambig = self._resolve("Prepara un report per il cliente Rossi Srl")
        assert [e.display_name for e in resolved] == ["Rossi Srl"]
        assert refs == [] and ambig == []


class TestProposalIsSpecificToTheRequest:
    def test_steps_and_deliverables_refer_to_the_request(self, service):
        _, _, proposal, _ = service.create_intent_and_proposal(
            "Prepara un report sul mercato delle candele artigianali", workspace_id="default",
        )
        titles = " | ".join(s.title for s in proposal.proposed_steps)
        assert "candele" in titles
        assert "Environment & Preconditions" not in titles
        assert all("analysis_report.md" not in (d.file_path or "") for d in proposal.expected_deliverables)
        assert "candele" in proposal.expected_deliverables[0].title
        assert proposal.status.value != "needs_clarification"


# ---------------------------------------------------------------------------
# End to end with a real Workspace and a recording provider (the model is simulated; stores, routing, memory and
# context assembly are the real ones).
# ---------------------------------------------------------------------------
class _RecordingProvider:
    """Answers with a fixed text and records everything the model was shown."""

    model = "recording-model"

    def __init__(self, text: str = "Risposta del modello."):
        self.text = text
        self.seen: list[str] = []

    def generate(self, messages, tools=None, output_schema=None):
        from aether.providers.types import ProviderResponse

        self.seen.append("\n".join(str(getattr(m, "content", "")) for m in messages))
        return ProviderResponse(content=self.text, model=self.model, provider="recording")

    @property
    def capabilities(self):
        from aether.providers.capabilities import ProviderCapabilities

        return ProviderCapabilities()


@pytest.fixture
def real_workspace(tmp_path: Path):
    from aether.workspace.workspace import Workspace

    ws = Workspace.get_or_init(tmp_path / "ws_memory", "Memory QA")
    yield ws
    ws.close()


class TestMemoryAcrossSessions:
    def test_remembered_fact_is_stored_and_reaches_the_model_in_a_new_session(self, real_workspace):
        ws = real_workspace
        provider = _RecordingProvider("Il tuo cliente principale è Rossi.")
        ws.personal.provider = provider

        saved = ws.personal.process_prompt(
            workspace_id=ws.id,
            prompt="Ricorda che il mio cliente principale si chiama Rossi e vuole report settimanali",
        )
        assert saved.tier == IntentTier.ANSWER
        assert saved.mission_id is None and saved.action_execution_id is None
        assert saved.metadata["intent_type"] == "memory_save"
        assert "Rossi" in saved.content and saved.content.startswith("Fatto")
        assert provider.seen == [], "saving a memory must not need the model"

        memories = ws.memory.list_memories(ws.id, limit=10)
        assert [m.content for m in memories] == ["il mio cliente principale si chiama Rossi e vuole report settimanali"]
        assert memories[0].provenance.verification_status == "user_stated"

        # New session: nothing but the persisted memory can tell the model who the client is.
        answer = ws.personal.process_prompt(workspace_id=ws.id, prompt="Come si chiama il mio cliente principale?")
        assert answer.session_id != saved.session_id
        assert answer.tier == IntentTier.ANSWER
        assert any("Rossi" in shown for shown in provider.seen), "the stored memory was not given to the model"

    def test_the_graph_node_search_finds_the_remembered_fact(self, real_workspace):
        ws = real_workspace
        ws.personal.provider = _RecordingProvider()
        ws.personal.process_prompt(workspace_id=ws.id, prompt="Remember that the referent for Bianchi is Laura Verdi")
        found = ws.knowledge_graph.search_nodes(workspace_id=ws.id, query="Laura Verdi", node_types=None, limit=5)
        assert found and "Laura Verdi" in found[0][0].summary

    def test_english_request_gets_an_english_confirmation(self, real_workspace):
        ws = real_workspace
        ws.personal.provider = _RecordingProvider()
        reply = ws.personal.process_prompt(workspace_id=ws.id, prompt="Remember that my favourite format is PDF")
        assert reply.content.startswith("Got it")


class TestAnswerMetadata:
    def test_answer_reports_the_provider_and_model_that_produced_it(self, real_workspace):
        ws = real_workspace
        ws.personal.provider = _RecordingProvider("Ciao, tutto bene.")
        reply = ws.personal.process_prompt(workspace_id=ws.id, prompt="Chi è il referente del cliente Bianchi?")
        assert reply.metadata["intent_type"] == "informational"
        assert reply.metadata["model"] == "recording-model"
        assert reply.metadata["provider"] == "recording"


class TestModelFilter:
    def test_non_conversational_models_are_not_offered_as_chat_models(self):
        from aether.providers.model_filter import split_chat_models

        chat, excluded = split_chat_models([
            "qwen/qwen3.8-27b", "whisper-large-v3", "canopylabs/orpheus-v1-english",
            "meta-llama/llama-prompt-guard-2-22m", "openai/gpt-oss-120b", "openai/gpt-oss-safeguard-20b",
            "text-embedding-3-small", "gpt-4o",
        ])
        assert chat == ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "gpt-4o"]
        assert set(excluded) == {
            "whisper-large-v3", "canopylabs/orpheus-v1-english", "meta-llama/llama-prompt-guard-2-22m",
            "openai/gpt-oss-safeguard-20b", "text-embedding-3-small",
        }


class TestGroqRateLimitRetry:
    """HTTP 429 handling of the Groq provider (the HTTP layer is simulated; the retry logic is the real one)."""

    @staticmethod
    def _provider():
        from aether.providers.groq_provider import GroqProvider
        from aether.providers.types import ProviderConfig

        return GroqProvider(ProviderConfig(api_key="gsk_test_key_0000000000", model="m", timeout=5.0))

    @staticmethod
    def _http_429(retry_after):
        import io
        import urllib.error
        from email.message import Message as EmailMessage

        headers = EmailMessage()
        if retry_after is not None:
            headers["retry-after"] = str(retry_after)
        return urllib.error.HTTPError(
            "https://api.groq.test/chat/completions", 429, "Too Many Requests", headers,
            io.BytesIO(b'{"error": {"message": "Rate limit reached"}}'),
        )

    @staticmethod
    def _ok():
        import io
        import json

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        body = {"model": "m-real", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}}
        return _Resp(json.dumps(body).encode())

    def _patch(self, monkeypatch, outcomes):
        import aether.providers.groq_provider as gp

        sleeps, calls = [], []

        def fake_urlopen(req, timeout=None):
            calls.append(1)
            outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(gp.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(gp.time, "sleep", lambda s: sleeps.append(s))
        return sleeps, calls

    def test_retry_after_is_honoured_and_the_request_then_succeeds(self, monkeypatch):
        from aether.providers.types import Message

        sleeps, calls = self._patch(monkeypatch, [self._http_429(9), self._ok()])
        res = self._provider().generate([Message(role="user", content="hi")])
        assert res.content == "ok" and len(calls) == 2
        assert sleeps and 9 <= sleeps[0] <= 10

    def test_retries_are_bounded_and_the_final_error_is_typed(self, monkeypatch):
        from aether.providers.errors import RateLimitError
        from aether.providers.types import Message

        sleeps, calls = self._patch(monkeypatch, [self._http_429(1)])
        with pytest.raises(RateLimitError) as err:
            self._provider().generate([Message(role="user", content="hi")])
        assert len(calls) == 1 + self._provider().MAX_RATE_LIMIT_RETRIES
        assert err.value.retry_after == 1.0
        assert "gsk_test_key" not in str(err.value)

    def test_a_long_wait_such_as_a_daily_quota_is_reported_not_slept_through(self, monkeypatch):
        from aether.providers.errors import RateLimitError
        from aether.providers.types import Message

        sleeps, calls = self._patch(monkeypatch, [self._http_429(1800)])
        with pytest.raises(RateLimitError):
            self._provider().generate([Message(role="user", content="hi")])
        assert len(calls) == 1 and sleeps == []

    def test_missing_retry_after_uses_exponential_backoff(self, monkeypatch):
        from aether.providers.types import Message

        sleeps, calls = self._patch(monkeypatch, [self._http_429(None), self._http_429(None), self._ok()])
        assert self._provider().generate([Message(role="user", content="hi")]).content == "ok"
        assert [round(s) for s in sleeps] == [2, 4]


class TestCreatedDocumentsAreVisibleAndSafe:
    def test_document_created_from_chat_lands_in_the_files_folder_and_is_listed(self, real_workspace):
        from aether.personal.context import collect_workspace_deliverables

        from conftest import make_test_accepted_authority

        ws = real_workspace
        _, authority = make_test_accepted_authority(ws, constraints=["allow:files.create_document"], title="Doc")
        execution = ws.action_executor.execute(
            action_id="files.create_document", workspace_id=ws.id,
            input_data={"filename": "riepilogo.md", "content": "# Riepilogo\n\nContenuto."}, auto_approve=True,
            authority=authority,
        )
        assert execution.status.value == "succeeded", execution.error_message
        created = Path(execution.output_data["path"])
        assert created.parent == Path(ws.files_dir) and created.is_file()
        assert not (Path(ws.root) / "riepilogo.md").exists(), "user documents must not be written into the workspace root"
        listed = [d for d in collect_workspace_deliverables(ws) if d.file_path == str(created.resolve())]
        assert listed and listed[0].title == "riepilogo.md"

    @pytest.mark.asyncio
    async def test_companion_file_endpoints_only_serve_user_facing_folders(self, real_workspace):
        from fastapi import HTTPException
        from aether.server.routes import preview_companion_file

        ws = real_workspace
        doc = Path(ws.files_dir) / "nota.md"
        doc.write_text("# Nota\n\nciao", encoding="utf-8")
        req = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(workspace=ws)))

        ok = await preview_companion_file(req, path=str(doc))
        assert ok["preview_available"] and "ciao" in ok["content"]

        secret = Path(ws.root) / "personal.db"
        secret.write_bytes(b"not for the browser")
        for bad in (str(secret), str(Path(ws.files_dir) / ".." / "personal.db"), "/etc/hosts", "../../etc/hosts"):
            with pytest.raises(HTTPException) as err:
                await preview_companion_file(req, path=bad)
            assert err.value.status_code in (403, 404), bad


class TestClarificationFlow:
    PROMPT = "Leggi e aggiorna il file report_finale.md con i dati di vendita"

    def test_ambiguous_request_asks_then_resumes_with_the_answer(self, real_workspace):
        ws = real_workspace
        svc = ws.personal
        _, _, first, _ = svc.create_intent_and_proposal(self.PROMPT, ws.id)
        assert first.status.value == "needs_clarification"
        assert {c.context_key for c in first.clarification_requirements} >= {"file:report_finale.md"}
        with pytest.raises(ValueError):
            svc.accept_proposal(first.id, ws.id)          # a question is open: it cannot be accepted

        second, validation, _ = svc.answer_clarification(first.id, ws.id, "Il file va creato nuovo in files/, parti da zero")
        assert second.id != first.id
        assert second.status.value != "needs_clarification"
        assert "Il file va creato nuovo" in second.objective          # the answer is part of what the user will approve
        assert svc.store.get_proposal(first.id, workspace_id=ws.id).status.value == "superseded"
        accepted, authority = svc.accept_proposal(second.id, ws.id)
        assert accepted.status.value == "accepted" and authority.proposal_id == second.id

    def test_facts_aether_can_check_are_not_resolved_by_saying_so(self, real_workspace):
        ws = real_workspace
        svc = ws.personal
        _, _, first, _ = svc.create_intent_and_proposal("Manda un riepilogo su Slack al team", ws.id)
        assert first.status.value == "needs_clarification"
        second, _, _ = svc.answer_clarification(first.id, ws.id, "Slack è collegato, fidati")
        assert second.status.value == "needs_clarification", "a missing connection is not fixed by a sentence"

    def test_only_a_waiting_proposal_with_a_non_empty_answer_can_be_clarified(self, real_workspace):
        ws = real_workspace
        svc = ws.personal
        _, _, ready, _ = svc.create_intent_and_proposal("Prepara un report per il cliente Rossi", ws.id)
        assert ready.status.value != "needs_clarification", "an unverified client name must not block the plan"
        with pytest.raises(ValueError):
            svc.answer_clarification(ready.id, ws.id, "qualcosa")
        _, _, waiting, _ = svc.create_intent_and_proposal(self.PROMPT, ws.id)
        with pytest.raises(ValueError):
            svc.answer_clarification(waiting.id, ws.id, "   ")


    def test_rejecting_a_pending_or_waiting_proposal_is_persisted(self, real_workspace):
        ws = real_workspace
        svc = ws.personal
        _, _, waiting, _ = svc.create_intent_and_proposal(self.PROMPT, ws.id)
        _, _, pending, _ = svc.create_intent_and_proposal("Prepara un report per il cliente Rossi", ws.id)
        for proposal in (waiting, pending):
            revoked = svc.revoke_proposal(proposal.id, ws.id, reason="rejected by user")
            assert revoked.status.value == "revoked"
            with pytest.raises(ValueError):
                svc.accept_proposal(proposal.id, ws.id)

    def test_the_answer_is_posted_in_the_session_as_the_next_proposal(self, real_workspace):
        ws = real_workspace
        provider = _RecordingProvider()
        ws.personal.provider = provider
        first_msg = ws.personal.process_prompt(workspace_id=ws.id, prompt=self.PROMPT)
        first = first_msg.metadata["proposal"]
        assert first["status"] == "needs_clarification"
        _, _, message = ws.personal.answer_clarification(
            first["id"], ws.id, "Crea il file da zero", session_id=first_msg.session_id,
        )
        assert message is not None and message.session_id == first_msg.session_id
        assert message.metadata["supersedes_proposal_id"] == first["id"]
        assert message.metadata["proposal"]["status"] != "needs_clarification"
        history = [m.id for m in ws.personal.store.get_recent_messages(first_msg.session_id, limit=10)]
        assert message.id in history


class TestSseShutdown:
    @pytest.mark.asyncio
    async def test_open_event_stream_ends_cleanly_when_the_server_stops(self):
        import asyncio
        from aether.personal.events import PersonalEventHub

        hub = PersonalEventHub()
        stopping = {"flag": False}
        gen = hub.event_generator("ws", timeout_seconds=30.0, should_stop=lambda: stopping["flag"], poll_seconds=0.05)
        assert (await gen.__anext__()).startswith("event: connected")
        assert hub.subscriber_count("ws") == 1
        stopping["flag"] = True
        assert (await asyncio.wait_for(gen.__anext__(), 2)).startswith("event: shutdown")
        with pytest.raises(StopAsyncIteration):                     # the stream is over: the response is terminated properly
            await asyncio.wait_for(gen.__anext__(), 2)
        assert hub.subscriber_count("ws") == 0, "the subscriber must be released"

    @pytest.mark.asyncio
    async def test_events_still_flow_and_keepalives_are_still_sent(self):
        import asyncio
        from aether.personal.events import PersonalEventHub

        hub = PersonalEventHub()
        gen = hub.event_generator("ws", timeout_seconds=0.2, should_stop=lambda: False, poll_seconds=0.05)
        await gen.__anext__()
        assert (await asyncio.wait_for(gen.__anext__(), 2)) == ": ping\n\n"
        hub.publish("ws", "assistant_message", {"x": 1})
        chunk = await asyncio.wait_for(gen.__anext__(), 2)
        assert chunk.startswith("event: assistant_message")
        await gen.aclose()


class TestConcurrentAccess:
    def test_parallel_requests_in_one_session_lose_nothing_and_do_not_mix(self, real_workspace):
        from concurrent.futures import ThreadPoolExecutor

        ws = real_workspace
        ws.personal.provider = _RecordingProvider("ok")
        first = ws.personal.process_prompt(workspace_id=ws.id, prompt="Ciao")
        session_id = first.session_id

        def remember(i: int):
            return ws.personal.process_prompt(
                workspace_id=ws.id, prompt=f"Ricorda che il codice cliente {i} è CLI-{i:03d}", session_id=session_id,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(remember, range(16)))

        assert all(r.metadata["intent_type"] == "memory_save" and r.session_id == session_id for r in replies)
        stored = sorted(m.content for m in ws.memory.list_memories(ws.id, limit=100))
        assert stored == sorted(f"il codice cliente {i} è CLI-{i:03d}" for i in range(16))
        messages = ws.personal.store.get_recent_messages(session_id, limit=200)
        user_msgs = [m for m in messages if m.role == "user" and "CLI-" in m.content]
        assistant_msgs = [m for m in messages if m.role == "assistant" and m.metadata.get("intent_type") == "memory_save"]
        assert len(user_msgs) == 16 and len(assistant_msgs) == 16
        assert len({m.id for m in messages}) == len(messages), "duplicate message ids"
        # every confirmation names the fact of ITS request
        for r in replies:
            assert any(r.content.endswith(f"CLI-{i:03d}") for i in range(16))

    def test_two_sessions_do_not_leak_into_each_other(self, real_workspace):
        from concurrent.futures import ThreadPoolExecutor

        ws = real_workspace
        ws.personal.provider = _RecordingProvider("ok")
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.map(lambda p: ws.personal.process_prompt(workspace_id=ws.id, prompt=p),
                            ["Ciao, sono Anna", "Hello, I am Bob"])
        assert a.session_id != b.session_id
        a_hist = [m.content for m in ws.personal.store.get_recent_messages(a.session_id, limit=20)]
        b_hist = [m.content for m in ws.personal.store.get_recent_messages(b.session_id, limit=20)]
        assert any("Anna" in c for c in a_hist) and not any("Bob" in c for c in a_hist)
        assert any("Bob" in c for c in b_hist) and not any("Anna" in c for c in b_hist)


class TestAgentToolBudget:
    def test_an_agent_that_keeps_calling_tools_is_forced_to_answer_on_its_last_turn(self):
        from aether.agents.agent import Agent
        from aether.core.execution import Task, ToolCall
        from aether.providers.capabilities import ProviderCapabilities
        from aether.providers.types import Message, ProviderResponse

        class Searcher:
            """Calls a tool every turn, and answers only when no tool is offered."""
            capabilities = ProviderCapabilities(tools=True)
            model = "searcher"

            def __init__(self):
                self.offered: list[int] = []

            def generate(self, messages, tools=None, output_schema=None):
                self.offered.append(len(tools or []))
                if tools:
                    call = ToolCall(call_id=f"c{len(self.offered)}", tool_name="search_knowledge", arguments={"query": "x"})
                    msg = Message(role="assistant", content="", tool_calls=[call])
                    return ProviderResponse(content="", model="searcher", finish_reason="tool_calls", message=msg, provider="s")
                msg = Message(role="assistant", content="Ecco tre nomi: Miele d'Oro, Alveare, Fiamma Dolce.")
                return ProviderResponse(content=msg.content, model="searcher", finish_reason="stop", message=msg, provider="s")

        provider = Searcher()
        agent = Agent(name="a", role="r", provider=provider, max_turns=4)
        # the agent exposes a tool schema the way a configured workforce does
        orig_run_loop = agent._run_loop
        tools_schema = [{"name": "search_knowledge", "description": "d", "parameters": {"type": "object", "properties": {}}}]

        class _Engine:
            def execute_tool_calls(self, calls, ctx):
                from aether.core.execution import ToolResult
                return [ToolResult(call_id=c.call_id, output="nessun risultato") for c in calls]

        agent.execution_engine = _Engine()
        from aether.core.execution import AgentContext
        task = Task(instruction="Dammi tre nomi")
        ctx = AgentContext.from_context(agent._build_context(task), messages=[Message(role="user", content="Dammi tre nomi")])
        result = orig_run_loop(task, ctx, tools_schema)
        assert result.success, result.error
        assert "Miele d'Oro" in result.output
        assert provider.offered[-1] == 0 and all(n == 1 for n in provider.offered[:-1])


class TestGroqConnectionRetry(TestGroqRateLimitRetry):
    def test_a_momentary_network_drop_is_retried_then_succeeds(self, monkeypatch):
        import urllib.error
        from aether.providers.types import Message

        drop = urllib.error.URLError(OSError(8, "nodename nor servname provided, or not known"))
        sleeps, calls = self._patch(monkeypatch, [drop, self._ok()])
        assert self._provider().generate([Message(role="user", content="hi")]).content == "ok"
        assert len(calls) == 2 and len(sleeps) == 1

    def test_a_real_outage_is_reported_after_bounded_retries(self, monkeypatch):
        import urllib.error
        from aether.providers.errors import ProviderConnectionError
        from aether.providers.types import Message

        drop = urllib.error.URLError(OSError(8, "nodename nor servname provided, or not known"))
        sleeps, calls = self._patch(monkeypatch, [drop])
        with pytest.raises(ProviderConnectionError):
            self._provider().generate([Message(role="user", content="hi")])
        assert len(calls) == 1 + self._provider().MAX_CONNECTION_RETRIES


class TestInferredDeliverables:
    def test_only_files_that_exist_count_and_attempts_stay_in_the_audit_log(self, real_workspace):
        ws = real_workspace
        store = ws.missions
        mission = store.create_mission(title="T", objective="O", workspace_id=ws.id, milestones=[{"title": "S", "description": "d"}])
        (Path(ws.files_dir) / "report.md").write_text("# Report\n\ncontenuto", encoding="utf-8")
        for i, (tool, path) in enumerate([
            ("list_directory", "."), ("list_directory", "/"), ("read_file", "report.md"),
            ("write_file", "report.md"), ("write_file", "./report.md"),
            ("write_file", "ghost.md"),                       # attempted, refused: no file exists
        ]):
            store.log_conversation_activity(
                mission.id, "analyst", f"Executed {tool}", activity_type="tool_called",
                details={"tool_name": tool, "arguments": {"path": path}}, created_at=f"2026-10-14T10:00:0{i}+00:00",
            )
        listed = store.list_deliverables(mission.id)
        assert [(d.name, d.file_available) for d in listed] == [("report.md", True)]
        assert listed[0].size_bytes > 0
        # the failed attempt is history, not a result: it is still in the activity log
        with store._get_connection() as conn:
            logged = [r[0] for r in conn.execute("SELECT metadata FROM conversation_activities").fetchall()]
        assert any("ghost.md" in m for m in logged)

    def test_a_registered_record_whose_file_is_gone_is_kept_but_flagged_unavailable(self, real_workspace):
        from aether.missions.models import Deliverable

        ws = real_workspace
        store = ws.missions
        mission = store.create_mission(title="T", objective="O", workspace_id=ws.id, milestones=[{"title": "S", "description": "d"}])
        real = Path(ws.files_dir) / "ok.md"
        real.write_text("x", encoding="utf-8")
        store.add_deliverable(mission.id, Deliverable(id="d1", mission_id=mission.id, name="ok.md", path=str(real), status="verified"))
        store.add_deliverable(mission.id, Deliverable(id="d2", mission_id=mission.id, name="gone.md", path=str(Path(ws.files_dir) / "gone.md"), status="needs_revision"))
        by_name = {d.name: d for d in store.list_deliverables(mission.id)}
        assert by_name["ok.md"].file_available is True and by_name["gone.md"].file_available is False
        assert by_name["gone.md"].to_dict()["file_available"] is False
        assert by_name["gone.md"].status == "needs_revision"          # history untouched



class TestWorkforceToolAuthority:
    def _authority(self, ws, constraints):
        from conftest import make_test_accepted_authority

        return make_test_accepted_authority(ws, constraints=constraints, title="Delega")[1]

    def test_an_accepted_delegation_lets_its_agents_write_the_report_but_nothing_more(self, real_workspace):
        from aether.core.execution import ExecutionBoundary, UnauthorizedExecutionError

        ws = real_workspace
        auth = self._authority(ws, [f"allow:workforce.delegate,workforce.delegate:{ws.id}"])
        check = lambda act: ExecutionBoundary.validate_authority(
            authority=auth, workspace_id=ws.id, store=ws.personal_store, action_or_boundary=act)
        check("tool:write_file")
        check("tool:patch_file")
        for denied in ("tool:delete_file", "tool:send_email", "email.send", "coding.delegate"):
            with pytest.raises(UnauthorizedExecutionError):
                check(denied)

    def test_a_non_workforce_authority_does_not_gain_file_tools(self, real_workspace):
        from aether.core.execution import ExecutionBoundary, UnauthorizedExecutionError

        ws = real_workspace
        auth = self._authority(ws, ["allow:files.create_document"])
        with pytest.raises(UnauthorizedExecutionError):
            ExecutionBoundary.validate_authority(
                authority=auth, workspace_id=ws.id, store=ws.personal_store, action_or_boundary="tool:write_file")

    def test_knowledge_search_is_read_only(self, real_workspace):
        from aether.knowledge.tool import create_knowledge_tool
        from aether.tools.base import ToolClassification

        assert create_knowledge_tool(real_workspace.knowledge).classification == ToolClassification.READ_ONLY


class TestRepeatedToolCalls:
    def _run(self, monkeypatch, tool_name="search_knowledge", read_only=True, max_turns=10):
        from aether.agents.agent import Agent
        from aether.core.execution import AgentContext, Task, ToolCall, ToolResult
        from aether.providers.capabilities import ProviderCapabilities
        from aether.providers.types import Message, ProviderResponse

        class Looper:
            capabilities = ProviderCapabilities(tools=True)
            model = "looper"

            def __init__(self):
                self.calls = 0
                self.offered = []

            def generate(self, messages, tools=None, output_schema=None):
                self.offered.append(len(tools or []))
                if tools:
                    self.calls += 1
                    call = ToolCall(call_id=f"c{self.calls}", tool_name=tool_name, arguments={"query": "stessa domanda"})
                    return ProviderResponse(content="", model="looper", finish_reason="tool_calls", provider="l",
                                            message=Message(role="assistant", content="", tool_calls=[call]))
                msg = Message(role="assistant", content="Risposta finale.")
                return ProviderResponse(content=msg.content, model="looper", finish_reason="stop", message=msg, provider="l")

        executed = []

        class Engine:
            def execute_tool_calls(self, calls, ctx):
                executed.extend(c.call_id for c in calls)
                return [ToolResult(call_id=c.call_id, output="nessun risultato") for c in calls]

        monkeypatch.setattr(Agent, "_tool_is_read_only", staticmethod(lambda ctx, name: read_only))
        provider = Looper()
        agent = Agent(name="a", role="r", provider=provider, max_turns=max_turns, max_tool_calls=50)
        agent.execution_engine = Engine()
        task = Task(instruction="x")
        ctx = AgentContext.from_context(agent._build_context(task), messages=[Message(role="user", content="x")])
        result = agent._run_loop(task, ctx, [{"name": tool_name, "description": "d", "parameters": {"type": "object", "properties": {}}}])
        return result, provider, executed

    def test_the_same_read_only_call_is_executed_once_and_the_model_is_then_forced_to_answer(self, monkeypatch):
        result, provider, executed = self._run(monkeypatch)
        assert result.success and "Risposta finale" in result.output
        assert executed == ["c1"], "an identical read-only call must not be executed again"
        assert provider.calls <= 5, "the model was allowed to loop long after repeating itself"
        assert provider.offered[-1] == 0

    def test_repeating_a_mutating_call_is_never_suppressed(self, monkeypatch):
        result, provider, executed = self._run(monkeypatch, tool_name="write_file", read_only=False, max_turns=4)
        assert len(executed) >= 3, "writes are not cached: each one runs"


class TestTruncatedAnswers:
    def _agent(self, parts):
        from aether.agents.agent import Agent
        from aether.core.execution import AgentContext, Task
        from aether.providers.capabilities import ProviderCapabilities
        from aether.providers.types import Message, ProviderResponse

        class Chunked:
            capabilities = ProviderCapabilities()
            model = "chunked"
            seen = []

            def generate(self, messages, tools=None, output_schema=None):
                self.seen.append(messages[-1].content)
                text, reason = parts[min(len(self.seen) - 1, len(parts) - 1)]
                return ProviderResponse(content=text, model="chunked", finish_reason=reason, provider="c",
                                        message=Message(role="assistant", content=text))

        provider = Chunked()
        provider.seen = []
        agent = Agent(name="a", role="r", provider=provider)
        task = Task(instruction="x")
        ctx = AgentContext.from_context(agent._build_context(task), messages=[Message(role="user", content="x")])
        return agent._run_loop(task, ctx, []), provider

    def test_a_cut_off_answer_is_continued_and_joined(self):
        result, provider = self._agent([("Report: tre nomi: Alvea", "length"), ("re, Fiamma Dolce, Cera d'Oro.", "stop")])
        assert result.success and result.output == "Report: tre nomi: Alveare, Fiamma Dolce, Cera d'Oro."
        assert "cut off" in provider.seen[1]
        assert not result.metadata.get("truncated")

    def test_an_answer_still_cut_off_after_the_continuations_is_flagged(self):
        result, _ = self._agent([("a", "length")])
        assert result.success and result.metadata["truncated"] is True


class TestDocumentVersusCode:
    @pytest.mark.parametrize("prompt", [
        "Leggi e aggiorna il file report_finale.md con i dati di vendita",
        "Modifica il documento riepilogo.md aggiungendo le conclusioni",
        "Riscrivi note.txt in modo più breve",
        "Update the file notes.md with today's decisions",
        "Correggi il verbale.docx: manca la data",
    ])
    def test_editing_a_document_is_a_document_operation(self, service, prompt):
        intent = service.classify_intent(prompt)
        assert intent.action_id == "files.create_document" and intent.tier == IntentTier.DO, (prompt, intent.action_id)
        assert intent.action_args["update"] is True and intent.intent_type == "document_update"

    @pytest.mark.parametrize("prompt", [
        "Aggiorna il file parser.py per gestire None",
        "Correggi il bug in parser.py che causa crash",
        "Modifica il codice del modulo billing aggiungendo un test",
        "Aggiungi una funzione calculate_total(items) in billing.py e scrivi i test",
        "Aggiorna la funzione main in app.py",
    ])
    def test_editing_code_still_goes_to_the_coding_agent(self, service, prompt):
        intent = service.classify_intent(prompt)
        assert intent.action_id == "coding.delegate", (prompt, intent.action_id)

    @pytest.mark.parametrize("prompt", [
        "Come aggiorno il file report.md?",
        "Come si modifica un documento in Word?",
        "Cosa significa aggiornare un file di testo?",
    ])
    def test_questions_about_documents_are_answers(self, service, prompt):
        intent = service.classify_intent(prompt)
        assert intent.tier == IntentTier.ANSWER and intent.action_id is None, (prompt, intent.action_id)


class TestUpdateDocumentEndToEnd:
    def test_the_model_sees_the_current_document_and_the_updated_one_is_written(self, real_workspace):
        from conftest import make_test_accepted_authority

        ws = real_workspace
        doc = Path(ws.files_dir) / "report_finale.md"
        doc.write_text("# Report\n\nVendite Q1: 100\n", encoding="utf-8")
        provider = _RecordingProvider("# Report\n\nVendite Q1: 100\nVendite Q2: 150\n")
        ws.personal.provider = provider
        prompt = "Leggi e aggiorna il file report_finale.md con i dati di vendita Q2: 150"

        pending = ws.personal.process_prompt(workspace_id=ws.id, prompt=prompt)
        assert pending.metadata["status"] == "proposal_pending" and doc.read_text(encoding="utf-8").count("Q2") == 0
        _, auth = make_test_accepted_authority(ws, constraints=["allow:files.create_document"], title="Aggiorna report")
        done = ws.personal.process_prompt(workspace_id=ws.id, prompt=prompt, authority=auth)

        assert done.tier == IntentTier.DO
        assert any("Vendite Q1: 100" in shown for shown in provider.seen), "the model did not see the current document"
        assert doc.read_text(encoding="utf-8").strip() == "# Report\n\nVendite Q1: 100\nVendite Q2: 150"
        assert "aggiornato" in done.content
        assert not (Path(ws.root) / "report_finale.md").exists()


class TestInformationRequests:
    @pytest.mark.parametrize("prompt", [
        "Dimmi quando riceve il report il cliente Bianchi",
        "Spiegami come si prepara un report per il cliente",
        "Il report del cliente Bianchi quando va inviato?",
        "Sai dirmi chi è il referente del cliente Bianchi",
        "Tell me when the client report is due",
    ])
    def test_information_requests_are_answers(self, service, prompt):
        intent = service.classify_intent(prompt)
        assert intent.tier == IntentTier.ANSWER, (prompt, intent.summary)

    @pytest.mark.parametrize("prompt", [
        "Puoi preparare un report su Lume & Miele?",
        "Mi serve un'analisi di mercato per le candele",
    ])
    def test_work_requests_stay_missions_even_when_phrased_politely(self, service, prompt):
        assert service.classify_intent(prompt).tier == IntentTier.DELEGATE


class TestDocumentOverwriteSafety:
    PROMPT = "Aggiorna il file nota.md con le conclusioni"

    def _run(self, ws, provider, prompt=None):
        from conftest import make_test_accepted_authority

        ws.personal.provider = provider
        _, auth = make_test_accepted_authority(ws, constraints=["allow:files.create_document"], title="Aggiorna")
        return ws.personal.process_prompt(workspace_id=ws.id, prompt=prompt or self.PROMPT, authority=auth)

    def _provider(self, parts):
        from aether.providers.capabilities import ProviderCapabilities
        from aether.providers.types import ProviderResponse

        class P:
            capabilities = ProviderCapabilities()
            model = "p"

            def __init__(self):
                self.calls = 0

            def generate(self, messages, tools=None, output_schema=None):
                text, reason = parts[min(self.calls, len(parts) - 1)]
                self.calls += 1
                return ProviderResponse(content=text, model="p", finish_reason=reason, provider="p")

        return P()

    def test_a_truncated_draft_never_replaces_the_document(self, real_workspace):
        ws = real_workspace
        doc = Path(ws.files_dir) / "nota.md"
        original = "# Nota\n\nRiga originale importante.\n"
        doc.write_text(original, encoding="utf-8")
        reply = self._run(ws, self._provider([("# Nota\n\nRiga origin", "length")]))
        assert doc.read_text(encoding="utf-8") == original, "a fragment replaced the user's document"
        assert "cut off" in reply.content or "nothing was written" in reply.content

    def test_a_cut_off_draft_is_continued_and_the_old_version_is_kept(self, real_workspace):
        ws = real_workspace
        doc = Path(ws.files_dir) / "nota.md"
        doc.write_text("# Nota\n\nVecchio testo.\n", encoding="utf-8")
        self._run(ws, self._provider([("# Nota\n\nNuovo te", "length"), ("sto completo.", "stop")]))
        assert doc.read_text(encoding="utf-8") == "# Nota\n\nNuovo testo completo."
        versions = list((Path(ws.files_dir) / ".aether-versions").glob("nota.md.*"))
        assert len(versions) == 1 and versions[0].read_text(encoding="utf-8") == "# Nota\n\nVecchio testo.\n"

    def test_a_document_too_large_to_rewrite_is_left_untouched(self, real_workspace):
        ws = real_workspace
        doc = Path(ws.files_dir) / "nota.md"
        big = "x" * 70_000
        doc.write_text(big, encoding="utf-8")
        reply = self._run(ws, self._provider([("breve", "stop")]))
        assert doc.read_text(encoding="utf-8") == big and "too large" in reply.content

    def test_history_folder_is_not_listed_as_a_result(self, real_workspace):
        from aether.personal.context import collect_workspace_deliverables

        ws = real_workspace
        doc = Path(ws.files_dir) / "nota.md"
        doc.write_text("v1", encoding="utf-8")
        self._run(ws, self._provider([("v2", "stop")]))
        names = [d.title for d in collect_workspace_deliverables(ws)]
        assert names.count("nota.md") == 1 and not any(".aether-versions" in n or n.startswith("nota.md.") for n in names)


class TestDeliverableRegisteredOnce:
    def _mission(self, ws):
        mission = ws.missions.create_mission(title="T", objective="O", workspace_id=ws.id, milestones=[{"title": "S", "description": "d"}])
        self.execs = [ws.missions.create_execution(mission_id=mission.id, team_name=None).id for _ in range(2)]
        return mission

    def test_the_same_file_registered_twice_is_one_record_with_a_trace(self, real_workspace):
        from aether.missions.models import Deliverable

        ws = real_workspace
        mission = self._mission(ws)
        doc = Path(ws.files_dir) / "report.md"
        doc.write_text("contenuto", encoding="utf-8")
        for i, spelling in enumerate(["report.md", str(doc), "./report.md"]):
            ws.missions.add_deliverable(mission.id, Deliverable(
                id=f"del_{i}", mission_id=mission.id, execution_id=self.execs[0], name="report.md", path=spelling, status="draft"))
        listed = ws.missions.list_deliverables(mission.id)
        assert len(listed) == 1 and listed[0].id == "del_0"
        assert listed[0].metadata["registrations"] == ["del_0", "del_1", "del_2"]
        # status updates through any of the old objects reach the single record
        ws.missions.add_deliverable(mission.id, Deliverable(
            id="del_2", mission_id=mission.id, execution_id=self.execs[0], name="report.md", path="./report.md", status="verified"))
        assert [d.status for d in ws.missions.list_deliverables(mission.id)] == ["verified"]

    def test_different_executions_and_different_files_stay_separate(self, real_workspace):
        from aether.missions.models import Deliverable

        ws = real_workspace
        mission = self._mission(ws)
        for name in ("a.md", "b.md"):
            (Path(ws.files_dir) / name).write_text(name, encoding="utf-8")
        ws.missions.add_deliverable(mission.id, Deliverable(id="d1", mission_id=mission.id, execution_id=self.execs[0], name="a.md", path="a.md"))
        ws.missions.add_deliverable(mission.id, Deliverable(id="d2", mission_id=mission.id, execution_id=self.execs[1], name="a.md", path="a.md"))
        ws.missions.add_deliverable(mission.id, Deliverable(id="d3", mission_id=mission.id, execution_id=self.execs[0], name="b.md", path="b.md"))
        assert sorted(d.id for d in ws.missions.list_deliverables(mission.id)) == ["d1", "d2", "d3"]

    def test_duplicates_already_stored_are_shown_once_and_never_deleted(self, real_workspace):
        ws = real_workspace
        mission = self._mission(ws)
        doc = Path(ws.files_dir) / "report.md"
        doc.write_text("x", encoding="utf-8")
        with ws.missions._get_connection() as conn:
            for i, ts in enumerate(["2026-10-14T10:00:00+00:00", "2026-10-14T11:00:00+00:00"]):
                conn.execute(
                    "INSERT INTO mission_deliverables (id, mission_id, execution_id, milestone_id, name, path, type, size_bytes, sha256, status, metadata, created_at, updated_at) "
                    "VALUES (?, ?, ?, NULL, 'report.md', ?, 'document', 1, NULL, 'verified', '{}', ?, ?)",
                    (f"old_{i}", mission.id, self.execs[0], str(doc), ts, ts))
        listed = ws.missions.list_deliverables(mission.id)
        assert [d.id for d in listed] == ["old_1"] and set(listed[0].metadata["registrations"]) == {"old_0", "old_1"}
        with ws.missions._get_connection() as conn:
            assert conn.execute("SELECT COUNT(*) FROM mission_deliverables WHERE mission_id = ?", (mission.id,)).fetchone()[0] == 2

    def test_deliberate_versions_of_an_artifact_are_not_merged(self, real_workspace):
        from aether.missions.models import Deliverable

        ws = real_workspace
        mission = self._mission(ws)
        (Path(ws.files_dir) / "arch.md").write_text("v", encoding="utf-8")
        ws.missions.add_deliverable(mission.id, Deliverable(id="v1", mission_id=mission.id, execution_id=self.execs[0], name="arch.md", path="arch.md", metadata={"version": 1}))
        ws.missions.add_deliverable(mission.id, Deliverable(id="v2", mission_id=mission.id, execution_id=self.execs[0], name="arch.md", path="arch.md",
                                                             metadata={"version": 2, "parent_deliverable_id": "v1"}))
        assert sorted(d.id for d in ws.missions.list_deliverables(mission.id)) == ["v1", "v2"]
