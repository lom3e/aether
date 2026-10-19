# Aether website

Marketing and download site for [Aether](https://github.com/lom3e/aether) — Next.js 16, IT/EN, deployed on Vercel at https://aethermate.com.

```bash
npm ci
npm run dev        # http://localhost:3000  (redirects to /it or /en)
npm run lint && npm run typecheck && npm test && npm run build
```

* `NEXT_PUBLIC_SITE_URL` overrides the canonical URL (default `https://aethermate.com`).
* Downloads point to the latest GitHub release asset `Aether.dmg`; no binaries live in this repo.
* Copy lives in `src/content/home.ts`; see `AGENTS.md` for the rules (claims must be true today).
