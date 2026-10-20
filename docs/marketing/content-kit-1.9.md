# Aether 1.9 — content kit (Instagram Reels / TikTok), no faces

Rules for every post: only show what the app really does today (see "Verified" below); never say "the only" or "nobody else"; say "built so that…". Use fake data only (the IBAN/codice fiscale below are made-up test values). No faces: screen recordings, hands-off, big captions, voice-over optional (or text only).

## Verified today (safe to claim)
- Hide-before-send: a capture is read locally (macOS Vision OCR), IBAN / cards / codice fiscale / emails / phones / API keys and long tokens are pixelated **before** the image is sent; the user sees "N aree nascoste" and can show them again. Verified with the real helper and a real-server shield route; the sent image's pixels are verified destroyed in an automated test.
- Receipts: under an answer, which memories/documents it used and what left the computer (provider, how many items were masked).
- Undo: document writes made by Aether can be undone (refused if the file changed afterwards).
- Privacy screen: what left (kinds and counts, never content), what Aether knows (edit / forget), history with undo.
- Second opinion: the same question to other configured models + a text comparison (it does not say who is right).
- Italian + English.

## Not verified yet (do NOT film or claim until Matteo has tried it on his Mac)
- Hold-the-key-and-speak with a real microphone (the key handling and the screen-reading are tested; the dictation start from a global key depends on macOS microphone/speech permission and the WebKit engine).
- Anything with a real cloud model (tests use mock providers).

## Demo 1 — "Screen Shield" (hero, 20 s)
Hook (text, 0–2 s): **"Ho chiesto all'AI di leggere la mia fattura. Guarda cosa vede davvero."** / "I asked an AI to read my invoice. Look at what it actually sees."
Shot list:
1. 0–3 s: a fake invoice page on screen with `IT60X0542811101000000123456` and `RSSMRA85T10A562S`, plus an email and a phone number.
2. 3–6 s: press the shortcut (show the keys on screen), Aether's Bar appears; chip "Sto guardando lo schermo".
3. 6–11 s: split view — left: the page; right: the image as sent, the IBAN/CF/email/phone pixelated; chip "4 aree sensibili nascoste".
4. 11–16 s: the answer ("La fattura è di 120 €, scade il 5…") — the AI still understood the page.
5. 16–20 s: Privacy screen → "Cosa esce": one request, 4 items hidden.
End card: **"Vede lo schermo. Non vede i tuoi dati."** / "It sees your screen. Not your data." + `aethermate.com`.
Caption IT: «Gli assistenti AI vedono il tuo schermo. Aether nasconde IBAN, codici fiscali e chiavi prima che l'immagine esca dal Mac. Gratis e open source.» Hashtags: #AI #privacy #mac #produttività #opensource #GDPR
Caption EN: "AI assistants can see your screen. Aether hides IBANs, tax IDs and keys before the image leaves your Mac. Free and open source." #AI #privacy #mac #productivity #opensource

## Demo 2 — "Ricevute e Annulla" (15 s)
Hook: **"E se potessi vedere perché l'AI sa quello che sa?"**
1. Ask something answered from a memory; answer appears.
2. Tap "Fonti (2) · inviato a groq · 2 oscurati" → the sources list.
3. Tap "Dimentica" on one memory → gone (verified).
4. Ask Aether to write a document, then Privacy → Cronologia → **Annulla** → the previous version is back.
End card: **"L'AI che puoi controllare e annullare."**
Caption: «Ogni risposta ha il suo scontrino: cosa ha usato, cosa è uscito dal computer. E le modifiche ai tuoi documenti si annullano.»

## Demo 3 — "Seconda opinione" (12 s) — needs two configured providers; film only with real keys
Hook: **"Non fidarti di un solo modello."** Ask one question → "Chiedi ad altri modelli" → answers side by side, "Risposte in parte diverse · numeri diversi: 120, 150". End: "Non ti dice chi ha ragione. Ti mostra dove dubitare."

## Posting plan (first two weeks)
- Day 1 Demo 1 (Reel + TikTok), day 3 Demo 2, day 6 a 7 s loop of the Bar appearing, day 9 Demo 3 (if keys), day 12 a "how it works" carousel (4 slides: capture → read locally → hide → send).
- Pin the GitHub link in bio; reply to comments with the IT/EN explanation; never answer "it's 100% safe": say "it hides what it can recognise; you can add your own blur".
- Honest limits to mention when asked: pattern-based (misses names/addresses), Mac Apple Silicon only, not notarized yet.

## How to record clips from the real app
- Use the packaged app with a throw-away data dir (never your real one): `HOME=$(mktemp -d) AETHER_DATA_DIR=$HOME/data build/Aether.app/Contents/MacOS/aether-desktop`.
- Screen recording: macOS Screenshot toolbar (⇧⌘5) or `ffmpeg -f avfoundation -i "1" -r 30 out.mp4`; crop to 9:16 with `ffmpeg -i out.mp4 -vf "crop=ih*9/16:ih" reel.mp4`.
- Captions are text overlays added in any editor; keep them ≥ 48 px and under 8 words per card.
