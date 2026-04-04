"use client";

import { useState } from "react";
import { AuditMode, AuditReport, AppState } from "@/types/audit";
import UploadZone      from "@/components/UploadZone";
import ProcessingState from "@/components/ProcessingState";
import AuditReportView from "@/components/AuditReport";

interface PendingUpload {
  name: string;
  mode: AuditMode;
}

export default function HomePage() {
  const [appState, setAppState]   = useState<AppState>("idle");
  const [pending,  setPending]    = useState<PendingUpload | null>(null);
  const [report,   setReport]     = useState<AuditReport | null>(null);
  const [apiError, setApiError]   = useState<string | null>(null);

  // ── Handle file upload submission ──────────────────────────
  const handleUpload = async (file: File, mode: AuditMode) => {
    setPending({ name: file.name, mode });
    setAppState("processing");
    setApiError(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("mode", mode);

    try {
      const res  = await fetch("/api/audit", { method: "POST", body: formData });
      const data = await res.json() as AuditReport & { error?: string };

      if (!res.ok || (data.error && !data.rule_findings?.length)) {
        setApiError(data.error ?? "Unknown error from audit API.");
        setAppState("error");
        return;
      }

      setReport(data);
      setAppState("done");
    } catch (err) {
      setApiError(err instanceof Error ? err.message : "Network error.");
      setAppState("error");
    }
  };

  const handleReset = () => {
    setAppState("idle");
    setReport(null);
    setPending(null);
    setApiError(null);
  };

  return (
    <div
      className="min-h-screen relative z-10"
      style={{ backgroundColor: "transparent" }}
    >
      {/* ── Page header ──────────────────────────────────── */}
      <header
        className="sticky top-0 z-20 px-6 py-4 flex items-center justify-between"
        style={{
          backgroundColor: "rgba(250,250,247,0.92)",
          backdropFilter:  "blur(8px)",
          borderBottom:    "1px solid #E4E3DC",
        }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-sm"
            style={{ backgroundColor: "#1A1917" }}
          >
            <span style={{ color: "#FAFAF7", fontSize: "14px" }}>⚖</span>
          </div>
          <span
            className="font-heading font-600 text-base tracking-tight"
            style={{ color: "#1A1917" }}
          >
            Clearfolio Review
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span
            className="font-mono text-xs px-2 py-0.5 rounded-full border"
            style={{ color: "#3A7D44", borderColor: "#3A7D4444", backgroundColor: "#EEF7EF" }}
          >
            v2 · local
          </span>
          {appState === "done" && (
            <button
              onClick={handleReset}
              className="font-mono text-xs"
              style={{ color: "#6B6963" }}
            >
              New audit
            </button>
          )}
        </div>
      </header>

      {/* ── Main content ─────────────────────────────────── */}
      <main className="px-4 py-12 sm:py-16">
        <div className="max-w-2xl mx-auto">

          {/* ── Idle: upload screen ───────────────────────── */}
          {appState === "idle" && (
            <div className="animate-[fadeIn_0.4s_ease_forwards]">
              {/* Hero text */}
              <div className="mb-10">
                <p
                  className="font-mono text-xs uppercase tracking-widest mb-3"
                  style={{ color: "#A8A49D" }}
                >
                  Contract Audit System
                </p>
                <h1
                  className="font-heading font-700 leading-tight mb-3"
                  style={{ fontSize: "clamp(1.75rem, 4vw, 2.5rem)", color: "#1A1917" }}
                >
                  Review any contract in seconds.
                </h1>
                <p
                  className="text-base leading-relaxed"
                  style={{
                    color:      "#6B6963",
                    maxWidth:   "480px",
                    lineHeight: "1.65",
                  }}
                >
                  AI-powered clause analysis, risk detection, and compliance review.{" "}
                  <span style={{ color: "#1A1917" }}>Everything runs locally</span> —
                  your documents never leave your machine.
                </p>
              </div>

              {/* Feature chips */}
              <div className="flex flex-wrap gap-2 mb-10">
                {[
                  "30 rule checks",
                  "Multi-model AI",
                  "Judge consensus",
                  "No cloud",
                  "Instant report",
                ].map((chip) => (
                  <span
                    key={chip}
                    className="font-mono text-xs px-2.5 py-1 rounded-full border"
                    style={{ color: "#6B6963", borderColor: "#E4E3DC" }}
                  >
                    {chip}
                  </span>
                ))}
              </div>

              {/* Upload zone */}
              <UploadZone onUpload={handleUpload} />
            </div>
          )}

          {/* ── Processing ────────────────────────────────── */}
          {appState === "processing" && pending && (
            <ProcessingState filename={pending.name} mode={pending.mode} />
          )}

          {/* ── Error (API / Python errors) ───────────────── */}
          {appState === "error" && (
            <div className="animate-[fadeIn_0.4s_ease_forwards]">
              <div
                className="rounded-xl border p-6 mb-6"
                style={{ borderColor: "#C8392B44", backgroundColor: "#FDF0EE" }}
              >
                <p
                  className="font-heading font-600 mb-2"
                  style={{ color: "#C8392B" }}
                >
                  Audit failed
                </p>
                <p
                  className="text-sm leading-relaxed font-mono mb-4"
                  style={{ color: "#6B6963" }}
                >
                  {apiError}
                </p>
                <div
                  className="text-xs font-mono p-3 rounded-lg mb-4"
                  style={{ backgroundColor: "#FAFAF7", color: "#6B6963", border: "1px solid #E4E3DC" }}
                >
                  <p className="font-600 mb-1" style={{ color: "#1A1917" }}>Checklist:</p>
                  <p>1. Ollama is running: <code>ollama serve</code></p>
                  <p>2. A model is pulled: <code>ollama pull llama3</code></p>
                  <p>3. clearfolio_review_v2.py is in the scripts path</p>
                  <p>4. CLEARFOLIO_SCRIPTS_PATH is set in .env.local</p>
                </div>
                <button
                  onClick={handleReset}
                  className="font-mono text-xs px-4 py-2 rounded-lg border transition-colors"
                  style={{ color: "#1A1917", borderColor: "#1A1917" }}
                >
                  ← Try again
                </button>
              </div>
            </div>
          )}

          {/* ── Done: report ──────────────────────────────── */}
          {appState === "done" && report && (
            <AuditReportView report={report} onReset={handleReset} />
          )}

        </div>
      </main>

      {/* ── Footer ───────────────────────────────────────── */}
      {appState === "idle" && (
        <footer
          className="mt-8 px-6 py-4 text-center"
          style={{ borderTop: "1px solid #E4E3DC" }}
        >
          <p
            className="font-mono text-xs"
            style={{ color: "#A8A49D" }}
          >
            Clearfolio Review · Privacy-first AI contract audit ·{" "}
            <span style={{ color: "#3A7D44" }}>No data leaves your system</span>
          </p>
        </footer>
      )}
    </div>
  );
}
