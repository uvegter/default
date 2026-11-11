"""Student review of the extracted curriculum, and the derived context the survey may use.

Only modules the student has marked completed/current, and only items left
included, ever reach the survey. Coverage is context: it never feeds interest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import (ContentItem, CurriculumExtraction, DisciplinePack, Grounding, Module, SessionState)
from .mapping import map_item, map_module, normalise


# ------------------------------------------------------------ review edits ---
def merge_extraction(state: SessionState, extraction: CurriculumExtraction) -> int:
    """Add extracted modules to the session; merge with an existing module of the same code/title."""
    state.documents.append(extraction.document)
    state.ingest_warnings.extend(extraction.warnings)
    state.flagged_lines.extend(extraction.flagged_lines)
    added = 0
    index = {(m.code or normalise(m.title)): m for m in state.modules}
    for mod in extraction.modules:
        key = mod.code or normalise(mod.title)
        existing = index.get(key)
        if existing is None:
            state.modules.append(mod)
            index[key] = mod
            added += 1
            continue
        seen = {(i.kind, normalise(i.text)) for i in existing.items}
        for item in mod.items:
            if (item.kind, normalise(item.text)) not in seen:
                existing.items.append(item)
        for fid in mod.broad_areas:
            if fid not in existing.broad_areas:
                existing.broad_areas.append(fid)
        existing.credits = existing.credits or mod.credits
        existing.year_or_level = existing.year_or_level or mod.year_or_level
    state.curriculum_confirmed = False   # anything new must be reviewed again
    return added


def add_module(state: SessionState, title: str, pack: DisciplinePack, code: str | None = None,
               status: str = "completed") -> Module:
    mod = Module(title=title.strip(), code=(code or "").strip() or None, status=status,  # type: ignore[arg-type]
                 origin="user", extraction_confidence="user", user_edited=True)
    map_module(mod, pack)
    state.modules.append(mod)
    state.curriculum_confirmed = False
    return mod


def add_item(module: Module, kind: str, text: str, pack: DisciplinePack, parent_id: str | None = None) -> ContentItem:
    item = ContentItem(kind=kind, text=text.strip(), parent_id=parent_id, origin="user",  # type: ignore[arg-type]
                       extraction_confidence="user")
    map_item(item, pack)
    module.items.append(item)
    module.user_edited = True
    return item


def edit_item_text(module: Module, item: ContentItem, text: str, pack: DisciplinePack) -> None:
    """A corrected item becomes the student's own statement; the mapping is recomputed from the new text."""
    if text.strip() == item.text:
        return
    item.text = text.strip()
    item.extraction_confidence = "user"
    if item.kind in ("topic", "subtopic") or item.origin == "user":
        item.taxonomy_ids, item.mapping_confidence = [], {}
    map_item(item, pack)
    module.user_edited = True


def remove_module(state: SessionState, module_id: str) -> None:
    state.modules = [m for m in state.modules if m.id != module_id]


def confirm_curriculum(state: SessionState) -> None:
    state.curriculum_confirmed = True


def clear_curriculum(state: SessionState) -> None:
    state.modules, state.documents = [], []
    state.ingest_warnings, state.flagged_lines = [], []
    state.curriculum_confirmed = False
    state.used_sample_curriculum = False


# ------------------------------------------- applying review-table edits ---
STATUS_LABELS = {"unconfirmed": "Not confirmed", "completed": "Completed", "current": "Taking now",
                 "optional": "Listed as optional", "not_taken": "Not taken"}
ENJOYMENT_LABELS = {"Liked it": "liked", "Disliked it": "disliked"}


def apply_module_rows(state: SessionState, rows: list[dict], order: list[str]) -> bool:
    """Apply the module table (status, code, title, optional liked/disliked) back to the session."""
    by_id = {m.id: m for m in state.modules}
    inv_status = {v: k for k, v in STATUS_LABELS.items()}
    changed = False
    for mid, row in zip(order, rows):
        m = by_id.get(mid)
        if m is None:
            continue
        new_status = inv_status.get(row.get("Status"), m.status)
        new_enjoy = ENJOYMENT_LABELS.get(row.get("How was it? (optional)"))
        new_code = (row.get("Code") or "").strip() or None
        new_title = (row.get("Title") or "").strip() or m.title
        if (new_status, new_enjoy, new_code, new_title) != (m.status, m.enjoyment, m.code, m.title):
            if (new_code, new_title) != (m.code, m.title):
                m.user_edited = True
            m.status, m.enjoyment, m.code, m.title = new_status, new_enjoy, new_code, new_title  # type: ignore[assignment]
            changed = True
    if changed:
        state.curriculum_confirmed = False
    return changed


def apply_item_rows(state: SessionState, module: Module, rows: list[dict], pack: DisciplinePack) -> None:
    """Apply the item editor for one module: include/exclude, retype, reword, add and delete rows."""
    by_id = {i.id: i for i in module.items}
    keep: set[str] = set()
    for row in rows:
        text = (row.get("Text") or "").strip()
        kind = row.get("Type") or "topic"
        iid = row.get("_id")
        if iid and iid in by_id:
            item = by_id[iid]
            keep.add(iid)
            item.included = bool(row.get("Use"))
            if kind != item.kind:
                item.kind, item.taxonomy_ids, item.mapping_confidence = kind, [], {}
                item.extraction_confidence = "user"
                map_item(item, pack)
            if text and text != item.text:
                edit_item_text(module, item, text, pack)
        elif text:
            new = add_item(module, kind, text, pack)
            new.included = row.get("Use") is not False
            keep.add(new.id)
    module.items = [i for i in module.items if i.id in keep]
    map_module(module, pack)
    module.user_edited = True
    state.curriculum_confirmed = False


# -------------------------------------------------------- derived context ---
@dataclass
class CurriculumContext:
    """What the survey is allowed to know about the confirmed curriculum."""

    has_syllabus: bool = False
    territory_links: dict[str, list[Grounding]] = field(default_factory=dict)
    method_links: dict[str, list[Grounding]] = field(default_factory=dict)
    studied_fields: dict[str, list[str]] = field(default_factory=dict)   # field id -> module labels
    familiarity: dict[str, str] = field(default_factory=dict)            # territory id -> familiar|adjacent|novel|unknown

    def familiarity_of(self, territory_id: str) -> str:
        return self.familiarity.get(territory_id, "unknown")


def build_context(state: SessionState, pack: DisciplinePack) -> CurriculumContext:
    ctx = CurriculumContext()
    studied = state.studied_modules           # [] unless the student confirmed the review
    if not studied:
        ctx.familiarity = {t.id: "unknown" for t in pack.territories}
        return ctx
    ctx.has_syllabus = True
    territory_ids = {t.id for t in pack.territories}
    method_ids = {m.id for m in pack.methods}
    for mod in studied:
        for fid in mod.broad_areas:
            ctx.studied_fields.setdefault(fid, []).append(mod.display_label)
        for item in mod.items:
            if not item.included:
                continue
            g = Grounding(module_id=mod.id, module_label=mod.display_label, item_id=item.id, item_text=item.text,
                          item_kind=item.kind, excerpt=item.evidence.excerpt if item.evidence else "",
                          page=item.evidence.page if item.evidence else None)
            if item.kind in ("topic", "subtopic"):
                for tid in item.taxonomy_ids:
                    if tid in territory_ids:
                        ctx.territory_links.setdefault(tid, []).append(g)
            elif item.kind == "method":
                for mid in item.taxonomy_ids:
                    if mid in method_ids:
                        ctx.method_links.setdefault(mid, []).append(g)
    # Prefer the most specific evidence first (subtopics, then high-confidence mappings).
    for links in ctx.territory_links.values():
        links.sort(key=lambda g: (g.item_kind != "subtopic", len(g.item_text)))
    for t in pack.territories:
        if t.id in ctx.territory_links:
            ctx.familiarity[t.id] = "familiar"
        elif t.field in ctx.studied_fields or any(a in ctx.territory_links for a in t.adjacent):
            ctx.familiarity[t.id] = "adjacent"
        else:
            ctx.familiarity[t.id] = "novel"
    return ctx
