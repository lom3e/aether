"""
Instruments a provider INSTANCE so every call is masked (cloud only) and written to the egress ledger.

The instance keeps its class, so ``isinstance`` checks and attribute access are unchanged; only generate/agenerate/
generate_stream/agenerate_stream are replaced on that one object. Local providers (Ollama, localhost endpoints) are
recorded as "stayed on this computer" and are not masked.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any
from urllib.parse import urlparse

from aether.privacy.ledger import EgressLedger
from aether.privacy.redaction import MaskMap, StreamRestorer, mask_text
from aether.privacy.scope import current_scope
from aether.providers.base import AIProvider

logger = logging.getLogger(__name__)


def provider_name(provider: Any) -> str:
    name = getattr(provider, "provider_name", None) or getattr(provider, "PROVIDER_ID", None)
    if isinstance(name, str) and name:
        return name.lower()
    return type(provider).__name__.lower().replace("provider", "")


def is_local(provider: Any) -> bool:
    if provider_name(provider) == "ollama":
        return True
    base = getattr(getattr(provider, "config", None), "base_url", None) or ""
    host = (urlparse(base).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _restore_obj(obj: Any, mapping: MaskMap) -> Any:
    if isinstance(obj, str):
        return mapping.restore(obj)
    if isinstance(obj, dict):
        return {k: _restore_obj(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_restore_obj(v, mapping) for v in obj]
    return obj


def _restore_response(resp: Any, mapping: MaskMap) -> Any:
    if mapping.total == 0 or resp is None:
        return resp
    try:
        resp.content = mapping.restore(getattr(resp, "content", "") or "")
        msg = getattr(resp, "message", None)
        if msg is not None:
            if getattr(msg, "content", None):
                msg.content = mapping.restore(msg.content)
            for tc in getattr(msg, "tool_calls", None) or []:
                try:
                    tc.arguments = _restore_obj(tc.arguments, mapping)
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        logger.debug("could not restore masked values in a provider response")
    return resp


def instrument_provider(provider: Any, ledger: EgressLedger, workspace_id: str | None = None) -> Any:
    if provider is None or getattr(provider, "_aether_audited", False) or not isinstance(provider, AIProvider):
        return provider
    local = is_local(provider)
    pname = provider_name(provider)

    def model() -> str | None:
        return getattr(getattr(provider, "config", None), "model", None) or getattr(provider, "model", None)

    def prepare(messages: list[Any]) -> tuple[list[Any], MaskMap, dict[str, int]]:
        scope = current_scope()
        redact = (not local) and ledger.settings().get("redact", True) and not (scope and scope.unmasked)
        mapping = MaskMap()
        out, chars, images, image_bytes = [], 0, 0, 0
        for m in messages:
            content = getattr(m, "content", "") or ""
            if redact and content:
                content, _ = mask_text(content, mapping)
            chars += len(content)
            for im in getattr(m, "images", None) or []:
                images += 1
                image_bytes += (len(im.data_b64) * 3) // 4
            out.append(dataclasses.replace(m, content=content) if content != (getattr(m, "content", "") or "") else m)
        return out, mapping, {"messages": len(messages), "chars": chars, "images": images, "image_bytes": image_bytes}

    def record(mapping: MaskMap, stats: dict[str, int], status: str = "ok", error_kind: str | None = None) -> None:
        scope = current_scope()
        try:
            entry = ledger.record(
                provider=pname, model=model(), local=local, workspace_id=workspace_id,
                session_id=scope.session_id if scope else None, purpose=scope.purpose if scope else None,
                redactions=dict(mapping.counts), unmasked=bool(scope and scope.unmasked and not local), status=status, error_kind=error_kind, **stats,
            )
            if scope is not None:
                scope.add(entry)
        except Exception:  # noqa: BLE001 - the ledger must never break a request
            logger.warning("egress ledger write failed", exc_info=True)

    orig_generate = provider.generate

    def generate(messages, tools=None, output_schema=None):
        prepared, mapping, stats = prepare(messages)
        try:
            resp = orig_generate(prepared, tools, output_schema)
        except Exception as exc:
            record(mapping, stats, "error", type(exc).__name__)
            raise
        record(mapping, stats)
        return _restore_response(resp, mapping)

    provider.generate = generate  # type: ignore[method-assign]

    if type(provider).agenerate is not AIProvider.agenerate:
        orig_agenerate = provider.agenerate

        async def agenerate(messages, tools=None, output_schema=None):
            prepared, mapping, stats = prepare(messages)
            try:
                resp = await orig_agenerate(prepared, tools, output_schema)
            except Exception as exc:
                record(mapping, stats, "error", type(exc).__name__)
                raise
            record(mapping, stats)
            return _restore_response(resp, mapping)

        provider.agenerate = agenerate  # type: ignore[method-assign]

    if type(provider).generate_stream is not AIProvider.generate_stream:
        orig_stream = provider.generate_stream

        def generate_stream(messages, tools=None, output_schema=None):
            prepared, mapping, stats = prepare(messages)
            restorer = StreamRestorer(mapping)
            status, err = "ok", None
            try:
                for chunk in orig_stream(prepared, tools, output_schema):
                    if mapping.total and getattr(chunk, "text", None):
                        chunk.text = restorer.feed(chunk.text)
                    yield chunk
                tail = restorer.flush()
                if tail:
                    from aether.providers.types import ProviderStreamChunk
                    yield ProviderStreamChunk(text=tail)
            except Exception as exc:
                status, err = "error", type(exc).__name__
                raise
            finally:
                record(mapping, stats, status, err)

        provider.generate_stream = generate_stream  # type: ignore[method-assign]

    if type(provider).agenerate_stream is not AIProvider.agenerate_stream:
        orig_astream = provider.agenerate_stream

        async def agenerate_stream(messages, tools=None, output_schema=None):
            prepared, mapping, stats = prepare(messages)
            restorer = StreamRestorer(mapping)
            status, err = "ok", None
            try:
                async for chunk in orig_astream(prepared, tools, output_schema):
                    if mapping.total and getattr(chunk, "text", None):
                        chunk.text = restorer.feed(chunk.text)
                    yield chunk
                tail = restorer.flush()
                if tail:
                    from aether.providers.types import ProviderStreamChunk
                    yield ProviderStreamChunk(text=tail)
            except Exception as exc:
                status, err = "error", type(exc).__name__
                raise
            finally:
                record(mapping, stats, status, err)

        provider.agenerate_stream = agenerate_stream  # type: ignore[method-assign]

    provider._aether_audited = True
    return provider


def ledger_for(workspace: Any) -> EgressLedger | None:
    """The workspace's ledger (created on first use), or None when there is no workspace to attach it to."""
    if workspace is None or not hasattr(workspace, "conversations_db_path"):
        return None

    def factory() -> EgressLedger:
        from pathlib import Path
        return EgressLedger(Path(workspace.conversations_db_path).parent / "privacy.db")

    try:
        getter = getattr(workspace, "_get_or_create", None)
        return getter("egress_ledger", factory) if getter else factory()
    except Exception:  # noqa: BLE001
        logger.warning("could not open the egress ledger", exc_info=True)
        return None
