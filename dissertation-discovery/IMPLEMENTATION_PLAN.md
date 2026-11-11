# Implementation plan and audit

Status at 11 November 2026. Companion to `PRODUCT_SPEC.md` (the brief) and `README.md` (how to run).

## 1. Audit of the repository (Phase 0)

| Question | Finding |
|---|---|
| Framework / entry points | The repository contained only **AmsterdamEats**, an unrelated restaurant-booking app in two forms: a SwiftUI iOS project (`AmsterdamEats/`) and a .NET MAUI Windows project (`AmsterdamEats.Maui/`). |
| Existing survey code | None. No Python, no survey, taxonomy or syllabus code on any branch of this repository. |
| Existing LLM integration | None. |
| Tests | None. |
| Could it be run? | Not relevant to this product (Xcode / .NET MAUI projects). They were left untouched. |

The spec refers to an earlier Claude Code/API prototype. **It is not in this repository**, so there was nothing to
preserve or extend. Per the brief ("if this is effectively an empty project…"), the product was built new, in its own
folder `dissertation-discovery/`, with the suggested stack: Python, Streamlit, Pydantic, SQLite, pypdf, python-docx,
pytest and a small Claude adapter. If the earlier prototype exists elsewhere, its question wording or taxonomy can be
ported into `config/` without code changes.

## 2. What was built

End-to-end vertical slice, all acceptance criteria in spec §13 exercised by tests or a browser run:

| Spec area | Where | Notes |
|---|---|---|
| Start / discipline screen | `app.py` `page_start` | Economics supported; Psychology placeholder shows the "no content pack" message (Scenario H). |
| Upload: PDF / DOCX / TXT / CSV / pasted text | `dissdisc/curriculum/ingest.py` | Local decoding, page numbers kept for PDFs, explicit failure states (unsupported, empty, too large, corrupt, image-only). |
| Extraction: modules, codes, levels, credits, topics, **subtopics**, methods, theories, outcomes, source evidence, confidence | `curriculum/extract.py` | Deterministic heading/section parser. Catalogue listing and later specification of the same module are merged. Assessment, reading list and staff sections are skipped. |
| Taxonomy mapping | `curriculum/mapping.py`, `config/disciplines/economics.yaml` | Keyword/synonym matching with a confidence level; one item can map to several territories. |
| Claude-assisted extraction (strict schema) | `curriculum/llm_extract.py`, `llm.py` | JSON-schema output, Pydantic validation with unknown fields rejected, every claim must be supported by text found in the document, approved IDs only, staff/e-mail lines removed before sending, falls back to the deterministic parser. |
| Review / correct / statuses | `curriculum/review.py`, `page_review` | Nothing is "studied" until marked completed/current **and** the review is confirmed. Edit wording, retype, untick, add, delete, add modules by hand. |
| Fixed calibration | `config/survey_config.yaml`, `page_calibration` | 8 field ratings, 7 Likert items, 2 direct constraints, 2 optional skippable items, 1 unscored open prompt. |
| Pairwise choice tasks with stored attributes | `survey/engine.py` | Territory pairs (attributes from the content pack) and profile pairs (attributes and signals from config). Stable IDs, seeded left/right order, optional strength and reason, "neither / not sure". |
| Adaptive selection | `survey/engine.py` | Rules in order: opening coverage → clarification → under-observed dimension → mix rule → challenge the leader → exploration → near tie → within-field refinement → leading group. Reason logged per task. |
| Profile and ranking | `survey/profile.py`, `scoring.py` | Pure functions of the responses. Five components, feasibility gate, diversity rule, qualitative evidence label. |
| Results and research handoff | `recommendations.py`, `page_results`, `page_handoff` | Three territories with traceable reasons (survey vs syllabus vs caution), methods, data routes to check, risks, search strings, 60–90 minute exercise, supervisor prompts. |
| Export | `exports.py` | Markdown summary and JSON record (design version, seed, task specs, responses, superseded responses, selection log). |
| Storage | `storage.py` | SQLite; resume by link; delete. Uploaded files and full text are never written. |
| Tests | `tests/` | 63 tests. |

### Design decisions worth knowing

* **Survey state is never stored, only answers.** `replay()` re-derives questions, profile and ranking from
  (config, content pack, confirmed curriculum, seed, answers). This is what makes backtracking safe and a session
  reproducible. Revised answers are kept in the log as superseded.
* **The syllabus contributes no interest signal.** It affects (a) which territory represents a field in a question
  and the wording note on the card, (b) the "familiar / next to / new" attribute, (c) a small feasibility adjustment
  when a typical method was taught, (d) explanations. A test asserts that topic-interest scores are identical with and
  without a syllabus for the same answers.
* **The LLM cannot reach the design.** It is given no survey config, is only asked for JSON in a schema the app
  supplies, and its output passes through validators before use. Question selection and scoring import no LLM code.
* **Uploaded text is data.** Instruction-like lines are dropped and listed for the student; the LLM prompt delimits
  the document and tells the model to ignore instructions; a test shows a poisoned syllabus yields an identical
  question sequence and ranking.

## 3. Decisions that affect the scientific meaning of the survey

All are isolated in `config/survey_config.yaml`. None is validated. Bump `design_version` when changing any of them.

| Decision | Current default | Why it matters |
|---|---|---|
| Scoring weights | 0.35 / 0.20 / 0.20 / 0.15 / 0.10 (spec placeholders) | Determines the ranking. Not calibrated. |
| Topic-interest update | Elo-style step (`choice_step`, `expectation_scale`) | A surprising choice moves scores more than an expected one, so a runner-up is not written off for losing to the favourite. A heuristic, not an estimated choice model. Order-dependent by design. |
| Opening field pairing | `interleaved` (1st v 5th by rating…) | Decides which comparisons are observed. `adjacent` is the alternative. |
| Attribute inference from territory choices | `attribute_spill: 0.15`, 1.0 when the student names that reason, 0 when they say "the subject itself" | How much method/feasibility/relevance preference is inferred from topic choices. |
| "Neither / not sure" | Allowed | Open decision in spec §15. |
| Feasibility | Ranking term **and** gate (flag + ×0.85 below 0.40); stated tolerance softens the term but never the raw estimate | Spec leaves "term or hard warning" open. |
| Diversity | Max 2 per field, theme-overlap limit, runners-up need neutral-or-better topic interest | Trades raw score for distinctness. |
| Exploration share | 0.30 of territory tasks outside the confirmed syllabus | Spec's proposed 70/30; untested. |
| Module "liked / disliked" flag | Counts as a response (weight 0.75 on the module's field) | A student statement, not syllabus inference; could be removed. |
| Stop rule | min 10, max 14; stop when first place and the set of three are unchanged for 3 tasks and the leader has met its runners-up | In simulated runs the survey usually reaches 14. |
| Optional values item | One distributional-focus item; if skipped the component is omitted | No political-orientation measure exists anywhere. |
| Career item | Recorded, not scored | Appears as a supervisor prompt only. |

## 4. Known limitations (truthful)

* **Claude integration has not been run against the live API.** No API key was available in the build environment.
  The adapter follows the current SDK's structured-output call, and the validation boundary is tested with a stub
  model (valid, hallucinated, malformed and adversarial outputs), but real-model extraction quality, latency and cost
  are unmeasured. The spec's Phase 2 "compare against deterministic fallback" has not been done.
* **Claude does not word explanations.** The "why it appears" text is generated by templates from recorded
  evidence. LLM use is limited to extraction and (opt-in) option-description wording.
* **The deterministic parser is heuristic.** It expects recognisable module headings (code + title, or
  "Module title:") and section labels such as "Module content" / "Learning outcomes". Multi-column PDFs, content held
  only in complex tables, and unusual layouts will parse poorly; the review screen is the safety net. Year/level is
  only taken from explicit text. Scanned PDFs are rejected (no OCR).
* **The taxonomy is seed content**: 8 fields, 28 territories, keyword mapping. Mapping is literal (e.g.
  "externalities" links to carbon pricing). Data sources are named suggestions to check; **no dataset link has been
  verified** and access conditions change.
* **Not a validated instrument.** Item wording, attribute levels and the choice design are not balanced or efficient
  in the discrete-choice sense, and no individual-level statistical inference is made or implied.
* **No accounts or access control.** A session is reachable by its ID in the page link on the machine running the
  app. There is no retention schedule, expiry or research-consent workflow. Source excerpts (short lines of the
  uploaded document) are stored with the reviewed records.
* **UI**: Streamlit reruns on each click (fast locally, no model call per click). PDF export is via the browser's
  print function. Accessibility relies on Streamlit's components (keyboard-operable, radio semantics for pill
  controls) and has not been audited. The review screen edits one module's contents at a time.
* **Psychology** is a placeholder pack that demonstrates the unsupported-discipline path only.

## 5. Next steps

1. Run Claude-assisted extraction on real handbooks; measure agreement with the deterministic parser and the
   rejection rate; tune the prompt and chunking.
2. Have an economist review and extend the territory pack, attribute levels and wording; verify dataset entries.
3. Decide the open design questions in §3 with the academic lead, then freeze `design_version` for any study.
4. Pilot with students: timing, comprehension of the cards, whether the shortlist feels right, stop rule.
5. Add institution-specific links, PDF export, and (if wanted) LLM-polished explanations behind the same validation.
6. Accounts, retention policy and a separate opt-in consent flow before any aggregate choice modelling.
