"""Model routing and cost metering.

Default path: Gemini 2.5 Flash-Lite. A larger model is called only when the measured confidence of the
small model is below the threshold in config/models.yaml. Changing provider is a config change.
Every call is metered in INR so the dashboard can report cost per completed exit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .rules import ROOT, load_yaml


@dataclass
class Call:
    step: str
    model: str
    tokens_in: int
    tokens_out: int
    inr: float


@dataclass
class ModelRouter:
    config: dict = field(default_factory=lambda: load_yaml(ROOT / "config" / "models.yaml"))
    calls: list[Call] = field(default_factory=list)

    def _inr(self, spec: dict, tokens_in: int, tokens_out: int) -> float:
        usd = tokens_in / 1e6 * spec["usd_per_1m_input"] + tokens_out / 1e6 * spec["usd_per_1m_output"]
        return usd * self.config["usd_to_inr"]

    def meter(self, step: str, tokens_in: int, tokens_out: int, confidence: float) -> str:
        default = self.config["default"]
        self.calls.append(Call(step, default["model"], tokens_in, tokens_out, self._inr(default, tokens_in, tokens_out)))
        if confidence < self.config["escalate_below_confidence"]:
            big = self.config["escalation"]
            self.calls.append(Call(step, big["model"], tokens_in, tokens_out, self._inr(big, tokens_in, tokens_out)))
            return big["model"]
        return default["model"]

    @property
    def total_inr(self) -> float:
        return sum(c.inr for c in self.calls)

    @property
    def tokens(self) -> tuple[int, int]:
        return sum(c.tokens_in for c in self.calls), sum(c.tokens_out for c in self.calls)


def estimate_from_workflow(steps: list[dict], config_path: Path | None = None) -> float:
    """Design time estimate: sum the llm token budgets in the workflow at the default model price."""
    cfg = load_yaml(config_path or ROOT / "config" / "models.yaml")
    spec = cfg["default"]
    t_in = sum(s.get("llm", {}).get("in", 0) for s in steps)
    t_out = sum(s.get("llm", {}).get("out", 0) for s in steps)
    usd = t_in / 1e6 * spec["usd_per_1m_input"] + t_out / 1e6 * spec["usd_per_1m_output"]
    return usd * cfg["usd_to_inr"]
