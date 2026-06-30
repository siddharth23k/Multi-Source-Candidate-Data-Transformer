"""CLI for the multi-source candidate data transformer.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from src.config import load_config, ConfigError
from src.pipeline import run


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Multi-source candidate data transformer")
    ap.add_argument("--csv", help="Recruiter CSV export path")
    ap.add_argument("--resume", action="append", default=[],
                    help="Resume PDF path (repeatable)")
    ap.add_argument("--config", help="Runtime output config JSON")
    ap.add_argument("--out", help="Write JSON here instead of stdout")
    ap.add_argument("--report", help="Write the diagnostics report JSON here")
    ap.add_argument("--region", default="IN", help="Fallback phone region (ISO-3166 alpha-2)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if not args.csv and not args.resume:
        ap.error("provide at least one source: --csv and/or --resume")

    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    result = run(csv_path=args.csv, resume_paths=args.resume,
                 config=config, phone_region=args.region)
    profiles = result.profiles

    # One candidate -> emit the object; many -> emit an array.
    payload = profiles[0] if len(profiles) == 1 else profiles
    text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"wrote {args.out} ({len(profiles)} profile(s))", file=sys.stderr)
    else:
        print(text)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(json.dumps(result.diagnostics, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {args.report}", file=sys.stderr)

    counts = result.diagnostics.get("summary", {})
    if counts:
        print(f"diagnostics: {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
