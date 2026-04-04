"use client";

import { useEffect, useState } from "react";
import { AuditMode } from "@/types/audit";

const QUICK_STEPS = [
  "Loading document…",
  "Parsing clauses…",
  "Running rule engine…",
  "Running AI analysis…",
  "Generating report…",
];

const DEEP_STEPS = [
  "Loading document…",
  "Parsing clauses…",
  "Running rule engine (30 checks)…",
  "Pass 1 — risk specialist analysing…",
  "Pass 1 — compliance specialist analysing…",
  "Pass 1 — completeness specialist analysing…",
  "Pass 2 — deep re-analysis on high-risk clauses…",
  "Judge model synthesising findings…",
  "Generating report…",
];

interface ProcessingStateProps {
  filename: string;
  mode:     AuditMode;
}

export default function ProcessingState({ filename, mode }: ProcessingStateProps) {
  const steps      = mode === "deep" ? DEEP_STEPS : QUICK_STEPS;
  const [step, setStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStep((s) => (s < steps.length - 1 ? s + 1 : s));
    }, mode === "deep" ? 4200 : 2600);
    return () => clearInterval(interval);
  }, [mode, steps.length]);

  return (
    <div className="animate-[fadeIn_0.4s_ease_forwards]">
      {/* Header */}
      <div className="mb-10">
        <p
          className="font-mono text-xs uppercase tracking-widest mb-2"
          style={{ color: "#A8A49D" }}
        >
          Processing audit
        </p>
        <h2
          className="font-heading text-2xl font-600 mb-1"
          style={{ color: "#1A1917" }}
        >
          {filename}
        </h2>
        <p style={{ color: "#6B6963", fontSize: "0.875rem" }}>
          {mode === "deep"
            ? "Deep mode — three specialist models running in parallel"
            : "Quick mode — single-pass analysis"}
        </p>
      </div>

      {/* Spinner + current step */}
      <div className="flex items-center gap-4 mb-10">
        <SpinnerRing />
        <div>
          <p
            className="font-mono text-sm transition-all duration-300"
            style={{ color: "#1A1917" }}
          >
            {steps[step]}
          </p>
          <p
            className="text-xs mt-0.5"
            style={{ color: "#A8A49D" }}
          >
            Step {step + 1} of {steps.length}
          </p>
        </div>
      </div>

      {/* Progress dots */}
      <div className="flex items-center gap-1.5 mb-12">
        {steps.map((_, i) => (
          <div
            key={i}
            className="rounded-full transition-all duration-500"
            style={{
              width:           i === step ? "20px" : "6px",
              height:          "6px",
              backgroundColor: i <= step ? "#1A1917" : "#E4E3DC",
            }}
          />
        ))}
      </div>

      {/* Skeleton cards */}
      <div className="space-y-3">
        {[84, 64, 96, 72].map((w, i) => (
          <div
            key={i}
            className="rounded-lg border overflow-hidden"
            style={{
              borderColor:    "#E4E3DC",
              opacity:        1 - i * 0.15,
              animationDelay: `${i * 0.1}s`,
            }}
          >
            <div className="flex">
              <div
                className="w-1 shrink-0 shimmer"
                style={{ height: "72px" }}
              />
              <div className="flex-1 px-4 py-3.5 space-y-2">
                <div
                  className="shimmer rounded"
                  style={{ width: `${w}%`, height: "14px" }}
                />
                <div
                  className="shimmer rounded"
                  style={{ width: "55%", height: "11px" }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Privacy note */}
      <div
        className="mt-10 flex items-center gap-2 text-xs font-mono"
        style={{ color: "#A8A49D" }}
      >
        <LockIcon />
        <span>No data leaves your system — all processing is local</span>
      </div>
    </div>
  );
}

function SpinnerRing() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      style={{ animation: "spin-slow 1s linear infinite" }}
    >
      <circle
        cx="14" cy="14" r="11"
        stroke="#E4E3DC"
        strokeWidth="2.5"
      />
      <path
        d="M 14 3 A 11 11 0 0 1 25 14"
        stroke="#1A1917"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <rect x="2" y="5.5" width="8" height="5.5" rx="1"
        stroke="currentColor" strokeWidth="1.2" />
      <path d="M4 5.5V4a2 2 0 1 1 4 0v1.5"
        stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}
