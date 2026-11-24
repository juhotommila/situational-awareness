"""Curated content for the deterministic parts of the prototype.

* `BASELINE_*` – the 09:15 account every participant starts from. It is written
  in exactly the same structure the live agent must produce, so the interface
  behaves identically whether a revision was curated, scripted or live.
* `MOCK_0935_*` – a scripted revision used by the MockAgent when the 09:35
  records are investigated without an API key (pilots, demos, fallback).
"""

from __future__ import annotations

from typing import List

from state import (
    AgentRevisionOutput,
    Claim,
    CompetingHypothesis,
    ConflictNote,
    Limitation,
    Projection,
    ToolCallLog,
)

# ---------------------------------------------------------------------------
# 09:15 baseline
# ---------------------------------------------------------------------------

BASELINE_STEPS: List[ToolCallLog] = [
    ToolCallLog(version=1, step=1, tool="search_passages", args={"query": "release 3.2 status confirmed go-live"},
                status="found", thought="Start from the report in question and anything that states readiness.",
                observation_summary="4 passage(s): D01.1, D01.4, D02.2, D01.def"),
    ToolCallLog(version=1, step=2, tool="read_record", args={"doc_id": "D01"}, status="found",
                thought="Read the status report in full, including how it defines its terms.",
                observation_summary="Read D01 – Weekly Status Report – Project Aurora (Release 3.2) (updated 2025-03-10 17:30)"),
    ToolCallLog(version=1, step=3, tool="read_record", args={"doc_id": "D02"}, status="found",
                thought="D01 lists the billing integration as Confirmed; check the Engineering input it was compiled from.",
                observation_summary="Read D02 – RE: Aurora 3.2 – status inputs for Monday report (updated 2025-03-10 15:48)"),
    ToolCallLog(version=1, step=4, tool="read_record", args={"doc_id": "D03"}, status="found",
                thought="D02 says contract tests would run overnight. Check the pipeline result.",
                observation_summary="Read D03 – CI/CD Pipeline Run – aurora-portal 3.2.0-rc4 (nightly) (updated 2025-03-11 06:05)"),
    ToolCallLog(version=1, step=5, tool="read_record", args={"doc_id": "D05"}, status="found",
                thought="'Confirmed' seems to be used differently by teams. Check the customer-facing definition.",
                observation_summary="Read D05 – Delivery Glossary & Definition of Done (customer projects) (updated 2024-11-05 09:00)"),
    ToolCallLog(version=1, step=6, tool="search_passages", args={"query": "Payline certificate renewal owner"},
                status="found", thought="D01 rates R-14 Low. Look for anything about the certificate and its owner.",
                observation_summary="4 passage(s): D06.1, D04.2, D06.3, D01.3"),
    ToolCallLog(version=1, step=7, tool="read_record", args={"doc_id": "D06"}, status="found",
                thought="Read the infra chat in full to see what is said about ownership.",
                observation_summary="Read D06 – #aurora-infra – chat excerpt (Payline certificate) (updated 2025-03-10 18:22)"),
    ToolCallLog(version=1, step=8, tool="read_record", args={"doc_id": "D04"}, status="found",
                thought="Check the dependency register for credentials and certificate status, and how current it is.",
                observation_summary="Read D04 – Aurora Dependency Register (updated 2025-02-24 11:12)"),
]

BASELINE_STOPPING_REASON = (
    "Agent concluded after 8 of 8 allowed tool calls: all six available records were read. "
    "The remaining questions cannot be answered from the records alone."
)

BASELINE_OUTPUT = AgentRevisionOutput(
    situation_summary=(
        "D01 reports Aurora 3.2 as Green and 'Confirmed' for go-live on 17 March. The supporting records only partly "
        "back this up. 'Confirmed' means different things in different teams. The staging contract tests that would "
        "verify the billing integration end-to-end have not run (D03). A certificate dependency due 20 March has no "
        "clear owner (D06). On current records, D01 can only be used externally with explicit qualifications."
    ),
    reliance="reliable_with_qualifications",
    overall_assessment=(
        "Usable as a starting point, but not as stated: 'Confirmed' and 'Green' in D01 do not meet the Delivery "
        "definitions required for external reporting (D05)."
    ),
    claims=[
        Claim(id="C1", claim_type="direct_record", citations=["D01"],
              text="D01 reports overall status Green and release 3.2 as 'Confirmed' for go-live on 17 March, with no High risks open."),
        Claim(id="C2", claim_type="direct_record", citations=["D02"],
              text="Engineering reported the billing API v2 integration as 'confirmed' because PR #482 was merged with all unit tests passing.",
              qualifications=["D02 itself notes that contract tests against the Meridian sandbox were still to run."]),
        Claim(id="C3", claim_type="agent_inference", citations=["D01", "D02", "D05"],
              text="The 'Confirmed' status for the billing integration in D01 most likely reflects Engineering's meaning (code merged), "
                   "not Delivery's meaning (verified end-to-end and safe to communicate externally).",
              conflicts=[ConflictNote(doc_ids=["D02", "D05"],
                                      note="'Confirmed' = code merged with unit tests (Engineering) vs. verified end-to-end in staging and signed off by QA (Delivery).")],
              qualifications=["Inference: D01 does not say which definition was applied. Its own note says 'reported as done by the team lead'."]),
        Claim(id="C4", claim_type="direct_record", citations=["D03"],
              text="The latest nightly pipeline for rc4 (06:05 today) shows PASSED overall, but the staging contract-test stage was SKIPPED because the environment was locked by a performance test.",
              conflicts=[ConflictNote(doc_ids=["D01", "D03"],
                                      note="D01 lists the integration as Confirmed. The stage that would verify it did not run.")]),
        Claim(id="C5", claim_type="direct_record", citations=["D04", "D06"],
              text="The Payline TLS certificate expires on 20 March. Renewal needs a signed CSR from Meridian, and nobody on our side clearly owns chasing it.",
              qualifications=["D04 is 15 days old.", "D06 is a partial chat export: 2 replies are missing."]),
        Claim(id="C6", claim_type="agent_inference", citations=["D01", "D05", "D06"],
              text="D01's rating of risk R-14 (certificate) as 'Low, handled by Infra' does not match the latest Infra message. Under the Delivery glossary, an unowned go-live risk should be rated at least Medium.",
              conflicts=[ConflictNote(doc_ids=["D01", "D06"],
                                      note="'Handled by Infra' (D01) vs. 'needs client-side action, owner unclear' (D06).")]),
    ],
    projections=[
        Projection(id="P1", based_on=["D01", "D02", "D03", "D04"],
                   outcome="If the staging contract tests pass before 12 March, UAT can start as scheduled and go-live on 17 March remains achievable.",
                   assumptions=["The billing integration works against the Meridian sandbox (unverified: D03 stage skipped).",
                                "Valid v2 sandbox credentials are installed in staging (last known status 'pending', D04, 24 Feb)."]),
        Projection(id="P2", based_on=["D04", "D06"],
                   outcome="If the Payline certificate is renewed before 20 March, card payments keep working at and after go-live.",
                   assumptions=["Someone at Meridian signs the CSR in time.",
                                "Someone on our side is named to chase it."]),
    ],
    limitations=[
        Limitation(id="L1", type="search_gap", related_docs=["D03"],
                   description="No record shows that the staging contract tests have ever passed for any 3.2 release candidate."),
        Limitation(id="L2", type="search_gap", related_docs=["D04"],
                   description="No record newer than 24 Feb gives the status of the Meridian v2 sandbox credentials."),
        Limitation(id="L3", type="conflict", related_docs=["D01", "D02", "D05"],
                   description="'Confirmed' has different meanings in Engineering (D02) and Delivery (D05), and D01 does not say which one it uses."),
        Limitation(id="L4", type="tacit_knowledge", related_docs=["D06"],
                   description="Ownership of the Payline certificate renewal is unclear since the previous security contact left. The chat export is truncated.",
                   unresolved_owner="Infra lead or Security team (needs a person to confirm)"),
        Limitation(id="L5", type="tacit_knowledge", related_docs=["D01"],
                   description="Only the PMO coordinator can confirm whether D01 applied Engineering or Delivery meanings when it was compiled.",
                   unresolved_owner="Project Coordinator, PMO"),
    ],
    competing_hypotheses=[
        CompetingHypothesis(id="H1", explanation="D01 is right in substance: the integration works and only the formal test run is outstanding.",
                            supporting=["D02", "D03 (unit tests pass)"], against=["D03 (contract stage skipped)", "D04 (credentials pending)"],
                            what_would_resolve="A successful staging contract-test run against the Meridian sandbox."),
        CompetingHypothesis(id="H2", explanation="D01 overstates readiness: 'Confirmed' only reflects the code merge, and the integration has not been verified.",
                            supporting=["D02", "D05", "D03 (contract stage skipped)"], against=["No record shows a failure either"],
                            what_would_resolve="Either the contract-test result or confirmation from the PMO coordinator."),
    ],
    what_changed=["Initial account built from records D01–D06 at 09:15."],
)

# ---------------------------------------------------------------------------
# Scripted 09:35 revision (MockAgent)
# ---------------------------------------------------------------------------

MOCK_0935_PLAN = [
    ("Check for new records since the last account.", "search_passages", {"query": "staging contract tests result failed"}),
    ("A new test report exists. Read it in full.", "read_record", {"doc_id": "D07"}),
    ("Check whether there is other new information about credentials or the review.", "search_passages", {"query": "credentials Meridian end of week review"}),
    ("Read the Customer Success message in full.", "read_record", {"doc_id": "D08"}),
    ("Is there any written commitment from Meridian IT on a date?", "search_passages", {"query": "Meridian IT credentials date committed"}),
]

MOCK_0935_STOPPING_REASON = (
    "Agent concluded after 5 tool calls: both new records were read. No written commitment from Meridian IT was found, "
    "and the remaining questions need people, not records."
)


def mock_0935_output(previous_claims: List[Claim]) -> AgentRevisionOutput:
    by_id = {c.id: c for c in previous_claims}
    claims: List[Claim] = []
    for cid in ("C1", "C2"):
        if cid in by_id:
            claims.append(by_id[cid])
    claims.append(
        Claim(id="C3", claim_type="agent_inference", citations=["D01", "D02", "D05", "D07"],
              text="The 'Confirmed' status for the billing integration in D01 reflected Engineering's meaning (code merged). The integration is not verified end-to-end, and a manual run has now failed.",
              conflicts=[ConflictNote(doc_ids=["D01", "D07"], note="'Confirmed' (D01) vs. 7 of 19 contract tests failing (D07).")],
              qualifications=["Now supported by D07. Previously inferred from terminology alone."])
    )
    if "C4" in by_id:
        claims.append(by_id["C4"])
    for cid in ("C5", "C6"):
        if cid in by_id:
            claims.append(by_id[cid])
    claims += [
        Claim(id="C7", claim_type="direct_record", citations=["D07"],
              text="A manual staging contract-test run (09:05–09:26) FAILED: 7 of 19 tests returned 401 Unauthorized on the v2 invoice and payment endpoints. rc4 is BLOCKED for UAT."),
        Claim(id="C8", claim_type="agent_inference", citations=["D04", "D07"],
              text="The likely cause is the v2 sandbox credentials that were still pending in D04: the staging credentials appear to be scoped for v1 only.",
              qualifications=["D07 says the credentials 'appear' to be v1-scoped. Not yet confirmed by Meridian."]),
        Claim(id="C9", claim_type="direct_record", citations=["D08"],
              text="Customer Success reports, second-hand, that Meridian IT expects to fix the credentials 'by end of week', and that Meridian's board pack already states 17 March.",
              qualifications=["Informal call. Nothing from Meridian in writing.", "'End of week' could mean any day up to Friday 14 March."]),
    ]
    # Preserve practitioner-provided claims from earlier revisions (DP6).
    for c in previous_claims:
        if c.claim_type == "user_provided":
            claims.append(c.model_copy(deep=True))
    return AgentRevisionOutput(
        situation_summary=(
            "Since 09:15, a manual staging test run (D07) has failed on the billing API v2 integration, and rc4 is blocked "
            "for UAT. This removes the main assumption behind D01's 'Confirmed' status. Meridian's informal estimate "
            "('by end of week', D08) would delay UAT beyond 12–14 March unless the fix lands early. D01 should not be presented "
            "as 'Green / Confirmed' at 11:00."
        ),
        reliance="not_reliable",
        overall_assessment=(
            "D01 is outdated on the integration milestone. An external review should present go-live on 17 March as "
            "conditional on credentials arriving and contract tests passing, which under the Delivery glossary is Amber with a stated condition."
        ),
        claims=claims,
        projections=[
            Projection(id="P1", based_on=["D01", "D02", "D03", "D04"],
                       outcome="If the staging contract tests pass before 12 March, UAT can start as scheduled and go-live on 17 March remains achievable.",
                       assumptions=["The billing integration works against the Meridian sandbox.",
                                    "Valid v2 sandbox credentials are installed in staging."],
                       status="invalidated", invalidated_by=["D07"],
                       invalidation_reason="D07: contract tests failed (401) because the staging credentials are v1-scoped. rc4 is blocked for UAT."),
            Projection(id="P2", based_on=["D04", "D06"],
                       outcome="If the Payline certificate is renewed before 20 March, card payments keep working at and after go-live.",
                       assumptions=["Someone at Meridian signs the CSR in time.", "Someone on our side is named to chase it."]),
            Projection(id="P3", based_on=["D07", "D08"],
                       outcome="If Meridian delivers v2 credentials by Wednesday 12 March and re-tests pass (about half a day), UAT could start on 13 March. That gives a compressed UAT window, and 17 March stays at risk.",
                       assumptions=["'By end of week' in practice means Wednesday or earlier (unconfirmed, D08).",
                                    "No further failures appear once the credentials are fixed.",
                                    "Meridian testers can still fit UAT into 13–14 March."]),
            Projection(id="P4", based_on=["D07", "D08"],
                       outcome="If the credentials arrive on Friday 14 March, UAT cannot finish before 17 March, and go-live has to move.",
                       assumptions=["UAT needs at least 2 working days (D01 schedules 3)."]),
        ],
        limitations=[
            Limitation(id="L1", type="search_gap", related_docs=["D07", "D08"],
                       description="No written commitment from Meridian IT on when v2 credentials will be delivered. Only a second-hand 'by end of week' (D08)."),
            Limitation(id="L3", type="conflict", related_docs=["D01", "D05", "D07"],
                       description="D01's 'Confirmed / Green' contradicts the Delivery definitions (D05) and the test result (D07)."),
            Limitation(id="L4", type="tacit_knowledge", related_docs=["D06", "D08"],
                       description="Ownership of the Payline certificate renewal is still unclear. It is also unknown whether it involves the same Meridian IT contact as the credentials.",
                       unresolved_owner="Infra lead or Security team. Customer Success could ask Meridian."),
            Limitation(id="L6", type="tacit_knowledge", related_docs=["D08"],
                       description="Whether to present 17 March as conditional, despite Meridian's board pack already stating it, is a relationship and accountability judgement that the records cannot settle.",
                       unresolved_owner="Delivery Manager, with the Customer Success Manager (talk before 11:00)"),
            Limitation(id="L7", type="tacit_knowledge", related_docs=["D07"],
                       description="Whether a credentials fix by mid-week is realistic needs direct contact with Meridian IT.",
                       unresolved_owner="Solution Architect, who owns DEP-07"),
        ],
        competing_hypotheses=[
            CompetingHypothesis(id="H3", explanation="The credentials and certificate issues share a root cause: slow responses from one Meridian IT contact.",
                                supporting=["D06 (no answer from Meridian)", "D08 (contact may be the same person)"], against=["Not confirmed by any record"],
                                what_would_resolve="Ask Customer Success to confirm the Meridian IT contact for both items."),
            CompetingHypothesis(id="H4", explanation="The two issues are separate. The certificate is an internal ownership gap on our side, not a Meridian delay.",
                                supporting=["D04 (renewal 'in progress – Infra')", "D06 (owner unclear on our side)"], against=["D06 (needs client-signed CSR)"],
                                what_would_resolve="Find the missing replies in the D06 thread, or ask the Infra lead."),
        ],
        what_changed=[
            "New record D07: staging contract tests failed, and rc4 is blocked for UAT.",
            "Projection P1 (UAT starts 12 March, go-live 17 March) is invalidated by D07. It stays visible below.",
            "Claim C3 is now supported by a test result, not just a difference in terminology.",
            "Reliance assessment changed from 'reliable with qualifications' to 'not reliable'.",
            "New projections P3 and P4 depend on when Meridian delivers the v2 credentials.",
            "New open point L6: how to present 17 March given Meridian's board pack is a human judgement.",
        ],
    )
