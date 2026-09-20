from __future__ import annotations

import json

from jev_router import routing_campaign
from jev_router.models import Attempt, Usage
from jev_router.swebench_runner import SWEbenchTask
from jev_router.tiered_routing import TieredJudgment


class Provider:
    def __init__(self, config):
        pass

    def judge(self, task):
        return TieredJudgment(
            "terra",
            {"luna": 0.1, "terra": 0.8, "sol": 0.1, "astra": 0.0},
            0.8,
            "low",
            {"low": 1.0},
            0.1,
            Usage(100, 0),
            5.0,
            "jev",
            0.0001,
            (Attempt(Usage(100, 0), 5.0, "ok"),),
        )


def test_routing_campaign_checkpoints_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(routing_campaign, "OpenRouterTieredJevProvider", Provider)
    task = SWEbenchTask("owner__repo-1", "owner/repo", "abcdef0", "Fix the bug")

    first = routing_campaign.route_swebench_tasks(
        [task], suite="suite", output_dir=tmp_path, config=object()
    )
    second = routing_campaign.route_swebench_tasks(
        [task], suite="suite", output_dir=tmp_path, config=object()
    )

    assert first["tasks_routed"] == second["tasks_routed"] == 1
    assert first["route_distribution"] == {"terra": 1}
    assert json.loads((tmp_path / "routing-summary.json").read_text())["jev_route_cost_usd"] == 0.0001
