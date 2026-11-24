"""Stay in the Know – practitioner interface + researcher controls.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import streamlit as st
from dotenv import load_dotenv

from agent import DEFAULT_MAX_STEPS, DEFAULT_MODEL, AgentRun, build_curated_baseline, make_provider
from state import Claim, EventLogger, InquiryRecord, Projection, ToolCallLog, UserAction, scenario_time
from tools import is_released, load_records

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="Stay in the Know – Inquiry Workspace",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ss = st.session_state
E = html.escape

TRIGGER_LABEL = {
    "baseline": "Initial investigation",
    "user_correction": "Practitioner correction",
    "user_redirect": "Practitioner redirect",
    "new_records": "New records (09:35)",
    "reinvestigate": "Re-investigation",
}
MODE_LABEL = {"curated": "cached baseline", "mock": "scripted agent", "gemini": "live Gemini agent"}
RELIANCE_LABEL = {
    "reliable": "Reliable",
    "reliable_with_qualifications": "Reliable with qualifications",
    "not_reliable": "Not reliable as stated",
    "undetermined": "Undetermined",
}
CLAIM_BADGE = {
    "direct_record": ("Direct record", "b-direct"),
    "agent_inference": ("Agent inference", "b-inference"),
    "user_provided": ("Practitioner input", "b-user"),
}
STATUS_CLASS = {
    "found": "s-ok", "concluded": "s-ok", "no_matches": "s-warn", "not_available": "s-warn",
    "not_found": "s-err", "tool_error": "s-err",
}


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
html, body, .stApp, .stMarkdown, button, input, textarea, select { font-family: 'Inter', system-ui, sans-serif !important; }
.stApp {
  background:
    radial-gradient(1100px 520px at 8% -12%, rgba(124,156,255,0.14), transparent 60%),
    radial-gradient(900px 480px at 100% -5%, rgba(192,132,252,0.10), transparent 60%),
    #0B0E14;
}
.block-container { padding-top: 1.4rem; padding-bottom: 4rem; max-width: 1520px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #0F131C; border-right: 1px solid rgba(255,255,255,.06); }

/* hero */
.hero { padding: 1.1rem 1.3rem 1.0rem; border-radius: 18px; margin-bottom: 1rem;
  background: linear-gradient(135deg, rgba(124,156,255,.10), rgba(192,132,252,.06) 60%, rgba(255,255,255,.02));
  border: 1px solid rgba(124,156,255,.18); box-shadow: 0 10px 40px -20px rgba(124,156,255,.35); }
.eyebrow { letter-spacing: .16em; font-size: .7rem; color: #8B93A7; font-weight: 600; text-transform: uppercase; }
.hero h1 { font-size: 1.45rem !important; font-weight: 650 !important; line-height: 1.35 !important; margin: .35rem 0 .8rem !important; padding: 0 !important;
  background: linear-gradient(90deg, #EEF1F8, #B4C3FF); -webkit-background-clip: text; background-clip: text; color: transparent; }
.chips { display: flex; flex-wrap: wrap; gap: .45rem; }
.chip { font-size: .76rem; padding: .26rem .7rem; border-radius: 999px; background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.09); color: #C9CFDD; white-space: nowrap; }
.chip.clock { background: rgba(124,156,255,.14); border-color: rgba(124,156,255,.4); color: #C7D2FF; font-weight: 600; }
.rel-reliable { background: rgba(52,211,153,.12) !important; color: #6EE7B7 !important; border-color: rgba(52,211,153,.4) !important; }
.rel-reliable_with_qualifications { background: rgba(251,191,36,.12) !important; color: #FCD34D !important; border-color: rgba(251,191,36,.4) !important; }
.rel-not_reliable { background: rgba(248,113,113,.12) !important; color: #FCA5A5 !important; border-color: rgba(248,113,113,.45) !important; }
.rel-undetermined { color: #9AA3B5 !important; }

/* generic cards: any container with key starting card- */
div[class*="st-key-card-"] {
  background: linear-gradient(180deg, rgba(23,28,40,.92), rgba(17,21,31,.92));
  border: 1px solid rgba(255,255,255,.07); border-radius: 14px; padding: .95rem 1.05rem .55rem;
  transition: border-color .2s ease, transform .2s ease, box-shadow .2s ease; }
div[class*="st-key-card-"]:hover { border-color: rgba(124,156,255,.35); box-shadow: 0 8px 30px -18px rgba(124,156,255,.5); }
div[class*="st-key-card-focus"] { border-color: rgba(124,156,255,.7) !important; box-shadow: 0 0 0 3px rgba(124,156,255,.18); }
div[class*="st-key-card-locked"] { opacity: .55; }
div[class*="st-key-panel-"] {
  background: rgba(17,21,31,.85); border: 1px solid rgba(124,156,255,.22); border-radius: 16px; padding: 1rem 1rem .6rem; }

.section-title { font-size: .74rem; letter-spacing: .14em; text-transform: uppercase; color: #8B93A7; font-weight: 650; margin: 1.4rem 0 .6rem; display:flex; align-items:center; gap:.5rem; }
.section-title .dp { font-size: .64rem; letter-spacing: .06em; color: #7C9CFF; background: rgba(124,156,255,.12); padding: .08rem .4rem; border-radius: 6px; }
.legend { font-size: .78rem; color: #8B93A7; margin: -.2rem 0 .7rem; }

.badge { display: inline-block; font-size: .68rem; font-weight: 650; letter-spacing: .04em; padding: .16rem .5rem; border-radius: 6px; margin-right: .35rem; vertical-align: middle; text-transform: uppercase; }
.b-direct { background: rgba(45,212,191,.13); color: #5EEAD4; border: 1px solid rgba(45,212,191,.35); }
.b-inference { background: rgba(192,132,252,.13); color: #D8B4FE; border: 1px solid rgba(192,132,252,.35); }
.b-user { background: rgba(56,189,248,.13); color: #7DD3FC; border: 1px solid rgba(56,189,248,.35); }
.b-new { background: rgba(52,211,153,.15); color: #6EE7B7; border: 1px solid rgba(52,211,153,.4); }
.b-rev { background: rgba(251,191,36,.14); color: #FCD34D; border: 1px solid rgba(251,191,36,.4); }
.b-id { background: rgba(255,255,255,.06); color: #AEB6C8; border: 1px solid rgba(255,255,255,.1); font-family: 'JetBrains Mono', monospace; }
.b-active { background: rgba(124,156,255,.14); color: #C7D2FF; border: 1px solid rgba(124,156,255,.4); }
.b-invalid { background: rgba(248,113,113,.14); color: #FCA5A5; border: 1px solid rgba(248,113,113,.45); }
.b-retired { background: rgba(148,163,184,.12); color: #CBD5E1; border: 1px solid rgba(148,163,184,.35); }

.claim-text { font-size: .97rem; line-height: 1.55; color: #E6E9F2; margin: .45rem 0 .3rem; }
.conflict { border-left: 3px solid #F59E0B; background: rgba(245,158,11,.08); padding: .45rem .7rem; border-radius: 8px; font-size: .84rem; margin-top: .45rem; color: #F5D9A8; }
.qual { color: #9AA3B5; font-size: .83rem; margin-top: .3rem; }
.qual::before { content: "↳ "; color: #5B6478; }

.summary { font-size: 1.02rem; line-height: 1.6; color: #E6E9F2; }
.assess { margin-top: .6rem; font-size: .9rem; color: #B9C1D3; }

.changed { border-radius: 16px; padding: 1rem 1.2rem; margin-bottom: .8rem; animation: slidein .55s ease;
  background: linear-gradient(135deg, rgba(124,156,255,.16), rgba(192,132,252,.09)); border: 1px solid rgba(124,156,255,.4); }
.changed h3 { font-size: 1rem !important; margin: 0 0 .35rem !important; padding: 0 !important; color: #DCE3FF; }
.changed ul { margin: .3rem 0 0 1.1rem; padding: 0; }
.changed li { font-size: .9rem; margin: .18rem 0; color: #DDE2EE; }
.meta-line { font-size: .78rem; color: #9AA3B5; }
.diff-added { color: #6EE7B7; } .diff-withdrawn { color: #FCA5A5; text-decoration: line-through; } .diff-before { color: #8B93A7; text-decoration: line-through; }

.newrec { border-radius: 14px; padding: .8rem 1.1rem; margin-bottom: .6rem; display:flex; align-items:center; gap:.8rem;
  background: rgba(251,191,36,.08); border: 1px solid rgba(251,191,36,.45); animation: pulse 2.4s infinite; color: #FDE68A; font-size: .92rem; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(251,191,36,.35);} 70% { box-shadow: 0 0 0 12px rgba(251,191,36,0);} 100% { box-shadow: 0 0 0 0 rgba(251,191,36,0);} }
@keyframes slidein { from { opacity: 0; transform: translateY(-6px);} to { opacity: 1; transform: none; } }

.outcome { font-size: .95rem; line-height: 1.5; color: #E6E9F2; margin: .45rem 0 .35rem; }
.invalid .outcome { text-decoration: line-through; text-decoration-color: rgba(248,113,113,.7); color: #8B93A7; }
.assume { font-size: .84rem; color: #B9C1D3; margin: .15rem 0; }
.assume::before { content: "◇ "; color: #7C9CFF; }
.invalid-box { margin-top: .5rem; background: rgba(248,113,113,.09); border-left: 3px solid #F87171; border-radius: 8px; padding: .45rem .7rem; font-size: .84rem; color: #FECACA; }

.limit-col h4 { font-size: .86rem !important; margin: 0 0 .5rem !important; padding: 0 !important; color: #DCE3FF; }
.limit { font-size: .85rem; color: #D2D8E5; padding: .5rem .65rem; border-radius: 9px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.06); margin-bottom: .45rem; }
.owner { display:block; margin-top: .3rem; font-size: .77rem; color: #7DD3FC; }
.stopbar { margin-top: .5rem; font-size: .84rem; color: #B9C1D3; padding: .55rem .8rem; border-radius: 10px; background: rgba(124,156,255,.07); border: 1px dashed rgba(124,156,255,.35); }

.rec-head { display:flex; align-items:center; gap:.5rem; flex-wrap: wrap; }
.rec-title { font-weight: 650; color: #EEF1F8; font-size: 1rem; }
.meta-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: .45rem .9rem; margin: .7rem 0 .4rem; }
.meta-grid div { font-size: .82rem; color: #D2D8E5; }
.meta-grid span { display:block; font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: #7D869A; margin-bottom: .1rem; }
.defn { font-size: .83rem; margin: .25rem 0; padding: .4rem .6rem; border-radius: 8px; background: rgba(192,132,252,.07); border: 1px solid rgba(192,132,252,.2); color: #E4D7FA; }
.ctx { font-size: .83rem; margin: .4rem 0; color: #FCD9A0; }
.content { white-space: pre-wrap; font-size: .9rem; line-height: 1.6; color: #D9DEEA; }

.tstep { display:grid; grid-template-columns: 2rem 1fr; gap: .6rem; padding: .55rem 0; border-bottom: 1px solid rgba(255,255,255,.05); }
.tnum { width: 1.7rem; height: 1.7rem; border-radius: 50%; display:flex; align-items:center; justify-content:center; font-size: .75rem; font-weight: 650; background: rgba(124,156,255,.15); color: #C7D2FF; }
.thought { font-size: .84rem; color: #AEB6C8; font-style: italic; }
.call { font-family: 'JetBrains Mono', monospace; font-size: .8rem; color: #E6E9F2; margin: .15rem 0; }
.obs { font-size: .8rem; color: #9AA3B5; }
.st-pill { font-size: .66rem; font-weight: 650; padding: .08rem .42rem; border-radius: 5px; margin-left: .35rem; text-transform: uppercase; letter-spacing: .04em; }
.s-ok { background: rgba(52,211,153,.14); color: #6EE7B7; } .s-warn { background: rgba(251,191,36,.14); color: #FCD34D; } .s-err { background: rgba(248,113,113,.14); color: #FCA5A5; }

div[data-testid="stSegmentedControl"] button { font-weight: 600; }
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
        return datetime.fromisoformat(iso).strftime("%a %d %b %H:%M")
    except ValueError:
        return iso


def age(iso: str, phase: str) -> str:
    try:
        delta = datetime.fromisoformat(scenario_time(phase)) - datetime.fromisoformat(iso)
    except ValueError:
        return ""
    hours = delta.total_seconds() / 3600
    if hours < 0:
        return "after current time"
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)} min before now"
    if hours < 48:
        return f"{hours:.0f} h before now"
    return f"{int(hours // 24)} days old"


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
    ss.toast = None
    log("session_start", snapshot=True, agent_mode=ss.agent_mode)


# ---------------------------------------------------------------------------
# Callbacks (only mutate state; heavy work happens in process_op)
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
        ss.toast = ("Write the correction first.", "⚠️")
        return
    target = ss.get("corr_target") or ""
    target = "" if target.startswith("(") else target.split(" ")[0]
    _add_action(UserAction(action_type="correct", note=note, target=target, scenario_time=ss.record.phase))
    ss.op = ("start", "user_correction", f"Correction{' to ' + target if target else ''}: {note}")


def cb_redirect() -> None:
    note = (ss.get("redir_note") or "").strip()
    target = ss.get("redir_doc") or ""
    target = "" if target.startswith("(") else target.split(" ")[0]
    if not note and not target:
        ss.toast = ("Say where the investigation should focus.", "⚠️")
        return
    note = note or f"Look again at {target}"
    _add_action(UserAction(action_type="redirect", note=note, target=target, scenario_time=ss.record.phase))
    ss.op = ("start", "user_redirect", f"Redirect: {note}")


def cb_reinvestigate() -> None:
    ss.op = ("start", "reinvestigate", "Practitioner requested a re-investigation.")


def cb_investigate_new() -> None:
    log("investigate_new_records_clicked")
    ss.op = ("start", "new_records", "Records D07–D08 became available at 09:35.")


def cb_step_mode() -> None:
    kind = "pause" if ss.step_mode else "resume"
    _add_action(UserAction(action_type=kind, note="Step-by-step mode " + ("on" if ss.step_mode else "off"), scenario_time=ss.record.phase))


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
    ss.toast = ("New records available (09:35)", "🕤")


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
    log("session_start", snapshot=True, agent_mode=ss.agent_mode)
    ss.toast = (f"New session for participant {pid}", "🧪")


def cb_retry_mock() -> None:
    ss.agent_mode = "mock"
    ss.agent_error = None
    log("agent_mode_change", mode="mock", reason="retry_after_error")


# ---------------------------------------------------------------------------
# Running the agent
# ---------------------------------------------------------------------------


def _log_step(s: ToolCallLog) -> None:
    log("agent_step", step=s.model_dump())


def _finalize(run: AgentRun) -> None:
    with st.spinner("Writing the revised account…"):
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
    log("revision", snapshot=True, trigger=rev.trigger, mode=rev.agent_mode, stopping_reason=rev.stopping_reason)
    if ss.view != "Situation":
        log("view_change", view="Situation", from_view=ss.view, via="auto_after_revision")
    ss.view = ss.last_view = "Situation"
    ss.focus_doc = None
    ss.toast = (f"Account revised to v{new.version}", "✨")


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
        log("agent_run_start", trigger=trigger, note=note, mode=run.mode, step_mode=ss.step_mode, max_steps=ss.max_steps)
        if ss.step_mode:
            return
        kind = "run_to_end"

    run: Optional[AgentRun] = ss.active_run
    if run is None:
        return
    if kind == "step":
        with st.spinner("Agent is taking one step…"):
            for s in run.step():
                _log_step(s)
    elif kind == "run_to_end":
        with st.status(f"Investigating ({MODE_LABEL[run.mode]})…", expanded=True) as status:
            def on_step(s: ToolCallLog) -> None:
                _log_step(s)
                status.write(f"**{s.step}.** `{s.tool}` {fmt_args(s)} → {s.status}  \n_{s.thought}_")
            run.run_to_end(on_step=on_step)
            status.update(label="Investigation finished, writing the account…", state="complete")
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
    last = rec.latest_revision
    st.markdown(
        f"""
<div class="hero">
  <div class="eyebrow">Stay in the Know · Inquiry workspace · Project Aurora</div>
  <h1>{E(rec.question)}</h1>
  <div class="chips">
    <span class="chip clock">🕘 Scenario time {rec.phase}</span>
    <span class="chip">Account v{rec.version}</span>
    <span class="chip rel-{rec.reliance}">D01 for external review: {RELIANCE_LABEL[rec.reliance]}</span>
    <span class="chip">Records available {n_avail}/{len(load_records())}</span>
    <span class="chip">Last revision by {MODE_LABEL.get(last.agent_mode, last.agent_mode) if last else '–'}</span>
  </div>
</div>""",
        unsafe_allow_html=True,
    )
    if rec.phase == "09:35" and "D07" not in rec.retrievals and ss.active_run is None:
        c1, c2 = st.columns([3.2, 1.5], vertical_alignment="center")
        c1.markdown(
            '<div class="newrec">🕤 <b>2 new records available (09:35).</b> The current account has not considered them yet.</div>',
            unsafe_allow_html=True,
        )
        c2.button("Investigate new records", key="btn_investigate_new", type="primary", on_click=cb_investigate_new, use_container_width=True)


# ---------------------------------------------------------------------------
# Rendering: Situation
# ---------------------------------------------------------------------------


def section(title: str, dp: str = "") -> None:
    dp_html = f'<span class="dp">{dp}</span>' if dp else ""
    st.markdown(f'<div class="section-title">{E(title)} {dp_html}</div>', unsafe_allow_html=True)


def render_changed(rec: InquiryRecord) -> None:
    rev = rec.latest_revision
    if not rev or rev.version <= 1:
        return
    bullets = "".join(f"<li>{E(b)}</li>" for b in rev.what_changed)
    st.markdown(
        f"""<div class="changed"><h3>What changed in v{rev.version}</h3>
<div class="meta-line">Trigger: <b>{E(TRIGGER_LABEL.get(rev.trigger, rev.trigger))}</b> · {E(rev.trigger_note)} · by {MODE_LABEL.get(rev.agent_mode, rev.agent_mode)} at scenario time {rev.scenario_time[-8:-3]}</div>
<ul>{bullets}</ul></div>""",
        unsafe_allow_html=True,
    )
    if rev.changed_claims:
        with st.expander(f"Claim-level changes ({len(rev.changed_claims)}) compared with v{rev.version - 1}"):
            rows = []
            for ch in rev.changed_claims:
                if ch.change == "added":
                    rows.append(f'<div class="qual"><span class="badge b-new">added</span><b>{ch.claim_id}</b> <span class="diff-added">{E(ch.after)}</span></div>')
                elif ch.change == "withdrawn":
                    rows.append(f'<div class="qual"><span class="badge b-invalid">withdrawn</span><b>{ch.claim_id}</b> <span class="diff-withdrawn">{E(ch.before)}</span></div>')
                else:
                    before = f'<div class="diff-before">{E(ch.before)}</div>' if ch.before != ch.after else '<div class="meta-line">(wording unchanged; basis or qualifications changed)</div>'
                    rows.append(f'<div class="qual"><span class="badge b-rev">revised</span><b>{ch.claim_id}</b>{before}<div>{E(ch.after)}</div></div>')
            st.markdown("".join(rows), unsafe_allow_html=True)


def render_claim(c: Claim, rec: InquiryRecord) -> None:
    rev = rec.latest_revision
    change = None
    if rev and rev.version > 1:
        change = next((ch.change for ch in rev.changed_claims if ch.claim_id == c.id), None)
    label, cls = CLAIM_BADGE[c.claim_type]
    tag = ""
    if change == "added":
        tag = f'<span class="badge b-new">new in v{rev.version}</span>'
    elif change == "revised":
        tag = f'<span class="badge b-rev">revised in v{rev.version}</span>'
    conflicts = "".join(
        f'<div class="conflict">⚖️ <b>Conflict {E(" vs ".join(cf.doc_ids))}:</b> {E(cf.note)}</div>' for cf in c.conflicts
    )
    quals = "".join(f'<div class="qual">{E(q)}</div>' for q in c.qualifications)
    with st.container(key=f"card-claim-{c.id}-v{rec.version}"):
        st.markdown(
            f'<span class="badge b-id">{c.id}</span><span class="badge {cls}">{label}</span>{tag}'
            f'<div class="claim-text">{E(c.text)}</div>{conflicts}{quals}',
            unsafe_allow_html=True,
        )
        if c.citations:
            key = f"cite-{c.id}-v{rec.version}"
            st.pills("Sources", c.citations, key=key, on_change=cb_citation, args=(key, c.id),
                     label_visibility="collapsed", format_func=lambda d: f"📄 {d}")
        else:
            st.markdown('<div class="meta-line" style="margin-bottom:.4rem">No record cited</div>', unsafe_allow_html=True)


def render_projection(p: Projection, rec: InquiryRecord) -> None:
    status_badge = {"active": ("Active", "b-active"), "invalidated": ("Invalidated", "b-invalid"), "retired": ("Retired", "b-retired")}[p.status]
    assumptions = "".join(f'<div class="assume">{E(a)}</div>' for a in p.assumptions)
    inval = ""
    if p.status != "active":
        by = f" by {E(', '.join(p.invalidated_by))}" if p.invalidated_by else ""
        inval = f'<div class="invalid-box"><b>{status_badge[0]}{by}.</b> {E(p.invalidation_reason)}</div>'
    since = f'<span class="meta-line"> · since v{p.since_version}</span>' if p.since_version else ""
    based = f'<div class="meta-line" style="margin-top:.45rem">Based on {E(", ".join(p.based_on))}</div>' if p.based_on else ""
    with st.container(key=f"card-proj-{p.id}-v{rec.version}"):
        st.markdown(
            f'<div class="{"invalid" if p.status != "active" else ""}">'
            f'<span class="badge b-id">{p.id}</span><span class="badge {status_badge[1]}">{status_badge[0]}</span>{since}'
            f'<div class="outcome">{E(p.outcome)}</div>'
            f'<div class="meta-line" style="margin:.2rem 0">Holds only if:</div>{assumptions}{inval}{based}</div>',
            unsafe_allow_html=True,
        )


def render_situation(rec: InquiryRecord) -> None:
    render_changed(rec)

    with st.container(key=f"card-summary-v{rec.version}"):
        st.markdown(
            f'<span class="badge rel-{rec.reliance}" style="border:1px solid">{RELIANCE_LABEL[rec.reliance]}</span>'
            f'<div class="summary" style="margin-top:.5rem">{E(rec.situation_summary)}</div>'
            f'<div class="assess"><b>Assessment:</b> {E(rec.overall_assessment)}</div>',
            unsafe_allow_html=True,
        )

    section("Claims and their basis", "DP2")
    st.markdown(
        '<div class="legend"><span class="badge b-direct">Direct record</span> stated in a record · '
        '<span class="badge b-inference">Agent inference</span> reasoned by the agent · '
        '<span class="badge b-user">Practitioner input</span> from your corrections · click 📄 to open the source</div>',
        unsafe_allow_html=True,
    )
    for c in rec.claims:
        render_claim(c, rec)

    rev = rec.latest_revision
    if rev and rev.competing_hypotheses:
        with st.expander(f"Competing explanations ({len(rev.competing_hypotheses)})", icon="🔀"):
            for h in rev.competing_hypotheses:
                st.markdown(
                    f'<div class="limit"><span class="badge b-id">{h.id}</span>{E(h.explanation)}'
                    f'<div class="qual">Supports: {E(", ".join(h.supporting) or "–")}</div>'
                    f'<div class="qual">Against: {E(", ".join(h.against) or "–")}</div>'
                    f'<div class="qual"><b>Would resolve:</b> {E(h.what_would_resolve)}</div></div>',
                    unsafe_allow_html=True,
                )

    section("Projections and their conditions", "DP4")
    active = [p for p in rec.projections if p.status == "active"]
    inactive = [p for p in rec.projections if p.status != "active"]
    cols = st.columns(2)
    for i, p in enumerate(active + inactive):
        with cols[i % 2]:
            render_projection(p, rec)

    section("Limits and unresolved points", "DP5")
    groups = [
        ("search_gap", "🔍 Search limits", "Searched, but nothing was found"),
        ("conflict", "⚖️ Unresolved conflicts", "Records disagree"),
        ("tacit_knowledge", "👤 Needs a person", "Cannot be settled from records alone"),
    ]
    cols = st.columns(3)
    for col, (typ, title, sub) in zip(cols, groups):
        items = [l for l in rec.limitations if l.type == typ]
        body = "".join(
            f'<div class="limit">{E(l.description)}'
            + (f'<span class="owner">→ {E(l.unresolved_owner)}</span>' if l.unresolved_owner else "")
            + (f'<div class="meta-line">{E(", ".join(l.related_docs))}</div>' if l.related_docs else "")
            + "</div>"
            for l in items
        ) or '<div class="meta-line">None recorded.</div>'
        col.markdown(f'<div class="limit-col"><h4>{title}</h4><div class="meta-line" style="margin:-.3rem 0 .5rem">{sub}</div>{body}</div>', unsafe_allow_html=True)
    if rev:
        st.markdown(f'<div class="stopbar">⏹ <b>Why the agent stopped:</b> {E(rev.stopping_reason)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Rendering: Evidence
# ---------------------------------------------------------------------------


def render_evidence(rec: InquiryRecord) -> None:
    records = load_records()
    if ss.focus_doc:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(f'<div class="meta-line">Opened from a citation: <b>{E(ss.focus_doc)}</b></div>', unsafe_allow_html=True)
        c2.button("← Back to Situation", key="btn_back", on_click=cb_back_to_situation, use_container_width=True)

    section("Records and their context", "DP1")
    order = sorted(records, key=lambda d: (d != ss.focus_doc, d))
    for doc_id in order:
        r = records[doc_id]
        if not is_released(r, rec.phase):
            with st.container(key=f"card-locked-{doc_id}"):
                st.markdown(f'<div class="rec-head"><span class="badge b-id">{doc_id}</span><span class="rec-title">🔒 Not yet available</span>'
                            f'<span class="chip">available from {r.release_phase}</span></div><div style="height:.5rem"></div>', unsafe_allow_html=True)
            continue
        focus = doc_id == ss.focus_doc
        retrieved = rec.retrievals.get(doc_id)
        cited_by = [c.id for c in rec.claims if doc_id in c.citations]
        defs = "".join(f'<div class="defn"><b>{E(d.term)}:</b> {E(d.meaning)}</div>' for d in r.definitions)
        ctx = f'<div class="ctx">⚠️ {E(r.context_note)}</div>' if r.context_note else ""
        with st.container(key=f"card-{'focus' if focus else 'rec'}-{doc_id}-v{rec.version}"):
            st.markdown(
                f"""<div class="rec-head"><span class="badge b-id">{doc_id}</span><span class="rec-title">{E(r.title)}</span><span class="chip">{E(r.source_type)}</span></div>
<div class="meta-grid">
  <div><span>Source system</span>{E(r.source_system)}</div>
  <div><span>Author / role</span>{E(r.author_role)}</div>
  <div><span>Record last updated</span>{fmt_ts(r.updated_at)} · {age(r.updated_at, rec.phase)}</div>
  <div><span>Retrieved by agent</span>{('at scenario time ' + retrieved[-8:-3]) if retrieved else 'Not yet read'}</div>
  <div><span>Depends on</span>{E(', '.join(r.dependencies) or '–')}</div>
  <div><span>Cited by claims</span>{E(', '.join(cited_by) or '–')}</div>
</div>{ctx}{('<div class="meta-line" style="margin-top:.4rem">Team-specific definitions</div>' + defs) if defs else ''}""",
                unsafe_allow_html=True,
            )
            with st.expander("Full record", expanded=focus):
                st.markdown(f'<div class="content">{E(r.content)}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Rendering: Investigation
# ---------------------------------------------------------------------------


def timeline_html(steps: List[ToolCallLog]) -> str:
    out = []
    for s in steps:
        if s.tool == "conclude":
            call = '<div class="call">■ conclude</div>'
        else:
            call = f'<div class="call">{E(s.tool)}({E(fmt_args(s))})<span class="st-pill {STATUS_CLASS.get(s.status, "s-warn")}">{E(s.status)}</span></div>'
        thought = f'<div class="thought">{E(s.thought)}</div>' if s.thought else ""
        obs = f'<div class="obs">→ {E(s.observation_summary)}</div>' if s.observation_summary else ""
        out.append(f'<div class="tstep"><div class="tnum">{s.step}</div><div>{thought}{call}{obs}</div></div>')
    return "".join(out) or '<div class="meta-line">No steps yet.</div>'


def render_investigation(rec: InquiryRecord) -> None:
    run: Optional[AgentRun] = ss.active_run
    if run is not None:
        section("Investigation in progress", "DP6")
        st.markdown(timeline_html(run.steps), unsafe_allow_html=True)

    section("Investigation trace by version", "DP3 · DP5")
    for rev in reversed(rec.revisions):
        steps = [s for s in rec.tool_log if s.version == rev.version]
        call_word = "tool call" if rev.tool_calls == 1 else "tool calls"
        title = f"v{rev.version} · {TRIGGER_LABEL.get(rev.trigger, rev.trigger)} · {rev.tool_calls} {call_word} · {MODE_LABEL.get(rev.agent_mode, rev.agent_mode)}"
        with st.expander(title, expanded=rev.version == rec.version):
            st.markdown(
                f'<div class="meta-line">{E(rev.trigger_note)}</div>{timeline_html(steps)}'
                f'<div class="stopbar">⏹ {E(rev.stopping_reason)}</div>',
                unsafe_allow_html=True,
            )

    section("Your direction history", "DP6")
    acts = [a for a in rec.user_actions]
    if acts:
        st.dataframe(
            [
                {
                    "Time": a.timestamp[-8:],
                    "Scenario": a.scenario_time,
                    "Action": a.action_type,
                    "Target": a.target or "–",
                    "Note": a.note,
                    "Applied in": f"v{a.applied_in_version}" if a.applied_in_version else ("–" if a.action_type in ("pause", "resume") else "pending"),
                }
                for a in acts
            ],
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.markdown('<div class="meta-line">No corrections or redirects yet.</div>', unsafe_allow_html=True)

    if rec.history:
        section("Earlier versions of the account", "DP3")
        versions = [h["version"] for h in rec.history]
        v = st.selectbox("Show version", versions, index=len(versions) - 1, format_func=lambda x: f"v{x}", key="hist_v")
        snap = InquiryRecord.model_validate(next(h for h in rec.history if h["version"] == v))
        if ss.get("_last_hist_v") != v:
            ss["_last_hist_v"] = v
            log("view_earlier_version", shown_version=v)
        st.markdown(
            f'<div class="limit"><span class="badge rel-{snap.reliance}" style="border:1px solid">{RELIANCE_LABEL[snap.reliance]}</span>'
            f'<div class="summary" style="font-size:.92rem;margin-top:.4rem">{E(snap.situation_summary)}</div></div>'
            + "".join(f'<div class="qual"><b>{c.id}</b> {E(c.text)}</div>' for c in snap.claims)
            + "".join(f'<div class="qual"><b>{p.id}</b> [{p.status}] {E(p.outcome)}</div>' for p in snap.projections),
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Rendering: direction panel (DP6)
# ---------------------------------------------------------------------------


def render_direction_panel(rec: InquiryRecord) -> None:
    run: Optional[AgentRun] = ss.active_run
    with st.container(key="panel-direct"):
        st.markdown('<div class="section-title" style="margin-top:0">Direct the inquiry <span class="dp">DP6</span></div>', unsafe_allow_html=True)

        if ss.agent_error:
            st.error(f"The agent could not complete the revision. The account is unchanged.\n\n{ss.agent_error}")
            st.button("Use scripted agent instead", key="btn_retry_mock", on_click=cb_retry_mock, use_container_width=True)

        if run is not None:
            st.markdown(f'<div class="meta-line">Step-by-step investigation · {run.tool_calls}/{run.max_steps} tool calls · {MODE_LABEL[run.mode]}</div>', unsafe_allow_html=True)
            st.markdown(timeline_html(run.steps[-3:]), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            c1.button("Next step ▶", key="btn_step", on_click=cb_run_op, args=("step",), type="primary", use_container_width=True)
            c2.button("Run to end ⏩", key="btn_run_end", on_click=cb_run_op, args=("run_to_end",), use_container_width=True)
            st.button("Stop and write account ⏹", key="btn_stop", on_click=cb_run_op, args=("stop",), use_container_width=True)
            st.text_input("Add direction for the next step", key="mid_dir", placeholder="e.g. check who owns the certificate", on_change=cb_mid_direction)
            return

        t_corr, t_redir = st.tabs(["✎ Correct", "➜ Redirect"])
        with t_corr:
            with st.form("form_correct", clear_on_submit=True, border=False):
                st.selectbox(
                    "What are you correcting?",
                    ["(the account in general)"] + [f"{c.id} – {c.text[:60]}…" for c in rec.claims],
                    key="corr_target",
                )
                st.text_area("Your correction", key="corr_note", height=90,
                             placeholder="e.g. Security took over certificate renewals last week.")
                st.form_submit_button("Submit correction", type="primary", on_click=cb_correction, use_container_width=True)
        with t_redir:
            with st.form("form_redirect", clear_on_submit=True, border=False):
                st.text_input("Focus the investigation on…", key="redir_note", placeholder="e.g. whether UAT can still start on 12 March")
                st.selectbox("Specific record (optional)", ["(any record)"] + [d for d, r in load_records().items() if is_released(r, rec.phase)], key="redir_doc")
                st.form_submit_button("Redirect investigation", type="primary", on_click=cb_redirect, use_container_width=True)

        st.button("↻ Re-investigate now", key="btn_reinvestigate", on_click=cb_reinvestigate, use_container_width=True)
        st.toggle("Step-by-step (pause after each agent step)", key="step_mode", on_change=cb_step_mode)

        recent = [a for a in rec.user_actions if a.action_type in ("correct", "redirect")][-3:]
        if recent:
            st.markdown('<div class="meta-line" style="margin-top:.6rem">Your recent direction (kept across revisions)</div>', unsafe_allow_html=True)
            for a in reversed(recent):
                applied = f"applied in v{a.applied_in_version}" if a.applied_in_version else "pending"
                st.markdown(f'<div class="limit"><span class="badge b-user">{a.action_type}</span>{E(a.note)}<div class="meta-line">{applied}</div></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Researcher sidebar
# ---------------------------------------------------------------------------


def render_sidebar(rec: InquiryRecord) -> None:
    sb = st.sidebar
    sb.markdown("### 🔬 Researcher control")
    sb.caption("Not part of the practitioner interface. Keep this sidebar collapsed during interviews.")

    with sb.expander("Session", expanded=True):
        st.text_input("Participant ID", value=ss.participant_id, key="pid_input")
        st.button("Start new participant session", key="btn_new_session", on_click=cb_new_session, use_container_width=True)
        st.caption(f"Logging to `logs/{ss.logger.path.name}`")

    with sb.expander("Scenario", expanded=True):
        st.button("Release 09:35 records (D07–D08)", key="btn_release", on_click=cb_release, disabled=rec.phase == "09:35",
                  type="primary", use_container_width=True)
        if ss.released_at:
            st.caption(f"Released at {ss.released_at} (wall clock)")
        st.button("Reset to 09:15 baseline", key="btn_reset", on_click=cb_reset, use_container_width=True)

    with sb.expander("Agent"):
        has_key = bool(get_api_key())
        st.radio("Agent mode", ["mock", "gemini"], key="agent_mode", format_func=lambda m: MODE_LABEL[m].capitalize(),
                 on_change=lambda: log("agent_mode_change", mode=ss.agent_mode))
        if ss.agent_mode == "gemini" and not has_key:
            st.warning("No GEMINI_API_KEY found (environment, .env or .streamlit/secrets.toml). Runs will fail; use the scripted agent.")
        st.text_input("Gemini model", key="model")
        st.slider("Max tool calls per run", 2, 12, key="max_steps")

    with sb.expander("Export", expanded=True):
        st.download_button("Download session log (JSON)", ss.logger.to_json(), file_name=ss.logger.path.name,
                           mime="application/json", use_container_width=True, on_click="ignore")
        st.download_button("Download current account (JSON)", rec.model_dump_json(indent=2), file_name=f"inquiry_v{rec.version}.json",
                           mime="application/json", use_container_width=True, on_click="ignore")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    init_state()
    process_op()
    if ss.toast:
        msg, icon = ss.toast
        st.toast(msg, icon=icon)
        ss.toast = None

    rec: InquiryRecord = ss.record
    render_sidebar(rec)
    render_header(rec)

    left, right = st.columns([2.5, 1.35], gap="large")
    with left:
        st.segmented_control(
            "View", ["Situation", "Evidence", "Investigation"], key="view", on_change=cb_view_change,
            label_visibility="collapsed",
            format_func=lambda v: {"Situation": "🧭 Situation", "Evidence": "📄 Evidence", "Investigation": "🔎 Investigation"}[v],
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
