"""Comprehensive test suite for Macro Step 14:
Client Work Automation, Client Review Portals, and Campaign Business Intelligence.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import pytest
from starlette.requests import Request

from aether.client.models import (
    BrandStyleGuide,
    CampaignBusinessIntelligence,
    ClientProfile,
    ClientReviewLink,
    ClientStatus,
    ReviewStatus,
)
from aether.client.automation import ClientAutomationEngine
from aether.client.store import ClientStore
from aether.content.models import Campaign, ContentItem, PlatformType, RepurposedVariant
from aether.workspace.workspace import Workspace
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    CreateClientPayload,
    CreateReviewLinkPayload,
    SubmitReviewDecisionPayload,
    create_client_route,
    get_client_route,
    list_clients_route,
    generate_client_report_route,
    create_review_link_route,
    get_review_by_token_route,
    submit_review_decision_route,
    get_campaign_bi_route,
)


def test_client_models_and_enums():
    """Verify serialization and deserialization of Client and BI models."""
    guide = BrandStyleGuide(
        tone="technical",
        keywords_include=["resilient", "deterministic", "autonomous"],
        keywords_exclude=["cheap", "magic"],
        target_audience="VP of Engineering & Architects",
        preferred_platforms=["linkedin", "newsletter"],
    )
    client = ClientProfile(
        name="Apex Systems",
        domain="apex.io",
        contact_email="vp@apex.io",
        status=ClientStatus.ACTIVE,
        brand_style=guide,
        monthly_budget_tokens=25_000_000,
        used_budget_tokens=3_500_000,
    )
    d = client.to_dict()
    assert d["status"] == "active"
    assert d["brand_style"]["tone"] == "technical"
    assert len(d["brand_style"]["keywords_include"]) == 3

    restored = ClientProfile.from_dict(d)
    assert restored.name == "Apex Systems"
    assert restored.brand_style.tone == "technical"
    assert restored.monthly_budget_tokens == 25_000_000

    rev = ClientReviewLink(
        client_id=client.id,
        deliverable_title="Q4 Architecture Campaign",
        status=ReviewStatus.PENDING,
    )
    assert rev.token.startswith("tok_")
    assert rev.status == ReviewStatus.PENDING


def test_client_store_sqlite_crud():
    """Verify SQLite operations for clients and review links."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "client.db"
        store = ClientStore(db_path)

        # 1. Client CRUD
        client = ClientProfile(
            name="Novacorp Global",
            domain="novacorp.com",
            contact_email="director@novacorp.com",
            brand_style=BrandStyleGuide(tone="bold"),
        )
        saved = store.create_client(client)
        assert saved.id == client.id

        retrieved = store.get_client(client.id)
        assert retrieved is not None
        assert retrieved.name == "Novacorp Global"
        assert retrieved.brand_style.tone == "bold"

        all_clients = store.list_clients()
        assert len(all_clients) == 1

        # 2. Review Link CRUD & Decision Gate
        engine = ClientAutomationEngine()
        rev = engine.create_review_link(
            client_id=client.id,
            deliverable_title="Sprint 1 Deliverables",
            deliverable_payload={"threads_count": 3, "articles_count": 1},
        )
        saved_rev = store.create_review_link(rev)
        assert saved_rev.token == rev.token

        by_token = store.get_review_by_token(rev.token)
        assert by_token is not None
        assert by_token.deliverable_title == "Sprint 1 Deliverables"
        assert by_token.status == ReviewStatus.PENDING

        # Client Approves
        approved = store.update_review_decision(
            token=rev.token,
            status=ReviewStatus.APPROVED,
            feedback="Looks fantastic, ready to publish.",
        )
        assert approved is not None
        assert approved.status == ReviewStatus.APPROVED
        assert approved.client_feedback == "Looks fantastic, ready to publish."
        assert approved.reviewed_at is not None


def test_client_automation_bi_and_executive_report():
    """Verify business intelligence calculation and executive report compilation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="bi-test-ws")

        # Create sample campaign and variants in ws.content
        camp = ws.content.create_campaign(
            Campaign(name="Cloud Migration Awareness", tags=["cloud", "enterprise"])
        )
        item = ws.content.save_content_item(
            ContentItem(campaign_id=camp.id, title="Migration Checklist", source_text="Full checklist...")
        )
        var1 = RepurposedVariant(
            item_id=item.id,
            platform=PlatformType.LINKEDIN,
            title="LinkedIn Migration Guide",
            hashtags=["#Cloud", "#Tech"],
            engagement_score=88.0,
            status="published",
        )
        var2 = RepurposedVariant(
            item_id=item.id,
            platform=PlatformType.TWITTER_THREAD,
            title="Twitter Migration Thread",
            thread_tweets=["Tweet 1 (1/2)", "Tweet 2 (2/2)"],
            hashtags=["#DevOps"],
            engagement_score=92.0,
            status="scheduled",
        )
        ws.content.save_variant(var1)
        ws.content.save_variant(var2)

        # 1. BI Generation
        engine = ws.client_engine
        bi = engine.generate_campaign_bi(camp.id, content_store=ws.content)
        assert bi.campaign_id == camp.id
        assert bi.total_assets == 2
        assert bi.published_assets == 1
        assert bi.scheduled_assets == 1
        assert bi.channel_breakdown["linkedin"] == 1
        assert bi.channel_breakdown["twitter_thread"] == 1
        assert bi.avg_engagement_score == 90.0
        assert bi.estimated_impressions > 0
        assert bi.estimated_roi_multiplier >= 3.0
        assert "Campaign Executive Summary" in bi.executive_summary

        # 2. Client Executive Report
        client = ws.client_store.create_client(
            ClientProfile(
                name="Vertex Labs",
                contact_email="ops@vertex.ai",
                active_campaign_ids=[camp.id],
                used_budget_tokens=4_200_000,
            )
        )
        report = engine.generate_client_executive_report(client, ws.client_store, ws.content)
        assert "Executive Client Report: Vertex Labs" in report
        assert "Monthly Budget:" in report
        assert "4,200,000" in report
        assert "Next Actions" in report


def test_action_executor_client_and_bi_actions():
    """Verify ActionExecutor running client automation and BI actions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="action-client-ws")
        executor = ws.actions

        # 1. client.create_profile
        res_create = executor.execute(
            "client.create_profile",
            ws.id,
            {
                "name": "Omni Health Tech",
                "domain": "omnihealth.com",
                "contact_email": "admin@omnihealth.com",
                "tone": "authoritative",
                "target_audience": "Healthcare CIOs",
            },
        )
        assert res_create.status.value == "success"
        client_data = res_create.output_data["client"]
        client_id = client_data["id"]
        assert client_data["name"] == "Omni Health Tech"

        # 2. client.list_profiles
        res_list = executor.execute("client.list_profiles", ws.id, {})
        assert res_list.status.value == "success"
        assert len(res_list.output_data["clients"]) >= 1

        # 3. client.create_review_link
        res_rev = executor.execute(
            "client.create_review_link",
            ws.id,
            {
                "client_id": client_id,
                "deliverable_title": "HIPAA Compliance Social Batch",
                "deliverable_type": "content_batch",
            },
        )
        assert res_rev.status.value == "success"
        rev_data = res_rev.output_data["review"]
        token = rev_data["token"]
        assert rev_data["status"] == "pending"

        # 4. client.submit_review
        res_sub = executor.execute(
            "client.submit_review",
            ws.id,
            {"token": token, "decision": "approved", "feedback": "Approved for dissemination."},
        )
        assert res_sub.status.value == "success"
        assert res_sub.output_data["review"]["status"] == "approved"

        # 5. client.generate_report
        res_rep = executor.execute(
            "client.generate_report",
            ws.id,
            {"client_id": client_id},
        )
        assert res_rep.status.value == "success"
        assert "Executive Client Report: Omni Health Tech" in res_rep.output_data["report_markdown"]

        # 6. analytics.get_campaign_bi
        res_bi = executor.execute(
            "analytics.get_campaign_bi",
            ws.id,
            {"campaign_id": "camp-test-analytics"},
        )
        assert res_bi.status.value == "success"
        assert res_bi.output_data["bi"]["campaign_id"] == "camp-test-analytics"


def test_personal_agent_client_and_bi_intents():
    """Verify PersonalAgentService detects client management, review links, reports, and BI intents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="personal-client-ws")
        service = PersonalAgentService(
            store=ws.personal_store,
            action_executor=ws.actions,
            activity_service=ws.activity,
        )

        # 1. Create client
        intent_cli = service.classify_intent("crea cliente chiamato BioTech Innovations")
        assert intent_cli.action_id == "client.create_profile"

        # 2. Review link
        intent_rev = service.classify_intent("invia per approvazione al cliente il deliverable Q3 Launch")
        assert intent_rev.action_id == "client.create_review_link"

        # 3. Client report
        intent_rep = service.classify_intent("genera report cliente per il quarterly review")
        assert intent_rep.action_id == "client.generate_report"

        # 4. Campaign BI
        intent_bi = service.classify_intent("mostra business intelligence della campagna camp-101")
        assert intent_bi.action_id == "analytics.get_campaign_bi"


class DummyAppState:
    def __init__(self, workspace):
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace):
        self.state = DummyAppState(workspace)


@pytest.mark.asyncio
async def test_fastapi_client_and_bi_routes():
    """Verify all Client and Business Intelligence FastAPI route handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="routes-client-ws")
        app = DummyApp(ws)
        req = Request(scope={"type": "http", "app": app})

        # 1. Create Client
        c_payload = CreateClientPayload(
            name="Quantum Computing Ltd",
            domain="quantum.tech",
            contact_email="lead@quantum.tech",
            tone="academic",
            target_audience="Physicists & Researchers",
        )
        c_res = await create_client_route(req, c_payload)
        assert c_res["name"] == "Quantum Computing Ltd"
        client_id = c_res["id"]

        # 2. Get Client
        retrieved_c = await get_client_route(req, client_id)
        assert retrieved_c["id"] == client_id

        # 3. List Clients
        clients_res = await list_clients_route(req)
        assert len(clients_res) >= 1

        # 4. Generate Client Report
        rep_res = await generate_client_report_route(req, client_id)
        assert rep_res["client_id"] == client_id
        assert "Executive Client Report: Quantum Computing Ltd" in rep_res["report_markdown"]

        # 5. Create Review Link
        rev_payload = CreateReviewLinkPayload(
            client_id=client_id,
            deliverable_title="Paper Summary Thread",
            deliverable_type="content_batch",
        )
        rev_res = await create_review_link_route(req, rev_payload)
        token = rev_res["token"]
        assert rev_res["status"] == "pending"

        # 6. Get Review by Token
        token_res = await get_review_by_token_route(req, token)
        assert token_res["token"] == token

        # 7. Submit Review Decision
        dec_payload = SubmitReviewDecisionPayload(
            decision="approved",
            feedback="All checks passed.",
        )
        dec_res = await submit_review_decision_route(req, token, dec_payload)
        assert dec_res["status"] == "approved"
        assert dec_res["client_feedback"] == "All checks passed."

        # 8. Get Campaign BI
        bi_res = await get_campaign_bi_route(req, "camp-routes-test")
        assert bi_res["campaign_id"] == "camp-routes-test"
        assert bi_res["estimated_roi_multiplier"] >= 2.5
