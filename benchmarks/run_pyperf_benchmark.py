"""
Official Python benchmark runner using pyperf (developed by Python core devs).
Measures statistically sound execution times with process isolation, warmup, and jitter calibration.
"""

import os
import sys
sys.path.insert(0, os.getcwd())

import json
import pyperf
from benchmarks.gpt_tokenizer_benchmark import make_person, toon_encode
from benchmarks.scaling_projection import make_dense_record, make_sparse_record
from twig.codec import encode as twig_encode, decode as twig_decode

if __name__ == "__main__":
    runner = pyperf.Runner()

    data_10 = [make_person(i) for i in range(10)]
    data_100 = [make_person(i) for i in range(100)]
    data_1000 = [make_dense_record(i) for i in range(1000)]
    data_sparse_100 = [make_sparse_record(i) for i in range(100)]

    twig_text_10 = twig_encode(data_10)
    twig_text_100 = twig_encode(data_100)
    twig_text_1000 = twig_encode(data_1000)
    json_text_100 = json.dumps(data_100)

    # Encode benchmarks
    runner.bench_func("twig_encode_10", twig_encode, data_10)
    runner.bench_func("twig_encode_100", twig_encode, data_100)
    runner.bench_func("twig_encode_1000_dense", twig_encode, data_1000)
    runner.bench_func("twig_encode_100_sparse", twig_encode, data_sparse_100)

    # Decode benchmarks
    runner.bench_func("twig_decode_10", twig_decode, twig_text_10)
    runner.bench_func("twig_decode_100", twig_decode, twig_text_100)
    runner.bench_func("twig_decode_1000_dense", twig_decode, twig_text_1000)

    # Format comparison benchmarks (n=100)
    runner.bench_func("json_dumps_100", json.dumps, data_100)
    runner.bench_func("json_loads_100", json.loads, json_text_100)
    runner.bench_func("toon_encode_100", toon_encode, data_100)
