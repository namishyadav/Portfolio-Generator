# AI-Assisted Resume Portfolio Generator

## 1. Project Title

AI-Assisted Resume Portfolio Generator

## 2. What the Application Does

A Python application that turns a plain-text resume (`.txt`) into a clean,
modern, responsive personal portfolio website (`portfolio.html`) with zero
manual HTML writing.

The application has two ways to run:

- **Command line** — `python main.py` reads `resume.txt`, sends it to Google's
  Gemini API, and writes `portfolio.html` directly to disk.
- **Local web app** — `python server.py` starts a small standard-library HTTP
  server at `http://localhost:8000/`. You upload a `.txt` CV in the browser,
  click **Generate Portfolio**, and the server runs the same pipeline and
  serves the result.

The entire pipeline runs locally: the only external service is the Gemini API,
which converts the resume text into structured JSON that Python validates,
normalizes, grounds against the source resume, and renders into HTML.

## 3. User Workflow

**Web app (recommended):**

1. Run `python server.py`.
2. Open <http://localhost:8000/> in your browser.
3. Drag-and-drop (or choose) a `.txt` CV. The selected filename is shown.
4. Click **Generate Portfolio** (enabled only after a valid `.txt` file is selected).
5. The loading state ("Analyzing your CV...") is shown while the server runs the pipeline.
6. On success, use **View Portfolio** (`/portfolio`) or **Download Portfolio** (`/download`).
7. On failure, a safe human-readable error message is shown — never a traceback, API key, or filesystem path.

**Command line:**

1. Put your resume text into `resume.txt`.
2. Run `python main.py`.
3. Open the generated `portfolio.html` in any browser.

## 4. Architecture

```
uploaded .txt CV (frontend)  or  resume.txt (CLI)
              │
              ▼
Python: clean + validate resume text
              │
              ▼
Gemini REST API (gemini-2.5-flash, JSON-only response requested)
              │
              ▼
Python: parse JSON
              │
              ▼
Python: normalize into the project's deterministic schema
              │
              ▼
Python: grounding validation (keep only facts supported by the resume)
              │
              ▼
Python: render HTML from template.html + style.css
              │
              ▼
portfolio.html  ──►  browser (via /portfolio or opened as a file)
```

`server.py` reuses the exact same functions from `main.py` — it never
duplicates the Gemini, JSON, grounding, or rendering logic.

## 5. Technologies Used

- **Language**: Python 3.10+ (only the standard library plus two packages)
- **AI API**: Google Gemini API (`gemini-2.5-flash`) over HTTPS/REST using the `requests` library
- **Configuration**: `python-dotenv` loads `GEMINI_API_KEY` from a local `.env` file
- **Web server**: Python standard library only (`http.server`, `socketserver`) — no web framework
- **Data format**: JSON (Gemini response is parsed, normalized, and validated by Python)
- **Frontend**: HTML5 + CSS3 (`frontend/index.html`, `frontend/app.css`) with a small amount of **vanilla JavaScript** (no framework, no libraries, no npm)
- **Output**: Semantic HTML5 (`template.html` + generated fragments) and CSS3 (`style.css`)
- **Version control**: GitHub

**No** React, TypeScript, Node.js, Express, Flask, FastAPI, Django, databases,
LangChain, RAG, vector databases, AI agents, or frontend JavaScript frameworks
are used. **No database is used** — the portfolio is written as a static
`portfolio.html` file. **No frontend framework is used** — the web UI is plain
HTML/CSS with a minimal inline vanilla-JavaScript script.

## 6. Project Structure

```
.
├── main.py                    # Core pipeline: cleaning, Gemini REST call,
│                              #   JSON parsing/normalization, grounding
│                              #   validation, HTML rendering, saving
├── server.py                  # Local web server (stdlib only): serves the
│                              #   frontend, accepts .txt uploads, reuses
│                              #   main.py's pipeline
├── frontend/
│   ├── index.html             # Web UI (upload, loading, result, error states)
│   └── app.css                # Web UI styling (no framework)
├── resume.txt                 # Plain-text input resume (sample data)
├── template.html              # HTML5 template with semantic placeholders
├── style.css                  # Portfolio styling (kept separate, not inlined)
├── requirements.txt           # Python dependencies (requests, python-dotenv)
├── README.md                  # This documentation
├── .env.example               # Example environment variables (placeholder only)
├── .gitignore                 # Git exclusion rules
├── test_json_validation.py    # Diagnostic test: malformed/incomplete JSON safety
├── test_grounding_validation.py  # Deterministic tests for grounding validation
└── portfolio.html             # Generated output (ignored by Git, regenerated
                               #   on every successful run)
```

## 7. Installation

1. Install Python 3.10 or newer (see below).
2. Create and activate a virtual environment (recommended, see below).
3. Install the dependencies: `pip install -r requirements.txt`.
4. Get a Gemini API key from Google AI Studio (see below).
5. Create a `.env` file from `.env.example` and add your key.

That's it — no other setup is required.

## 8. Python Version Requirement

Python 3.10 or newer is required (3.11+ recommended). The project uses only
the Python standard library plus `requests` and `python-dotenv`.

## 9. Virtual Environment Setup

Create an isolated environment so dependencies do not affect the rest of
your system:

```bash
# Windows (Git Bash or PowerShell)
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

`.venv/` is already excluded from Git via `.gitignore`.

## 10. Installing Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` contains only what the implementation actually uses:

- `requests>=2.28` — direct Gemini REST API calls
- `python-dotenv>=1.0` — loads `GEMINI_API_KEY` from `.env`

No other dependencies are required or added.

## 11. Creating .env

Copy the example file and add your key:

```bash
cp .env.example .env
```

Then edit `.env` so it contains your real key:

```
GEMINI_API_KEY=your_actual_key_here
```

The API key is loaded only from the environment (`.env` file or environment
variable) and is **never hardcoded, printed, or embedded in the generated HTML**.
`.env` is excluded from Git.

## 12. Setting GEMINI_API_KEY (Google AI Studio)

1. Go to <https://aistudio.google.com/apikey> and sign in with your Google account.
2. Click **Create API key** (or **Get API key**) and copy the generated key.
3. Keep the key private — treat it like a password. Never commit it.

**A valid Gemini API key is required for actual AI generation.** The Gemini
API requires internet access and a valid key. Free-tier keys work but are
subject to quota and rate limits; when the quota is exceeded the program
reports a clear message (e.g. `Error: Gemini API quota or rate limit exceeded.`)
and exits gracefully.

## 13. Running the Application

### Web app

```bash
python server.py
```

Expected startup output:

```
AI Resume Portfolio Generator
Running at: http://localhost:8000/
```

Then open <http://localhost:8000/> in your browser, upload a `.txt` CV, and
click **Generate Portfolio**.

### Command line

```bash
python main.py
```

Expected output on a successful run:

```
============================================================
 AI-Assisted Resume Portfolio Generator
============================================================
Resume loaded successfully.
Cleaned resume character count: 2952 characters

Sending resume to Gemini for JSON extraction...
Using Gemini REST API...
Gemini REST HTTP response received.

Gemini response received successfully.

Gemini JSON parsed and validated successfully.

--- Grounding Validation ---
Skills removed as unsupported: 0
Technologies removed as unsupported: 0
...
----------------------------

--- Normalized Resume Data ---
{ ...normalized JSON... }

--- Normalization Summary ---
Education items: 1
Experience items: 2
Project items: 2
Skills: 15
Achievements: 2
Contact links: 2
-------------------------------

Generating portfolio HTML...

Portfolio generated successfully: portfolio.html
```

### Supported CV format

The current upload format is **`.txt` only** (plain text, UTF-8). The web UI
accepts `.txt` files, and `server.py` rejects any other extension with a clear
message. **PDF and DOCX are not supported** — they are not implemented.

## 14. How Portfolio Generation Works

1. **Read + clean + validate** — the CV text is read as UTF-8, stripped of
   blank lines and stray whitespace, and checked to be non-empty and long enough.
2. **Gemini extraction** — the cleaned resume is sent to `gemini-2.5-flash`
   over the REST API with `responseMimeType: "application/json"` and a strict
   zero-hallucination prompt. Gemini returns structured JSON only.
3. **Parse + normalize** — the JSON is parsed safely (invalid, incomplete, or
   null responses become safe defaults) and normalized into the project's
   deterministic schema. Unknown Gemini fields are ignored.
4. **Grounding validation** — extracted facts are checked against the original
   resume text; anything not explicitly supported is removed (see §15).
5. **Render** — `render_html()` reads `template.html` and `style.css` from
   disk, substitutes the normalized data into the placeholders, and omits any
   section that has no data. `portfolio.html` is always generated by Python —
   never written by hand.

## 15. Grounding Validation

Gemini output is treated as a **draft**, and a Python-side grounding layer
filters it against the source resume before anything reaches the portfolio:

- Skills and technologies must appear **explicitly** in the resume — semantic
  equivalents, paraphrases, and generalized phrases (e.g. "Agile
  methodologies" appearing only inside a sentence) are rejected.
- Companies, project titles, education institutions, and locations must match
  the resume text (conservative normalization: lowercase, trimmed, collapsed
  whitespace).
- URLs, emails, and phone numbers are kept only if they appear in the resume.
- Matching is **conservative by design**: false negatives (dropping a
  borderline value) are preferred over hallucinations.

After grounding, the console prints a summary such as:

```
--- Grounding Validation ---
Skills removed as unsupported: 0
Technologies removed as unsupported: 0
Companies removed as unsupported: 0
Projects removed as unsupported: 0
Education institutions removed as unsupported: 0
Locations removed as unsupported: 0
Contact values removed as unsupported: 0
----------------------------
```

This does **not** guarantee zero hallucinations — it reduces the risk. You
must still review the final portfolio against the resume (§18).

## 16. Security Considerations

- `GEMINI_API_KEY` is stored only in the local `.env` file, which is ignored
  by Git. It is never hardcoded, printed, or written into HTML. **The API key
  is never sent to the browser** — it stays in the server/CLI process.
- All Gemini-supplied text is escaped with Python's `html.escape()` before
  being inserted into the generated HTML.
- External links are restricted to `http://` / `https://`; dangerous schemes
  such as `javascript:`, `data:`, and `vbscript:` are rejected.
- `server.py` serves **only whitelisted routes** (`/`, `/app.css`, `/portfolio`,
  `/download`, `POST /generate`). There is no generic static file serving, so
  arbitrary filesystem access and path-traversal attempts return 404.
- Uploads are limited to `.txt` files, empty files are rejected, and the
  maximum body size is capped at **1 MB**.
- Errors returned to the browser are safe, human-readable messages. Python
  tracebacks are logged to the server console only, never to the client.
- Unexpected placeholders in the template (`{{...}}`) raise a clear error
  instead of producing broken HTML.
- `portfolio.html` is regenerated on every successful run and is ignored by
  Git (see §21).

## 17. Testing

Run the two deterministic test suites (neither makes Gemini API calls):

```bash
python test_json_validation.py
python test_grounding_validation.py
```

- **`test_json_validation.py`** — verifies that malformed or incomplete Gemini
  responses never crash the application: completely invalid JSON, a valid
  non-object root, incomplete JSON, and JSON with null values are all handled
  safely (clear error or safe empty defaults). It never loads or prints an
  API key.
- **`test_grounding_validation.py`** — deterministic tests for the grounding
  layer: unsupported skills/technologies/companies/projects/institutions/
  locations/URLs/contact values are removed, exact matches (case-insensitive,
  whitespace-normalized) are preserved, and semantic/paraphrased matches are
  rejected.

Current results: `test_grounding_validation.py` → 56 passed, 0 failed;
`test_json_validation.py` → all cases handled safely.

## 18. Responsible AI

Gemini's output is treated as a **draft**, not as truth:

- The prompt instructs the model to extract only information present in the
  resume and never invent or fabricate content.
- The prompt also states that the generated content will be manually verified
  against the original resume.
- Python validates the JSON structure, enforces the project's schema, and
  runs grounding validation against the source resume.
- **You are still responsible for reviewing the final `portfolio.html`**
  against the original resume before sharing or submitting it anywhere.

This tool assists, but does not replace, human judgment.

## 19. Privacy

- Your resume text is sent to Google's Gemini API for processing. It is not
  stored by this program (uploads are processed in memory).
- Do not include sensitive information in your CV — no passwords, government
  IDs, home addresses, financial data, or anything you would not want shared
  with a third-party AI service.
- The API key never leaves your machine (it is only sent to Google in the
  request header for authentication).

## 20. Hallucination Risks and Known Limitations

Large language models can hallucinate — produce plausible-sounding content
that is not in the source material. This project reduces (but cannot
eliminate) that risk through its strict prompt, JSON validation, and grounding
layer. This application does **not** guarantee zero hallucinations.

Known limitations:

- **A valid Gemini API key and internet access are required** for actual AI
  generation; free-tier keys are subject to quota/rate limits.
- Gemini is non-deterministic: repeated runs may produce slightly different
  JSON, and occasional model errors are possible.
- The quality of the output depends on the quality and clarity of the source
  resume.
- Only information present in the resume can be extracted; anything missing is
  left empty.
- No automatic fact-checking or verification is performed by the program.
- Only `.txt` uploads are supported — PDF/DOCX are not implemented.
- The web server is a local development server (`http.server`); it is not
  hardened for public internet deployment.

Always verify names, dates, employers, projects, achievements, and links
before using the portfolio.

## 21. GitHub Submission Instructions

1. **Before committing, confirm no secrets are staged**: `.env` must not exist
   in the repository (it is in `.gitignore`). Verify with `git status` and,
   if needed, `git ls-files | grep -i env`.
2. Include: `main.py`, `server.py`, `frontend/`, `resume.txt`, `template.html`,
   `style.css`, `requirements.txt`, `README.md`, `.gitignore`, `.env.example`,
   `test_json_validation.py`, and `test_grounding_validation.py`.
3. `portfolio.html` **is ignored by Git** (generated output — it is
   regenerated on every successful run). If you want to show the generated
   output in the repository, regenerate it with `python main.py` (or
   `python server.py`) and force-add it (`git add -f portfolio.html`) —
   otherwise it stays out of version control.
4. Write a clear commit message describing the pipeline, then push to your
   GitHub repository.
5. In the repository description or README, note that the project requires a
   Gemini API key and internet access to run.

---

**Final reminder**: review the generated `portfolio.html` against your
original resume before sharing it. Gemini output is a draft.
