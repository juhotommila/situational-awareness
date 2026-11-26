"""Inquiry state for the situational awareness prototype.

The `InquiryRecord` is the single persistent object behind the practitioner
interface. Its fields map onto the design principles:

    DP1 Contextualise evidence           -> ScenarioRecord / RecordMetadata, InquiryRecord.retrievals
    DP2 Make the basis examinable        -> Claim (claim_type, citations, conflicts, qualifications)
    DP3 Enable reconsideration           -> Revision (changed_claims, what_changed, competing_hypotheses)
    DP4 Expose projection conditions     -> Projection (assumptions, status, invalidated_by)
    DP5 Identify provisional points      -> Limitation, Revision.stopping_reason
    DP6 Support effective direction      -> UserAction, ToolCallLog

The module also contains `EventLogger`, which writes a per-participant JSON log
for the qualitative analysis (Chapter 5).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

Phase = Literal["09:15", "09:35"]
PHASE_ORDER: List[str] = ["09:15", "09:35"]

# Fixed scenario date so that record timestamps and the scenario clock line up.
SCENARIO_DATE = "2025-03-11"

INQUIRY_QUESTION = (
    "Can the internal status report (D01) be relied upon for the "
    "11:00 external review of release 3.2?"
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def scenario_time(phase: str) -> str:
    return f"{SCENARIO_DATE}T{phase}:00"


def short_id(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# DP1: scenario records and their context
# ---------------------------------------------------------------------------


class Definition(BaseModel):
    term: str
    meaning: str


class RecordMetadata(BaseModel):
    doc_id: str
    title: str
    source_type: str  # e.g. "Status report", "Email thread", "Chat export"
    source_system: str  # e.g. "PMO Portfolio Tool", "Outlook", "Teams"
    author_role: str
    updated_at: str  # when the record itself was last changed (ISO)
    release_phase: Phase  # when the record becomes available in the scenario
    definitions: List[Definition] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    context_note: str = ""  # caveats about the record itself (e.g. truncated export)


class ScenarioRecord(RecordMetadata):
    content: str


# ---------------------------------------------------------------------------
# DP2: claims and their basis
# ---------------------------------------------------------------------------

ClaimType = Literal["direct_record", "agent_inference", "user_provided"]


class ConflictNote(BaseModel):
    doc_ids: List[str]
    note: str


class Claim(BaseModel):
    id: str = Field(description="Stable id, e.g. C1. Keep ids stable across revisions.")
    text: str
    claim_type: ClaimType = Field(
        description="direct_record = stated in a record; agent_inference = reasoned by the agent; "
        "user_provided = taken from a practitioner correction."
    )
    citations: List[str] = Field(default_factory=list, description="Record ids, e.g. ['D02']")
    conflicts: List[ConflictNote] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DP3: reconsideration
# ---------------------------------------------------------------------------


class CompetingHypothesis(BaseModel):
    id: str
    explanation: str
    supporting: List[str] = Field(default_factory=list, description="Record ids or claim ids")
    against: List[str] = Field(default_factory=list)
    what_would_resolve: str = ""


class ClaimChange(BaseModel):
    claim_id: str
    change: Literal["added", "revised", "withdrawn"]
    before: str = ""
    after: str = ""


TriggerType = Literal["baseline", "user_correction", "user_redirect", "new_records", "reinvestigate"]
AgentMode = Literal["curated", "mock", "gemini"]


class Revision(BaseModel):
    version: int
    trigger: TriggerType
    trigger_note: str = ""
    created_at: str = Field(default_factory=now_iso)
    scenario_time: str = ""
    agent_mode: AgentMode = "mock"
    model_name: str = ""
    models_used: List[str] = Field(default_factory=list)
    addressed_user_actions: List[str] = Field(default_factory=list)
    unaddressed_user_actions: List[str] = Field(default_factory=list)
    what_changed: List[str] = Field(default_factory=list)
    changed_claims: List[ClaimChange] = Field(default_factory=list)
    competing_hypotheses: List[CompetingHypothesis] = Field(default_factory=list)
    stopping_reason: str = ""
    tool_calls: int = 0


# ---------------------------------------------------------------------------
# DP4: projections and their conditions
# ---------------------------------------------------------------------------

ProjectionStatus = Literal["active", "invalidated", "retired"]


class Projection(BaseModel):
    id: str = Field(description="Stable id, e.g. P1. Never reuse an id for a different projection.")
    outcome: str = Field(description="Conditional statement: 'If X holds, then Y'.")
    assumptions: List[str] = Field(default_factory=list)
    based_on: List[str] = Field(default_factory=list, description="Record ids")
    status: ProjectionStatus = "active"
    invalidated_by: List[str] = Field(default_factory=list, description="Record ids or user action ids")
    invalidation_reason: str = ""
    since_version: int = 0  # managed by merge_revision


# ---------------------------------------------------------------------------
# DP5: limits, gaps and provisional points
# ---------------------------------------------------------------------------

LimitationType = Literal["search_gap", "conflict", "tacit_knowledge"]


class Limitation(BaseModel):
    id: str
    type: LimitationType = Field(
        description="search_gap = records searched but nothing found; conflict = unresolved disagreement "
        "between records; tacit_knowledge = needs a person/organisational knowledge to resolve."
    )
    description: str
    related_docs: List[str] = Field(default_factory=list)
    unresolved_owner: str = Field("", description="Who could resolve it, if known. Empty if not applicable.")


# ---------------------------------------------------------------------------
# DP6: practitioner direction and the investigation trace
# ---------------------------------------------------------------------------

ActionType = Literal["correct", "redirect", "pause", "resume", "stop"]


class UserAction(BaseModel):
    id: str = Field(default_factory=lambda: short_id("A"))
    timestamp: str = Field(default_factory=now_iso)
    scenario_time: str = ""
    action_type: ActionType
    note: str = ""
    target: str = ""  # claim id or record id, optional
    applied_in_version: Optional[int] = None
    not_addressed_in_versions: List[int] = Field(default_factory=list)


ToolStatus = Literal["found", "no_matches", "not_available", "not_found", "tool_error", "concluded"]


class ToolCallLog(BaseModel):
    version: int
    step: int
    timestamp: str = Field(default_factory=now_iso)
    thought: str = ""
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    status: ToolStatus
    observation_summary: str = ""


# ---------------------------------------------------------------------------
# Structured output the agent must produce on every revision
# ---------------------------------------------------------------------------

Reliance = Literal["reliable", "reliable_with_qualifications", "not_reliable", "undetermined"]


class AgentRevisionOutput(BaseModel):
    """Everything the agent must return when it concludes an investigation."""

    situation_summary: str
    reliance: Reliance
    overall_assessment: str
    claims: List[Claim]
    projections: List[Projection]
    limitations: List[Limitation]
    competing_hypotheses: List[CompetingHypothesis]
    what_changed: List[str] = Field(
        description="Plain-language bullets describing how this account differs from the previous one."
    )
    addressed_user_actions: List[str] = Field(
        default_factory=list, description="Ids of practitioner actions taken into account."
    )


# ---------------------------------------------------------------------------
# The persistent inquiry record
# ---------------------------------------------------------------------------


class InquiryRecord(BaseModel):
    question: str = INQUIRY_QUESTION
    phase: Phase = "09:15"
    version: int = 0
    situation_summary: str = ""
    reliance: Reliance = "undetermined"
    overall_assessment: str = ""
    claims: List[Claim] = Field(default_factory=list)
    projections: List[Projection] = Field(default_factory=list)
    limitations: List[Limitation] = Field(default_factory=list)
    revisions: List[Revision] = Field(default_factory=list)
    user_actions: List[UserAction] = Field(default_factory=list)
    tool_log: List[ToolCallLog] = Field(default_factory=list)
    retrievals: Dict[str, str] = Field(default_factory=dict)  # doc_id -> scenario time last read
    history: List[Dict[str, Any]] = Field(default_factory=list)  # snapshots of earlier versions

    # -- convenience -------------------------------------------------------
    @property
    def latest_revision(self) -> Optional[Revision]:
        return self.revisions[-1] if self.revisions else None

    def claim(self, claim_id: str) -> Optional[Claim]:
        return next((c for c in self.claims if c.id == claim_id), None)

    def pending_actions(self) -> List[UserAction]:
        return [
            a
            for a in self.user_actions
            if a.applied_in_version is None and a.action_type in ("correct", "redirect")
        ]

    def considered_docs(self) -> List[str]:
        return sorted(self.retrievals.keys())

    def snapshot(self) -> Dict[str, Any]:
        return self.model_dump(exclude={"history"})


# ---------------------------------------------------------------------------
# Merging an agent output into the record (DP3/DP4 bookkeeping)
# ---------------------------------------------------------------------------


def _claim_signature(c: Claim) -> tuple:
    return (c.text.strip(), c.claim_type, tuple(sorted(c.citations)))


def merge_revision(
    record: InquiryRecord,
    output: AgentRevisionOutput,
    *,
    trigger: TriggerType,
    trigger_note: str,
    steps: List[ToolCallLog],
    stopping_reason: str,
    agent_mode: AgentMode,
    model_name: str = "",
    models_used: Optional[List[str]] = None,
) -> InquiryRecord:
    """Produce the next version of the record. Old states are kept in `history`;
    invalidated or dropped projections stay visible rather than disappearing."""

    new_version = record.version + 1
    new = record.model_copy(deep=True)
    if record.version > 0:
        new.history = record.history + [record.snapshot()]
    new.version = new_version

    # --- claims + diff -----------------------------------------------------
    old_claims = {c.id: c for c in record.claims}
    new_claims = {c.id: c for c in output.claims}
    changes: List[ClaimChange] = []
    for cid, c in new_claims.items():
        if cid not in old_claims:
            changes.append(ClaimChange(claim_id=cid, change="added", after=c.text))
        elif _claim_signature(old_claims[cid]) != _claim_signature(c) or (
            [q for q in c.qualifications] != [q for q in old_claims[cid].qualifications]
        ):
            changes.append(
                ClaimChange(claim_id=cid, change="revised", before=old_claims[cid].text, after=c.text)
            )
    for cid, c in old_claims.items():
        if cid not in new_claims:
            changes.append(ClaimChange(claim_id=cid, change="withdrawn", before=c.text))
    new.claims = list(output.claims)

    # --- projections: never silently delete --------------------------------
    out_proj = {p.id: p for p in output.projections}
    merged: List[Projection] = []
    for old in record.projections:
        if old.id in out_proj:
            p = out_proj.pop(old.id).model_copy()
            p.since_version = old.since_version or new_version
            merged.append(p)
        elif old.status == "active":
            kept = old.model_copy()
            kept.status = "retired"
            kept.invalidation_reason = kept.invalidation_reason or f"Not carried forward in v{new_version}."
            merged.append(kept)
        else:
            merged.append(old)
    for p in out_proj.values():
        p = p.model_copy()
        p.since_version = new_version
        merged.append(p)
    new.projections = merged

    # --- the rest ------------------------------------------------------------
    new.situation_summary = output.situation_summary
    new.reliance = output.reliance
    new.overall_assessment = output.overall_assessment
    new.limitations = list(output.limitations)

    addressed_ids = set(output.addressed_user_actions)
    addressed_this_rev: List[str] = []
    unaddressed_this_rev: List[str] = []
    for a in new.user_actions:
        if a.applied_in_version is None and a.action_type in ("correct", "redirect"):
            if a.id in addressed_ids:
                a.applied_in_version = new_version
                addressed_this_rev.append(a.id)
            else:
                a.not_addressed_in_versions.append(new_version)
                unaddressed_this_rev.append(a.id)

    stamped_steps = []
    for s in steps:
        s = s.model_copy()
        s.version = new_version
        stamped_steps.append(s)
        if s.tool == "read_record" and s.status == "found":
            new.retrievals[str(s.args.get("doc_id"))] = scenario_time(record.phase)
    new.tool_log = record.tool_log + stamped_steps

    used_models = list(models_used) if models_used is not None else ([model_name] if model_name else [])
    new.revisions = record.revisions + [
        Revision(
            version=new_version,
            trigger=trigger,
            trigger_note=trigger_note,
            scenario_time=scenario_time(record.phase),
            agent_mode=agent_mode,
            model_name=model_name,
            models_used=used_models,
            addressed_user_actions=addressed_this_rev,
            unaddressed_user_actions=unaddressed_this_rev,
            what_changed=list(output.what_changed),
            changed_claims=changes,
            competing_hypotheses=list(output.competing_hypotheses),
            stopping_reason=stopping_reason,
            tool_calls=len([s for s in steps if s.tool != "conclude"]),
        )
    ]
    return new


# ---------------------------------------------------------------------------
# Research traceability (Chapter 5)
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"


class EventLogger:
    """Appends timestamped events to logs/participant_<id>_<session>.json.

    Each event stores wall-clock time, scenario time, the current account
    version and an event-specific payload. Revisions also store a full
    InquiryRecord snapshot so quotes can be matched to what was on screen.
    """

    def __init__(self, participant_id: str, log_dir: Path = LOG_DIR):
        self.participant_id = participant_id.strip() or "anon"
        self.session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in self.participant_id if ch.isalnum() or ch in "-_") or "anon"
        self.path = log_dir / f"participant_{safe}_{self.session_id}.json"
        self.data: Dict[str, Any] = {
            "participant_id": self.participant_id,
            "session_id": self.session_id,
            "started_at": now_iso(),
            "events": [],
        }
        self._flush()

    def log(
        self,
        event: str,
        *,
        record: Optional[InquiryRecord] = None,
        snapshot: bool = False,
        **payload: Any,
    ) -> None:
        entry: Dict[str, Any] = {"t": now_iso(), "event": event, **payload}
        if record is not None:
            entry["scenario_time"] = record.phase
            entry["version"] = record.version
            if snapshot:
                entry["snapshot"] = record.snapshot()
        self.data["events"].append(entry)
        self._flush()

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    def _flush(self) -> None:
        self.path.write_text(self.to_json(), encoding="utf-8")
