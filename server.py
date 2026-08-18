"""
AI Resume Portfolio Generator - Local web server (Stage 2 integration)
======================================================================

A small local server built ONLY with the Python standard library. It serves
the approved Stage 1 frontend and connects the "Generate Portfolio" button
to the EXISTING pipeline in main.py (no duplication of that logic).

Endpoints:
    GET  /            -> frontend/index.html
    GET  /app.css     -> frontend/app.css
    POST /generate    -> accept a .txt CV (multipart/form-data), run the
                         existing pipeline, and write portfolio.html
    GET  /portfolio   -> the generated portfolio.html
    GET  /download    -> the generated portfolio.html as a download

Security notes:
    - Only the whitelisted routes above are served; there is no generic
      static-file serving, so arbitrary filesystem access is impossible.
    - Errors returned to the browser are safe, human-readable messages.
      Tracebacks are logged to the SERVER console only, never to the client.
    - The Gemini API key is read from .env and never exposed to the browser.

Run with:
    python server.py
"""

import json
import os
import sys
import traceback
from email import message_from_bytes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

import main as pipeline  # the existing, working pipeline - reused, never duplicated
                          # (aliased because this file defines its own main())

# ---------------------------------------------------------------------------
# Paths (anchored to this file's directory so the server works from any CWD)
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_INDEX = BASE_DIR / "frontend" / "index.html"
FRONTEND_CSS = BASE_DIR / "frontend" / "app.css"
PORTFOLIO_FILE = BASE_DIR / "portfolio.html"

MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB cap for uploaded CVs
MIN_CV_NON_WHITESPACE = 30  # same rule as main.validate_resume_text


# ---------------------------------------------------------------------------
# Safe, user-facing errors
# ---------------------------------------------------------------------------

class ServerError(Exception):
    """An error that maps to a safe JSON error response (never a traceback)."""

    def __init__(self, status, message):
        self.status = status
        self.message = message
        super().__init__(message)


class GeminiHTTPError(ServerError):
    """Translates main.GeminiAPIError into a safe HTTP error response."""

    @staticmethod
    def from_api_error(error):
        reason = getattr(error, "reason", "") or ""
        if "quota" in reason or "rate" in reason:
            return GeminiHTTPError(503, "Gemini API quota or rate limit exceeded. Please try again later.")
        if reason == "timeout":
            return GeminiHTTPError(504, "Gemini request timed out. Please try again later.")
        if reason == "network error":
            return GeminiHTTPError(502, "Could not reach the Gemini API. Check your internet connection and try again.")
        if reason == "authentication error":
            return GeminiHTTPError(502, "Gemini API authentication failed. Check the server configuration.")
        if "JSON parse error" in reason or "JSON validation error" in reason:
            return GeminiHTTPError(502, "Gemini returned an invalid response. Please try again.")
        if "HTML rendering error" in reason:
            return GeminiHTTPError(502, "Could not render the portfolio. Please try again.")
        return GeminiHTTPError(502, "Portfolio generation failed. Please try again.")


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class PortfolioHandler(BaseHTTPRequestHandler):
    """Serves only the whitelisted routes for the portfolio application."""

    # Mask the default "BaseHTTP/0.6 Python/x.y.z" server banner so the
    # Python version is not advertised to clients.
    server_version = "PortfolioServer"
    sys_version = ""

    # Same security headers on every response: no MIME sniffing, a content
    # security policy that only allows same-origin resources plus the page's
    # own inline script (no external scripts, no eval, no inline styles), and
    # no caching for sensitive/dynamic content.
    _CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'"

    def _send_security_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", self._CSP)

    # ----- response helpers -------------------------------------------------

    def _send_json(self, status, payload, cache="no-cache, no-store"):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_security_headers()
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type, as_attachment=False, cache="no-cache"):
        try:
            data = path.read_bytes()
        except OSError:
            self._send_json(404, {"success": False, "error": "File not found."})
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self._send_security_headers()
        self.send_header("Cache-Control", cache)
        if as_attachment:
            self.send_header("Content-Disposition", 'attachment; filename="portfolio.html"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ----- request body / multipart parsing ---------------------------------

    def _read_body(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ServerError(400, "Malformed request: invalid Content-Length.")
        if length <= 0:
            raise ServerError(400, "Empty request body.")
        if length > MAX_BODY_BYTES:
            raise ServerError(413, "Upload is too large (maximum 1 MB).")
        return self.rfile.read(length)

    def _parse_upload(self):
        """Returns (file_bytes, filename) parsed from a multipart/form-data body."""
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ServerError(400, "Request must use multipart/form-data.")
        body = self._read_body()
        try:
            message = message_from_bytes(
                b"Content-Type: " + content_type.encode("utf-8") + b"\r\n"
                b"MIME-Version: 1.0\r\n\r\n" + body
            )
        except Exception:
            raise ServerError(400, "Malformed upload request.")
        if not message.is_multipart():
            raise ServerError(400, "Malformed upload request.")
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() != "form-data":
                continue
            filename = part.get_filename()
            if filename:
                payload = part.get_payload(decode=True)
                if payload is None:
                    raise ServerError(400, "Could not read the uploaded file.")
                return payload, filename
        raise ServerError(400, "No file was uploaded.")

    # ----- backend pipeline reuse -------------------------------------------

    def _get_api_key(self):
        load_dotenv(BASE_DIR / ".env")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not api_key.strip():
            raise ServerError(500, "Server configuration error: Gemini API key is not configured.")
        return api_key.strip()

    def _generate_portfolio(self, cv_bytes):
        """Runs the uploaded CV through the EXISTING main.py pipeline."""
        # 1. Decode and clean the CV text (reuses pipeline.clean_resume_text).
        text = cv_bytes.decode("utf-8", errors="replace")
        cleaned = pipeline.clean_resume_text(text)

        # 2. Validate (mirrors pipeline.validate_resume_text, but without sys.exit).
        if not cleaned.strip():
            raise ServerError(400, "CV is empty. Please upload a non-empty resume.")
        if len("".join(cleaned.split())) < MIN_CV_NON_WHITESPACE:
            raise ServerError(400, "CV is too short. Please provide a more complete resume.")
        try:
            pipeline.validate_resume_text(cleaned)
        except SystemExit:
            raise ServerError(400, "CV validation failed. Please provide a valid resume.")

        # 3. Gemini extraction -> JSON parsing/normalization (existing functions).
        try:
            api_key = self._get_api_key()
            json_response = pipeline.extract_resume_json(cleaned, api_key)
            normalized = pipeline.parse_and_validate_json(json_response)
        except pipeline.GeminiAPIError as error:
            raise GeminiHTTPError.from_api_error(error)

        # 4. Grounding validation (existing function - filters unsupported facts).
        normalized, _ = pipeline.grounding_validate_resume(normalized, cleaned)

        # 5. Render + save (existing functions).
        try:
            html_content = pipeline.render_html(normalized)
            pipeline.save_portfolio(html_content)
        except pipeline.GeminiAPIError as error:
            raise GeminiHTTPError.from_api_error(error)
        except SystemExit:
            raise ServerError(500, "Could not save the generated portfolio. Check server permissions.")

    # ----- routes ------------------------------------------------------------

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                if not FRONTEND_INDEX.exists():
                    self._send_json(404, {"success": False, "error": "Frontend not found on the server."})
                else:
                    self._send_file(FRONTEND_INDEX, "text/html; charset=utf-8")
                return
            if path == "/app.css":
                self._send_file(FRONTEND_CSS, "text/css; charset=utf-8")
                return
            if path == "/portfolio":
                if not PORTFOLIO_FILE.exists():
                    self._send_json(404, {"success": False, "error": "Portfolio has not been generated yet. Generate it first."})
                else:
                    self._send_file(PORTFOLIO_FILE, "text/html; charset=utf-8", cache="no-store")
                return
            if path == "/download":
                if not PORTFOLIO_FILE.exists():
                    self._send_json(404, {"success": False, "error": "Portfolio has not been generated yet. Generate it first."})
                else:
                    self._send_file(PORTFOLIO_FILE, "text/html; charset=utf-8", as_attachment=True, cache="no-store")
                return
            self._send_json(404, {"success": False, "error": "Not found."})
        except Exception:
            traceback.print_exc()  # server console only - never to the browser
            self._send_json(500, {"success": False, "error": "An unexpected server error occurred. Please try again."})

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/generate":
            self._send_json(404, {"success": False, "error": "Not found."})
            return
        try:
            cv_bytes, filename = self._parse_upload()
            if not filename or not filename.lower().endswith(".txt"):
                raise ServerError(400, "Unsupported file type. Please upload a .txt file.")
            self._generate_portfolio(cv_bytes)
        except ServerError as error:
            self._send_json(error.status, {"success": False, "error": error.message})
            return
        except SystemExit:
            # A pipeline function called sys.exit(); translate to a safe error.
            self._send_json(500, {"success": False, "error": "Portfolio generation failed. Please try again."})
            return
        except Exception:
            traceback.print_exc()  # server console only - never to the browser
            self._send_json(500, {"success": False, "error": "An unexpected server error occurred. Please try again."})
            return
        self._send_json(200, {
            "success": True,
            "message": "Portfolio generated successfully.",
            "portfolio_url": "/portfolio",
        })

    # Suppress the default per-request logging noise but keep a compact line.
    def log_message(self, format, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), format % args))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    host = "127.0.0.1"
    port = 8000

    try:
        server = ThreadingHTTPServer((host, port), PortfolioHandler)
    except OSError as error:
        print(f"Error: could not start the server on port {port}. {error}")
        sys.exit(1)

    print("AI Resume Portfolio Generator")
    print(f"Running at: http://localhost:{port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
