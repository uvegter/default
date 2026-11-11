"""Rule-based territory ranking, feasibility gate, diversity and evidence labels.

Transparent heuristic scoring (spec §6.2). The weights are placeholders, not
estimates; nothing here is a statistical model of the individual student.
"""
from __future__ import annotations

from .config import SurveyConfig
from .curriculum.review import CurriculumContext
from .models import DisciplinePack, HistoryEntry, PreferenceProfile, Recommendation, Territory


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


def _match(preference: float, level: float) -> float:
    """How well a territory level (0–1) suits a preference (0–1).

    Linear and monotonic: a neutral preference (0.5) is indifferent between levels; the stronger the
    preference, the more a high level is favoured over a low one (and vice versa).
    """
    return preference * level + (1 - preference) * (1 - level)


# -------------------------------------------------------------- components ---
def method_fit(cfg: SurveyConfig, t: Territory, p: PreferenceProfile) -> float:
    mf = cfg.scoring["method_fit"]
    approach = p.score(f"approach.{t.approach}")
    for sec in t.secondary_approaches:
        approach = max(approach, mf["secondary_approach_discount"] * p.score(f"approach.{sec}"))
    style = p.score(f"style.{t.style}")
    return mf["approach_weight"] * approach + mf["style_weight"] * style


def raw_feasibility(cfg: SurveyConfig, t: Territory, p: PreferenceProfile, ctx: CurriculumContext
                    ) -> tuple[float, list[str]]:
    """Initial feasibility from card attributes, stated constraints and taught methods. Returns (score, notes)."""
    fz, lv = cfg.scoring["feasibility"], cfg.level_values
    notes: list[str] = []
    score = (lv["data_access"][t.data_access] + lv["technical_demand"][t.technical_demand]) / 2
    soft = p.constraints.get("con_software")
    if soft in fz["software_adjust"]:
        adj = fz["software_adjust"][soft][t.technical_demand]
        score += adj
        if adj < 0:
            notes.append("The typical methods here are technically demanding relative to the software experience "
                         "you reported.")
    data = p.constraints.get("con_data_access")
    if data in fz["data_adjust"]:
        adj = fz["data_adjust"][data][t.data_access]
        score += adj
        if adj < 0:
            notes.append("You said you can only use freely downloadable data; typical data for this territory "
                         "needs registration, an application or your own collection.")
    if ctx.has_syllabus:
        taught = [m for m in t.methods if m in ctx.method_links]
        if taught:
            score += fz["syllabus_method_taught"]
        else:
            score += fz["syllabus_method_not_found"]
            notes.append("None of the typical methods for this territory were found in your confirmed modules. "
                         "That does not rule it out, but raise it with your supervisor.")
    return _clip(score), notes


def values_alignment(cfg: SurveyConfig, t: Territory, p: PreferenceProfile) -> float:
    lv = cfg.level_values
    parts = [_match(p.score("policy_relevance"), lv["policy_relevance"][t.policy_relevance])]
    if "distributional_values" in p.key_scores:   # only if the student answered the optional item
        parts.append(_match(p.key_scores["distributional_values"], lv["distributional_focus"][t.distributional_focus]))
    return sum(parts) / len(parts)


def exploration_fit(cfg: SurveyConfig, t: Territory, p: PreferenceProfile, ctx: CurriculumContext) -> float:
    fam = cfg.scoring["familiarity_values"].get(ctx.familiarity_of(t.id))
    if fam is None:     # no confirmed syllabus: neutral for every territory
        return 0.5
    return _match(p.score("novelty"), 1 - fam)


# ----------------------------------------------------------------- ranking ---
def rank_territories(cfg: SurveyConfig, pack: DisciplinePack, profile: PreferenceProfile, ctx: CurriculumContext
                     ) -> list[Recommendation]:
    w, fz = cfg.scoring["weights"], cfg.scoring["feasibility"]
    tol = profile.score("feasibility_tolerance")
    out: list[Recommendation] = []
    for t in pack.territories:
        feas, notes = raw_feasibility(cfg, t, profile, ctx)
        # Tolerance softens how much difficulty costs in the ranking; it never makes data available.
        feas_term = _clip(feas + fz["tolerance_relief"] * (tol - 0.5) * (1 - feas))
        comps = {
            "topic_interest": profile.territory_scores.get(t.id, 0.5),
            "method_fit": method_fit(cfg, t, profile),
            "feasibility": feas_term,
            "values_alignment": values_alignment(cfg, t, profile),
            "exploration_fit": exploration_fit(cfg, t, profile, ctx),
        }
        fit = sum(w[k] * comps[k] for k in w)
        flag = feas < fz["gate_threshold"]
        if flag:
            fit *= fz["gate_penalty"]
            notes.insert(0, "Initial feasibility looks low. Treat this as a direction to test with your supervisor "
                            "before committing.")
        out.append(Recommendation(territory_id=t.id, rank=0, fit=round(fit, 6), components=comps, raw_feasibility=feas,
                                  feasibility_flag=flag, familiarity=ctx.familiarity_of(t.id), feasibility_notes=notes))
    out.sort(key=lambda r: (-r.fit, r.territory_id))
    for i, r in enumerate(out, start=1):
        r.rank = i
    return out


def select_diverse(cfg: SurveyConfig, pack: DisciplinePack, ranking: list[Recommendation]) -> list[Recommendation]:
    """Strongest first, then the next-highest directions that are genuinely different."""
    dv = cfg.diversity
    n = dv["n_results"]
    chosen: list[Recommendation] = []

    def similar(a: Territory, b: Territory) -> bool:
        ta, tb = set(a.themes), set(b.themes)
        return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) > dv["max_shared_theme_share"]

    floor = dv["min_topic_interest"]
    # Each pass relaxes one rule, so three results are always returned when three territories exist.
    for max_per_field, check_themes, min_interest in ((dv["max_per_field"], True, floor), (dv["max_per_field"], False, floor),
                                                      (dv["max_per_field"], False, 0.0), (99, False, 0.0)):
        for r in ranking:
            if len(chosen) >= n:
                break
            if r in chosen:
                continue
            t = pack.territory(r.territory_id)
            # An easy or well-matched method never makes up for a topic the student showed little interest in.
            if chosen and r.components["topic_interest"] < min_interest:
                continue
            same_field = sum(1 for c in chosen if pack.territory(c.territory_id).field == t.field)
            if same_field >= max_per_field:
                continue
            if check_themes and any(similar(t, pack.territory(c.territory_id)) for c in chosen):
                continue
            chosen.append(r)
        if len(chosen) >= n:
            break
    result = []
    for i, r in enumerate(chosen, start=1):
        r2 = r.model_copy(deep=True)
        if r.rank != i:
            r2.diversity_note = (f"Ranked {r.rank} on score alone. Higher-scoring territories were left out because "
                                 "they were too close to one already listed, so that the three are genuinely different.")
        r2.rank = i
        result.append(r2)
    return result


# ---------------------------------------------------------------- evidence ---
def evidence_for(cfg: SurveyConfig, pack: DisciplinePack, territory_id: str, profile: PreferenceProfile,
                 history: list[HistoryEntry], calibration: dict) -> tuple[str, float, dict]:
    """How much consistent survey evidence bears on this territory. NOT a probability of anything."""
    ev = cfg.evidence
    pts = ev["points"]
    t = pack.territory(territory_id)
    prefix = cfg.calibration["field_interest"]["id_prefix"]
    detail = {"field_rated": False, "direct_for": 0, "direct_against": 0, "field_for": 0, "field_against": 0}
    for h in history:
        if h.spec.template_id != "territory_pair" or h.response.selected_option_id is None:
            continue
        ids = [o.territory_id for o in h.spec.options]
        chosen = h.spec.option(h.response.selected_option_id).territory_id
        if territory_id in ids:
            detail["direct_for" if chosen == territory_id else "direct_against"] += 1
        else:
            fields = {pack.territory(i).field for i in ids}
            if t.field in fields and len(fields) == 2:
                detail["field_for" if pack.territory(chosen).field == t.field else "field_against"] += 1
    points = 0.0
    if calibration.get(f"{prefix}:{t.field}") is not None:
        detail["field_rated"] = True
        points += pts["field_rated"]
    points += min(pts["direct_task_cap"], pts["direct_task"] * (detail["direct_for"] + detail["direct_against"]))
    points += min(pts["field_task_cap"], pts["field_task"] * (detail["field_for"] + detail["field_against"]))
    min_w = cfg.adaptive["min_key_weight"]
    if profile.weight(f"approach.{t.approach}") >= min_w and profile.weight(f"style.{t.style}") >= min_w:
        points += pts["approach_and_style_observed"]
    contradictions = 0
    if detail["direct_for"] and detail["direct_against"]:
        contradictions += 1
    if any(c.id.endswith(f":{t.field}") for c in profile.conflicts):
        contradictions += 1
    points += pts["contradiction"] * contradictions
    if profile.n_tasks and profile.unsure_share >= ev["unsure_share_threshold"]:
        points += pts["high_unsure_share"]
    detail["contradictions"] = contradictions
    label = "Insufficient information"
    for name, minimum in sorted(ev["labels"].items(), key=lambda kv: -kv[1]):
        if points >= minimum:
            label = name
            break
    return label, round(points, 2), detail


def band(value: float) -> str:
    """Qualitative label for a 0–1 component. Deliberately coarse: no pseudo-precision."""
    if value >= 0.72:
        return "Strong"
    if value >= 0.58:
        return "Good"
    if value >= 0.42:
        return "Mixed"
    return "Weak"
