# Situational Awareness – Prototype

A lightweight Python + Streamlit research prototype designed for formative evaluation interviews (FEDS) around Design Principles **DP1–DP6**.

It uses a **hybrid execution model**:
- **Deterministic 09:15 baseline ([baseline_0915.json](baseline_0915.json)):** Every participant starts from the exact same cached investigation over records `D01–D06`.
- **Live constrained ReAct agent ([agent.py](agent.py)):** Handles practitioner corrections, redirects, and the `09:35` release (`D07–D08`) using `google-genai` tool calling and structured Pydantic outputs (with a deterministic scripted `Mock` fallback for offline pilots).

---

## Quick Start

### 1. Create the virtual environment (Python 3.12+)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Provide your Gemini API key (recommended for a public repo)

To ensure your API key can never be accidentally committed, set it as a shell environment variable in the terminal before launching Streamlit:

```bash
export GEMINI_API_KEY="your-key-here"
```

*(Optional)* You can also override the model or step budget:

```bash
export GEMINI_MODEL="gemini-3.8-flash"
export AGENT_MAX_STEPS="8"
```

> **Note:** Without `GEMINI_API_KEY`, the app automatically starts in **Scripted (offline)** mode so you can test the UI and run offline pilots. `.env` and `.streamlit/secrets.toml` are both listed in `.gitignore`, though using a terminal environment variable keeps secrets out of the repo folder altogether.

### 3. Run the app

```bash
streamlit run app.py
```

---

## How Evidence Tools & Agentic Calls Work

The prototype separates **deterministic evidence access** (`tools.py`), **bounded agent orchestration** (`agent.py`), and **state transitions** (`state.py`) so every step of an investigation is inspectable and interruptible.

### 1. Phase-Filtered Evidence Tools (`tools.py`)
The agent has access to only two local Python functions, declared to the model via `TOOL_DECLARATIONS` and filtered by the current scenario phase (`09:15` exposes `D01–D06`; `09:35` unlocks `D07–D08`):

- **`search_passages(query)`** — Runs BM25 keyword retrieval (`rank_bm25`) over paragraph chunks and team-specific definitions from currently released records, requiring genuine term overlap.
- **`read_record(doc_id)`** — Returns the full content and DP1 metadata (`source_system`, `author_role`, `updated_at`, `definitions`, `dependencies`, `context_note`) of a single record.

Every tool call returns a structured `status` field (`found`, `no_matches`, `not_available`, `not_found`, or `tool_error`). This allows both the agent and the practitioner to distinguish an empty search (`no_matches`, which is evidence of absence only within the available records) from an unreleased document (`not_available`, without leaking its title or content) or a tool failure (`tool_error`).

### 2. Constrained, Resumable ReAct Loop (`agent.py`)
Each investigation runs inside an `AgentRun` object wrapping a `Provider` (`GeminiProvider` for live calls or `MockProvider` for offline/scripted runs):

1. **Context initialization (`start`)** — The agent receives the inquiry question, scenario clock, trigger reason, a metadata-only catalogue of currently available records, the current `InquiryRecord` (claims, projections, limitations, competing hypotheses), and all persistent practitioner corrections/redirects.
2. **Manual function-calling turns (`step`)** — In `GeminiProvider`, `google-genai` automatic function calling is explicitly disabled (`AutomaticFunctionCallingConfig(disable=True)`). On each turn, the model emits a short rationale plus zero or more function calls (`search_passages` / `read_record`). `AgentRun` enforces the tool-call budget (`max_steps`), executes each tool locally via `execute_tool()`, appends a `ToolCallLog` entry for the **Investigation** view, and feeds the tool responses back to the model via `Part.from_function_response(...)`.
3. **Practitioner control mid-run (DP6)** — Because `AgentRun.step()` advances one turn at a time, the UI's **Step-by-step** toggle lets the practitioner pause after every turn, inject a mid-run redirect (`add_direction()`), or stop the run early (`stop()`).
4. **Termination & stopping reason (DP5)** — The loop ends when the model stops calling tools (`CONCLUDE: ...`), reaches `max_steps`, encounters an error, or is stopped by the practitioner. The exact stopping reason is recorded on the revision.
5. **Structured JSON synthesis (`final_output`)** — Once the investigation loop finishes, a dedicated generation call produces JSON validated against the Pydantic `AgentRevisionOutput` schema (using `response_schema`, with a `response_json_schema` fallback and one validation retry). On transient `503` load spikes, `GeminiProvider` automatically falls back from `gemini-3.8-flash` to `gemini-3.5-flash-lite` before surfacing a recoverable error.

### 3. Revision Merging & Auditability (`state.py`)
`merge_revision()` folds the validated `AgentRevisionOutput` into a new `InquiryRecord` version without erasing prior state:
- Snapshots the previous version into `record.history` (viewable in **Investigation → Earlier versions**).
- Computes structured `ClaimChange` diffs (`added`, `revised`, `withdrawn`) for the **Changes in vN** banner (DP3).
- Retains invalidated or retired projections alongside active ones so broken assumptions stay visible (DP4).
- Marks pending practitioner corrections/redirects as applied **only** when listed in `output.addressed_user_actions`; any unaddressed item is flagged as `not addressed in vN` and kept pending for the next run (DP6).
- Records `model_name` and `models_used` on every `Revision` (including fallback transitions) and logs the full snapshot via `EventLogger` (Chapter 5 traceability).

---

## Architecture & Mapping to DP1–DP6

| File | Role |
|---|---|
| `app.py` | Three-view practitioner interface (**Situation**, **Evidence**, **Investigation**), persistent **Direction** panel (DP6), and collapsible **Researcher controls** sidebar. |
| `state.py` | Pydantic v2 schemas (`InquiryRecord`, `Claim`, `Projection`, `Revision`, `Limitation`, `UserAction`, `ToolCallLog`), `merge_revision` history/invalidation logic, and `EventLogger`. |
| `agent.py` | Step-wise, resumable ReAct investigation loop (`GeminiProvider` and `MockProvider`) with configurable tool-call budget, pre-interview API check, and structured JSON validation. |
| `tools.py` | Phase-filtered `search_passages` (BM25) and `read_record` tools returning explicit statuses (`found`, `no_matches`, `not_available`, `not_found`, `tool_error`). |
| `records/D01_*.json` … `D08_*.json` | Eight neutral release-3.2 scenario records split into `09:15` (`D01–D06`) and `09:35` (`D07–D08`; hidden until released). |
| `baseline_0915.json` | Cached deterministic `09:15` baseline loaded at session start and reset. Rebuild via `python scripts/build_baseline.py`. |
| `logs/` | Auto-saved `participant_<id>_<session>.json` event logs with full `InquiryRecord` snapshots (gitignored). |

---

## Interview Protocol Checklist

1. **Before the participant arrives:**
   - Open the **Researcher controls** sidebar (`>` top-left).
   - Enter the **Participant ID** (e.g. `P01`) and click **New session**.
   - Confirm **Mode** is set to **Live Gemini** (scripted mode is for offline demos only and cannot evaluate corrections) and click **Check API connection**.
   - Collapse the sidebar so only the practitioner interface is visible.
2. **Phase 1 (`09:15` baseline):**
   - Let the participant inspect **Situation**, click inline record citations (`D01`–`D06`) into **Evidence**, inspect **Investigation**, and optionally submit a correction or redirect.
3. **Phase 2 (`09:35` expectation violation):**
   - Briefly open the sidebar and click **Release 09:35 (D07–D08)**, then collapse the sidebar.
   - A notification bar appears in the practitioner view; let the participant decide when to click **Investigate** (or use **Step-by-step** mode).
4. **After the interview:**
   - Open the sidebar and click **Session log (JSON)** (a copy is also continuously flushed to `logs/participant_<id>_<session>.json`).
   - Click **Reset to 09:15** (or start a **New session**) for the next participant.

---

## Running Tests

```bash
.venv/bin/python -m pytest
```
