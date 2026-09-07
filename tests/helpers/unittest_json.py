from __future__ import annotations

import argparse
import io
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("modules", nargs="*")
    parser.add_argument("--discover-start")
    parser.add_argument("--top-level")
    options = parser.parse_args(sys.argv[1:] if arguments is None else arguments)
    if not options.modules and options.discover_start is None:
        parser.error("at least one unittest module or --discover-start is required")
    if options.modules and options.discover_start is not None:
        parser.error("modules and --discover-start are mutually exclusive")

    loader = unittest.defaultTestLoader
    suite = (
        loader.discover(options.discover_start, top_level_dir=options.top_level)
        if options.discover_start is not None
        else unittest.TestSuite(
            loader.loadTestsFromName(name) for name in options.modules
        )
    )
    diagnostics = io.StringIO()
    result = unittest.TextTestRunner(
        stream=diagnostics,
        verbosity=2,
    ).run(suite)
    diagnostic_bytes = diagnostics.getvalue().encode("utf-8", errors="replace")
    if diagnostic_bytes:
        sys.stdout.buffer.write(diagnostic_bytes)

    summary = {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful(),
        "tests_run": result.testsRun,
    }
    payload = "UNITTEST_SUMMARY=" + json.dumps(
        summary,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"
    sys.stdout.buffer.write(payload.encode("utf-8"))
    sys.stdout.buffer.flush()
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
