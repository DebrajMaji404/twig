# Twig web playground

A minimal web UI to try Twig in the browser: paste JSON, get compact
Twig text back (and vice versa), with a live token/char-reduction stat.
Encoding and decoding run as **real Python** via a Vercel serverless
function — not a JavaScript reimplementation — so what you see here is
exactly the same codec (`twig/codec.py`) the rest of this repo tests.

## Structure

```
web/
├── index.html          # frontend UI (vanilla HTML/CSS/JS, no build step)
├── api/
│   ├── index.py         # Flask app: /api/encode, /api/decode, /api/health
│   └── twig_codec.py     # a copy of ../../twig/codec.py -- keep in sync!
├── requirements.txt      # just "flask"
└── vercel.json           # routes /api/* to the Flask entrypoint
```

**Why a copy of `codec.py`?** Vercel's Python runtime bundles files
reachable from the function's own directory; keeping a self-contained
copy under `api/` avoids relying on package-install behavior across the
whole monorepo. If you change `twig/codec.py`, copy your changes into
`web/api/twig_codec.py` too (or wire up a symlink / build step if you'd
rather not maintain two copies by hand).

## Deploy to Vercel (free, Hobby plan)

```bash
cd web
npx vercel          # first deploy, follow the prompts
npx vercel --prod   # promote to production
```

Or connect the GitHub repo directly in the Vercel dashboard and set the
**Root Directory** to `web/` in the project settings, so Vercel only
builds this subfolder rather than the whole monorepo.

No environment variables or build command needed — `requirements.txt`
plus the `api/` convention is all Vercel's Python runtime needs.

## Analytics: page views and visitor count

This page has two separate pieces, both optional and independent of
each other:

**1. Collecting the data** — a tracking script (`/_vercel/insights/script.js`)
is already included in `index.html`. It does nothing on its own until
you enable Web Analytics for this project:

1. Vercel dashboard → your project → **Analytics** tab → **Enable**.
2. Deploy (or just wait for the next deploy) — the script starts
   sending page-view events automatically, no code changes needed.
3. You can see the numbers immediately in the Vercel dashboard's
   Analytics tab. This part is free on the Hobby plan within Vercel's
   usage limits.

**2. Displaying the numbers on the page itself** (the part in the
footer, "X page views from Y visitors") — this needs a bit more setup,
since it calls [Vercel's Web Analytics
API](https://vercel.com/docs/analytics/web-analytics-api) from the
`/api/stats` serverless function using a personal access token that
must stay server-side (never exposed to visitors' browsers):

1. **Create an access token**: Vercel dashboard → your avatar → Settings
   → Tokens → Create Token. Give it a name, no special scopes needed
   beyond the default.
2. **Find your project ID**: your project → Settings → General → look
   for "Project ID" (starts with `prj_`).
3. **Find your team ID** (only if this project belongs to a team, not
   your personal account) — Settings → General on the *team* level.
   Personal-account projects should skip this entirely; the API call
   omits `teamId` automatically if unset.
4. **Add these as environment variables** on the project: Settings →
   Environment Variables:
   - `VERCEL_TOKEN` = the token from step 1
   - `VERCEL_PROJECT_ID` = the ID from step 2
   - `VERCEL_TEAM_ID` = the ID from step 3 (skip this one for personal projects)
5. Redeploy. The footer stat line appears automatically once
   `/api/stats` gets a successful response — until then it stays
   hidden (check by visiting `/api/stats` directly; it always returns
   200 with `{"available": false, "reason": "..."}` while unconfigured,
   never a broken page).

**Honest note on testing**: the `/api/stats` endpoint's request-building
and error-handling were tested directly (confirmed it correctly reaches
out to `api.vercel.com` with the right headers and gracefully reports
failures as JSON rather than crashing), but the actual live call to
Vercel's real API was **not** verified end-to-end, since the sandbox
this was built in has no network access to `api.vercel.com` and no real
Vercel credentials to test with. If step 5 doesn't show numbers after a
minute or two, check your deployment's function logs for the exact
error `/api/stats` is returning — it's designed to surface the real
failure reason, not hide it.

## Run locally

```bash
cd web
npm i -g vercel
vercel dev
```

This starts the Flask function on Vercel's local dev server (usually
`http://localhost:3000`), serving `index.html` and the `/api/*` routes
together, exactly like production.

Alternatively, to test just the Python side without Vercel's CLI:

```bash
cd web/api
pip install flask
python3 -c "
from index import app
app.run(port=5000, debug=True)
"
```

Then open `index.html` directly in a browser (you'll need to either
serve it locally or update the fetch URLs to `http://localhost:5000/...`,
since opening the file with `file://` won't have same-origin API access).

## Known limitations of this playground specifically

- Vercel's free Hobby plan serverless functions have a **cold start**
  the first time they're hit after being idle — the first "Convert"
  click after a while may take 1-2 extra seconds.
- Very large pasted JSON (hundreds of KB+) may hit Vercel's default
  request body size limit; this hasn't been tuned or tested here.
- The `@types`/`@tree` header text uses a monospace font in the output
  panel for readability, but Twig's actual bytes are plain UTF-8 text —
  nothing about the format itself depends on how it's displayed.

For the format's own known limitations (not the playground's), see the
main [README](../README.md#known-limitations--read-before-relying-on-this-in-production).
