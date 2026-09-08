"""
Vercel Python serverless function (Flask/WSGI, the currently-documented
pattern for Vercel's Python runtime as of 2026 -- see
https://vercel.com/docs/functions/runtimes/python).

Single entrypoint handling both routes; vercel.json rewrites /api/*
requests here so Flask's own router does the rest.

Uses the real, tested twig codec (twig_codec.py, a copy of the package's
twig/codec.py kept in sync with the main repo) -- genuine Python
execution, not a JS reimplementation.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Make this file's own directory importable regardless of HOW it gets
# loaded. Vercel's "default location" invocation (api/index.py found
# directly) adds this file's own directory to sys.path automatically --
# but the dotted-entrypoint style (web.api.index:app, used when deploying
# from the repo root instead of web/) imports it as part of a package
# path, where that implicit same-directory behavior is NOT guaranteed.
# Without this, `from twig_codec import ...` below could fail with
# ModuleNotFoundError depending on which of those two ways Vercel chose.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, request, jsonify, Response
from twig_codec import encode, decode

app = Flask(__name__)

_INDEX_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html")


@app.route("/")
def serve_index():
    # Flask handles every request here (confirmed: without this route,
    # Flask itself returned "Not Found" for "/", proving requests DO
    # reach this app correctly -- the missing piece was just this route,
    # not a Vercel routing/rewrite problem).
    with open(_INDEX_HTML_PATH, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/encode", methods=["POST", "OPTIONS"])
def api_encode():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        payload = request.get_json(force=True)
        data = payload["json"]

        twig_text = encode(data)
        json_str = json.dumps(data)

        json_chars = len(json_str)
        twig_chars = len(twig_text)
        reduction = (1 - twig_chars / json_chars) * 100 if json_chars else 0

        return jsonify({
            "twig": twig_text,
            "json_chars": json_chars,
            "twig_chars": twig_chars,
            "reduction_pct": round(reduction, 1),
        })
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


@app.route("/api/decode", methods=["POST", "OPTIONS"])
def api_decode():
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        payload = request.get_json(force=True)
        twig_text = payload["twig"]
        data = decode(twig_text)
        return jsonify({"json": data})
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """
    Proxies Vercel's Web Analytics API (docs.vercel.com/docs/analytics/
    web-analytics-api) so the page can display real visitor/pageview
    counts without ever exposing the access token to the browser -- the
    token stays server-side, read from an environment variable.

    Requires these environment variables to be set in the Vercel project
    (Settings -> Environment Variables), documented in web/README.md:
      VERCEL_TOKEN       -- a personal access token (Account Settings -> Tokens)
      VERCEL_PROJECT_ID  -- this project's ID (Project Settings -> General)
      VERCEL_TEAM_ID     -- optional; omit entirely for a personal-account
                            project (not part of a team), per Vercel's docs

    Always returns 200 with an "available" flag rather than a hard error
    when unconfigured, so the frontend can just hide the stats widget
    instead of showing a broken state before setup is done.
    """
    token = os.environ.get("VERCEL_TOKEN")
    project_id = os.environ.get("VERCEL_PROJECT_ID")
    team_id = os.environ.get("VERCEL_TEAM_ID")

    if not token or not project_id:
        return jsonify({
            "available": False,
            "reason": "VERCEL_TOKEN and/or VERCEL_PROJECT_ID environment "
                      "variables are not set. See web/README.md for setup.",
        })

    params = {"projectId": project_id}
    if team_id:
        params["teamId"] = team_id
    url = "https://api.vercel.com/v1/query/web-analytics/visits/count?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        data = body.get("data", {})
        return jsonify({
            "available": True,
            "pageviews": data.get("pageviews", 0),
            "visitors": data.get("visitors", 0),
        })
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        return jsonify({"available": False, "reason": f"Vercel API returned {e.code}: {detail}"})
    except Exception as e:
        return jsonify({"available": False, "reason": f"{type(e).__name__}: {e}"})


# Vercel's Python runtime looks for a WSGI `app` object in this file.
