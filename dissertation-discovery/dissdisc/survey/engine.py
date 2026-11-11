"""Adaptive question selection inside the fixed design.

"Adaptive" means: choose the next item from the pre-approved bank using the
explicit rules below. No model is involved. Given the same configuration,
content pack, confirmed curriculum, seed and answers, `replay` always produces
the same questions in the same order, with the reason for each logged.

The survey state is never stored as truth: it is re-derived by replaying the
answers. That is what makes backtracking safe (no stale derived scores).
"""
from __future__ import annotations

import math
import random
from typing import Any

from ..config import SurveyConfig
from ..curriculum.review import CurriculumContext
from ..models import (DisciplinePack, Grounding, HistoryEntry, Module, OptionSpec, PreferenceProfile, QuestionSpec,
                      Recommendation, Response, SurveyRun, Territory)
from ..scoring import rank_territories, select_diverse
from .profile import build_profile


def territory_pair_id(a: str, b: str) -> str:
    x, y = sorted((a, b))
    return f"tp__{x}__{y}"


class Engine:
    def __init__(self, cfg: SurveyConfig, pack: DisciplinePack, ctx: CurriculumContext, seed: int):
        self.cfg, self.pack, self.ctx, self.seed = cfg, pack, ctx, seed
        self.ad = cfg.adaptive

    def rng(self, *parts: Any) -> random.Random:
        return random.Random("|".join(str(p) for p in (self.seed, self.cfg.design_version, *parts)))

    # ---------------------------------------------------------- builders ----
    def _territory_option(self, t: Territory) -> OptionSpec:
        attrs = t.card_attributes()
        attrs["familiarity"] = self.ctx.familiarity_of(t.id)
        return OptionSpec(id=t.id, kind="territory", territory_id=t.id, label=t.label, blurb=t.blurb, attributes=attrs)

    def territory_pair(self, a: Territory, b: Territory, reason: str, step: int, **detail: Any) -> QuestionSpec:
        qid = territory_pair_id(a.id, b.id)
        opts = sorted([self._territory_option(a), self._territory_option(b)], key=lambda o: o.id)
        order = [o.id for o in opts]
        self.rng("order", qid).shuffle(order)          # seeded left/right counterbalancing
        grounding = []
        for o in opts:
            links = self.ctx.territory_links.get(o.id, [])
            if links:
                grounding.append(links[0].model_copy(update={"option_id": o.id}))
        tp = self.cfg.choice_tasks["territory_pair"]
        return QuestionSpec(id=qid, template_id="territory_pair", design_version=self.cfg.design_version,
                            dimension_ids=list(tp["dimensions"]), prompt=tp["prompt"], options=opts, display_order=order,
                            selection_reason=reason, selection_detail=detail, grounding=grounding, step_index=step)

    def profile_question(self, pair: dict[str, Any], template: str, reason: str, step: int, **detail: Any) -> QuestionSpec:
        opts = [OptionSpec(id=f"{pair['id']}.{side}", kind="profile", label=pair[side]["label"], blurb=pair[side]["blurb"],
                           attributes={k: str(v) for k, v in pair[side].get("attributes", {}).items()},
                           signals={k: float(v) for k, v in pair[side].get("signals", {}).items()})
                for side in ("a", "b")]
        order = [o.id for o in opts]
        self.rng("order", pair["id"]).shuffle(order)
        grounding: list[Grounding] = []
        for mid in pair.get("grounding_methods", []):   # cite a taught method only if it was reviewed and accepted
            links = self.ctx.method_links.get(mid)
            if links:
                grounding.append(links[0])
                break
        return QuestionSpec(id=pair["id"], template_id=template, design_version=self.cfg.design_version,  # type: ignore[arg-type]
                            dimension_ids=[pair["dimension"]], prompt=pair["prompt"], options=opts, display_order=order,
                            selection_reason=reason, selection_detail=detail, grounding=grounding,
                            explanation=pair.get("explanation"), step_index=step)

    # ------------------------------------------------------------ helpers ----
    @staticmethod
    def _stats(history: list[HistoryEntry]) -> dict[str, Any]:
        shown: set[str] = set()
        compared: set[frozenset[str]] = set()
        asked = {h.spec.id for h in history}
        t_tasks = [h for h in history if h.spec.template_id == "territory_pair"]
        for h in t_tasks:
            ids = [o.territory_id for o in h.spec.options]
            shown.update(ids)                                   # type: ignore[arg-type]
            compared.add(frozenset(ids))                        # type: ignore[arg-type]
        return {"shown": shown, "compared": compared, "asked": asked, "t_tasks": t_tasks}

    def _is_exploratory(self, spec: QuestionSpec) -> bool:
        return any(o.attributes.get("familiarity") in ("adjacent", "novel") for o in spec.options)

    def _wants_exploration(self, st: dict[str, Any]) -> bool:
        """Deterministic quota so that roughly `exploration_ratio` of territory tasks leave the syllabus."""
        if not self.ctx.has_syllabus:
            return False
        n_t = len(st["t_tasks"])
        done = sum(1 for h in st["t_tasks"] if self._is_exploratory(h.spec))
        return done < math.floor(self.ad["exploration_ratio"] * (n_t + 1) + 0.5)

    def _pick_in_field(self, fid: str, st: dict[str, Any], step: int, explore: bool) -> Territory | None:
        cands = [t for t in self.pack.territories if t.field == fid and t.id not in st["shown"]]
        if not cands:
            cands = [t for t in self.pack.territories if t.field == fid]
        if not cands:
            return None
        if self.ctx.has_syllabus:
            familiar = [t for t in cands if self.ctx.familiarity_of(t.id) == "familiar"]
            other = [t for t in cands if self.ctx.familiarity_of(t.id) != "familiar"]
            pool = (other or familiar) if explore else (familiar or other)
        else:
            pool = cands
        return self.rng("pick", step, fid).choice(sorted(pool, key=lambda t: t.id))

    # ---------------------------------------------------------- selection ----
    def select_next(self, history: list[HistoryEntry], profile: PreferenceProfile, ranking: list[Recommendation],
                    ) -> tuple[QuestionSpec | None, str | None]:
        """Return (next question, None) or (None, stop_reason)."""
        ad, n = self.ad, len(history)
        st = self._stats(history)
        if n >= ad["max_tasks"]:
            return None, "max_tasks_reached"
        coverage = ad["coverage_sequence"]
        if n < len(coverage):
            q = self._coverage(coverage[n], st, profile, n)
            if q is not None:
                return q, None

        pending_clar = self._pending_clarification(history, profile, ranking, st)
        challenge = self._pending_challenge(st, ranking)
        if n >= ad["min_tasks"] and pending_clar is None and challenge is None and self._stable(history):
            return None, "stable_ranking"
        if pending_clar is not None:
            return self.profile_question(pending_clar, "clarification", f"clarify:{pending_clar['id']}", n), None

        # Under-observed core dimensions.
        for key in ad["required_keys"]:
            if profile.weight(key) < ad["min_key_weight"]:
                pair = self._profile_pair_for(key, st)
                if pair is not None:
                    return self.profile_question(pair, "profile_pair", "low_dimension_coverage", n, key=key), None
        # Keep a mix: after a run of territory tasks, ask the next follow-up profile pair.
        run_len = ad["max_territory_run"]
        if len(history) >= run_len and all(h.spec.template_id == "territory_pair" for h in history[-run_len:]):
            pair = self._followup_pair(st, profile)
            if pair is not None:
                return self.profile_question(pair, "profile_pair", "dimension_followup", n), None

        # The current favourite must face its strongest alternatives before anything is refined.
        if challenge is not None:
            return self.territory_pair(challenge[0], challenge[1], "challenge_leader", n, rival_rank=challenge[2]), None
        q = self._adaptive_territory_task(st, ranking, n)
        if q is not None:
            return q, None
        pair = self._followup_pair(st, profile)
        if pair is not None:
            return self.profile_question(pair, "profile_pair", "dimension_followup", n), None
        return None, "no_informative_questions_left"

    def _coverage(self, slot: str, st: dict[str, Any], profile: PreferenceProfile, n: int) -> QuestionSpec | None:
        if slot == "P":
            for pid in self.ad["coverage_profile_pairs"]:
                if pid not in st["asked"]:
                    return self.profile_question(self.cfg.profile_pairs[pid], "profile_pair", "dimension_coverage", n)
            return None
        seen_fields = {self.pack.territory(t).field for t in st["shown"]}
        unseen = sorted((f for f in self.pack.fields if f.id not in seen_fields),
                        key=lambda f: (-profile.field_scores.get(f.id, 0.5), f.id))
        if not unseen:
            return None
        if len(unseen) >= 2:
            # "interleaved": each stronger-rated field first meets a mid/lower-rated one, so two favourites are
            # not forced to knock each other out before both have been seen (head-to-heads come later).
            # "adjacent": pair the most similar-rated fields.
            j = len(unseen) // 2 if self.ad.get("coverage_pairing", "interleaved") == "interleaved" else 1
            fa, fb = unseen[0].id, unseen[j].id
        else:
            others = sorted((f for f in self.pack.fields if f.id != unseen[0].id),
                            key=lambda f: (-profile.field_scores.get(f.id, 0.5), f.id))
            if not others:
                return None
            fa, fb = unseen[0].id, others[0].id
        explore = self._wants_exploration(st)
        a = self._pick_in_field(fa, st, n, explore)
        b = self._pick_in_field(fb, st, n, False)
        if a is None or b is None or a.id == b.id:
            return None
        return self.territory_pair(a, b, "field_coverage", n, fields=[fa, fb])

    def _pending_clarification(self, history: list[HistoryEntry], profile: PreferenceProfile,
                               ranking: list[Recommendation], st: dict[str, Any]) -> dict[str, Any] | None:
        asked = sum(1 for h in history if h.spec.template_id == "clarification")
        if asked >= self.ad["max_clarifications"] or len(history) < len(self.ad["coverage_sequence"]):
            return None
        active = {c.id for c in profile.conflicts}
        leader = ranking[0] if ranking else None
        if (leader is not None and leader.feasibility_flag
                and profile.score("feasibility_tolerance") <= self.ad["conflict_low"]):
            active.add("cl_interest_vs_feasibility")
        for cid, clar in self.cfg.clarifications.items():
            if cid in active and cid not in st["asked"]:
                return clar
        return None

    def _pending_challenge(self, st: dict[str, Any], ranking: list[Recommendation]
                           ) -> tuple[Territory, Territory, int] | None:
        """The leader versus the first runner-up (in the distinct shortlist) it has not yet been compared with."""
        shortlist = select_diverse(self.cfg, self.pack, ranking)
        if len(shortlist) < 2:
            return None
        leader = self.pack.territory(shortlist[0].territory_id)
        # Fields the leader has already been compared with: another territory from the same field would mostly
        # repeat that comparison, so it does not count as an untested alternative.
        met_fields = set()
        for pair in st["compared"]:
            if leader.id in pair:
                met_fields.update(self.pack.territory(t).field for t in pair if t != leader.id)
        for rival in shortlist[1:]:
            r = self.pack.territory(rival.territory_id)
            if frozenset((leader.id, r.id)) in st["compared"]:
                continue
            if r.field != leader.field and r.field in met_fields:
                continue
            return leader, r, rival.rank
        return None

    def _stable(self, history: list[HistoryEntry]) -> bool:
        w = self.ad["stability_window"]
        if len(history) < w + 1:
            return False
        # Stable = same first place and same set of three (2nd/3rd may swap) across the window.
        tops = [(h.top3_after[:1], frozenset(h.top3_after)) for h in history[-(w + 1):]]
        return all(t == tops[0] for t in tops) and bool(tops[0][0])

    def _profile_pair_for(self, key: str, st: dict[str, Any]) -> dict[str, Any] | None:
        for pid in self.ad["coverage_profile_pairs"] + self.ad["followup_profile_pairs"]:
            pair = self.cfg.profile_pairs[pid]
            if pid not in st["asked"] and (key in pair["a"]["signals"] or key in pair["b"]["signals"]):
                return pair
        return None

    def _followup_pair(self, st: dict[str, Any], profile: PreferenceProfile) -> dict[str, Any] | None:
        cands = [self.cfg.profile_pairs[pid] for pid in self.ad["followup_profile_pairs"] if pid not in st["asked"]]
        if not cands:
            return None
        # Least-observed dimension first; bank order breaks ties.
        def observed(pair: dict[str, Any]) -> float:
            keys = set(pair["a"]["signals"]) | set(pair["b"]["signals"])
            return min(profile.weight(k) for k in keys) if keys else 0.0
        return min(cands, key=observed)

    def _adaptive_territory_task(self, st: dict[str, Any], ranking: list[Recommendation], n: int) -> QuestionSpec | None:
        if len(ranking) < 2:
            return None
        T = self.pack.territory
        leader = T(ranking[0].territory_id)
        compared = st["compared"]

        def fresh(a: str, b: str) -> bool:
            return a != b and frozenset((a, b)) not in compared

        # 1. Exploration beyond the confirmed syllabus (or, with no syllabus, beyond what has been shown).
        adaptive_t = sum(1 for h in st["t_tasks"] if h.spec.selection_reason != "field_coverage")
        explore_now = self._wants_exploration(st) if self.ctx.has_syllabus else (
            (adaptive_t + 1) % self.ad["no_syllabus_exploration_every"] == 0)
        if explore_now:
            top_ids = [r.territory_id for r in ranking[:3]]
            near = {a for tid in top_ids for a in T(tid).adjacent}
            top_fields = {T(tid).field for tid in top_ids}
            near_fields = {a for f in top_fields for a in self.pack.field(f).adjacent} | top_fields

            def unexplored(r: Recommendation) -> bool:
                if r.territory_id in st["shown"]:
                    return False
                return self.ctx.familiarity_of(r.territory_id) != "familiar"

            pool = [r for r in ranking if unexplored(r)]
            adjacent_pool = [r for r in pool if r.territory_id in near or T(r.territory_id).field in near_fields]
            for cand in (adjacent_pool or pool)[:1]:
                partner = next((T(r.territory_id) for r in ranking[:4] if fresh(r.territory_id, cand.territory_id)), None)
                if partner is not None:
                    return self.territory_pair(T(cand.territory_id), partner, "exploration", n,
                                               explored=cand.territory_id)
        # 2. Near tie between the two leading territories.
        second = T(ranking[1].territory_id)
        if ranking[0].fit - ranking[1].fit <= self.ad["tie_margin"] and fresh(leader.id, second.id):
            return self.territory_pair(leader, second, "top_two_tie", n,
                                       margin=round(ranking[0].fit - ranking[1].fit, 4))
        # 3. Which part of the leading field? (needed to reach a territory rather than a field)
        sib = next((T(r.territory_id) for r in ranking[1:]
                    if T(r.territory_id).field == leader.field and fresh(leader.id, r.territory_id)
                    and ranking[0].fit - r.fit <= self.ad["refine_margin"]), None)
        if sib is not None:
            return self.territory_pair(leader, sib, "within_field_refine", n, field=leader.field)
        # 4. Any untested comparison among the leading group.
        top = [r.territory_id for r in ranking[:6]]
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                if fresh(a, b):
                    return self.territory_pair(T(a), T(b), "resolve_leading_group", n)
        return None


def replay(cfg: SurveyConfig, pack: DisciplinePack, ctx: CurriculumContext, calibration: dict[str, Any],
           answers: dict[str, Response], seed: int, studied_modules: list[Module] | None = None) -> SurveyRun:
    """Re-derive the whole survey from the stored answers. Pure and deterministic."""
    engine = Engine(cfg, pack, ctx, seed)
    run = SurveyRun()
    if not pack.supported:
        run.stop_reason = "unsupported_discipline"
        return run
    history: list[HistoryEntry] = []
    while True:
        profile = build_profile(cfg, pack, calibration, history, ctx, studied_modules)
        ranking = rank_territories(cfg, pack, profile, ctx)
        if history and not history[-1].top3_after:
            history[-1].top3_after = [r.territory_id for r in select_diverse(cfg, pack, ranking)]
        spec, stop = engine.select_next(history, profile, ranking)
        if spec is not None:
            run.selection_log.append({"step": spec.step_index, "question_id": spec.id, "template": spec.template_id,
                                      "reason": spec.selection_reason, "detail": spec.selection_detail,
                                      "display_order": spec.display_order})
        if spec is None:
            run.stop_reason = stop
            break
        if any(h.spec.id == spec.id for h in history):   # safety: never ask the same task twice
            run.selection_log.pop()
            run.stop_reason = "no_informative_questions_left"
            break
        response = answers.get(spec.id)
        if response is None:
            run.current = spec
            break
        history.append(HistoryEntry(spec=spec, response=response))
    run.history, run.profile, run.ranking = history, profile, ranking
    return run
