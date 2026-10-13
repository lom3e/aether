"""
PersonalEventHub.publish may be called from any thread (an approval running in ``asyncio.to_thread``, the background
task manager). ``asyncio.Queue`` is not thread-safe, so the event must be handed to the loop that owns the queue.
Deterministic: no sleeps; the only timeouts are safety nets that fail the test instead of hanging it.
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from aether.personal.events import PersonalEventHub


@pytest.mark.asyncio
async def test_publish_from_a_worker_thread_is_delivered_on_the_subscribers_loop(monkeypatch):
    hub = PersonalEventHub()
    queue = hub.subscribe("ws")  # subscribed inside the running loop: that loop owns the queue
    loop_thread = threading.get_ident()
    put_threads: list[int] = []
    real_put = asyncio.Queue.put_nowait

    def recording_put(self, item):
        put_threads.append(threading.get_ident())
        return real_put(self, item)

    monkeypatch.setattr(asyncio.Queue, "put_nowait", recording_put)
    asyncio.get_running_loop().set_debug(True)  # asyncio then rejects non-thread-safe calls made from another thread

    getter = asyncio.create_task(queue.get())
    await asyncio.sleep(0)  # the subscriber is now waiting on the queue

    counts: list[int] = []

    def worker():
        counts.append(hub.publish("ws", "task.update", {"i": 1}))
        counts.append(hub.publish("ws", "task.update", {"i": 2}))
        counts.append(hub.publish("ws", "task.update", {"i": 3}))

    await asyncio.to_thread(worker)
    # Checked BEFORE waiting for the events, so a regression fails here instead of waiting on a lost event.
    assert counts == [1, 1, 1], "every publish must report a delivered subscriber"

    first = await asyncio.wait_for(getter, timeout=10)
    rest = [await asyncio.wait_for(queue.get(), timeout=10) for _ in range(2)]

    assert [e["data"]["i"] for e in [first, *rest]] == [1, 2, 3], "FIFO order of one publishing thread is preserved"
    assert set(put_threads) == {loop_thread}, "the queue must only ever be touched from its own loop thread"


@pytest.mark.asyncio
async def test_publish_on_the_loop_thread_still_works_and_reports_the_subscriber():
    hub = PersonalEventHub()
    queue = hub.subscribe("ws")
    assert hub.publish("ws", "evt", {"ok": True}) == 1
    assert (await asyncio.wait_for(queue.get(), timeout=10))["data"]["ok"] is True
    assert hub.publish("other-ws", "evt", {}) == 0


def test_publish_to_a_subscriber_whose_loop_is_closed_drops_it():
    hub = PersonalEventHub()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_subscribe(hub, "ws"))
    finally:
        loop.close()
    assert hub.subscriber_count("ws") == 1
    assert hub.publish("ws", "evt", {}) == 0  # no live loop to deliver to
    assert hub.subscriber_count("ws") == 0, "a dead subscriber must be removed, not kept forever"


def test_subscription_outside_a_loop_keeps_the_direct_delivery_contract():
    hub = PersonalEventHub()
    queue = hub.subscribe("ws")  # no running loop: legacy synchronous use
    assert hub.publish("ws", "evt", {"n": 1}) == 1
    assert queue.get_nowait()["data"]["n"] == 1


async def _subscribe(hub: PersonalEventHub, workspace_id: str) -> None:
    hub.subscribe(workspace_id)
