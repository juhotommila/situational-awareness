import json

from agent import AgentRun, MockProvider, build_curated_baseline
from state import AgentRevisionOutput, EventLogger, InquiryRecord, UserAction, merge_revision
from tools import load_records, read_record, released_ids, search_passages


# --- records & tools ---------------------------------------------------------

def test_eight_records_load():
    recs = load_records()
    assert sorted(recs) == [f"D0{i}" for i in range(1, 9)]


def test_records_use_neutral_language():
    recs = load_records()
    combined = "\n".join(json.dumps(r.model_dump()) for r in recs.values())
    for forbidden in ("Aurora", "Meridian", "Payline", "steering-group", "board pack"):
        assert forbidden not in combined, f"Found {forbidden!r} in scenario records"


def test_phase_filtering_hides_late_records():
    assert released_ids("09:15") == ["D01", "D02", "D03", "D04", "D05", "D06"]
    assert read_record("D07", "09:15")["status"] == "not_available"
    assert "record" not in read_record("D07", "09:15")
    assert read_record("D07", "09:35")["status"] == "found"
    res = search_passages("401 Unauthorized", "09:15")
    assert res["status"] == "no_matches"
    assert search_passages("401 Unauthorized", "09:35")["results"][0]["doc_id"] == "D07"


def test_tool_statuses():
    assert search_passages("", "09:15")["status"] == "tool_error"
    assert read_record("D99", "09:15")["status"] == "not_found"
    assert search_passages("contract tests skipped", "09:15")["status"] == "found"


# --- schemas & baseline ---------------------------------------------------------

def test_baseline_roundtrip():
    rec = build_curated_baseline()
    assert rec.version == 1 and rec.history == []
    assert rec.latest_revision.model_name == "curated-baseline"
    again = InquiryRecord.model_validate_json(rec.model_dump_json())
    assert again == rec
    assert set(rec.retrievals) == {"D01", "D02", "D03", "D04", "D05", "D06"}


def test_committed_baseline_matches_curated():
    from pathlib import Path

    committed = InquiryRecord.model_validate_json(Path("baseline_0915.json").read_text())
    curated = build_curated_baseline()
    assert committed == curated, "baseline_0915.json is stale: run python scripts/build_baseline.py"


def test_agent_output_schema_is_json_serialisable():
    json.dumps(AgentRevisionOutput.model_json_schema())


# --- agent + merge -------------------------------------------------------------

def _release(rec: InquiryRecord) -> InquiryRecord:
    rec = rec.model_copy(deep=True)
    rec.phase = "09:35"
    return rec


def test_mock_0935_invalidates_projection_and_keeps_history():
    base = _release(build_curated_baseline())
    run = AgentRun(base, trigger="new_records", provider=MockProvider(), max_steps=8)
    run.run_to_end()
    new = run.finalize()
    assert new.version == 2
    assert len(new.history) == 1 and new.history[0]["version"] == 1
    assert new.latest_revision.model_name == "mock-scripted"
    assert new.latest_revision.models_used == ["mock-scripted"]
    p1 = next(p for p in new.projections if p.id == "P1")
    assert p1.status == "invalidated" and "D07" in p1.invalidated_by
    assert any(p.id == "P3" and p.since_version == 2 for p in new.projections)
    assert new.reliance == "not_reliable"
    changes = {c.claim_id: c.change for c in new.latest_revision.changed_claims}
    assert changes["C7"] == "added" and changes["C3"] == "revised"
    assert "D07" in new.retrievals


def test_step_budget_is_enforced():
    base = _release(build_curated_baseline())
    run = AgentRun(base, trigger="new_records", provider=MockProvider(), max_steps=2)
    run.run_to_end()
    assert run.tool_calls == 2
    assert "limit" in run.stopping_reason


def test_correction_persists_and_is_applied():
    base = build_curated_baseline()
    base.user_actions.append(UserAction(id="A1", action_type="correct", target="C6",
                                        note="Security team took over certificate renewals last week."))
    run = AgentRun(base, trigger="user_correction", provider=MockProvider())
    run.run_to_end()
    v2 = run.finalize()
    assert any(c.claim_type == "user_provided" for c in v2.claims)
    assert any("Disputed by the practitioner" in q for q in v2.claim("C6").qualifications)
    assert v2.user_actions[0].applied_in_version == 2
    assert v2.user_actions[0].not_addressed_in_versions == []
    assert v2.latest_revision.addressed_user_actions == ["A1"]
    assert v2.latest_revision.unaddressed_user_actions == []
    assert v2.pending_actions() == []

    # Correction claim must survive a subsequent 09:35 revision as well.
    run2 = AgentRun(_release(v2), trigger="new_records", provider=MockProvider())
    run2.run_to_end()
    v3 = run2.finalize()
    assert any(c.claim_type == "user_provided" and "Security team" in c.text for c in v3.claims)


def test_unaddressed_correction_stays_pending_and_is_flagged():
    base = build_curated_baseline()
    base.user_actions.append(UserAction(id="A1", action_type="correct", target="C4",
                                        note="Contract tests actually ran and passed."))
    base.user_actions.append(UserAction(id="A2", action_type="redirect",
                                        note="Check certificate owner."))

    # Model claims to have addressed only A2, ignoring A1.
    out = AgentRevisionOutput(
        situation_summary=base.situation_summary,
        reliance=base.reliance,
        overall_assessment=base.overall_assessment,
        claims=base.claims,
        projections=base.projections,
        limitations=base.limitations,
        competing_hypotheses=base.latest_revision.competing_hypotheses,
        what_changed=["Checked certificate owner."],
        addressed_user_actions=["A2"],
    )
    v2 = merge_revision(
        base,
        out,
        trigger="user_correction",
        trigger_note="Correction test",
        steps=[],
        stopping_reason="Concluded.",
        agent_mode="gemini",
        model_name="gemini-3.5-flash-lite",
        models_used=["gemini-3.8-flash", "gemini-3.5-flash-lite"],
    )

    a1, a2 = v2.user_actions
    assert a1.applied_in_version is None
    assert a1.not_addressed_in_versions == [2]
    assert a2.applied_in_version == 2
    assert a2.not_addressed_in_versions == []
    # A1 remains pending so it is sent to the model again on the next run.
    assert [a.id for a in v2.pending_actions()] == ["A1"]
    assert v2.latest_revision.addressed_user_actions == ["A2"]
    assert v2.latest_revision.unaddressed_user_actions == ["A1"]
    assert v2.latest_revision.model_name == "gemini-3.5-flash-lite"
    assert v2.latest_revision.models_used == ["gemini-3.8-flash", "gemini-3.5-flash-lite"]


def test_stop_by_user():
    base = _release(build_curated_baseline())
    run = AgentRun(base, trigger="new_records", provider=MockProvider())
    run.step()
    run.stop()
    new = run.finalize()
    assert "Stopped by the practitioner" in new.latest_revision.stopping_reason
    assert new.latest_revision.tool_calls == 1


def test_event_logger(tmp_path):
    log = EventLogger("P01", log_dir=tmp_path)
    rec = build_curated_baseline()
    log.log("view_change", record=rec, view="Evidence")
    log.log("revision", record=rec, snapshot=True)
    data = json.loads(log.path.read_text())
    assert data["participant_id"] == "P01"
    assert [e["event"] for e in data["events"]] == ["view_change", "revision"]
    assert data["events"][1]["snapshot"]["version"] == 1
