"""Framework-independent application service: the functions the UI (or tests, or a
future API) call. Mirrors the service contracts in PRODUCT_SPEC.md §10.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from .config import ROOT, SurveyConfig, load_pack, load_survey_config
from .curriculum import review
from .curriculum.ingest import DecodedText, decode_text, decode_upload
from .curriculum.llm_extract import extract
from .curriculum.review import CurriculumContext, build_context
from .llm import LLMAdapter, NullLLM
from .models import CurriculumExtraction, DisciplinePack, QuestionCopy, Response, SessionState, SurveyRun
from .recommendations import ResultsBundle, build_results
from .survey.copy import render_question_copy
from .survey.engine import replay

SAMPLE_SYLLABUS = ROOT / "sample_data" / "economics_programme_handbook.txt"
# Modules the built-in demo student is treated as having taken (the student can change these on review).
SAMPLE_STUDIED = {"ECON2020": "completed", "ECON2030": "completed", "ECON2040": "completed", "ECON2110": "completed",
                  "ECON2120": "completed", "ECON2160": "current"}


def new_session(discipline_id: str = "economics", seed: int | None = None, cfg: SurveyConfig | None = None
                ) -> SessionState:
    cfg = cfg or load_survey_config()
    pack = load_pack(discipline_id)
    return SessionState(discipline_id=discipline_id, design_version=cfg.design_version, pack_version=pack.pack_version,
                        random_seed=seed if seed is not None else secrets.randbelow(2**31))


def pack_for(state: SessionState) -> DisciplinePack:
    return load_pack(state.discipline_id)


# -------------------------------------------------------------- curriculum ---
def ingest_file(state: SessionState, filename: str, data: bytes, llm: LLMAdapter | None = None,
                cfg: SurveyConfig | None = None) -> CurriculumExtraction:
    cfg = cfg or load_survey_config()
    return _ingest(state, decode_upload(filename, data, cfg), llm, cfg)


def ingest_text(state: SessionState, text: str, name: str = "pasted text", llm: LLMAdapter | None = None,
                cfg: SurveyConfig | None = None) -> CurriculumExtraction:
    cfg = cfg or load_survey_config()
    return _ingest(state, decode_text(text, name), llm, cfg)


def _ingest(state: SessionState, decoded: DecodedText, llm: LLMAdapter | None, cfg: SurveyConfig) -> CurriculumExtraction:
    extraction = extract(decoded, pack_for(state), llm or NullLLM(), cfg)
    if decoded.ok:
        review.merge_extraction(state, extraction)
    else:
        state.documents.append(extraction.document)   # metadata only, so the failure is visible on reset/export
    # `decoded` (the raw text) goes out of scope here: it is never stored on the session.
    return extraction


def load_sample_curriculum(state: SessionState, cfg: SurveyConfig | None = None) -> CurriculumExtraction:
    extraction = ingest_text(state, Path(SAMPLE_SYLLABUS).read_text(encoding="utf-8"), "sample_programme_handbook.txt",
                             cfg=cfg)
    for mod in state.modules:
        if mod.code in SAMPLE_STUDIED:
            mod.status = SAMPLE_STUDIED[mod.code]  # type: ignore[assignment]
    state.used_sample_curriculum = True
    return extraction


# ------------------------------------------------------------------ survey ---
def context_for(state: SessionState) -> CurriculumContext:
    return build_context(state, pack_for(state))


def run_survey(state: SessionState, cfg: SurveyConfig | None = None) -> SurveyRun:
    """Derive the full survey state from stored answers (pure; safe to call on every render)."""
    cfg = cfg or load_survey_config()
    return replay(cfg, pack_for(state), context_for(state), state.calibration, state.answers, state.random_seed,
                  state.studied_modules)


def record_response(state: SessionState, question_id: str, selected_option_id: str | None,
                    strength: str | None = None, reason_code: str | None = None, cfg: SurveyConfig | None = None
                    ) -> SurveyRun:
    """Record (or revise) an answer, then re-derive everything. Invalid input is rejected, never stored."""
    cfg = cfg or load_survey_config()
    run = run_survey(state, cfg)
    spec = run.current if run.current and run.current.id == question_id else next(
        (h.spec for h in run.history if h.spec.id == question_id), None)
    if spec is None:
        raise ValueError(f"Question {question_id!r} is not part of this session's survey")
    if selected_option_id is not None and selected_option_id not in [o.id for o in spec.options]:
        raise ValueError(f"{selected_option_id!r} is not an option of {question_id!r}")
    if selected_option_id is None and not cfg.choice_tasks.get("allow_unsure", True):
        raise ValueError("'Neither / unsure' is disabled in this design")
    if strength is not None and strength not in cfg.choice_tasks["strength_options"]:
        raise ValueError(f"Unknown strength {strength!r}")
    if reason_code is not None and reason_code not in cfg.choice_tasks["reason_options"]:
        raise ValueError(f"Unknown reason code {reason_code!r}")
    response = Response(question_id=question_id, selected_option_id=selected_option_id,
                        strength=strength if selected_option_id else None,
                        reason_code=reason_code if selected_option_id else None,
                        uncertainty_flag=selected_option_id is None)
    state.answers[question_id] = response
    state.response_log.append(response)
    return run_survey(state, cfg)


def set_calibration(state: SessionState, values: dict[str, Any], cfg: SurveyConfig | None = None) -> None:
    """Store calibration answers after validating them against the fixed scales."""
    cfg = cfg or load_survey_config()
    pack = pack_for(state)
    prefix = cfg.calibration["field_interest"]["id_prefix"]
    likert_ids = {i["id"] for i in cfg.all_likert_items()} | {f"{prefix}:{f.id}" for f in pack.fields}
    constraint_opts = {c["id"]: set(c["options"]) for c in cfg.calibration["constraints"]}
    clean: dict[str, Any] = {}
    for key, val in values.items():
        if val is None or val == "":
            continue
        if key in likert_ids:
            if int(val) not in range(1, 6):
                raise ValueError(f"{key}: rating must be 1–5")
            clean[key] = int(val)
        elif key in constraint_opts:
            if val not in constraint_opts[key]:
                raise ValueError(f"{key}: unknown option {val!r}")
            clean[key] = val
        elif key == cfg.calibration["open_prompt"]["id"]:
            clean[key] = str(val)[:1000]
        else:
            raise ValueError(f"Unknown calibration item {key!r}")
    state.calibration = clean
    state.calibration_done = True


def question_copy(state: SessionState, spec, llm: LLMAdapter | None = None, cache: dict | None = None,
                  cfg: SurveyConfig | None = None) -> QuestionCopy:
    cfg = cfg or load_survey_config()
    return render_question_copy(spec, cfg, pack_for(state), context_for(state), llm, cache)


def results(state: SessionState, run: SurveyRun | None = None, cfg: SurveyConfig | None = None) -> ResultsBundle:
    cfg = cfg or load_survey_config()
    run = run or run_survey(state, cfg)
    return build_results(cfg, pack_for(state), run, context_for(state), state.calibration, state.institution_id)


def reset_survey(state: SessionState) -> None:
    state.answers, state.response_log = {}, []
    state.calibration, state.calibration_done = {}, False
