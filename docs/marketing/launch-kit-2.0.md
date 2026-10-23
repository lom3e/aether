# Aether — launch kit (draft, publish only after the owner's hands-on test and approval)

Rules: every claim below must be true on the released build. Never "the only", "first", "100% safe". Say "built so that…".
Fake data only in demos. No faces. Publication happens from the owner's accounts, by the owner or with explicit approval
for each post.

## Positioning in one line
- IT: **L'assistente AI per Mac che non finge: se dice "fatto", l'ha fatto davvero — e puoi annullarlo.**
- EN: **The Mac AI assistant that doesn't pretend: when it says "done", it did it — and you can undo it.**

## The five proofs (each one demo-able in 15 seconds)
1. **Sees your screen, not your data.** Summon it with a shortcut: it reads the screen locally and pixelates IBANs, tax
   codes, card numbers and API keys before anything leaves the Mac.
2. **No fake "done".** A reply cannot claim it deleted, sent or moved something unless that action really ran in that turn.
3. **Confirm first, undo after.** Calendar changes show what will happen (before → after); after it, one click puts things
   back (a deleted event is recreated, a moved one goes back).
4. **A receipt for every answer.** Which memories and documents were used, what left the computer, how much was masked.
5. **In your pocket, without a server.** Pair Telegram with a one-time link; the Mac answers, with the same memory and the
   same confirmations. Works while Aether is open.

Plus: talks back when you talk to it (system voices, offline) · Italian and English · free and open source (MIT).

## Honest limits (say them before someone else does)
- macOS on Apple Silicon only for now; Windows build not verified on real hardware.
- Not notarized yet: first launch needs right click → Open (**strongly recommended to fix before a public launch**:
  Apple Developer Program, 99 USD/year; it removes the scary warning that costs most downloads).
- Masking is pattern-based: it misses names and addresses; you can always see what was hidden.
- Google sign-in shows "unverified app" until Google's review. Gmail (read, drafts, send with a 10-second undo, Trash, archive; never deletes for good) uses a restricted scope: it works for test users only until Google's security assessment.
- Needs a model: a free Groq key works; local models through Ollama are supported.

## Product Hunt (EN)
**Name:** Aether
**Tagline (60):** The Mac AI assistant that confirms before it acts — and can undo it
**Description:** Aether lives behind a shortcut. Hold it and talk: it reads your screen locally and blurs bank details and
keys before anything leaves your Mac. It manages your calendar with a clear before → after confirmation and a one-click
Undo, keeps a receipt of what it used and what it sent, and answers from your phone over Telegram — no server in between.
Free, open source, Italian and English.
**First comment (maker):** I built Aether because every assistant I tried either couldn't touch my real stuff, or touched
it and told me "done" when nothing happened. Aether's rule is simple: it can only say it did something if it really ran,
it shows you exactly what will change, and it can put it back. Ask me anything — and tell me what broke.

## Show HN (EN)
**Title:** Show HN: Aether – a local-first Mac assistant that can't claim actions it didn't run
**Body:** Aether is a desktop assistant (Tauri + Python sidecar, MIT). Things that may interest HN:
- an honesty guard: replies that claim a real-world action are replaced unless an action execution backs them;
- model-assisted routing that only *structures* a request into a known action; changes go through an approval and run
  exactly as confirmed (the accepted args are stored, never re-interpreted);
- local OCR (macOS Vision) + pattern masking before a screenshot goes to a cloud model;
- inverse operations for calendar changes (recreate, move back with a "changed since" check);
- Telegram as a long-polling surface paired with a one-time deep link, no webhook.
Repo: github.com/lom3e/aether — limits and what is not verified are listed in the README.

## Reddit
- **r/macapps** (EN): "I made a free, open-source assistant for Mac that confirms before touching your calendar and can undo
  it" + 20 s video of the shortcut → screen read → masked IBAN → answer.
- **r/LocalLLaMA** (EN): focus on "works with local models via Ollama, masking before cloud calls, receipts of egress".
- **r/ItalyInformatica / r/italy** (IT): «Ho fatto un assistente AI per Mac, gratuito e open source, che nasconde IBAN e
  codice fiscale prima di mandare lo schermo al modello. Feedback?»
Rules: read each subreddit's self-promotion rules first; one post per sub; answer every comment.

## LinkedIn (IT)
«In un anno ho provato tutti gli assistenti AI. Il problema non era l'intelligenza: era la fiducia. "Fatto!" e invece no.
Così ho costruito Aether: un assistente per Mac che legge lo schermo ma nasconde IBAN e codici fiscali prima di inviarlo,
ti mostra cosa cambierà prima di toccare il calendario, e se cambi idea annulla. Gratuito e open source. Lo trovi su
aethermate.com — cerco persone che lo mettano alla prova.»

## Instagram Reels / TikTok (no faces) — new clips on top of content-kit-1.9.md
1. **"Fatto. (Davvero.)"** 12 s: «sposta la riunione con Rossi a venerdì» → card *da: gio 11:00 → a: ven 15:00* → Conferma
   → Google Calendar updated → «Annulla» → back. Caption: «Prima ti mostra cosa cambia. Dopo puoi tornare indietro.»
2. **"Dal telefono, senza server"** 10 s: phone screen, Telegram, «che impegni ho domani?» → answer → Mac on the desk.
3. **"Chiedi a voce, risponde a voce"** 8 s: hold the key, ask, the answer is spoken (subtitles on screen).

## Press pitch (IT, short) — tech desks (e.g. HDblog, DDay, Wired Italia, Il Post Tecnologia)
Oggetto: Un assistente AI per Mac, italiano e open source, costruito per non fingere
Testo: 5 righe con i cinque punti sopra, il link al sito, a GitHub e a un video di 30 s; disponibilità per una demo.

## Launch checklist (in order)
1. Owner tests the build (calendar move/delete/undo, Telegram pairing, spoken answers, Screen Shield).
2. Notarize the app (strongly recommended) and publish the release only with explicit approval.
3. Update the site with these claims only after step 1.
4. Record the clips from the real app with a throw-away data dir.
5. Product Hunt on a Tuesday–Thursday, 00:01 PT; Show HN the same day at ~15:00 CET; Reddit spread over a week.
6. Search Console + sitemap (already prepared) once the site is updated.
