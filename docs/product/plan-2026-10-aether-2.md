# Aether 2 — audit and plan (2026-10-22)

## Audit (measured, not assumed)

**Screens.** All 22 views open in IT and EN with no console errors, no failing API calls and no visible translation keys (automated crawl of the classic interface, isolated data).

**Truthfulness problems found.**
- Marketplace shows invented download counts and star ratings (seeded catalog in `ecosystem/store.py`, e.g. 3420 downloads, 4.98).
- Chat could claim an action it never ran: with a conversation going, "cancella …" was read as a refusal and the model improvised "provvedo subito" (fixed for the calendar on 2026-10-21; the general risk remains for any action the keyword rules do not recognise).
- Calendar creation from chat sets the start time to "now" (title parsed by keywords, no date parsing).
- English text in the Italian interface: agent system prompts shown as descriptions, marketplace descriptions, content sample text, activity log titles ("Completed: …").

**Structure.** 22 top-level views for one personal assistant; duplicated screens (Results and Deliverables are the same page; Memory and Knowledge split; the Workforce hub has six tabs of internal concepts). Intent routing is keyword-based (`personal/service.py`, ~4,000 lines): every phrasing not foreseen falls to the model with no tools.

**Tests.** Full suite run file by file (see the audit log); failures are classified as environment (a coding CLI installed on this Mac, Tauri debug binary removed after builds), stale expectations, or real defects.

**Roadmap position.** M0 done; M1a done except notarization (declined for now); Companion Bar, Screen Shield, Privacy, receipts, undo, OAuth one-click (Google live) done on `development`. Open: M3a voice output, M3b Telegram, M4 Gmail/GitHub live, M5 verified execution UI, M6 UX overhaul.

## Plan

### Phase 1 — Everything works and tells the truth
1. **Honesty guard**: a model reply may not claim a completed action (deleted, sent, created, booked, moved…) unless an action actually ran in that turn; otherwise the claim is replaced by an honest statement and the user is offered the real action.
2. **Model-driven tool routing** as fallback to the keyword rules: the model picks among registered actions (calendar list/create/move/delete, remember, people & jobs, documents); reads run, changes go to the approval card.
3. **Calendar complete**: create with real date/time parsing, move, delete, undo of a deletion (recreate from the saved copy).
4. **No fake data**: marketplace without invented numbers; everything in the Italian interface in Italian.
5. **Green suite**: fix stale tests, keep environment-dependent ones explicit.

### Phase 2 — One Aether, simple
Five places: **Oggi**, **Lavori**, **Memoria** (people, facts, documents, knowledge), **Collegamenti**, **Privacy**. Everything else under "Strumenti avanzati". Duplicated screens merged. One interface instead of Orb vs classic.

### Phase 3 — Unique
- **"Cosa ho fatto"**: one timeline of everything Aether did, each entry with its receipt and an Undo where possible.
- **Telegram** as a mobile surface of the same runtime (local-first, pairing code).
- **Spoken answers** with the system voice (optional, offline).
- **Gmail read-only** and a morning brief from calendar + mail.
- Proactive help from People & jobs (deadlines, preparing before an appointment).

### Phase 4 — Launch
Build + smoke + hands-on test by the owner → release 1.9 only with explicit approval → site copy with verified claims only → demo video and content kit → launch posts (Product Hunt, Reddit, Hacker News, LinkedIn, Instagram/TikTok) drafted here, published only with the owner's approval and accounts.
