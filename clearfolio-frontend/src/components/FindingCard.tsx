"use client";

import { RuleFinding, AIFinding, riskColour, riskBg } from "@/types/audit";

// ── Rule Engine Finding Card ──────────────────────────────────────────────
interface RuleCardProps {
  finding: RuleFinding;
}

export function RuleCard({ finding }: RuleCardProps) {
  const colour = riskColour(finding.severity);
  const bg     = riskBg(finding.severity);

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: `${colour}28`, backgroundColor: bg }}
    >
      {/* Left accent bar + content */}
      <div className="flex">
        <div
          className="w-1 shrink-0 rounded-l-lg"
          style={{ backgroundColor: colour }}
        />
        <div className="flex-1 px-4 py-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              {/* Title row */}
              <div className="flex items-center gap-2 flex-wrap">
                <SeverityPill severity={finding.severity} />
                <span
                  className="font-mono text-xs"
                  style={{ color: colour, opacity: 0.65 }}
                >
                  {finding.rule_id}
                </span>
                <span
                  className="font-heading text-sm font-600"
                  style={{ color: "#1A1917" }}
                >
                  {finding.title}
                </span>
              </div>

              {/* Detail */}
              <p
                className="mt-1.5 text-sm leading-relaxed"
                style={{ color: "#6B6963" }}
              >
                {finding.detail}
              </p>
            </div>

            {/* Category badge */}
            <span
              className="shrink-0 text-xs font-mono px-2 py-0.5 rounded-full border"
              style={{
                color:           colour,
                borderColor:     `${colour}44`,
                backgroundColor: `${colour}0D`,
              }}
            >
              {finding.category}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── AI / Judge Finding Card ───────────────────────────────────────────────
interface AICardProps {
  finding: AIFinding;
  deepMode?: boolean;
}

export function AICard({ finding, deepMode = false }: AICardProps) {
  const colour = riskColour(finding.risk);
  const bg     = riskBg(finding.risk);

  const confColour =
    finding.confidence >= 80 ? "#2E7D32" :
    finding.confidence >= 60 ? "#92680A" : "#C8392B";

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{ borderColor: `${colour}28`, backgroundColor: bg }}
    >
      <div className="flex">
        <div
          className="w-1 shrink-0 rounded-l-lg"
          style={{ backgroundColor: colour }}
        />
        <div className="flex-1 px-4 py-3.5">
          {/* Top row: clause label + risk + confidence */}
          <div className="flex items-center justify-between gap-3 mb-2">
            <div className="flex items-center gap-2 flex-wrap">
              <SeverityPill severity={finding.risk} />
              <span
                className="font-heading text-sm font-600"
                style={{ color: "#1A1917" }}
              >
                {finding.clause_label}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {deepMode && finding.judge_validated && (
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded-full border"
                  style={{
                    color:           "#2E7D32",
                    borderColor:     "#2E7D3244",
                    backgroundColor: "#2E7D320D",
                  }}
                >
                  ✓ validated
                </span>
              )}
              <span
                className="font-mono text-xs"
                style={{ color: confColour }}
              >
                {finding.confidence}%
              </span>
            </div>
          </div>

          {/* Issue + Suggestion */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <FieldBlock
              label="Issue"
              value={finding.issue}
              colour="#1A1917"
            />
            <FieldBlock
              label="Suggestion"
              value={finding.suggestion}
              colour="#2E7D32"
              icon="→"
            />
          </div>

          {/* Deep mode: source models + judge note */}
          {deepMode && (
            <div
              className="mt-2.5 flex items-center gap-3 text-xs font-mono flex-wrap"
              style={{ color: "#A8A49D" }}
            >
              {finding.source_models.length > 0 && (
                <span>
                  via{" "}
                  {finding.source_models.map((m, i) => (
                    <span
                      key={i}
                      className="inline-block px-1.5 py-0.5 rounded mr-1"
                      style={{ background: "#E4E3DC", color: "#6B6963" }}
                    >
                      {m}
                    </span>
                  ))}
                </span>
              )}
              {finding.judge_note && (
                <span style={{ color: "#A8A49D" }}>
                  judge: {finding.judge_note}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────
function SeverityPill({ severity }: { severity: string }) {
  const colour = riskColour(severity as never);
  return (
    <span
      className="inline-flex items-center font-mono text-xs font-500 px-2 py-0.5 rounded-full"
      style={{
        color:           colour,
        backgroundColor: `${colour}18`,
      }}
    >
      {severity}
    </span>
  );
}

function FieldBlock({
  label,
  value,
  colour,
  icon,
}: {
  label:  string;
  value:  string;
  colour: string;
  icon?:  string;
}) {
  return (
    <div>
      <p
        className="text-xs font-mono uppercase tracking-wider mb-0.5"
        style={{ color: "#A8A49D" }}
      >
        {label}
      </p>
      <p className="text-sm" style={{ color: colour }}>
        {icon && <span className="mr-1">{icon}</span>}
        {value}
      </p>
    </div>
  );
}
