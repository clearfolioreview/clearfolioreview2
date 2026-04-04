#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║    CLEARFOLIO REVIEW v3.1 — Production Contract Audit  (Coverage Fix)        ║
║    Privacy-First | Local-Only | Multi-Model | Complete Document Coverage     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  v3.1 Coverage Fixes (root-cause of ~4% document visibility bug):            ║
║  C01  Parser now uses paragraph.style (not text patterns) as primary signal  ║
║  C02  List Paragraph style bodies are NOT lumped into giant blobs;           ║
║       each list item becomes its own paragraph within its parent section     ║
║  C03  Large sections (>CHUNK_CHARS) split into overlapping sub-chunks        ║
║       with CHUNK_OVERLAP overlap so clause boundaries are never cut mid-sent ║
║  C04  CHUNK_CHARS raised to 1600 (fills llama3/mistral context properly)     ║
║  C05  ALL clauses are processed — no top-N selector that drops clauses       ║
║  C06  Batched prompt sending: clauses grouped by token budget per LLM call   ║
║  C07  Sub-chunk indices carry parent clause index for correct mapping        ║
║  C08  QuickAnalyser also processes all clauses via same batch mechanism      ║
║  C09  Batch size configurable via CF_BATCH_CHARS env var                     ║
║  C10  Progress bar shows actual batches sent / total batches                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Usage:
    python clearfolio_review.py <contract.docx> [options]

Options:
    --mode   quick|deep   quick = single model, deep = 3 specialist + judge
    --output json|txt     write report file alongside input
    --verbose             enable DEBUG logging to stderr
    --info                print architecture notes and exit

Dependencies:
    pip install python-docx requests

Ollama:
    ollama pull llama3        # quick mode + risk specialist
    ollama pull mistral       # compliance specialist  (deep mode)
    ollama pull phi3          # completeness specialist (deep mode)
    ollama pull deepseek-r1   # judge (optional, falls back to llama3)
"""

import sys
import os
import re
import json
import hashlib
import logging
import textwrap
import time
import argparse
import ctypes
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from docx import Document


# ─────────────────────────────────────────────────────────────────────────────
# WINDOWS ANSI
# ─────────────────────────────────────────────────────────────────────────────
def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        k32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        k32.SetConsoleMode(k32.GetStdHandle(-11), 7)
    except Exception:
        pass

_enable_windows_ansi()


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
log = logging.getLogger("clearfolio")

def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )
    log.setLevel(level)


# ─────────────────────────────────────────────────────────────────────────────
# COLOUR HELPERS
# ─────────────────────────────────────────────────────────────────────────────
class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    RED = "\033[91m";  YELLOW = "\033[93m"; GREEN = "\033[92m"
    CYAN = "\033[96m"; MAGENTA = "\033[95m"; WHITE = "\033[97m"
    BLUE = "\033[94m"; ORANGE = "\033[38;5;208m"; PURPLE = "\033[38;5;141m"

def col(text: object, *codes: str) -> str:
    return "".join(codes) + str(text) + C.RESET

TERMINAL_WIDTH = 92

def hr(char: str = "─", colour: str = C.DIM) -> str:
    return col(char * TERMINAL_WIDTH, colour)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES  (defined before any class uses them)
# ─────────────────────────────────────────────────────────────────────────────
def _fatal(msg: str) -> None:
    log.critical(msg)
    print(col(f"\n  ✗ FATAL: {msg}\n", C.RED, C.BOLD), file=sys.stderr)
    sys.exit(1)

def _warn(msg: str) -> None:
    log.warning(msg)
    print(col(f"  ⚠  {msg}", C.YELLOW))

def _status(msg: str) -> None:
    log.info(msg)
    print(col(f"  ▶  {msg}", C.CYAN))

def _section(msg: str) -> None:
    print()
    print(col(f"  {'─'*4}  {msg}  {'─'*4}", C.BOLD, C.WHITE))
    print()

def _banner_skipped(reason: str) -> None:
    print()
    print(hr("─"))
    print(col("  ⊘  AI ANALYSIS SKIPPED", C.YELLOW, C.BOLD))
    print(col(f"     Reason  : {reason}", C.DIM))
    print(col("     Rule-engine findings are still complete.", C.DIM))
    print(hr("─"))
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL    = os.getenv("CF_OLLAMA_URL",    "http://localhost:11434")
OLLAMA_TIMEOUT     = int(os.getenv("CF_TIMEOUT",   "240"))
OLLAMA_RETRIES     = int(os.getenv("CF_RETRIES",   "3"))
OLLAMA_RETRY_DELAY = float(os.getenv("CF_RETRY_DELAY", "2.0"))
INTER_PASS_SLEEP   = float(os.getenv("CF_PASS_SLEEP",  "1.0"))

MAX_DOC_CHARS      = int(os.getenv("CF_MAX_DOC",   "500000"))

# ── Chunking config  [C03, C04, C06, C09] ────────────────────────────────────
# CHUNK_CHARS: max chars of clause text in a single LLM call
# Llama3 8B context ≈ 8k tokens ≈ 24k chars.
# We send ~6 clauses × 1600 chars = ~9600 chars + system prompt = safe.
CHUNK_CHARS        = int(os.getenv("CF_CHUNK_CHARS", "1600"))   # per clause snippet [C04]
BATCH_CHARS        = int(os.getenv("CF_BATCH_CHARS", "4000"))   # total chars per LLM call [C06]
CHUNK_OVERLAP      = int(os.getenv("CF_CHUNK_OVERLAP", "150"))  # overlap between sub-chunks [C03]

MODEL_QUICK  = os.getenv("CF_MODEL_QUICK",  "llama3")
MODEL_A      = os.getenv("CF_MODEL_A",      "llama3")
MODEL_B      = os.getenv("CF_MODEL_B",      "mistral")
MODEL_C      = os.getenv("CF_MODEL_C",      "phi3")
JUDGE_MODEL  = os.getenv("CF_JUDGE_MODEL",  "deepseek-r1")


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class AIFinding:
    clause_label:    str
    risk:            str    # CRITICAL / HIGH / MEDIUM / LOW
    issue:           str
    suggestion:      str
    confidence:      int    # 0–100
    clause_index:    int  = -1
    source_models:   list = field(default_factory=list)
    judge_validated: bool = False
    judge_note:      str  = ""
    pass_number:     int  = 1

@dataclass
class ModelResult:
    model_name:  str
    role:        str
    raw_output:  str
    findings:    list
    elapsed_sec: float = 0.0
    error:       str   = ""
    pass_number: int   = 1


# ─────────────────────────────────────────────────────────────────────────────
# 1. DOCUMENT LOADER
# ─────────────────────────────────────────────────────────────────────────────
class DocumentLoader:
    SCAN_KEYWORDS = [
        "scanned", "scan only", "image-based", "ocr required",
        "this document is an image",
    ]

    def __init__(self, filepath: str):
        self.filepath   = filepath
        self.doc        = None
        self.full_text  = ""
        self.raw_paragraphs: list[dict] = []   # preserves style metadata
        self.truncated  = False

    def load(self) -> "DocumentLoader":
        self._validate_path()
        self._open_docx()
        self._extract_paragraphs()
        self._check_not_scanned()
        self._build_full_text()
        return self

    def _validate_path(self) -> None:
        if not os.path.exists(self.filepath):
            _fatal(f"File not found: {self.filepath}")
        if not self.filepath.lower().endswith(".docx"):
            _fatal("Only .docx files are accepted.")

    def _open_docx(self) -> None:
        try:
            self.doc = Document(self.filepath)
        except Exception as exc:
            _fatal(f"Cannot open .docx: {exc}")

    def _extract_paragraphs(self) -> None:
        """
        Extract every paragraph with its style name and heading level.
        Deduplicates table cells.
        Preserves 'List Paragraph' style tag so the parser can handle it.
        """
        seen: set[str] = set()

        def _add(text: str, style: str, level: int) -> None:
            key = text.strip()
            if not key or key in seen:
                return
            seen.add(key)
            self.raw_paragraphs.append({
                "text":  key,
                "style": style,
                "level": level,
            })

        for para in self.doc.paragraphs:
            style = para.style.name if para.style else "Normal"
            level = self._heading_level(style)
            _add(para.text, style, level)

        for table in self.doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    _add(cell.text, "Table", 0)

        log.debug("Extracted %d unique paragraphs", len(self.raw_paragraphs))

    @staticmethod
    def _heading_level(style: str) -> int:
        """Multi-digit heading levels handled (Heading 1 … Heading 12)."""
        m = re.match(r"Heading\s+(\d+)", style, re.IGNORECASE)
        if m:
            return int(m.group(1))
        if style.lower() in ("title", "subtitle"):
            return 1
        return 0

    def _check_not_scanned(self) -> None:
        if not self.raw_paragraphs:
            _fatal("Document is empty or image/scan-based. Text-based .docx required.")
        snippet = " ".join(p["text"].lower() for p in self.raw_paragraphs[:6])
        for kw in self.SCAN_KEYWORDS:
            if kw in snippet:
                _fatal(f"Scanned/image-based document detected ('{kw}').")

    def _build_full_text(self) -> None:
        text = "\n".join(p["text"] for p in self.raw_paragraphs)
        if len(text) > MAX_DOC_CHARS:
            self.truncated = True
            text = text[:MAX_DOC_CHARS]
            _warn(f"Document exceeds {MAX_DOC_CHARS:,} chars — text capped. "
                  "Later content may not be rule-checked.")
        self.full_text = text


# ─────────────────────────────────────────────────────────────────────────────
# 2. DOCUMENT PARSER  —  Style-aware, sub-chunking, complete coverage
# ─────────────────────────────────────────────────────────────────────────────
class DocumentParser:
    """
    Phase 1 — Section segmentation using paragraph.style as primary signal.
      Any paragraph with style level > 0 (Heading N) or style "Title/Subtitle"
      starts a new section. Text-pattern clause detection is secondary.

    Phase 2 — Sub-chunking.
      Sections with body > CHUNK_CHARS are split into overlapping sub-chunks
      so NO content exceeds the LLM's practical context budget.
      Sub-chunks carry the parent section index for correct mapping.

    This guarantees 100% of document content reaches an LLM call.  [C01–C08]
    """

    # Secondary text-based clause boundary pattern (only used when style=Normal/Body)
    _CLAUSE_RE = re.compile(
        r"^(?:"
        r"(?:Article|Section|Clause|Schedule|Exhibit|Annex|Appendix)\s+[\w\d]+"
        r"|(?:\d{1,2}\.){1,3}\d*\s+"
        r"|\([a-z]\)\s+"
        r")",
        re.IGNORECASE,
    )

    # Styles that contain list items — treat as body, NOT as new sections
    _LIST_STYLES = {"list paragraph", "list bullet", "list number",
                    "list continue", "list", "body text"}

    def __init__(self, loader: DocumentLoader):
        self.raw_paragraphs = loader.raw_paragraphs

    def parse(self) -> list[dict]:
        """Return fully-indexed flat list of sections + sub-chunks."""
        raw_sections = self._segment_into_sections()
        flat         = self._sub_chunk_sections(raw_sections)
        # Re-assign sequential indices after sub-chunking
        for i, s in enumerate(flat):
            s["index"]     = i
            s["full_text"] = (s["title"] + " " + s["body"]).lower()
        log.debug("Parser: %d raw sections → %d flat chunks after sub-chunking",
                  len(raw_sections), len(flat))
        return flat

    # ── Phase 1: section segmentation ────────────────────────────────────────
    def _segment_into_sections(self) -> list[dict]:
        sections: list[dict] = []
        current: Optional[dict] = None

        for para in self.raw_paragraphs:
            text      = para["text"]
            style     = para["style"]
            level     = para["level"]
            style_low = style.lower()

            # ── Determine if this para starts a new section ───────────────────
            # Priority 1: word-processor heading style (most reliable)
            is_heading = level > 0

            # Priority 2: title / subtitle
            if not is_heading and style_low in ("title", "subtitle"):
                is_heading = True

            # Priority 3: text-pattern clause start — ONLY for non-list styles
            is_list = any(s in style_low for s in self._LIST_STYLES)
            is_clause_text = (
                not is_heading
                and not is_list
                and bool(self._CLAUSE_RE.match(text))
            )

            if is_heading or is_clause_text:
                if current:
                    sections.append(current)
                current = {
                    "title":       text,
                    "body":        "",
                    "index":       -1,   # assigned later
                    "style":       style,
                    "is_heading":  is_heading,
                    "parent_idx":  -1,
                }
            else:
                # Body / list / normal paragraph — append to current section
                if current is None:
                    current = {
                        "title":      "Preamble",
                        "body":       "",
                        "index":      -1,
                        "style":      "Body",
                        "is_heading": False,
                        "parent_idx": -1,
                    }
                sep = "\n" if current["body"] else ""
                current["body"] += sep + text

        if current:
            sections.append(current)

        # Fallback: if still only one giant section, chunk by paragraph groups
        if len(sections) <= 1:
            sections = self._fallback_paragraph_chunks()

        return sections

    def _fallback_paragraph_chunks(self) -> list[dict]:
        """Chunk every 6 paragraphs — used when document has no headings."""
        CHUNK_SIZE = 6
        chunks, buf = [], []
        for i, para in enumerate(self.raw_paragraphs):
            buf.append(para["text"])
            if len(buf) == CHUNK_SIZE or i == len(self.raw_paragraphs) - 1:
                chunks.append({
                    "title":      buf[0][:80],
                    "body":       "\n".join(buf[1:]),
                    "index":      -1,
                    "style":      "Fallback",
                    "is_heading": False,
                    "parent_idx": -1,
                })
                buf = []
        return chunks

    # ── Phase 2: sub-chunk sections whose body exceeds CHUNK_CHARS ───────────
    def _sub_chunk_sections(self, sections: list[dict]) -> list[dict]:
        """
        For any section whose body length > CHUNK_CHARS, split it into
        overlapping sub-chunks each ≤ CHUNK_CHARS.

        The sub-chunk inherits the parent title with a " [part N/M]" suffix
        so the LLM knows it is a fragment of a larger clause.

        Sub-chunks keep a `parent_idx` pointing to the first (root) section
        in the output list for deduplication purposes.  [C03, C07]
        """
        result: list[dict] = []

        for sec in sections:
            body = sec["body"]

            if len(body) <= CHUNK_CHARS:
                # Section fits in one LLM call — keep as-is
                sec["parent_idx"] = len(result)
                result.append(sec)
                continue

            # Split body into overlapping windows
            sub_bodies = _sliding_window(body, CHUNK_CHARS, CHUNK_OVERLAP)
            n = len(sub_bodies)

            for part_num, sub_body in enumerate(sub_bodies, start=1):
                suffix  = f" [part {part_num}/{n}]" if n > 1 else ""
                sub_sec = {
                    "title":      sec["title"] + suffix,
                    "body":       sub_body,
                    "index":      -1,          # fixed below
                    "style":      sec["style"],
                    "is_heading": sec["is_heading"],
                    "parent_idx": len(result), # first sub-chunk = root
                }
                result.append(sub_sec)

        return result


def _sliding_window(text: str, window: int, overlap: int) -> list[str]:
    """
    Split `text` into chunks of length ≤ `window`, advancing by
    (window - overlap) characters. Tries to break on sentence boundaries.
    """
    step   = max(1, window - overlap)
    chunks = []
    start  = 0

    while start < len(text):
        end = start + window
        if end >= len(text):
            chunks.append(text[start:])
            break

        # Try to break at the last sentence-ending punctuation before `end`
        snip = text[start:end]
        # Search backwards for '. ' or '\n'
        best_break = -1
        for m in re.finditer(r"[.!?]\s|\n", snip):
            best_break = m.end()
        if best_break > window // 2:
            end = start + best_break

        chunks.append(text[start:end])
        start += step

    return chunks if chunks else [text]


# ─────────────────────────────────────────────────────────────────────────────
# 3. RULE ENGINE — 30 Deterministic Rules
# ─────────────────────────────────────────────────────────────────────────────
class RuleEngine:
    SEVERITY = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}

    _DOC_PATTERNS: list[tuple] = [
        ("R01", "Missing Clause", "CRITICAL", "No Termination Clause",
         "No termination provision found.",
         re.compile(r"\bterminat\w*\b")),
        ("R02", "Missing Clause", "CRITICAL", "No Liability Clause",
         "No clause limiting or defining liability.",
         re.compile(r"\b(liabilit\w*|limitation of liability)\b")),
        ("R03", "Missing Clause", "HIGH", "No Jurisdiction / Governing Law",
         "Disputes may be subject to uncertain legal venue.",
         re.compile(r"\b(jurisdict\w*|governing law|choice of law|applicable law)\b")),
        ("R04", "Missing Clause", "HIGH", "No Payment Terms",
         "No payment, fee, or compensation clause detected.",
         re.compile(r"\b(payment|invoic\w*|fee|compensation|remunerat\w*)\b")),
        ("R05", "Missing Clause", "MEDIUM", "No Confidentiality Clause",
         "Sensitive information may not be protected.",
         re.compile(r"\b(confidential\w*|non-disclosure|nda|proprietary information)\b")),
        ("R06", "Missing Clause", "MEDIUM", "No Dispute Resolution Mechanism",
         "No arbitration, mediation, or ADR clause found.",
         re.compile(r"\b(arbitrat\w*|mediat\w*|dispute resolution|adr)\b")),
        ("R07", "Missing Clause", "MEDIUM", "No Force Majeure Clause",
         "Parties may be liable even under extraordinary circumstances.",
         re.compile(r"\b(force majeure|act of god|unforeseeable event)\b")),
        ("R08", "Missing Clause", "HIGH", "No Intellectual Property Clause",
         "Ownership of created works or IP may be ambiguous.",
         re.compile(r"\b(intellectual property|ip rights|copyright|ownership of work)\b")),
        ("R09", "Missing Clause", "MEDIUM", "No Indemnification Clause",
         "No indemnity provision — loss allocation is unclear.",
         re.compile(r"\bindemnif\w*\b")),
        ("R10", "Missing Clause", "LOW", "No Warranty or Disclaimer",
         "No warranty terms or disclaimer of warranties found.",
         re.compile(r"\b(warrant\w*|disclaim\w*|as-is|no representation)\b")),
        ("R11", "Missing Clause", "LOW", "No Amendment Procedure",
         "No process defined for modifying the agreement.",
         re.compile(r"\b(amend\w*|modif\w*|variation|change to this agreement)\b")),
        ("R12", "Missing Clause", "LOW", "No Notice Clause",
         "Method and address for official notices not specified.",
         re.compile(r"\b(notice|notification|written notice|notify)\b")),
        ("R13", "Missing Clause", "LOW", "No Assignment Clause",
         "Unclear whether rights can be transferred to third parties.",
         re.compile(r"\b(assign\w*|transfer of rights|delegate)\b")),
        ("R14", "Term Risk", "MEDIUM", "No Contract Term / Duration Defined",
         "Agreement may be open-ended with no expiry or renewal terms.",
         re.compile(r"\b(term|duration|period|expir\w*|renew\w*)\b")),
        ("R15", "Missing Clause", "LOW", "No Entire Agreement / Merger Clause",
         "Prior negotiations may override the contract.",
         re.compile(r"\b(entire agreement|whole agreement|supersedes|merger clause)\b")),
    ]

    _CLAUSE_PATTERNS: list[tuple] = [
        ("R16", "One-sided Language", "HIGH", "Unilateral Termination / Sole Discretion",
         re.compile(r"\b(at\s+(its|our|their)\s+sole\s+discretion|without\s+cause|at\s+will)\b")),
        ("R17", "One-sided Language", "HIGH", "Unilateral Modification Right",
         re.compile(r"\b(reserves?\s+the\s+right\s+to\s+(change|modify|amend|update)|"
                    r"may\s+(change|modify|amend)\s+at\s+any\s+time)\b")),
        ("R18", "Liability Risk", "CRITICAL", "Unlimited Liability Exposure",
         re.compile(r"\b(unlimited\s+liability|no\s+cap\s+on\s+damages|"
                    r"liable\s+for\s+all\s+(losses|damages|costs))\b")),
        ("R20", "IP Risk", "HIGH", "Broad / Total IP Assignment",
         re.compile(r"\b(all\s+(rights|ip|intellectual property|inventions)\s+(are\s+)?assigned|"
                    r"work\s+made\s+for\s+hire|assign\s+all\s+rights?)\b")),
        ("R23", "Liability Risk", "MEDIUM", "Liquidated Damages Clause",
         re.compile(r"\bliquidated\s+damages?\b")),
        ("R24", "Payment Risk", "MEDIUM", "Penalties / Late Fees Defined",
         re.compile(r"\b(penalty|penalties|late\s+fee|interest\s+on\s+(late|unpaid))\b")),
        ("R25", "Legal Rights", "HIGH", "Jury Trial Waiver",
         re.compile(r"\bwaiv\w*\s+(jury\s+trial|right\s+to\s+jury)\b")),
        ("R26", "Legal Rights", "HIGH", "Class Action Waiver",
         re.compile(r"\bclass\s+action\s+waiv\w*|waiv\w*\s+class\s+action\b")),
        ("R29", "Payment Risk", "HIGH", "Unilateral Price Change Right",
         re.compile(r"\b(may\s+(increase|change|adjust)\s+(price|fee|rate|cost)|"
                    r"right\s+to\s+(change|adjust)\s+price)\b")),
    ]

    _RE_AUTO_RENEW  = re.compile(r"\b(auto[- ]?renew\w*|automatically\s+renews?|rolls?\s+over)\b")
    _RE_OPT_OUT     = re.compile(r"\b(opt[- ]out|cancel\w*|notice\s+to\s+(cancel|terminate|renew))\b")
    _RE_NON_COMPETE = re.compile(r"\b(non[- ]?compete|covenant\s+not\s+to\s+compete)\b")
    _RE_YEARS       = re.compile(r"(\d+)\s+year")
    _RE_NON_SOLIC   = re.compile(r"\bnon[- ]?solicit\w*\b")
    _RE_BEST_EFF    = re.compile(r"\b(best\s+efforts?|reasonable\s+efforts?|commercially\s+reasonable)\b")
    _RE_SLA         = re.compile(r"\b(\d+\s*(hour|day|week|month)|sla|service\s+level)\b")
    _RE_3P_INDEM    = re.compile(r"\bindemnif\w+.{0,40}third[- ]?party\s+claim\b")
    _RE_SURVIVE_KEY = re.compile(r"\b(confidentialit\w*|intellectual property|indemnif\w*)\b")
    _RE_SURVIVE     = re.compile(r"\bsurviv\w*\b")

    def __init__(self, clauses: list[dict], full_text: str):
        self.clauses   = clauses
        self.full_text = full_text.lower()
        self._findings: list[dict] = []

    def run(self) -> list[dict]:
        self._findings = []
        self._document_level()
        self._clause_level()
        self._findings.sort(key=lambda f: -self.SEVERITY.get(f["severity"], 0))
        return self._findings

    def _document_level(self) -> None:
        ft = self.full_text
        for rule_id, cat, sev, title, detail, pattern in self._DOC_PATTERNS:
            if not pattern.search(ft):
                self._add(rule_id, cat, sev, title, detail, -1)

    def _clause_level(self) -> None:
        for clause in self.clauses:
            ft = clause["full_text"]
            ci = clause["index"]
            for rule_id, cat, sev, title, pattern in self._CLAUSE_PATTERNS:
                if pattern.search(ft):
                    self._add(rule_id, cat, sev, title,
                              f"Clause '{clause['title'][:60]}' triggers this check.", ci)
            if self._RE_AUTO_RENEW.search(ft) and not self._RE_OPT_OUT.search(ft):
                self._add("R19", "Term Risk", "MEDIUM",
                          "Auto-Renewal Without Opt-Out",
                          f"Clause '{clause['title'][:60]}' auto-renews with no cancellation path.", ci)
            if self._RE_NON_COMPETE.search(ft):
                years = self._RE_YEARS.findall(ft)
                if years and any(int(y) > 1 for y in years):
                    self._add("R21", "Restrictive Covenant", "HIGH",
                              "Non-Compete Exceeds 1 Year",
                              f"Clause '{clause['title'][:60]}' imposes non-compete > 1 year.", ci)
            if self._RE_NON_SOLIC.search(ft):
                self._add("R22", "Restrictive Covenant", "MEDIUM",
                          "Non-Solicitation Clause Present",
                          f"Clause '{clause['title'][:60]}' restricts solicitation.", ci)
            if self._RE_BEST_EFF.search(ft) and not self._RE_SLA.search(ft):
                self._add("R27", "Performance Risk", "LOW",
                          "Vague Performance Standard (Best Efforts Only)",
                          f"Clause '{clause['title'][:60]}' uses vague effort language with no SLA.", ci)
            if self._RE_3P_INDEM.search(ft):
                self._add("R28", "Indemnity Risk", "MEDIUM",
                          "Broad Third-Party Indemnification",
                          f"Clause '{clause['title'][:60]}' requires broad third-party indemnity.", ci)
        if (self._RE_SURVIVE_KEY.search(self.full_text) and
                not self._RE_SURVIVE.search(self.full_text)):
            self._add("R30", "Survivability", "LOW",
                      "No Survival Clause for Key Obligations",
                      "Confidentiality / IP / indemnity may not survive termination.")

    def _add(self, rule_id: str, category: str, severity: str,
             title: str, detail: str, clause_index: int = -1) -> None:
        if clause_index < 0:
            if any(f["rule_id"] == rule_id for f in self._findings):
                return
        else:
            if any(f["rule_id"] == rule_id and f["clause_index"] == clause_index
                   for f in self._findings):
                return
        self._findings.append({
            "rule_id": rule_id, "category": category, "severity": severity,
            "title": title, "detail": detail, "clause_index": clause_index,
        })


# ─────────────────────────────────────────────────────────────────────────────
# 4a. PROMPT CACHE  (thread-safe)
# ─────────────────────────────────────────────────────────────────────────────
class PromptCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lock  = threading.Lock()

    def key(self, model: str, system: str, prompt: str) -> str:
        return hashlib.sha256((model + "||" + system + "||" + prompt).encode()).hexdigest()

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._store[key] = value

    def size(self) -> int:
        with self._lock:
            return len(self._store)


_prompt_cache = PromptCache()


# ─────────────────────────────────────────────────────────────────────────────
# 4b. OLLAMA CLIENT
# ─────────────────────────────────────────────────────────────────────────────
class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL,
                 timeout: int = OLLAMA_TIMEOUT) -> None:
        self.base_url    = base_url
        self.timeout     = timeout
        self._mdl_cache: Optional[list[str]] = None

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def raw_models(self) -> list[str]:
        if self._mdl_cache is not None:
            return self._mdl_cache
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            self._mdl_cache = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            self._mdl_cache = []
        log.debug("Available: %s", self._mdl_cache)
        return self._mdl_cache

    def base_names(self) -> list[str]:
        return [m.split(":")[0] for m in self.raw_models()]

    def resolve_model(self, preferred: str, fallback: str) -> str:
        raw   = self.raw_models()
        bases = self.base_names()
        pref_base = preferred.split(":")[0]
        if preferred in raw:                         return preferred
        if pref_base in bases:                       return raw[bases.index(pref_base)]
        for full, base in zip(raw, bases):
            if base.startswith(pref_base):           return full
        if preferred != fallback:
            _warn(f"Model '{preferred}' not installed — falling back to '{fallback}'")
            return self.resolve_model(fallback, fallback)
        return fallback

    def generate(self, model: str, prompt: str, system: str,
                 temperature: float = 0.1) -> tuple[str, str]:
        cache_key = _prompt_cache.key(model, system, prompt)
        cached    = _prompt_cache.get(cache_key)
        if cached is not None:
            log.debug("Cache hit model=%s", model)
            return cached, ""

        payload = {
            "model": model, "prompt": prompt, "system": system,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 1800},
        }
        last_err = ""
        for attempt in range(1, OLLAMA_RETRIES + 1):
            try:
                resp = requests.post(f"{self.base_url}/api/generate",
                                     json=payload, timeout=self.timeout)
                resp.raise_for_status()
                text = resp.json().get("response", "")
                _prompt_cache.set(cache_key, text)
                return text, ""
            except requests.exceptions.Timeout:
                last_err = "Request timed out"
            except Exception as exc:
                last_err = str(exc)
            if attempt < OLLAMA_RETRIES:
                delay = OLLAMA_RETRY_DELAY * (2 ** (attempt - 1))
                log.warning("Attempt %d/%d failed: %s — retry in %.1fs",
                            attempt, OLLAMA_RETRIES, last_err, delay)
                time.sleep(delay)
        log.error("Ollama failed after %d attempts: %s", OLLAMA_RETRIES, last_err)
        return "", last_err


# ─────────────────────────────────────────────────────────────────────────────
# 4c. SYSTEM PROMPTS
# ─────────────────────────────────────────────────────────────────────────────
_TABLE_FMT = textwrap.dedent("""\
    Output ONLY a pipe-delimited table, one row per finding, NO header, NO markdown:
        [N] Clause title | Risk | Issue | Suggestion | Confidence
    - [N]         : the integer index printed before each clause in the input (e.g. [3])
    - Clause title: first ≤8 words of the clause title
    - Risk        : exactly one of  CRITICAL / HIGH / MEDIUM / LOW
    - Issue       : ≤15 words describing the specific risk
    - Suggestion  : ≤15 words with a concrete fix
    - Confidence  : integer percentage e.g. 82%
    Skip clauses that are well-drafted with no issues.
    Do NOT include preamble, explanation, headers, or markdown.
""")

SYSTEM_PROMPT_A = textwrap.dedent("""\
    You are a CONTRACT RISK SPECIALIST. Focus: financial, legal, operational risks.
    Look for: uncapped liability, penalty clauses, unfavourable indemnity, one-sided
    termination, payment traps, auto-renewal without exit, unilateral price changes,
    any clause that disproportionately burdens one party.
""") + _TABLE_FMT

SYSTEM_PROMPT_B = textwrap.dedent("""\
    You are a REGULATORY COMPLIANCE SPECIALIST. Focus: legal/regulatory compliance.
    Look for: missing mandatory disclosures, GDPR/data-protection gaps, consumer-
    protection violations, unenforceable provisions, jurisdictional compliance issues.
""") + _TABLE_FMT

SYSTEM_PROMPT_C = textwrap.dedent("""\
    You are a CONTRACT COMPLETENESS SPECIALIST. Focus: what is missing or ambiguous.
    Look for: absent clauses (warranties, SLAs, IP ownership, force majeure, dispute
    resolution, confidentiality, survival), vague language, undefined terms, gaps that
    leave obligations unclear.
""") + _TABLE_FMT

SYSTEM_PROMPT_JUDGE = textwrap.dedent("""\
    You are the CHIEF CONTRACT AUDIT JUDGE.
    You receive clause text and findings from 3 specialist models.
    Your job:
    1. DEDUPLICATE: merge findings about the same clause and same issue
    2. RESOLVE CONFLICTS: pick the most accurate risk level based on original text
    3. VALIDATE: discard findings NOT supported by the clause text
    4. ENRICH: keep the best Issue + Suggestion
    5. CONFIDENCE: boost if models agree; reduce if weak evidence

    Output ONLY a pipe-delimited table, NO header:
        [N] Clause | Risk | Issue | Suggestion | Confidence | Models | Note
    - [N]     : clause index integer from input
    - Models  : which specialist models flagged it (e.g. A,B or A,B,C)
    - Note    : ≤10 words judge rationale or "validated"
    No preamble, markdown, or extra text.
""")


# ─────────────────────────────────────────────────────────────────────────────
# 4d. CLAUSE PROMPT BUILDER  +  BATCHING  [C05, C06, C08]
# ─────────────────────────────────────────────────────────────────────────────
def build_clause_prompt(clauses: list[dict], max_per_clause: int = CHUNK_CHARS) -> str:
    """
    Build a single prompt string embedding [N] before each clause.
    Each clause body is capped at max_per_clause chars.
    """
    parts = []
    for c in clauses:
        snippet = (c["title"] + "\n" + c["body"])[:max_per_clause].replace("\n", " ")
        parts.append(f"[{c['index']}] {snippet}")
    return "\n\n".join(parts)


def batch_clauses(clauses: list[dict],
                  batch_chars: int = BATCH_CHARS,
                  clause_chars: int = CHUNK_CHARS) -> list[list[dict]]:
    """
    Group clauses into batches where the total prompt length does not
    exceed batch_chars.  Each clause's contribution is min(body, clause_chars).
    This ensures we never exceed the model's practical context window.  [C06]
    """
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_size   = 0

    for clause in clauses:
        clause_size = min(len(clause["title"]) + len(clause["body"]), clause_chars) + 10
        if current_batch and current_size + clause_size > batch_chars:
            batches.append(current_batch)
            current_batch = []
            current_size  = 0
        current_batch.append(clause)
        current_size += clause_size

    if current_batch:
        batches.append(current_batch)

    return batches if batches else [[]]


# ─────────────────────────────────────────────────────────────────────────────
# 4e. RESPONSE PARSER
# ─────────────────────────────────────────────────────────────────────────────
VALID_RISKS = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

def parse_model_response(raw: str, model_name: str,
                         clauses: list[dict], pass_num: int = 1) -> list[AIFinding]:
    if not raw:
        return []

    clause_map = {c["index"]: c for c in clauses}
    findings: list[AIFinding] = []

    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or set(line) <= set("-=+~"):
            continue

        parts = re.split(r"\s*\|\s*", line, maxsplit=5)
        if len(parts) < 5:
            continue

        clause_raw, risk_raw, issue, suggestion, conf_raw = parts[:5]
        risk = risk_raw.strip().upper()
        if risk not in VALID_RISKS:
            continue

        # Clause index — prefer embedded [N], fall back to title fuzzy
        matched_index = -1
        clause_label  = clause_raw.strip()
        idx_m = re.match(r"\[(\d+)]", clause_raw.strip())
        if idx_m:
            candidate = int(idx_m.group(1))
            if candidate in clause_map:
                matched_index = candidate
                tail = clause_raw[idx_m.end():].strip()
                clause_label = tail or clause_map[candidate]["title"][:50]
        else:
            label_low = clause_label.lower()
            for idx, c in clause_map.items():
                t = c["title"].lower()
                if t.startswith(label_low[:12]) or label_low[:16] in t:
                    matched_index = idx
                    break

        conf_str = re.sub(r"[^\d.]", "", conf_raw)
        try:
            cv       = float(conf_str) if conf_str else 50.0
            conf_int = max(0, min(100, int(cv if cv > 1.0 else cv * 100)))
        except (ValueError, ZeroDivisionError):
            conf_int = 50

        findings.append(AIFinding(
            clause_label  = clause_label[:50],
            risk          = risk,
            issue         = issue.strip()[:80],
            suggestion    = suggestion.strip()[:80],
            confidence    = conf_int,
            clause_index  = matched_index,
            source_models = [model_name],
            pass_number   = pass_num,
        ))

    return findings


# ─────────────────────────────────────────────────────────────────────────────
# 4f. BATCHED MODEL RUNNER  —  core of the coverage fix  [C05–C10]
# ─────────────────────────────────────────────────────────────────────────────
def run_model_over_all_clauses(
    model_name: str,
    role: str,
    system_prompt: str,
    clauses: list[dict],
    client: OllamaClient,
    pass_number: int = 1,
    show_progress: bool = True,
) -> ModelResult:
    """
    Split clauses into batches and call the model once per batch.
    Aggregates all findings into a single ModelResult.
    This guarantees EVERY clause reaches the model.  [C05, C08]
    """
    batches     = batch_clauses(clauses)
    all_findings: list[AIFinding] = []
    all_raw: list[str] = []
    total_elapsed = 0.0
    last_err = ""

    for batch_idx, batch in enumerate(batches, start=1):
        if show_progress:
            _status(
                f"    [{role:<13}] [{model_name}] "
                f"batch {batch_idx}/{len(batches)} "
                f"({len(batch)} clauses, "
                f"~{sum(min(len(c['body']), CHUNK_CHARS) for c in batch):,} chars) …"
            )

        prompt   = build_clause_prompt(batch)
        t0       = time.time()
        raw, err = client.generate(model_name, prompt, system_prompt)
        elapsed  = time.time() - t0
        total_elapsed += elapsed

        if err:
            last_err = err
            _warn(f"    [{role}] batch {batch_idx} error: {err}")
            continue

        batch_findings = parse_model_response(raw, model_name, clauses, pass_number)
        all_findings.extend(batch_findings)
        all_raw.append(raw)

        log.debug("Batch %d: %d findings in %.1fs", batch_idx, len(batch_findings), elapsed)

    if show_progress:
        icon = "✓" if not last_err else "✗"
        _status(
            f"  [{icon}] {role:<13} [{model_name}] "
            f"pass {pass_number} complete — "
            f"{len(all_findings)} findings across {len(batches)} batches "
            f"({total_elapsed:.1f}s total)"
        )

    return ModelResult(
        model_name  = model_name,
        role        = role,
        raw_output  = "\n".join(all_raw),
        findings    = all_findings,
        elapsed_sec = total_elapsed,
        error       = last_err,
        pass_number = pass_number,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4g. QUICK ANALYSER  (single model — complete coverage)
# ─────────────────────────────────────────────────────────────────────────────
class QuickAnalyser:
    def __init__(self, clauses: list[dict], client: OllamaClient) -> None:
        self.clauses = clauses
        self.client  = client
        self.model   = client.resolve_model(MODEL_QUICK, "llama3")

    def run(self) -> list[AIFinding]:
        if not self.client.is_alive():
            _banner_skipped("Ollama is not reachable at " + OLLAMA_BASE_URL)
            return []

        substantive = [c for c in self.clauses if len(c["body"]) > 20]
        _status(f"  Quick model [{self.model}] — {len(substantive)} clauses "
                f"in {len(batch_clauses(substantive))} batches …")

        result = run_model_over_all_clauses(
            model_name    = self.model,
            role          = "risk",
            system_prompt = SYSTEM_PROMPT_A,
            clauses       = substantive,
            client        = self.client,
            pass_number   = 1,
            show_progress = True,
        )

        if result.error and not result.findings:
            _banner_skipped(f"Quick model failed: {result.error}")
        return result.findings


# ─────────────────────────────────────────────────────────────────────────────
# 4h. MULTI-MODEL PARALLEL LAYER  (deep mode — all clauses, batched, but not parallel)
# ─────────────────────────────────────────────────────────────────────────────
class MultiModelLayer:
    """
    Run 3 specialist models sequentially (low VRAM optimized).
    Each model processes clauses in chunks.
    """

    def __init__(self, clauses: list[dict], client: OllamaClient) -> None:
        self.clauses = clauses
        self.client = client

        self.model_a = client.resolve_model(MODEL_A, "llama3")
        self.model_b = client.resolve_model(MODEL_B, self.model_a)
        self.model_c = client.resolve_model(MODEL_C, self.model_a)

        log.debug(
            "Models: A=%s B=%s C=%s",
            self.model_a, self.model_b, self.model_c
        )

    def run_pass(
        self,
        pass_number: int,
        focus_clauses: Optional[list[dict]] = None
    ) -> list[ModelResult]:

        target = focus_clauses if focus_clauses is not None else self.clauses
        substantive = [c for c in target if len(c["body"]) > 20]

        if not substantive:
            return []

        specs = [
            (self.model_a, "risk",         SYSTEM_PROMPT_A),
            (self.model_b, "compliance",   SYSTEM_PROMPT_B),
            (self.model_c, "completeness", SYSTEM_PROMPT_C),
        ]

        chunks = batch_clauses(substantive)

        _status(
            f"{len(substantive)} clauses → {len(chunks)} chunks "
            f"(sequential low-VRAM mode)"
        )

        results: list[ModelResult] = []

        for chunk_id, chunk in enumerate(chunks):
            _status(f"Chunk {chunk_id + 1}/{len(chunks)}")

            for model, role, prompt in specs:
                try:
                    res = run_model_over_all_clauses(
                        model_name=model,
                        role=role,
                        system_prompt=prompt,
                        clauses=chunk,
                        client=self.client,
                        pass_number=pass_number,
                        show_progress=True
                    )

                    results.append(res)

                    icon = "✓" if not res.error else "✗"
                    _status(
                        f"  [{icon}] {role:<13} [{model}] — "
                        f"{len(res.findings)} findings ({res.elapsed_sec:.1f}s)"
                    )

                except Exception as exc:
                    _warn(f"{role} [{model}] error: {exc}")

        return results


# ─────────────────────────────────────────────────────────────────────────────
# 4i. JUDGE MODEL
# ─────────────────────────────────────────────────────────────────────────────
class JudgeModel:
    CLAUSE_SNIPPET = 500

    def __init__(self, clauses: list[dict], client: OllamaClient) -> None:
        self.clauses     = clauses
        self.client      = client
        self.judge_model = client.resolve_model(JUDGE_MODEL, MODEL_A)

    def adjudicate(self, model_results: list[ModelResult]) -> list[AIFinding]:
        if not model_results:
            return []

        # Collect all unique findings from all results
        all_findings = [f for mr in model_results for f in mr.findings]
        if not all_findings:
            return []

        # Build judge prompt — summarise findings grouped by clause
        prompt   = self._build_judge_prompt(model_results)
        _status(f"  Judge [{self.judge_model}] synthesising "
                f"{len(all_findings)} findings from {len(model_results)} model runs …")
        t0       = time.time()
        raw, err = self.client.generate(
            self.judge_model, prompt, SYSTEM_PROMPT_JUDGE, temperature=0.05
        )
        elapsed  = time.time() - t0

        if err:
            _warn(f"Judge model error ({elapsed:.1f}s): {err} — using fallback merge")
            return self._fallback_merge(model_results)

        findings = self._parse_judge_response(raw)
        _status(f"  Judge done in {elapsed:.1f}s — {len(findings)} validated findings")
        return findings

    def _build_judge_prompt(self, model_results: list[ModelResult]) -> str:
        sections: list[str] = []

        # Top substantive clauses as context (capped to avoid judge token overflow)
        snippets = []
        by_body = sorted([c for c in self.clauses if len(c["body"]) > 20],
                          key=lambda x: -len(x["body"]))[:20]
        for c in by_body:
            snippet = (c["title"] + " " + c["body"])[:self.CLAUSE_SNIPPET].replace("\n", " ")
            snippets.append(f"[{c['index']}] {snippet}")
        sections.append("[ORIGINAL CLAUSES]\n" + "\n\n".join(snippets))

        role_labels = {"risk": "A — Risk", "compliance": "B — Compliance",
                       "completeness": "C — Completeness"}
        for res in model_results:
            if not res.raw_output.strip():
                continue
            label  = role_labels.get(res.role, res.role.upper())
            header = f"[MODEL {label} | model={res.model_name} | pass={res.pass_number}]"
            sections.append(header + "\n" + res.raw_output.strip()[:8000])

        return "\n\n" + ("═" * 60 + "\n\n").join(sections)

    def _parse_judge_response(self, raw: str) -> list[AIFinding]:
        findings: list[AIFinding] = []
        clause_map = {c["index"]: c for c in self.clauses}

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or set(line) <= set("-=+~"):
                continue
            parts = re.split(r"\s*\|\s*", line, maxsplit=6)
            if len(parts) < 5:
                continue

            clause_raw = parts[0]
            risk       = parts[1].strip().upper() if len(parts) > 1 else ""
            issue      = parts[2].strip()         if len(parts) > 2 else ""
            suggestion = parts[3].strip()         if len(parts) > 3 else ""
            conf_raw   = parts[4].strip()         if len(parts) > 4 else "70"
            models_raw = parts[5].strip()         if len(parts) > 5 else ""
            note       = parts[6].strip()         if len(parts) > 6 else "validated"

            if risk not in VALID_RISKS:
                continue

            matched_index = -1
            clause_label  = clause_raw
            idx_m = re.match(r"\[(\d+)]", clause_raw.strip())
            if idx_m:
                candidate = int(idx_m.group(1))
                if candidate in clause_map:
                    matched_index = candidate
                    clause_label  = clause_raw[idx_m.end():].strip() or \
                                    clause_map[candidate]["title"][:50]

            conf_str = re.sub(r"[^\d.]", "", conf_raw)
            try:
                cv       = float(conf_str) if conf_str else 70.0
                conf_int = max(0, min(100, int(cv if cv > 1.0 else cv * 100)))
            except (ValueError, ZeroDivisionError):
                conf_int = 70

            source = [m.strip() for m in models_raw.split(",") if m.strip()] or ["judge"]
            findings.append(AIFinding(
                clause_label    = clause_label[:50],
                risk            = risk,
                issue           = issue[:80],
                suggestion      = suggestion[:80],
                confidence      = conf_int,
                clause_index    = matched_index,
                source_models   = source,
                judge_validated = True,
                judge_note      = note[:60],
                pass_number     = 0,
            ))
        return findings

    @staticmethod
    def _fallback_merge(model_results: list[ModelResult]) -> list[AIFinding]:
        RISK_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        bucket: dict[str, AIFinding] = {}
        for mr in model_results:
            for f in mr.findings:
                key = f"{f.clause_label[:10].lower()}|{f.risk}|{f.issue[:12].lower()}"
                if key not in bucket:
                    bucket[key] = f
                else:
                    ex = bucket[key]
                    if f.confidence > ex.confidence:
                        f.source_models = list(set(ex.source_models + f.source_models))
                        bucket[key] = f
                    else:
                        ex.source_models = list(set(ex.source_models + f.source_models))
        merged = sorted(bucket.values(),
                        key=lambda f: (RISK_RANK.get(f.risk, 0), f.confidence),
                        reverse=True)
        for f in merged:
            f.judge_validated = False
            f.judge_note      = "programmatic merge (judge unavailable)"
        return merged


# ─────────────────────────────────────────────────────────────────────────────
# 4j. DEEP AUDIT ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────
class DeepAuditOrchestrator:
    def __init__(self, clauses: list[dict], client: OllamaClient) -> None:
        self.clauses         = clauses
        self.client          = client
        self.multi_layer     = MultiModelLayer(clauses, client)
        self.judge           = JudgeModel(clauses, client)
        self.all_results:    list[ModelResult] = []
        self.final_findings: list[AIFinding]   = []

    def run(self) -> list[AIFinding]:
        if not self.client.is_alive():
            _banner_skipped("Ollama is not reachable at " + OLLAMA_BASE_URL)
            return []

        # Pass 1 — all clauses, all 3 models
        print()
        _status(col("Pass 1 — Broad analysis (3 models, all clauses, batched)",
                    C.CYAN, C.BOLD))
        p1 = self.multi_layer.run_pass(pass_number=1)
        self.all_results.extend(p1)

        if INTER_PASS_SLEEP > 0:
            time.sleep(INTER_PASS_SLEEP)

        # Pass 2 — only CRITICAL/HIGH-flagged clauses get deeper focus
        focus = self._high_risk_clauses(p1)
        if focus:
            print()
            _status(col(f"Pass 2 — Deep re-analysis on {len(focus)} "
                        f"high-risk clause(s)", C.CYAN, C.BOLD))
            p2 = self.multi_layer.run_pass(pass_number=2, focus_clauses=focus)
            self.all_results.extend(p2)
            if INTER_PASS_SLEEP > 0:
                time.sleep(INTER_PASS_SLEEP)
        else:
            _status("  Pass 2 skipped — no CRITICAL/HIGH clauses in pass 1")

        # Judge
        print()
        _status(col("Judge synthesis — deduplication + conflict resolution",
                    C.CYAN, C.BOLD))
        self.final_findings = self.judge.adjudicate(self.all_results)
        return self.final_findings

    def _high_risk_clauses(self, results: list[ModelResult]) -> list[dict]:
        idx_set: set[int] = set()
        for mr in results:
            for f in mr.findings:
                if f.risk in ("CRITICAL", "HIGH") and f.clause_index >= 0:
                    idx_set.add(f.clause_index)
        by_idx = {c["index"]: c for c in self.clauses}
        return [by_idx[i] for i in idx_set if i in by_idx]

    @property
    def model_results(self) -> list[ModelResult]:
        return self.all_results


# ─────────────────────────────────────────────────────────────────────────────
# 5. FINDING AGGREGATOR
# ─────────────────────────────────────────────────────────────────────────────
class FindingAggregator:
    RISK_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    @staticmethod
    def deduplicate_ai(findings: list[AIFinding]) -> list[AIFinding]:
        seen: dict[str, AIFinding] = {}
        for f in findings:
            key = f"{f.clause_label[:10].lower()}|{f.risk}|{f.issue[:10].lower()}"
            if key not in seen or f.confidence > seen[key].confidence:
                seen[key] = f
        return sorted(seen.values(),
                      key=lambda f: (FindingAggregator.RISK_RANK.get(f.risk, 0),
                                     f.confidence),
                      reverse=True)

    @staticmethod
    def merge_stats(rule_findings: list[dict],
                    ai_findings: list[AIFinding]) -> dict:
        counts: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for f in rule_findings:
            counts[f.get("severity", "LOW")] = counts.get(f.get("severity", "LOW"), 0) + 1
        for f in ai_findings:
            counts[f.risk] = counts.get(f.risk, 0) + 1
        return counts


# ─────────────────────────────────────────────────────────────────────────────
# 6. AUDIT SCORER
# ─────────────────────────────────────────────────────────────────────────────
class AuditScorer:
    RULE_PENALTY = {"CRITICAL": 12, "HIGH": 7, "MEDIUM": 4, "LOW": 2, "INFO": 0}
    AI_PENALTY   = {"CRITICAL":  6, "HIGH": 4, "MEDIUM": 2, "LOW": 1}

    def compute(self, rule_findings: list[dict], ai_findings: list[AIFinding]) -> int:
        rule_total = sum(self.RULE_PENALTY.get(f["severity"], 0) for f in rule_findings)
        ai_total   = sum(self.AI_PENALTY.get(f.risk, 0) for f in ai_findings)
        return max(0, min(100, 100 - rule_total - ai_total))

    @staticmethod
    def grade(score: int) -> tuple[str, str]:
        if score >= 85: return "A", C.GREEN
        if score >= 70: return "B", C.CYAN
        if score >= 55: return "C", C.YELLOW
        if score >= 40: return "D", C.MAGENTA
        return "F", C.RED


# ─────────────────────────────────────────────────────────────────────────────
# 7. OUTPUT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────
class OutputGenerator:
    SEV_COLOUR = {
        "CRITICAL": C.RED, "HIGH": C.MAGENTA,
        "MEDIUM": C.YELLOW, "LOW": C.CYAN, "INFO": C.DIM,
    }

    def __init__(self, filepath: str, clauses: list[dict],
                 rule_findings: list[dict], ai_findings: list[AIFinding],
                 score: int, mode: str, ai_skipped: bool,
                 model_results: Optional[list[ModelResult]] = None) -> None:
        self.filepath      = filepath
        self.clauses       = clauses
        self.rule_findings = rule_findings
        self.ai_findings   = ai_findings
        self.score         = score
        self.mode          = mode
        self.ai_skipped    = ai_skipped
        self.model_results = model_results or []

    def render(self) -> None:
        self._header()
        self._summary_box()
        if self.mode == "deep" and self.model_results:
            self._model_panel()
        self._rule_findings()
        self._ai_findings()
        self._missing_clauses()
        if self.mode == "deep":
            self._judge_section()
        self._footer()

    def _header(self) -> None:
        print()
        print(col("╔" + "═" * (TERMINAL_WIDTH - 2) + "╗", C.CYAN, C.BOLD))
        title = "  CLEARFOLIO REVIEW v3.1 — CONTRACT AUDIT REPORT  "
        pad   = (TERMINAL_WIDTH - 2 - len(title)) // 2
        print(col("║" + " " * pad + title +
                  " " * (TERMINAL_WIDTH - 2 - pad - len(title)) + "║", C.CYAN, C.BOLD))
        print(col("╚" + "═" * (TERMINAL_WIDTH - 2) + "╝", C.CYAN, C.BOLD))
        print(col(f"  File    : {os.path.basename(self.filepath)}", C.WHITE))
        print(col(f"  Audited : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}", C.DIM))
        print(col(f"  Clauses : {len(self.clauses)} (chunks after sub-split)", C.DIM))
        print(col(f"  Mode    : {self.mode.upper()}", C.DIM))
        print()

    def _summary_box(self) -> None:
        grade, gcol = AuditScorer.grade(self.score)
        stats       = FindingAggregator.merge_stats(self.rule_findings, self.ai_findings)
        bar_fill    = int(self.score / 100 * 44)
        bar         = col("█" * bar_fill, gcol) + col("░" * (44 - bar_fill), C.DIM)

        print(hr("═", C.BOLD))
        print(col("  AUDIT SCORE", C.BOLD, C.WHITE))
        print(hr("─"))
        print(f"  Score : {col(str(self.score) + ' / 100', gcol, C.BOLD)}"
              f"   Grade : {col(grade, gcol, C.BOLD)}")
        print(f"  [{bar}]")
        print()
        print(f"  Totals :  "
              f"{col(str(stats['CRITICAL']) + ' CRITICAL', C.RED, C.BOLD)}  "
              f"{col(str(stats['HIGH'])     + ' HIGH',     C.MAGENTA)}  "
              f"{col(str(stats['MEDIUM'])   + ' MEDIUM',   C.YELLOW)}  "
              f"{col(str(stats['LOW'])      + ' LOW',      C.CYAN)}")
        print(f"  Sources:  Rule engine {col(str(len(self.rule_findings)), C.WHITE)}  "
              f"AI {col(str(len(self.ai_findings)), C.WHITE)}"
              + (col("  [AI skipped]", C.YELLOW) if self.ai_skipped else ""))
        print(hr("═", C.BOLD))
        print()

    def _model_panel(self) -> None:
        print(col("  MODEL PERFORMANCE SUMMARY", C.BOLD, C.WHITE))
        print(hr("─"))
        passes: dict[int, list[ModelResult]] = {}
        for mr in self.model_results:
            passes.setdefault(mr.pass_number, []).append(mr)
        for pass_num in sorted(passes.keys()):
            print(col(f"  Pass {pass_num}:", C.BOLD, C.CYAN))
            for mr in passes[pass_num]:
                ok = col("✓", C.GREEN) if not mr.error else col("✗", C.RED)
                print(f"    {ok}  {col(mr.model_name, C.WHITE):<28}  "
                      f"[{mr.role}]  {len(mr.findings)} findings  "
                      f"{round(mr.elapsed_sec, 1)}s"
                      + (col(f"  {mr.error[:40]}", C.RED) if mr.error else ""))
        print()

    def _rule_findings(self) -> None:
        if not self.rule_findings:
            print(col("  ✓ No deterministic rule violations found.", C.GREEN, C.BOLD))
            print(); return
        print(col(f"  RULE ENGINE FINDINGS  ({len(self.rule_findings)})", C.BOLD, C.WHITE))
        print(hr("─"))
        for f in self.rule_findings:
            sc = self.SEV_COLOUR.get(f["severity"], C.WHITE)
            print(f"  {col('['+f['severity']+']', sc, C.BOLD):<30} "
                  f"{col(f['rule_id'], C.DIM)}  {col(f['title'], C.WHITE, C.BOLD)}")
            wrapped = textwrap.fill(f["detail"], width=TERMINAL_WIDTH - 8,
                                    initial_indent=" " * 6, subsequent_indent=" " * 6)
            print(col(wrapped, C.DIM))
            if f["clause_index"] >= 0:
                ci    = f["clause_index"]
                label = self.clauses[ci]["title"][:60] if ci < len(self.clauses) else "—"
                print(col(f"       ↳ Clause [{ci}]: {label}", C.DIM))
            print()
        print()

    def _ai_findings(self) -> None:
        if not self.ai_findings:
            msg = "AI ANALYSIS SKIPPED" if self.ai_skipped else "AI returned no findings."
            print(col(f"  ⊘  {msg}", C.YELLOW)); print(); return
        label = ("MULTI-MODEL AI — JUDGE VALIDATED"
                 if self.mode == "deep" else f"AI ANALYSIS  [{MODEL_QUICK}]")
        print(col(f"  {label}", C.BOLD, C.WHITE))
        print(hr("─"))
        cw = [26, 10, 27, 27, 7]
        headers = ["Clause", "Risk", "Issue", "Suggestion", "Conf"]
        if self.mode == "deep":
            headers.append("Models")
        print("  " + "  ".join(col(f"{h:<{cw[i]}}" if i < len(cw) else h, C.BOLD)
                                for i, h in enumerate(headers)))
        print("  " + "─" * (sum(cw) + 2 * len(cw)))
        for f in self.ai_findings:
            rc  = self.SEV_COLOUR.get(f.risk, C.WHITE)
            cc  = C.GREEN if f.confidence >= 80 else (C.YELLOW if f.confidence >= 60 else C.RED)
            vtag = col("✓", C.GREEN) if f.judge_validated else col("·", C.DIM)
            row = (
                col(f"{f.clause_label[:cw[0]]:<{cw[0]}}", C.WHITE) + "  " +
                col(f"{f.risk:<{cw[1]}}", rc, C.BOLD) + "  " +
                f"{f.issue[:cw[2]]:<{cw[2]}}  " +
                f"{f.suggestion[:cw[3]]:<{cw[3]}}  " +
                col(f"{str(f.confidence)+'%':<{cw[4]}}", cc)
            )
            if self.mode == "deep":
                row += "  " + col(f"{vtag} {','.join(f.source_models)[:10]}", C.DIM)
            print("  " + row)
        print()

    def _missing_clauses(self) -> None:
        ids     = {f"R{str(i).zfill(2)}" for i in range(1, 16)}
        missing = [f for f in self.rule_findings if f["rule_id"] in ids]
        if not missing:
            print(col("  ✓ All standard clauses present.", C.GREEN)); print(); return
        print(col(f"  MISSING / ABSENT CLAUSES  ({len(missing)})", C.BOLD, C.RED))
        print(hr("─"))
        for f in missing:
            sc = self.SEV_COLOUR.get(f["severity"], C.WHITE)
            print(f"  {col('✗', sc, C.BOLD)}  {col(f['title'], C.WHITE)}"
                  f"  {col('['+f['severity']+']', sc)}")
        print()

    def _judge_section(self) -> None:
        validated = [f for f in self.ai_findings if f.judge_validated]
        consensus = [f for f in self.ai_findings if len(f.source_models) >= 2]
        print(col("  JUDGE VALIDATION SUMMARY", C.BOLD, C.WHITE))
        print(hr("─"))
        print(f"  Judge-validated : {col(str(len(validated)), C.GREEN, C.BOLD)}")
        print(f"  Multi-model consensus (≥2 models): {col(str(len(consensus)), C.CYAN)}")
        if consensus:
            print()
            for f in sorted(consensus,
                            key=lambda x: ({"CRITICAL":4,"HIGH":3,"MEDIUM":2,"LOW":1}
                                           .get(x.risk, 0), x.confidence),
                            reverse=True)[:8]:
                rc  = self.SEV_COLOUR.get(f.risk, C.WHITE)
                src = ",".join(f.source_models)
                print(f"    {col(f.risk, rc, C.BOLD):<22}  "
                      f"{col(f.clause_label[:28], C.WHITE):<30}  "
                      f"src={col(src, C.DIM):<10}  "
                      f"conf={col(str(f.confidence)+'%', C.GREEN)}"
                      + (f"  {col(f.judge_note[:40], C.DIM)}" if f.judge_note else ""))
        print()

    def _footer(self) -> None:
        print(hr("═", C.BOLD))
        print(col("  Clearfolio Review v3.1 | Local-Only | No Data Leaves This Machine",
                  C.DIM))
        print(col("  DISCLAIMER: AI-assisted output. Does not constitute legal advice.",
                  C.DIM))
        print(hr("═", C.BOLD))
        print()


# ─────────────────────────────────────────────────────────────────────────────
# 8. REPORT EXPORT
# ─────────────────────────────────────────────────────────────────────────────
def export_report(filepath: str, clauses: list[dict],
                  rule_findings: list[dict], ai_findings: list[AIFinding],
                  score: int, grade: str, mode: str,
                  ai_skipped: bool, model_results: list[ModelResult],
                  fmt: str) -> str:
    base     = os.path.splitext(filepath)[0]
    out_path = f"{base}_audit.{fmt}"

    if fmt == "json":
        data = {
            "clearfolio_version": "3.1",
            "audited_at":      datetime.now().isoformat(),
            "filename":        os.path.basename(filepath),
            "mode":            mode,
            "score":           score,
            "grade":           grade,
            "clauses_count":   len(clauses),
            "ai_skipped":      ai_skipped,
            "chunk_chars":     CHUNK_CHARS,
            "batch_chars":     BATCH_CHARS,
            "rule_findings":   rule_findings,
            "ai_findings":     [asdict(f) for f in ai_findings],
            "model_results": [
                {"model": mr.model_name, "role": mr.role, "pass": mr.pass_number,
                 "findings": len(mr.findings), "elapsed_sec": round(mr.elapsed_sec, 1),
                 "error": mr.error or None}
                for mr in model_results
            ],
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
    elif fmt == "txt":
        lines = [
            "CLEARFOLIO REVIEW v3.1 — AUDIT REPORT", "=" * 60,
            f"File    : {os.path.basename(filepath)}",
            f"Audited : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Score   : {score}/100  Grade: {grade}",
            f"Mode    : {mode}  Clauses: {len(clauses)}", "",
            "RULE FINDINGS", "-" * 40,
        ]
        for f in rule_findings:
            lines += [f"[{f['severity']}] {f['rule_id']} {f['title']}",
                      f"    {f['detail']}", ""]
        lines += ["", "AI FINDINGS", "-" * 40]
        for f in ai_findings:
            lines += [f"[{f.risk}] {f.clause_label}  conf={f.confidence}%",
                      f"    Issue      : {f.issue}",
                      f"    Suggestion : {f.suggestion}", ""]
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="clearfolio_review",
        description="Clearfolio Review v3.1 — Complete-coverage contract auditor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python clearfolio_review.py contract.docx
              python clearfolio_review.py contract.docx --mode deep --output json
              CF_BATCH_CHARS=6000 python clearfolio_review.py big_contract.docx --mode deep

            tuning for slow machines (small context models):
              CF_BATCH_CHARS=4000 CF_CHUNK_CHARS=800  → smaller batches, more calls
              CF_TIMEOUT=300                           → allow 5 min per call

            tuning for fast machines (large context models):
              CF_BATCH_CHARS=16000 CF_CHUNK_CHARS=2400 → fewer, larger batches

            env variables:
              CF_OLLAMA_URL     Ollama URL           (default: http://localhost:11434)
              CF_TIMEOUT        Seconds per call     (default: 240)
              CF_RETRIES        Retry count          (default: 3)
              CF_CHUNK_CHARS    Max chars per clause (default: 1600)
              CF_BATCH_CHARS    Max chars per batch  (default: 8000)
              CF_CHUNK_OVERLAP  Sub-chunk overlap    (default: 150)
              CF_MODEL_QUICK    Quick mode model     (default: llama3)
              CF_MODEL_A        Risk specialist      (default: llama3)
              CF_MODEL_B        Compliance specialist(default: mistral)
              CF_MODEL_C        Completeness spec.   (default: phi3)
              CF_JUDGE_MODEL    Judge model          (default: deepseek-r1)
        """),
    )
    p.add_argument("filepath", help=".docx contract file path")
    p.add_argument("--mode", choices=["quick", "deep"], default="quick")
    p.add_argument("--output", choices=["json", "txt"], default=None)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--info", action="store_true",
                   help="print architecture notes and exit")
    return p.parse_args()


def _print_info() -> None:
    print(textwrap.dedent("""\
    CLEARFOLIO REVIEW v3.1 — ARCHITECTURE NOTES
    ════════════════════════════════════════════

    Coverage fix (why v3 only saw 4% of documents):
    ─────────────────────────────────────────────
    v3 bug: DocumentParser used text-pattern matching for clause detection.
    The test contract had 190 "List Paragraph" style paragraphs — all lumped
    into one giant section body (39,796 chars). Since only 450 chars per
    clause were sent to LLMs, and only top-N clauses were selected, the
    system saw ~4% of the document.

    v3.1 fix:
      1. Parser primary signal = paragraph.style (Heading N, Title, etc.)
      2. List Paragraph / Body Text are BODY, never start new sections
      3. Large sections split into overlapping sub-chunks (CHUNK_CHARS=1600)
      4. All clauses are sent — no top-N selector
      5. Batched: each LLM call gets BATCH_CHARS chars (default 8,000)
         so one 100-page contract → ~N batches per model, each fully covered
      6. CHUNK_CHARS=1600 fills llama3 context (8k tokens ≈ 24k chars)
         properly vs old 450 chars

    Pipeline:
      .docx → Loader → Parser (style+subchunk) → RuleEngine
            → [Batched AI] → Aggregator → Score → Output
    """))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()
    _configure_logging(args.verbose)

    if args.info:
        _print_info()
        sys.exit(0)

    print()
    mode_tag = col(f"[{args.mode.upper()} MODE]", C.BOLD,
                   C.GREEN if args.mode == "deep" else C.BLUE)
    print(col("  ■ CLEARFOLIO REVIEW v3.1 ", C.CYAN, C.BOLD) + mode_tag)
    print()

    # Step 1: Load
    _status("Loading document …")
    loader = DocumentLoader(args.filepath).load()
    _status(f"Loaded {len(loader.raw_paragraphs)} paragraphs "
            f"from {col(os.path.basename(args.filepath), C.WHITE)}"
            + (col("  [truncated]", C.YELLOW) if loader.truncated else ""))

    # Step 2: Parse with sub-chunking
    _status("Parsing clauses (style-aware + sub-chunking) …")
    clauses = DocumentParser(loader).parse()
    substantive = [c for c in clauses if len(c["body"]) > 20]
    n_batches_est = len(batch_clauses(substantive))
    _status(
        f"Detected {col(str(len(clauses)), C.WHITE)} chunks "
        f"({len(substantive)} substantive, "
        f"~{n_batches_est} batch(es)/model with "
        f"BATCH_CHARS={BATCH_CHARS:,} CHUNK_CHARS={CHUNK_CHARS:,})"
    )

    # Step 3: Rule Engine (runs on full_text — complete coverage always)
    _status("Running rule engine (30 rules, full document) …")
    rule_findings = RuleEngine(clauses, loader.full_text).run()
    _status(f"Rule engine: {col(str(len(rule_findings)), C.WHITE)} findings")

    # Step 4: AI Analysis
    client         = OllamaClient()
    ai_findings:   list[AIFinding]  = []
    model_results: list[ModelResult] = []
    ai_skipped     = False

    if args.mode == "quick":
        _section("Quick AI Analysis — All Clauses, Batched")
        ai_findings = QuickAnalyser(clauses, client).run()
        if not ai_findings and not client.is_alive():
            ai_skipped = True

    else:
        _section("Deep AI Analysis — 3 Models × All Clauses × Batched + Judge")
        orch          = DeepAuditOrchestrator(clauses, client)
        ai_findings   = orch.run()
        model_results = orch.model_results
        if not ai_findings and not client.is_alive():
            ai_skipped = True

    # Step 5: Deduplicate
    ai_findings = FindingAggregator.deduplicate_ai(ai_findings)
    cache_hits  = _prompt_cache.size()
    _status(f"Final AI findings: {col(str(len(ai_findings)), C.WHITE)}"
            + (f"  {col(f'(cache hits: {cache_hits})', C.DIM)}" if cache_hits else ""))

    # Step 6: Score
    score        = AuditScorer().compute(rule_findings, ai_findings)
    grade, _gcol = AuditScorer.grade(score)

    # Step 7: Terminal report
    _status("Generating report …\n")
    OutputGenerator(
        filepath      = args.filepath,
        clauses       = clauses,
        rule_findings = rule_findings,
        ai_findings   = ai_findings,
        score         = score,
        mode          = args.mode,
        ai_skipped    = ai_skipped,
        model_results = model_results,
    ).render()

    # Step 8: Optional export
    if args.output:
        out_path = export_report(
            filepath      = args.filepath,
            clauses       = clauses,
            rule_findings = rule_findings,
            ai_findings   = ai_findings,
            score         = score,
            grade         = grade,
            mode          = args.mode,
            ai_skipped    = ai_skipped,
            model_results = model_results,
            fmt           = args.output,
        )
        _status(col(f"Report saved → {out_path}", C.GREEN))


if __name__ == "__main__":
    main()
