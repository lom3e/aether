"""Aether on your phone through Telegram, local-first.

The desktop polls Telegram (no public server, no webhook): when the Mac is off, the bot is silent, which is the accepted
trade-off. Nobody can talk to the bot until a chat is paired: the app shows a one-time link (t.me/<bot>?start=<code>),
the user taps it, Telegram sends "/start <code>" and only that chat is added to the allow-list. Every message goes through
the same Personal Agent as the desktop (same memory, same confirmations); one conversation per chat so follow-ups
("cancellali") keep their context. Changes are confirmed with buttons, exactly like the confirmation cards in the app.
Voice messages are transcribed with Whisper through the user's own provider key (the same as in the app); /oggi sends
the day's brief with its one question as buttons; "may I do this by myself from now on?" is answered with buttons too.
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

PAIRING_TTL = 600  # seconds a pairing link stays valid
_SESSION_KEY = "telegram_session:{chat}"
_PENDING_KEY = "telegram_pending:{proposal}"
_AUTONOMY_KEY = "telegram_autonomy:{ref}"  # callback data is limited to 64 bytes: the autonomy key is kept here


def plain(text: str) -> str:
    """Telegram rejects malformed Markdown and the message is lost: send model text as plain text."""
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    t = re.sub(r"`([^`]*)`", r"\1", t)
    return t.strip()[:4000] or "…"


class TelegramMobile:
    """One per workspace. Thread-safe enough for one polling thread plus API calls from the app."""

    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._offset: int | None = None
        self._pairing: dict[str, float] = {}
        self.last_error = ""
        self.last_poll_at: float | None = None

    # ---- setup and pairing ---------------------------------------------------------------------------------------
    def _connection(self) -> Any:
        return self.ws.connections.get_connection(self.ws.id, "telegram")

    def _connector(self) -> Any:
        return self.ws.connections.get_telegram_connector(self.ws.id)

    def setup(self, bot_token: str) -> dict[str, Any]:
        """Checks the token with Telegram (getMe), stores it in the secret store, returns the pairing link."""
        from aether.connections.models import Connection, ConnectionStatus
        from aether.connections.telegram import TelegramConnector

        token = (bot_token or "").strip()
        probe = TelegramConnector(auth_metadata={"bot_token": token})
        ok, message = probe.verify(live_check=True)
        if not ok:
            return {"status": "error", "message": message}
        username = (re.search(r"@(\w+)", message) or [None, ""])[1]
        existing = self._connection()
        now = datetime.now(timezone.utc).isoformat()
        meta = dict(existing.auth_metadata) if existing else {}
        meta.update({"bot_token": token, "bot_username": username, "polling": True})
        meta.setdefault("allowed_chat_ids", "")
        conn = Connection(
            id=existing.id if existing else f"conn-{uuid.uuid4().hex[:10]}",
            workspace_id=self.ws.id, provider="telegram", account_name=f"@{username}" if username else "Telegram",
            status=ConnectionStatus.VERIFIED, scopes=self.ws.connections.get_default_capabilities("telegram"),
            capabilities=self.ws.connections.get_default_capabilities("telegram"), auth_metadata=meta,
            last_verified_at=now, last_verification_error=None, verification_method="telegram_getme",
            created_at=existing.created_at if existing else now, updated_at=now,
        )
        self.ws.connections.save_connection(conn)
        self.start()
        return {"status": "ok", "bot_username": username, **self.pairing_link()}

    def pairing_link(self) -> dict[str, Any]:
        conn = self._connection()
        username = (conn.auth_metadata or {}).get("bot_username") if conn else ""
        code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:10]
        self._pairing = {c: exp for c, exp in self._pairing.items() if exp > time.time()}
        self._pairing[code] = time.time() + PAIRING_TTL
        return {"code": code, "link": f"https://t.me/{username}?start={code}" if username else "", "expires_in": PAIRING_TTL}

    def _allowed(self) -> list[str]:
        conn = self._connection()
        raw = str((conn.auth_metadata or {}).get("allowed_chat_ids") or "") if conn else ""
        return [x.strip() for x in raw.split(",") if x.strip()]

    def _pair(self, chat_id: Any, code: str, name: str) -> bool:
        exp = self._pairing.pop(code, None)
        if not exp or exp < time.time():
            return False
        conn = self._connection()
        allowed = self._allowed()
        if str(chat_id) not in allowed:
            allowed.append(str(chat_id))
        meta = dict(conn.auth_metadata or {})
        meta["allowed_chat_ids"] = ",".join(allowed)
        names = dict(meta.get("paired_names") or {})
        names[str(chat_id)] = name
        meta["paired_names"] = names
        conn.auth_metadata = meta
        conn.updated_at = datetime.now(timezone.utc).isoformat()
        self.ws.connections.save_connection(conn)
        return True

    def unpair_all(self) -> None:
        conn = self._connection()
        if conn:
            meta = dict(conn.auth_metadata or {})
            meta["allowed_chat_ids"] = ""
            meta["paired_names"] = {}
            conn.auth_metadata = meta
            self.ws.connections.save_connection(conn)

    def status(self) -> dict[str, Any]:
        conn = self._connection()
        meta = (conn.auth_metadata or {}) if conn else {}
        return {
            "configured": bool(conn and meta.get("bot_token")),
            "bot_username": meta.get("bot_username", ""),
            "paired": [{"chat_id": c, "name": (meta.get("paired_names") or {}).get(c, "")} for c in self._allowed()],
            "running": bool(self._thread and self._thread.is_alive()),
            "last_poll_at": self.last_poll_at,
            "last_error": self.last_error,
        }

    # ---- polling -------------------------------------------------------------------------------------------------
    def start(self) -> bool:
        conn = self._connection()
        if not conn or not (conn.auth_metadata or {}).get("bot_token"):
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="aether-telegram", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                updates = self._connector().get_updates(offset=self._offset, timeout=25)
                self.last_poll_at = time.time()
                self.last_error = ""
                for upd in updates:
                    self._offset = int(upd.get("update_id", 0)) + 1
                    try:
                        self.handle(upd)
                    except Exception as exc:  # noqa: BLE001 - one bad update must not stop the bot
                        logger.warning("Telegram update failed: %s", type(exc).__name__)
            except Exception as exc:  # noqa: BLE001
                self.last_error = type(exc).__name__
                self._stop.wait(5)

    # ---- one update ----------------------------------------------------------------------------------------------
    def handle(self, update: dict[str, Any]) -> dict[str, Any]:
        tg = self._connector()
        if "callback_query" in update:
            return self._callback(tg, update["callback_query"])
        msg = update.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        text = str(msg.get("text") or "").strip()
        voice = msg.get("voice") or msg.get("audio")
        if chat_id is not None and not text and voice and str(chat_id) in self._allowed():
            return self._voice(tg, chat_id, voice)
        if chat_id is None or not text:
            return {"status": "ignored"}
        if text.startswith("/start "):
            name = " ".join(x for x in ((msg.get("from") or {}).get("first_name"), (msg.get("from") or {}).get("username")) if x)
            if self._pair(chat_id, text.split(" ", 1)[1].strip(), name):
                tg.send_message(chat_id=chat_id, parse_mode="", text=(
                    "Collegato! Da qui puoi scrivere ad Aether come sul Mac: stessa memoria, stesse conferme.\n"
                    "Esempi: «che impegni ho domani?», «ricordami di chiamare Rossi», «sposta la riunione a venerdì».\n"
                    "Funziono quando Aether è aperto sul tuo computer."))
                return {"status": "paired"}
        if str(chat_id) not in self._allowed():
            tg.send_message(chat_id=chat_id, parse_mode="", text="Questo Aether è privato. Per collegare questa chat apri Aether sul tuo computer → Collegamenti → Telegram.")
            return {"status": "unauthorized"}
        if text in ("/start", "/help"):
            tg.send_message(chat_id=chat_id, parse_mode="", text=(
                "Scrivimi o mandami un vocale con quello che ti serve. Le modifiche (calendario, mail, documenti) ti chiedono sempre "
                "conferma qui.\n/oggi: il riepilogo della giornata.\n/sera: chiudi la giornata (e sposta a domani quello che resta)."))
            return {"status": "help"}
        if text.split("@")[0] in ("/oggi", "/today"):
            return self._brief(tg, chat_id, "en" if text.startswith("/today") else "it")
        if text.split("@")[0] in ("/sera", "/evening"):
            return self._brief(tg, chat_id, "en" if text.startswith("/evening") else "it", evening=True)
        return self._ask(tg, chat_id, text)

    def _voice(self, tg: Any, chat_id: Any, voice: dict[str, Any]) -> dict[str, Any]:
        """A voice message: Whisper with the user's key turns it into text, which is shown back and then handled as usual."""
        from aether.personal import voice_engine

        if int(voice.get("duration") or 0) > 180:
            tg.send_message(chat_id=chat_id, parse_mode="", text="Il vocale è troppo lungo: tienilo sotto i tre minuti.")
            return {"status": "voice_too_long"}
        try:
            audio = tg.get_file_bytes(voice.get("file_id"))
            heard = voice_engine.transcribe(self.ws, audio, voice.get("mime_type") or "audio/ogg", "it")
        except voice_engine.VoiceError as exc:
            if exc.code == "use_device":
                tg.send_message(chat_id=chat_id, parse_mode="", text=(
                    "Per capire i vocali mi serve una chiave Groq o OpenAI in Aether (Impostazioni → Modello). Intanto scrivimi pure."))
                return {"status": "voice_needs_key"}
            tg.send_message(chat_id=chat_id, parse_mode="", text="Non sono riuscito a capire il vocale. Riprova o scrivimi.")
            return {"status": "voice_failed", "code": exc.code}
        except Exception as exc:  # noqa: BLE001
            tg.send_message(chat_id=chat_id, parse_mode="", text="Non sono riuscito a scaricare il vocale. Riprova.")
            return {"status": "voice_failed", "code": type(exc).__name__}
        text = (heard.get("text") or "").strip()
        if not text:
            tg.send_message(chat_id=chat_id, parse_mode="", text="Non ho sentito niente nel vocale.")
            return {"status": "voice_empty"}
        tg.send_message(chat_id=chat_id, parse_mode="", text=f"🎙 «{text}»")
        out = self._ask(tg, chat_id, text)
        out["heard"] = text
        return out

    def _brief(self, tg: Any, chat_id: Any, language: str = "it", evening: bool = False) -> dict[str, Any]:
        from aether.life import presence_brief
        from aether.life.store import life_store_for

        store = life_store_for(self.ws)
        b = presence_brief.evening(self.ws, store, language=language) if evening else presence_brief.build(self.ws, store, language=language)
        if evening and not b.get("text"):
            b = {"text": "Today there is nothing to close." if language == "en" else "Oggi non c'è niente da chiudere.", "offer": None}
        offer = b.get("offer")
        if not offer:
            tg.send_message(chat_id=chat_id, parse_mode="", text=b["text"])
            return {"status": "brief"}
        if offer.get("promise_id"):
            ref = f"{offer['type']}:{offer['promise_id']}"
        else:  # a money, reconnect or roll-over offer does not fit in Telegram's 64-byte button data: kept here until answered
            store.update_settings(telegram_offer=offer)
            ref = f"{offer['type']}:@"
        yes, no = ("Yes", "Not now") if language == "en" else ("Sì", "Non ora")
        tg.send_message(chat_id=chat_id, parse_mode="", text=b["text"], reply_markup={"inline_keyboard": [[
            {"text": yes, "callback_data": f"by:{ref}"}, {"text": no, "callback_data": f"bn:{ref}"}]]})
        return {"status": "brief_with_offer", "offer": offer}

    def _session(self, chat_id: Any) -> str | None:
        try:
            return self.ws.personal_store.get_setting(_SESSION_KEY.format(chat=chat_id)) or None
        except Exception:  # noqa: BLE001
            return None

    def _ask(self, tg: Any, chat_id: Any, text: str, authority: Any = None) -> dict[str, Any]:
        reply = self.ws.personal.process_prompt(workspace_id=self.ws.id, prompt=text, session_id=self._session(chat_id), authority=authority)
        try:
            self.ws.personal_store.set_setting(_SESSION_KEY.format(chat=chat_id), reply.session_id)
        except Exception:  # noqa: BLE001
            pass
        meta = reply.metadata or {}
        if meta.get("status") == "proposal_pending" and meta.get("proposal_id"):
            pid, ver = meta["proposal_id"], meta.get("proposal_version", 1)
            self.ws.personal_store.set_setting(_PENDING_KEY.format(proposal=pid), text)
            tg.send_message(chat_id=chat_id, parse_mode="", text=plain(reply.content), reply_markup={"inline_keyboard": [[
                {"text": "Conferma", "callback_data": f"ok:{pid}:{ver}"}, {"text": "Annulla", "callback_data": f"no:{pid}"}]]})
            return {"status": "proposal_sent", "proposal_id": pid}
        waiting = next((s for s in reply.steps if s.status == "waiting_approval"), None)
        if waiting is not None and reply.action_execution_id:
            tg.send_message(chat_id=chat_id, parse_mode="", text=plain(reply.content), reply_markup={"inline_keyboard": [[
                {"text": "Approva", "callback_data": f"approve:{reply.action_execution_id}"}, {"text": "Rifiuta", "callback_data": f"reject:{reply.action_execution_id}"}]]})
            return {"status": "approval_sent", "execution_id": reply.action_execution_id}
        offer = meta.get("autonomy_offer") or {}
        if meta.get("undo_execution_id"):
            tg.send_message(chat_id=chat_id, parse_mode="", text=plain(reply.content), reply_markup={"inline_keyboard": [[
                {"text": "Annulla", "callback_data": f"undo:{meta['undo_execution_id']}"}]]})
            if offer.get("key"):
                self._offer_autonomy(tg, chat_id, offer)
            return {"status": "done_with_undo"}
        tg.send_message(chat_id=chat_id, parse_mode="", text=plain(reply.content))
        if offer.get("key"):
            self._offer_autonomy(tg, chat_id, offer)
        return {"status": "answered"}

    def _offer_autonomy(self, tg: Any, chat_id: Any, offer: dict[str, Any]) -> None:
        """Earned autonomy, on the phone: after the same approval three times in a row, ask once with two buttons."""
        ref = uuid.uuid4().hex[:10]
        self.ws.personal_store.set_setting(_AUTONOMY_KEY.format(ref=ref), offer["key"])
        label = offer.get("label") or "questa azione"
        tg.send_message(chat_id=chat_id, parse_mode="", text=(
            f"Me l'hai approvato più volte di fila: d'ora in poi posso farlo da solo? ({label}). Resterà sempre annullabile, "
            "e puoi togliermi il permesso in Aether → Privacy."), reply_markup={"inline_keyboard": [[
                {"text": "Sì, fallo da solo", "callback_data": f"auto:y:{ref}"}, {"text": "No, chiedimelo", "callback_data": f"auto:n:{ref}"}]]})

    def _callback(self, tg: Any, cb: dict[str, Any]) -> dict[str, Any]:
        data = str(cb.get("data") or "")
        chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
        if str(chat_id) not in self._allowed():
            tg.answer_callback_query(cb.get("id"), "Non autorizzato.", show_alert=True)
            return {"status": "unauthorized"}
        tg.answer_callback_query(cb.get("id"), "Ricevuto.")
        if data.startswith("ok:"):
            _, pid, ver = (data.split(":") + ["1"])[:3]
            _, authority = self.ws.personal.accept_proposal(proposal_id=pid, workspace_id=self.ws.id, expected_version=int(ver), actor="user:telegram", channel="telegram")
            original = self.ws.personal_store.get_setting(_PENDING_KEY.format(proposal=pid)) or ""
            return self._ask(tg, chat_id, original, authority=authority)
        if data.startswith("no:"):
            self.ws.personal.revoke_proposal(data.split(":", 1)[1], self.ws.id, actor="user:telegram", reason="declined on Telegram")
            tg.send_message(chat_id=chat_id, parse_mode="", text="Va bene, non faccio niente.")
            return {"status": "declined"}
        if data.startswith("approve:"):
            res = self.ws.action_executor.approve_execution(data.split(":", 1)[1])
            ok = str(getattr(res.status, "value", res.status)) in ("succeeded", "completed")
            tg.send_message(chat_id=chat_id, parse_mode="", text="Fatto." if ok else f"Non è riuscito: {getattr(res, 'error_message', '') or 'errore'}")
            return {"status": "approved" if ok else "failed"}
        if data.startswith("undo:"):
            from aether.actions import undo as undo_mod

            try:
                undo_mod.undo(self.ws, data.split(":", 1)[1])
                tg.send_message(chat_id=chat_id, parse_mode="", text="Annullato: è tutto come prima.")
                return {"status": "undone"}
            except undo_mod.UndoError as exc:
                why = {"changed_since": "l'evento è stato cambiato di nuovo nel frattempo", "already_undone": "era già stato annullato"}.get(exc.code, "non è stato possibile")
                tg.send_message(chat_id=chat_id, parse_mode="", text=f"Non ho annullato: {why}.")
                return {"status": "undo_refused", "code": exc.code}
        if data.startswith("auto:"):
            _, ans, ref = (data.split(":") + ["", ""])[:3]
            key = self.ws.personal_store.get_setting(_AUTONOMY_KEY.format(ref=ref)) or ""
            from aether.personal.autonomy import autonomy_store_for

            st = autonomy_store_for(self.ws)
            row = st.get(key) if key else None
            if not row or not row.get("offered_at"):
                tg.send_message(chat_id=chat_id, parse_mode="", text="Questa proposta non è più valida.")
                return {"status": "autonomy_stale"}
            st.decide(key, ans == "y")
            self.ws.personal_store.set_setting(_AUTONOMY_KEY.format(ref=ref), "")
            tg.send_message(chat_id=chat_id, parse_mode="", text=(
                "Va bene: d'ora in poi lo faccio da solo, e ti dico sempre cosa ho fatto." if ans == "y" else "Va bene, continuerò a chiedertelo."))
            return {"status": "autonomy_granted" if ans == "y" else "autonomy_declined", "key": key}
        if data.startswith(("by:", "bn:")):
            from aether.life import presence_brief
            from aether.life.store import life_store_for

            kind, _, pid = data[3:].partition(":")
            offer = {"type": kind, "promise_id": None if pid == "-" else pid}
            store = life_store_for(self.ws)
            if pid == "@":
                offer = dict(store.settings().get("telegram_offer") or {})
                store.update_settings(telegram_offer={})
                if offer.get("type") != kind:
                    tg.send_message(chat_id=chat_id, parse_mode="", text="Questa proposta non è più valida.")
                    return {"status": "brief_stale"}
            try:
                if data.startswith("bn:"):
                    presence_brief.decline(store, offer)
                    tg.send_message(chat_id=chat_id, parse_mode="", text="Va bene, non te lo richiedo.")
                    return {"status": "brief_declined"}
                out = presence_brief.accept(self.ws, store, offer)
            except ValueError:
                tg.send_message(chat_id=chat_id, parse_mode="", text="Questa proposta non è più valida.")
                return {"status": "brief_stale"}
            if out.get("prompt"):
                return self._ask(tg, chat_id, out["prompt"])
            tg.send_message(chat_id=chat_id, parse_mode="", text=out.get("text") or "Fatto.")
            return {"status": "brief_accepted"}
        if data.startswith("reject:"):
            self.ws.action_executor.reject_execution(data.split(":", 1)[1])
            tg.send_message(chat_id=chat_id, parse_mode="", text="Va bene, non faccio niente.")
            return {"status": "rejected"}
        return {"status": "ignored"}


_instances: dict[str, TelegramMobile] = {}


def for_workspace(ws: Any) -> TelegramMobile:
    inst = _instances.get(ws.id)
    if inst is None or inst.ws is not ws:
        inst = _instances[ws.id] = TelegramMobile(ws)
    return inst
