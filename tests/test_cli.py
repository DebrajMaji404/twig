"""
Tests for the twig CLI. Runs the real `twig` console script as a
subprocess (not just calling internal functions), since that's what
actually needs to work for users -- catches packaging/entry-point issues
that calling cli.main() directly in-process would miss.
"""

import json
import subprocess
import sys

import pytest


def run_cli(args, input_text=None, cwd=None):
    """Runs `python -m twig.cli <args>` as a subprocess (equivalent to
    the installed `twig` command, but doesn't depend on PATH setup in
    whatever environment runs the tests)."""
    return subprocess.run(
        [sys.executable, "-m", "twig.cli"] + args,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


@pytest.fixture
def sample_data():
    return [
        {
            "name": "ffs",
            "address": {
                "present": {"state": "West Bengal", "pin": "713201"},
            },
            "experience": [{"companyName": "Tata Steel", "years": 2}],
        }
    ]


@pytest.fixture
def sample_json_file(tmp_path, sample_data):
    p = tmp_path / "data.json"
    p.write_text(json.dumps(sample_data), encoding="utf-8")
    return p


def test_encode_to_stdout(sample_json_file, sample_data):
    result = run_cli(["encode", str(sample_json_file)])
    assert result.returncode == 0
    assert "T:root" in result.stdout
    assert "~L" in result.stdout


def test_encode_then_decode_round_trip(sample_json_file, sample_data, tmp_path):
    twig_file = tmp_path / "out.twig"
    r1 = run_cli(["encode", str(sample_json_file), "-o", str(twig_file)])
    assert r1.returncode == 0
    assert twig_file.exists()

    r2 = run_cli(["decode", str(twig_file)])
    assert r2.returncode == 0
    assert json.loads(r2.stdout) == sample_data


def test_stdin_input_with_dash(sample_data):
    result = run_cli(["encode", "-"], input_text=json.dumps(sample_data))
    assert result.returncode == 0
    assert "T:root" in result.stdout


def test_decode_compact_flag(sample_json_file, sample_data, tmp_path):
    twig_file = tmp_path / "out.twig"
    run_cli(["encode", str(sample_json_file), "-o", str(twig_file)])
    result = run_cli(["decode", str(twig_file), "--compact"])
    assert result.returncode == 0
    assert "\n" not in result.stdout.strip()  # compact = single line
    assert json.loads(result.stdout) == sample_data


def test_missing_input_file_exits_nonzero():
    result = run_cli(["encode", "definitely_does_not_exist.json"])
    assert result.returncode == 1
    assert "no such file" in result.stderr
    assert "Traceback" not in result.stderr  # no raw Python traceback leaked


def test_invalid_json_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("not valid json{{{", encoding="utf-8")
    result = run_cli(["encode", str(bad)])
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr
    assert "Traceback" not in result.stderr


def test_malformed_twig_exits_nonzero(tmp_path):
    bad = tmp_path / "bad.twig"
    bad.write_text("garbage not twig at all", encoding="utf-8")
    result = run_cli(["decode", str(bad)])
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_single_object_shape_preserved_through_cli(tmp_path):
    """CLI-level regression test for the same shape-preservation bug
    fixed in the core codec: a single JSON object (not a list) must
    come back as a single object, not wrapped in a list."""
    data = {"status": "success", "meta": {"total": 1}}
    json_file = tmp_path / "single.json"
    json_file.write_text(json.dumps(data), encoding="utf-8")

    twig_file = tmp_path / "single.twig"
    run_cli(["encode", str(json_file), "-o", str(twig_file)])

    result = run_cli(["decode", str(twig_file), "--compact"])
    decoded = json.loads(result.stdout)
    assert decoded == data
    assert isinstance(decoded, dict)
