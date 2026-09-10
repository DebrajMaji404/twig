"""
Standard performance benchmark suite using pytest-benchmark.
Measures execution speed, throughput (ops/sec), min/max/mean/median latency.

Run with:
    python -m pytest tests/test_benchmark_performance.py --benchmark-columns=min,max,mean,stddev,median,ops
"""

import json
import pytest
from benchmarks.gpt_tokenizer_benchmark import make_person, toon_encode
from benchmarks.scaling_projection import make_dense_record, make_sparse_record
from twig.codec import encode as twig_encode, decode as twig_decode


@pytest.fixture(scope="module")
def data_10():
    return [make_person(i) for i in range(10)]


@pytest.fixture(scope="module")
def data_100():
    return [make_person(i) for i in range(100)]


@pytest.fixture(scope="module")
def data_1000():
    return [make_dense_record(i) for i in range(1000)]


@pytest.fixture(scope="module")
def data_sparse_100():
    return [make_sparse_record(i) for i in range(100)]


@pytest.fixture(scope="module")
def encoded_twig_10(data_10):
    return twig_encode(data_10)


@pytest.fixture(scope="module")
def encoded_twig_100(data_100):
    return twig_encode(data_100)


@pytest.fixture(scope="module")
def encoded_twig_1000(data_1000):
    return twig_encode(data_1000)


# ---------------------------------------------------------------------------
# Twig Encode Benchmarks
# ---------------------------------------------------------------------------

def test_benchmark_twig_encode_10(benchmark, data_10):
    benchmark(twig_encode, data_10)


def test_benchmark_twig_encode_100(benchmark, data_100):
    benchmark(twig_encode, data_100)


def test_benchmark_twig_encode_1000(benchmark, data_1000):
    benchmark(twig_encode, data_1000)


def test_benchmark_twig_encode_sparse_100(benchmark, data_sparse_100):
    benchmark(twig_encode, data_sparse_100)


# ---------------------------------------------------------------------------
# Twig Decode Benchmarks
# ---------------------------------------------------------------------------

def test_benchmark_twig_decode_10(benchmark, encoded_twig_10):
    benchmark(twig_decode, encoded_twig_10)


def test_benchmark_twig_decode_100(benchmark, encoded_twig_100):
    benchmark(twig_decode, encoded_twig_100)


def test_benchmark_twig_decode_1000(benchmark, encoded_twig_1000):
    benchmark(twig_decode, encoded_twig_1000)


# ---------------------------------------------------------------------------
# Comparison Benchmarks: Twig vs JSON vs TOON
# ---------------------------------------------------------------------------

def test_benchmark_json_dumps_100(benchmark, data_100):
    benchmark(json.dumps, data_100)


def test_benchmark_json_loads_100(benchmark, data_100):
    s = json.dumps(data_100)
    benchmark(json.loads, s)


def test_benchmark_toon_encode_100(benchmark, data_100):
    benchmark(toon_encode, data_100)
