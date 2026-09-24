"""
Telegram Operational Bridge for Aether.
Connects Telegram Bot interactions directly to the Aether Personal Agent,
Workforce Delegation, and Action Approval lifecycle.
"""
from __future__ import annotations

import logging
from typing import Any

from aether.connections.telegram import TelegramConnector

logger = logging.getLogger(__name__)


class TelegramBridge:
    """
    Bridge that translates Telegram messages into Aether Personal Agent prompts
    and handles interactive inline button callbacks for action approvals.
    """

    @classmethod
    def handle_update(cls, update: dict[str, Any], workspace: Any) -> dict[str, Any]:
        """
        Dispatches an incoming Telegram update (webhook or poll).
        """
        conn = workspace.connections.get_connection(workspace.name, "telegram")
        if not conn or not conn.auth_metadata.get("bot_token"):
            return {"status": "ignored", "reason": "Telegram not configured in workspace"}

        connector = TelegramConnector(auth_metadata=conn.auth_metadata)

        # 1. Handle Inline Button Click (Callback Query)
        if "callback_query" in update:
            cb = update["callback_query"]
            cb_id = cb.get("id")
            data = str(cb.get("data", ""))
            message = cb.get("message", {})
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            message_id = message.get("message_id")

            if not connector.is_chat_authorized(chat_id):
                connector.answer_callback_query(cb_id, "Non autorizzato.", show_alert=True)
                return {"status": "unauthorized"}

            if data.startswith("approve:"):
                exec_id = data.split(":", 1)[1]
                try:
                    res = workspace.action_executor.approve_execution(exec_id)
                    connector.answer_callback_query(cb_id, "✅ Azione approvata ed eseguita!")
                    connector.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"✅ *Azione Approvata ed Eseguita con Successo*\nID: `{exec_id}`\nRisultato: `{res.status.value}`",
                    )
                    return {"status": "approved", "execution_id": exec_id}
                except Exception as exc:
                    connector.answer_callback_query(cb_id, f"Errore: {exc}", show_alert=True)
                    return {"status": "error", "error": str(exc)}

            elif data.startswith("reject:"):
                exec_id = data.split(":", 1)[1]
                try:
                    workspace.action_executor.reject_execution(exec_id)
                    connector.answer_callback_query(cb_id, "❌ Azione rifiutata.")
                    connector.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"❌ *Azione Rifiutata dall'Utente*\nID: `{exec_id}`",
                    )
                    return {"status": "rejected", "execution_id": exec_id}
                except Exception as exc:
                    connector.answer_callback_query(cb_id, f"Errore: {exc}", show_alert=True)
                    return {"status": "error", "error": str(exc)}

            connector.answer_callback_query(cb_id, "Ricevuto.")
            return {"status": "callback_handled"}

        # 2. Handle Text Message
        if "message" in update:
            msg = update["message"]
            chat = msg.get("chat", {})
            chat_id = chat.get("id")
            text = str(msg.get("text", "")).strip()

            if not text:
                return {"status": "ignored", "reason": "empty_text"}

            if not connector.is_chat_authorized(chat_id):
                connector.send_message(
                    chat_id=chat_id,
                    text=f"⛔ *Accesso Negato*\nQuesto bot Aether è privato. Il tuo Chat ID `{chat_id}` non è tra quelli autorizzati.",
                )
                return {"status": "unauthorized"}

            if text.startswith("/start") or text.startswith("/help"):
                welcome = (
                    "👋 *Benvenuto su Aether!*\n\n"
                    "Sono il tuo Assistente Operativo Aether. Puoi scrivermi qualsiasi richiesta:\n"
                    "- 📅 _\"Crea un evento domani alle 15 con il team\"_\n"
                    "- 📧 _\"Invia una email di recap a matteo@example.com\"_\n"
                    "- 🚀 _\"Sincronizza le connessioni\"_\n"
                    "- 🤖 _\"Delega all'agente esterno l'analisi dei contratti\"_\n\n"
                    "Se un'azione richiede la tua verifica, ti manderò un pulsante per approvarla istantaneamente da qui."
                )
                connector.send_message(chat_id=chat_id, text=welcome)
                return {"status": "welcome_sent"}

            # Process prompt through PersonalAgentService
            reply = workspace.personal.process_prompt(
                workspace_id=workspace.name,
                prompt=text,
            )

            # Check if action required approval
            has_pending = any(s.status == "pending_approval" for s in reply.steps)
            if has_pending and reply.action_execution_id:
                action_step = next((s for s in reply.steps if s.details and "action_id" in s.details), None)
                action_id = action_step.details["action_id"] if action_step else "action"
                connector.send_approval_request(
                    chat_id=chat_id,
                    action_id=action_id,
                    execution_id=reply.action_execution_id,
                    title=f"Richiesta: {text[:50]}",
                    description=reply.content,
                )
            else:
                connector.send_message(chat_id=chat_id, text=reply.content or "Operazione completata.")

            return {"status": "processed", "steps": len(reply.steps)}

        return {"status": "ignored", "reason": "unsupported_update_type"}
