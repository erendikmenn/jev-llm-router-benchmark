from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .models import Task
from .pricing import estimate_tokens


@dataclass(frozen=True)
class Eligibility:
    eligible_roles: tuple[str, ...]
    reject_reason: str | None


def check_eligibility(task: Task, config: AppConfig) -> Eligibility:
    modality = task.constraints.get("modality", "text")
    if modality != "text":
        return Eligibility((), f"unsupported_modality:{modality}")
    if task.constraints.get("requires_tools", False):
        return Eligibility((), "tools_not_enabled_in_v1")

    estimated = estimate_tokens(task.prompt)
    requested_output = int(
        task.constraints.get("max_output_tokens", config.experiment["max_output_tokens"])
    )
    roles: list[str] = []
    for role in ("cheap", "strong"):
        model = getattr(config, role)
        if (
            estimated + requested_output <= model.context_tokens
            and requested_output <= model.max_output_tokens
            and model.text_only_benchmark_eligible
        ):
            roles.append(role)
    if not roles:
        return Eligibility((), "context_or_output_limit_exceeded")
    return Eligibility(tuple(roles), None)

