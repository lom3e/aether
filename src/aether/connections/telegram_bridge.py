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
                    "👋 *Benvenuto su Aether Operativo!*\n\n"
                    "Sono il tuo Assistente Companion connesso all'intero ecosistema Aether:\n"
                    "- 📊 `/status` — Panoramica missioni, task e approvazioni\n"
                    "- 🎯 `/missions` — Missioni attive del workforce\n"
                    "- 📁 `/deliverables` — Ultimi deliverable e artefatti generati\n"
                    "- 💬 Oppure scrivi qualsiasi istruzione in linguaggio naturale!\n\n"
                    "Se un'azione richiede la tua verifica, riceverai pulsanti inline per approvarla istantaneamente."
                )
                connector.send_message(chat_id=chat_id, text=welcome)
                return {"status": "welcome_sent"}

            if text.startswith("/status") or text.startswith("/overview"):
                ov = workspace.personal.get_overview(workspace.name)
                pending_cnt = len(ov.get("pending_approvals", []))
                active_m = len(ov.get("active_works", []))
                tasks_cnt = len(ov.get("background_tasks", []))
                unread_n = ov.get("unread_notifications", 0)
                msg_status = (
                    f"🧭 *Stato Operativo Aether*\n"
                    f"Workspace: `{workspace.name}`\n\n"
                    f"• 🎯 Missioni Attive: *{active_m}*\n"
                    f"• ⚡ Background Tasks: *{tasks_cnt}*\n"
                    f"• 🛡️ Approvazioni in Attesa: *{pending_cnt}*\n"
                    f"• 🔔 Notifiche non lette: *{unread_n}*\n"
                )
                connector.send_message(chat_id=chat_id, text=msg_status)
                return {"status": "status_sent"}

            if text.startswith("/missions"):
                ov = workspace.personal.get_overview(workspace.name)
                active = ov.get("active_works", [])
                if not active:
                    connector.send_message(chat_id=chat_id, text="🎯 Nessuna missione attualmente in corso.")
                else:
                    lines = ["🎯 *Missioni del Workforce Attive:*\n"]
                    for m in active[:5]:
                        title = m.get("title") or m.get("goal") or "Missione"
                        status = m.get("status", "running")
                        lines.append(f"• *{title}* (`{status}`)")
                    connector.send_message(chat_id=chat_id, text="\n".join(lines))
                return {"status": "missions_sent"}

            if text.startswith("/deliverables"):
                delivs = workspace.personal.list_deliverables(workspace.name, limit=5)
                if not delivs:
                    connector.send_message(chat_id=chat_id, text="📁 Nessun deliverable recente trovato nel workspace.")
                else:
                    lines = ["📁 *Ultimi Deliverable e Artefatti:*\n"]
                    for d in delivs:
                        title = d.get("title", "File")
                        src = d.get("source", "workspace")
                        summary = d.get("summary", "")
                        lines.append(f"• *{title}* ({src})\n  _{summary[:60]}_")
                    connector.send_message(chat_id=chat_id, text="\n".join(lines))
                return {"status": "deliverables_sent"}

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
