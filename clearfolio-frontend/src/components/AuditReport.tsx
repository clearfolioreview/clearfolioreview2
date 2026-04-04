"use client";

import { useState } from "react";
import {
  AuditReport, RuleFinding, AIFinding,
  MissingClause, Severity, riskColour, riskBg, SEVERITY_ORDER,
} from "@/types/audit";
import ScoreBadge  from "./ScoreBadge";
import { RuleCard, AICard } from "./FindingCard";

interface AuditReportProps {
  report:     AuditReport;
  onReset:    () => void;
}

type Tab = "overview" | "rules" | "ai" | "missing";
type Filter = "ALL" | "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export default function AuditReportView({ report, onReset }: AuditReportProps) {
  const [tab,    setTab]    = useState<Tab>("overview");
  const [filter, setFilter] = useState<Filter>("ALL");

  const deepMode = report.mode === "deep";

  // ── Derived stats ──────────────────────────────────────────
  const allRuleFindings = report.rule_findings;
  const allAiFindings   = report.ai_findings;

  const ruleCount = (sev: Severity) =>
    allRuleFindings.filter((f) => f.severity === sev).length;
  const aiCount = (risk: string) =>
    allAiFindings.filter((f) => f.risk === risk).length;

  const totalCritical = ruleCount("CRITICAL") + aiCount("CRITICAL");
  const totalHigh     = ruleCount("HIGH")     + aiCount("HIGH");
  const totalMedium   = ruleCount("MEDIUM")   + aiCount("MEDIUM");
  const totalLow      = ruleCount("LOW")      + aiCount("LOW");

  // ── Filtered findings ──────────────────────────────────────
  const filteredRules = filter === "ALL"
    ? allRuleFindings
    : allRuleFindings.filter((f) => f.severity === filter);

  const filteredAI = filter === "ALL"
    ? allAiFindings
    : allAiFindings.filter((f) => f.risk === filter);

  // ── Error state ────────────────────────────────────────────
  if (report.error && !report.rule_findings.length && !report.ai_findings.length) {
    return <ErrorPanel error={report.error} onReset={onReset} />;
  }

  return (
    <div className="animate-[fadeIn_0.45s_ease_forwards]">

      {/* ── Top bar ────────────────────────────────────────── */}
      <div
        className="flex items-center justify-between mb-8 pb-5"
        style={{ borderBottom: "1px solid #E4E3DC" }}
      >
        <div>
          <div
            className="font-mono text-xs uppercase tracking-widest mb-1"
            style={{ color: "#A8A49D" }}
          >
            Audit Complete · {report.mode} mode
          </div>
          <h2
            className="font-heading font-600 text-xl"
            style={{ color: "#1A1917" }}
          >
            {report.filename}
          </h2>
          <p
            className="text-sm mt-0.5"
            style={{ color: "#6B6963" }}
          >
            {report.clauses_count} clauses analysed
            {deepMode && report.model_summary.length > 0 &&
              ` · ${report.model_summary.length} model runs`}
          </p>
        </div>
        <button
          onClick={onReset}
          className="font-mono text-xs px-3 py-1.5 rounded-lg border transition-colors"
          style={{ color: "#6B6963", borderColor: "#E4E3DC" }}
        >
          ← New audit
        </button>
      </div>

      {/* ── Score + stat pills ─────────────────────────────── */}
      <div className="flex items-center gap-8 mb-10 flex-wrap">
        <ScoreBadge score={report.score} grade={report.grade} size={110} />
        <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "Critical", count: totalCritical, sev: "CRITICAL" },
            { label: "High",     count: totalHigh,     sev: "HIGH" },
            { label: "Medium",   count: totalMedium,   sev: "MEDIUM" },
            { label: "Low",      count: totalLow,      sev: "LOW" },
          ].map(({ label, count, sev }) => (
            <StatPill
              key={sev}
              label={label}
              count={count}
              severity={sev as Severity}
              active={filter === sev}
              onClick={() => setFilter((f) => f === sev ? "ALL" : sev as Filter)}
            />
          ))}
        </div>
      </div>

      {/* ── Privacy + privacy note ─────────────────────────── */}
      <PrivacyBanner />

      {/* ── Tab bar ────────────────────────────────────────── */}
      <div
        className="flex gap-0 mb-6 rounded-lg p-1"
        style={{ backgroundColor: "#F4F3EE", display: "inline-flex" }}
      >
        {([
          { id: "overview", label: "Overview",       count: null },
          { id: "rules",    label: "Rule Findings",  count: allRuleFindings.length },
          { id: "ai",       label: "AI Findings",    count: allAiFindings.length },
          { id: "missing",  label: "Missing",         count: report.missing_clauses.length },
        ] as { id: Tab; label: string; count: number | null }[]).map((t) => (
          <TabBtn
            key={t.id}
            label={t.label}
            count={t.count}
            active={tab === t.id}
            onClick={() => setTab(t.id)}
          />
        ))}
      </div>

      {/* ── Tab content ───────────────────────────────────── */}

      {/* OVERVIEW ─────────────────────────────────────────── */}
      {tab === "overview" && (
        <div className="stagger space-y-3">
          {/* Critical + High rule findings first */}
          {allRuleFindings
            .filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH")
            .slice(0, 4)
            .map((f) => (
              <RuleCard key={f.rule_id} finding={f} />
            ))}

          {/* Top AI findings */}
          {allAiFindings
            .filter((f) => f.risk === "CRITICAL" || f.risk === "HIGH")
            .slice(0, 3)
            .map((f, i) => (
              <AICard key={i} finding={f} deepMode={deepMode} />
            ))}

          {/* Missing clauses summary */}
          {report.missing_clauses.length > 0 && (
            <div
              className="rounded-lg border px-4 py-4"
              style={{ borderColor: "#E4E3DC", backgroundColor: "#FAFAF7" }}
            >
              <p
                className="font-mono text-xs uppercase tracking-widest mb-3"
                style={{ color: "#A8A49D" }}
              >
                Missing Clauses ({report.missing_clauses.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {report.missing_clauses.map((mc) => (
                  <MissingTag key={mc.rule_id} mc={mc} />
                ))}
              </div>
            </div>
          )}

          {/* Deep mode: model summary */}
          {deepMode && report.model_summary.length > 0 && (
            <ModelSummaryPanel summary={report.model_summary} />
          )}
        </div>
      )}

      {/* RULE FINDINGS ────────────────────────────────────── */}
      {tab === "rules" && (
        <>
          <FilterBar filter={filter} onChange={setFilter} />
          <div className="stagger space-y-3 mt-4">
            {filteredRules.length === 0 ? (
              <EmptyState message="No rule findings match this filter." />
            ) : (
              [...filteredRules]
                .sort((a, b) =>
                  SEVERITY_ORDER[b.severity as Severity] -
                  SEVERITY_ORDER[a.severity as Severity]
                )
                .map((f) => <RuleCard key={f.rule_id} finding={f} />)
            )}
          </div>
        </>
      )}

      {/* AI FINDINGS ──────────────────────────────────────── */}
      {tab === "ai" && (
        <>
          <FilterBar filter={filter} onChange={setFilter} />
          <div className="stagger space-y-3 mt-4">
            {filteredAI.length === 0 ? (
              <EmptyState
                message={
                  allAiFindings.length === 0
                    ? "AI analysis was skipped or returned no findings. Ensure Ollama is running."
                    : "No AI findings match this filter."
                }
              />
            ) : (
              filteredAI.map((f, i) => (
                <AICard key={i} finding={f} deepMode={deepMode} />
              ))
            )}
          </div>
        </>
      )}

      {/* MISSING CLAUSES ──────────────────────────────────── */}
      {tab === "missing" && (
        <div className="stagger space-y-2 mt-1">
          {report.missing_clauses.length === 0 ? (
            <div
              className="rounded-lg border px-4 py-4 flex items-center gap-3"
              style={{ borderColor: "#2E7D3244", backgroundColor: "#EEF7EF" }}
            >
              <span style={{ fontSize: "18px" }}>✓</span>
              <p className="text-sm" style={{ color: "#2E7D32" }}>
                All standard clauses are present in this contract.
              </p>
            </div>
          ) : (
            report.missing_clauses
              .sort((a, b) =>
                SEVERITY_ORDER[b.severity as Severity] -
                SEVERITY_ORDER[a.severity as Severity]
              )
              .map((mc) => <MissingClauseRow key={mc.rule_id} mc={mc} />)
          )}
        </div>
      )}

      {/* ── Disclaimer ───────────────────────────────────── */}
      <p
        className="text-xs font-mono mt-10 pt-5"
        style={{ color: "#A8A49D", borderTop: "1px solid #E4E3DC" }}
      >
        This audit is AI-assisted and does not constitute legal advice. ·
        Clearfolio Review v2 · Local-only processing
      </p>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function StatPill({
  label, count, severity, active, onClick
}: {
  label:    string;
  count:    number;
  severity: Severity;
  active:   boolean;
  onClick:  () => void;
}) {
  const colour = riskColour(severity);
  return (
    <button
      onClick={onClick}
      className="rounded-lg border px-3 py-2.5 text-left transition-all duration-150"
      style={{
        borderColor:     active ? colour : "#E4E3DC",
        backgroundColor: active ? riskBg(severity) : "transparent",
        cursor:          "pointer",
      }}
    >
      <p
        className="font-mono font-600 text-lg leading-none"
        style={{ color: active ? colour : "#1A1917" }}
      >
        {count}
      </p>
      <p
        className="text-xs mt-0.5"
        style={{ color: active ? colour : "#6B6963", opacity: active ? 0.8 : 1 }}
      >
        {label}
      </p>
    </button>
  );
}

function TabBtn({
  label, count, active, onClick
}: {
  label:   string;
  count:   number | null;
  active:  boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="font-heading text-sm font-500 px-3.5 py-1.5 rounded-md transition-all duration-150"
      style={{
        backgroundColor: active ? "#FFFFFF" : "transparent",
        color:           active ? "#1A1917" : "#6B6963",
        boxShadow:       active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
        cursor:          "pointer",
        whiteSpace:      "nowrap",
      }}
    >
      {label}
      {count !== null && count > 0 && (
        <span
          className="ml-1.5 font-mono text-xs"
          style={{ color: active ? "#1A1917" : "#A8A49D" }}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function FilterBar({
  filter,
  onChange,
}: {
  filter:   Filter;
  onChange: (f: Filter) => void;
}) {
  const filters: Filter[] = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];
  return (
    <div className="flex gap-2 flex-wrap">
      {filters.map((f) => (
        <button
          key={f}
          onClick={() => onChange(f)}
          className="font-mono text-xs px-2.5 py-1 rounded-full border transition-all duration-150"
          style={{
            borderColor:     filter === f ? "#1A1917" : "#E4E3DC",
            backgroundColor: filter === f ? "#1A1917" : "transparent",
            color:           filter === f ? "#FAFAF7" : "#6B6963",
            cursor:          "pointer",
          }}
        >
          {f}
        </button>
      ))}
    </div>
  );
}

function MissingTag({ mc }: { mc: MissingClause }) {
  const colour = riskColour(mc.severity);
  return (
    <span
      className="inline-flex items-center gap-1 font-mono text-xs px-2.5 py-1 rounded-full border"
      style={{
        color:           colour,
        borderColor:     `${colour}44`,
        backgroundColor: `${colour}0D`,
      }}
    >
      <span>✗</span>
      {mc.title}
    </span>
  );
}

function MissingClauseRow({ mc }: { mc: MissingClause }) {
  const colour = riskColour(mc.severity);
  const bg     = riskBg(mc.severity);
  return (
    <div
      className="flex items-center gap-3 rounded-lg border px-4 py-3"
      style={{ borderColor: `${colour}28`, backgroundColor: bg }}
    >
      <span
        className="font-mono text-base"
        style={{ color: colour }}
      >
        ✗
      </span>
      <div className="flex-1">
        <span
          className="font-heading text-sm font-600"
          style={{ color: "#1A1917" }}
        >
          {mc.title}
        </span>
        <span
          className="ml-2 font-mono text-xs"
          style={{ color: "#A8A49D" }}
        >
          {mc.rule_id}
        </span>
      </div>
      <span
        className="font-mono text-xs px-2 py-0.5 rounded-full"
        style={{
          color:           colour,
          backgroundColor: `${colour}18`,
        }}
      >
        {mc.severity}
      </span>
    </div>
  );
}

function ModelSummaryPanel({ summary }: { summary: AuditReport["model_summary"] }) {
  const byPass: Record<number, typeof summary> = {};
  summary.forEach((m) => {
    (byPass[m.pass] = byPass[m.pass] ?? []).push(m);
  });

  return (
    <div
      className="rounded-lg border px-4 py-4"
      style={{ borderColor: "#E4E3DC" }}
    >
      <p
        className="font-mono text-xs uppercase tracking-widest mb-3"
        style={{ color: "#A8A49D" }}
      >
        Model Performance
      </p>
      {Object.entries(byPass).map(([pass, models]) => (
        <div key={pass} className="mb-3 last:mb-0">
          <p
            className="font-mono text-xs mb-1.5"
            style={{ color: "#A8A49D" }}
          >
            Pass {pass}
          </p>
          <div className="space-y-1.5">
            {models.map((m, i) => (
              <div key={i} className="flex items-center gap-3">
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    backgroundColor: m.error ? "#C8392B" : "#2E7D32",
                  }}
                />
                <span
                  className="font-mono text-xs w-32 truncate"
                  style={{ color: "#1A1917" }}
                >
                  {m.model}
                </span>
                <span
                  className="text-xs capitalize"
                  style={{ color: "#6B6963" }}
                >
                  {m.role}
                </span>
                <span
                  className="ml-auto font-mono text-xs"
                  style={{ color: "#A8A49D" }}
                >
                  {m.findings} findings · {m.elapsed_sec}s
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PrivacyBanner() {
  return (
    <div
      className="rounded-lg flex items-center gap-3 px-4 py-2.5 mb-6"
      style={{ backgroundColor: "#F4F3EE", border: "1px solid #E4E3DC" }}
    >
      <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="#3A7D44">
        <rect x="2" y="6" width="9" height="6" rx="1" strokeWidth="1.2" />
        <path d="M4.5 6V4.5a2 2 0 0 1 4 0V6" strokeWidth="1.2" strokeLinecap="round" />
      </svg>
      <p className="text-xs font-mono" style={{ color: "#6B6963" }}>
        No data leaves your system · All analysis ran locally
      </p>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div
      className="rounded-lg border px-4 py-6 text-center"
      style={{ borderColor: "#E4E3DC" }}
    >
      <p className="text-sm" style={{ color: "#6B6963" }}>{message}</p>
    </div>
  );
}

function ErrorPanel({ error, onReset }: { error: string; onReset: () => void }) {
  return (
    <div className="animate-[fadeIn_0.4s_ease_forwards]">
      <div
        className="rounded-xl border p-6"
        style={{ borderColor: "#C8392B44", backgroundColor: "#FDF0EE" }}
      >
        <p
          className="font-heading font-600 text-base mb-2"
          style={{ color: "#C8392B" }}
        >
          Audit failed
        </p>
        <pre
          className="font-mono text-xs whitespace-pre-wrap leading-relaxed mb-4"
          style={{ color: "#6B6963" }}
        >
          {error}
        </pre>
        <button
          onClick={onReset}
          className="font-mono text-xs px-3 py-1.5 rounded-lg border"
          style={{ color: "#C8392B", borderColor: "#C8392B44" }}
        >
          ← Try again
        </button>
      </div>
    </div>
  );
}
