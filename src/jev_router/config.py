from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model_id: str
    context_tokens: int
    max_output_tokens: int
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    supports_streaming: bool
    text_only_benchmark_eligible: bool
    profile: str


@dataclass(frozen=True)
class AppConfig:
    raw: dict
    cheap: ModelConfig
    strong: ModelConfig

    @property
    def experiment(self) -> dict:
        return self.raw["experiment"]

    @property
    def router(self) -> dict:
        return self.raw["router"]

    @property
    def jev_price(self) -> dict:
        return self.raw["pricing"]["jev"]


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    return AppConfig(
        raw=raw,
        cheap=ModelConfig(**raw["models"]["cheap"]),
        strong=ModelConfig(**raw["models"]["strong"]),
    )
