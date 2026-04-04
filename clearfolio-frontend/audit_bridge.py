#!/usr/bin/env python3
"""
audit_bridge.py — JSON bridge between Clearfolio Review CLI and the Next.js frontend.

Called by the Next.js API route. Imports pipeline classes directly from
clearfolio_review_v2.py (must be in same directory or CLEARFOLIO_PATH env var).

Usage:
    python audit_bridge.py <contract.docx> [--mode quick|deep]

Outputs:
    A single JSON object to stdout. All ANSI/terminal output is suppressed.
    On error the JSON will contain an "error" key with a description.
"""

import sys
import os
import json
import argparse
import traceback
import io
from contextlib import redirect_stdout, redirect_stderr

# ── Locate clearfolio_review_v2.py ─────────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_cf_path    = os.getenv("CLEARFOLIO_PATH", _script_dir)
sys.path.insert(0, _cf_path)

# ── Suppress all terminal output from the main module ──────────────────────
_null_io = io.StringIO()

def _import_clearfolio():
    """Import pipeline classes, suppressing any module-level print."""
    with redirect_stdout(_null_io), redirect_stderr(_null_io):
        from clearfolio_review_v2 import (
            DocumentLoader,
            DocumentParser,
            RuleEngine,
            OllamaClient,
            QuickAnalyser,
            DeepAuditOrchestrator,
            FindingAggregator,
            AuditScorer,
            AIFinding,
        )
    return (DocumentLoader, DocumentParser, RuleEngine, OllamaClient,
            QuickAnalyser, DeepAuditOrchestrator, FindingAggregator,
            AuditScorer, AIFinding)


def _finding_to_dict(f) -> dict:
    """Serialise an AIFinding dataclass to a plain dict."""
    return {
        "clause_label":   f.clause_label,
        "risk":           f.risk,
        "issue":          f.issue,
        "suggestion":     f.suggestion,
        "confidence":     f.confidence,
        "clause_index":   f.clause_index,
        "source_models":  f.source_models,
        "judge_validated": f.judge_validated,
        "judge_note":     f.judge_note,
        "pass_number":    f.pass_number,
    }


def run_audit(filepath: str, mode: str) -> dict:
    """Run the full audit pipeline and return a serialisable result dict."""
    (DocumentLoader, DocumentParser, RuleEngine, OllamaClient,
     QuickAnalyser, DeepAuditOrchestrator, FindingAggregator,
     AuditScorer, AIFinding) = _import_clearfolio()

    # Redirect all _status/_warn/_fatal prints during pipeline
    with redirect_stdout(_null_io), redirect_stderr(_null_io):
        loader  = DocumentLoader(filepath).load()
        clauses = DocumentParser(loader).parse()
        rule_findings = RuleEngine(clauses, loader.full_text).run()

        client = OllamaClient()
        ai_findings = []
        model_results = []

        if mode == "quick":
            raw = QuickAnalyser(clauses, client).run()
            ai_findings = raw
        else:
            orch = DeepAuditOrchestrator(clauses, client)
            ai_findings   = orch.run()
            model_results = orch.model_results

        ai_findings = FindingAggregator.deduplicate_ai(ai_findings)
        score       = AuditScorer().compute(rule_findings, ai_findings)

    grade, _ = AuditScorer.grade(score)

    # Identify missing clause rule IDs (R01–R15)
    missing_rule_ids = {f"R{str(i).zfill(2)}" for i in range(1, 16)}
    missing_clauses  = [
        {"rule_id": f["rule_id"], "title": f["title"], "severity": f["severity"]}
        for f in rule_findings
        if f["rule_id"] in missing_rule_ids
    ]

    # Model summary for deep mode
    model_summary = []
    for mr in model_results:
        model_summary.append({
            "model":       mr.model_name,
            "role":        mr.role,
            "pass":        mr.pass_number,
            "findings":    len(mr.findings),
            "elapsed_sec": round(mr.elapsed_sec, 1),
            "error":       mr.error or None,
        })

    return {
        "filename":      os.path.basename(filepath),
        "score":         score,
        "grade":         grade,
        "mode":          mode,
        "clauses_count": len(clauses),
        "rule_findings": rule_findings,
        "ai_findings":   [_finding_to_dict(f) for f in ai_findings],
        "missing_clauses": missing_clauses,
        "model_summary": model_summary,
        "error":         None,
    }


def main():
    parser = argparse.ArgumentParser(description="Clearfolio Review JSON bridge")
    parser.add_argument("filepath")
    parser.add_argument("--mode", choices=["quick", "deep"], default="quick")
    args = parser.parse_args()

    try:
        result = run_audit(args.filepath, args.mode)
    except SystemExit as exc:
        # _fatal() calls sys.exit — capture the message from stderr buffer
        msg = _null_io.getvalue().strip() or f"Fatal error (exit code {exc.code})"
        result = {"error": msg, "score": 0, "grade": "F",
                  "rule_findings": [], "ai_findings": [], "missing_clauses": []}
    except Exception:
        result = {"error": traceback.format_exc(),
                  "score": 0, "grade": "F",
                  "rule_findings": [], "ai_findings": [], "missing_clauses": []}

    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
