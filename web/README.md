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
