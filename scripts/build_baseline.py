"""Build baseline_0915.json – the identical starting account for every interview.

    python scripts/build_baseline.py            # curated baseline (default, deterministic)
    python scripts/build_baseline.py --live     # run the live Gemini agent over D01–D06 instead
    python scripts/build_baseline.py --live --out baseline_live.json

The curated baseline is committed to the repo. A live baseline can be generated
for comparison, reviewed by hand and then promoted by renaming it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from agent import AgentRun, build_curated_baseline, make_provider  # noqa: E402
from state import InquiryRecord  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Use the Gemini agent instead of the curated baseline.")
    ap.add_argument("--out", default=str(ROOT / "baseline_0915.json"))
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    if args.live:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        run = AgentRun(InquiryRecord(), trigger="baseline", trigger_note="Initial investigation of records D01–D06.",
                       provider=make_provider("gemini", api_key=key))
        run.run_to_end(on_step=lambda s: print(f"  step {s.step}: {s.tool} {s.args} -> {s.status}"))
        record = run.finalize()
    else:
        record = build_curated_baseline()

    Path(args.out).write_text(record.model_dump_json(indent=2), encoding="utf-8")
    print(f"Wrote {args.out} (version {record.version}, {len(record.claims)} claims, {len(record.projections)} projections)")


if __name__ == "__main__":
    main()
