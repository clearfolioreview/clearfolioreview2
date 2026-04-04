# Clearfolio Review — Frontend (Part 3)

Privacy-first AI contract audit UI built with Next.js 14, TypeScript, and Tailwind CSS.

## Prerequisites

- Node.js 18+
- Python 3.10+ with `python-docx` and `requests` installed
- [Ollama](https://ollama.ai) running locally with at least one model pulled
- `clearfolio_review_v2.py` from Part 2

## Directory layout

```
your-workspace/
├── clearfolio_review_v2.py     ← Part 2 Python engine
├── audit_bridge.py             ← JSON bridge (included here)
└── clearfolio-frontend/        ← this project
    ├── src/
    │   ├── app/
    │   │   ├── page.tsx
    │   │   ├── layout.tsx
    │   │   ├── globals.css
    │   │   └── api/audit/route.ts
    │   ├── components/
    │   │   ├── UploadZone.tsx
    │   │   ├── AuditReport.tsx
    │   │   ├── ScoreBadge.tsx
    │   │   ├── FindingCard.tsx
    │   │   └── ProcessingState.tsx
    │   └── types/audit.ts
    └── audit_bridge.py         ← copy of bridge (for same-dir convenience)
```

## Setup

```bash
# 1. Install frontend deps
cd clearfolio-frontend
npm install

# 2. Copy environment file
cp .env.example .env.local

# 3. Edit .env.local — set path to your Python scripts
#    CLEARFOLIO_SCRIPTS_PATH=..   (default: parent directory)
#    PYTHON_BIN=python3

# 4. Ensure Ollama is running and models are available
ollama serve &
ollama pull llama3         # quick mode
ollama pull mistral        # deep mode — compliance model
ollama pull phi3           # deep mode — completeness model
# Optional: ollama pull deepseek-r1   # judge model

# 5. Install Python dependencies
pip install python-docx requests

# 6. Run the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Usage

1. Drop a `.docx` contract file onto the upload area (or click to browse)
2. Select **Quick** (fast, single model) or **Deep** (3 models + judge)
3. Click **Run Audit**
4. View the structured report: score, grade, findings, missing clauses

## Audit modes

| Mode  | Models            | Duration       | Best for            |
|-------|-------------------|----------------|---------------------|
| Quick | 1 (risk-focused)  | ~20–60s        | Fast first pass     |
| Deep  | 3 + judge         | ~2–5 min       | Thorough review     |

## Environment variables

| Variable                  | Default    | Description                          |
|---------------------------|------------|--------------------------------------|
| `CLEARFOLIO_SCRIPTS_PATH` | `../`      | Dir containing `audit_bridge.py`     |
| `PYTHON_BIN`              | `python3`  | Python executable                    |
| `DEFAULT_AUDIT_MODE`      | `quick`    | Default mode (unused — UI sets this) |

## Privacy

- All files are written to `/tmp/clearfolio/` and deleted immediately after audit
- No external API calls are made at any point
- Ollama runs entirely locally — no model telemetry leaves your machine
