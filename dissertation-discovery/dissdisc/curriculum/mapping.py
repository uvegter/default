"""Deterministic mapping of course text onto the controlled taxonomy.

Keyword/synonym matching only. A match says "this text mentions X"; it never
says the student is interested in X or competent at it.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..models import ContentItem, DisciplinePack, Module

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9&]+")


def normalise(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    return _WS.sub(" ", _NON_ALNUM.sub(" ", text.lower().replace("’", "'"))).strip()


def _kw_regex(keyword: str) -> re.Pattern[str]:
    kw = re.escape(normalise(keyword)).replace(r"\ ", " ")
    return re.compile(rf"(?<![a-z0-9]){kw}(?:s|es)?(?![a-z0-9])")


def _cs_regex(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])")


class TaxonomyMatcher:
    def __init__(self, pack: DisciplinePack):
        self.pack = pack
        self._territory = [(t.id, [(k, _kw_regex(k)) for k in t.keywords]) for t in pack.territories]
        self._field = [(f.id, [_kw_regex(k) for k in f.keywords]) for f in pack.fields]
        self._method = [
            (m.id, [_kw_regex(k) for k in m.keywords], [_cs_regex(k) for k in m.keywords_cs]) for m in pack.methods
        ]
        self._theory = [(t.id, [_kw_regex(k) for k in t.keywords]) for t in pack.theories]

    def territories(self, text: str) -> dict[str, str]:
        """territory id -> mapping confidence ('high' | 'medium')."""
        norm = normalise(text)
        out: dict[str, str] = {}
        for tid, kws in self._territory:
            hits = [k for k, rx in kws if rx.search(norm)]
            if not hits:
                continue
            strong = len(hits) >= 2 or any(" " in normalise(k) for k in hits)
            out[tid] = "high" if strong else "medium"
        return out

    def fields(self, text: str) -> list[str]:
        norm = normalise(text)
        return [fid for fid, rxs in self._field if any(rx.search(norm) for rx in rxs)]

    def methods(self, text: str) -> list[str]:
        norm = normalise(text)
        return [
            mid
            for mid, rxs, cs in self._method
            if any(rx.search(norm) for rx in rxs) or any(rx.search(text) for rx in cs)
        ]

    def theories(self, text: str) -> list[str]:
        norm = normalise(text)
        return [tid for tid, rxs in self._theory if any(rx.search(norm) for rx in rxs)]


@lru_cache(maxsize=8)
def _cached_matcher(pack_id: str, pack_version: str) -> TaxonomyMatcher:
    from ..config import load_pack

    return TaxonomyMatcher(load_pack(pack_id))


def matcher_for(pack: DisciplinePack) -> TaxonomyMatcher:
    try:
        return _cached_matcher(pack.id, pack.pack_version)
    except KeyError:   # ad-hoc pack built in tests
        return TaxonomyMatcher(pack)


def map_item(item: ContentItem, pack: DisciplinePack) -> ContentItem:
    """(Re)compute taxonomy IDs for one content item from its text."""
    m = matcher_for(pack)
    if item.kind in ("topic", "subtopic"):
        found = m.territories(item.text)
        item.taxonomy_ids = list(found)
        item.mapping_confidence = dict(found)
    elif item.kind == "method":
        ids = m.methods(item.text)
        if ids or item.origin == "user":
            item.taxonomy_ids = ids
            item.mapping_confidence = {i: "high" for i in ids}
    elif item.kind == "theory":
        ids = m.theories(item.text)
        if ids or item.origin == "user":
            item.taxonomy_ids = ids
            item.mapping_confidence = {i: "high" for i in ids}
    return item


def map_module(module: Module, pack: DisciplinePack) -> Module:
    """Map every item and derive the module's broad areas (field IDs)."""
    m = matcher_for(pack)
    for item in module.items:
        if item.kind in ("topic", "subtopic") or not item.taxonomy_ids:
            map_item(item, pack)
    areas = list(m.fields(module.title))
    counts: dict[str, int] = {}
    territory_index = {t.id: t.field for t in pack.territories}
    for tid in m.territories(module.title):         # e.g. "Economics of Migration", "Health Economics"
        if territory_index[tid] not in areas:
            areas.append(territory_index[tid])
    content = module.of_kind("topic", "subtopic")
    for item in content:
        for fid in {territory_index[t] for t in item.taxonomy_ids if t in territory_index}:
            counts[fid] = counts.get(fid, 0) + 1
    threshold = max(2, round(0.25 * len(content)))
    for fid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if n >= threshold and fid not in areas:
            areas.append(fid)
    # Keep any area the student set by hand.
    for fid in module.broad_areas:
        if module.user_edited and fid not in areas:
            areas.append(fid)
    module.broad_areas = areas
    return module
