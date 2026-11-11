"""Readable Markdown summary and a structured JSON record of a session."""
from __future__ import annotations

import json
from typing import Any

from .config import SurveyConfig, load_survey_config
from .models import SessionState, SurveyRun
from .recommendations import ResultsBundle
from .scoring import band
from .service import pack_for, results, run_survey

ACCESS_LABEL = {"open": "open access", "registration": "free registration needed", "subscription": "library subscription",
                "restricted": "restricted / application", "own_collection": "you would collect it yourself"}
DIMENSION_LABELS = {"topic_interest": "Topic-interest fit", "method_fit": "Methods fit",
                    "feasibility": "Initial feasibility", "values_alignment": "Relevance/values alignment",
                    "exploration_fit": "Familiarity/novelty fit"}


def export_markdown(state: SessionState, run: SurveyRun | None = None, bundle: ResultsBundle | None = None,
                    cfg: SurveyConfig | None = None) -> str:
    cfg = cfg or load_survey_config()
    pack = pack_for(state)
    run = run or run_survey(state, cfg)
    bundle = bundle or results(state, run, cfg)
    L: list[str] = []
    L.append("# Dissertation Discovery — my research directions")
    L.append("")
    L.append(f"*{pack.label} · session {state.id} · survey design {state.design_version} · "
             f"content pack {state.pack_version}*")
    L.append("")
    L.append("> These are **research territories to investigate**, not dissertation titles or research questions. "
             "The ranking is a transparent rule-based heuristic built from my own answers; it is not a statistical "
             "prediction. Data availability, feasibility and originality all need checking with my supervisor.")
    L.append("")
    if bundle.overall_notice:
        L += [f"**Note:** {bundle.overall_notice}", ""]
    if not bundle.recommendations:
        return "\n".join(L)

    L.append("## Shortlist")
    for rec in bundle.recommendations:
        t = pack.territory(rec.territory_id)
        L += ["", f"### {rec.rank}. {t.label}", "", f"**Research territory:** {pack.label} → " + " → ".join(t.path), "",
              f"**Evidence from the survey:** {rec.evidence_label} "
              "(how much consistent evidence my answers gave; not a probability of success)", ""]
        L.append("**Why it appears**")
        for r in rec.reasons:
            L.append(f"- {r.text}")
        L += ["", "**How it scored (qualitative bands)**"]
        for key in ("topic_interest", "method_fit"):
            L.append(f"- {DIMENSION_LABELS[key]}: {band(rec.components[key])}")
        L.append(f"- {DIMENSION_LABELS['feasibility']}: {band(rec.raw_feasibility)}"
                 + (" — flagged for discussion" if rec.feasibility_flag else ""))
        L += ["", "**Promising angles (starting points, not questions)**"] + [f"- {a}" for a in t.angles]
        L += ["", "**Methods to examine**"] + [f"- {m}" for m in rec.method_notes]
        L += ["", "**Data routes to check (suggestions, not verified access)**"]
        L += [f"- {d.name} — {ACCESS_LABEL[d.access]}. {d.note}" for d in t.data_routes]
        L += ["", "**Research risks**"] + [f"- {x}" for x in rec.feasibility_notes + t.risks]
        L += ["", "**Literature search strings**"] + [f"- `{s}`" for s in t.search_strings]
        if rec.diversity_note:
            L += ["", f"*{rec.diversity_note}*"]

    top = bundle.recommendations[0]
    plan = bundle.plans[top.territory_id]
    L += ["", f"## My {plan.total_time} research exercise", "", f"For: **{pack.territory(top.territory_id).label}**", ""]
    for i, s in enumerate(plan.steps, start=1):
        L.append(f"- [ ] **{i}. {s.title}** ({s.minutes} min) — {s.detail}")
    L += ["", "**Where to search**", f"- {plan.library_note}"]
    for d in plan.databases[1:]:
        L.append(f"- {d['label']}" + (f" — {d['url']}" if d.get("url") else "") + f" — {d['note']}")
    L += ["", "## Questions for my supervisor"] + [f"- {p}" for p in plan.supervisor_prompts]

    if bundle.conflicts:
        L += ["", "## Trade-offs in my answers"] + [f"- {c}" for c in bundle.conflicts]

    L += ["", "## My preference profile", ""]
    for d in cfg.dimensions:
        for key in d.get("keys", []):
            if key in run.profile.key_scores and run.profile.weight(key) > 0:
                kind, _, level = key.partition(".")
                label = cfg.attribute_label(kind, level) if level else d["label"]
                L.append(f"- {d['label']} — {label}: {band(run.profile.key_scores[key])}")
    answered = run.profile.n_tasks - run.profile.n_unsure
    L += ["", f"Choice questions answered: {answered} with a preference, {run.profile.n_unsure} unsure."]
    open_id = cfg.calibration["open_prompt"]["id"]
    if state.calibration.get(open_id):
        L += ["", f"**Something that stuck with me:** {state.calibration[open_id]}"]

    studied = state.studied_modules
    if studied:
        L += ["", "## Confirmed modules used as context", ""]
        L += [f"- {m.display_label} ({m.status})" for m in studied]
        if state.used_sample_curriculum:
            L += ["", "*These came from the built-in sample syllabus, not from my own upload.*"]
    else:
        L += ["", "*No syllabus was used: nothing above refers to my own modules.*"]

    w = bundle.weights
    L += ["", "## How this was ranked", "",
          "Each territory gets a score that is a weighted sum of five components computed from my answers: "
          + ", ".join(f"{DIMENSION_LABELS[k].lower()} ({int(v * 100)}%)" for k, v in w.items())
          + ". These weights are provisional design choices, not calibrated estimates. Syllabus coverage never "
            "raises topic interest; it only informs familiarity, method plausibility and the explanations. The three "
            "results are chosen to be thematically distinct."]
    return "\n".join(L) + "\n"


def export_json(state: SessionState, run: SurveyRun | None = None, cfg: SurveyConfig | None = None) -> str:
    """Structured record: design version, seed, question specs with attributes, responses and selection log."""
    cfg = cfg or load_survey_config()
    run = run or run_survey(state, cfg)
    bundle = results(state, run, cfg)
    record: dict[str, Any] = {
        "session_id": state.id, "discipline": state.discipline_id, "design_version": state.design_version,
        "pack_version": state.pack_version, "random_seed": state.random_seed, "created_at": state.created_at,
        "calibration": state.calibration,
        "tasks": [{"step": h.spec.step_index, "question_id": h.spec.id, "template_id": h.spec.template_id,
                   "dimension_ids": h.spec.dimension_ids, "selection_reason": h.spec.selection_reason,
                   "display_order": h.spec.display_order,
                   "options": [{"id": o.id, "attributes": o.attributes, "signals": o.signals} for o in h.spec.options],
                   "response": h.response.model_dump()} for h in run.history],
        "superseded_responses": [r.model_dump() for r in state.response_log
                                 if r.id not in {a.id for a in state.answers.values()}],
        "selection_log": run.selection_log, "stop_reason": run.stop_reason,
        "recommendations": [{"rank": r.rank, "territory_id": r.territory_id, "evidence_label": r.evidence_label,
                             "components": {k: round(v, 3) for k, v in r.components.items()}}
                            for r in bundle.recommendations],
        "confirmed_modules": [{"code": m.code, "title": m.title, "status": m.status} for m in state.studied_modules],
    }
    return json.dumps(record, indent=2)
