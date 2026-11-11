"""Review-table edits and a headless click-through of the Streamlit app (no browser, no API key)."""
from pathlib import Path

import pytest

from dissdisc import service
from dissdisc.curriculum import review

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_review_table_edits_are_applied(pack, state_with_syllabus):
    st = state_with_syllabus
    lab = next(m for m in st.modules if m.code == "ECON2110")
    macro = next(m for m in st.modules if m.code == "ECON2020")
    rows = [{"Status": "Not taken", "Code": "ECON2110", "Title": "Labour Economics", "How was it? (optional)": "—"},
            {"Status": "Completed", "Code": "ECON2020", "Title": "Macro II", "How was it? (optional)": "Liked it"}]
    assert review.apply_module_rows(st, rows, [lab.id, macro.id])
    assert lab.status == "not_taken" and macro.title == "Macro II" and macro.enjoyment == "liked"
    assert not st.curriculum_confirmed
    assert not review.apply_module_rows(st, rows, [lab.id, macro.id])          # idempotent
    items = [{"_id": i.id, "Use": i.included, "Type": i.kind, "Text": i.text} for i in macro.items]
    items[0]["Use"] = False                                                    # exclude
    items[1]["Text"] = "Minimum wages and monopsony"                           # reword -> remapped
    removed = items.pop(2)                                                     # delete a row
    items.append({"_id": None, "Use": True, "Type": "method", "Text": "Vector autoregression"})   # add a row
    review.apply_item_rows(st, macro, items, pack)
    by_id = {i.id: i for i in macro.items}
    assert by_id[items[0]["_id"]].included is False
    assert by_id[items[1]["_id"]].taxonomy_ids == ["lab_min_wage"] and by_id[items[1]["_id"]].extraction_confidence == "user"
    assert removed["_id"] not in by_id
    added = macro.items[-1]
    assert added.origin == "user" and added.taxonomy_ids == ["m_timeseries"] and added.evidence is None


def _click(at, label_part: str):
    btn = next(b for b in at.button if label_part in b.label)
    return btn.click().run()


def test_app_click_through_without_syllabus(tmp_path, monkeypatch):
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.setenv("DD_DB_PATH", str(tmp_path / "ui.sqlite3"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception and any("Find a dissertation direction" in t.value for t in at.title)
    at = _click(at, "Continue without a syllabus")
    assert not at.exception and "how you like to work" in at.title[0].value
    at = _click(at, "Continue to the choices")
    assert not at.exception
    for _ in range(30):
        if any("See my shortlist" in b.label for b in at.button):
            break
        at = _click(at, "Choose A")
        at = _click(at, "Continue")
        assert not at.exception
    at = _click(at, "See my shortlist")
    assert not at.exception and at.title[0].value == "Your shortlist"
    text = " ".join(m.value for m in at.markdown)
    assert text.count("research territory</div>") == 3
    assert "your syllabus" not in text.lower() and "confirmed module" not in text.lower()
    at = _click(at, "Get my research plan")
    assert not at.exception and "60–90 minute" in at.title[0].value
    state = at.session_state["state"]
    assert len(state.answers) >= 10 and service.results(state).recommendations


def test_app_sample_syllabus_review_screen(tmp_path, monkeypatch):
    AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
    monkeypatch.setenv("DD_DB_PATH", str(tmp_path / "ui.sqlite3"))
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = _click(at, "Try with a sample syllabus")
    assert not at.exception and at.title[0].value == "Check what we found"
    assert [m.value for m in at.metric] == ["41", "6", "8"]
    at = _click(at, "Looks right")
    assert not at.exception and at.session_state["state"].curriculum_confirmed
