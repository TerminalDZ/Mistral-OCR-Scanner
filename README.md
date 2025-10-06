# Mistral OCR Scanner

Local-first OCR + Document QnA web app powered by Mistral (OCR + chat), FastAPI backend, and a simple modern frontend.

---

## Table of contents

- [What it is](#what-it-is)
- [Key features](#key-features)
- [Architecture & files](#architecture--files)
- [Prerequisites](#prerequisites)
- [Quickstart (local)](#quickstart-local)
- [Configuration / .env](#configuration--env)
- [API reference (useful endpoints)](#api-reference-useful-endpoints)
- [Frontend usage (browser)](#frontend-usage-browser)
- [Examples (curl / PowerShell)](#examples-curl--powershell)
- [Troubleshooting (common issues & fixes)](#troubleshooting-common-issues--fixes)
- [Production notes & hardening](#production-notes--hardening)
- [Project structure](#project-structure)
- [License & contribution](#license--contribution)

---

## What it is

A developer-friendly, user-facing application that:

- uploads PDF / image documents,
- runs OCR (using **mistral-ocr-latest**),
- optionally runs document QnA / summary using **mistral-small-latest**,
- extracts a clean Markdown representation and a short `title` for the document,
- saves everything locally (`data/uploads`, `data/results`, SQLite `jobs.db`),
- provides a modern single-file frontend (Tailwind + Dropzone + PDF.js + marked) that shows Markdown, allows asking questions, and downloads `.md` or `.docx`.

No message queue, no Redis, no Celery. The backend processes files through a thread pool.

---

## Key features

- Clean Markdown output from OCR (rendered in the UI).
- Title automatically generated after OCR (via model or heuristics).
- Document QnA (post-upload or on demand). QnA results are stored with the job.
- Download result as `.md` or `.docx`.
- Local-first storage + SQLite job registry (`data/jobs.db`).
- Simple, modern frontend: Dropzone for uploads, PDF preview, Markdown rendering.
- Simple APIs for automation/integration.

---

## Architecture & files

Important files / folders you’ll interact with:

```
/app
  ├─ main.py           # FastAPI app + endpoints + startup/shutdown
  ├─ tasks.py          # processing pipeline: upload -> OCR -> title -> optional QnA
  ├─ utils.py          # storage, DB helpers, migrations
  ├─ mistral_client.py # wraps Mistral client (expects MISTRAL_API_KEY)
frontend/
  ├─ index.html
  ├─ main.js           # frontend logic (Dropzone, polling, rendering)
data/
  ├─ uploads/          # saved uploaded files
  ├─ results/          # job results (job_id.json)
  └─ jobs.db           # sqlite jobs table
requirements.txt
```

---

## Prerequisites

- Python 3.10+ (3.12 tested in dev).
- pip (and virtualenv recommended).
- A Mistral API key with files/ocr and chat access.
- Optional: a modern browser.

Recommended packages are in `requirements.txt` (FastAPI, uvicorn, python-mistralai, python-docx, python-dotenv, aiofiles).

---

## Quickstart (local)

1. Clone the repo:

```bash
git clone https://github.com/TerminalDZ/Mistral-OCR-Scanner
cd Mistral-OCR-Scanner
```

2. Create venv and install:

```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

3. Create `.env` at the project root (example below) with your Mistral key.

4. Run the server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> Tip: on Windows you can use `--reload` for development but the app uses `startup/shutdown` handlers to make reload stable. If you see weird multiprocessing errors, run without `--reload`.

5. Open the UI: `http://localhost:8000/`

---

## Configuration / .env

Create `.env` (project root) with at least:

```
MISTRAL_API_KEY=sk-...
STORAGE_PATH=./data         # optional, defaults to ./data
MAX_WORKERS=3               # thread pool size for processing
DOC_QNA_MODEL=mistral-small-latest   # used for title & QnA
```

Do NOT commit `.env` to git. Treat `MISTRAL_API_KEY` as secret.

---

## API reference (useful endpoints)

Use these endpoints for automation or testing.

- `GET /`
  Serves frontend `index.html`.

- `POST /api/upload`
  Upload a file. Form multipart: `file` (UploadFile). Optional query/form fields:

  - `do_annotations` (bool)
  - `do_qna` (bool)
  - `annotation_schema` (JSON string)

  Response:

  ```json
  { "job_id": "<id>" }
  ```

- `GET /api/status/{job_id}`
  Returns job status, `result_url` if available.

- `GET /api/result/{job_id}`
  Returns the full JSON result file (for debugging / raw export).

- `GET /api/jobs`
  List recent jobs (reads SQLite).

- `POST /api/qna`
  Body JSON: `{ "job_id":"<id>", "question":"..." }`
  Triggers QnA using stored/signed document URL (uploads original if no document_url stored). Returns `{ "answer": <model response> }`. QnA result is appended to job result JSON.

- `GET /api/download/{job_id}?format=md|docx`
  Download the final document (Markdown or generated Word `.docx`). The endpoint prefers OCR-generated `full_markdown`, else falls back to `qna_summary` + title.

---

## Frontend usage (browser)

1. Open UI at `http://localhost:8000/`.
2. Drag & drop PDF or image to upload area (Dropzone).
3. Optionally check **Run initial summary (QnA)** to ask the model for a summary during processing.
4. After processing:

   - The job appears in **History** with a generated `title`.
   - Click **View** to render the Markdown.
   - Use **Ask** to run additional QnA on the document; the answer will appear rendered as Markdown.
   - Use **Download .md** or **Download .docx** to save results.

The frontend renders Markdown (using `marked`). QnA answers are displayed as Markdown blocks — headings, lists, etc. — as produced by the model.

---

## Examples (curl & PowerShell)

### Curl (Linux/macOS or Windows curl.exe)

Upload:

```bash
curl -v -X POST "http://localhost:8000/api/upload" \
  -F "file=@/path/to/file.pdf" \
  -F "do_qna=false"
```

QnA (ask):

```bash
curl -X POST "http://localhost:8000/api/qna" \
  -H "Content-Type: application/json" \
  -d '{"job_id":"<job_id_here>", "question":"What is this document about?" }'
```

Download Markdown:

```bash
curl -L "http://localhost:8000/api/download/<job_id>?format=md" -o result.md
```

### Windows PowerShell (working approach)

If `curl` alias points to Invoke-WebRequest (older PS), use the system curl:

```powershell
& 'C:\Windows\System32\curl.exe' -v -X POST "http://localhost:8000/api/upload" -F "file=@C:\path\to\file.pdf"
```

If you prefer PowerShell native, use `Invoke-RestMethod` with multipart form data helper script or use `System.Net.Http.HttpClient` snippet. (In practice, using `curl.exe` is simplest.)

---

## File structure (example)

```
.
├─ app/
│  ├─ main.py
│  ├─ tasks.py
│  ├─ utils.py
│  └─ mistral_client.py
├─ frontend/
│  ├─ index.html
│  └─ main.js
├─ data/
│  ├─ uploads/
│  ├─ results/
│  └─ jobs.db
├─ requirements.txt
├─ README.md   <-- you are here
└─ .env
```

---

## Contribution

- Contributions: open issues / PRs. Keep changes focused, add tests for any backend change, and document architecture changes in README.


