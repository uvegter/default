"""Typed domain models (Pydantic). No UI or framework imports here."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------- catalogue ---
class FieldNode(BaseModel):
    id: str
    label: str
    keywords: list[str] = []
    adjacent: list[str] = []


class MethodNode(BaseModel):
    id: str
    label: str
    group: str  # approach group: quant_empirical | theory_modelling | qual_survey | experimental
    keywords: list[str] = []
    keywords_cs: list[str] = []  # case-sensitive acronyms (OLS, VAR, ...)


class TheoryNode(BaseModel):
    id: str
    label: str
    keywords: list[str] = []


class DataRoute(BaseModel):
    name: str
    access: Literal["open", "registration", "subscription", "restricted", "own_collection"]
    note: str = ""


class Territory(BaseModel):
    """A research territory: field → subfield/problem → phenomenon (+ plausible methods)."""

    id: str
    field: str
    label: str
    path: list[str]
    blurb: str
    keywords: list[str] = []
    themes: list[str] = []
    approach: str
    secondary_approaches: list[str] = []
    methods: list[str] = []
    style: str
    policy_relevance: Literal["low", "medium", "high"]
    data_access: Literal["open", "moderate", "restricted"]
    technical_demand: Literal["low", "medium", "high"]
    distributional_focus: Literal["low", "medium", "high"]
    angles: list[str] = []
    data_routes: list[DataRoute] = []
    risks: list[str] = []
    search_strings: list[str] = []
    supervisor_questions: list[str] = []
    adjacent: list[str] = []

    def card_attributes(self) -> dict[str, str]:
        return {
            "approach": self.approach,
            "style": self.style,
            "policy_relevance": self.policy_relevance,
            "data_access": self.data_access,
            "technical_demand": self.technical_demand,
            "distributional_focus": self.distributional_focus,
        }


class DisciplinePack(BaseModel):
    id: str
    label: str
    pack_version: str
    phrases: dict[str, str] = {}
    fields: list[FieldNode] = []
    methods: list[MethodNode] = []
    theories: list[TheoryNode] = []
    territories: list[Territory] = []
    _idx: dict[str, dict[str, Any]] = PrivateAttr(default_factory=dict)

    def territory(self, tid: str) -> Territory:
        return self._index("territories")[tid]

    def field(self, fid: str) -> FieldNode:
        return self._index("fields")[fid]

    def method(self, mid: str) -> MethodNode:
        return self._index("methods")[mid]

    def _index(self, attr: str) -> dict[str, Any]:
        if attr not in self._idx:
            self._idx[attr] = {x.id: x for x in getattr(self, attr)}
        return self._idx[attr]

    @property
    def supported(self) -> bool:
        """A pack without territories cannot produce recommendations."""
        return bool(self.territories) and bool(self.fields)


# -------------------------------------------------------------- curriculum ---
ItemKind = Literal["topic", "subtopic", "method", "theory", "outcome"]
Confidence = Literal["high", "medium", "low", "user"]
ModuleStatus = Literal["unconfirmed", "completed", "current", "optional", "not_taken"]
STUDIED_STATUSES = ("completed", "current")


class SourceEvidence(BaseModel):
    document_id: Optional[str] = None
    page: Optional[int] = None
    heading: Optional[str] = None
    excerpt: str = ""


class ContentItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ci"))
    kind: ItemKind
    text: str
    parent_id: Optional[str] = None           # for subtopics: the topic they sit under
    taxonomy_ids: list[str] = []              # territory IDs (topic/subtopic), method IDs, theory IDs
    mapping_confidence: dict[str, str] = {}   # taxonomy id -> high|medium
    evidence: Optional[SourceEvidence] = None
    extraction_confidence: Confidence = "medium"
    origin: Literal["extracted", "llm", "user"] = "extracted"
    included: bool = True


class Module(BaseModel):
    id: str = Field(default_factory=lambda: new_id("mod"))
    document_id: Optional[str] = None
    code: Optional[str] = None
    title: str
    year_or_level: Optional[str] = None
    credits: Optional[str] = None
    status: ModuleStatus = "unconfirmed"
    listed_as: Literal["core", "optional", "unknown"] = "unknown"
    broad_areas: list[str] = []               # field IDs
    items: list[ContentItem] = []
    evidence: Optional[SourceEvidence] = None
    extraction_confidence: Confidence = "medium"
    origin: Literal["extracted", "llm", "user"] = "extracted"
    enjoyment: Optional[Literal["liked", "disliked"]] = None  # student's own flag
    user_edited: bool = False

    @property
    def display_label(self) -> str:
        return f"{self.code} {self.title}".strip() if self.code else self.title

    @property
    def studied(self) -> bool:
        return self.status in STUDIED_STATUSES

    def of_kind(self, *kinds: str, included_only: bool = True) -> list[ContentItem]:
        return [i for i in self.items if i.kind in kinds and (i.included or not included_only)]


class CurriculumDocument(BaseModel):
    id: str = Field(default_factory=lambda: new_id("doc"))
    original_filename: str
    sha256: str
    media_type: str
    parse_status: Literal["ok", "empty", "image_only", "unsupported", "too_large", "error"]
    n_pages: Optional[int] = None
    n_chars: int = 0
    uploaded_at: str = Field(default_factory=now_iso)
    extractor: Literal["deterministic", "llm", "none"] = "none"
    message: str = ""


class CurriculumExtraction(BaseModel):
    document: CurriculumDocument
    modules: list[Module] = []
    warnings: list[str] = []
    flagged_lines: list[str] = []   # instruction-like lines ignored as untrusted text
    rejected_claims: int = 0        # LLM claims dropped because they had no source support


# ------------------------------------------------------------------ survey ---
class OptionSpec(BaseModel):
    id: str
    kind: Literal["territory", "profile"]
    territory_id: Optional[str] = None
    label: str
    blurb: str
    attributes: dict[str, str] = {}
    signals: dict[str, float] = {}   # explicit preference-key signals (profile options)


class Grounding(BaseModel):
    """A citation of confirmed course material used in question wording."""

    option_id: Optional[str] = None
    module_id: str
    module_label: str
    item_id: str
    item_text: str
    item_kind: str
    excerpt: str = ""
    page: Optional[int] = None


class QuestionSpec(BaseModel):
    """The structured, auditable definition of one task. Displayed prose is separate."""

    id: str
    template_id: Literal["territory_pair", "profile_pair", "clarification"]
    design_version: str
    dimension_ids: list[str]
    prompt: str
    options: list[OptionSpec]
    display_order: list[str]          # option IDs in on-screen order (seeded counterbalancing)
    selection_reason: str
    selection_detail: dict[str, Any] = {}
    grounding: list[Grounding] = []
    explanation: Optional[str] = None  # for clarifications: why we are asking
    step_index: int = 0

    def option(self, oid: str) -> OptionSpec:
        return next(o for o in self.options if o.id == oid)

    def other(self, oid: str) -> OptionSpec:
        return next(o for o in self.options if o.id != oid)


class QuestionCopy(BaseModel):
    """Displayed text for a question. May be LLM-worded; never carries scoring data."""

    question_id: str
    prompt: str
    preface: Optional[str] = None
    option_titles: dict[str, str]
    option_blurbs: dict[str, str]
    option_notes: dict[str, list[str]] = {}
    source: Literal["deterministic", "llm"] = "deterministic"


class Response(BaseModel):
    id: str = Field(default_factory=lambda: new_id("resp"))
    question_id: str
    selected_option_id: Optional[str] = None   # None => "neither / unsure"
    strength: Optional[Literal["slight", "clear", "strong"]] = None
    reason_code: Optional[str] = None
    uncertainty_flag: bool = False
    created_at: str = Field(default_factory=now_iso)


class HistoryEntry(BaseModel):
    spec: QuestionSpec
    response: Response
    top3_after: list[str] = []


class Observation(BaseModel):
    key: str
    value: float
    weight: float
    source: str        # e.g. "cal_enjoy_data", "pp_familiar_novel", "tp__a__b"
    kind: str          # likert | field_rating | choice | choice_attribute | module_flag


class Conflict(BaseModel):
    id: str
    description: str
    keys: list[str] = []


class PreferenceProfile(BaseModel):
    key_scores: dict[str, float] = {}
    key_weights: dict[str, float] = {}
    field_scores: dict[str, float] = {}
    territory_scores: dict[str, float] = {}
    constraints: dict[str, str] = {}
    observations: list[Observation] = []
    conflicts: list[Conflict] = []
    n_tasks: int = 0
    n_unsure: int = 0

    def score(self, key: str, default: float = 0.5) -> float:
        return self.key_scores.get(key, default)

    def weight(self, key: str) -> float:
        return self.key_weights.get(key, 0.0)

    @property
    def unsure_share(self) -> float:
        return self.n_unsure / self.n_tasks if self.n_tasks else 0.0


class Reason(BaseModel):
    kind: Literal["survey", "syllabus", "caution"]
    text: str
    refs: list[str] = []   # question IDs / calibration item IDs / content item IDs


class Recommendation(BaseModel):
    territory_id: str
    rank: int
    fit: float
    components: dict[str, float]           # topic_interest, method_fit, feasibility, values_alignment, exploration_fit
    raw_feasibility: float
    feasibility_flag: bool = False
    familiarity: str = "unknown"
    evidence_label: str = "Insufficient information"
    evidence_points: float = 0.0
    reasons: list[Reason] = []
    feasibility_notes: list[str] = []
    method_notes: list[str] = []
    diversity_note: Optional[str] = None


class SurveyRun(BaseModel):
    """Everything derived from (config, pack, curriculum, seed, answers). Never stored as truth."""

    history: list[HistoryEntry] = []
    current: Optional[QuestionSpec] = None
    stop_reason: Optional[str] = None
    profile: PreferenceProfile = PreferenceProfile()
    ranking: list[Recommendation] = []      # all territories, best first, before diversity
    selection_log: list[dict[str, Any]] = []


# ----------------------------------------------------------------- session ---
class SessionState(BaseModel):
    id: str = Field(default_factory=lambda: new_id("sess"))
    discipline_id: str = "economics"
    design_version: str = ""
    pack_version: str = ""
    random_seed: int = 0
    created_at: str = Field(default_factory=now_iso)
    stage: str = "start"
    year_of_study: Optional[str] = None
    university: Optional[str] = None
    institution_id: str = "generic"
    documents: list[CurriculumDocument] = []
    modules: list[Module] = []
    curriculum_confirmed: bool = False
    used_sample_curriculum: bool = False
    calibration: dict[str, Any] = {}          # item id -> value (None/absent = skipped)
    calibration_done: bool = False
    answers: dict[str, Response] = {}          # active response per question ID
    response_log: list[Response] = []          # every response ever given, including superseded ones
    ingest_warnings: list[str] = []
    flagged_lines: list[str] = []

    @property
    def studied_modules(self) -> list[Module]:
        if not self.curriculum_confirmed:
            return []
        return [m for m in self.modules if m.studied]

    @property
    def has_curriculum(self) -> bool:
        return bool(self.studied_modules)
