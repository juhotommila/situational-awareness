# Stay in the Know — Sensemaking Prototype

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

> **Note:** Without `GEMINI_API_KEY`, the app automatically starts in **Scripted agent (Mock)** mode so you can test the UI and run offline pilots. `.env` and `.streamlit/secrets.toml` are both listed in `.gitignore`, though using a terminal environment variable keeps secrets out of the repo folder altogether.

### 3. Run the app

```bash
streamlit run app.py
```

---

## Architecture & Mapping to DP1–DP6

| File | Role |
|---|---|
| `app.py` | Three-view practitioner interface (**Situation**, **Evidence**, **Investigation**), persistent **Direct the inquiry** panel (DP6), and collapsible **Researcher control** sidebar. |
| `state.py` | Pydantic v2 schemas (`InquiryRecord`, `Claim`, `Projection`, `Revision`, `Limitation`, `UserAction`, `ToolCallLog`), `merge_revision` history/invalidation logic, and `EventLogger`. |
| `agent.py` | Step-wise, resumable ReAct investigation loop (`GeminiProvider` and `MockProvider`) with configurable tool-call budget and structured JSON validation. |
| `tools.py` | Phase-filtered `search_passages` (BM25) and `read_record` tools returning explicit statuses (`found`, `no_matches`, `not_available`, `not_found`, `tool_error`). |
| `records/D01_*.json` … `D08_*.json` | The 8 Project Aurora (Release 3.2) scenario records split into `09:15` (`D01–D06`) and `09:35` (`D07–D08`). |
| `baseline_0915.json` | Cached deterministic `09:15` baseline loaded at session start and reset. Rebuild via `python scripts/build_baseline.py`. |
| `logs/` | Auto-saved `participant_<id>_<session>.json` event logs with full `InquiryRecord` snapshots (gitignored). |

---

## Interview Protocol Checklist

1. **Before the participant arrives:**
   - Open the **Researcher control** sidebar (`>` top-left).
   - Enter the **Participant ID** (e.g. `P01`) and click **Start new participant session**.
   - Confirm **Agent mode** (`Live Gemini agent` or `Scripted agent`) and **Max tool calls per run**.
   - Collapse the sidebar so only the practitioner interface is visible.
2. **Phase 1 (`09:15` baseline):**
   - Let the participant inspect **Situation**, click inline `[Dxx]` citations into **Evidence**, inspect **Investigation**, and optionally submit a correction or redirect.
3. **Phase 2 (`09:35` expectation violation):**
   - Briefly open the sidebar and click **Release 09:35 records (D07–D08)**, then collapse the sidebar.
   - A notification banner appears in the practitioner view; let the participant decide when to click **Investigate new records** (or use **Step-by-step** mode).
4. **After the interview:**
   - Open the sidebar and click **Download session log (JSON)** (a copy is also continuously flushed to `logs/participant_<id>_<session>.json`).
   - Click **Reset to 09:15 baseline** (or start a new participant session) for the next participant.

---

## Running Tests

```bash
.venv/bin/python -m pytest
```
