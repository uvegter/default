"""Deterministic syllabus extraction: page text -> structured modules.

Heading/section heuristics only; no model call. Every extracted claim carries
the source line it came from. Lines that look like instructions to an AI system
are dropped and reported (uploaded documents are untrusted data).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import ContentItem, CurriculumExtraction, DisciplinePack, Module, SourceEvidence
from .ingest import DecodedText
from .mapping import map_module, matcher_for, normalise

CODE = r"[A-Z]{2,6}[ -]?\d{3,5}[A-Z]?"
RE_CODE_TITLE = re.compile(rf"^(?:Module\s*[:\-–]?\s*)?(?P<code>{CODE})\s*[:\-–—]?\s+(?P<title>[A-Z][^\n]{{2,110}})$")
RE_TITLE_LINE = re.compile(r"^(?:module|course|unit)\s*(?:title|name)?\s*[:\-–]\s*(?P<title>.+)$", re.I)
RE_CODE_LINE = re.compile(rf"^(?:module|course|unit)\s*code\s*[:\-–]\s*(?P<code>{CODE})\s*$", re.I)
RE_CREDITS = re.compile(r"(\d{1,3})\s*(?:credits?|ects|cats)\b", re.I)
RE_CREDITS_LINE = re.compile(r"^credits?(?:\s*value)?\s*[:\-–]\s*(\d{1,3})\b", re.I)
RE_LEVEL = re.compile(r"\b(?:(year|level|stage)\s*[:\-–]?\s*(\d)\b|(first|second|third|final)[- ]year)", re.I)
RE_BULLET = re.compile(r"^[-•*·–▪○●◦]\s+")
RE_NUMBERED = re.compile(r"^\(?\d{1,2}[.)]\s+")
RE_UNIT_PREFIX = re.compile(
    r"^(?:weeks?|lectures?|topic|unit|session|part|block|seminar)\s*\d+(?:\s*(?:[-–&,]|and|to)\s*\d+)*\s*[:.\-–)]*\s*", re.I
)
RE_TRAILING_NUM = re.compile(r"\s+(\d{1,3})\s*$")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

SECTION_CONTENT = ("module content", "syllabus", "indicative content", "indicative syllabus", "topics", "topics covered",
                   "outline", "module outline", "content", "course content", "weekly schedule", "lecture schedule",
                   "lecture programme", "what you will study", "outline content", "syllabus content", "lecture topics")
SECTION_OUTCOMES = ("learning outcomes", "intended learning outcomes", "module learning outcomes", "on completion",
                    "objectives", "module objectives", "aims", "module aims", "aims and objectives")
SECTION_METHODS = ("methods", "methods and skills", "skills", "techniques", "skills outcomes", "methods taught",
                   "quantitative methods", "research methods taught")
SECTION_OVERVIEW = ("overview", "module overview", "summary", "module summary", "description", "module description",
                    "introduction", "about this module")
SECTION_IGNORE = ("assessment", "assessments", "assessment methods", "methods of assessment", "reading", "reading list",
                  "key reading", "indicative reading", "recommended reading", "essential reading", "bibliography",
                  "prerequisites", "pre-requisites", "pre-requisite", "prerequisite", "co-requisites", "corequisites",
                  "teaching", "teaching methods", "teaching and learning", "teaching and learning methods",
                  "learning and teaching", "contact hours", "private study", "staff", "module leader", "module leaders",
                  "module convenor", "module manager", "lecturer", "lecturers", "tutor", "tutors", "timetable",
                  "contact", "contact details", "office hours", "email", "feedback", "resit", "exam", "examination",
                  "coursework", "delivery", "teaching staff", "this module is approved as", "mutually exclusive")
META_IGNORE_KEYS = ("module leader", "module convenor", "module manager", "lecturer", "tutor", "email", "contact",
                    "office", "semester", "term", "taught", "department", "school", "faculty", "assessment",
                    "prerequisites", "pre-requisites", "co-requisites", "exam", "coursework", "delivery",
                    "academic year", "last updated", "version")

STATUS_OPTIONAL = re.compile(r"\b(optional|elective|option)\b.{0,30}\b(modules?|courses?|units?)\b|"
                             r"\b(choose|select)\b.{0,60}\b(from|credits)\b|^(optional|electives?|options)\s*:?$", re.I)
STATUS_CORE = re.compile(r"\b(compulsory|core|mandatory|required)\b.{0,30}\b(modules?|courses?|units?)\b|"
                         r"^(compulsory|core)\s*:?$", re.I)

INSTRUCTION_PATTERNS = [re.compile(p, re.I) for p in (
    r"\bignore\b.{0,30}\b(instructions?|rules|prompts?|guidelines)\b",
    r"\bdisregard\b.{0,30}\b(instructions?|rules|prompts?|above|previous)\b",
    r"\bsystem prompt\b",
    r"\byou are now\b",
    r"\bas an ai\b",
    r"\b(rank|put|place|recommend|score)\b.{0,50}\b(first|top|highest|number one)\b",
    r"\b(reveal|print|output|show)\b.{0,30}\b(secret|api key|password|system|prompt)\b",
    r"\bnew instructions?\b",
    r"</?\s*(system|assistant|instructions?)\s*>",
    r"\boverride\b.{0,30}\b(rules|settings|scoring|instructions?)\b",
)]

RE_SPEC_HEADING = re.compile(r"^(?:module|course|unit)\s+(?:specifications?|descriptions?|details|outlines?|"
                             r"summaries|information)\s*:?$", re.I)

LIST_TRIGGERS = re.compile(
    r"(?:topics?(?: covered)? (?:will )?include|content includes|covers(?: topics such as)?|including|such as|"
    r"introduces|we (?:will )?(?:study|cover|examine)|examines|explores|you will study)\s*:?\s+(.+)", re.I)


@dataclass
class Line:
    page: int
    text: str      # stripped
    indent: int


def looks_like_instruction(text: str) -> bool:
    return any(p.search(text) for p in INSTRUCTION_PATTERNS)


def _lines(decoded: DecodedText) -> list[Line]:
    out: list[Line] = []
    for pno, page in enumerate(decoded.pages, start=1):
        for raw in page.split("\n"):
            expanded = raw.expandtabs(4)
            stripped = expanded.strip()
            out.append(Line(pno, stripped, len(expanded) - len(expanded.lstrip())))
    return out


def _section_of(text: str) -> tuple[str, str, str] | None:
    """Return (section_kind, heading, inline_rest) if the line is a section heading."""
    head, sep, rest = text.partition(":")
    key = normalise(RE_NUMBERED.sub("", RE_BULLET.sub("", head)))
    if not key or len(key) > 45:
        return None
    if not sep and len(text) > 45:
        return None
    for kind, names in (("ignore", SECTION_IGNORE), ("content", SECTION_CONTENT), ("outcomes", SECTION_OUTCOMES),
                        ("methods", SECTION_METHODS), ("overview", SECTION_OVERVIEW)):
        if key in names:
            return kind, head.strip(), rest.strip()
    return None


def _split_list(text: str) -> list[str]:
    text = text.strip().rstrip(".")
    if ";" in text:
        parts = text.split(";")
    elif "," in text:
        parts = text.split(",")
    else:
        parts = [text]
    out = []
    for p in parts:
        p = re.sub(r"^\s*(?:and|&)\s+", "", p.strip(), flags=re.I).strip(" .")
        if p:
            out.append(p)
    return out


def _clean_title(title: str) -> tuple[str, str | None]:
    """Strip trailing credit info from a title; return (title, credits)."""
    credits = None
    m = re.search(r"\(([^)]*)\)\s*$", title)
    if m and RE_CREDITS.search(m.group(1)):
        credits = RE_CREDITS.search(m.group(1)).group(1)
        title = title[: m.start()]
    else:
        m2 = RE_CREDITS.search(title)
        if m2 and m2.end() >= len(title.rstrip()) - 1:
            credits = m2.group(1)
            title = title[: m2.start()]
        else:
            m3 = RE_TRAILING_NUM.search(title)
            if m3:
                credits = m3.group(1)
                title = title[: m3.start()]
    return title.strip(" -–—:|,").strip(), credits


def _level_from(text: str) -> str | None:
    m = RE_LEVEL.search(text)
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1).capitalize()} {m.group(2)}"
    return f"{m.group(3).capitalize()} year"


class _Builder:
    def __init__(self, pack: DisciplinePack, document_id: str):
        self.pack = pack
        self.matcher = matcher_for(pack)
        self.document_id = document_id
        self.modules: list[Module] = []
        self.flagged: list[str] = []
        self.current: Module | None = None
        self.section = "header"
        self.section_heading: str | None = None
        self.last_topic: ContentItem | None = None
        self.last_topic_indent = 0
        self.status_hint = "unknown"
        self.level_hint: str | None = None
        self.pending_code: str | None = None
        self._seen: set[tuple[str, str, str]] = set()

    # -- helpers -----------------------------------------------------------
    def evidence(self, line: Line) -> SourceEvidence:
        return SourceEvidence(document_id=self.document_id, page=line.page, heading=self.section_heading,
                              excerpt=RE_EMAIL.sub("[email removed]", line.text)[:240])

    def start_module(self, line: Line, title: str, code: str | None, credits: str | None = None) -> None:
        level = _level_from(line.text) or self.level_hint
        if code and not level:
            digits = re.search(r"\d", code)
            # Many UK codes encode the level in the first digit; too unreliable to assert, so leave empty.
            _ = digits
        code = code.replace(" ", "").replace("-", "") if code else None
        # A catalogue often lists a module and later gives its full specification: merge, don't duplicate.
        for existing in self.modules:
            same = (code and existing.code == code) or (not code and normalise(existing.title) == normalise(title))
            if same:
                existing.credits = existing.credits or credits
                existing.year_or_level = existing.year_or_level or level
                self.current, self.section, self.section_heading = existing, "header", None
                self.last_topic, self.pending_code = None, None
                return
        mod = Module(document_id=self.document_id, code=code, title=title,
                     credits=credits, year_or_level=level, listed_as=self.status_hint,  # type: ignore[arg-type]
                     status="optional" if self.status_hint == "optional" else "unconfirmed",
                     evidence=self.evidence(line), extraction_confidence="medium")
        self.modules.append(mod)
        self.current = mod
        self.section = "header"
        self.section_heading = None
        self.last_topic = None
        self.pending_code = None

    def add(self, kind: str, text: str, line: Line, conf: str = "high", parent: ContentItem | None = None,
            taxonomy_ids: list[str] | None = None) -> ContentItem | None:
        assert self.current is not None
        text = text.strip(" \t-–•*·.;:,")
        if len(text) < 3 or not re.search(r"[A-Za-z]{3}", text):
            return None
        key = (self.current.id, kind, normalise(text) if not taxonomy_ids else ",".join(taxonomy_ids))
        if key in self._seen:
            return None
        self._seen.add(key)
        item = ContentItem(kind=kind, text=text, parent_id=parent.id if parent else None,  # type: ignore[arg-type]
                           evidence=self.evidence(line), extraction_confidence=conf,  # type: ignore[arg-type]
                           taxonomy_ids=taxonomy_ids or [],
                           mapping_confidence={t: "high" for t in (taxonomy_ids or [])})
        self.current.items.append(item)
        return item

    def scan_lexicon(self, line: Line, conf: str) -> None:
        for mid in self.matcher.methods(line.text):
            self.add("method", self.pack.method(mid).label, line, conf, taxonomy_ids=[mid])
        theory_index = {t.id: t for t in self.pack.theories}
        for tid in self.matcher.theories(line.text):
            self.add("theory", theory_index[tid].label, line, conf, taxonomy_ids=[tid])

    # -- line handlers -----------------------------------------------------
    def content_line(self, line: Line, text: str) -> None:
        bulleted = bool(RE_BULLET.match(text) or RE_NUMBERED.match(text))
        body = RE_UNIT_PREFIX.sub("", RE_NUMBERED.sub("", RE_BULLET.sub("", text))).strip()
        if not body:
            return
        # Nested bullet => subtopic of the previous topic.
        if bulleted and self.last_topic is not None and line.indent > self.last_topic_indent:
            for part in _split_list(body) if len(body) > 60 and (";" in body) else [body]:
                self.add("subtopic", part, line, "high", parent=self.last_topic)
            return
        if len(body) > 170 or (body.count(" ") > 16 and body.endswith(".")):
            self.prose_line(line, body, in_content=True)
            return
        head, tail = body, ""
        for sep in (":", " – ", " — ", " - "):
            if sep in body:
                head, tail = body.split(sep, 1)
                break
        else:
            m = re.match(r"^(.*?)\s*\(([^)]{6,})\)\s*\.?$", body)
            if m:
                head, tail = m.group(1), m.group(2)
        head = head.strip()
        if not tail and not bulleted and ("," in body or ";" in body) and len(_split_list(body)) >= 3:
            # A bare comma list on one line: each element is a topic.
            for part in _split_list(body):
                self.add("topic", part, line, "medium")
            self.last_topic = None
            return
        topic = self.add("topic", head, line, "high")
        if topic is not None:
            self.last_topic, self.last_topic_indent = topic, line.indent
        if tail and topic is not None:
            for part in _split_list(tail):
                self.add("subtopic", part, line, "high", parent=topic)

    def prose_line(self, line: Line, text: str, in_content: bool = False) -> None:
        """Free-text description: only pull out explicit lists ('topics include a, b and c')."""
        assert self.current is not None
        has_structured = any(i.kind == "topic" and i.extraction_confidence == "high" for i in self.current.items)
        if has_structured and not in_content:
            return
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            m = LIST_TRIGGERS.search(sentence)
            if not m:
                continue
            parts = _split_list(re.sub(r"\s+and\s+", ", ", m.group(1)))
            for part in parts:
                if 1 <= len(part.split()) <= 9:
                    self.add("topic", part, line, "medium")

    def feed(self, line: Line, prev_blank: bool) -> None:
        text = line.text
        if not text:
            return
        if looks_like_instruction(text):
            self.flagged.append(text[:200])
            return
        # Document-level hints (apply whether or not a module is open).
        if STATUS_OPTIONAL.search(text) and len(text) < 120:
            self.status_hint = "optional"
            if not RE_CODE_TITLE.match(text):
                self._close_if_listing()
                return
        elif STATUS_CORE.search(text) and len(text) < 120:
            self.status_hint = "core"
            if not RE_CODE_TITLE.match(text):
                self._close_if_listing()
                return
        if len(text) < 60 and RE_SPEC_HEADING.match(text):
            self.status_hint = "unknown"
            self._close_if_listing()
            return
        if len(text) < 40 and RE_LEVEL.fullmatch(text.strip(" :-–")):
            self.level_hint = _level_from(text)
            return

        in_prereq = self.section == "ignore" and self.section_heading and "requisite" in self.section_heading.lower()
        # --- module headers ---
        m = RE_CODE_TITLE.match(text) if not in_prereq else None
        if m and not text.endswith(".") and len(m.group("title").split()) <= 14:
            title, credits = _clean_title(m.group("title"))
            if title and not _section_of(title):
                self.start_module(line, title, m.group("code"), credits)
                return
        m = RE_CODE_LINE.match(text)
        if m:
            if self.current is not None and self.current.code is None and not self.current.items:
                self.current.code = m.group("code").replace(" ", "")
            else:
                self.pending_code = m.group("code")
            return
        m = RE_TITLE_LINE.match(text)
        if m and not _section_of(text) and not re.match(r"^(module|course|unit)\s*(code|leader|convenor|content|outline|"
                                                      r"aims|summary|overview|description|learning|objectives|manager)",
                                                      text, re.I):
            title, credits = _clean_title(m.group("title"))
            cm = re.match(rf"^({CODE})\s*[:\-–—]?\s+(.*)$", title)
            code = self.pending_code
            if cm:
                code, title = cm.group(1), cm.group(2)
            if title:
                self.start_module(line, title, code, credits)
                return
        if self.current is None:
            return

        # --- section headings ---
        sec = _section_of(text)
        if sec:
            self.section, self.section_heading, rest = sec
            self.last_topic = None
            if rest and self.section != "ignore":
                self.dispatch(line, rest)
            return
        # --- metadata lines in the header area ---
        if self.section in ("header", "overview"):
            cm = RE_CREDITS_LINE.match(text)
            if cm:
                self.current.credits = cm.group(1)
                return
            key = normalise(text.split(":", 1)[0]) if ":" in text else ""
            if key in ("level", "year", "stage", "year of study", "level of study"):
                self.current.year_or_level = _level_from(text) or text.split(":", 1)[1].strip()[:20]
                return
            if key and any(key.startswith(k) for k in META_IGNORE_KEYS):
                return
            if not self.current.credits and RE_CREDITS.search(text) and len(text) < 60:
                self.current.credits = RE_CREDITS.search(text).group(1)
                return
        if self.section == "ignore":
            return
        self.dispatch(line, text)

    def dispatch(self, line: Line, text: str) -> None:
        if self.section == "content":
            self.content_line(line, text)
            self.scan_lexicon(line, "high")
        elif self.section == "outcomes":
            body = RE_NUMBERED.sub("", RE_BULLET.sub("", text)).strip()
            if len(body) >= 15 and not body.endswith(":"):
                self.add("outcome", body[:300], line, "high")
            self.scan_lexicon(line, "high")
        elif self.section == "methods":
            self.scan_lexicon(line, "high")
        else:  # header / overview prose
            self.prose_line(line, text)
            self.scan_lexicon(line, "medium")

    def _close_if_listing(self) -> None:
        """A status heading ends the previous module block."""
        self.current = None
        self.section = "header"


def extract_curriculum(decoded: DecodedText, pack: DisciplinePack) -> CurriculumExtraction:
    """Deterministic extraction. Returns modules with status 'unconfirmed' (or 'optional' when listed as such)."""
    doc = decoded.document
    result = CurriculumExtraction(document=doc)
    if not decoded.ok:
        result.warnings.append(doc.message)
        return result
    if decoded.csv_rows is not None:
        result.modules = _from_csv(decoded, pack)
    else:
        b = _Builder(pack, doc.id)
        prev_blank = True
        for line in _lines(decoded):
            b.feed(line, prev_blank)
            prev_blank = not line.text
        result.modules = b.modules
        result.flagged_lines = b.flagged
        if not b.modules:
            fallback = _fallback_module(decoded, pack, b)
            if fallback is not None:
                result.modules = [fallback]
                result.warnings.append(
                    "No module headings were recognised, so the text has been treated as one module. "
                    "Please check its title and contents.")
    for mod in result.modules:
        map_module(mod, pack)
        has_content = bool(mod.of_kind("topic", "subtopic"))
        if mod.extraction_confidence != "low":
            mod.extraction_confidence = "high" if (mod.code and has_content) else "medium"
    doc.extractor = "deterministic"
    if result.flagged_lines:
        result.warnings.append(
            f"{len(result.flagged_lines)} line(s) looked like instructions rather than course content and were ignored.")
    if not result.modules:
        result.warnings.append(
            "No modules could be identified in this document. You can paste module descriptions, "
            "or add modules by hand on the review screen.")
    n_optional = sum(1 for m in result.modules if m.listed_as == "optional")
    if len(result.modules) >= 12 or n_optional:
        result.warnings.append(
            "This looks like a programme catalogue. Nothing is treated as studied until you mark it "
            "as completed or current.")
    return result


def _fallback_module(decoded: DecodedText, pack: DisciplinePack, b: _Builder) -> Module | None:
    lines = [l for l in _lines(decoded) if l.text and not looks_like_instruction(l.text)]
    if not lines:
        return None
    first = lines[0].text
    title = first if len(first) <= 80 and not first.endswith(".") else "Untitled module (please rename)"
    mod = Module(document_id=decoded.document.id, title=title, extraction_confidence="low", evidence=b.evidence(lines[0]))
    b.modules.append(mod)
    b.current = mod
    b.section = "content"
    for line in lines[1 if title == first else 0:]:
        sec = _section_of(line.text)
        if sec:
            b.section, b.section_heading, rest = sec
            if rest and b.section != "ignore":
                b.dispatch(line, rest)
            continue
        if b.section != "ignore":
            b.dispatch(line, line.text)
    for item in mod.items:
        if item.kind in ("topic", "subtopic"):
            item.extraction_confidence = "low"
    b.modules.remove(mod)
    return mod if mod.items else None


def _from_csv(decoded: DecodedText, pack: DisciplinePack) -> list[Module]:
    modules: list[Module] = []
    status_map = {"completed": "completed", "taken": "completed", "current": "current", "optional": "optional",
                  "not taken": "not_taken", "not_taken": "not_taken"}
    matcher = matcher_for(pack)
    for n, row in enumerate(decoded.csv_rows or [], start=2):
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        title = r.get("title") or r.get("module") or r.get("module title") or r.get("name")
        if not title or looks_like_instruction(" ".join(r.values())):
            continue
        ev = SourceEvidence(document_id=decoded.document.id, page=1, heading=f"CSV row {n}",
                            excerpt="; ".join(f"{k}={v}" for k, v in r.items() if v)[:240])
        mod = Module(document_id=decoded.document.id, code=(r.get("code") or r.get("module code") or None), title=title,
                     year_or_level=r.get("year") or r.get("level") or r.get("year_or_level") or None,
                     credits=r.get("credits") or None, evidence=ev,
                     status=status_map.get(r.get("status", "").lower(), "unconfirmed"))  # type: ignore[arg-type]
        for kind, col in (("topic", "topics"), ("subtopic", "subtopics"), ("outcome", "learning_outcomes")):
            for part in [p.strip() for p in r.get(col, "").split(";") if p.strip()]:
                mod.items.append(ContentItem(kind=kind, text=part, evidence=ev, extraction_confidence="high"))  # type: ignore[arg-type]
        for part in [p.strip() for p in r.get("methods", "").split(";") if p.strip()]:
            ids = matcher.methods(part)
            mod.items.append(ContentItem(kind="method", text=part, evidence=ev, extraction_confidence="high",
                                         taxonomy_ids=ids, mapping_confidence={i: "high" for i in ids}))
        modules.append(mod)
    return modules
