// ─────────────────────────────────────────────────────────────
// Clearfolio Review — Shared TypeScript Types
// ─────────────────────────────────────────────────────────────

export type Severity   = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type RiskLevel  = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NONE";
export type AuditMode  = "quick" | "deep";
export type Grade      = "A" | "B" | "C" | "D" | "F";

// ── Rule Engine Finding ───────────────────────────────────────
export interface RuleFinding {
  rule_id:      string;       // e.g. "R01"
  category:     string;       // e.g. "Missing Clause"
  severity:     Severity;
  title:        string;
  detail:       string;
  clause_index: number;       // -1 = document-level
}

// ── AI / Judge Finding ────────────────────────────────────────
export interface AIFinding {
  clause_label:    string;
  risk:            RiskLevel;
  issue:           string;
  suggestion:      string;
  confidence:      number;     // 0–100
  clause_index:    number;
  source_models:   string[];
  judge_validated: boolean;
  judge_note:      string;
  pass_number:     number;
}

// ── Missing Clause (subset of RuleFinding) ────────────────────
export interface MissingClause {
  rule_id:  string;
  title:    string;
  severity: Severity;
}

// ── Model Performance (deep mode) ────────────────────────────
export interface ModelSummary {
  model:       string;
  role:        string;
  pass:        number;
  findings:    number;
  elapsed_sec: number;
  error:       string | null;
}

// ── Full Audit Report ─────────────────────────────────────────
export interface AuditReport {
  filename:        string;
  score:           number;
  grade:           Grade;
  mode:            AuditMode;
  clauses_count:   number;
  rule_findings:   RuleFinding[];
  ai_findings:     AIFinding[];
  missing_clauses: MissingClause[];
  model_summary:   ModelSummary[];
  error:           string | null;
}

// ── UI State ──────────────────────────────────────────────────
export type AppState = "idle" | "processing" | "done" | "error";

export interface UploadedFile {
  name: string;
  size: number;
  mode: AuditMode;
}

// ── Helpers ───────────────────────────────────────────────────
export const SEVERITY_ORDER: Record<Severity, number> = {
  CRITICAL: 4,
  HIGH:     3,
  MEDIUM:   2,
  LOW:      1,
  INFO:     0,
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  CRITICAL: "Critical",
  HIGH:     "High",
  MEDIUM:   "Medium",
  LOW:      "Low",
  NONE:     "None",
};

export function gradeColour(grade: Grade): string {
  return {
    A: "#2E7D32",
    B: "#0277BD",
    C: "#F57F17",
    D: "#E65100",
    F: "#B71C1C",
  }[grade] ?? "#1A1917";
}

export function riskColour(risk: RiskLevel | Severity): string {
  return {
    CRITICAL: "#C8392B",
    HIGH:     "#C05621",
    MEDIUM:   "#92680A",
    LOW:      "#1D5A8E",
    NONE:     "#3A7D44",
    INFO:     "#6B6963",
  }[risk] ?? "#1A1917";
}

export function riskBg(risk: RiskLevel | Severity): string {
  return {
    CRITICAL: "#FDF0EE",
    HIGH:     "#FDF3EE",
    MEDIUM:   "#FDF8EC",
    LOW:      "#EEF4FC",
    NONE:     "#EEF7EF",
    INFO:     "#F4F3EE",
  }[risk] ?? "#F4F3EE";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024)       return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
