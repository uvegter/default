"""Simulated students for demos and tests. They answer through the same service
functions as the UI, using a simple taste function; no survey logic lives here."""
from __future__ import annotations

from typing import Any, Callable

from . import service
from .curriculum.review import confirm_curriculum
from .models import QuestionSpec, SessionState, SurveyRun

Persona = dict[str, Any]

LABOUR_POLICY: Persona = {
    "name": "Labour/policy-oriented student",
    "field_ratings": {"labour": 5, "public": 4, "development": 3, "macro": 2, "international": 3, "environmental": 3,
                      "behavioural": 2, "finance_io": 1},
    "likert": {"cal_enjoy_data": 5, "cal_enjoy_theory": 2, "cal_enjoy_qual": 3, "cal_policy": 5, "cal_causal": 3,
               "cal_feasibility": 3, "cal_novelty": 2, "cal_values_distribution": 5},
    "constraints": {"con_software": "basic", "con_data_access": "can_apply"},
    "field_taste": {"labour": 3.0, "public": 2.0, "international": 0.8, "development": 0.8},
    "theme_taste": {"institutions": 1.5, "inequality": 1.0, "policy": 0.5, "modelling": -1.0, "finance": -1.0},
    "signal_taste": {"approach.quant_empirical": 1, "policy_relevance": 1, "style.descriptive_comparison": 0.5,
                     "style.policy_evaluation": 0.5, "approach.theory_modelling": -1, "novelty": -0.5},
}

MACRO_THEORY: Persona = {
    "name": "Macro/theory-oriented student",
    "field_ratings": {"labour": 2, "public": 2, "development": 2, "macro": 5, "international": 4, "environmental": 2,
                      "behavioural": 3, "finance_io": 4},
    "likert": {"cal_enjoy_data": 2, "cal_enjoy_theory": 5, "cal_enjoy_qual": 1, "cal_policy": 2, "cal_causal": 3,
               "cal_feasibility": 4, "cal_novelty": 3},
    "constraints": {"con_software": "basic", "con_data_access": "public_only"},
    "field_taste": {"macro": 3.0, "finance_io": 1.5, "international": 1.5},
    "theme_taste": {"modelling": 1.5, "monetary": 1.5, "expectations": 1.0, "inequality": -0.5, "policy": -0.3},
    "signal_taste": {"approach.theory_modelling": 1, "style.modelling": 1, "approach.quant_empirical": -0.5,
                     "policy_relevance": -1, "feasibility_tolerance": 0.5},
}

UNCERTAIN: Persona = {
    "name": "Uncertain student",
    "field_ratings": {f: 3 for f in ("labour", "public", "development", "macro", "international", "environmental",
                                     "behavioural", "finance_io")},
    "likert": {"cal_enjoy_data": 3, "cal_enjoy_theory": 3, "cal_enjoy_qual": 3, "cal_policy": 3, "cal_causal": 4,
               "cal_feasibility": 3, "cal_novelty": 3},
    "constraints": {"con_software": "unsure", "con_data_access": "unsure"},
    "unsure_every": 3,      # answers only every third task; the rest are "neither / unsure"
    "contradict": True,     # and alternates between sides when it does answer
}


def calibration_for(persona: Persona) -> dict[str, Any]:
    cal: dict[str, Any] = {f"cal_field:{f}": r for f, r in persona["field_ratings"].items()}
    cal.update(persona.get("likert", {}))
    cal.update(persona.get("constraints", {}))
    return cal


def chooser(persona: Persona, pack) -> Callable[[QuestionSpec, int], str | None]:
    def choose(spec: QuestionSpec, n: int) -> str | None:
        if persona.get("unsure_every"):
            if n % persona["unsure_every"] != 0:
                return None
            return spec.display_order[(n // persona["unsure_every"]) % 2]
        scores = {}
        for o in spec.options:
            if o.kind == "territory":
                t = pack.territory(o.territory_id)
                scores[o.id] = persona["field_taste"].get(t.field, 0.0) + sum(
                    persona["theme_taste"].get(th, 0.0) for th in t.themes)
            else:
                scores[o.id] = sum(persona["signal_taste"].get(k, 0.0) * (1 if v >= 0.5 else -1)
                                   for k, v in o.signals.items())
        best = sorted(scores, key=lambda k: (-scores[k], k))
        return best[0]
    return choose


def run_persona(persona: Persona, seed: int = 11, with_syllabus: bool = True, state: SessionState | None = None
                ) -> tuple[SessionState, SurveyRun]:
    state = state or service.new_session("economics", seed=seed)
    if with_syllabus and not state.modules:
        service.load_sample_curriculum(state)
        confirm_curriculum(state)
    service.set_calibration(state, calibration_for(persona))
    choose = chooser(persona, service.pack_for(state))
    run = service.run_survey(state)
    while run.current is not None:
        q = run.current
        run = service.record_response(state, q.id, choose(q, len(run.history)))
    return state, run
