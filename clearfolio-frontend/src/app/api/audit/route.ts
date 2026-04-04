import { NextRequest, NextResponse } from "next/server";
import { spawn }  from "child_process";
import { writeFile, unlink, mkdir } from "fs/promises";
import { existsSync } from "fs";
import path  from "path";
import os    from "os";

// ── Config ────────────────────────────────────────────────────────────────
const PYTHON_BIN     = process.env.PYTHON_BIN     ?? "python3";
const SCRIPTS_PATH   = process.env.CLEARFOLIO_SCRIPTS_PATH
                     ?? path.join(process.cwd(), "..");
const BRIDGE_SCRIPT  = path.join(SCRIPTS_PATH, "audit_bridge.py");
const EXEC_TIMEOUT   = 300_000; // 5 min max (deep mode is slow)

// ─────────────────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  let tempPath: string | null = null;

  try {
    // ── 1. Parse multipart form data ──────────────────────────
    const formData = await req.formData();
    const file     = formData.get("file") as File | null;
    const mode     = (formData.get("mode") as string) ?? "quick";

    if (!file) {
      return NextResponse.json(
        { error: "No file provided." },
        { status: 400 }
      );
    }

    if (!file.name.toLowerCase().endsWith(".docx")) {
      return NextResponse.json(
        { error: "Only .docx files are supported. Scanned or image-based PDFs cannot be processed." },
        { status: 400 }
      );
    }

    if (file.size > 25 * 1024 * 1024) {
      return NextResponse.json(
        { error: "File exceeds the 25 MB limit." },
        { status: 400 }
      );
    }

    // ── 2. Write to temp file ─────────────────────────────────
    const tmpDir = path.join(os.tmpdir(), "clearfolio");
    if (!existsSync(tmpDir)) {
      await mkdir(tmpDir, { recursive: true });
    }

    const safeName = `audit_${Date.now()}_${Math.random().toString(36).slice(2)}.docx`;
    tempPath       = path.join(tmpDir, safeName);

    const buffer   = Buffer.from(await file.arrayBuffer());
    await writeFile(tempPath, buffer);

    // ── 3. Run Python bridge ──────────────────────────────────
    const jsonOutput = await runBridge(tempPath, mode);

    // ── 4. Parse and return ───────────────────────────────────
    let result: Record<string, unknown>;
    try {
      result = JSON.parse(jsonOutput);
    } catch {
      return NextResponse.json(
        { error: `Bridge returned non-JSON output:\n${jsonOutput.slice(0, 500)}` },
        { status: 500 }
      );
    }

    return NextResponse.json(result);

  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });

  } finally {
    // ── 5. Always clean up temp file ─────────────────────────
    if (tempPath) {
      try { await unlink(tempPath); } catch { /* ignore */ }
    }
  }
}

// ── Spawn the Python bridge and capture stdout ─────────────────────────────
function runBridge(filePath: string, mode: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const args   = [BRIDGE_SCRIPT, filePath, "--mode", mode];
    const proc   = spawn(PYTHON_BIN, args, {
      env: { ...process.env, CLEARFOLIO_PATH: SCRIPTS_PATH },
    });

    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];

    proc.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    proc.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));

    const timer = setTimeout(() => {
      proc.kill("SIGTERM");
      reject(new Error("Audit timed out after 5 minutes."));
    }, EXEC_TIMEOUT);

    proc.on("close", (code) => {
      clearTimeout(timer);
      const out = Buffer.concat(stdout).toString("utf8").trim();
      const err = Buffer.concat(stderr).toString("utf8").trim();

      if (code !== 0 && !out) {
        reject(new Error(err || `Python bridge exited with code ${code}`));
      } else {
        // Bridge always prints JSON on last stdout line
        const lines = out.split("\n").filter(Boolean);
        const last  = lines[lines.length - 1] ?? "{}";
        resolve(last);
      }
    });

    proc.on("error", (err) => {
      clearTimeout(timer);
      reject(new Error(
        err.message.includes("ENOENT")
          ? `Python not found at "${PYTHON_BIN}". Set PYTHON_BIN in .env.local.`
          : err.message
      ));
    });
  });
}
