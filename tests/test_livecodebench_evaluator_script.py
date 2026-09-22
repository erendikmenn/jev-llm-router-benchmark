from __future__ import annotations

import importlib.util
import base64
import json
import pickle
import zlib
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "evaluate_livecodebench_subset.py"
SPEC = importlib.util.spec_from_file_location("lcb_eval_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_candidate_pass_requires_every_official_test_to_pass():
    assert MODULE._candidate_passed({0: [[True, True]]}, 0)
    assert not MODULE._candidate_passed({0: [[True, False]]}, 0)
    assert not MODULE._candidate_passed({0: [[]]}, 0)


def test_evaluation_sample_combines_public_and_encoded_private_tests():
    private = [{"input": "2\n", "output": "4\n", "testtype": "stdin"}]
    encoded = base64.b64encode(zlib.compress(pickle.dumps(json.dumps(private)))).decode()
    sample = MODULE._evaluation_sample(
        {
            "public_test_cases": json.dumps(
                [{"input": "1\n", "output": "2\n", "testtype": "stdin"}]
            ),
            "private_test_cases": encoded,
            "metadata": json.dumps({"func_name": None}),
        }
    )

    payload = json.loads(sample["input_output"])
    assert payload == {
        "inputs": ["1\n", "2\n"],
        "outputs": ["2\n", "4\n"],
        "fn_name": None,
    }
