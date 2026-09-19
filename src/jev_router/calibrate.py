from __future__ import annotations

from dataclasses import dataclass

from .models import Task
from .scoring import score_output


@dataclass(frozen=True)
class CalibrationPoint:
    threshold: float
    quality: float
    quality_loss_pp: float
    strong_rate: float


def calibration_curve(tasks: list[Task]) -> list[CalibrationPoint]:
    if not tasks:
        raise ValueError("calibration requires at least one dev task")
    strong_quality = [score_output(task, task.fixture["strong"]["text"]) for task in tasks]
    cheap_quality = [score_output(task, task.fixture["cheap"]["text"]) for task in tasks]
    baseline = sum(strong_quality) / len(tasks)
    thresholds = sorted({0.0, 1.0, *(float(task.jev_fixture["probabilities"]["strong"]) for task in tasks)})
    points: list[CalibrationPoint] = []
    for threshold in thresholds:
        selected_strong = [float(task.jev_fixture["probabilities"]["strong"]) >= threshold for task in tasks]
        quality = sum(
            strong_quality[index] if is_strong else cheap_quality[index]
            for index, is_strong in enumerate(selected_strong)
        ) / len(tasks)
        points.append(
            CalibrationPoint(
                threshold=threshold,
                quality=quality,
                quality_loss_pp=(baseline - quality) * 100,
                strong_rate=sum(selected_strong) / len(tasks),
            )
        )
    return points


def select_threshold(points: list[CalibrationPoint], max_loss_pp: float) -> CalibrationPoint:
    feasible = [point for point in points if point.quality_loss_pp <= max_loss_pp]
    if not feasible:
        return min(points, key=lambda point: point.quality_loss_pp)
    return min(feasible, key=lambda point: (point.strong_rate, point.threshold))
