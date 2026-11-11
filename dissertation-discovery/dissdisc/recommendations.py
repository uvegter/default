"""Final shortlist: three distinct territories with traceable reasons and a research handoff.

Every reason is generated from a recorded response or a confirmed, source-backed
curriculum item, and carries references to them. Nothing is asserted about the
syllabus unless a studied module contains an included item that supports it.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from pydantic import BaseModel

from .config import SurveyConfig, load_institutions
from .curriculum.review import CurriculumContext
from .models import DisciplinePack, HistoryEntry, PreferenceProfile, Reason, Recommendation, SurveyRun, Territory
from .scoring import evidence_for, select_diverse


class ResearchStep(BaseModel):
    title: str
    minutes: str
    detail: str


class ResearchPlan(BaseModel):
    territory_id: str
    total_time: str
    steps: list[ResearchStep]
    search_strings: list[str]
    scholar_links: dict[str, str]
    library_note: str
    databases: list[dict[str, Any]]
    supervisor_prompts: list[str]


class ResultsBundle(BaseModel):
    recommendations: list[Recommendation]
    plans: dict[str, ResearchPlan]
    overall_notice: str | None = None
    conflicts: list[str] = []
    weights: dict[str, float] = {}
    stop_reason: str | None = None
    n_tasks: int = 0
    n_unsure: int = 0


def _fmt_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_reasons(cfg: SurveyConfig, pack: DisciplinePack, t: Territory, rec: Recommendation, profile: PreferenceProfile,
                  history: list[HistoryEntry], calibration: dict[str, Any], ctx: CurriculumContext,
                  detail: dict[str, Any]) -> tuple[list[Reason], list[str]]:
    reasons: list[Reason] = []
    method_notes: list[str] = []
    field = pack.field(t.field)
    prefix = cfg.calibration["field_interest"]["id_prefix"]

    # ---- survey evidence -----------------------------------------------------
    won_over, lost_to, refs_for, refs_against = [], [], [], []
    for h in history:
        if h.spec.template_id != "territory_pair" or h.response.selected_option_id is None:
            continue
        ids = [o.territory_id for o in h.spec.options]
        if t.id not in ids:
            continue
        other = pack.territory(next(i for i in ids if i != t.id))
        if h.response.selected_option_id == t.id:
            won_over.append(other.label)
            refs_for.append(h.spec.id)
        else:
            lost_to.append(other.label)
            refs_against.append(h.spec.id)
    if won_over:
        reasons.append(Reason(kind="survey", refs=refs_for,
                              text=f"Your survey choices: you picked this territory over {_fmt_list(won_over)}."))
    rating = calibration.get(f"{prefix}:{t.field}")
    field_bits = []
    if rating is not None and int(rating) >= 4:
        field_bits.append(f"you rated {field.label} {int(rating)} out of 5 for interest")
    if detail["field_for"]:
        total = detail["field_for"] + detail["field_against"]
        field_bits.append(f"in {detail['field_for']} of {total} other comparison{'s' if total != 1 else ''} "
                          f"involving {field.label} you chose the {field.label} direction")
    if field_bits:
        reasons.append(Reason(kind="survey", refs=[f"{prefix}:{t.field}"],
                              text="Your survey responses: " + _fmt_list(field_bits) + "."))
    approach_label = cfg.attribute_label("approach", t.approach).lower()
    style_label = cfg.attribute_label("style", t.style).lower()
    if profile.score(f"approach.{t.approach}") >= 0.6 and profile.weight(f"approach.{t.approach}") > 0:
        reasons.append(Reason(kind="survey", refs=[f"approach.{t.approach}"],
                              text=f"Your survey answers lean towards {approach_label}, which is the usual way of working here."))
    elif profile.score(f"style.{t.style}") >= 0.6 and profile.weight(f"style.{t.style}") > 0:
        reasons.append(Reason(kind="survey", refs=[f"style.{t.style}"],
                              text=f"Your survey answers favour {style_label}, the dominant style of research in this territory."))
    if t.policy_relevance == "high" and profile.score("policy_relevance") >= 0.6:
        reasons.append(Reason(kind="survey", refs=["policy_relevance"],
                              text="Your survey answers: real-world policy relevance matters to you, and this "
                                   "territory has direct policy links."))
    if (t.distributional_focus == "high" and profile.key_scores.get("distributional_values", 0) >= 0.6):
        reasons.append(Reason(kind="survey", refs=["cal_values_distribution"],
                              text="Your survey answers: you said differences in outcomes between groups matter in "
                                   "the research you want to do; that is central here."))
    if not any(r.kind == "survey" for r in reasons):
        reasons.append(Reason(kind="caution", text="Little in your responses bears directly on this territory. It is "
                              "listed because it scored reasonably across the dimensions, not because of a clear signal."))

    # ---- syllabus evidence (only when confirmed and source-backed) ----------
    links = ctx.territory_links.get(t.id, [])
    if links:
        by_module: dict[str, list] = {}
        for g in links:
            by_module.setdefault(g.module_label, []).append(g)
        for module_label, gs in list(by_module.items())[:2]:
            quoted = _fmt_list([f"“{g.item_text}”" for g in gs[:3]])
            reasons.append(Reason(kind="syllabus", refs=[g.item_id for g in gs[:3]],
                                  text=f"Your syllabus: your confirmed module {module_label} covers {quoted}. "
                                       "This is familiarity, not evidence that you like the topic."))
    elif ctx.has_syllabus:
        fam = ctx.familiarity_of(t.id)
        if fam == "adjacent":
            reasons.append(Reason(kind="caution", text="This sits next to material in your confirmed modules rather "
                                  "than inside it, so expect more background reading."))
        elif fam == "novel":
            reasons.append(Reason(kind="caution", text="Nothing in your confirmed modules maps to this territory. It is "
                                  "here because of your choices, and would need more background reading."))
    for mid in t.methods:
        label = pack.method(mid).label
        ml = ctx.method_links.get(mid)
        if ml:
            excerpt = ml[0].excerpt.lstrip("-•*·–0123456789.) ").strip()[:90]
            method_notes.append(f"{label}: appears in your confirmed module {ml[0].module_label} "
                                f"(“{excerpt}”). Being taught a method is not the same as being comfortable "
                                "applying it.")
        elif ctx.has_syllabus:
            method_notes.append(f"{label}: not found in your confirmed modules. Ask whether it is realistic to learn.")
        else:
            method_notes.append(f"{label}: check whether you have been taught this.")

    # ---- cautions --------------------------------------------------------------
    if lost_to:
        reasons.append(Reason(kind="caution", refs=refs_against,
                              text=f"Against this: you preferred {_fmt_list(lost_to)} when it was offered alongside."))
    return reasons, method_notes


def build_plan(cfg: SurveyConfig, pack: DisciplinePack, t: Territory, rec: Recommendation, profile: PreferenceProfile,
               institution_id: str, calibration: dict[str, Any]) -> ResearchPlan:
    inst_cfg = load_institutions()
    inst = inst_cfg["institutions"].get(institution_id) or inst_cfg["institutions"]["generic"]
    url = inst_cfg["scholar_search_url"]
    steps = [
        ResearchStep(title="Find two academic papers", minutes="20–25",
                     detail="Use the search strings below. Aim for one recent overview or review article and one "
                            "influential or recent empirical/theoretical paper. For each, write one line: what question "
                            "does it actually ask?"),
        ResearchStep(title="Identify one unresolved disagreement or gap", minutes="10–15",
                     detail="From the introductions and conclusions, note one thing the authors disagree about, could "
                            "not test, or flag for future work. Do not assume a gap exists just because you have not "
                            "found a paper on it."),
        ResearchStep(title="Check two possible data sources", minutes="15–20",
                     detail="For each candidate source, verify: can you actually access it, what is the unit of "
                            "observation, which years and places does it cover, and does it contain the key variables? "
                            "The sources listed for this territory are suggestions to check, not guarantees."),
        ResearchStep(title="Choose one provisional setting", minutes="5–10",
                     detail="Pick a country, institution, industry, period or population that would make the scope "
                            "concrete. You can change it later."),
        ResearchStep(title="Draft one provisional research question in your own words", minutes="10–20",
                     detail="Only after the steps above. One sentence, written by you, that you would be willing to "
                            "show your supervisor as a starting point rather than a final title."),
    ]
    prompts = [
        "Is this territory appropriately narrow for a dissertation at my level, and which part needs narrowing most?",
        "Are the data sources and the method I have in mind realistic in the time available?",
        "What should I read first?",
    ]
    prompts.extend(t.supervisor_questions)
    if rec.feasibility_flag:
        prompts.append("The tool flagged low initial feasibility for this direction. Is there a more tractable version?")
    for c in profile.conflicts[:2]:
        prompts.append("A tension in my survey answers to discuss: " + c.description)
    if calibration.get("cal_career") is not None and int(calibration["cal_career"]) >= 4:
        prompts.append("I would like the dissertation to connect to work I hope to do later. Does this direction help?")
    return ResearchPlan(
        territory_id=t.id, total_time="60–90 minutes", steps=steps, search_strings=list(t.search_strings),
        scholar_links={s: url.format(query=quote_plus(s)) for s in t.search_strings},
        library_note=f"{inst['library']['label']}: {inst['library']['note']}",
        databases=[inst["library"], *inst["databases"]], supervisor_prompts=prompts)


def build_results(cfg: SurveyConfig, pack: DisciplinePack, run: SurveyRun, ctx: CurriculumContext,
                  calibration: dict[str, Any], institution_id: str = "generic") -> ResultsBundle:
    if not pack.supported:
        return ResultsBundle(recommendations=[], plans={}, overall_notice=(
            f"No topic content pack is configured for {pack.label} yet, so no research territories can be "
            "recommended. The survey engine supports other disciplines once a content pack is added."))
    top = select_diverse(cfg, pack, run.ranking)
    plans: dict[str, ResearchPlan] = {}
    for rec in top:
        t = pack.territory(rec.territory_id)
        label, points, detail = evidence_for(cfg, pack, t.id, run.profile, run.history, calibration)
        rec.evidence_label, rec.evidence_points = label, points
        rec.reasons, rec.method_notes = build_reasons(cfg, pack, t, rec, run.profile, run.history, calibration, ctx, detail)
        plans[t.id] = build_plan(cfg, pack, t, rec, run.profile, institution_id, calibration)
    notice = None
    limited = sum(1 for r in top if r.evidence_label in ("Limited evidence", "Insufficient information"))
    answered = run.profile.n_tasks - run.profile.n_unsure
    if run.profile.n_tasks == 0:
        notice = ("You have not answered any choice questions yet, so this shortlist rests only on your initial "
                  "ratings. Treat it as a very rough starting point.")
    elif run.profile.unsure_share >= cfg.evidence["unsure_share_threshold"] or limited >= 2:
        notice = (f"Limited evidence: you gave a clear preference in {answered} of {run.profile.n_tasks} choice "
                  "questions, so this shortlist is tentative. That is a legitimate result: it suggests exploring "
                  "several directions a little before narrowing down.")
    return ResultsBundle(recommendations=top, plans=plans, overall_notice=notice,
                         conflicts=[c.description for c in run.profile.conflicts], weights=dict(cfg.scoring["weights"]),
                         stop_reason=run.stop_reason, n_tasks=run.profile.n_tasks, n_unsure=run.profile.n_unsure)
