"""Displayed wording for an approved QuestionSpec.

Deterministic templates are the default and always available. An LLM may only
re-word the two option blurbs; titles, prompts, attributes, IDs and scoring are
fixed. LLM text is validated and silently replaced by the template if invalid.
"""
from __future__ import annotations

import re
from typing import Any

from ..config import SurveyConfig, env_flag
from ..curriculum.extract import looks_like_instruction
from ..curriculum.review import CurriculumContext
from ..llm import LLMAdapter
from ..models import DisciplinePack, QuestionCopy, QuestionSpec

COPY_SYSTEM = """You re-word short descriptions of research directions for undergraduate students.

You are given approved options with fixed IDs, titles and attributes. For each option write ONE plain, concrete \
sentence (at most 35 words) describing it. Rules:
- Keep the meaning of the approved description. Do not add topics, methods, data sources, statistics, claims about \
the student, or anything that makes one option sound better than the other.
- Do not phrase it as a research question or a dissertation title.
- Do not mention attributes that are not listed for that option."""

MAX_BLURB = 260
_BANNED = re.compile(r"\d|%|\?|perfect|guarantee|passion|best choice|you should", re.I)


def _copy_schema(option_ids: list[str]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": ["blurbs"],
            "properties": {"blurbs": {"type": "object", "additionalProperties": False, "required": option_ids,
                                      "properties": {oid: {"type": "string"} for oid in option_ids}}}}


def deterministic_copy(spec: QuestionSpec, cfg: SurveyConfig, pack: DisciplinePack, ctx: CurriculumContext) -> QuestionCopy:
    titles, blurbs, notes = {}, {}, {}
    grounding_by_option = {g.option_id: g for g in spec.grounding if g.option_id}
    for o in spec.options:
        titles[o.id], blurbs[o.id] = o.label, o.blurb
        n: list[str] = []
        if o.kind == "territory":
            t = pack.territory(o.territory_id)
            n.append("Usual approach: " + cfg.attribute_label("approach", t.approach).lower())
            n.append(cfg.attribute_label("data_access", t.data_access))
            g = grounding_by_option.get(o.id)
            if g is not None:      # only present when a confirmed studied module supports it
                n.append(f"Links to “{g.item_text}” in your module {g.module_label}")
            elif ctx.has_syllabus:
                fam = o.attributes.get("familiarity")
                n.append("Next to material in your confirmed modules" if fam == "adjacent"
                         else "Outside your confirmed modules")
        notes[o.id] = n
    preface = None
    general = [g for g in spec.grounding if not g.option_id]
    if general:
        g = general[0]
        method_label = g.item_text
        method_label = method_label[:1].lower() + method_label[1:]
        preface = (f"Your confirmed module {g.module_label} mentions {method_label}. That tells us it was "
                   "taught, not whether you enjoyed it, so:")
    return QuestionCopy(question_id=spec.id, prompt=spec.prompt, preface=preface, option_titles=titles,
                        option_blurbs=blurbs, option_notes=notes, source="deterministic")


def render_question_copy(spec: QuestionSpec, cfg: SurveyConfig, pack: DisciplinePack, ctx: CurriculumContext,
                         llm: LLMAdapter | None = None, cache: dict[str, dict[str, str]] | None = None) -> QuestionCopy:
    copy = deterministic_copy(spec, cfg, pack, ctx)
    if llm is None or not llm.enabled or not env_flag("DD_LLM_COPY"):
        return copy
    key = f"{spec.design_version}:{spec.id}"
    blurbs = cache.get(key) if cache is not None else None
    if blurbs is None:
        blurbs = _llm_blurbs(spec, cfg, llm)
        if cache is not None and blurbs is not None:
            cache[key] = blurbs
    if blurbs is None:
        return copy
    return copy.model_copy(update={"option_blurbs": blurbs, "source": "llm"})


def _llm_blurbs(spec: QuestionSpec, cfg: SurveyConfig, llm: LLMAdapter) -> dict[str, str] | None:
    ids = [o.id for o in spec.options]
    lines = []
    for o in spec.options:
        attrs = "; ".join(f"{k}={cfg.attribute_label(k, v)}" for k, v in o.attributes.items() if k != "familiarity")
        lines.append(f"- id: {o.id}\n  title: {o.label}\n  approved description: {o.blurb}\n  attributes: {attrs}")
    raw = llm.complete_json(system=COPY_SYSTEM, user="Options:\n" + "\n".join(lines), schema=_copy_schema(ids),
                            max_tokens=1000, effort="low")
    return validate_blurbs(raw, ids)


def validate_blurbs(raw: Any, option_ids: list[str]) -> dict[str, str] | None:
    """Accept LLM wording only if it has exactly the approved option IDs and passes basic content checks."""
    if not isinstance(raw, dict) or not isinstance(raw.get("blurbs"), dict):
        return None
    blurbs = raw["blurbs"]
    if set(blurbs) != set(option_ids):
        return None
    out = {}
    for oid in option_ids:
        text = blurbs[oid]
        if not isinstance(text, str):
            return None
        text = " ".join(text.split())
        if not (25 <= len(text) <= MAX_BLURB) or _BANNED.search(text) or looks_like_instruction(text):
            return None
        out[oid] = text
    return out
