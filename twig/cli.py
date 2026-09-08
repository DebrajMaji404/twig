"""
Command-line interface for Twig.

    twig encode file.json                  # writes compact Twig to stdout
    twig encode file.json -o file.twig      # writes to a file instead
    twig decode file.twig                  # writes JSON to stdout (pretty)
    twig decode file.twig -o file.json      # writes to a file instead
    twig encode -                           # reads JSON from stdin
    cat file.json | twig encode -           # same, piped

Exit codes: 0 on success, 1 on any error (bad JSON, malformed Twig text,
missing file, etc.) -- errors are printed to stderr with a clear message,
never a raw Python traceback, so this is safe to use in scripts/pipelines.
"""

from __future__ import annotations

import argparse
import json
import sys

from .codec import decode as twig_decode
from .codec import encode as twig_encode


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_output(text: str, path: str | None) -> None:
    if path is None or path == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def cmd_encode(args: argparse.Namespace) -> int:
    try:
        raw = _read_input(args.input)
    except FileNotFoundError:
        print(f"twig encode: no such file: {args.input}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"twig encode: could not read {args.input}: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"twig encode: {args.input} is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        result = twig_encode(data)
    except Exception as e:
        print(f"twig encode: failed to encode: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    _write_output(result, args.output)

    if args.stats and args.output:
        json_chars = len(raw)
        twig_chars = len(result)
        reduction = (1 - twig_chars / json_chars) * 100 if json_chars else 0
        direction = "smaller" if reduction >= 0 else "larger"
        print(f"twig encode: {json_chars} -> {twig_chars} chars ({abs(reduction):.1f}% {direction})", file=sys.stderr)

    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    try:
        raw = _read_input(args.input)
    except FileNotFoundError:
        print(f"twig decode: no such file: {args.input}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"twig decode: could not read {args.input}: {e}", file=sys.stderr)
        return 1

    try:
        data = twig_decode(raw)
    except Exception as e:
        print(f"twig decode: failed to decode: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    indent = None if args.compact else 2
    result = json.dumps(data, indent=indent, ensure_ascii=False)
    _write_output(result, args.output)

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twig",
        description="Encode JSON to compact Twig text, or decode it back.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_encode = subparsers.add_parser("encode", help="JSON -> Twig")
    p_encode.add_argument("input", help="path to a JSON file, or '-' for stdin")
    p_encode.add_argument("-o", "--output", help="write to this file instead of stdout")
    p_encode.add_argument(
        "--stats", action="store_true",
        help="print char-count reduction to stderr (only meaningful with -o, "
             "since stdout is reserved for the encoded text itself)",
    )
    p_encode.set_defaults(func=cmd_encode)

    p_decode = subparsers.add_parser("decode", help="Twig -> JSON")
    p_decode.add_argument("input", help="path to a Twig text file, or '-' for stdin")
    p_decode.add_argument("-o", "--output", help="write to this file instead of stdout")
    p_decode.add_argument(
        "--compact", action="store_true",
        help="write minified JSON instead of pretty-printed (indent=2)",
    )
    p_decode.set_defaults(func=cmd_decode)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
