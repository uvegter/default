"""Preference profile: a pure function of the student's responses.

Everything here is ordinary, inspectable arithmetic. No model call. The syllabus
contributes NO observation: only what the student answered does (including their
own optional liked/disliked flag on a module).
"""
from __future__ import annotations

import math
from typing import Any

from ..config import SurveyConfig
from ..curriculum.review import CurriculumContext
from ..models import Conflict, DisciplinePack, HistoryEntry, Module, Observation, PreferenceProfile


def likert_value(rating: Any) -> float | None:
    try:
        r = int(rating)
    except (TypeError, ValueError):
        return None
    return (r - 1) / 4 if 1 <= r <= 5 else None


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _shrunk(observations: list[Observation], prior: float, prior_strength: float) -> tuple[float, float]:
    w = sum(o.weight for o in observations)
    total = prior_strength * prior + sum(o.weight * o.value for o in observations)
    return total / (prior_strength + w), w


def build_profile(cfg: SurveyConfig, pack: DisciplinePack, calibration: dict[str, Any], history: list[HistoryEntry],
                  ctx: CurriculumContext, studied_modules: list[Module] | None = None) -> PreferenceProfile:
    sc = cfg.scoring
    obs: list[Observation] = []

    # ---- Phase A: direct ratings -------------------------------------------
    prefix = cfg.calibration["field_interest"]["id_prefix"]
    for f in pack.fields:
        v = likert_value(calibration.get(f"{prefix}:{f.id}"))
        if v is not None:
            obs.append(Observation(key=f"field.{f.id}", value=v, weight=sc["field_rating_weight"],
                                   source=f"{prefix}:{f.id}", kind="field_rating"))
    values_opted_in = likert_value(calibration.get("cal_values_distribution")) is not None
    for item in cfg.all_likert_items():
        v = likert_value(calibration.get(item["id"]))
        if v is None:
            continue
        for key, sign in item.get("signals", {}).items():
            obs.append(Observation(key=key, value=v if sign > 0 else 1 - v, weight=sc["likert_weight"],
                                   source=item["id"], kind="likert"))
    # The student's own flag on a module they studied is a response, so it may inform field interest.
    for mod in studied_modules or []:
        if mod.enjoyment in ("liked", "disliked"):
            for fid in mod.broad_areas:
                obs.append(Observation(key=f"field.{fid}", value=1.0 if mod.enjoyment == "liked" else 0.0,
                                       weight=sc["module_enjoyment_weight"], source=f"module:{mod.id}", kind="module_flag"))

    # Field interest before any choices: ratings (and module flags) shrunk towards neutral.
    k = sc["prior_strength"]
    f_base = {f.id: _shrunk([o for o in obs if o.key == f"field.{f.id}"], 0.5, k)[0] for f in pack.fields}
    f_delta = {f.id: 0.0 for f in pack.fields}
    t_delta = {t.id: 0.0 for t in pack.territories}
    t_count = {t.id: 0.0 for t in pack.territories}

    def t_score(t) -> float:
        return _clip(_clip(f_base[t.field] + f_delta[t.field]) + t_delta[t.id])

    # ---- Phase B/C: choices -------------------------------------------------
    n_unsure = 0
    lv = cfg.level_values
    reason_attrs = cfg.choice_tasks.get("reason_attributes", {})
    for h in history:
        r, spec = h.response, h.spec
        if r.selected_option_id is None:
            n_unsure += 1
            continue
        w = sc["strength_weights"].get(r.strength or "", sc["choice_weight_default"])
        chosen, rejected = spec.option(r.selected_option_id), spec.other(r.selected_option_id)
        if spec.template_id != "territory_pair":
            for key, val in chosen.signals.items():
                obs.append(Observation(key=key, value=float(val), weight=w, source=spec.id, kind="choice"))
            continue
        tc, tr = pack.territory(chosen.territory_id), pack.territory(rejected.territory_id)
        # Topic interest: an Elo-style step. The chosen territory moves up and the other down; the move is
        # small when the choice was expected from earlier answers and larger when it was a surprise, so a
        # runner-up is not written off merely for losing to the current favourite.
        sc_c, sc_r = t_score(tc), t_score(tr)
        expected = 1 / (1 + math.exp(-(sc_c - sc_r) / sc["expectation_scale"]))
        step = sc["choice_step"] * w * (1 - expected)
        t_delta[tc.id] += step
        t_delta[tr.id] -= step
        t_count[tc.id] += w
        t_count[tr.id] += w
        obs.append(Observation(key=f"territory.{tc.id}", value=step, weight=w, source=spec.id, kind="choice"))
        obs.append(Observation(key=f"territory.{tr.id}", value=-step, weight=w, source=spec.id, kind="choice"))
        if tc.field != tr.field:
            fstep = step * sc["field_spill"]
            f_delta[tc.field] += fstep
            f_delta[tr.field] -= fstep
            obs.append(Observation(key=f"field.{tc.field}", value=1.0, weight=w * sc["field_spill"], source=spec.id,
                                   kind="choice"))
            obs.append(Observation(key=f"field.{tr.field}", value=0.0, weight=w * sc["field_spill"], source=spec.id,
                                   kind="choice"))
        if r.reason_code == "topic":
            continue   # the student said the subject decided it: card attributes get no credit
        boosted = set(reason_attrs.get(r.reason_code or "", []))

        def aw(attr: str) -> float:
            return w * (sc["attribute_spill_with_reason"] if attr in boosted else sc["attribute_spill"])

        def add(key: str, value: float, attr: str) -> None:
            obs.append(Observation(key=key, value=value, weight=aw(attr), source=spec.id, kind="choice_attribute"))

        ca, ra = chosen.attributes, rejected.attributes
        for attr in ("approach", "style"):
            if ca.get(attr) and ra.get(attr) and ca[attr] != ra[attr]:
                add(f"{attr}.{ca[attr]}", 1.0, attr)
                add(f"{attr}.{ra[attr]}", 0.0, attr)
        if ca.get("policy_relevance") != ra.get("policy_relevance"):
            add("policy_relevance", 1.0 if lv["policy_relevance"][ca["policy_relevance"]] >
                lv["policy_relevance"][ra["policy_relevance"]] else 0.0, "policy_relevance")
        for attr in ("data_access", "technical_demand"):
            if ca.get(attr) != ra.get(attr):   # lower level value = harder
                add("feasibility_tolerance", 1.0 if lv[attr][ca[attr]] < lv[attr][ra[attr]] else 0.0, attr)
        if values_opted_in and ca.get("distributional_focus") != ra.get("distributional_focus"):
            add("distributional_values", 1.0 if lv["distributional_focus"][ca["distributional_focus"]] >
                lv["distributional_focus"][ra["distributional_focus"]] else 0.0, "distributional_focus")
        fam = sc["familiarity_values"]
        fc, fr = ca.get("familiarity"), ra.get("familiarity")
        if fc in fam and fr in fam and fam[fc] != fam[fr]:
            add("novelty", 1.0 if fam[fc] < fam[fr] else 0.0, "familiarity")

    # ---- aggregate ----------------------------------------------------------
    by_key: dict[str, list[Observation]] = {}
    for o in obs:
        by_key.setdefault(o.key, []).append(o)
    profile = PreferenceProfile(observations=obs, n_tasks=len(history), n_unsure=n_unsure)
    for key in cfg.preference_keys:
        if key == "distributional_values" and not values_opted_in:
            continue   # skipped optional item: the key simply does not exist for this student
        profile.key_scores[key], profile.key_weights[key] = _shrunk(by_key.get(key, []), 0.5, k)
    for f in pack.fields:
        profile.field_scores[f.id] = _clip(f_base[f.id] + f_delta[f.id])
        profile.key_weights[f"field.{f.id}"] = sum(o.weight for o in by_key.get(f"field.{f.id}", []))
    for t in pack.territories:
        profile.territory_scores[t.id] = t_score(t)
        profile.key_weights[f"territory.{t.id}"] = t_count[t.id]
    profile.constraints = {c["id"]: calibration[c["id"]] for c in cfg.calibration["constraints"]
                           if calibration.get(c["id"])}
    profile.conflicts = detect_conflicts(cfg, pack, profile, calibration, by_key)
    return profile


def detect_conflicts(cfg: SurveyConfig, pack: DisciplinePack, profile: PreferenceProfile, calibration: dict[str, Any],
                     by_key: dict[str, list[Observation]]) -> list[Conflict]:
    """Tensions between signals. Reported as trade-offs to think about, never as errors."""
    hi, lo = cfg.adaptive["conflict_high"], cfg.adaptive["conflict_low"]
    out: list[Conflict] = []
    if profile.score("style.causal_identification") >= hi and profile.score("approach.quant_empirical") <= lo:
        out.append(Conflict(id="cl_causal_vs_data", keys=["style.causal_identification", "approach.quant_empirical"],
                            description="You are drawn to cause-and-effect questions but less keen on hands-on data "
                                        "work. Causal questions usually need data methods, so discuss which matters more."))
    if profile.score("policy_relevance") >= hi and profile.score("approach.theory_modelling") >= hi:
        out.append(Conflict(id="cl_policy_vs_theory", keys=["policy_relevance", "approach.theory_modelling"],
                            description="You value real-world relevance and also enjoy theory. Both are possible, but "
                                        "a dissertation usually leans one way."))
    prefix = cfg.calibration["field_interest"]["id_prefix"]
    for f in pack.fields:
        rating = calibration.get(f"{prefix}:{f.id}")
        choices = [o for o in by_key.get(f"field.{f.id}", []) if o.kind == "choice"]
        if rating is None or len(choices) < 2:
            continue
        wins = sum(1 for o in choices if o.value == 1.0)
        if int(rating) >= 4 and wins == 0:
            out.append(Conflict(id=f"rated_high_chose_against:{f.id}", keys=[f"field.{f.id}"],
                                description=f"You rated {f.label} highly but chose other areas over it each time it "
                                            "appeared. Your choices were given more weight than the rating."))
        elif int(rating) <= 2 and wins == len(choices):
            out.append(Conflict(id=f"rated_low_chose_for:{f.id}", keys=[f"field.{f.id}"],
                                description=f"You rated {f.label} low but chose it each time it appeared. It may "
                                            "deserve a second look."))
    return out
