# Dissertation Discovery

A guided, adaptive stated-preference survey that helps undergraduates find **research territories** worth
investigating for a dissertation, and sends them away with a 60–90 minute reading and data exercise. It is not a
topic or title generator and writes no part of a dissertation.

Economics is the first discipline. The survey engine, data model and syllabus reader are discipline-independent;
adding a discipline means adding a content pack in `config/disciplines/`.

* Product brief and acceptance criteria: [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md)
* Audit, design decisions and limitations: [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md)

## Run it

Requires Python 3.10 or later.

```bash
cd dissertation-discovery
```

```bash
pip install -r requirements.txt
```

```bash
streamlit run app.py
```

Open the local URL Streamlit prints (by default http://localhost:8501). No API key is needed: without one the app
runs in **demo mode** using the built-in parser, built-in question wording and the curated economics pack.

Run the tests:

```bash
python -m pytest -q
```

Print three simulated student journeys (labour/policy, macro/theory, uncertain) on the same sample syllabus:

```bash
python scripts/simulate_journeys.py
```

## Try the syllabus → survey → results journey

1. **Start**: keep *Economics*. Choose one of:
   * *Try with a sample syllabus*: loads the fictional BSc Economics handbook in `sample_data/` with six modules
     pre-marked as studied.
   * *Upload or paste my syllabus*: upload any of the files in `sample_data/`, or your own.
   * *Continue without a syllabus*.
2. **Your syllabus**: upload one or more files and/or paste text, then *Read my documents*. Try
   `sample_module_specs.pdf` (two modules, page numbers kept), `sample_module_spec.docx`, `sample_module_list.csv`,
   `sample_scanned_no_text.pdf` (shows the scanned-document message) and `sample_adversarial_module.txt` (two
   instruction-like lines are ignored and listed).
3. **Review modules**: set each module you took to *Completed* or *Taking now* in the table. Open a module to
   untick, correct or add topics, subtopics and methods; each row shows the source line it came from. Nothing is used
   until you press *Looks right*.
4. **About you**: field interest ratings, seven agree/disagree items, two practical constraints, two optional items.
5. **Choices**: pick between two cards, optionally say how strongly and why, or answer *Neither / not sure*. *Back*
   lets you change an earlier answer; later questions and all results are recalculated. *Why am I being asked this?*
   shows the selection rule that produced the question.
6. **Shortlist**: three ranked territories with reasons marked as coming from your survey answers (💬), your
   confirmed syllabus (📘) or as cautions (⚖️), plus angles, methods and data routes to check, risks and search
   strings. *How this was ranked* shows the weights.
7. **Research plan**: the 60–90 minute checklist, copyable search strings, library/database entry points, supervisor
   questions, and downloads (Markdown summary, JSON record).

The page link contains a session ID, so reopening it on the same machine resumes the session. *Privacy and reset* in
the sidebar deletes it.

## Sample files (`sample_data/`, all fictional)

| File | Use |
|---|---|
| `economics_programme_handbook.txt` | Catalogue of 41 modules (compulsory and optional lists) with full specifications for 8. Also the built-in demo syllabus. |
| `sample_module_specs.pdf` | Two module specifications on two pages. |
| `sample_module_spec.docx` | One module with a details table and bulleted content. |
| `sample_module_list.csv` | Columns `code,title,year,credits,status,topics,subtopics,methods` (semicolon-separated lists). |
| `sample_scanned_no_text.pdf` | A PDF with no text layer. |
| `sample_adversarial_module.txt` | Contains "ignore your instructions…" lines. |

Regenerate the binary samples with `python scripts/make_sample_files.py`.

## Claude integration (optional)

Set an API key in the environment before starting the app; never put it in code or commit it.

```bash
export ANTHROPIC_API_KEY=your-key-here
```

| Variable | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | unset | When set, Claude can assist syllabus extraction. Unset means demo mode. |
| `DD_LLM_MODEL` | `claude-opus-5-5` | Model used by the adapter. |
| `DD_LLM_EXTRACT` | `1` | Default state of the "Use Claude to help read the document" tick-box (shown only when a key is set). |
| `DD_LLM_COPY` | `0` | `1` lets Claude re-word the two option descriptions on a card (cached per question). |
| `DD_DISABLE_LLM` | unset | `1` forces demo mode even with a key. |
| `DD_DB_PATH` | `data/sessions.sqlite3` | SQLite file for sessions. |
| `DD_CONFIG_DIR` | `config` | Alternative configuration directory. |

What Claude may do, and how it is contained:

* **Extract and tag curriculum data** into a strict JSON schema. Output with unknown fields is rejected; each module
  title and item must be supported by text found in the uploaded document or it is discarded and counted; only
  approved method and territory IDs are accepted; staff/contact lines and e-mail addresses are removed before text is
  sent; on any failure the built-in parser is used.
* **Re-word option descriptions** for an already-selected question (opt-in). Titles, prompts, option IDs, attributes
  and order are fixed; text that is too long, contains numbers or instruction-like content, or has the wrong option
  IDs is replaced by the built-in wording.
* It **never** selects questions, computes scores, ranks territories, or sees the survey configuration.

This integration is covered by tests using a stub model. **It has not yet been exercised against the live API**
(see `IMPLEMENTATION_PLAN.md` §4).

## Configuration (edit without touching code)

| File | Contains |
|---|---|
| `config/survey_config.yaml` | Design version, scales, dimensions, calibration items, attribute levels, profile-pair bank, clarification questions, scoring weights and parameters, diversity and evidence rules, adaptive policy (coverage, min/max tasks, exploration ratio, stop rule), upload limits. |
| `config/disciplines/economics.yaml` | Fields, methods, theories and 28 research territories with attributes, angles, data routes to check, risks, search strings and supervisor questions. |
| `config/disciplines/psychology.yaml` | Placeholder showing how an unsupported discipline behaves. |
| `config/institutions.yaml` | Library and database entry points (generic and University of Leeds). |

The configuration is validated on load: an item or option that signals an undeclared preference key, or weights that
do not sum to 1, stops the app. The numbers are proposed defaults, not validated estimates. Change `design_version`
whenever you change what is measured or how it is scored.

## Code layout

```
app.py                      Streamlit screens only
dissdisc/
  models.py                 Pydantic domain models
  config.py                 loads and validates configuration and packs
  service.py                functions the UI calls (ingest, record_response, results, …)
  curriculum/ingest.py      file decoding (PDF, DOCX, TXT, CSV)
  curriculum/extract.py     deterministic extraction with source evidence
  curriculum/mapping.py     keyword mapping to the taxonomy
  curriculum/llm_extract.py validated Claude-assisted extraction
  curriculum/review.py      student corrections; what the survey may know about the curriculum
  survey/profile.py         preference profile from responses
  survey/engine.py          adaptive question selection and deterministic replay
  survey/copy.py            question wording (templates; optional validated LLM wording)
  scoring.py                ranking, feasibility gate, diversity, evidence labels
  recommendations.py        reasons, research plan, results bundle
  exports.py                Markdown and JSON exports
  storage.py                SQLite persistence
  llm.py                    adapter: none / stub / Anthropic
  simulate.py               simulated students for demos and tests
tests/                      63 tests
```

## How the ranking works (short version)

For each territory: `fit = 0.35 × topic interest + 0.20 × methods fit + 0.20 × feasibility + 0.15 × relevance/values
alignment + 0.10 × familiar-versus-new fit`.

* **Topic interest** starts from the student's rating of the field and moves with each territory choice; a
  surprising choice moves it more than an expected one.
* **Methods fit** compares the territory's usual approach and research style with the student's Likert answers and
  profile-pair choices.
* **Feasibility** comes from the territory's typical data access and technical demand, the student's stated software
  and data constraints, and whether a typical method appears in a confirmed module. Below a threshold the territory
  is flagged and marked down.
* **Syllabus coverage never raises topic interest.**
* The three results must be distinct (at most two from one field, limited theme overlap).
* "Evidence" labels (Higher / Moderate / Limited / Insufficient) describe how much consistent survey evidence bears
  on a territory. They are not probabilities.

## Limitations

See `IMPLEMENTATION_PLAN.md` §4 for the full list. In brief: the live Claude path is untested; the built-in parser is
heuristic and scanned PDFs are unsupported; the economics pack is seed content with unverified data-source
suggestions; the instrument and weights are not validated; there are no accounts or retention controls.
