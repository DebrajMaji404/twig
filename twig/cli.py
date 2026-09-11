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


def count_tokens(text: str, encoding_name: str = "o200k_base") -> tuple[int, bool]:
    """Returns (token_count, is_exact). Uses tiktoken if available, else heuristic."""
    try:
        import tiktoken
        try:
            enc = tiktoken.get_encoding(encoding_name)
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text, disallowed_special=())), True
    except Exception:
        # Fallback heuristic: ~3.8 chars/token for structured text
        return max(1, int(len(text) / 3.8)), False


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

    if (args.stats or getattr(args, "tokens", False)) and args.output:
        json_chars = len(raw)
        twig_chars = len(result)
        reduction = (1 - twig_chars / json_chars) * 100 if json_chars else 0
        direction = "smaller" if reduction >= 0 else "larger"
        stat_line = f"twig encode: {json_chars} -> {twig_chars} chars ({abs(reduction):.1f}% {direction})"

        if getattr(args, "tokens", False):
            encoding = getattr(args, "encoding", "o200k_base")
            j_tok, is_exact = count_tokens(raw, encoding)
            t_tok, _ = count_tokens(result, encoding)
            tok_red = (1 - t_tok / j_tok) * 100 if j_tok else 0
            tok_dir = "smaller" if tok_red >= 0 else "larger"
            exact_lbl = encoding if is_exact else f"est. {encoding}"
            stat_line += f" | {j_tok} -> {t_tok} tokens ({abs(tok_red):.1f}% {tok_dir}, {exact_lbl})"

        print(stat_line, file=sys.stderr)

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


def cmd_benchmark(args: argparse.Namespace) -> int:
    try:
        raw = _read_input(args.input)
    except FileNotFoundError:
        print(f"twig benchmark: no such file: {args.input}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"twig benchmark: could not read {args.input}: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"twig benchmark: {args.input} is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        twig_text = twig_encode(data)
    except Exception as e:
        print(f"twig benchmark: failed to encode to Twig: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    pretty_json = json.dumps(data, indent=2, ensure_ascii=False)
    min_json = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    try:
        import yaml
        yaml_text = yaml.dump(data, allow_unicode=True, sort_keys=False)
    except Exception:
        yaml_text = None

    encoding_name = getattr(args, "encoding", "o200k_base")
    formats = [
        ("JSON (pretty)", pretty_json),
        ("JSON (minified)", min_json),
    ]
    if yaml_text is not None:
        formats.append(("YAML", yaml_text))
    formats.append(("Twig", twig_text))

    rows = []
    min_tok = None
    pretty_tok = None
    is_exact = True

    for name, text in formats:
        chars = len(text)
        tokens, exact = count_tokens(text, encoding_name)
        is_exact = exact
        if name == "JSON (minified)":
            min_tok = tokens
        elif name == "JSON (pretty)":
            pretty_tok = tokens
        rows.append((name, chars, tokens))

    title = f"Twig Token Benchmark: {args.input}"
    enc_info = f"Tokenizer: {encoding_name}" if is_exact else f"Tokenizer: {encoding_name} (heuristic fallback)"
    print(f"\n{title}")
    print(enc_info)
    print("=" * 74)
    header = f"{'Format':<18} {'Chars':>10} {'Tokens':>10} {'vs. Min JSON':>15} {'vs. Pretty':>15}"
    print(header)
    print("-" * 74)

    for name, chars, tokens in rows:
        vs_min = f"{(tokens - min_tok) / min_tok * 100:+.1f}%" if min_tok else "baseline"
        if name == "JSON (minified)":
            vs_min = "baseline"
        vs_pretty = f"{(tokens - pretty_tok) / pretty_tok * 100:+.1f}%" if pretty_tok else "baseline"
        if name == "JSON (pretty)":
            vs_pretty = "baseline"
        row_str = f"{name:<18} {chars:>10,d} {tokens:>10,d} {vs_min:>15} {vs_pretty:>15}"
        if name == "Twig":
            print("-" * 74)
            print(f">> {row_str}")
        else:
            print(f"   {row_str}")

    print("=" * 74)
    if min_tok and rows[-1][2] < min_tok:
        saved_tok = min_tok - rows[-1][2]
        pct = (saved_tok / min_tok) * 100
        print(f"Twig saves {saved_tok:,d} tokens ({pct:.1f}%) compared to minified JSON.\n")
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
        help="print char-count reduction to stderr (meaningful with -o)",
    )
    p_encode.add_argument(
        "--tokens", action="store_true",
        help="print token-count reduction to stderr using tiktoken (meaningful with -o)",
    )
    p_encode.add_argument(
        "--encoding", default="o200k_base",
        help="tiktoken encoding to use with --tokens (default: o200k_base)",
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

    p_bench = subparsers.add_parser("benchmark", help="Benchmark JSON vs Minified vs YAML vs Twig")
    p_bench.add_argument("input", help="path to a JSON file, or '-' for stdin")
    p_bench.add_argument(
        "--encoding", default="o200k_base",
        help="tiktoken encoding to use (default: o200k_base)",
    )
    p_bench.set_defaults(func=cmd_benchmark)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
