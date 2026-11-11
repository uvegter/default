"""Dissertation Discovery — Streamlit UI.

Run:  streamlit run app.py

This file only renders screens and forwards input to `dissdisc.service`.
All survey logic, scoring and extraction live in the `dissdisc` package.
"""
from __future__ import annotations


import streamlit as st

from dissdisc import service
from dissdisc.config import env_flag, list_packs, load_institutions, load_survey_config
from dissdisc.curriculum import review
from dissdisc.exports import ACCESS_LABEL, export_json, export_markdown
from dissdisc.llm import get_llm
from dissdisc.models import Module, SessionState
from dissdisc.scoring import band
from dissdisc.storage import Store

st.set_page_config(page_title="Dissertation Discovery", page_icon="🧭", layout="centered")

CFG = load_survey_config()
STAGES = [("start", "Start"), ("upload", "Your syllabus"), ("review", "Review modules"), ("calibration", "About you"),
          ("choices", "Choices"), ("results", "Shortlist"), ("handoff", "Research plan")]
STATUS_LABELS = review.STATUS_LABELS
REASON_TEXT = {
    "field_coverage": "An opening question: every broad area appears once so that nothing is ruled out unseen.",
    "dimension_coverage": "An opening question about how you like to work, asked of everyone.",
    "challenge_leader": "Your current front-runner is being tested against a strong alternative it has not met yet.",
    "top_two_tie": "Your two leading directions are very close, so this compares them directly.",
    "exploration": "This introduces a direction you have not seen yet, so the shortlist is not limited to the familiar.",
    "within_field_refine": "You seem drawn to this area, so this compares two different parts of it.",
    "low_dimension_coverage": "One aspect of your preferences has had little evidence so far.",
    "dimension_followup": "A further trade-off about how you like to work.",
    "resolve_leading_group": "Two of your leading directions have not been compared directly yet.",
}

CSS = """
<style>
.block-container {max-width: 920px; padding-top: 3.6rem;}
h1 {letter-spacing: -0.02em;}
.dd-kicker {font-size: .78rem; letter-spacing: .09em; text-transform: uppercase; opacity: .65; margin-bottom: .2rem;}
.dd-lead {font-size: 1.08rem; line-height: 1.55; opacity: .9;}
.dd-chip {display: inline-block; font-size: .78rem; padding: .16rem .55rem; margin: .12rem .3rem .12rem 0;
          border-radius: 999px; border: 1px solid rgba(128,128,128,.35); background: rgba(128,128,128,.08);}
.dd-chip.syll {border-color: rgba(31,111,235,.45); background: rgba(31,111,235,.10);}
.dd-chip.warn {border-color: rgba(200,120,0,.5); background: rgba(200,120,0,.10);}
.dd-chip.ok {border-color: rgba(26,127,55,.5); background: rgba(26,127,55,.10);}
.dd-path {font-size: .9rem; opacity: .8; margin: .15rem 0 .5rem 0;}
.dd-rank {font-size: .8rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; opacity: .7;}
.dd-card-title {font-size: 1.12rem; font-weight: 650; line-height: 1.3; margin: .1rem 0 .4rem 0;}
.dd-meter {display: flex; align-items: center; gap: .5rem; margin: .18rem 0; font-size: .88rem;}
.dd-meter .lbl {width: 11.5rem; opacity: .85;}
.dd-meter .segs {display: flex; gap: 3px;}
.dd-meter .seg {width: 26px; height: 9px; border-radius: 2px; background: rgba(128,128,128,.22);}
.dd-meter .seg.on {background: #1f6feb;}
.dd-meter .val {font-weight: 600; min-width: 3.5rem;}
.dd-src {font-size: .8rem; opacity: .7;}
.dd-note {font-size: .86rem; opacity: .8;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 12px;}
@media (max-width: 640px) {.dd-meter .lbl {width: 8.5rem;}}
</style>
"""


# ------------------------------------------------------------------ plumbing ---
@st.cache_resource
def _store() -> Store:
    return Store()


@st.cache_resource
def _llm():
    return get_llm()


def _state() -> SessionState:
    if "state" not in st.session_state:
        sid = st.query_params.get("session")
        loaded = _store().load(sid) if sid else None
        st.session_state.state = loaded or service.new_session("economics")
        st.query_params["session"] = st.session_state.state.id
    return st.session_state.state


def _save(run=None) -> None:
    try:
        _store().save(_state(), run)
    except Exception as exc:  # persistence must never break the journey
        st.session_state["_save_error"] = type(exc).__name__


def _go(stage: str) -> None:
    _state().stage = stage
    st.session_state.pop("view_index", None)
    _save()
    st.rerun()


def _reset_everything() -> None:
    try:
        _store().delete(_state().id)
    except Exception:
        pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.query_params.clear()
    st.rerun()


def _meter(label: str, value: float) -> str:
    b = band(value)
    on = {"Weak": 1, "Mixed": 2, "Good": 3, "Strong": 4}[b]
    segs = "".join(f'<span class="seg{" on" if i < on else ""}"></span>' for i in range(4))
    return f'<div class="dd-meter"><span class="lbl">{label}</span><span class="segs">{segs}</span><span class="val">{b}</span></div>'


def _chips(items: list[tuple[str, str]]) -> str:
    return "".join(f'<span class="dd-chip {cls}">{text}</span>' for text, cls in items)


def _stage_allowed(stage: str, state: SessionState) -> bool:
    if stage in ("start", "upload"):
        return True
    if stage == "review":
        return bool(state.modules)
    if stage == "calibration":
        return True
    if stage == "choices":
        return state.calibration_done
    return state.calibration_done and bool(state.answers)


def sidebar(state: SessionState) -> None:
    with st.sidebar:
        st.markdown("### 🧭 Dissertation Discovery")
        llm = _llm()
        if llm.enabled:
            st.caption("AI assistance is **on** for reading uploads"
                       + (" and wording options" if env_flag("DD_LLM_COPY") else "")
                       + ". It never chooses questions or scores.")
        else:
            st.caption("**Demo mode**: no AI model is used. Everything runs on built-in rules and wording.")
        current = [s for s, _ in STAGES].index(state.stage) if state.stage in dict(STAGES) else 0
        for i, (sid, label) in enumerate(STAGES):
            mark = "●" if i == current else ("✓" if i < current else "○")
            if st.button(f"{mark}  {label}", key=f"nav_{sid}", width="stretch",
                         disabled=not _stage_allowed(sid, state), type="primary" if i == current else "secondary"):
                _go(sid)
        st.divider()
        with st.expander("Privacy and reset"):
            st.markdown(
                "- Uploaded files are read in memory. The file and its full text are **not stored**; only the module "
                "records you review (with short source excerpts) and your answers are saved, in a local database "
                "file on the computer running this app.\n"
                + ("- AI assistance is on: the text of uploaded documents (with staff names and e-mail addresses on "
                   "contact lines removed) is sent to Anthropic's API to help extract modules.\n" if llm.enabled else
                   "- Nothing is sent to any AI service in demo mode.\n")
                + "- There are no accounts. Anyone with this page's link (it contains your session ID) can reopen "
                  "this session on this computer.\n- This is a prototype: do not upload documents containing "
                  "sensitive personal information.")
            if st.button("Delete my session and start over", width="stretch"):
                _reset_everything()
            if st.button("Remove uploaded syllabus only", width="stretch", disabled=not state.modules):
                review.clear_curriculum(state)
                _go("upload")
        st.caption(f"Session `{state.id}` · design `{state.design_version}`")


# -------------------------------------------------------------------- screens ---
def page_start(state: SessionState) -> None:
    st.markdown('<div class="dd-kicker">Guided exploration, not a topic generator</div>', unsafe_allow_html=True)
    st.title("Find a dissertation direction worth investigating")
    st.markdown('<p class="dd-lead">Tell us what you have studied, answer a short series of research-preference '
                'questions, and leave with three evidence-based research directions and a concrete plan to explore '
                'them yourself.</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**What you get**\n- Three ranked *research territories* with the reasons they fit\n"
                    "- Methods, data routes and risks to check\n- A 60–90 minute reading and data exercise\n"
                    "- Questions to take to your supervisor")
    with c2:
        st.markdown("**What it does not do**\n- Write a title, question or any part of your dissertation\n"
                    "- Promise originality, data access or feasibility\n- Replace your supervisor\n"
                    "- Invent references")
    st.caption("The first survey takes roughly 10–15 minutes. You can go back and change answers at any point.")
    st.divider()
    packs = list_packs()
    ids = [p.id for p in packs]
    c1, c2 = st.columns(2)
    with c1:
        disc = st.selectbox("Discipline", ids, index=ids.index(state.discipline_id) if state.discipline_id in ids else 0,
                            format_func=lambda i: next(p.label + ("" if p.supported else " (content not yet available)")
                                                       for p in packs if p.id == i))
        year = st.selectbox("Stage of study", ["Year 1", "Year 2", "Year 3 / final year", "Postgraduate", "Other"],
                            index=["Year 1", "Year 2", "Year 3 / final year", "Postgraduate", "Other"].index(
                                state.year_of_study) if state.year_of_study else 1)
    with c2:
        uni = st.text_input("University (optional)", value=state.university or "")
        insts = load_institutions()["institutions"]
        inst = st.selectbox("Library links to show", list(insts), format_func=lambda i: insts[i]["label"],
                            index=list(insts).index(state.institution_id) if state.institution_id in insts else 0)
    if disc != state.discipline_id:
        fresh = service.new_session(disc, seed=state.random_seed)
        fresh.id, fresh.created_at = state.id, state.created_at
        st.session_state.state = state = fresh
    state.year_of_study, state.university, state.institution_id = year, uni.strip() or None, inst
    pack = service.pack_for(state)
    if not pack.supported:
        st.warning(f"**{pack.label} is not supported yet.** The survey engine and syllabus reader are "
                   "discipline-independent, but no topic content pack has been written for this discipline, so no "
                   "research territories can be recommended. Choose Economics to try the full journey.")
        _save()
        return
    st.markdown("#### How would you like to begin?")
    c1, c2, c3 = st.columns(3)
    if c1.button("Upload or paste my syllabus", type="primary", width="stretch"):
        _go("upload")
    if c2.button("Try with a sample syllabus", width="stretch"):
        review.clear_curriculum(state)
        service.load_sample_curriculum(state)
        st.session_state["module_table_v"] = st.session_state.get("module_table_v", 0) + 1
        _go("review")
    if c3.button("Continue without a syllabus", width="stretch"):
        _go("calibration")
    st.caption("The sample is a fictional BSc Economics handbook. Without a syllabus the survey uses a curated list "
               "of economics research areas and never refers to your modules.")


def page_upload(state: SessionState) -> None:
    st.title("Your syllabus")
    st.markdown("Upload or paste a programme handbook, module catalogue or individual module descriptions. We pull "
                "out modules, topics, subtopics and taught methods, and **you check everything on the next screen** "
                "before any of it is used.")
    llm = _llm()
    use_llm = False
    if llm.enabled:
        use_llm = st.checkbox("Use Claude to help read the document (sends its text to Anthropic's API)",
                              value=env_flag("DD_LLM_EXTRACT", True),
                              help="AI suggestions are only kept when matching text is found in your document. "
                                   "Untick to use the built-in parser only.")
    limits = CFG.uploads
    files = st.file_uploader("Upload files", type=[e.strip(".") for e in limits["accepted_extensions"]],
                             accept_multiple_files=True,
                             help=f"Text-based PDF, Word (.docx), plain text or CSV, up to {limits['max_file_mb']} MB each.")
    pasted = st.text_area("…or paste module descriptions", height=160,
                          placeholder="ECON2110 Labour Economics\nModule content\nWeek 1: Labour supply – hours of work; participation\n…")
    st.caption("🔒 Files are read in memory and not stored. Scanned (image-only) PDFs cannot be read in this version. "
               "See *Privacy and reset* in the sidebar.")
    if st.button("Read my documents", type="primary", disabled=not (files or pasted.strip())):
        adapter = llm if use_llm else None
        outcomes = []
        with st.spinner("Reading…"):
            for f in files or []:
                try:
                    ex = service.ingest_file(state, f.name, f.getvalue(), adapter)
                    outcomes.append((f.name, ex))
                except Exception as exc:   # defensive: an unexpected parser bug must not crash the page
                    outcomes.append((f.name, f"Unexpected problem reading this file ({type(exc).__name__}). "
                                             "Try pasting the text instead."))
            if pasted.strip():
                try:
                    outcomes.append(("Pasted text", service.ingest_text(state, pasted, "pasted text", adapter)))
                except Exception as exc:
                    outcomes.append(("Pasted text", f"Unexpected problem reading the pasted text ({type(exc).__name__})."))
        st.session_state["ingest_outcomes"] = outcomes
        st.session_state["module_table_v"] = st.session_state.get("module_table_v", 0) + 1
        _save()
    for name, ex in st.session_state.get("ingest_outcomes", []):
        if isinstance(ex, str):
            st.error(f"**{name}** — {ex}")
        elif ex.document.parse_status != "ok":
            st.error(f"**{name}** — {ex.document.message}")
        elif not ex.modules:
            st.warning(f"**{name}** — the file was read, but no modules were recognised. "
                       "Paste the module descriptions, or add modules by hand on the review screen.")
        else:
            n_items = sum(len(m.items) for m in ex.modules)
            how = "with AI assistance" if ex.document.extractor == "llm" else "with the built-in parser"
            st.success(f"**{name}** — found {len(ex.modules)} module(s) and {n_items} content item(s) {how}.")
            for w in ex.warnings:
                st.info(w)
    c1, c2, c3 = st.columns(3)
    if c1.button("Review what was found →", type="primary", disabled=not state.modules, width="stretch"):
        _go("review")
    if c2.button("Add modules by hand", width="stretch"):
        st.session_state["show_add_module"] = True
        _go("review")
    if c3.button("Skip the syllabus", width="stretch"):
        _go("calibration")


def _item_rows(m: Module, pack) -> list[dict]:
    labels = {t.id: t.label for t in pack.territories} | {x.id: x.label for x in pack.methods} | {
        x.id: x.label for x in pack.theories}
    rows = []
    for i in m.items:
        src = ""
        if i.evidence:
            src = (f"p.{i.evidence.page} · " if i.evidence.page else "") + f"“{i.evidence.excerpt[:110]}”"
        elif i.origin == "user":
            src = "added by you"
        conf = {"high": "High", "medium": "Medium — check", "low": "Low — check", "user": "Yours"}[i.extraction_confidence]
        rows.append({"_id": i.id, "Use": i.included, "Type": i.kind, "Text": i.text,
                     "Linked research area / method": "; ".join(labels.get(t, t) for t in i.taxonomy_ids) or "—",
                     "Confidence": conf, "Source in your document": src})
    return rows


def page_review(state: SessionState) -> None:
    pack = service.pack_for(state)
    st.title("Check what we found")
    st.markdown("This is the only course information the survey will use. **Nothing counts as studied until you say "
                "so**: set each module you have taken to *Completed* or *Taking now*. Being listed in a handbook, or "
                "having completed a module, is never treated as a sign that you liked it or are good at it.")
    if state.used_sample_curriculum:
        st.info("You are looking at the built-in **sample** handbook (a fictional BSc Economics programme). Six "
                "modules are pre-marked as studied so you can try the journey; change them as you like.")
    for w in dict.fromkeys(state.ingest_warnings):
        st.caption("ℹ️ " + w)
    if state.flagged_lines:
        with st.expander(f"{len(state.flagged_lines)} line(s) in your document were ignored"):
            st.caption("These looked like instructions to a computer system rather than course content, so they "
                       "were not extracted. Uploaded text is only ever treated as data.")
            for line in state.flagged_lines:
                st.code(line, language=None)

    if state.modules:
        n_studied = sum(m.studied for m in state.modules)
        c1, c2, c3 = st.columns(3)
        c1.metric("Modules found", len(state.modules))
        c2.metric("Marked as studied", n_studied)
        c3.metric("With topics extracted", sum(bool(m.of_kind("topic", "subtopic", included_only=False)) for m in state.modules))
        b1, b2, b3 = st.columns(3)
        v = st.session_state.get("module_table_v", 0)
        if b1.button("Mark compulsory modules as completed", width="stretch",
                     disabled=not any(m.listed_as == "core" for m in state.modules),
                     help="Only modules the document lists as compulsory/core. Check the result."):
            for m in state.modules:
                if m.listed_as == "core" and m.status == "unconfirmed":
                    m.status = "completed"
            st.session_state["module_table_v"] = v + 1
            state.curriculum_confirmed = False
            _save()
            st.rerun()
        if b2.button("Clear all statuses", width="stretch"):
            for m in state.modules:
                m.status = "optional" if m.listed_as == "optional" else "unconfirmed"
            st.session_state["module_table_v"] = v + 1
            state.curriculum_confirmed = False
            _save()
            st.rerun()
        only_content = b3.toggle("Only modules with topics", value=False)
        shown = [m for m in state.modules if not only_content or m.items]
        fields = {f.id: f.label for f in pack.fields}
        rows = [{"Status": STATUS_LABELS[m.status], "Code": m.code or "", "Title": m.title,
                 "Topics": len(m.of_kind("topic", "subtopic", included_only=False)),
                 "Year / level": m.year_or_level or "", "How was it? (optional)": {"liked": "Liked it", "disliked": "Disliked it"}.get(m.enjoyment, "—"),
                 "Broad area": ", ".join(fields.get(a, a) for a in m.broad_areas) or "—",
                 "Check": "⚠ low confidence" if m.extraction_confidence == "low" else ""} for m in shown]
        edited = st.data_editor(
            rows, key=f"module_table_{v}_{only_content}", hide_index=True, width="stretch", num_rows="fixed",
            height=min(38 * (len(rows) + 1) + 4, 460),
            column_config={
                "Status": st.column_config.SelectboxColumn(options=list(STATUS_LABELS.values()), required=True, width="medium"),
                "How was it? (optional)": st.column_config.SelectboxColumn(
                    options=["—", "Liked it", "Disliked it"], width="medium",
                    help="Optional. Your own view of a module you took is treated as one of your answers."),
                "Code": st.column_config.TextColumn(width="small"),
                "Year / level": st.column_config.TextColumn(disabled=True, width="small"),
                "Broad area": st.column_config.TextColumn(disabled=True),
                "Topics": st.column_config.NumberColumn(disabled=True, width="small"),
                "Check": st.column_config.TextColumn(disabled=True, width="small")})
        review.apply_module_rows(state, edited, [m.id for m in shown])

        st.markdown("#### Topics, subtopics and methods")
        with_items = [m for m in state.modules]
        default = next((i for i, m in enumerate(with_items) if m.studied and m.items), 0)
        sel = st.selectbox("Open a module to check or correct its contents", range(len(with_items)), index=default,
                           format_func=lambda i: f"{with_items[i].display_label}  ·  {STATUS_LABELS[with_items[i].status]}"
                                                 f"  ·  {len(with_items[i].items)} items")
        m = with_items[sel]
        iv = st.session_state.setdefault("item_v", {}).get(m.id, 0)
        st.caption("Untick anything that is wrong or that you did not actually cover, correct the wording, or add "
                   "rows. *Topics* and more specific *subtopics* are kept separately; *methods* are what the module "
                   "says it teaches, not a claim that you are confident using them.")
        edited_items = st.data_editor(
            _item_rows(m, pack), key=f"items_{m.id}_{iv}", hide_index=True, width="stretch", num_rows="dynamic",
            column_order=["Use", "Type", "Text", "Linked research area / method", "Confidence", "Source in your document"],
            column_config={
                "Use": st.column_config.CheckboxColumn(default=True, width="small"),
                "Type": st.column_config.SelectboxColumn(options=["topic", "subtopic", "method", "theory", "outcome"],
                                                         default="topic", required=True, width="small"),
                "Text": st.column_config.TextColumn(width="large"),
                "Linked research area / method": st.column_config.TextColumn(disabled=True),
                "Confidence": st.column_config.TextColumn(disabled=True, width="small"),
                "Source in your document": st.column_config.TextColumn(disabled=True)})
        c1, c2 = st.columns([1, 1])
        if c1.button("Save changes to this module", width="stretch"):
            review.apply_item_rows(state, m, edited_items, pack)
            st.session_state["item_v"][m.id] = iv + 1
            _save()
            st.rerun()
        if c2.button("Remove this module", width="stretch"):
            review.remove_module(state, m.id)
            st.session_state["module_table_v"] = v + 1
            state.curriculum_confirmed = False
            _save()
            st.rerun()
    else:
        st.info("No modules yet. Add them by hand below, or go back and upload or paste a document.")

    with st.expander("Add a module by hand", expanded=st.session_state.pop("show_add_module", False) or not state.modules):
        with st.form("add_module", clear_on_submit=True):
            c1, c2, c3 = st.columns([1, 3, 2])
            code = c1.text_input("Code (optional)")
            title = c2.text_input("Module title")
            status = c3.selectbox("Status", ["completed", "current"], format_func=STATUS_LABELS.get)
            topics = st.text_area("Topics you covered (one per line; optional)", height=90)
            methods = st.text_input("Methods taught (optional, separated by semicolons)")
            if st.form_submit_button("Add module") and title.strip():
                mod = review.add_module(state, title, pack, code=code, status=status)
                for line in topics.splitlines():
                    if line.strip():
                        review.add_item(mod, "topic", line, pack)
                for part in methods.split(";"):
                    if part.strip():
                        review.add_item(mod, "method", part, pack)
                review.map_module(mod, pack)
                st.session_state["module_table_v"] = st.session_state.get("module_table_v", 0) + 1
                _save()
                st.rerun()

    st.divider()
    n_studied = sum(m.studied for m in state.modules)
    if n_studied == 0:
        st.warning("No module is marked *Completed* or *Taking now*, so the survey would run without any course "
                   "context. That is fine if it is what you want.")
    c1, c2 = st.columns([2, 1])
    if c1.button(f"Looks right — use these {n_studied} module(s) →", type="primary", width="stretch"):
        if state.modules:
            review.apply_item_rows(state, m, edited_items, pack)   # keep unsaved edits to the open module
        review.confirm_curriculum(state)
        _go("calibration")
    if c2.button("← Add another document", width="stretch"):
        _go("upload")


def page_calibration(state: SessionState) -> None:
    pack = service.pack_for(state)
    cal_cfg = CFG.calibration
    st.title("About you and how you like to work")
    st.caption("Short, fixed questions asked of everyone. Leave anything blank if you are not sure.")
    prev = state.calibration
    values: dict = {}
    fi = cal_cfg["field_interest"]
    anchors = CFG.scales[fi["scale"]]["anchors"]
    st.markdown(f"#### {fi['prompt']}")
    st.caption(f"1 = {anchors[1]} · 5 = {anchors[5]}. {fi['help']}")
    for f in pack.fields:
        c1, c2 = st.columns([5, 4])
        c1.markdown(f"**{f.label}**")
        key = f"{fi['id_prefix']}:{f.id}"
        values[key] = c2.pills(f.label, [1, 2, 3, 4, 5], default=prev.get(key), key=f"w_{key}", label_visibility="collapsed")
    lk = CFG.scales["likert5"]["anchors"]
    st.markdown("#### How far do you agree?")

    def likert(item: dict, optional: bool = False) -> None:
        text = item["text"].format(**pack.phrases)
        st.markdown(f"**{text}**" + ("  \n*" + item["note"] + "*" if optional else ""))
        values[item["id"]] = st.pills(text, [1, 2, 3, 4, 5], format_func=lambda v: lk[v], default=prev.get(item["id"]),
                                      key=f"w_{item['id']}", label_visibility="collapsed")

    for item in cal_cfg["likert_items"]:
        likert(item)
    st.markdown("#### Practical constraints")
    for con in cal_cfg["constraints"]:
        opts = list(con["options"])
        values[con["id"]] = st.radio(con["text"], opts, format_func=con["options"].get, key=f"w_{con['id']}",
                                     index=opts.index(prev[con["id"]]) if prev.get(con["id"]) in opts else None)
    st.markdown("#### Optional")
    st.caption("These are about what you want your research to focus on. They are not a political questionnaire, "
               "and skipping them changes nothing else.")
    for item in cal_cfg["optional_items"]:
        likert(item, optional=True)
    op = cal_cfg["open_prompt"]
    values[op["id"]] = st.text_area(op["text"], value=prev.get(op["id"], ""), help=op["note"], height=80)
    st.caption(op["note"])
    st.divider()
    c1, c2 = st.columns([2, 1])
    if c1.button("Continue to the choices →", type="primary", width="stretch"):
        try:
            service.set_calibration(state, values)
        except ValueError as exc:
            st.error(f"One of the answers could not be saved: {exc}")
            return
        _go("choices")
    if c2.button("← Back", width="stretch"):
        _go("review" if state.modules else "start")


def page_choices(state: SessionState) -> None:
    pack = service.pack_for(state)
    run = service.run_survey(state)
    view = st.session_state.get("view_index")
    if view is not None and view >= len(run.history):
        view = None
        st.session_state.pop("view_index", None)
    if view is None and run.current is None:
        st.title("That is enough to build your shortlist")
        why = {"stable_ranking": "Your leading directions have stopped changing, so more questions would add little.",
               "max_tasks_reached": "You have reached the maximum number of questions for this survey.",
               "no_informative_questions_left": "There are no further informative comparisons to ask."}
        st.markdown(why.get(run.stop_reason or "", ""))
        c1, c2 = st.columns([2, 1])
        if c1.button("See my shortlist →", type="primary", width="stretch"):
            _save(run)
            _go("results")
        if c2.button("← Review my answers", width="stretch") and run.history:
            st.session_state["view_index"] = len(run.history) - 1
            st.rerun()
        return
    spec = run.history[view].spec if view is not None else run.current
    stored = run.history[view].response if view is not None else state.answers.get(spec.id)
    copy = service.question_copy(state, spec, _llm(), st.session_state.setdefault("copy_cache", {}))
    n = spec.step_index + 1
    ad = CFG.adaptive
    st.markdown(f'<div class="dd-kicker">Question {n}</div>', unsafe_allow_html=True)
    st.progress(min((n - 1) / ad["max_tasks"], 1.0))
    st.caption(f"Usually {ad['min_tasks']}–{ad['max_tasks']} questions. It stops earlier once your shortlist settles.")
    if view is not None:
        st.info("You are revisiting an earlier answer. If you change it, later questions may change too and your "
                "results are recalculated from scratch.")
    if spec.explanation:
        st.markdown(f"*{spec.explanation}*")
    if copy.preface:
        st.markdown(f'<span class="dd-chip syll">From your syllabus</span> {copy.preface}', unsafe_allow_html=True)
    st.subheader(copy.prompt)

    pick_key = f"pick_{spec.id}"
    if pick_key not in st.session_state:
        st.session_state[pick_key] = stored.selected_option_id if stored else None
    pick = st.session_state[pick_key]
    cols = st.columns(2)
    for col, oid, letter in zip(cols, spec.display_order, "AB"):
        with col, st.container(border=True):
            st.markdown(f'<div class="dd-rank">Option {letter}{" · selected" if pick == oid else ""}</div>'
                        f'<div class="dd-card-title">{copy.option_titles[oid]}</div>', unsafe_allow_html=True)
            st.markdown(copy.option_blurbs[oid])
            chips = [(note, "syll" if "your module" in note else "") for note in copy.option_notes.get(oid, [])]
            if chips:
                st.markdown(_chips(chips), unsafe_allow_html=True)
            if st.button(f"Choose {letter}", key=f"btn_{spec.id}_{oid}", width="stretch",
                         type="primary" if pick == oid else "secondary"):
                st.session_state[pick_key] = oid
                st.rerun()
    strength = reason = None
    if pick:
        ct = CFG.choice_tasks
        same = stored is not None and stored.selected_option_id == pick
        strength = st.pills("How strongly do you prefer it? (optional)", list(ct["strength_options"]),
                            format_func=ct["strength_options"].get, default=stored.strength if same else None,
                            key=f"str_{spec.id}")
        if spec.template_id == "territory_pair":   # reason codes refer to card attributes, so only ask here
            reason = st.pills("What mainly decided it? (optional)", list(ct["reason_options"]),
                              format_func=ct["reason_options"].get, default=stored.reason_code if same else None,
                              key=f"rsn_{spec.id}")

    def submit(option_id):
        try:
            new_run = service.record_response(state, spec.id, option_id, strength if option_id else None,
                                              reason if option_id else None)
        except ValueError as exc:
            st.error(f"That answer could not be recorded: {exc}")
            return
        st.session_state.pop(pick_key, None)
        if view is not None:
            nxt = view + 1
            if nxt < len(new_run.history):
                st.session_state["view_index"] = nxt
            else:
                st.session_state.pop("view_index", None)
        _save(new_run)
        st.rerun()

    c1, c2, c3 = st.columns([1, 1.4, 1.6])
    if c1.button("← Back", width="stretch", disabled=(view == 0) or (view is None and not run.history)):
        st.session_state["view_index"] = (view - 1) if view is not None else len(run.history) - 1
        st.rerun()
    if CFG.choice_tasks.get("allow_unsure", True):
        if c2.button("Neither / not sure", width="stretch", help="A legitimate answer. It is recorded as "
                     "uncertainty and does not move your scores."):
            submit(None)
    if c3.button("Continue →", type="primary", width="stretch", disabled=not pick):
        submit(pick)
    with st.expander("Why am I being asked this?"):
        base = spec.selection_reason.split(":")[0]
        st.markdown(REASON_TEXT.get(spec.selection_reason) or ("A follow-up to understand a tension between two of "
                    "your earlier answers." if base == "clarify" else spec.selection_reason))
        dims = {d["id"]: d["label"] for d in CFG.dimensions}
        st.caption("Measures: " + ", ".join(dims[d] for d in spec.dimension_ids)
                   + ". The questions, options and scoring are fixed in advance by the survey design; the order "
                     "adapts to your answers using published rules. Task ID: `" + spec.id + "`")
    if run.history and view is None and len(run.history) >= ad["min_tasks"]:
        st.caption("You can stop here if you wish.")
        if st.button("Stop and see my shortlist"):
            _save(run)
            _go("results")


def _result_card(state: SessionState, pack, rec, plan) -> None:
    t = pack.territory(rec.territory_id)
    with st.container(border=True):
        ev_cls = {"Higher evidence": "ok", "Moderate evidence": "", "Limited evidence": "warn"}.get(rec.evidence_label, "warn")
        fam = {"familiar": ("Builds on your modules", "syll"), "adjacent": ("Next to your modules", ""),
               "novel": ("New to your programme", "")}.get(rec.familiarity)
        chips = [(rec.evidence_label, ev_cls)] + ([fam] if fam else []) + (
            [("Feasibility to discuss", "warn")] if rec.feasibility_flag else [])
        st.markdown(f'<div class="dd-rank">#{rec.rank} research territory</div>'
                    f'<div class="dd-card-title">{t.label}</div>'
                    f'<div class="dd-path">{pack.label} → {" → ".join(t.path)}</div>{_chips(chips)}',
                    unsafe_allow_html=True)
        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Why it appears**")
            for r in rec.reasons:
                icon = {"survey": "💬", "syllabus": "📘", "caution": "⚖️"}[r.kind]
                st.markdown(f"{icon} {r.text}")
        with right:
            st.markdown("**At a glance**")
            st.markdown(_meter("Topic-interest fit", rec.components["topic_interest"])
                        + _meter("Methods fit", rec.components["method_fit"])
                        + _meter("Initial feasibility", rec.raw_feasibility)
                        + f'<div class="dd-meter"><span class="lbl">Survey evidence</span><span class="val" '
                          f'style="min-width:auto">{rec.evidence_label}</span></div>', unsafe_allow_html=True)
            st.caption("Bands, not measurements. “Evidence” is how much consistent information your answers gave, "
                       "not a chance of success.")
        if rec.diversity_note:
            st.caption(rec.diversity_note)
        tabs = st.tabs(["Promising angles", "Methods & data to check", "Risks", "Search terms", "Next step"])
        with tabs[0]:
            st.caption("Starting points for reading. Not ready-made questions.")
            for a in t.angles:
                st.markdown(f"- {a}")
        with tabs[1]:
            st.markdown("**Methods to examine**")
            for note in rec.method_notes:
                st.markdown(f"- {note}")
            st.markdown("**Data routes to check** — suggestions, not verified access")
            for d in t.data_routes:
                st.markdown(f"- {d.name} · *{ACCESS_LABEL[d.access]}* — {d.note}")
        with tabs[2]:
            for x in rec.feasibility_notes + t.risks:
                st.markdown(f"- {x}")
        with tabs[3]:
            st.caption("Copy into your library search, EconLit, Scopus, Web of Science or Google Scholar.")
            for s in t.search_strings:
                c1, c2 = st.columns([4, 1])
                c1.code(s, language=None)
                c2.link_button("Scholar ↗", plan.scholar_links[s], width="stretch")
        with tabs[4]:
            st.markdown("Find two credible papers in this territory and check whether the data and methods they use "
                        "would be open to you. The full 60–90 minute exercise is on the next screen.")
            for q in plan.supervisor_prompts[:2] + t.supervisor_questions[:1]:
                st.markdown(f"- *Ask your supervisor:* {q}")


def page_results(state: SessionState) -> None:
    pack = service.pack_for(state)
    run = service.run_survey(state)
    bundle = service.results(state, run)
    st.title("Your shortlist")
    st.markdown("Three **research territories** to investigate, in rank order. They are directions, not titles or "
                "questions: the question comes from your own reading.")
    if run.current is not None:
        st.warning(f"The survey is not finished ({len(run.history)} questions answered), so this shortlist is "
                   "provisional.")
        if st.button("Continue the survey"):
            _go("choices")
    if bundle.overall_notice:
        st.warning(bundle.overall_notice)
    if not bundle.recommendations:
        return
    for rec in bundle.recommendations:
        _result_card(state, pack, rec, bundle.plans[rec.territory_id])
    with st.expander("Compare the three side by side"):
        rows = []
        for rec in bundle.recommendations:
            t = pack.territory(rec.territory_id)
            rows.append({"#": rec.rank, "Territory": t.label, "Topic interest": band(rec.components["topic_interest"]),
                         "Methods fit": band(rec.components["method_fit"]), "Feasibility": band(rec.raw_feasibility),
                         "Evidence": rec.evidence_label, "Usual approach": CFG.attribute_label("approach", t.approach),
                         "Typical data": CFG.attribute_label("data_access", t.data_access)})
        st.dataframe(rows, hide_index=True, width="stretch")
    if bundle.conflicts:
        with st.expander("Trade-offs in your answers"):
            st.caption("Not mistakes: tensions worth thinking about and raising with your supervisor.")
            for c in bundle.conflicts:
                st.markdown(f"- {c}")
    with st.expander("How this was ranked"):
        names = {"topic_interest": "Topic interest (your ratings and choices)", "method_fit": "Methods and style fit",
                 "feasibility": "Initial feasibility", "values_alignment": "Relevance / values alignment",
                 "exploration_fit": "Familiar versus new"}
        st.markdown("Each territory's score is a weighted sum of five components calculated by fixed rules from your "
                    "answers:\n" + "\n".join(f"- {names[k]}: {int(v * 100)}%" for k, v in bundle.weights.items()))
        st.markdown("These weights are **provisional design choices, not calibrated estimates**, and a short survey "
                    "from one person cannot support a statistical model of your preferences. "
                    + ("Course material never raises topic interest: it only informs familiarity, whether typical "
                       "methods were taught, and the explanations. " if state.has_curriculum else
                       "No course material was used, so nothing here refers to modules you have taken. ")
                    + "A territory with low initial feasibility is flagged and marked down. The "
                    "three results are chosen to be distinct, so a close runner-up from the same area may be left "
                    "out. No AI model takes part in question selection or scoring.")
        st.caption(f"Answered {bundle.n_tasks - bundle.n_unsure} choice questions with a preference, "
                   f"{bundle.n_unsure} as unsure. Survey design {state.design_version}, seed {state.random_seed}.")
    st.divider()
    c1, c2 = st.columns([2, 1])
    if c1.button("Get my research plan →", type="primary", width="stretch"):
        _go("handoff")
    if c2.button("← Revise my answers", width="stretch"):
        st.session_state["view_index"] = max(len(run.history) - 1, 0)
        _go_keep_view("choices")


def _go_keep_view(stage: str) -> None:
    view = st.session_state.get("view_index")
    _state().stage = stage
    _save()
    if view is not None:
        st.session_state["view_index"] = view
    st.rerun()


def page_handoff(state: SessionState) -> None:
    pack = service.pack_for(state)
    run = service.run_survey(state)
    bundle = service.results(state, run)
    st.title("Your 60–90 minute research exercise")
    if not bundle.recommendations:
        st.warning(bundle.overall_notice or "No shortlist yet.")
        return
    st.markdown("Do this **before** you settle on a question or meet your supervisor. It is designed to be done by "
                "you: the app does not find the papers or write the question.")
    ids = [r.territory_id for r in bundle.recommendations]
    tid = st.radio("Territory to investigate", ids, horizontal=False,
                   format_func=lambda i: f"#{ids.index(i) + 1}  {pack.territory(i).label}")
    plan, t = bundle.plans[tid], pack.territory(tid)
    st.markdown("#### Checklist")
    for i, s in enumerate(plan.steps, start=1):
        st.checkbox(f"**{i}. {s.title}** · {s.minutes} min", key=f"chk_{tid}_{i}")
        st.markdown(f'<div class="dd-note" style="margin:-.6rem 0 .5rem 1.9rem">{s.detail}</div>', unsafe_allow_html=True)
    st.markdown("#### Search strings to copy")
    for s in plan.search_strings:
        c1, c2 = st.columns([4, 1])
        c1.code(s, language=None)
        c2.link_button("Scholar ↗", plan.scholar_links[s], width="stretch")
    st.markdown("#### Where to search")
    for d in plan.databases:
        if d.get("url"):
            st.markdown(f"- [{d['label']}]({d['url']}) — {d['note']}")
        else:
            st.markdown(f"- **{d['label']}** — {d['note']}")
    st.caption("These are database entry points. The app does not supply article references, so every source you "
               "cite will be one you found and read.")
    st.markdown("#### Data routes to verify")
    for d in t.data_routes:
        st.markdown(f"- {d.name} · *{ACCESS_LABEL[d.access]}* — {d.note}")
    st.markdown("#### Questions for your supervisor")
    for p in plan.supervisor_prompts:
        st.markdown(f"- {p}")
    st.divider()
    st.markdown("#### Take it with you")
    md = export_markdown(state, run, bundle)
    c1, c2 = st.columns(2)
    c1.download_button("Download summary (Markdown)", md, file_name="dissertation-discovery-summary.md",
                       mime="text/markdown", width="stretch", type="primary")
    c2.download_button("Download my answers (JSON)", export_json(state, run),
                       file_name="dissertation-discovery-record.json", mime="application/json", width="stretch")
    with st.expander("Copy the summary as text"):
        st.code(md, language="markdown")
    st.caption("To print or save as PDF, use your browser's print function on this page or on the downloaded summary. "
               "You can come back to this session later with the same link and revise your answers after reading.")
    if st.button("← Back to my shortlist"):
        _go("results")


# ----------------------------------------------------------------------- main ---
def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    state = _state()
    if state.stage not in dict(STAGES) or not _stage_allowed(state.stage, state):
        state.stage = "start"
    sidebar(state)
    {"start": page_start, "upload": page_upload, "review": page_review, "calibration": page_calibration,
     "choices": page_choices, "results": page_results, "handoff": page_handoff}[state.stage](state)
    if st.session_state.get("_save_error"):
        st.caption(f"⚠ Your progress could not be saved to disk ({st.session_state['_save_error']}); "
                   "it is kept for this browser tab only.")


main()
