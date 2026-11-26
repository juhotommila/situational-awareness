"""Inquiry workspace — practitioner interface and researcher controls.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv

from agent import DEFAULT_MAX_STEPS, DEFAULT_MODEL, AgentRun, build_curated_baseline, check_gemini_api, make_provider
from state import Claim, EventLogger, InquiryRecord, Projection, Revision, ToolCallLog, UserAction, scenario_time
from tools import is_released, load_records

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="Inquiry Workspace",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ss = st.session_state
E = html.escape

TRIGGER_LABEL = {
    "baseline": "Baseline",
    "user_correction": "Correction",
    "user_redirect": "Redirect",
    "new_records": "09:35 release",
    "reinvestigate": "Re-investigation",
}
MODE_LABEL = {"curated": "baseline", "mock": "scripted", "gemini": "Gemini"}
RELIANCE_LABEL = {
    "reliable": "Reliable",
    "reliable_with_qualifications": "Qualified",
    "not_reliable": "Not reliable",
    "undetermined": "Undetermined",
}
CLAIM_BADGE = {
    "direct_record": ("Direct", "b-direct"),
    "agent_inference": ("Inference", "b-inference"),
    "user_provided": ("Practitioner", "b-user"),
}
STATUS_CLASS = {
    "found": "s-ok",
    "concluded": "s-ok",
    "no_matches": "s-warn",
    "not_available": "s-warn",
    "not_found": "s-err",
    "tool_error": "s-err",
}


# ---------------------------------------------------------------------------
# Styling — Nordic editorial / academic register
# ---------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap');

:root {
  --bg: #F8F7F4;
  --surface: #FFFFFF;
  --surface-muted: #F2F0EB;
  --border: #E2DFD7;
  --border-strong: #C9C5BA;
  --ink: #1E242B;
  --ink-muted: #5A626D;
  --ink-faint: #7A828E;
  --accent: #1F4E79;
  --accent-bg: #EEF3F8;
  --accent-bd: #C4D6E7;
  --ok: #1E5A42;
  --ok-bg: #EEF6F2;
  --ok-bd: #C5DFD3;
  --warn: #805308;
  --warn-bg: #FCF6E9;
  --warn-bd: #E5CFA0;
  --err: #8A2C2C;
  --err-bg: #FCF1F1;
  --err-bd: #E6C3C3;
  --inf: #424878;
  --inf-bg: #F1F2FA;
  --inf-bd: #D1D4EA;
}

html, body, .stApp, .stMarkdown, button, input, textarea, select {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  color: var(--ink);
}
.stApp { background: var(--bg); }
.block-container { padding-top: 1.5rem; padding-bottom: 3.5rem; max-width: 1380px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] {
  background: #F1EFEA;
  border-right: 1px solid var(--border);
}

/* Header */
.mast {
  padding-bottom: .9rem;
  margin-bottom: 1.15rem;
  border-bottom: 1px solid var(--border-strong);
}
.mast-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: .5rem;
  margin-bottom: .45rem;
}
.mast-meta {
  font-size: .78rem;
  color: var(--ink-muted);
  letter-spacing: .01em;
}
.mast-meta b { color: var(--ink); font-weight: 600; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: .76rem; }
.mast h1 {
  font-family: 'Source Serif 4', Georgia, serif !important;
  font-size: 1.48rem !important;
  font-weight: 600 !important;
  line-height: 1.32 !important;
  color: var(--ink) !important;
  margin: 0 !important;
  padding: 0 !important;
  max-width: 62ch;
}

/* Reliance pills */
.rel {
  display: inline-block;
  font-size: .72rem;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  padding: .2rem .55rem;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
}
.rel-reliable { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-bd); }
.rel-reliable_with_qualifications { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-bd); }
.rel-not_reliable { background: var(--err-bg); color: var(--err); border-color: var(--err-bd); }
.rel-undetermined { background: var(--surface-muted); color: var(--ink-muted); }

/* Cards */
div[class*="st-key-card-"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: .85rem 1rem .95rem !important;
  margin-bottom: .25rem;
}
div[class*="st-key-card-"] div[data-testid="stMarkdownContainer"] p:last-child {
  margin-bottom: 0;
}
div[class*="st-key-card-focus"] {
  border-color: var(--accent) !important;
  border-left-width: 3px !important;
}
div[class*="st-key-card-locked"] {
  background: var(--surface-muted);
  opacity: .75;
}
div[class*="st-key-panel-"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: .9rem .95rem .65rem;
}

/* Section headings */
.sec-h {
  font-size: .72rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--ink-muted);
  font-weight: 600;
  margin: 1.35rem 0 .55rem;
  padding-bottom: .3rem;
  border-bottom: 1px solid var(--border);
}

/* Badges */
.b {
  display: inline-block;
  font-size: .67rem;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  padding: .12rem .42rem;
  border-radius: 3px;
  margin-right: .3rem;
  vertical-align: middle;
  border: 1px solid transparent;
}
.b-id {
  font-family: 'IBM Plex Mono', monospace;
  background: var(--surface-muted);
  color: var(--ink);
  border-color: var(--border);
}
.b-direct { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-bd); }
.b-inference { background: var(--inf-bg); color: var(--inf); border-color: var(--inf-bd); }
.b-user { background: var(--accent-bg); color: var(--accent); border-color: var(--accent-bd); }
.b-new { background: var(--ok-bg); color: var(--ok); border-color: var(--ok-bd); }
.b-rev { background: var(--warn-bg); color: var(--warn); border-color: var(--warn-bd); }
.b-active { background: var(--accent-bg); color: var(--accent); border-color: var(--accent-bd); }
.b-invalid { background: var(--err-bg); color: var(--err); border-color: var(--err-bd); }
.b-retired { background: var(--surface-muted); color: var(--ink-muted); border-color: var(--border); }

/* Text blocks */
.summary { font-size: .95rem; line-height: 1.6; color: var(--ink); }
.assess { margin-top: .5rem; font-size: .86rem; line-height: 1.5; color: var(--ink-muted); }
.claim-text { font-size: .92rem; line-height: 1.55; color: var(--ink); margin: .4rem 0 .25rem; }
.conflict {
  border-left: 2px solid #B57B14;
  background: var(--warn-bg);
  padding: .38rem .65rem;
  border-radius: 0 4px 4px 0;
  font-size: .82rem;
  line-height: 1.45;
  margin-top: .35rem;
  color: #5C3D06;
}
.qual { color: var(--ink-muted); font-size: .81rem; line-height: 1.45; margin-top: .22rem; }
.qual::before { content: "— "; color: var(--ink-faint); }
.meta { font-size: .77rem; color: var(--ink-faint); }

/* Revision banner & 09:35 notice */
.changed {
  background: var(--accent-bg);
  border: 1px solid var(--accent-bd);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  padding: .75rem 1rem;
  margin-bottom: .8rem;
}
.changed-head { font-size: .84rem; font-weight: 600; color: var(--accent); margin-bottom: .2rem; }
.changed ul { margin: .3rem 0 0 1.05rem; padding: 0; }
.changed li { font-size: .85rem; line-height: 1.45; margin: .15rem 0; color: var(--ink); }
.diff-added { color: var(--ok); }
.diff-withdrawn, .diff-before { color: var(--ink-faint); text-decoration: line-through; }

.notice {
  background: var(--warn-bg);
  border: 1px solid var(--warn-bd);
  border-left: 3px solid #B57B14;
  border-radius: 4px;
  padding: .6rem .9rem;
  margin-bottom: .5rem;
  font-size: .86rem;
  color: #5C3D06;
}

/* Projections */
.outcome { font-size: .9rem; line-height: 1.5; color: var(--ink); margin: .4rem 0 .35rem; }
.invalid .outcome { text-decoration: line-through; text-decoration-color: var(--err); color: var(--ink-faint); }
.assume { font-size: .81rem; line-height: 1.45; color: var(--ink-muted); margin: .12rem 0; }
.assume::before { content: "· "; font-weight: 700; color: var(--accent); }
.inval-note {
  margin-top: .45rem;
  border-left: 2px solid var(--err);
  background: var(--err-bg);
  padding: .38rem .6rem;
  border-radius: 0 4px 4px 0;
  font-size: .81rem;
  color: var(--err);
}

/* Limits */
.lim-head { font-size: .8rem; font-weight: 600; color: var(--ink); margin: 0 0 .4rem; }
.lim-item {
  font-size: .82rem;
  line-height: 1.45;
  color: var(--ink);
  padding: .5rem .65rem;
  border-radius: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  margin-bottom: .4rem;
}
.owner { display: block; margin-top: .28rem; font-size: .76rem; color: var(--accent); font-weight: 500; }
.stopbar {
  margin-top: .55rem;
  font-size: .81rem;
  color: var(--ink-muted);
  padding: .48rem .75rem;
  border-radius: 4px;
  background: var(--surface-muted);
  border: 1px solid var(--border);
}

/* Evidence */
.rec-head { display: flex; align-items: baseline; gap: .45rem; flex-wrap: wrap; }
.rec-title { font-weight: 600; color: var(--ink); font-size: .95rem; }
.rec-type { font-size: .75rem; color: var(--ink-faint); }
.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(185px, 1fr));
  gap: .4rem .85rem;
  margin: .6rem 0 .4rem;
  padding-top: .5rem;
  border-top: 1px solid var(--border);
}
.meta-grid div { font-size: .81rem; color: var(--ink); }
.meta-grid span {
  display: block;
  font-size: .66rem;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--ink-faint);
  margin-bottom: .06rem;
}
.defn {
  font-size: .81rem;
  margin: .22rem 0;
  padding: .35rem .55rem;
  border-radius: 4px;
  background: var(--inf-bg);
  border: 1px solid var(--inf-bd);
  color: var(--ink);
}
.ctx { font-size: .81rem; margin: .35rem 0; color: var(--warn); }
.content { white-space: pre-wrap; font-size: .88rem; line-height: 1.62; color: var(--ink); }

/* Timeline */
.tstep {
  display: grid;
  grid-template-columns: 1.7rem 1fr;
  gap: .55rem;
  padding: .48rem 0;
  border-bottom: 1px solid var(--border);
}
.tnum {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'IBM Plex Mono', monospace;
  font-size: .72rem;
  font-weight: 500;
  background: var(--surface-muted);
  color: var(--ink-muted);
  border: 1px solid var(--border);
}
.thought { font-size: .81rem; color: var(--ink-muted); font-style: italic; }
.call { font-family: 'IBM Plex Mono', monospace; font-size: .78rem; color: var(--ink); margin: .12rem 0; }
.obs { font-size: .79rem; color: var(--ink-muted); }
.st-pill {
  font-size: .64rem;
  font-weight: 600;
  padding: .06rem .35rem;
  border-radius: 3px;
  margin-left: .35rem;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.s-ok { background: var(--ok-bg); color: var(--ok); }
.s-warn { background: var(--warn-bg); color: var(--warn); }
.s-err { background: var(--err-bg); color: var(--err); }

/* Quiet Streamlit controls */
div[data-testid="stSegmentedControl"] button { font-weight: 500; font-size: .86rem; }
div[data-testid="stPills"] button {
  font-family: 'IBM Plex Mono', monospace !important;
  font-size: .75rem !important;
  min-height: 1.65rem !important;
  padding: .1rem .5rem !important;
}
</style>
"""


# ---------------------------------------------------------------------------
# Setup & helpers
# ---------------------------------------------------------------------------


def get_api_key() -> Optional[str]:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except Exception:
        return None


@st.cache_data
def _baseline_json() -> str:
    path = ROOT / "baseline_0915.json"
    return path.read_text(encoding="utf-8") if path.exists() else build_curated_baseline().model_dump_json()


def fresh_baseline() -> InquiryRecord:
    return InquiryRecord.model_validate_json(_baseline_json())


def log(event: str, snapshot: bool = False, **payload) -> None:
    ss.logger.log(event, record=ss.record, snapshot=snapshot, **payload)


def fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except ValueError:
        return iso


def age(iso: str, phase: str) -> str:
    try:
        delta = datetime.fromisoformat(scenario_time(phase)) - datetime.fromisoformat(iso)
    except ValueError:
        return ""
    hours = delta.total_seconds() / 3600
    if hours < 0:
        return "after now"
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)} min ago"
    if hours < 48:
        return f"{hours:.0f} h ago"
    return f"{int(hours // 24)} d ago"


def init_state() -> None:
    if "record" in ss:
        return
    ss.record = fresh_baseline()
    ss.participant_id = "pilot"
    ss.logger = EventLogger(ss.participant_id)
    ss.view = "Situation"
    ss.last_view = "Situation"
    ss.active_run = None
    ss.op = None
    ss.focus_doc = None
    ss.step_mode = False
    ss.agent_mode = "gemini" if get_api_key() else "mock"
    ss.model = DEFAULT_MODEL
    ss.max_steps = DEFAULT_MAX_STEPS
    ss.released_at = None
    ss.agent_error = None
    ss.api_check = None
    ss.toast = None
    log("session_start", snapshot=True, agent_mode=ss.agent_mode, model=ss.model)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


def cb_view_change() -> None:
    if ss.view is None:
        ss.view = ss.last_view
        return
    log("view_change", view=ss.view, from_view=ss.last_view)
    ss.last_view = ss.view


def cb_citation(key: str, claim_id: str) -> None:
    doc = ss.get(key)
    ss[key] = None
    if not doc:
        return
    log("citation_click", doc_id=doc, claim_id=claim_id, from_view=ss.last_view)
    ss.focus_doc = doc
    ss.view = "Evidence"
    ss.last_view = "Evidence"


def cb_back_to_situation() -> None:
    log("view_change", view="Situation", from_view="Evidence", via="back_button")
    ss.view = "Situation"
    ss.last_view = "Situation"
    ss.focus_doc = None


def _add_action(action: UserAction) -> None:
    ss.record.user_actions.append(action)
    if ss.active_run is not None:
        ss.active_run.record.user_actions.append(action.model_copy())
    log("user_action", action=action.model_dump())


def cb_correction() -> None:
    note = (ss.get("corr_note") or "").strip()
    if not note:
        ss.toast = "Enter a correction first."
        return
    target = ss.get("corr_target") or ""
    target = "" if target == "General" else target.split(" ")[0]
    _add_action(UserAction(action_type="correct", note=note, target=target, scenario_time=ss.record.phase))
    ss.op = ("start", "user_correction", f"Correction{f' ({target})' if target else ''}: {note}")


def cb_redirect() -> None:
    note = (ss.get("redir_note") or "").strip()
    target = ss.get("redir_doc") or ""
    target = "" if target == "Any" else target.split(" ")[0]
    if not note and not target:
        ss.toast = "Specify a focus or record."
        return
    note = note or f"Review {target}"
    _add_action(UserAction(action_type="redirect", note=note, target=target, scenario_time=ss.record.phase))
    ss.op = ("start", "user_redirect", f"Redirect: {note}")


def cb_reinvestigate() -> None:
    ss.op = ("start", "reinvestigate", "Manual re-investigation.")


def cb_investigate_new() -> None:
    log("investigate_new_records_clicked")
    ss.op = ("start", "new_records", "Records D07–D08 released at 09:35.")


def cb_step_mode() -> None:
    kind = "pause" if ss.step_mode else "resume"
    _add_action(UserAction(action_type=kind, note="Step-by-step " + ("on" if ss.step_mode else "off"), scenario_time=ss.record.phase))


def cb_run_op(kind: str) -> None:
    ss.op = (kind,)


def cb_mid_direction() -> None:
    note = (ss.get("mid_dir") or "").strip()
    if not note or ss.active_run is None:
        return
    _add_action(UserAction(action_type="redirect", note=f"(mid-run) {note}", target="", scenario_time=ss.record.phase))
    ss.active_run.add_direction(note)
    ss.mid_dir = ""


def cb_release() -> None:
    ss.record.phase = "09:35"
    ss.released_at = datetime.now().strftime("%H:%M:%S")
    log("release_0935", released=["D07", "D08"])
    ss.toast = "09:35 records available (D07, D08)."


def cb_reset() -> None:
    ss.record = fresh_baseline()
    ss.active_run = None
    ss.focus_doc = None
    ss.released_at = None
    ss.agent_error = None
    ss.view = ss.last_view = "Situation"
    log("reset_to_baseline", snapshot=True)


def cb_new_session() -> None:
    pid = (ss.get("pid_input") or "").strip() or "anon"
    ss.participant_id = pid
    ss.logger = EventLogger(pid)
    cb_reset()
    log("session_start", snapshot=True, agent_mode=ss.agent_mode, model=ss.model)
    ss.toast = f"Session started: {pid}"


def cb_retry_mock() -> None:
    ss.agent_mode = "mock"
    ss.agent_error = None
    log("agent_mode_change", mode="mock", model="mock-scripted", reason="retry_after_error")


def cb_check_api() -> None:
    ok, msg = check_gemini_api(get_api_key(), ss.model)
    ss.api_check = (ok, msg)
    log("api_check", ok=ok, model=ss.model, detail=msg)


def _action_status(a: UserAction) -> Tuple[str, str]:
    if a.applied_in_version is not None:
        return f"applied in v{a.applied_in_version}", "b-new"
    if a.not_addressed_in_versions:
        return f"not addressed in v{a.not_addressed_in_versions[-1]}", "b-rev"
    if a.action_type in ("pause", "resume", "stop"):
        return "–", ""
    return "pending", "b-retired"


def _revision_model_label(rev: Revision) -> str:
    if rev.models_used:
        return " -> ".join(rev.models_used)
    if rev.model_name:
        return rev.model_name
    return MODE_LABEL.get(rev.agent_mode, rev.agent_mode)


# ---------------------------------------------------------------------------
# Running the agent
# ---------------------------------------------------------------------------


def _log_step(s: ToolCallLog) -> None:
    log("agent_step", step=s.model_dump())


def _finalize(run: AgentRun) -> None:
    with st.spinner("Updating account…"):
        try:
            new = run.finalize()
        except Exception as exc:
            ss.agent_error = f"{type(exc).__name__}: {exc}"
            log("agent_error", error=ss.agent_error, steps=[s.model_dump() for s in run.steps])
            ss.active_run = None
            return
    ss.record = new
    ss.active_run = None
    rev = new.latest_revision
    log(
        "revision",
        snapshot=True,
        trigger=rev.trigger,
        mode=rev.agent_mode,
        model_name=rev.model_name,
        models_used=rev.models_used,
        addressed_user_actions=rev.addressed_user_actions,
        unaddressed_user_actions=rev.unaddressed_user_actions,
        stopping_reason=rev.stopping_reason,
    )
    if ss.view != "Situation":
        log("view_change", view="Situation", from_view=ss.view, via="auto_after_revision")
    ss.view = ss.last_view = "Situation"
    ss.focus_doc = None
    ss.toast = f"Updated to v{new.version}."


def process_op() -> None:
    op, ss.op = ss.op, None
    if not op:
        return
    kind = op[0]
    if kind == "start":
        _, trigger, note = op
        try:
            provider = make_provider(ss.agent_mode, api_key=get_api_key(), model=ss.model)
        except Exception as exc:
            ss.agent_error = str(exc)
            return
        run = AgentRun(ss.record, trigger=trigger, trigger_note=note, provider=provider, max_steps=ss.max_steps)
        ss.active_run = run
        ss.agent_error = None
        log("agent_run_start", trigger=trigger, note=note, mode=run.mode, model=ss.model, step_mode=ss.step_mode, max_steps=ss.max_steps)
        if ss.step_mode:
            return
        kind = "run_to_end"

    run: Optional[AgentRun] = ss.active_run
    if run is None:
        return
    if kind == "step":
        with st.spinner("Running step…"):
            for s in run.step():
                _log_step(s)
    elif kind == "run_to_end":
        with st.status(f"Investigating ({MODE_LABEL[run.mode]})…", expanded=False) as status:
            def on_step(s: ToolCallLog) -> None:
                _log_step(s)
                status.write(f"`{s.step}.` `{s.tool}({fmt_args(s)})` — {s.status}")
            run.run_to_end(on_step=on_step)
            status.update(label="Investigation complete", state="complete")
    elif kind == "stop":
        run.stop()
        log("agent_run_stopped_by_user", tool_calls=run.tool_calls)
    if run.done:
        _finalize(run)


def fmt_args(s: ToolCallLog) -> str:
    if not s.args:
        return ""
    return ", ".join(f'{k}="{v}"' for k, v in s.args.items())


# ---------------------------------------------------------------------------
# Rendering: header
# ---------------------------------------------------------------------------


def render_header(rec: InquiryRecord) -> None:
    n_avail = sum(1 for r in load_records().values() if is_released(r, rec.phase))
    st.markdown(
        f"""
<div class="mast">
  <div class="mast-top">
    <div class="mast-meta">Release 3.2 &middot; <span class="mono"><b>{rec.phase}</b></span> &middot; <span class="mono">v{rec.version}</span> &middot; {n_avail} records</div>
    <span class="rel rel-{rec.reliance}">D01: {RELIANCE_LABEL[rec.reliance]}</span>
  </div>
  <h1>{E(rec.question)}</h1>
</div>""",
        unsafe_allow_html=True,
    )
    if rec.phase == "09:35" and "D07" not in rec.retrievals and ss.active_run is None:
        c1, c2 = st.columns([3.8, 1.2], vertical_alignment="center")
        c1.markdown(
            '<div class="notice"><b>09:35</b> — Two new records available (D07, D08), not yet incorporated.</div>',
            unsafe_allow_html=True,
        )
        c2.button("Investigate", key="btn_investigate_new", type="primary", on_click=cb_investigate_new, use_container_width=True)


# ---------------------------------------------------------------------------
# Rendering: Situation
# ---------------------------------------------------------------------------


def section(title: str) -> None:
    st.markdown(f'<div class="sec-h">{E(title)}</div>', unsafe_allow_html=True)


def render_changed(rec: InquiryRecord) -> None:
    rev = rec.latest_revision
    if not rev or rev.version <= 1:
        return
    bullets = "".join(f"<li>{E(b)}</li>" for b in rev.what_changed)
    trig = TRIGGER_LABEL.get(rev.trigger, rev.trigger)
    unaddressed_html = ""
    if rev.unaddressed_user_actions:
        by_id = {a.id: a for a in rec.user_actions}
        notes = "; ".join(
            E(by_id[aid].note) if aid in by_id else E(aid)
            for aid in rev.unaddressed_user_actions
        )
        unaddressed_html = (
            f'<div class="conflict" style="margin-top:.5rem">'
            f'<b>Not addressed in v{rev.version}:</b> {notes} (kept pending for the next run).'
            f'</div>'
        )
    st.markdown(
        f"""<div class="changed">
<div class="changed-head">Changes in v{rev.version} &middot; {E(trig)} ({rev.scenario_time[-8:-3]})</div>
<ul>{bullets}</ul>{unaddressed_html}</div>""",
        unsafe_allow_html=True,
    )
    if rev.changed_claims:
        with st.expander(f"Claim diff vs. v{rev.version - 1} ({len(rev.changed_claims)})"):
            rows = []
            for ch in rev.changed_claims:
                if ch.change == "added":
                    rows.append(f'<div class="qual"><span class="b b-new">added</span><span class="mono">{ch.claim_id}</span> <span class="diff-added">{E(ch.after)}</span></div>')
                elif ch.change == "withdrawn":
                    rows.append(f'<div class="qual"><span class="b b-invalid">withdrawn</span><span class="mono">{ch.claim_id}</span> <span class="diff-withdrawn">{E(ch.before)}</span></div>')
                else:
                    before = f'<div class="diff-before">{E(ch.before)}</div>' if ch.before != ch.after else '<div class="meta">(basis or qualification updated)</div>'
                    rows.append(f'<div class="qual"><span class="b b-rev">revised</span><span class="mono">{ch.claim_id}</span>{before}<div>{E(ch.after)}</div></div>')
            st.markdown("".join(rows), unsafe_allow_html=True)


def render_claim(c: Claim, rec: InquiryRecord) -> None:
    rev = rec.latest_revision
    change = None
    if rev and rev.version > 1:
        change = next((ch.change for ch in rev.changed_claims if ch.claim_id == c.id), None)
    label, cls = CLAIM_BADGE[c.claim_type]
    tag = ""
    if change == "added":
        tag = f'<span class="b b-new">v{rev.version}</span>'
    elif change == "revised":
        tag = f'<span class="b b-rev">revised</span>'
    conflicts = "".join(
        f'<div class="conflict"><b>Conflict ({E(" / ".join(cf.doc_ids))}):</b> {E(cf.note)}</div>' for cf in c.conflicts
    )
    quals = "".join(f'<div class="qual">{E(q)}</div>' for q in c.qualifications)
    with st.container(key=f"card-claim-{c.id}-v{rec.version}"):
        st.markdown(
            f'<span class="b b-id">{c.id}</span><span class="b {cls}">{label}</span>{tag}'
            f'<div class="claim-text">{E(c.text)}</div>{conflicts}{quals}',
            unsafe_allow_html=True,
        )
        if c.citations:
            key = f"cite-{c.id}-v{rec.version}"
            st.pills("Sources", c.citations, key=key, on_change=cb_citation, args=(key, c.id),
                     label_visibility="collapsed")
        else:
            st.markdown('<div class="meta" style="margin-bottom:.3rem">No record cited</div>', unsafe_allow_html=True)


def render_projection(p: Projection, rec: InquiryRecord) -> None:
    status_badge = {
        "active": ("Active", "b-active"),
        "invalidated": ("Invalidated", "b-invalid"),
        "retired": ("Retired", "b-retired"),
    }[p.status]
    assumptions = "".join(f'<div class="assume">{E(a)}</div>' for a in p.assumptions)
    inval = ""
    if p.status != "active":
        by = f" ({E(', '.join(p.invalidated_by))})" if p.invalidated_by else ""
        inval = f'<div class="inval-note"><b>{status_badge[0]}{by}:</b> {E(p.invalidation_reason)}</div>'
    since = f'<span class="meta"> · v{p.since_version}</span>' if p.since_version else ""
    based = f'<div class="meta" style="margin-top:.4rem">Basis: <span class="mono">{E(", ".join(p.based_on))}</span></div>' if p.based_on else ""
    with st.container(key=f"card-proj-{p.id}-v{rec.version}"):
        st.markdown(
            f'<div class="{"invalid" if p.status != "active" else ""}">'
            f'<span class="b b-id">{p.id}</span><span class="b {status_badge[1]}">{status_badge[0]}</span>{since}'
            f'<div class="outcome">{E(p.outcome)}</div>'
            f'<div class="meta" style="margin:.15rem 0">Assumes</div>{assumptions}{inval}{based}</div>',
            unsafe_allow_html=True,
        )


def render_situation(rec: InquiryRecord) -> None:
    render_changed(rec)

    with st.container(key=f"card-summary-v{rec.version}"):
        st.markdown(
            f'<div class="summary">{E(rec.situation_summary)}</div>'
            f'<div class="assess"><b>Assessment:</b> {E(rec.overall_assessment)}</div>',
            unsafe_allow_html=True,
        )

    section("Claims")
    for c in rec.claims:
        render_claim(c, rec)

    rev = rec.latest_revision
    if rev and rev.competing_hypotheses:
        with st.expander(f"Competing explanations ({len(rev.competing_hypotheses)})"):
            for h in rev.competing_hypotheses:
                st.markdown(
                    f'<div class="lim-item"><span class="b b-id">{h.id}</span>{E(h.explanation)}'
                    f'<div class="qual">For: {E(", ".join(h.supporting) or "–")}</div>'
                    f'<div class="qual">Against: {E(", ".join(h.against) or "–")}</div>'
                    f'<div class="qual"><b>Resolves via:</b> {E(h.what_would_resolve)}</div></div>',
                    unsafe_allow_html=True,
                )

    section("Projections")
    active = [p for p in rec.projections if p.status == "active"]
    inactive = [p for p in rec.projections if p.status != "active"]
    cols = st.columns(2)
    for i, p in enumerate(active + inactive):
        with cols[i % 2]:
            render_projection(p, rec)

    section("Limits & open questions")
    groups = [
        ("search_gap", "Search gaps"),
        ("conflict", "Unresolved conflicts"),
        ("tacit_knowledge", "Requires a person"),
    ]
    cols = st.columns(3)
    for col, (typ, title) in zip(cols, groups):
        items = [l for l in rec.limitations if l.type == typ]
        body = "".join(
            f'<div class="lim-item">{E(l.description)}'
            + (f'<span class="owner">{E(l.unresolved_owner)}</span>' if l.unresolved_owner else "")
            + (f'<div class="meta mono" style="margin-top:.2rem">{E(", ".join(l.related_docs))}</div>' if l.related_docs else "")
            + "</div>"
            for l in items
        ) or '<div class="meta">None.</div>'
        col.markdown(f'<div class="lim-head">{title}</div>{body}', unsafe_allow_html=True)
    if rev:
        st.markdown(f'<div class="stopbar"><b>Stopped:</b> {E(rev.stopping_reason)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Rendering: Evidence
# ---------------------------------------------------------------------------


def render_evidence(rec: InquiryRecord) -> None:
    records = load_records()
    if ss.focus_doc:
        c1, c2 = st.columns([4, 1.1], vertical_alignment="center")
        c1.markdown(f'<div class="meta">Viewing cited record <span class="mono"><b>{E(ss.focus_doc)}</b></span></div>', unsafe_allow_html=True)
        c2.button("← Situation", key="btn_back", on_click=cb_back_to_situation, use_container_width=True)

    section("Records")
    order = sorted(records, key=lambda d: (d != ss.focus_doc, d))
    for doc_id in order:
        r = records[doc_id]
        if not is_released(r, rec.phase):
            continue
        focus = doc_id == ss.focus_doc
        retrieved = rec.retrievals.get(doc_id)
        cited_by = [c.id for c in rec.claims if doc_id in c.citations]
        defs = "".join(f'<div class="defn"><b>{E(d.term)}:</b> {E(d.meaning)}</div>' for d in r.definitions)
        ctx = f'<div class="ctx">{E(r.context_note)}</div>' if r.context_note else ""
        with st.container(key=f"card-{'focus' if focus else 'rec'}-{doc_id}-v{rec.version}"):
            st.markdown(
                f"""<div class="rec-head"><span class="b b-id">{doc_id}</span><span class="rec-title">{E(r.title)}</span><span class="rec-type">{E(r.source_type)}</span></div>
<div class="meta-grid">
  <div><span>Source</span>{E(r.source_system)}</div>
  <div><span>Author</span>{E(r.author_role)}</div>
  <div><span>Updated</span>{fmt_ts(r.updated_at)} ({age(r.updated_at, rec.phase)})</div>
  <div><span>Retrieved</span>{(retrieved[-8:-3]) if retrieved else 'Not read'}</div>
  <div><span>Depends on</span><span class="mono">{E(', '.join(r.dependencies) or '–')}</span></div>
  <div><span>Cited in</span><span class="mono">{E(', '.join(cited_by) or '–')}</span></div>
</div>{ctx}{('<div class="meta" style="margin-top:.35rem">Definitions</div>' + defs) if defs else ''}""",
                unsafe_allow_html=True,
            )
            with st.expander("Full text", expanded=focus):
                st.markdown(f'<div class="content">{E(r.content)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Rendering: Investigation
# ---------------------------------------------------------------------------


def timeline_html(steps: List[ToolCallLog]) -> str:
    out = []
    for s in steps:
        if s.tool == "conclude":
            call = '<div class="call">conclude</div>'
        else:
            call = f'<div class="call">{E(s.tool)}({E(fmt_args(s))})<span class="st-pill {STATUS_CLASS.get(s.status, "s-warn")}">{E(s.status)}</span></div>'
        thought = f'<div class="thought">{E(s.thought)}</div>' if s.thought else ""
        obs = f'<div class="obs">{E(s.observation_summary)}</div>' if s.observation_summary else ""
        out.append(f'<div class="tstep"><div class="tnum">{s.step}</div><div>{thought}{call}{obs}</div></div>')
    return "".join(out) or '<div class="meta">No steps yet.</div>'


def render_investigation(rec: InquiryRecord) -> None:
    run: Optional[AgentRun] = ss.active_run
    if run is not None:
        section("Active run")
        st.markdown(timeline_html(run.steps), unsafe_allow_html=True)

    section("Trace by version")
    for rev in reversed(rec.revisions):
        steps = [s for s in rec.tool_log if s.version == rev.version]
        call_word = "call" if rev.tool_calls == 1 else "calls"
        title = f"v{rev.version} · {TRIGGER_LABEL.get(rev.trigger, rev.trigger)} · {rev.tool_calls} {call_word} · {_revision_model_label(rev)}"
        with st.expander(title, expanded=rev.version == rec.version):
            st.markdown(
                f'<div class="meta">{E(rev.trigger_note)}</div>{timeline_html(steps)}'
                f'<div class="stopbar">{E(rev.stopping_reason)}</div>',
                unsafe_allow_html=True,
            )

    section("Direction history")
    acts = list(rec.user_actions)
    if acts:
        st.dataframe(
            [
                {
                    "Time": a.timestamp[-8:],
                    "Phase": a.scenario_time,
                    "Type": a.action_type,
                    "Target": a.target or "–",
                    "Note": a.note,
                    "Status": _action_status(a)[0],
                }
                for a in acts
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.markdown('<div class="meta">No corrections or redirects recorded.</div>', unsafe_allow_html=True)

    if rec.history:
        section("Earlier versions")
        versions = [h["version"] for h in rec.history]
        v = st.selectbox("Version", versions, index=len(versions) - 1, format_func=lambda x: f"v{x}", key="hist_v")
        snap = InquiryRecord.model_validate(next(h for h in rec.history if h["version"] == v))
        if ss.get("_last_hist_v") != v:
            ss["_last_hist_v"] = v
            log("view_earlier_version", shown_version=v)
        st.markdown(
            f'<div class="lim-item"><span class="rel rel-{snap.reliance}">{RELIANCE_LABEL[snap.reliance]}</span>'
            f'<div class="summary" style="font-size:.88rem;margin-top:.4rem">{E(snap.situation_summary)}</div></div>'
            + "".join(f'<div class="qual"><span class="mono"><b>{c.id}</b></span> {E(c.text)}</div>' for c in snap.claims)
            + "".join(f'<div class="qual"><span class="mono"><b>{p.id}</b></span> [{p.status}] {E(p.outcome)}</div>' for p in snap.projections),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Rendering: direction panel
# ---------------------------------------------------------------------------


def render_direction_panel(rec: InquiryRecord) -> None:
    run: Optional[AgentRun] = ss.active_run
    with st.container(key="panel-direct"):
        st.markdown('<div class="sec-h" style="margin-top:0">Direction</div>', unsafe_allow_html=True)

        if ss.agent_error:
            st.error(f"Revision failed; account unchanged.\n\n{ss.agent_error}")
            st.button("Switch to scripted mode", key="btn_retry_mock", on_click=cb_retry_mock, use_container_width=True)

        if run is not None:
            st.markdown(f'<div class="meta">Step-by-step · {run.tool_calls}/{run.max_steps} calls · {MODE_LABEL[run.mode]}</div>', unsafe_allow_html=True)
            st.markdown(timeline_html(run.steps[-3:]), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.button("Next step", key="btn_step", on_click=cb_run_op, args=("step",), type="primary", use_container_width=True)
            c2.button("Finish run", key="btn_run_end", on_click=cb_run_op, args=("run_to_end",), use_container_width=True)
            st.button("Stop & update", key="btn_stop", on_click=cb_run_op, args=("stop",), use_container_width=True)
            st.text_input("Mid-run note", key="mid_dir", placeholder="e.g. check certificate owner", on_change=cb_mid_direction)
            return

        t_corr, t_redir = st.tabs(["Correct", "Redirect"])
        with t_corr:
            with st.form("form_correct", clear_on_submit=True, border=False):
                st.selectbox(
                    "Target",
                    ["General"] + [f"{c.id} — {c.text[:48]}…" for c in rec.claims],
                    key="corr_target",
                )
                st.text_area("Correction", key="corr_note", height=84,
                             placeholder="e.g. Security owns certificate renewals since last week.")
                st.form_submit_button("Apply correction", type="primary", on_click=cb_correction, use_container_width=True)
        with t_redir:
            with st.form("form_redirect", clear_on_submit=True, border=False):
                st.text_input("Focus", key="redir_note", placeholder="e.g. whether UAT can start 12 March")
                st.selectbox("Record", ["Any"] + [d for d, r in load_records().items() if is_released(r, rec.phase)], key="redir_doc")
                st.form_submit_button("Redirect", type="primary", on_click=cb_redirect, use_container_width=True)

        st.button("Re-investigate", key="btn_reinvestigate", on_click=cb_reinvestigate, use_container_width=True)
        st.toggle("Step-by-step", key="step_mode", on_change=cb_step_mode)

        recent = [a for a in rec.user_actions if a.action_type in ("correct", "redirect")][-3:]
        if recent:
            st.markdown('<div class="meta" style="margin:.6rem 0 .25rem">Active direction</div>', unsafe_allow_html=True)
            for a in reversed(recent):
                st_label, st_cls = _action_status(a)
                st_html = f'<span class="b {st_cls}" style="margin-top:.25rem">{E(st_label)}</span>' if st_cls else f'<div class="meta">{E(st_label)}</div>'
                st.markdown(f'<div class="lim-item"><span class="b b-user">{a.action_type}</span>{E(a.note)}<div>{st_html}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Researcher sidebar
# ---------------------------------------------------------------------------


def render_sidebar(rec: InquiryRecord) -> None:
    sb = st.sidebar
    sb.markdown("#### Researcher controls")
    sb.caption("Keep collapsed during interviews.")

    with sb.expander("Session", expanded=True):
        st.text_input("Participant ID", value=ss.participant_id, key="pid_input")
        st.button("New session", key="btn_new_session", on_click=cb_new_session, use_container_width=True)
        st.caption(f"`logs/{ss.logger.path.name}`")

    with sb.expander("Scenario", expanded=True):
        st.button("Release 09:35 (D07–D08)", key="btn_release", on_click=cb_release, disabled=rec.phase == "09:35",
                  type="primary", use_container_width=True)
        if ss.released_at:
            st.caption(f"Released {ss.released_at}")
        st.button("Reset to 09:15", key="btn_reset", on_click=cb_reset, use_container_width=True)

    with sb.expander("Agent", expanded=True):
        has_key = bool(get_api_key())
        st.radio(
            "Mode",
            ["mock", "gemini"],
            key="agent_mode",
            format_func=lambda m: "Scripted (offline demo)" if m == "mock" else "Live Gemini",
            on_change=lambda: log("agent_mode_change", mode=ss.agent_mode, model=ss.model),
        )
        if ss.agent_mode == "mock":
            st.caption("For offline demos only; scripted mode cannot evaluate corrections. Use Live Gemini for interviews.")
        elif not has_key:
            st.warning("GEMINI_API_KEY not set.")
        st.text_input("Model", key="model")
        st.slider("Max tool calls", 2, 12, key="max_steps")
        if ss.agent_mode == "gemini":
            st.button("Check API connection", key="btn_check_api", on_click=cb_check_api, use_container_width=True)
            if ss.api_check is not None:
                ok, msg = ss.api_check
                (st.success if ok else st.error)(msg)

    with sb.expander("Export", expanded=True):
        st.download_button("Session log (JSON)", ss.logger.to_json(), file_name=ss.logger.path.name,
                           mime="application/json", use_container_width=True, on_click="ignore")
        st.download_button("Current account (JSON)", rec.model_dump_json(indent=2), file_name=f"inquiry_v{rec.version}.json",
                           mime="application/json", use_container_width=True, on_click="ignore")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    process_op()
    if ss.toast:
        st.toast(ss.toast)
        ss.toast = None

    rec: InquiryRecord = ss.record
    render_sidebar(rec)
    render_header(rec)

    left, right = st.columns([2.6, 1.25], gap="large")
    with left:
        st.segmented_control(
            "View", ["Situation", "Evidence", "Investigation"], key="view", on_change=cb_view_change,
            label_visibility="collapsed",
        )
        view = ss.view or ss.last_view
        if view == "Situation":
            render_situation(rec)
        elif view == "Evidence":
            render_evidence(rec)
        else:
            render_investigation(rec)
    with right:
        render_direction_panel(rec)


main()
