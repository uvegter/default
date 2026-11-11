"""Fixed design, adaptive rules, reproducibility, backtracking and response validation."""
import json

import pytest

from dissdisc import service
from dissdisc.models import Response
from dissdisc.simulate import LABOUR_POLICY, MACRO_THEORY, calibration_for, chooser, run_persona
from dissdisc.storage import Store
from dissdisc.survey.engine import territory_pair_id

ALLOWED_REASONS = {"field_coverage", "dimension_coverage", "challenge_leader", "top_two_tie", "exploration",
                   "within_field_refine", "low_dimension_coverage", "dimension_followup", "resolve_leading_group"}


def _answers_signature(run):
    return [(h.spec.id, h.spec.selection_reason, tuple(h.spec.display_order), h.response.selected_option_id)
            for h in run.history]


def test_question_specs_are_fixed_and_fully_attributed(cfg, pack):
    state, run = run_persona(LABOUR_POLICY, seed=5)
    ids = [h.spec.id for h in run.history]
    assert len(ids) == len(set(ids))                                       # no task asked twice
    territory_ids = {t.id for t in pack.territories}
    bank = set(cfg.profile_pairs) | set(cfg.clarifications)
    for h in run.history:
        s = h.spec
        assert s.design_version == cfg.design_version == state.design_version
        assert set(s.dimension_ids) <= set(cfg.dimension_ids)
        assert len(s.options) == 2 and sorted(s.display_order) == sorted(o.id for o in s.options)
        reason = s.selection_reason
        assert reason in ALLOWED_REASONS or reason.startswith("clarify:")
        if s.template_id == "territory_pair":
            assert {o.territory_id for o in s.options} <= territory_ids
            assert s.id == territory_pair_id(*[o.id for o in s.options])
            for o in s.options:                                            # card attributes come from the pack
                assert {"approach", "style", "policy_relevance", "data_access", "technical_demand",
                        "distributional_focus", "familiarity"} <= set(o.attributes)
                assert o.signals == {}
        else:
            assert s.id in bank
            for o in s.options:                                            # profile signals come from the config
                side = o.id.rsplit(".", 1)[1]
                src = (cfg.profile_pairs.get(s.id) or cfg.clarifications[s.id])[side]
                assert o.signals == {k: float(v) for k, v in src["signals"].items()}
    assert territory_pair_id("b", "a") == territory_pair_id("a", "b") == "tp__a__b"


def test_opening_tasks_cover_every_field_and_core_dimensions(cfg, pack):
    _, run = run_persona(MACRO_THEORY, seed=9, with_syllabus=False)
    opening = run.history[: len(cfg.adaptive["coverage_sequence"])]
    fields = {pack.territory(o.territory_id).field for h in opening for o in h.spec.options if o.territory_id}
    assert fields == {f.id for f in pack.fields}
    assert [h.spec.id for h in opening if h.spec.template_id == "profile_pair"] == cfg.adaptive["coverage_profile_pairs"]
    assert cfg.adaptive["min_tasks"] <= len(run.history) <= cfg.adaptive["max_tasks"]
    assert run.stop_reason in ("stable_ranking", "max_tasks_reached", "no_informative_questions_left")


def test_seeded_session_is_reproducible_and_logged(cfg):
    s1, r1 = run_persona(LABOUR_POLICY, seed=42)
    s2, r2 = run_persona(LABOUR_POLICY, seed=42)
    assert _answers_signature(r1) == _answers_signature(r2)
    assert r1.selection_log == r2.selection_log and len(r1.selection_log) == len(r1.history)
    assert all({"step", "question_id", "reason", "display_order"} <= set(e) for e in r1.selection_log)
    assert [r.territory_id for r in r1.ranking] == [r.territory_id for r in r2.ranking]
    # Re-deriving from the stored answers alone gives the same survey.
    assert _answers_signature(service.run_survey(s1)) == _answers_signature(r1)
    # A different seed changes the randomised parts (which territory represents a field / left-right order).
    _, r3 = run_persona(LABOUR_POLICY, seed=43)
    assert [(h.spec.id, h.spec.display_order) for h in r3.history] != [(h.spec.id, h.spec.display_order) for h in r1.history]


def test_revising_an_answer_leaves_no_stale_derived_state(pack):
    state, run = run_persona(LABOUR_POLICY, seed=7)
    target = run.history[2]                                   # a territory task early in the survey
    assert target.spec.template_id == "territory_pair"
    other = target.spec.other(target.response.selected_option_id).id
    n_log = len(state.response_log)
    revised = service.record_response(state, target.spec.id, other, strength="strong")
    # 1. The revision is what counts now, and the old response is kept only as superseded.
    assert state.answers[target.spec.id].selected_option_id == other
    assert len(state.response_log) == n_log + 1
    hist = {h.spec.id: h for h in revised.history}
    assert hist[target.spec.id].response.selected_option_id == other
    # 2. Everything derived equals a fresh replay of exactly the answers now in force.
    fresh = service.new_session(seed=7)
    service.load_sample_curriculum(fresh)
    from dissdisc.curriculum.review import confirm_curriculum
    confirm_curriculum(fresh)
    service.set_calibration(fresh, calibration_for(LABOUR_POLICY))
    fresh.answers = {qid: r.model_copy() for qid, r in state.answers.items()}
    again = service.run_survey(fresh)
    assert _answers_signature(again) == _answers_signature(revised)
    assert again.profile.territory_scores == revised.profile.territory_scores
    assert again.profile.key_scores == revised.profile.key_scores
    assert [r.territory_id for r in again.ranking] == [r.territory_id for r in revised.ranking]
    # 3. The change actually moved the profile.
    assert revised.profile.territory_scores[other] > run.profile.territory_scores[other]
    # 4. Answers to questions that are no longer on the path are not used.
    on_path = {h.spec.id for h in revised.history}
    for o in revised.profile.observations:
        if o.kind in ("choice", "choice_attribute"):
            assert o.source in on_path


def test_invalid_responses_are_rejected_not_stored(state):
    run = service.run_survey(state)
    q = run.current
    for kwargs in ({"selected_option_id": "not_an_option"}, {"selected_option_id": q.options[0].id, "strength": "massive"},
                   {"selected_option_id": q.options[0].id, "reason_code": "vibes"}):
        with pytest.raises(ValueError):
            service.record_response(state, q.id, **kwargs)
    with pytest.raises(ValueError):
        service.record_response(state, "tp__made__up", None)
    assert state.answers == {} and state.response_log == []
    with pytest.raises(ValueError):
        service.set_calibration(state, {"cal_enjoy_data": 9})
    with pytest.raises(ValueError):
        service.set_calibration(state, {"cal_charisma": 5})
    with pytest.raises(ValueError):
        service.set_calibration(state, {"con_software": "wizard"})


def test_unsure_is_recorded_without_moving_scores(state):
    service.set_calibration(state, {})
    before = service.run_survey(state)
    q = before.current
    after = service.record_response(state, q.id, None)
    assert after.profile.n_unsure == 1 and state.answers[q.id].uncertainty_flag
    assert after.profile.territory_scores == before.profile.territory_scores
    assert after.current.id != q.id


def test_conflicting_signals_trigger_a_clarification(cfg, state):
    cal = {"cal_causal": 5, "cal_enjoy_data": 1, "cal_enjoy_theory": 3}
    service.set_calibration(state, cal)
    run = service.run_survey(state)
    assert any(c.id == "cl_causal_vs_data" for c in run.profile.conflicts)
    asked = []
    while run.current is not None:
        q = run.current
        asked.append((q.template_id, q.id, q.selection_reason, q.explanation))
        # Keep the tension alive: prefer causal work, avoid data work.
        pick = next((o.id for o in q.options if o.signals.get("style.causal_identification") == 1
                     or o.signals.get("approach.quant_empirical") == 0), q.display_order[0])
        run = service.record_response(state, q.id, pick)
        if any(a[1] == "cl_causal_vs_data" for a in asked):
            break
    clar = next(a for a in asked if a[1] == "cl_causal_vs_data")
    assert clar[0] == "clarification" and clar[2] == "clarify:cl_causal_vs_data" and clar[3]
    assert len(asked) > len(cfg.adaptive["coverage_sequence"])          # only after broad coverage


def test_exploration_goes_beyond_the_confirmed_syllabus(cfg):
    _, run = run_persona(LABOUR_POLICY, seed=21)
    t_tasks = [h for h in run.history if h.spec.template_id == "territory_pair"]
    outside = [h for h in t_tasks if any(o.attributes["familiarity"] in ("adjacent", "novel") for o in h.spec.options)]
    inside = [h for h in t_tasks if any(o.attributes["familiarity"] == "familiar" for o in h.spec.options)]
    assert len(outside) / len(t_tasks) >= cfg.adaptive["exploration_ratio"] - 0.05
    assert inside                                                       # ...but the syllabus is still used
    # Without a syllabus an unseen territory is still introduced during the adaptive phase or all are 'unknown'.
    _, run2 = run_persona(LABOUR_POLICY, seed=21, with_syllabus=False)
    assert all(o.attributes["familiarity"] == "unknown" for h in run2.history for o in h.spec.options if o.territory_id)


def test_survey_stops_early_when_ranking_is_stable(cfg, pack, state):
    """A decisive student whose favourite keeps winning should not be asked the maximum number of tasks."""
    cal = {f"cal_field:{f.id}": 1 for f in pack.fields}
    cal.update({"cal_field:environmental": 5, "cal_enjoy_data": 5, "cal_policy": 5, "cal_enjoy_theory": 1})
    service.set_calibration(state, cal)
    run = service.run_survey(state)
    n = 0
    while run.current is not None:
        q = run.current
        if q.template_id == "territory_pair":
            pick = min(q.options, key=lambda o: (pack.territory(o.id).field != "environmental", o.id)).id
        else:
            pick = q.options[0].id
        run = service.record_response(state, q.id, pick, strength="strong")
        n += 1
    assert cfg.adaptive["min_tasks"] <= n <= cfg.adaptive["max_tasks"]
    assert run.stop_reason in ("stable_ranking", "max_tasks_reached")
    assert pack.territory(run.ranking[0].territory_id).field == "environmental"


def test_storage_roundtrip_delete_and_no_raw_document_text(tmp_path, sample_text):
    state, run = run_persona(LABOUR_POLICY, seed=3)
    target = run.history[0]
    service.record_response(state, target.spec.id, target.spec.other(target.response.selected_option_id).id)
    run = service.run_survey(state)
    store = Store(tmp_path / "s.sqlite3")
    store.save(state, run)
    loaded = store.load(state.id)
    assert loaded.model_dump() == state.model_dump()
    assert _answers_signature(service.run_survey(loaded)) == _answers_signature(run)
    assert store.count("questions", state.id) == len(run.history) + (1 if run.current else 0)
    assert store.count("responses", state.id) == len(state.response_log)        # includes the superseded one
    raw = (tmp_path / "s.sqlite3").read_bytes()
    assert b"You will not take all of them" not in raw         # handbook prose that is not a curriculum item
    assert b"a.example@" not in raw                            # staff contact details are never kept
    store.delete(state.id)
    assert store.load(state.id) is None and store.count("responses", state.id) == 0
    assert json.loads(state.model_dump_json())["random_seed"] == 3
