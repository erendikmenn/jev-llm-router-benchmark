from __future__ import annotations

import json

from jev_router import swebench_pro_runner


def test_pro_adapter_emits_official_patch_shape(tmp_path, monkeypatch):
    source = tmp_path / "predictions.jsonl"
    source.write_text(
        json.dumps(
            {
                "instance_id": "instance_owner__repo-abc",
                "model_name_or_path": "jev-router/router-only/gpt",
                "model_patch": "diff --git a/a b/a",
            }
        )
        + "\n"
    )

    def fake_generate(*args, **kwargs):
        return {"predictions": str(source), "measurements": []}

    monkeypatch.setattr(swebench_pro_runner, "generate_swebench_arm", fake_generate)
    result = swebench_pro_runner.generate_swebench_pro_arm(
        [],
        arm="router-only",
        workspace_root=tmp_path / "workspaces",
        output_dir=tmp_path,
        config=object(),
    )
    rows = json.loads((tmp_path / "swebench-pro-predictions.json").read_text())

    assert result["pro_prediction_count"] == 1
    assert rows == [
        {
            "instance_id": "instance_owner__repo-abc",
            "patch": "diff --git a/a b/a",
            "prefix": "jev-router-router-only",
        }
    ]
