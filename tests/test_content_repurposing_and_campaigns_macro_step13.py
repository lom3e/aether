"""Comprehensive test suite for Macro Step 13:
Social Media Workforce & Content Repurposing Engine (including Campaigns & Action Integration).
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest
from starlette.requests import Request

from aether.content.models import (
    Campaign,
    ContentItem,
    ContentStatus,
    ContentTone,
    PlatformType,
    RepurposeRequest,
    RepurposeResult,
    RepurposedVariant,
)
from aether.content.repurposer import ContentRepurposingEngine
from aether.content.store import ContentStore
from aether.workspace.workspace import Workspace
from aether.actions.registry import ActionRegistry
from aether.actions.executor import ActionExecutor
from aether.personal.service import PersonalAgentService
from aether.server.routes import (
    RepurposePayload,
    CreateCampaignPayload,
    ScheduleVariantPayload,
    repurpose_content_route,
    create_campaign_route,
    list_campaigns_route,
    get_campaign_route,
    list_content_items_route,
    list_content_variants_route,
    schedule_variant_route,
    publish_variant_route,
)


SAMPLE_ARTICLE = """
# Scaling Autonomous Agent Workforces: Lessons from 10,000 Operations

Autonomous multi-agent systems are revolutionizing modern engineering workflows. However, running agents at scale reveals critical architectural challenges.

Key takeaways and lessons learned:
* True leverage comes from deterministic state machines combined with adaptive model routing.
* Resilient fallback chains prevent cascading failures when upstream LLM providers suffer degradation.
* Deep knowledge ingestion with SQLite FTS5 BM25 search outperforms brittle naive vector lookups.
* Continuous workforce memory injection prevents knowledge regression across distributed teams.
* Every mission deliverable must produce verifiable, replayable flight recorder lineage.

By standardizing on self-healing execution and strict safety policies, engineering velocity increased by 400% while reducing manual triage time to near zero.
"""


def test_content_models_and_enums():
    """Verify serialization and deserialization of Content models."""
    variant = RepurposedVariant(
        item_id="item-test-1",
        platform=PlatformType.TWITTER_THREAD,
        title="Twitter Breakdown",
        body="Sample thread content",
        thread_tweets=["Tweet 1 (1/2)", "Tweet 2 (2/2)"],
        hashtags=["#AI", "#Tech"],
        call_to_action="Follow for more",
        character_count=180,
        compliance_passed=True,
        engagement_score=92.5,
        status=ContentStatus.DRAFT,
    )
    d = variant.to_dict()
    assert d["platform"] == "twitter_thread"
    assert d["status"] == "draft"
    assert len(d["thread_tweets"]) == 2

    restored = RepurposedVariant.from_dict(d)
    assert restored.platform == PlatformType.TWITTER_THREAD
    assert restored.status == ContentStatus.DRAFT
    assert restored.engagement_score == 92.5

    campaign = Campaign(
        name="Q3 Growth Blitz",
        description="Scaling Aether workforce awareness",
        target_audience="Developers and CTOs",
        objectives=["Publish 20 threads", "Deliver 5 newsletters"],
        tags=["growth", "ai"],
    )
    camp_d = campaign.to_dict()
    assert camp_d["name"] == "Q3 Growth Blitz"
    assert len(camp_d["objectives"]) == 2
    camp_restored = Campaign.from_dict(camp_d)
    assert camp_restored.name == campaign.name


def test_repurposer_engine_linkedin():
    """Verify LinkedIn generation with hook, structured takeaways, CTA and character limit."""
    engine = ContentRepurposingEngine()
    var = engine.repurpose_for_linkedin(
        source_text=SAMPLE_ARTICLE,
        title="Scaling Autonomous Agent Workforces",
        tone=ContentTone.THOUGHT_LEADERSHIP,
    )
    assert var.platform == PlatformType.LINKEDIN
    assert "Scaling Autonomous Agent Workforces" in var.title
    assert "Most teams struggle" in var.body
    assert "👉" in var.body or "📌" in var.body
    assert "#AI" in var.body or "#" in var.body
    assert var.call_to_action != ""
    assert var.compliance_passed is True
    assert var.character_count <= 3000
    assert var.engagement_score >= 60.0


def test_repurposer_engine_twitter_thread():
    """Verify Twitter Thread generation with numbered tweets strictly <= 280 chars."""
    engine = ContentRepurposingEngine()
    var = engine.repurpose_for_twitter_thread(
        source_text=SAMPLE_ARTICLE,
        title="Scaling Autonomous Agent Workforces",
        tone=ContentTone.PUNCHY_VIRAL,
    )
    assert var.platform == PlatformType.TWITTER_THREAD
    assert len(var.thread_tweets) >= 3
    # Check that EVERY single tweet is <= 280 characters
    for idx, tweet in enumerate(var.thread_tweets):
        assert len(tweet) <= 280, f"Tweet {idx + 1} exceeds 280 characters ({len(tweet)} chars): {tweet}"
        assert f"({idx + 1}/{len(var.thread_tweets)})" in tweet

    assert var.compliance_passed is True
    assert var.compliance_notes == []
    assert var.engagement_score >= 70.0


def test_repurposer_engine_newsletter_and_video():
    """Verify Newsletter and Video Script adapters."""
    engine = ContentRepurposingEngine()

    # Newsletter
    nl = engine.repurpose_for_newsletter(SAMPLE_ARTICLE, "Scaling Agent Workforces")
    assert nl.platform == PlatformType.NEWSLETTER
    assert "**Subject:**" in nl.body
    assert "## The Big Picture" in nl.body
    assert nl.call_to_action != ""

    # Video Script
    vs = engine.repurpose_for_video_script(SAMPLE_ARTICLE, "Scaling Agent Workforces")
    assert vs.platform == PlatformType.VIDEO_SCRIPT
    assert "HOOK" in vs.body
    assert "Visual:" in vs.body
    assert "Spoken:" in vs.body
    assert vs.estimated_read_time_sec >= 20


def test_content_store_sqlite_crud():
    """Verify SQLite persistence for Campaigns, Items, and Variants."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "content.db"
        store = ContentStore(db_path)

        # 1. Campaign
        camp = Campaign(
            name="Product Launch 2.0",
            description="Campaign description",
            target_audience="Tech Leads",
            objectives=["Reach 10k readers"],
            tags=["launch", "v2"],
        )
        saved_camp = store.create_campaign(camp)
        assert saved_camp.id == camp.id

        retrieved_camp = store.get_campaign(camp.id)
        assert retrieved_camp is not None
        assert retrieved_camp.name == "Product Launch 2.0"
        assert retrieved_camp.tags == ["launch", "v2"]

        # 2. Content Item
        item = ContentItem(
            campaign_id=camp.id,
            title="Launch Manifesto",
            source_text=SAMPLE_ARTICLE,
            content_type="article",
        )
        saved_item = store.save_content_item(item)
        assert saved_item.id == item.id

        retrieved_item = store.get_content_item(item.id)
        assert retrieved_item is not None
        assert retrieved_item.campaign_id == camp.id

        # 3. Variants
        engine = ContentRepurposingEngine()
        res = engine.repurpose(
            RepurposeRequest(
                source_text=SAMPLE_ARTICLE,
                title="Launch Manifesto",
                campaign_id=camp.id,
            )
        )
        for var in res.variants:
            var.item_id = item.id
            store.save_variant(var)

        variants_all = store.list_variants(item_id=item.id)
        assert len(variants_all) >= 4

        # 4. Status update
        v0 = variants_all[0]
        assert v0.status == ContentStatus.DRAFT
        updated = store.update_variant_status(v0.id, ContentStatus.SCHEDULED, scheduled_at="2026-10-01T12:00:00Z")
        assert updated is not None
        assert updated.status == ContentStatus.SCHEDULED
        assert updated.scheduled_at == "2026-10-01T12:00:00Z"

        # List by status
        scheduled_list = store.list_variants(status="scheduled")
        assert len(scheduled_list) == 1
        assert scheduled_list[0].id == v0.id


def test_workspace_content_properties():
    """Verify Workspace integration for content store and engine."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="content-test-ws")
        assert ws.content is not None
        assert isinstance(ws.content, ContentStore)
        assert ws.content_engine is not None
        assert isinstance(ws.content_engine, ContentRepurposingEngine)


def test_action_executor_content_actions():
    """Verify ActionExecutor running content repurposing and campaign actions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="action-content-ws")
        executor = ws.actions

        # 1. content.create_campaign
        res_camp = executor.execute(
            "content.create_campaign",
            ws.id,
            {"name": "Autumn Expansion", "description": "Workforce campaign", "objectives": ["Goal A"]},
        )
        assert res_camp.status.value == "success"
        camp_data = res_camp.output_data["campaign"]
        camp_id = camp_data["id"]
        assert camp_data["name"] == "Autumn Expansion"

        # 2. content.repurpose
        res_rep = executor.execute(
            "content.repurpose",
            ws.id,
            {
                "source_text": SAMPLE_ARTICLE,
                "title": "Autonomous Workforce Guide",
                "campaign_id": camp_id,
                "target_platforms": ["linkedin", "twitter_thread"],
            },
        )
        assert res_rep.status.value == "success"
        variants = res_rep.output_data["variants"]
        assert len(variants) == 2
        var_id = variants[0]["id"]

        # 3. content.list_campaigns
        res_list_camps = executor.execute("content.list_campaigns", ws.id, {})
        assert res_list_camps.status.value == "success"
        assert len(res_list_camps.output_data["campaigns"]) >= 1

        # 4. content.schedule_variant
        res_sched = executor.execute(
            "content.schedule_variant",
            ws.id,
            {"variant_id": var_id, "scheduled_at": "2026-11-15T09:00:00Z"},
        )
        assert res_sched.status.value == "success"
        assert res_sched.output_data["variant"]["status"] == "scheduled"


def test_personal_companion_content_intents():
    """Verify PersonalCompanion detects repurpose and campaign intents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="personal-content-ws")
        service = PersonalAgentService(
            store=ws.personal_store,
            action_executor=ws.actions,
            activity_service=ws.activity,
        )

        # 1. Repurpose intent
        intent_rep = service.classify_intent("repurpose this blog post into twitter thread and linkedin")
        assert intent_rep.action_id == "content.repurpose"

        # 2. Campaign create intent
        intent_camp = service.classify_intent("crea una nuova campagna marketing per il lancio")
        assert intent_camp.action_id == "content.create_campaign"

        # 3. Campaign list intent
        intent_list = service.classify_intent("mostra le campagne social attive")
        assert intent_list.action_id == "content.list_campaigns"


class DummyAppState:
    def __init__(self, workspace):
        self.workspace = workspace


class DummyApp:
    def __init__(self, workspace):
        self.state = DummyAppState(workspace)


@pytest.mark.asyncio
async def test_fastapi_content_routes():
    """Verify all Content Repurposing and Campaign FastAPI route handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Workspace.get_or_init(tmpdir, name="routes-content-ws")
        app = DummyApp(ws)
        req = Request(scope={"type": "http", "app": app})

        # 1. Create Campaign
        camp_payload = CreateCampaignPayload(
            name="Developer Sprint Campaign",
            description="Campaign for dev community",
            objectives=["Post weekly insights"],
            tags=["dev", "sprint"],
        )
        camp_res = await create_campaign_route(req, camp_payload)
        assert camp_res["name"] == "Developer Sprint Campaign"
        camp_id = camp_res["id"]

        # 2. Get Campaign
        retrieved_camp = await get_campaign_route(req, camp_id)
        assert retrieved_camp["id"] == camp_id

        # 3. List Campaigns
        camps_res = await list_campaigns_route(req)
        assert len(camps_res) >= 1

        # 4. Repurpose Content
        rep_payload = RepurposePayload(
            source_text=SAMPLE_ARTICLE,
            title="Scaling Agent Workforces",
            target_platforms=["linkedin", "twitter_thread", "newsletter"],
            tone="thought_leadership",
            campaign_id=camp_id,
        )
        rep_res = await repurpose_content_route(req, rep_payload)
        assert "item" in rep_res
        assert len(rep_res["variants"]) == 3
        var_id = rep_res["variants"][0]["id"]

        # 5. List Content Items
        items_res = await list_content_items_route(req, campaign_id=camp_id)
        assert len(items_res) == 1

        # 6. List Variants
        vars_res = await list_content_variants_route(req, item_id=rep_res["item"]["id"])
        assert len(vars_res) == 3

        # 7. Schedule Variant
        sched_res = await schedule_variant_route(
            req, var_id, ScheduleVariantPayload(scheduled_at="2026-10-15T10:00:00Z")
        )
        assert sched_res["status"] == "scheduled"
        assert sched_res["scheduled_at"] == "2026-10-15T10:00:00Z"

        # 8. Publish Variant
        pub_res = await publish_variant_route(req, var_id)
        assert pub_res["status"] == "published"
        assert pub_res["published_at"] is not None
