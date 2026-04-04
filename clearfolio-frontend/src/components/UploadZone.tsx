"use client";

import { useCallback, useRef, useState } from "react";
import { AuditMode, formatFileSize } from "@/types/audit";

interface UploadZoneProps {
  onUpload: (file: File, mode: AuditMode) => void;
  disabled?: boolean;
}

export default function UploadZone({ onUpload, disabled = false }: UploadZoneProps) {
  const inputRef    = useRef<HTMLInputElement>(null);
  const [dragging,  setDragging]  = useState(false);
  const [selected,  setSelected]  = useState<File | null>(null);
  const [mode,      setMode]      = useState<AuditMode>("quick");
  const [error,     setError]     = useState<string | null>(null);

  // ── File validation ─────────────────────────────────────────
  const validate = (file: File): string | null => {
    if (!file.name.toLowerCase().endsWith(".docx")) {
      return "Only .docx files are accepted. Supports digitally generated documents only.";
    }
    if (file.size > 25 * 1024 * 1024) {
      return "File must be under 25 MB.";
    }
    return null;
  };

  const handleFile = useCallback((file: File) => {
    const err = validate(file);
    if (err) {
      setError(err);
      setSelected(null);
      return;
    }
    setError(null);
    setSelected(file);
  }, []);

  // ── Drag events ─────────────────────────────────────────────
  const onDragOver  = (e: React.DragEvent) => { e.preventDefault(); setDragging(true); };
  const onDragLeave = ()                    => setDragging(false);
  const onDrop      = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const handleSubmit = () => {
    if (selected) onUpload(selected, mode);
  };

  return (
    <div className="space-y-6 animate-[fadeIn_0.4s_ease_forwards]">

      {/* Drop zone ─────────────────────────────────────────── */}
      <div
        className={`drop-zone rounded-xl cursor-pointer select-none ${dragging ? "drag-over" : ""}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        style={{
          padding:         "52px 32px",
          textAlign:       "center",
          backgroundColor: dragging ? "#F4F3EE" : "transparent",
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="hidden"
          onChange={onChange}
          disabled={disabled}
        />

        {selected ? (
          /* Selected file preview */
          <div className="space-y-2">
            <div
              className="inline-flex items-center justify-center w-12 h-12 rounded-lg mb-2"
              style={{ backgroundColor: "#E4E3DC" }}
            >
              <DocIcon />
            </div>
            <p
              className="font-heading font-600 text-base"
              style={{ color: "#1A1917" }}
            >
              {selected.name}
            </p>
            <p
              className="font-mono text-xs"
              style={{ color: "#A8A49D" }}
            >
              {formatFileSize(selected.size)} · Word Document
            </p>
            <p
              className="text-xs mt-1 underline underline-offset-2"
              style={{ color: "#A8A49D" }}
            >
              Click to change
            </p>
          </div>
        ) : (
          /* Placeholder */
          <div className="space-y-3">
            <div
              className="inline-flex items-center justify-center w-12 h-12 rounded-lg mx-auto mb-1"
              style={{ backgroundColor: "#F4F3EE", border: "1.5px solid #E4E3DC" }}
            >
              <UploadIcon />
            </div>
            <div>
              <p
                className="font-heading font-500 text-base"
                style={{ color: "#1A1917" }}
              >
                Drop your contract here
              </p>
              <p
                className="text-sm mt-1"
                style={{ color: "#6B6963" }}
              >
                or{" "}
                <span
                  className="underline underline-offset-2 cursor-pointer"
                  style={{ color: "#1A1917" }}
                >
                  browse files
                </span>
              </p>
            </div>
            <p
              className="font-mono text-xs"
              style={{ color: "#A8A49D" }}
            >
              .docx only · up to 25 MB
            </p>
          </div>
        )}
      </div>

      {/* Validation error ────────────────────────────────────── */}
      {error && (
        <div
          className="rounded-lg px-4 py-3 text-sm flex items-start gap-2.5"
          style={{
            backgroundColor: "#FDF0EE",
            border:          "1px solid #C8392B28",
            color:           "#C8392B",
          }}
        >
          <AlertIcon />
          <span className="leading-snug">{error}</span>
        </div>
      )}

      {/* Mode selector ────────────────────────────────────────── */}
      <div>
        <p
          className="font-mono text-xs uppercase tracking-widest mb-3"
          style={{ color: "#A8A49D" }}
        >
          Audit Mode
        </p>
        <div className="grid grid-cols-2 gap-3">
          {(["quick", "deep"] as AuditMode[]).map((m) => (
            <ModeCard
              key={m}
              value={m}
              selected={mode === m}
              onClick={() => setMode(m)}
            />
          ))}
        </div>
      </div>

      {/* Submit button ────────────────────────────────────────── */}
      <button
        onClick={handleSubmit}
        disabled={!selected || disabled}
        className="w-full font-heading font-600 text-sm rounded-lg py-3.5 transition-all duration-200"
        style={{
          backgroundColor: selected && !disabled ? "#1A1917" : "#E4E3DC",
          color:           selected && !disabled ? "#FAFAF7"  : "#A8A49D",
          cursor:          selected && !disabled ? "pointer"  : "not-allowed",
          letterSpacing:   "0.01em",
        }}
      >
        Run Audit →
      </button>

      {/* Footer messaging ─────────────────────────────────────── */}
      <div className="space-y-2 pt-1">
        <PrivacyLine icon={<LockIcon />} text="No data leaves your system" />
        <PrivacyLine icon={<DocCheckIcon />} text="Supports digitally generated documents only" />
      </div>
    </div>
  );
}

// ── Mode selection card ───────────────────────────────────────────────────
function ModeCard({
  value,
  selected,
  onClick,
}: {
  value:    AuditMode;
  selected: boolean;
  onClick:  () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="text-left rounded-lg px-4 py-3.5 border transition-all duration-150"
      style={{
        borderColor:     selected ? "#1A1917" : "#E4E3DC",
        backgroundColor: selected ? "#1A1917" : "transparent",
        cursor:          "pointer",
      }}
    >
      <p
        className="font-heading font-600 text-sm capitalize mb-0.5"
        style={{ color: selected ? "#FAFAF7" : "#1A1917" }}
      >
        {value}
      </p>
      <p
        className="text-xs leading-snug"
        style={{ color: selected ? "#A8A49D" : "#6B6963" }}
      >
        {value === "quick"
          ? "Single model · fast"
          : "3 models + judge · thorough"}
      </p>
    </button>
  );
}

// ── Privacy line ──────────────────────────────────────────────────────────
function PrivacyLine({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div
      className="flex items-center gap-2 text-xs"
      style={{ color: "#A8A49D" }}
    >
      {icon}
      <span>{text}</span>
    </div>
  );
}

// ── Icons ─────────────────────────────────────────────────────────────────
function UploadIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor"
      style={{ color: "#A8A49D" }}>
      <path d="M10 13V5M7 8l3-3 3 3" strokeWidth="1.5" strokeLinecap="round"
        strokeLinejoin="round" />
      <path d="M3 15a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2" strokeWidth="1.5"
        strokeLinecap="round" />
    </svg>
  );
}

function DocIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" stroke="#1A1917">
      <path d="M13 2H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"
        strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M13 2v5h5M8 13h6M8 9h4" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none" className="shrink-0 mt-0.5"
      stroke="currentColor">
      <circle cx="7.5" cy="7.5" r="6.5" strokeWidth="1.3" />
      <path d="M7.5 4.5v3.5M7.5 10.5v.5" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor">
      <rect x="2" y="5.5" width="8" height="5.5" rx="1" strokeWidth="1.2" />
      <path d="M4 5.5V4a2 2 0 1 1 4 0v1.5" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function DocCheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor">
      <path d="M7 1H3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4z"
        strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M7 1v3h3M4 7l1.5 1.5L8 6" strokeWidth="1.2" strokeLinecap="round"
        strokeLinejoin="round" />
    </svg>
  );
}
