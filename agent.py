"""Constrained ReAct investigation agent.

An `AgentRun` is a resumable, step-wise investigation. The practitioner can
run it to completion or step through it one model turn at a time, add
direction mid-run, or stop it early (DP6). Every tool call is logged as a
`ToolCallLog` for the Investigation view, and the run ends in a structured
`AgentRevisionOutput`, which `merge_revision` folds into the InquiryRecord.

Two providers share the same interface:
    * GeminiProvider – live tool calling through the google-genai SDK
    * MockProvider   – scripted, deterministic (no key / offline / pilots)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from state import (
    AgentRevisionOutput,
    Claim,
    InquiryRecord,
    Limitation,
    ToolCallLog,
    TriggerType,
    UserAction,
    merge_revision,
    scenario_time,
)
from tools import TOOL_DECLARATIONS, execute_tool, load_records, record_catalogue, summarise_observation

DEFAULT_MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "8"))
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

ToolCall = Tuple[str, Dict[str, Any]]


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

INVESTIGATE_SYSTEM = """You are the investigation agent inside a sensemaking support tool used by a delivery practitioner.
Your job is NOT to decide for the practitioner. Your job is to make the basis of the situation examinable.

Rules:
- Use the tools to examine the records currently available. You have a budget of at most {max_steps} tool calls in this run.
- Pay attention to record metadata: who wrote it, when it was last updated compared with the current scenario time ({now}),
  team-specific definitions of terms, dependencies, and context notes such as truncated exports.
- A 'no_matches' search result is evidence of absence only within these records. It does not show that something did not happen.
- Practitioner corrections and redirects are persistent. Respect them. If the records contradict a correction, flag the conflict
  instead of silently overriding it.
- Before each tool call, write one short sentence saying why you are making it.
- When you have enough to revise the account, or when the remaining questions need people rather than records, stop calling tools
  and reply with a single line starting with 'CONCLUDE:' and the reason.
"""

FINAL_SYSTEM = """You are the investigation agent inside a sensemaking support tool. Produce the revised account of the situation as JSON
matching the given schema. The practitioner will examine every field, so be precise, concise, and honest about uncertainty.
Write in plain, understated prose without filler or repetition.

Field rules:
- claims: claim_type 'direct_record' only if a record states it; 'agent_inference' for your reasoning; 'user_provided' for content taken
  from practitioner corrections. Cite record ids (e.g. "D03") in citations. Record conflicts between records in 'conflicts', and put
  caveats (age of record, partial exports, second-hand reports) in 'qualifications'. Keep the ids of claims that still apply (C1, C2...);
  give new claims new ids.
- projections: conditional 'If X, then Y' outcomes with explicit assumptions. Keep the ids of existing projections. If a projection's
  assumption is contradicted, keep it with status 'invalidated', fill invalidated_by and invalidation_reason, and add a NEW projection
  with a new id if a revised outlook applies. Never reuse an id for a different projection.
- limitations: 'search_gap' (searched, nothing found), 'conflict' (unresolved disagreement), 'tacit_knowledge' (needs a person or
  organisational knowledge). Name unresolved_owner where a role could resolve it.
- competing_hypotheses: plausible alternative explanations, with what would resolve them.
- what_changed: short bullets comparing this account with the previous one (or 'Initial account' if there was none).
- addressed_user_actions: ids of the practitioner actions you took into account.
- reliance: whether D01 can be relied on for the external review, on the current evidence.
"""


def _compact_account(record: InquiryRecord) -> Dict[str, Any]:
    return {
        "version": record.version,
        "situation_summary": record.situation_summary,
        "reliance": record.reliance,
        "overall_assessment": record.overall_assessment,
        "claims": [c.model_dump() for c in record.claims],
        "projections": [p.model_dump(exclude={"since_version"}) for p in record.projections],
        "limitations": [l.model_dump() for l in record.limitations],
        "competing_hypotheses": [h.model_dump() for h in (record.latest_revision.competing_hypotheses if record.latest_revision else [])],
    }


def _actions_payload(record: InquiryRecord) -> List[Dict[str, Any]]:
    return [
        {**a.model_dump(include={"id", "action_type", "note", "target"}), "pending": a.applied_in_version is None}
        for a in record.user_actions
        if a.action_type in ("correct", "redirect")
    ]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class Provider:
    mode: str = "mock"

    def start(self, run: "AgentRun") -> None: ...

    def next_turn(self, run: "AgentRun") -> Tuple[str, List[ToolCall]]:
        raise NotImplementedError

    def observe(self, run: "AgentRun", results: List[Tuple[str, Dict[str, Any]]]) -> None: ...

    def add_direction(self, run: "AgentRun", note: str) -> None: ...

    def final_output(self, run: "AgentRun") -> AgentRevisionOutput:
        raise NotImplementedError


class MockProvider(Provider):
    """Deterministic, scripted behaviour. Investigates the 09:35 records with a
    fixed plan; for corrections/redirects it searches the records for the
    practitioner's note and folds the outcome into the account transparently."""

    mode = "mock"

    def start(self, run: "AgentRun") -> None:
        from scenario_scripts import MOCK_0935_PLAN

        self.new_records = run.record.phase == "09:35" and "D07" not in run.record.retrievals
        plan: List[Tuple[str, str, Dict[str, Any]]] = []
        if self.new_records:
            plan += list(MOCK_0935_PLAN)
        for a in run.pending:
            label = "correction" if a.action_type == "correct" else "redirect"
            plan.append((f"Practitioner {label} {a.id}: check whether the records bear on it.", "search_passages", {"query": a.note}))
            if a.target.upper().startswith("D"):
                plan.append((f"The {label} points at {a.target}: re-read it.", "read_record", {"doc_id": a.target.upper()}))
        if not plan:
            plan.append(("Re-check the core question against the available records.", "search_passages", {"query": "confirmed status integration verified"}))
        self.plan = plan
        self.directions: List[str] = []

    def add_direction(self, run: "AgentRun", note: str) -> None:
        self.directions.append(note)
        self.plan.append((f"Mid-run direction from practitioner: '{note}'.", "search_passages", {"query": note}))

    def next_turn(self, run: "AgentRun") -> Tuple[str, List[ToolCall]]:
        if not self.plan:
            return ("CONCLUDE: scripted plan complete; remaining questions need people rather than records.", [])
        thought, tool, args = self.plan.pop(0)
        return (thought, [(tool, args)])

    def final_output(self, run: "AgentRun") -> AgentRevisionOutput:
        from scenario_scripts import mock_0935_output

        rec = run.record
        if self.new_records:
            out = mock_0935_output(rec.claims)
        else:
            out = AgentRevisionOutput(
                situation_summary=rec.situation_summary,
                reliance=rec.reliance,
                overall_assessment=rec.overall_assessment,
                claims=[c.model_copy(deep=True) for c in rec.claims],
                projections=[p.model_copy(deep=True) for p in rec.projections],
                limitations=[l.model_copy(deep=True) for l in rec.limitations],
                competing_hypotheses=list(rec.latest_revision.competing_hypotheses) if rec.latest_revision else [],
                what_changed=[],
            )
        self._overlay_actions(run, out)
        if not out.what_changed:
            out.what_changed = ["Re-checked the account. No new evidence changed it."]
        return out

    # -- helpers ----------------------------------------------------------
    def _search_result_for(self, run: "AgentRun", query: str) -> Optional[Dict[str, Any]]:
        for tool, args, result in run.observations:
            if tool == "search_passages" and args.get("query") == query:
                return result
        return None

    def _overlay_actions(self, run: "AgentRun", out: AgentRevisionOutput) -> None:
        n_user = len([c for c in out.claims if c.id.startswith("U")])
        for a in run.pending + [UserAction(action_type="redirect", note=d, id="mid-run") for d in self.directions]:
            res = self._search_result_for(run, a.note) or {}
            docs = sorted({r["doc_id"] for r in res.get("results", [])})
            if a.action_type == "correct":
                n_user += 1
                quals = (
                    [f"Related passages found in {', '.join(docs)}. Check whether they support or contradict this."]
                    if docs
                    else ["No record corroborates or contradicts this correction."]
                )
                out.claims.append(
                    Claim(id=f"U{n_user}", claim_type="user_provided", text=a.note, citations=[], qualifications=quals)
                )
                target = out.claims and next((c for c in out.claims if c.id == a.target), None)
                if target:
                    target.qualifications.append(f"Disputed by the practitioner ({a.id}): {a.note}")
                    out.what_changed.append(f"Claim {target.id} is now marked as disputed by the practitioner.")
                out.what_changed.append(f"Practitioner correction recorded as claim U{n_user}.")
                if not docs:
                    out.limitations.append(
                        Limitation(id=f"L-{a.id}", type="search_gap",
                                   description=f"No record found that corroborates the practitioner's correction: '{a.note}'.",
                                   unresolved_owner="Practitioner (tacit knowledge)")
                    )
            else:
                where = f"relevant passages in {', '.join(docs)}" if docs else "no matching passages"
                out.what_changed.append(f"Investigation refocused on '{a.note}': {where} (see the Investigation view).")
            if a.id != "mid-run":
                out.addressed_user_actions.append(a.id)


class GeminiProvider(Provider):
    """Live tool calling with google-genai. Function calling is manual so that
    every call can be logged, budgeted and paused."""

    mode = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        from google import genai
        from google.genai import types

        self.types = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=45_000))
        self.model = model
        self.contents: List[Any] = []
        self.pending_text: List[str] = []

    # -- plumbing -----------------------------------------------------------
    def _generate(self, contents, config):
        # google-genai already retries transient 429/503 errors internally via tenacity;
        # we only fall back across models if the primary model stays unavailable.
        models = [self.model]
        if self.model != "gemini-3.5-flash-lite":
            models.append("gemini-3.5-flash-lite")
        last_exc: Optional[Exception] = None
        for m in models:
            try:
                return self.client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                transient = any(code in msg for code in ("429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
                if not transient:
                    raise
        assert last_exc is not None
        raise last_exc

    def _user(self, parts):
        return self.types.Content(role="user", parts=parts)

    # -- interface ------------------------------------------------------------
    def start(self, run: "AgentRun") -> None:
        t = self.types
        rec = run.record
        self.config = t.GenerateContentConfig(
            system_instruction=INVESTIGATE_SYSTEM.format(max_steps=run.max_steps, now=scenario_time(rec.phase)),
            tools=[t.Tool(function_declarations=[t.FunctionDeclaration(**d) for d in TOOL_DECLARATIONS])],
            automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.2,
        )
        payload = {
            "inquiry_question": rec.question,
            "scenario_time": scenario_time(rec.phase),
            "trigger": run.trigger,
            "trigger_note": run.trigger_note,
            "available_records": record_catalogue(rec.phase),
            "records_already_read_in_earlier_versions": rec.considered_docs(),
            "current_account": _compact_account(rec),
            "practitioner_actions": _actions_payload(rec),
        }
        self.contents = [
            self._user([t.Part.from_text(text="Revise the account for this situation.\n\n" + json.dumps(payload, indent=1, ensure_ascii=False))])
        ]

    def add_direction(self, run: "AgentRun", note: str) -> None:
        self.pending_text.append(f"Practitioner direction (mid-run): {note}")

    def _flush_pending(self) -> None:
        if not self.pending_text:
            return
        part = self.types.Part.from_text(text="\n".join(self.pending_text))
        self.pending_text = []
        if self.contents and getattr(self.contents[-1], "role", None) == "user":
            self.contents[-1].parts.append(part)
        else:
            self.contents.append(self._user([part]))

    def next_turn(self, run: "AgentRun") -> Tuple[str, List[ToolCall]]:
        self._flush_pending()
        resp = self._generate(self.contents, self.config)
        cand = resp.candidates[0] if resp.candidates else None
        if cand is None or cand.content is None:
            return ("CONCLUDE: the model returned no content.", [])
        self.contents.append(cand.content)
        text = " ".join(p.text for p in (cand.content.parts or []) if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
        calls = [(fc.name, dict(fc.args or {})) for fc in (resp.function_calls or [])]
        return (text or ("(no reasoning text)" if calls else "CONCLUDE: no further tool calls."), calls)

    def observe(self, run: "AgentRun", results: List[Tuple[str, Dict[str, Any]]]) -> None:
        parts = [self.types.Part.from_function_response(name=name, response=result) for name, result in results]
        self.contents.append(self._user(parts))

    def final_output(self, run: "AgentRun") -> AgentRevisionOutput:
        t = self.types
        rec = run.record
        trace = [
            {"step": i + 1, "thought": s.thought, "tool": s.tool, "args": s.args, "result": _truncate(res)}
            for i, (s, res) in enumerate(zip([s for s in run.steps if s.tool != "conclude"], [o[2] for o in run.observations]))
        ]
        payload = {
            "inquiry_question": rec.question,
            "scenario_time": scenario_time(rec.phase),
            "trigger": run.trigger,
            "trigger_note": run.trigger_note,
            "previous_account": _compact_account(rec),
            "practitioner_actions": _actions_payload(rec),
            "mid_run_directions": run.directions,
            "investigation_trace": trace,
            "stopping_reason": run.stopping_reason,
        }
        prompt = "Produce the revised account as JSON.\n\n" + json.dumps(payload, indent=1, ensure_ascii=False)
        contents = [self._user([t.Part.from_text(text=prompt)])]
        from pydantic import ValidationError

        schema_configs = [
            dict(response_schema=AgentRevisionOutput),
            dict(response_json_schema=AgentRevisionOutput.model_json_schema()),
        ]
        last_err: Optional[Exception] = None
        for schema_cfg in schema_configs:
            cfg = t.GenerateContentConfig(system_instruction=FINAL_SYSTEM, response_mime_type="application/json", temperature=0.2, **schema_cfg)
            for _ in range(2):
                try:
                    resp = self._generate(contents, cfg)
                except Exception as exc:
                    last_err = exc
                    if "400" in str(exc) and "schema" in str(exc).lower():
                        break  # try the next schema style
                    raise RuntimeError(f"Model request failed: {exc}") from exc
                try:
                    return AgentRevisionOutput.model_validate_json(resp.text or "")
                except ValidationError as exc:
                    last_err = exc
                    contents = contents + [self._user([t.Part.from_text(text=f"Your previous output was invalid: {exc}. Return valid JSON only.")])]
        raise RuntimeError(f"Could not obtain a valid structured revision from the model: {last_err}")


def _truncate(obj: Dict[str, Any], limit: int = 6000) -> Any:
    s = json.dumps(obj, ensure_ascii=False)
    return obj if len(s) <= limit else s[:limit] + "…[truncated]"


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


class AgentRun:
    def __init__(
        self,
        record: InquiryRecord,
        *,
        trigger: TriggerType,
        trigger_note: str = "",
        provider: Provider,
        max_steps: int = DEFAULT_MAX_STEPS,
    ):
        self.record = record.model_copy(deep=True)
        self.trigger = trigger
        self.trigger_note = trigger_note
        self.provider = provider
        self.max_steps = max_steps
        self.pending: List[UserAction] = self.record.pending_actions()
        self.steps: List[ToolCallLog] = []
        self.observations: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
        self.directions: List[str] = []
        self.done = False
        self.stopping_reason = ""
        self.error: Optional[str] = None
        self.provider.start(self)

    @property
    def mode(self) -> str:
        return self.provider.mode

    @property
    def tool_calls(self) -> int:
        return len(self.observations)

    def _log(self, **kw) -> ToolCallLog:
        entry = ToolCallLog(version=self.record.version + 1, step=len(self.steps) + 1, **kw)
        self.steps.append(entry)
        return entry

    def step(self) -> List[ToolCallLog]:
        """Advance one model turn. Returns the steps logged in this turn."""
        if self.done:
            return []
        if self.tool_calls >= self.max_steps:
            self.done = True
            self.stopping_reason = f"Reached the tool-call limit ({self.max_steps}/{self.max_steps}). The account may be incomplete."
            return []
        before = len(self.steps)
        try:
            thought, calls = self.provider.next_turn(self)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.done = True
            self.stopping_reason = f"Stopped by an error after {self.tool_calls} tool call(s): {self.error}"
            return self.steps[before:]
        if not calls:
            reason = thought.split("CONCLUDE:", 1)[-1].strip() if "CONCLUDE:" in thought else thought
            self._log(tool="conclude", status="concluded", thought=reason)
            self.done = True
            self.stopping_reason = f"Agent concluded after {self.tool_calls} of {self.max_steps} allowed tool calls: {reason}"
            return self.steps[before:]
        results = []
        remaining = self.max_steps - self.tool_calls
        for i, (name, args) in enumerate(calls[:remaining]):
            result = execute_tool(name, args, self.record.phase)
            self.observations.append((name, args, result))
            self._log(tool=name, args=args, status=result.get("status", "tool_error"),
                      thought=thought if i == 0 else "", observation_summary=summarise_observation(name, result))
            results.append((name, result))
        for name, args in calls[remaining:]:  # over budget: answer so the conversation stays valid
            results.append((name, {"status": "tool_error", "error": "Tool-call budget exhausted."}))
        self.provider.observe(self, results)
        return self.steps[before:]

    def run_to_end(self, on_step=None) -> None:
        while not self.done:
            new = self.step()
            if on_step:
                for s in new:
                    on_step(s)

    def add_direction(self, note: str) -> None:
        self.directions.append(note)
        self.provider.add_direction(self, note)

    def stop(self) -> None:
        self.done = True
        self.stopping_reason = f"Stopped by the practitioner after {self.tool_calls} tool call(s)."

    def finalize(self) -> InquiryRecord:
        if self.error:
            raise RuntimeError(self.error)
        if not self.done:
            self.stop()
        output = self.provider.final_output(self)
        return merge_revision(
            self.record,
            output,
            trigger=self.trigger,
            trigger_note=self.trigger_note,
            steps=self.steps,
            stopping_reason=self.stopping_reason,
            agent_mode=self.mode,  # type: ignore[arg-type]
        )


def make_provider(mode: str, api_key: Optional[str] = None, model: Optional[str] = None) -> Provider:
    if mode == "gemini":
        if not api_key:
            raise ValueError("Gemini mode needs an API key (GEMINI_API_KEY).")
        return GeminiProvider(api_key=api_key, model=model or DEFAULT_MODEL)
    return MockProvider()


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def build_curated_baseline() -> InquiryRecord:
    from scenario_scripts import BASELINE_OUTPUT, BASELINE_STEPS, BASELINE_STOPPING_REASON

    load_records()  # validate records exist
    empty = InquiryRecord()
    rec = merge_revision(
        empty,
        BASELINE_OUTPUT,
        trigger="baseline",
        trigger_note="Initial investigation of records D01–D06 (cached for all participants).",
        steps=BASELINE_STEPS,
        stopping_reason=BASELINE_STOPPING_REASON,
        agent_mode="curated",
    )
    # Fixed timestamps: the baseline must be identical for every participant.
    fixed = scenario_time("09:15")
    for s in rec.tool_log:
        s.timestamp = fixed
    rec.revisions[0].created_at = fixed
    return rec
