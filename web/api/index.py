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
from flask import Flask, request, jsonify
from twig_codec import encode, decode

app = Flask(__name__)


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


# Vercel's Python runtime looks for a WSGI `app` object in this file.
