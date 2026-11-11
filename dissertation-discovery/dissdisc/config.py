"""Loads the researcher-controlled configuration and discipline packs."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .models import DisciplinePack

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("DD_CONFIG_DIR", ROOT / "config"))


class SurveyConfig:
    """Thin read-only wrapper over survey_config.yaml with a few convenience accessors."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw
        self.design_version: str = raw["design_version"]
        self.scales = raw["scales"]
        self.dimensions = raw["dimensions"]
        self.attributes = raw["attributes"]
        self.level_values = raw["level_values"]
        self.calibration = raw["calibration"]
        self.choice_tasks = raw["choice_tasks"]
        self.profile_pairs = {p["id"]: p for p in raw["profile_pairs"]}
        self.clarifications = {c["id"]: c for c in raw["clarifications"]}
        self.scoring = raw["scoring"]
        self.diversity = raw["diversity"]
        self.evidence = raw["evidence"]
        self.adaptive = raw["adaptive"]
        self.uploads = raw["uploads"]
        self._validate()

    # -- convenience -----------------------------------------------------
    @property
    def preference_keys(self) -> list[str]:
        keys: list[str] = []
        for d in self.dimensions:
            keys.extend(d.get("keys", []))
        return keys

    @property
    def dimension_ids(self) -> list[str]:
        return [d["id"] for d in self.dimensions]

    def attribute_label(self, attr: str, level: str) -> str:
        return self.attributes.get(attr, {}).get(level, level)

    def all_likert_items(self) -> list[dict[str, Any]]:
        return list(self.calibration["likert_items"]) + list(self.calibration["optional_items"])

    def _validate(self) -> None:
        """Fail fast if the design references constructs that are not declared."""
        keys = set(self.preference_keys)
        dims = set(self.dimension_ids)
        for item in self.all_likert_items():
            assert item["dimension"] in dims, f"{item['id']}: unknown dimension"
            for k in item.get("signals", {}):
                assert k in keys, f"{item['id']}: unknown preference key {k}"
        for bank in (self.profile_pairs, self.clarifications):
            for pid, p in bank.items():
                assert p["dimension"] in dims, f"{pid}: unknown dimension"
                for side in ("a", "b"):
                    for k in p[side].get("signals", {}):
                        assert k in keys, f"{pid}.{side}: unknown preference key {k}"
        w = self.scoring["weights"]
        assert abs(sum(w.values()) - 1.0) < 1e-6, "scoring weights must sum to 1"
        for pid in self.adaptive["coverage_profile_pairs"] + self.adaptive["followup_profile_pairs"]:
            assert pid in self.profile_pairs, f"adaptive: unknown profile pair {pid}"


@lru_cache(maxsize=4)
def load_survey_config(path: str | None = None) -> SurveyConfig:
    p = Path(path) if path else CONFIG_DIR / "survey_config.yaml"
    return SurveyConfig(yaml.safe_load(p.read_text(encoding="utf-8")))


@lru_cache(maxsize=16)
def load_pack(discipline_id: str) -> DisciplinePack:
    p = CONFIG_DIR / "disciplines" / f"{discipline_id}.yaml"
    if not p.exists():
        raise KeyError(f"No discipline pack named {discipline_id!r}")
    return DisciplinePack.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")))


def list_packs() -> list[DisciplinePack]:
    packs = []
    for p in sorted((CONFIG_DIR / "disciplines").glob("*.yaml")):
        packs.append(load_pack(p.stem))
    # Supported packs first, then alphabetical.
    return sorted(packs, key=lambda x: (not x.supported, x.label))


@lru_cache(maxsize=1)
def load_institutions() -> dict[str, Any]:
    return yaml.safe_load((CONFIG_DIR / "institutions.yaml").read_text(encoding="utf-8"))


def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")
