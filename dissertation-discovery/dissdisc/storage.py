"""SQLite persistence for development sessions.

What is stored: the session's structured state (reviewed module records with
short source excerpts, calibration answers, choice responses, question specs,
selection log). What is NOT stored: uploaded files or their full text.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from .config import ROOT
from .models import SessionState, SurveyRun, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, discipline TEXT, design_version TEXT, pack_version TEXT, random_seed INTEGER,
    stage TEXT, created_at TEXT, updated_at TEXT, state_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY, session_id TEXT, original_filename TEXT, sha256 TEXT, media_type TEXT,
    parse_status TEXT, extractor TEXT, n_chars INTEGER, uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS questions (
    session_id TEXT, question_id TEXT, step_index INTEGER, template_id TEXT, design_version TEXT,
    dimension_ids TEXT, option_ids TEXT, display_order TEXT, attribute_payload TEXT, source_grounding TEXT,
    selection_reason TEXT, selection_detail TEXT, PRIMARY KEY (session_id, question_id));
CREATE TABLE IF NOT EXISTS responses (
    id TEXT PRIMARY KEY, session_id TEXT, question_id TEXT, selected_option_id TEXT, strength TEXT,
    reason_code TEXT, uncertainty_flag INTEGER, active INTEGER, created_at TEXT);
"""


def default_db_path() -> Path:
    return Path(os.environ.get("DD_DB_PATH", ROOT / "data" / "sessions.sqlite3"))


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = sqlite3.connect(":memory:", check_same_thread=False) if str(self.path) == ":memory:" else None
        with closing(self._conn()) as c:
            c.executescript(SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        if self._memory is not None:
            return _NoClose(self._memory)  # type: ignore[return-value]
        return sqlite3.connect(self.path, check_same_thread=False)

    def save(self, state: SessionState, run: SurveyRun | None = None) -> None:
        with closing(self._conn()) as c:
            c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
                      (state.id, state.discipline_id, state.design_version, state.pack_version, state.random_seed,
                       state.stage, state.created_at, now_iso(), state.model_dump_json()))
            c.execute("DELETE FROM documents WHERE session_id=?", (state.id,))
            c.executemany("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?,?)",
                          [(d.id, state.id, d.original_filename, d.sha256, d.media_type, d.parse_status, d.extractor,
                            d.n_chars, d.uploaded_at) for d in state.documents])
            c.execute("DELETE FROM responses WHERE session_id=?", (state.id,))
            active = {r.id for r in state.answers.values()}
            c.executemany("INSERT OR REPLACE INTO responses VALUES (?,?,?,?,?,?,?,?,?)",
                          [(r.id, state.id, r.question_id, r.selected_option_id, r.strength, r.reason_code,
                            int(r.uncertainty_flag), int(r.id in active), r.created_at) for r in state.response_log])
            if run is not None:
                c.execute("DELETE FROM questions WHERE session_id=?", (state.id,))
                specs = [h.spec for h in run.history] + ([run.current] if run.current else [])
                c.executemany("INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
                    (state.id, s.id, s.step_index, s.template_id, s.design_version, json.dumps(s.dimension_ids),
                     json.dumps([o.id for o in s.options]), json.dumps(s.display_order),
                     json.dumps({o.id: {"attributes": o.attributes, "signals": o.signals} for o in s.options}),
                     json.dumps([g.model_dump() for g in s.grounding]), s.selection_reason,
                     json.dumps(s.selection_detail)) for s in specs])
            c.commit()

    def load(self, session_id: str) -> SessionState | None:
        with closing(self._conn()) as c:
            row = c.execute("SELECT state_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            return None
        try:
            return SessionState.model_validate_json(row[0])
        except Exception:
            return None

    def delete(self, session_id: str) -> None:
        with closing(self._conn()) as c:
            for table in ("sessions", "documents", "questions", "responses"):
                col = "id" if table == "sessions" else "session_id"
                c.execute(f"DELETE FROM {table} WHERE {col}=?", (session_id,))
            c.commit()

    def count(self, table: str, session_id: str) -> int:
        col = "id" if table == "sessions" else "session_id"
        with closing(self._conn()) as c:
            return c.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=?", (session_id,)).fetchone()[0]


class _NoClose:
    """Wrap a shared in-memory connection so `closing()` does not close it."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        pass
