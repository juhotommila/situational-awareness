"""Curated content for the deterministic parts of the prototype.

* `BASELINE_*` – the 09:15 account every participant starts from. It uses the
  same schema the live agent must produce, so the interface behaves identically
  across curated, scripted and live revisions.
* `MOCK_0935_*` – a scripted revision used by MockProvider when the 09:35
  records are investigated offline (demos and fallback only).
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
    ToolCallLog(
        version=1, step=1, tool="search_passages", args={"query": "release 3.2 status confirmed go-live"},
        status="found", thought="Start with the status report and records mentioning readiness.",
        observation_summary="4 passage(s): D01.1, D01.4, D02.2, D01.def",
    ),
    ToolCallLog(
        version=1, step=2, tool="read_record", args={"doc_id": "D01"}, status="found",
        thought="Read the status report and its definitions.",
        observation_summary="Read D01 – Weekly status report – release 3.2 (updated 2025-03-10 17:30)",
    ),
    ToolCallLog(
        version=1, step=3, tool="read_record", args={"doc_id": "D02"}, status="found",
        thought="Check the engineering input behind the Confirmed billing integration status.",
        observation_summary="Read D02 – RE: Release 3.2 – status inputs for Monday report (updated 2025-03-10 15:48)",
    ),
    ToolCallLog(
        version=1, step=4, tool="read_record", args={"doc_id": "D03"}, status="found",
        thought="Check whether the overnight staging contract tests mentioned in D02 ran.",
        observation_summary="Read D03 – CI/CD pipeline run – customer-portal 3.2.0-rc4 (nightly) (updated 2025-03-11 06:05)",
    ),
    ToolCallLog(
        version=1, step=5, tool="read_record", args={"doc_id": "D05"}, status="found",
        thought="Check the external reporting definition of Confirmed and Green.",
        observation_summary="Read D05 – Delivery glossary and definition of done (external reporting) (updated 2024-11-05 09:00)",
    ),
    ToolCallLog(
        version=1, step=6, tool="search_passages", args={"query": "payment gateway certificate renewal owner"},
        status="found", thought="Check supporting records for risk R-14 (TLS certificate).",
        observation_summary="4 passage(s): D06.1, D04.2, D06.3, D01.3",
    ),
    ToolCallLog(
        version=1, step=7, tool="read_record", args={"doc_id": "D06"}, status="found",
        thought="Read the infrastructure chat excerpt on certificate renewal and ownership.",
        observation_summary="Read D06 – Infrastructure channel – chat excerpt (TLS certificate) (updated 2025-03-10 18:22)",
    ),
    ToolCallLog(
        version=1, step=8, tool="read_record", args={"doc_id": "D04"}, status="found",
        thought="Check the dependency register for credentials, certificate status, and update date.",
        observation_summary="Read D04 – Release 3.2 dependency register (updated 2025-02-24 11:12)",
    ),
]

BASELINE_STOPPING_REASON = (
    "Concluded after 8 of 8 tool calls: all six available records were read. "
    "Remaining open points require confirmation from people rather than records."
)

BASELINE_OUTPUT = AgentRevisionOutput(
    situation_summary=(
        "D01 reports release 3.2 as Green and Confirmed for go-live on 17 March. Supporting records "
        "only partly back this up. 'Confirmed' is defined differently across teams, the staging contract "
        "tests for billing API v2 were skipped (D03), and a TLS certificate expiring on 20 March has no "
        "clear internal owner (D06). On current records, D01 can be used externally only with qualifications."
    ),
    reliance="reliable_with_qualifications",
    overall_assessment=(
        "Usable only with caveats: 'Confirmed' and 'Green' in D01 do not meet the Delivery definitions "
        "required for external reporting (D05)."
    ),
    claims=[
        Claim(
            id="C1", claim_type="direct_record", citations=["D01"],
            text="D01 reports overall status Green and release 3.2 as Confirmed for go-live on 17 March, with no High risks open.",
        ),
        Claim(
            id="C2", claim_type="direct_record", citations=["D02"],
            text="Engineering marked the billing API v2 integration as confirmed because PR #482 was merged with unit tests passing.",
            qualifications=["D02 notes that contract tests against the customer sandbox were still scheduled to run overnight."],
        ),
        Claim(
            id="C3", claim_type="agent_inference", citations=["D01", "D02", "D05"],
            text="The Confirmed status for the billing integration in D01 likely reflects Engineering's definition (code merged), "
                 "not Delivery's definition for external reporting (verified end-to-end in staging and signed off by QA).",
            conflicts=[ConflictNote(
                doc_ids=["D02", "D05"],
                note="'Confirmed' = code merged with unit tests (Engineering) vs. verified end-to-end in staging and signed off by QA (Delivery).",
            )],
            qualifications=["Inference: D01 does not state which definition was used; PMO's glossary defines Confirmed as reported done by the team lead."],
        ),
        Claim(
            id="C4", claim_type="direct_record", citations=["D03"],
            text="The nightly pipeline for rc4 (06:05) shows PASSED overall, but staging-contract-tests was SKIPPED because the staging environment was locked by a manual performance test.",
            conflicts=[ConflictNote(
                doc_ids=["D01", "D03"],
                note="D01 lists the integration as Confirmed, while the pipeline stage that verifies it did not run.",
            )],
        ),
        Claim(
            id="C5", claim_type="direct_record", citations=["D04", "D06"],
            text="The payment-gateway TLS certificate expires on 20 March. Renewal requires a signed CSR from the customer, and internal ownership is unclear.",
            qualifications=["D04 was last updated 15 days ago (24 Feb).", "D06 is a partial chat export: 2 replies are missing."],
        ),
        Claim(
            id="C6", claim_type="agent_inference", citations=["D01", "D05", "D06"],
            text="D01 rates risk R-14 (TLS certificate) as Low and handled by Infrastructure, which conflicts with D06. Under D05, an unowned go-live risk should be rated at least Medium.",
            conflicts=[ConflictNote(
                doc_ids=["D01", "D06"],
                note="'Handled by Infrastructure' (D01) vs. customer action needed and internal owner unclear (D06).",
            )],
        ),
    ],
    projections=[
        Projection(
            id="P1", based_on=["D01", "D02", "D03", "D04"],
            outcome="If the staging contract tests pass before 12 March, UAT can start on schedule and go-live on 17 March remains achievable.",
            assumptions=[
                "The billing integration works against the customer sandbox (unverified: D03 stage skipped).",
                "Valid v2 sandbox credentials are installed in staging (last recorded status 'pending', D04, 24 Feb).",
            ],
        ),
        Projection(
            id="P2", based_on=["D04", "D06"],
            outcome="If the payment-gateway TLS certificate is renewed before 20 March, card payments continue working at and after go-live.",
            assumptions=[
                "The customer signs the CSR in time.",
                "An internal owner is assigned to follow up.",
            ],
        ),
    ],
    limitations=[
        Limitation(
            id="L1", type="search_gap", related_docs=["D03"],
            description="No record shows staging contract tests passing for any 3.2 release candidate.",
        ),
        Limitation(
            id="L2", type="search_gap", related_docs=["D04"],
            description="No record newer than 24 Feb states the status of the v2 sandbox credentials.",
        ),
        Limitation(
            id="L3", type="conflict", related_docs=["D01", "D02", "D05"],
            description="'Confirmed' has different definitions in Engineering (D02) and Delivery (D05); D01 does not state which one applies.",
        ),
        Limitation(
            id="L4", type="tacit_knowledge", related_docs=["D06"],
            description="Internal ownership of the TLS certificate renewal is unclear since the previous security contact left. The chat export is incomplete.",
            unresolved_owner="Infrastructure lead or Security team",
        ),
        Limitation(
            id="L5", type="tacit_knowledge", related_docs=["D01"],
            description="Only the PMO coordinator can confirm which definition of Confirmed was used when compiling D01.",
            unresolved_owner="Project coordinator, PMO",
        ),
    ],
    competing_hypotheses=[
        CompetingHypothesis(
            id="H1",
            explanation="D01 is accurate in substance: the integration works and only the formal staging run is pending.",
            supporting=["D02", "D03 (unit tests pass)"],
            against=["D03 (contract stage skipped)", "D04 (credentials pending)"],
            what_would_resolve="A completed staging contract-test run against the customer sandbox.",
        ),
        CompetingHypothesis(
            id="H2",
            explanation="D01 overstates readiness: 'Confirmed' reflects only the code merge, and end-to-end integration is unverified.",
            supporting=["D02", "D05", "D03 (contract stage skipped)"],
            against=["No record shows a test failure yet"],
            what_would_resolve="Contract-test results or confirmation from the PMO coordinator.",
        ),
    ],
    what_changed=["Initial account compiled from records D01–D06 at 09:15."],
)

# ---------------------------------------------------------------------------
# Scripted 09:35 revision (MockProvider)
# ---------------------------------------------------------------------------

MOCK_0935_PLAN = [
    ("Check for new records on staging contract tests.", "search_passages", {"query": "staging contract tests result failed"}),
    ("Read the new staging test report.", "read_record", {"doc_id": "D07"}),
    ("Check for new updates on credentials or the 11:00 review.", "search_passages", {"query": "credentials customer end of week review"}),
    ("Read the account manager email.", "read_record", {"doc_id": "D08"}),
    ("Check whether any written date exists from customer IT.", "search_passages", {"query": "customer IT credentials date written"}),
]

MOCK_0935_STOPPING_REASON = (
    "Concluded after 5 tool calls: both new records were read. No written commitment from customer IT was found; "
    "remaining questions require direct human follow-up."
)


def mock_0935_output(previous_claims: List[Claim]) -> AgentRevisionOutput:
    by_id = {c.id: c for c in previous_claims}
    claims: List[Claim] = []
    for cid in ("C1", "C2"):
        if cid in by_id:
            claims.append(by_id[cid])
    claims.append(
        Claim(
            id="C3", claim_type="agent_inference", citations=["D01", "D02", "D05", "D07"],
            text="The Confirmed status in D01 reflected Engineering's definition (code merged). The integration is not verified end-to-end, and a manual staging run has failed.",
            conflicts=[ConflictNote(doc_ids=["D01", "D07"], note="'Confirmed' (D01) vs. 7 of 19 contract tests failing (D07).")],
            qualifications=["Now backed by test results in D07 rather than terminology differences alone."],
        )
    )
    for cid in ("C4", "C5", "C6"):
        if cid in by_id:
            claims.append(by_id[cid])
    claims += [
        Claim(
            id="C7", claim_type="direct_record", citations=["D07"],
            text="A manual staging contract-test run (09:05–09:26) FAILED: 7 of 19 tests returned HTTP 401 Unauthorized on /v2/invoices and /v2/payments. rc4 is BLOCKED for UAT.",
        ),
        Claim(
            id="C8", claim_type="agent_inference", citations=["D04", "D07"],
            text="The likely cause is the v2 sandbox credentials still listed as pending in D04: staging credentials appear to be scoped for v1 only.",
            qualifications=["D07 notes that credentials 'appear' to be v1-scoped; not yet confirmed by customer IT."],
        ),
        Claim(
            id="C9", claim_type="direct_record", citations=["D08"],
            text="The account manager reports, second-hand, that customer IT expects to resolve credentials 'by end of week', and that customer review materials already state 17 March.",
            qualifications=["Informal call; nothing confirmed in writing.", "'End of week' could mean any day up to Friday 14 March."],
        ),
    ]
    # Preserve practitioner-provided claims from earlier revisions (DP6).
    for c in previous_claims:
        if c.claim_type == "user_provided":
            claims.append(c.model_copy(deep=True))
    return AgentRevisionOutput(
        situation_summary=(
            "A manual staging run (D07) failed on the billing API v2 integration, blocking rc4 for UAT. "
            "This contradicts D01's Confirmed status. The customer's informal estimate ('by end of week', D08) "
            "would delay UAT beyond 12–14 March unless credentials arrive early. D01 should not be presented "
            "as Green / Confirmed at 11:00."
        ),
        reliance="not_reliable",
        overall_assessment=(
            "D01 is no longer current on the integration milestone. Under D05, go-live on 17 March should be "
            "reported as Amber with stated conditions (credentials delivered and contract tests passing)."
        ),
        claims=claims,
        projections=[
            Projection(
                id="P1", based_on=["D01", "D02", "D03", "D04"],
                outcome="If the staging contract tests pass before 12 March, UAT can start on schedule and go-live on 17 March remains achievable.",
                assumptions=[
                    "The billing integration works against the customer sandbox.",
                    "Valid v2 sandbox credentials are installed in staging.",
                ],
                status="invalidated",
                invalidated_by=["D07"],
                invalidation_reason="D07: contract tests failed (HTTP 401) with v1-scoped credentials; rc4 is blocked for UAT.",
            ),
            Projection(
                id="P2", based_on=["D04", "D06"],
                outcome="If the payment-gateway TLS certificate is renewed before 20 March, card payments continue working at and after go-live.",
                assumptions=["The customer signs the CSR in time.", "An internal owner is assigned to follow up."],
            ),
            Projection(
                id="P3", based_on=["D07", "D08"],
                outcome="If customer IT provides v2 credentials by Wednesday 12 March and re-testing passes (~0.5 day), UAT could start on 13 March with a compressed window and 17 March still at risk.",
                assumptions=[
                    "'By end of week' means Wednesday or earlier (unconfirmed, D08).",
                    "No further defects appear once credentials are fixed.",
                    "Customer testers can fit UAT into 13–14 March.",
                ],
            ),
            Projection(
                id="P4", based_on=["D07", "D08"],
                outcome="If credentials arrive on Friday 14 March, UAT cannot finish before 17 March and go-live must move.",
                assumptions=["UAT requires at least 2 working days (D01 allocates 3)."],
            ),
        ],
        limitations=[
            Limitation(
                id="L1", type="search_gap", related_docs=["D07", "D08"],
                description="No written commitment from customer IT on when v2 credentials will arrive; only a second-hand 'by end of week' (D08).",
            ),
            Limitation(
                id="L3", type="conflict", related_docs=["D01", "D05", "D07"],
                description="D01's Green / Confirmed status conflicts with Delivery definitions (D05) and the failed test run (D07).",
            ),
            Limitation(
                id="L4", type="tacit_knowledge", related_docs=["D06", "D08"],
                description="Internal ownership of the TLS certificate renewal remains unclear, and it is unknown whether the same customer IT contact handles both items.",
                unresolved_owner="Infrastructure lead or Security team; Account manager to check with customer",
            ),
            Limitation(
                id="L6", type="tacit_knowledge", related_docs=["D08"],
                description="Deciding how to communicate a conditional 17 March date when customer review materials already state it is a stakeholder judgement outside the records.",
                unresolved_owner="Delivery lead and Account manager (align before 11:00)",
            ),
            Limitation(
                id="L7", type="tacit_knowledge", related_docs=["D07"],
                description="Whether a mid-week credentials fix is realistic requires direct confirmation from customer IT.",
                unresolved_owner="Solution architect (DEP-07 owner)",
            ),
        ],
        competing_hypotheses=[
            CompetingHypothesis(
                id="H3",
                explanation="The credentials and certificate issues share one bottleneck: slow responses from a single customer IT contact.",
                supporting=["D06 (no reply from customer)", "D08 (contact may be the same person)"],
                against=["Unconfirmed in any record"],
                what_would_resolve="Account manager confirms the customer IT contact for both items.",
            ),
            CompetingHypothesis(
                id="H4",
                explanation="The two issues are independent: the certificate delay stems from missing internal ownership.",
                supporting=["D04 (renewal listed 'in progress – Infrastructure')", "D06 (internal owner unclear)"],
                against=["D06 (still requires customer-signed CSR)"],
                what_would_resolve="Check the missing replies in D06 or confirm with the Infrastructure lead.",
            ),
        ],
        what_changed=[
            "D07: staging contract tests failed (7/19 HTTP 401); rc4 is blocked for UAT.",
            "Projection P1 (UAT starts 12 March, go-live 17 March) is invalidated by D07 and kept visible below.",
            "Claim C3 is now backed by failed test results rather than definition differences alone.",
            "Reliance assessment changed from Qualified to Not reliable.",
            "Added conditional projections P3 and P4 depending on when v2 credentials arrive.",
            "Added open point L6: presenting 17 March as conditional requires alignment before 11:00.",
        ],
    )
