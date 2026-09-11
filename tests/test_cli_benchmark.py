"""
Tests for the twig CLI benchmark command and --tokens flag.
"""

import json
import subprocess
import sys
import pytest


def run_cli(args, input_text=None, cwd=None):
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
            "name": f"User{i}",
            "role": "Engineer",
            "address": {"city": "New York", "zip": f"1000{i}"},
            "tags": ["alpha", "beta"],
        }
        for i in range(10)
    ]


@pytest.fixture
def sample_json_file(tmp_path, sample_data):
    p = tmp_path / "data.json"
    p.write_text(json.dumps(sample_data), encoding="utf-8")
    return p


def test_cli_benchmark_file(sample_json_file):
    result = run_cli(["benchmark", str(sample_json_file)])
    assert result.returncode == 0
    assert "Twig Token Benchmark" in result.stdout
    assert "JSON (pretty)" in result.stdout
    assert "JSON (minified)" in result.stdout
    assert "Twig" in result.stdout
    assert "vs. Min JSON" in result.stdout


def test_cli_benchmark_stdin(sample_data):
    result = run_cli(["benchmark", "-"], input_text=json.dumps(sample_data))
    assert result.returncode == 0
    assert "Twig Token Benchmark: -" in result.stdout
    assert "Tokens" in result.stdout


def test_cli_encode_tokens_flag(sample_json_file, tmp_path):
    out = tmp_path / "out.twig"
    result = run_cli(["encode", str(sample_json_file), "-o", str(out), "--stats", "--tokens"])
    assert result.returncode == 0
    assert out.exists()
    assert "tokens (" in result.stderr
    assert "smaller" in result.stderr
