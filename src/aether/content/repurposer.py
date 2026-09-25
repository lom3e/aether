"""Content Repurposing Engine for multi-platform adaptation and social media workforce."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import uuid

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


class ContentRepurposingEngine:
    """Intelligent engine for analyzing source content and adapting it to multiple platform formats."""

    def __init__(self):
        pass

    def extract_key_points(self, text: str, max_points: int = 5) -> List[str]:
        """Extract main insights, bullet points, or high-value statements from source text."""
        points: List[str] = []
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # 1. Look for existing bullet points or numbered lists
        for line in lines:
            bullet_match = re.match(r"^[\*\-\•\>]|\d+\.\s*(.+)$", line)
            if bullet_match:
                cleaned = re.sub(r"^[\*\-\•\>]|\d+\.\s*", "", line).strip()
                # strip bolding
                cleaned = re.sub(r"^\*\*|\*\*$", "", cleaned).strip()
                if len(cleaned) > 15 and cleaned not in points:
                    points.append(cleaned)
                    if len(points) >= max_points:
                        return points

        # 2. Look for sentences containing insight markers
        sentences = re.split(r"(?<=[.!?])\s+", text)
        insight_markers = [
            "important", "crucial", "critical", "key", "learned", "result", "benefit",
            "feature", "build", "deliver", "solution", "advantage", "breakthrough",
            "revealed", "discovered", "fundamental", "metric", "improved", "strategy"
        ]
        for s in sentences:
            s_clean = s.strip().replace("\n", " ")
            if len(s_clean) > 25 and len(s_clean) < 220:
                if any(m in s_clean.lower() for m in insight_markers) and s_clean not in points:
                    points.append(s_clean)
                    if len(points) >= max_points:
                        return points

        # 3. Fallback: extract the most substantial distinct sentences
        for s in sentences:
            s_clean = s.strip().replace("\n", " ")
            if 30 <= len(s_clean) <= 180 and s_clean not in points:
                points.append(s_clean)
                if len(points) >= max_points:
                    break

        if not points:
            # Fallback when text is short
            points = [text.strip()[:160]] if text.strip() else ["Key operational milestone delivered."]

        return points[:max_points]

    def generate_hook(self, title: str, key_points: List[str], tone: ContentTone) -> str:
        """Generate high-conversion opening hooks tailored to tone."""
        clean_title = title.strip() or "This Breakthrough"
        first_point = key_points[0] if key_points else "what we learned building this."

        if tone == ContentTone.THOUGHT_LEADERSHIP:
            return (
                f"Most teams struggle to scale effectively. Here is how {clean_title} changes the game:"
            )
        elif tone == ContentTone.PUNCHY_VIRAL:
            return (
                f"Stop doing this the old way. {clean_title} just changed everything:\n\n"
                f"Here are the unvarnished facts 👇"
            )
        elif tone == ContentTone.EDUCATIONAL:
            return (
                f"Everything you need to understand about {clean_title} in 60 seconds:"
            )
        elif tone == ContentTone.STORYTELLING:
            return (
                f"We spent the last few weeks solving a hard problem. What happened next surprised us:"
            )
        else:  # CONVERSATIONAL
            return (
                f"Quick insight on {clean_title} that might save your team hours this week:"
            )

    def extract_hashtags(self, title: str, text: str) -> List[str]:
        """Generate relevant hashtags based on keywords."""
        corpus = f"{title} {text}".lower()
        tags = set()

        keyword_map = {
            "ai": "#AI",
            "agent": "#AutonomousAgents",
            "automation": "#Automation",
            "workflow": "#Workflows",
            "software": "#SoftwareEngineering",
            "engineering": "#Engineering",
            "python": "#Python",
            "developer": "#DevCommunity",
            "leadership": "#TechLeadership",
            "business": "#BusinessGrowth",
            "data": "#DataScience",
            "cloud": "#CloudComputing",
            "security": "#CyberSecurity",
            "architecture": "#SystemDesign",
        }

        for kw, tag in keyword_map.items():
            if kw in corpus:
                tags.add(tag)

        # Ensure at least 3-4 sensible tags
        defaults = ["#AI", "#Innovation", "#Tech", "#Productivity"]
        for d in defaults:
            if len(tags) < 4:
                tags.add(d)

        return sorted(list(tags))[:5]

    def repurpose_for_linkedin(
        self,
        source_text: str,
        title: str,
        tone: ContentTone = ContentTone.THOUGHT_LEADERSHIP,
        target_audience: str = "Professionals & Engineers",
    ) -> RepurposedVariant:
        """Generate an executive thought-leadership LinkedIn post."""
        key_points = self.extract_key_points(source_text, max_points=4)
        hook = self.generate_hook(title, key_points, tone)
        hashtags = self.extract_hashtags(title, source_text)

        bullets_str = ""
        emojis = ["👉", "📌", "💡", "⚡", "🚀"]
        for idx, pt in enumerate(key_points):
            emo = emojis[idx % len(emojis)]
            bullets_str += f"{emo} {pt}\n\n"

        cta = "What is your team's approach to this? Let's discuss in the comments below 👇"

        body = (
            f"{hook}\n\n"
            f"Here are the core takeaways:\n\n"
            f"{bullets_str}"
            f"Key Takeaway: True leverage comes from deliberate systems, not manual repetition.\n\n"
            f"{cta}\n\n"
            f"{' '.join(hashtags)}"
        )

        char_count = len(body)
        compliance_notes = []
        if char_count > 3000:
            compliance_notes.append("Post exceeds LinkedIn 3000 character limit.")
        compliance_passed = len(compliance_notes) == 0

        variant = RepurposedVariant(
            item_id="",
            platform=PlatformType.LINKEDIN,
            title=f"LinkedIn: {title}",
            body=body,
            thread_tweets=[],
            hashtags=hashtags,
            call_to_action=cta,
            estimated_read_time_sec=max(30, int(len(body.split()) / 3.5)),
            character_count=char_count,
            compliance_passed=compliance_passed,
            compliance_notes=compliance_notes,
            engagement_score=self.calculate_engagement_score(
                has_hook=True, has_cta=True, char_count=char_count, max_recommended=2200, bullet_count=len(key_points)
            ),
            status=ContentStatus.DRAFT,
            metadata={"tone": tone.value, "target_audience": target_audience},
        )
        return variant

    def repurpose_for_twitter_thread(
        self,
        source_text: str,
        title: str,
        tone: ContentTone = ContentTone.PUNCHY_VIRAL,
    ) -> RepurposedVariant:
        """Generate a high-engagement Twitter/X thread with strict 280-char enforcement."""
        key_points = self.extract_key_points(source_text, max_points=6)
        hashtags = self.extract_hashtags(title, source_text)

        raw_tweets: List[str] = []

        # Hook Tweet (Tweet 1)
        hook_headline = title.strip()
        if len(hook_headline) > 80:
            hook_headline = hook_headline[:77] + "..."
        tweet_1 = f"🧵 {hook_headline}\n\nMost people overlook this, but here is what actually works:\n\nA quick breakdown 👇"
        raw_tweets.append(tweet_1)

        # Body Tweets
        for idx, pt in enumerate(key_points):
            pt_clean = pt.strip()
            # If point is too long to fit in 280 chars with tweet numbering
            prefix = f"{idx + 2}/ "
            budget = 275 - len(prefix)
            if len(pt_clean) > budget:
                pt_clean = pt_clean[:budget - 3] + "..."
            tweet_body = f"{pt_clean}"
            raw_tweets.append(tweet_body)

        # Outro & CTA Tweet
        outro_idx = len(raw_tweets) + 1
        outro_tweet = (
            "TL;DR:\n"
            f"• {title[:60]}\n"
            "• Execute with discipline & automate the routine.\n\n"
            "If you found this useful:\n"
            "1. Retweet the first tweet 🔁\n"
            "2. Follow for more deep dives 🤝"
        )
        if len(outro_tweet) > 270:
            outro_tweet = "If you found this thread helpful:\n1. Retweet the first tweet 🔁\n2. Follow for more! 🤝"
        raw_tweets.append(outro_tweet)

        # Number all tweets cleanly (1/N, 2/N, ... N/N) and ensure strict <= 280 chars
        total_tweets = len(raw_tweets)
        final_tweets: List[str] = []
        compliance_notes: List[str] = []

        for i, tw in enumerate(raw_tweets):
            num_suffix = f"\n\n({i + 1}/{total_tweets})"
            available = 280 - len(num_suffix)
            if len(tw) > available:
                tw_cut = tw[:available - 3] + "..."
                final_tw = f"{tw_cut}{num_suffix}"
            else:
                final_tw = f"{tw}{num_suffix}"

            if len(final_tw) > 280:
                compliance_notes.append(f"Tweet {i + 1} exceeds 280 chars ({len(final_tw)} chars).")

            final_tweets.append(final_tw)

        compliance_passed = len(compliance_notes) == 0
        full_body = "\n\n---\n\n".join(final_tweets)

        variant = RepurposedVariant(
            item_id="",
            platform=PlatformType.TWITTER_THREAD,
            title=f"Twitter Thread: {title}",
            body=full_body,
            thread_tweets=final_tweets,
            hashtags=hashtags[:3],
            call_to_action="Retweet first tweet & follow for more.",
            estimated_read_time_sec=max(30, len(final_tweets) * 15),
            character_count=len(full_body),
            compliance_passed=compliance_passed,
            compliance_notes=compliance_notes,
            engagement_score=self.calculate_engagement_score(
                has_hook=True, has_cta=True, char_count=len(full_body), max_recommended=2500, bullet_count=len(key_points)
            ),
            status=ContentStatus.DRAFT,
            metadata={"tweet_count": total_tweets, "tone": tone.value},
        )
        return variant

    def repurpose_for_newsletter(
        self,
        source_text: str,
        title: str,
        tone: ContentTone = ContentTone.EDUCATIONAL,
    ) -> RepurposedVariant:
        """Generate an editorial newsletter edition."""
        key_points = self.extract_key_points(source_text, max_points=5)
        subject_line = f"Digest: {title} — Key Learnings & Strategy"
        preview_text = f"Inside this edition: {key_points[0][:120]}..." if key_points else "Latest engineering updates."

        body_sections = []
        for i, pt in enumerate(key_points):
            body_sections.append(f"### {i+1}. Insight & Application\n{pt}\n")

        newsletter_md = (
            f"**Subject:** {subject_line}\n"
            f"**Preview:** {preview_text}\n\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"*Welcome to this week's edition. Today we are diving into {title.lower()} and why it matters for your team.*\n\n"
            f"## The Big Picture\n\n"
            f"{source_text[:350]}...\n\n"
            f"## Core Insights & Action Items\n\n"
            + "\n".join(body_sections)
            + f"\n## What This Means For You\n\n"
            f"Rather than treating these lessons as theory, consider where this can be applied in your current sprint.\n\n"
            f"**Hit reply** and let us know your thoughts — we read every single email!\n\n"
            f"— The Aether Workforce Team"
        )

        variant = RepurposedVariant(
            item_id="",
            platform=PlatformType.NEWSLETTER,
            title=subject_line,
            body=newsletter_md,
            thread_tweets=[],
            hashtags=[],
            call_to_action="Hit reply to discuss with our team.",
            estimated_read_time_sec=max(60, int(len(newsletter_md.split()) / 3.0)),
            character_count=len(newsletter_md),
            compliance_passed=True,
            compliance_notes=[],
            engagement_score=85.0,
            status=ContentStatus.DRAFT,
            metadata={"subject_line": subject_line, "preview_text": preview_text, "tone": tone.value},
        )
        return variant

    def repurpose_for_video_script(
        self,
        source_text: str,
        title: str,
        tone: ContentTone = ContentTone.PUNCHY_VIRAL,
    ) -> RepurposedVariant:
        """Generate a 30-60 second short-form video script with teleprompter visual cues."""
        key_points = self.extract_key_points(source_text, max_points=3)
        p1 = key_points[0] if len(key_points) > 0 else "The old way is holding you back."
        p2 = key_points[1] if len(key_points) > 1 else "Here is what changes the game."
        p3 = key_points[2] if len(key_points) > 2 else "Execute with systematic precision."

        script = (
            f"# Video Script (Short-form: Reels / TikTok / Shorts)\n"
            f"**Target Duration:** 45 seconds | **Tone:** {tone.value}\n\n"
            f"### [00:00 - 00:04] HOOK\n"
            f"- **Visual:** Direct to camera, quick punch-in zoom.\n"
            f"- **On-Screen Text:** ⚠️ STOP DOING THIS!\n"
            f'- **Spoken:** "If you are still tackling {title[:40]} the manual way, stop right now."\n\n'
            f"### [00:04 - 00:15] THE FRICTION\n"
            f"- **Visual:** B-roll / screen recording showing repetitive bottleneck.\n"
            f"- **On-Screen Text:** The hidden cost\n"
            f'- **Spoken:** "{p1}"\n\n'
            f"### [00:15 - 00:35] THE CORE INSIGHT\n"
            f"- **Visual:** Split screen / system architecture / quick demo.\n"
            f"- **On-Screen Text:** 💡 The Solution\n"
            f'- **Spoken:** "{p2} And here is the secret: {p3}"\n\n'
            f"### [00:35 - 00:45] CALL TO ACTION\n"
            f"- **Visual:** Point down to caption / bio link overlay.\n"
            f"- **On-Screen Text:** Save for later & Comment below\n"
            f'- **Spoken:** "Save this video for your next project and comment your thoughts below!"\n'
        )

        word_count = len(re.findall(r'"([^"]*)"', script))
        total_words = sum(len(s.split()) for s in re.findall(r'"([^"]*)"', script))
        est_sec = max(25, int(total_words / 2.3))

        variant = RepurposedVariant(
            item_id="",
            platform=PlatformType.VIDEO_SCRIPT,
            title=f"Video Script: {title}",
            body=script,
            thread_tweets=[],
            hashtags=self.extract_hashtags(title, source_text)[:4],
            call_to_action="Save this video & comment your thoughts.",
            estimated_read_time_sec=est_sec,
            character_count=len(script),
            compliance_passed=True,
            compliance_notes=[],
            engagement_score=88.0,
            status=ContentStatus.DRAFT,
            metadata={"estimated_duration_seconds": est_sec, "tone": tone.value},
        )
        return variant

    def repurpose_for_blog(
        self,
        source_text: str,
        title: str,
        tone: ContentTone = ContentTone.THOUGHT_LEADERSHIP,
    ) -> RepurposedVariant:
        """Generate a complete long-form blog post with SEO structure."""
        key_points = self.extract_key_points(source_text, max_points=5)
        hashtags = self.extract_hashtags(title, source_text)

        sections = []
        for i, pt in enumerate(key_points):
            sections.append(f"## {i+1}. {pt[:50]}...\n\n{pt}\n\nDeepening our understanding of this principle allows organizations to build resilient foundations rather than quick fixes.\n")

        blog_md = (
            f"# {title}\n\n"
            f"*Published by Aether Workforce Intelligence*\n\n"
            f"> **Executive Summary:** {key_points[0] if key_points else title}\n\n"
            f"---\n\n"
            f"## Introduction\n\n"
            f"{source_text[:400]}...\n\n"
            + "\n".join(sections)
            + f"\n## Conclusion & Action Steps\n\n"
            f"Adopting these strategies transforms operational friction into compounding velocity.\n\n"
            f"**Tags:** {', '.join(hashtags)}"
        )

        variant = RepurposedVariant(
            item_id="",
            platform=PlatformType.BLOG,
            title=f"Article: {title}",
            body=blog_md,
            thread_tweets=[],
            hashtags=hashtags,
            call_to_action="Subscribe to our blog for weekly deep dives.",
            estimated_read_time_sec=max(90, int(len(blog_md.split()) / 3.5)),
            character_count=len(blog_md),
            compliance_passed=True,
            compliance_notes=[],
            engagement_score=82.0,
            status=ContentStatus.DRAFT,
            metadata={"tone": tone.value},
        )
        return variant

    def calculate_engagement_score(
        self,
        has_hook: bool,
        has_cta: bool,
        char_count: int,
        max_recommended: int,
        bullet_count: int,
    ) -> float:
        """Heuristic engagement score calculation (0 - 100)."""
        score = 50.0
        if has_hook:
            score += 15.0
        if has_cta:
            score += 15.0
        if bullet_count >= 3:
            score += 10.0
        if 200 <= char_count <= max_recommended:
            score += 10.0
        elif char_count > max_recommended * 1.5:
            score -= 10.0
        return min(100.0, max(0.0, score))

    def repurpose(self, request: RepurposeRequest) -> RepurposeResult:
        """Repurpose source text into requested platforms and return the structured result."""
        item = ContentItem(
            campaign_id=request.campaign_id,
            title=request.title,
            source_text=request.source_text,
            content_type=request.metadata.get("content_type", "article"),
            metadata=request.metadata,
        )

        variants: List[RepurposedVariant] = []

        for platform in request.target_platforms:
            if platform == PlatformType.LINKEDIN:
                var = self.repurpose_for_linkedin(
                    request.source_text, request.title, request.tone, request.target_audience
                )
            elif platform == PlatformType.TWITTER_THREAD:
                var = self.repurpose_for_twitter_thread(
                    request.source_text, request.title, request.tone
                )
            elif platform == PlatformType.NEWSLETTER:
                var = self.repurpose_for_newsletter(
                    request.source_text, request.title, request.tone
                )
            elif platform == PlatformType.VIDEO_SCRIPT:
                var = self.repurpose_for_video_script(
                    request.source_text, request.title, request.tone
                )
            elif platform == PlatformType.BLOG:
                var = self.repurpose_for_blog(
                    request.source_text, request.title, request.tone
                )
            else:
                continue

            var.item_id = item.id
            variants.append(var)

        return RepurposeResult(item=item, variants=variants)
