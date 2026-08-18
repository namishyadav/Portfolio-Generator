"""
AI-Assisted Resume Portfolio Generator
======================================
Step 4: Resume reading/cleaning/validation + Gemini API integration +
JSON normalization + portfolio.html generation.

Current pipeline:
1. Load the Gemini API key from .env using python-dotenv.
2. Read, clean, and validate resume.txt.
3. Send the cleaned resume to the Gemini API and ask for structured JSON.
4. Parse the JSON and normalize it into the project's deterministic schema:
   only the expected schema fields are kept, unknown Gemini fields are ignored,
   and missing values become "" / [].
5. Render portfolio.html from template.html + style.css using the normalized data.
6. Save portfolio.html to disk.
"""

import os
import re
import sys
import json
from html import escape

import requests
from dotenv import load_dotenv


class GeminiAPIError(RuntimeError):
    """Application-level Gemini API failure that should not crash the program."""

    def __init__(self, reason, detail=None):
        self.reason = reason
        self.detail = detail or reason
        super().__init__(self.detail)

# Gemini model used for extracting structured JSON from the resume.
# gemini-2.5-flash is a currently supported, stable model with good
# price-performance and reliable JSON output mode.
GEMINI_MODEL = "gemini-2.5-flash"

# Instructions sent to Gemini alongside the resume text.
# These rules keep the model grounded: resume.txt is the ONLY source of
# truth, and nothing may be invented, inferred, or embellished.
GEMINI_SYSTEM_INSTRUCTION = """
You are a strict resume parser. resume.txt is the ONLY source of truth.

Grounding rules (non-negotiable):
- Use only facts explicitly stated in the supplied resume.
- Do not infer information from context.
- Do not convert implied knowledge into explicit skills or technologies.
- Do not use general knowledge about the candidate.
- Do not complete missing information.
- Never invent, infer, embellish, or assume anything: skills, technologies,
  companies, job titles, dates, education details, GPA, achievements,
  project names, project descriptions, URLs, contact information,
  locations, or coursework.
- If a field is not explicitly supported by the resume, return an empty
  string ("") or an empty array ([]).
- Preserve the resume's factual wording where practical. Do not creatively
  rewrite factual claims.
- Return JSON only. Do not return Markdown.
- Do not include ```json fences or any other formatting around the JSON.
- Follow the exact JSON schema below. Do not add extra fields.
- Keep the professional summary concise and factual, based only on the resume.
- The generated content will be manually verified against the original
  resume.txt, so accuracy is critical.

Return the JSON in exactly this structure:
{
  "name": "",
  "headline": "",
  "summary": "",
  "skills": [],
  "education": [
    {
      "institution": "",
      "degree": "",
      "field_of_study": "",
      "start_date": "",
      "end_date": "",
      "gpa": "",
      "highlights": [],
      "location": ""
    }
  ],
  "experience": [
    {
      "company": "",
      "role": "",
      "location": "",
      "start_date": "",
      "end_date": "",
      "description": [],
      "technologies": []
    }
  ],
  "projects": [
    {
      "title": "",
      "description": [],
      "technologies": [],
      "link": "",
      "start_date": "",
      "end_date": ""
    }
  ],
  "achievements": [],
  "contact": {
    "email": "",
    "phone": "",
    "location": "",
    "links": [
      {
        "platform": "",
        "url": ""
      }
    ]
  }
}
"""


def load_environment():
    """
    Loads the Gemini API key from the local .env file.

    Steps:
    1. Load .env using python-dotenv.
    2. Read GEMINI_API_KEY with os.getenv().
    3. If the key is missing or blank, print a clear error and exit gracefully.

    Never prints the actual API key.
    Returns the API key string.
    """
    # 1. Load environment variables from the .env file.
    load_dotenv()

    # 2. Read the API key from the environment.
    api_key = os.getenv("GEMINI_API_KEY")

    # 3. Reject a missing or blank key.
    if not api_key or not api_key.strip():
        print("\nError: GEMINI_API_KEY is not configured. Create a .env file and add your Gemini API key.")
        sys.exit(1)

    return api_key.strip()


def clean_resume_text(text):
    """
    Cleans up raw resume text WITHOUT changing the actual information.

    What it removes:
    - Leading and trailing whitespace on the whole text.
    - Blank lines, and lines that contain only whitespace.
    - Repeated spaces and tabs inside a line (collapsed to one space).

    What it keeps:
    - Meaningful line separation (a single blank line between blocks).

    Returns the cleaned resume text as a string.
    """
    cleaned_lines = []

    for line in text.splitlines():
        # Collapse repeated spaces/tabs into a single space,
        # then remove leading/trailing whitespace from the line.
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()

        if not cleaned_line:
            # This line is blank. Keep ONE blank line so that sections
            # stay visually separated, but drop the extra blank lines.
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
        else:
            cleaned_lines.append(cleaned_line)

    # Remove any blank line(s) at the very end of the text.
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)


def validate_resume_text(text):
    """
    Validates that the cleaned resume text has enough content.

    Rejects the input (by exiting gracefully) when:
    - The text is empty (or only whitespace).
    - The text has fewer than 30 non-whitespace characters.

    Returns the validated text on success.
    """
    # 1. Reject completely empty content.
    if not text.strip():
        print("\nError: resume.txt is empty. Please add your resume.")
        sys.exit(1)

    # 2. Reject content that is too short.
    #    Only non-whitespace characters count toward the minimum.
    non_whitespace_count = len("".join(text.split()))
    if non_whitespace_count < 30:
        print("\nError: resume.txt is too short. Please provide a more complete resume.")
        sys.exit(1)

    return text


def read_resume_file(file_path="resume.txt"):
    """
    Reads the resume file, cleans it, and validates it.

    Steps:
    1. Check that the file exists.
    2. Read the file using UTF-8 encoding.
    3. Clean the content with clean_resume_text().
    4. Validate the cleaned content with validate_resume_text().

    Returns the validated, cleaned resume text.
    """
    # 1. Check whether the resume file exists.
    if not os.path.exists(file_path):
        print(f"\nError: {file_path} was not found. Please create {file_path} and add your resume.")
        sys.exit(1)

    # 2. Read the file using UTF-8 encoding.
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            raw_text = file.read()
    except Exception as error:
        print(f"\nError: Could not read file '{file_path}': {error}")
        sys.exit(1)

    # 3. Clean the raw text.
    cleaned_text = clean_resume_text(raw_text)

    # 4. Validate the cleaned text.
    validate_resume_text(cleaned_text)

    # 5. Return the validated, cleaned text.
    return cleaned_text


def extract_resume_json(resume_text, api_key):
    """
    Sends the cleaned resume text to the Gemini API via REST and requests structured JSON.

    Steps:
    1. Prepare the REST API request with the resume text and extraction instructions.
    2. Send a POST request to the Gemini REST endpoint with the API key in headers.
    3. Configure response to return JSON via generationConfig.
    4. Return the RAW response text. JSON parsing happens in a later step.

    Raises GeminiAPIError for network/auth/quota/server issues so the program
    can display a concise user-facing message without printing a full traceback.
    """
    print("\nSending resume to Gemini for JSON extraction...")

    # 1. Prepare the REST API endpoint and headers.
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    # 2. Prepare the request payload with resume text, system instruction, and JSON response config.
    payload = {
        "system_instruction": {
            "parts": [
                {"text": GEMINI_SYSTEM_INSTRUCTION}
            ]
        },
        "contents": [
            {
                "parts": [
                    {"text": resume_text}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    print("Using Gemini REST API...")

    try:
        # 3. Send POST request to Gemini REST API with a 60-second timeout.
        #    Extracting the full resume with the system instruction and JSON
        #    mode takes longer than a trivial prompt, so 30s is too tight.
        response = requests.post(url, headers=headers, json=payload, timeout=60)

        # 4. Check HTTP status code and handle errors.
        if response.status_code == 200:
            # The HTTP request completed successfully (the response body is
            # parsed next).
            print("Gemini REST HTTP response received.")
            # Extract the response text from the JSON response.
            try:
                response_json = response.json()
                if "candidates" in response_json and len(response_json["candidates"]) > 0:
                    candidate = response_json["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            text = parts[0]["text"].strip()
                            if text:
                                return text
                            else:
                                raise GeminiAPIError("API error", "Gemini returned an empty response.")
                raise GeminiAPIError("API error", "Gemini response structure was invalid.")
            except json.JSONDecodeError as error:
                raise GeminiAPIError("API error", "Failed to parse Gemini JSON response.") from error
        elif response.status_code in (400, 401, 403):
            raise GeminiAPIError("authentication error", "Invalid or unauthorized Gemini API key.")
        elif response.status_code == 429:
            raise GeminiAPIError("API/quota error", "Gemini API quota or rate limit exceeded.")
        elif response.status_code >= 500:
            raise GeminiAPIError("API server error", "Gemini API server error.")
        else:
            raise GeminiAPIError("API error", f"Gemini API request failed (HTTP {response.status_code}).")

    except requests.Timeout:
        raise GeminiAPIError("timeout", "Gemini request timed out after 60 seconds.")
    except requests.ConnectionError:
        raise GeminiAPIError("network error", "Could not connect to the Gemini API.")
    except requests.RequestException as error:
        raise GeminiAPIError("network error", f"Gemini request failed: {type(error).__name__}")
    except KeyboardInterrupt:
        raise
    except GeminiAPIError:
        raise
    except Exception as error:
        raise GeminiAPIError("unexpected error", f"Unexpected error while calling the Gemini API: {type(error).__name__}") from error


def normalize_string(value):
    """
    Converts a value into a clean, trimmed string.

    - None and empty values become "".
    - Lists are joined with ", " so no information is lost
      (Gemini sometimes returns a single-element list).
    - Everything else is converted to a trimmed string.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, list):
        return ", ".join(normalize_string(item) for item in value if normalize_string(item))
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def normalize_list(value):
    """
    Converts a value into a list.

    - None and empty values become [].
    - A list is kept as-is.
    - Any other single value is wrapped into a one-item list
      (e.g. a plain string becomes ["string"]).
    """
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_value(item, *keys):
    """
    Returns the first non-empty value found under any of the given keys.

    This is the core fix for field-name mismatches: if Gemini used a slightly
    different name (e.g. "graduation_date" instead of "end_date"), the value
    is still found and preserved.
    """
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_technologies(value):
    """
    Converts a technologies/skills field into a list of strings.

    - A list is kept as-is (each item trimmed).
    - A comma-separated string ("Python, HTML, CSS") is split into
      ["Python", "HTML", "CSS"] - a representation change only.
    - Any other single value becomes a one-item list.
    """
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [normalize_string(item) for item in value if normalize_string(item)]
    if isinstance(value, str):
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value.strip()]
    return [normalize_string(value)]


def _split_date_range(dates):
    """
    Splits a combined date range such as "June 2025 - August 2025" into
    (start_date, end_date).

    Only a clean, mechanical split is accepted:
    - exactly two parts separated by a dash, and
    - each part must contain at least one digit (a year).

    Ambiguous or non-splittable strings return ("", "") so dates are never
    guessed or invented.
    """
    if not dates:
        return "", ""
    parts = [part.strip() for part in re.split(r"\s*-\s*", str(dates)) if part.strip()]
    if len(parts) != 2:
        return "", ""
    start, end = parts
    if not re.search(r"\d", start) or not re.search(r"\d", end):
        return "", ""
    return start, end


def _item_has_content(item):
    """
    Returns True if an item holds any real information (non-empty string,
    list, dict, or other value). Used to decide whether to keep an item.
    """
    for value in item.values():
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return True
        elif isinstance(value, (list, dict)):
            if value:
                return True
        else:
            return True
    return False


def parse_and_validate_json(raw_json_str):
    """
    Parses and validates the raw Gemini JSON response into a normalized structure.

    The normalized output follows the project's deterministic schema exactly:
    Gemini's field names are matched through several aliases and mapped onto
    the schema fields, while any unrecognized extra fields are ignored. Missing
    values become "" or [], and genuinely empty or malformed items are skipped.

    Steps:
    1. Parse the raw JSON string using json.loads().
    2. Validate that the root is a dictionary.
    3. Ensure all top-level fields exist and have correct types.
    4. Normalize missing/null values to appropriate defaults.
    5. Normalize nested structures (education, experience, projects, achievements).
    6. Normalize contact information and links.
    7. Return the normalized dictionary.

    Raises GeminiAPIError if the JSON is malformed or invalid.
    """
    # 1. Parse the raw JSON response.
    try:
        data = json.loads(raw_json_str)
    except json.JSONDecodeError as error:
        raise GeminiAPIError("JSON parse error", f"Gemini response was not valid JSON: {error}") from error

    # 2. Ensure the root is a dictionary.
    if not isinstance(data, dict):
        raise GeminiAPIError("JSON validation error", "Gemini response root is not a JSON object.")

    # 3. Create the master normalized schema.
    normalized = {
        "name": "",
        "headline": "",
        "summary": "",
        "skills": [],
        "education": [],
        "experience": [],
        "projects": [],
        "achievements": [],
        "contact": {
            "email": "",
            "phone": "",
            "location": "",
            "links": []
        }
    }

    # 4. Normalize top-level string fields.
    normalized["name"] = normalize_string(data.get("name"))
    normalized["headline"] = normalize_string(data.get("headline"))
    normalized["summary"] = normalize_string(data.get("summary"))

    # 5. Normalize top-level list fields.
    # Skills may arrive as a list, a single string, or a comma-separated
    # string such as "Python, JavaScript, SQL" - all become a list.
    normalized["skills"] = _normalize_technologies(data.get("skills"))

    # 6. Normalize education list.
    raw_education = data.get("education")
    if raw_education:
        for edu_item in normalize_list(raw_education):
            if not isinstance(edu_item, dict):
                continue  # Malformed item: skip it, keep processing valid ones.

            # Field-name aliases Gemini may use. The first non-empty value
            # wins; missing fields stay at their default "" or [].
            mapped_keys = (
                "institution", "school", "university", "college",
                "degree", "qualification", "credential",
                "field_of_study", "major", "field", "program", "concentration",
                "start_date", "start", "started",
                "end_date", "graduation_date", "graduation", "expected_graduation", "completed",
                "dates", "duration", "period", "date_range",
                "gpa",
                "highlights", "details", "coursework", "bullets",
                "location", "city", "place",
            )

            # Start/end dates come from their aliases. If both are still empty,
            # a combined "dates" string is split mechanically (never guessed).
            start_date = normalize_string(
                _first_value(edu_item, "start_date", "start", "started")
            )
            end_date = normalize_string(
                _first_value(edu_item, "end_date", "graduation_date", "graduation",
                             "expected_graduation", "completed")
            )
            if not (start_date and end_date):
                combined = normalize_string(
                    _first_value(edu_item, "dates", "duration", "period", "date_range")
                )
                split_start, split_end = _split_date_range(combined)
                if not start_date:
                    start_date = split_start
                if not end_date:
                    end_date = split_end

            normalized_edu = {
                "institution": normalize_string(
                    _first_value(edu_item, "institution", "school", "university", "college")
                ),
                "degree": normalize_string(
                    _first_value(edu_item, "degree", "qualification", "credential")
                ),
                "field_of_study": normalize_string(
                    _first_value(edu_item, "field_of_study", "major", "field", "program", "concentration")
                ),
                "start_date": start_date,
                "end_date": end_date,
                "gpa": normalize_string(_first_value(edu_item, "gpa")),
                "highlights": [
                    normalize_string(item)
                    for item in normalize_list(_first_value(edu_item, "highlights", "details", "coursework", "bullets"))
                    if normalize_string(item)
                ],
                # Location is preserved when Gemini provides it ("" by default).
                "location": normalize_string(
                    _first_value(edu_item, "location", "city", "place")
                ),
            }

            # Only keep the item if it carries real information.
            if _item_has_content(normalized_edu):
                normalized["education"].append(normalized_edu)

    # 7. Normalize experience list.
    raw_experience = data.get("experience")
    if raw_experience:
        for exp_item in normalize_list(raw_experience):
            if not isinstance(exp_item, dict):
                continue  # Malformed item: skip it, keep processing valid ones.

            mapped_keys = (
                "company", "employer", "organization", "org",
                "title", "role", "position", "job_title",
                "location", "place",
                "start_date", "start", "started",
                "end_date", "end", "ended",
                "dates", "duration", "period", "date_range",
                "description", "descriptions", "responsibilities", "details", "bullets",
                "technologies", "technology", "tech_stack", "skills", "tools",
            )

            # Start/end dates come from their aliases. If both are still empty,
            # a combined "dates" string is split mechanically (never guessed).
            start_date = normalize_string(
                _first_value(exp_item, "start_date", "start", "started")
            )
            end_date = normalize_string(
                _first_value(exp_item, "end_date", "end", "ended")
            )
            if not (start_date and end_date):
                combined = normalize_string(
                    _first_value(exp_item, "dates", "duration", "period", "date_range")
                )
                split_start, split_end = _split_date_range(combined)
                if not start_date:
                    start_date = split_start
                if not end_date:
                    end_date = split_end

            normalized_exp = {
                "company": normalize_string(
                    _first_value(exp_item, "company", "employer", "organization", "org")
                ),
                "role": normalize_string(
                    _first_value(exp_item, "role", "title", "position", "job_title")
                ),
                "location": normalize_string(
                    _first_value(exp_item, "location", "place")
                ),
                "start_date": start_date,
                "end_date": end_date,
                "description": [
                    normalize_string(item)
                    for item in normalize_list(_first_value(exp_item, "description", "descriptions", "responsibilities", "details", "bullets"))
                    if normalize_string(item)
                ],
                "technologies": _normalize_technologies(
                    _first_value(exp_item, "technologies", "technology", "tech_stack", "skills", "tools")
                ),
            }

            # Only keep the item if it carries real information.
            if _item_has_content(normalized_exp):
                normalized["experience"].append(normalized_exp)

    # 8. Normalize projects list.
    raw_projects = data.get("projects")
    if raw_projects:
        for proj_item in normalize_list(raw_projects):
            if not isinstance(proj_item, dict):
                continue  # Malformed item: skip it, keep processing valid ones.

            mapped_keys = (
                "name", "title", "project_name", "project",
                "description", "summary", "overview", "details",
                "technologies", "technology", "tech", "tech_stack", "stack", "tools",
                "link", "url", "href", "project_link", "github",
                "start_date", "start", "started",
                "end_date", "end", "ended",
                "dates", "duration", "period",
            )

            # Start/end dates come from their aliases. If both are still empty,
            # a combined "dates" string is split mechanically (never guessed).
            start_date = normalize_string(
                _first_value(proj_item, "start_date", "start", "started")
            )
            end_date = normalize_string(
                _first_value(proj_item, "end_date", "end", "ended")
            )
            if not (start_date and end_date):
                combined = normalize_string(
                    _first_value(proj_item, "dates", "duration", "period")
                )
                split_start, split_end = _split_date_range(combined)
                if not start_date:
                    start_date = split_start
                if not end_date:
                    end_date = split_end

            normalized_proj = {
                "title": normalize_string(
                    _first_value(proj_item, "title", "name", "project_name", "project")
                ),
                # Description stays a list of strings even when Gemini sends a
                # single string - it is NEVER stringified into "['...']".
                "description": [
                    normalize_string(item)
                    for item in normalize_list(_first_value(proj_item, "description", "summary", "overview", "details"))
                    if normalize_string(item)
                ],
                # Technologies may be a list or a comma-separated string
                # such as "Python, HTML, CSS" - both become a list.
                "technologies": _normalize_technologies(
                    _first_value(proj_item, "technologies", "technology", "tech", "tech_stack", "stack", "tools")
                ),
                "link": normalize_string(
                    _first_value(proj_item, "link", "url", "href", "project_link", "github")
                ),
                "start_date": start_date,
                "end_date": end_date,
            }

            # Only keep the item if it carries real information.
            if _item_has_content(normalized_proj):
                normalized["projects"].append(normalized_proj)

    # 9. Normalize achievements list (should be strings).
    raw_achievements = data.get("achievements")
    if raw_achievements:
        for ach_item in normalize_list(raw_achievements):
            normalized_ach = normalize_string(ach_item)
            if normalized_ach:  # Only add non-empty achievements
                normalized["achievements"].append(normalized_ach)

    # 10. Normalize contact information.
    raw_contact = data.get("contact")
    if isinstance(raw_contact, dict):
        normalized["contact"]["email"] = normalize_string(raw_contact.get("email"))
        normalized["contact"]["phone"] = normalize_string(raw_contact.get("phone"))
        normalized["contact"]["location"] = normalize_string(raw_contact.get("location"))

        # 11. Normalize contact links.
        raw_links = raw_contact.get("links")
        if raw_links:
            for link_item in normalize_list(raw_links):
                if isinstance(link_item, str):
                    # Convert URL string to dict with platform detection.
                    url = normalize_string(link_item)
                    if url:
                        # Detect platform from URL.
                        platform = "Link"
                        if "linkedin" in url.lower():
                            platform = "LinkedIn"
                        elif "github" in url.lower():
                            platform = "GitHub"
                        elif "twitter" in url.lower() or "x.com" in url.lower():
                            platform = "Twitter"
                        normalized["contact"]["links"].append({
                            "platform": platform,
                            "url": url
                        })
                elif isinstance(link_item, dict):
                    # Already a dict, normalize its fields.
                    normalized_link = {
                        "platform": normalize_string(link_item.get("platform") or "Link"),
                        "url": normalize_string(link_item.get("url") or link_item.get("link"))
                    }
                    if normalized_link["url"]:  # Only add if URL is present
                        normalized["contact"]["links"].append(normalized_link)

    return normalized


# ---------------------------------------------------------------------------
# Grounding validation (zero-hallucination guard)
# ---------------------------------------------------------------------------

def _grounding_normalize(text):
    """
    Normalizes text for conservative grounding comparisons.

    Lowercases, trims whitespace, and collapses runs of whitespace into a
    single space. Punctuation is left intact so genuine differences are
    never accidentally approved. No fuzzy matching is used.
    """
    if text is None:
        return ""
    text = str(text).lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _digits_only(text):
    """
    Extracts only the digits from a string (used for phone comparison,
    so formatting differences like "(206) 555-0100" vs "206-555-0100"
    do not cause a supported value to be rejected).
    """
    if text is None:
        return ""
    return re.sub(r"\D", "", str(text))


# Characters that mark a value as appearing in a LIST-LIKE context in the
# resume (e.g. "Skills: Python, JavaScript" or "- Data Structures"), as
# opposed to being embedded inside a prose sentence.
_LIST_BOUNDARY_CHARS = set(":,;|/\\-*\u2022()[]{}")


def _nearest_non_space_char(text, index, backward):
    """
    Returns the nearest non-space character at/beyond index, scanning in the
    given direction, or None at the text boundary.
    """
    step = -1 if backward else 1
    while 0 <= index < len(text):
        if text[index] != " ":
            return text[index]
        index += step
    return None


def _grounding_in_list_context(value_normalized, resume_normalized):
    """
    Returns True if the normalized value occurs in the resume next to list
    punctuation (comma, colon, pipe, bullet, bracket, ...) on at least one
    side - i.e. it is an ENUMERATED item, not a phrase copied from prose.

    This is the strictness that keeps enumerated skills/technologies
    ("Skills: Python, Git, HTML") while rejecting prose phrases Gemini
    copied verbatim from sentences (e.g. "modern web technologies" or
    "Agile methodologies") even when those phrases literally appear in the
    resume text.
    """
    start = 0
    while True:
        index = resume_normalized.find(value_normalized, start)
        if index == -1:
            return False
        left = _nearest_non_space_char(resume_normalized, index - 1, backward=True)
        right = _nearest_non_space_char(
            resume_normalized, index + len(value_normalized), backward=False
        )
        if (left is None or left in _LIST_BOUNDARY_CHARS) or (
            right is None or right in _LIST_BOUNDARY_CHARS
        ):
            return True
        start = index + 1


def _grounding_phrase_supported(value, resume_normalized, require_list_context=False):
    """
    Returns True if a phrase value is reasonably supported by the resume.

    - Single words use word-boundary matching so "Go" does not match "Google"
      and "R" does not match "REST".
    - Multi-word phrases use substring matching after conservative
      normalization (lowercase + collapsed whitespace).
    - When require_list_context=True (used for skills and technologies), a
      multi-word value must additionally appear in a list-like context in the
      resume (next to list punctuation), so prose phrases such as "modern web
      technologies" are rejected even when they literally occur in a sentence.

    This is deliberately conservative: it never uses fuzzy matching, so it
    cannot accidentally approve a hallucinated value.
    """
    value_normalized = _grounding_normalize(value)
    if not value_normalized:
        return False
    if " " in value_normalized:
        if require_list_context:
            return _grounding_in_list_context(value_normalized, resume_normalized)
        return value_normalized in resume_normalized
    return re.search(
        rf"(?<!\w){re.escape(value_normalized)}(?!\w)",
        resume_normalized,
    ) is not None


def grounding_validate_resume(data, resume_text):
    """
    Validates extracted factual fields against the original resume text.

    The zero-hallucination guarantee: every extracted fact must be explicitly
    supported by resume.txt. Unsupported values are removed (scalars become
    "", list items are dropped), while supported values are preserved.

    Validated fields:
    - skills, technologies (list items are filtered)
    - companies, education institutions, project titles (blanked)
    - locations (blanked when unsupported)
    - contact email / phone / location / link URLs (blanked or dropped)

    Descriptions and summaries are NOT filtered: a descriptive sentence may
    naturally be reworded, as long as its factual claims are grounded.

    Returns (filtered_data, removed_counts) where removed_counts maps each
    category to the number of unsupported values removed.
    """
    removed_counts = {
        "skills": 0,
        "technologies": 0,
        "companies": 0,
        "projects": 0,
        "institutions": 0,
        "locations": 0,
        "contact": 0,
    }

    # Defensive: unusable inputs are returned untouched.
    if not isinstance(data, dict) or not resume_text or not isinstance(resume_text, str):
        return data, removed_counts

    resume_normalized = _grounding_normalize(resume_text)
    resume_digits = _digits_only(resume_text)

    # 1. Skills: drop any skill not explicitly present in the resume.
    #    Multi-word skills must appear in a list-like context (not prose),
    #    so generalized phrases like "modern web technologies" are rejected.
    filtered_skills = []
    for skill in normalize_list(data.get("skills")):
        skill_text = normalize_string(skill)
        if skill_text and _grounding_phrase_supported(
            skill_text, resume_normalized, require_list_context=True
        ):
            filtered_skills.append(skill_text)
        else:
            removed_counts["skills"] += 1
    data["skills"] = filtered_skills

    # 2. Experience: companies, locations, and technologies.
    for exp in normalize_list(data.get("experience")):
        if not isinstance(exp, dict):
            continue
        company = normalize_string(exp.get("company"))
        if company and not _grounding_phrase_supported(company, resume_normalized):
            exp["company"] = ""
            removed_counts["companies"] += 1
        location = normalize_string(exp.get("location"))
        if location and not _grounding_phrase_supported(location, resume_normalized):
            exp["location"] = ""
            removed_counts["locations"] += 1
        filtered_tech = []
        for tech in normalize_list(exp.get("technologies")):
            tech_text = normalize_string(tech)
            if tech_text and _grounding_phrase_supported(
                tech_text, resume_normalized, require_list_context=True
            ):
                filtered_tech.append(tech_text)
            else:
                removed_counts["technologies"] += 1
        exp["technologies"] = filtered_tech

    # 3. Education: institutions and locations.
    for edu in normalize_list(data.get("education")):
        if not isinstance(edu, dict):
            continue
        institution = normalize_string(edu.get("institution"))
        if institution and not _grounding_phrase_supported(institution, resume_normalized):
            edu["institution"] = ""
            removed_counts["institutions"] += 1
        location = normalize_string(edu.get("location"))
        if location and not _grounding_phrase_supported(location, resume_normalized):
            edu["location"] = ""
            removed_counts["locations"] += 1

    # 4. Projects: titles and technologies.
    for proj in normalize_list(data.get("projects")):
        if not isinstance(proj, dict):
            continue
        title = normalize_string(proj.get("title"))
        if title and not _grounding_phrase_supported(title, resume_normalized):
            proj["title"] = ""
            removed_counts["projects"] += 1
        filtered_tech = []
        for tech in normalize_list(proj.get("technologies")):
            tech_text = normalize_string(tech)
            if tech_text and _grounding_phrase_supported(
                tech_text, resume_normalized, require_list_context=True
            ):
                filtered_tech.append(tech_text)
            else:
                removed_counts["technologies"] += 1
        proj["technologies"] = filtered_tech

    # 5. Contact: email, phone, location, and link URLs must appear in the resume.
    contact = data.get("contact")
    if isinstance(contact, dict):
        email = normalize_string(contact.get("email"))
        if email and _grounding_normalize(email) not in resume_normalized:
            contact["email"] = ""
            removed_counts["contact"] += 1
        phone = normalize_string(contact.get("phone"))
        if phone and _digits_only(phone) not in resume_digits:
            contact["phone"] = ""
            removed_counts["contact"] += 1
        location = normalize_string(contact.get("location"))
        if location and not _grounding_phrase_supported(location, resume_normalized):
            contact["location"] = ""
            removed_counts["contact"] += 1
        filtered_links = []
        for link in normalize_list(contact.get("links")):
            if not isinstance(link, dict):
                continue
            url = normalize_string(link.get("url"))
            if url and _grounding_normalize(url) in resume_normalized:
                filtered_links.append(link)
            else:
                removed_counts["contact"] += 1
        contact["links"] = filtered_links

    return data, removed_counts


def print_grounding_validation(removed_counts):
    """
    Prints the grounding validation diagnostics (counts of removed values).

    Shows only counts - never the API key and never sensitive data.
    """
    print("\n--- Grounding Validation ---")
    print(f"Skills removed as unsupported: {removed_counts['skills']}")
    print(f"Technologies removed as unsupported: {removed_counts['technologies']}")
    print(f"Companies removed as unsupported: {removed_counts['companies']}")
    print(f"Projects removed as unsupported: {removed_counts['projects']}")
    print(f"Education institutions removed as unsupported: {removed_counts['institutions']}")
    print(f"Locations removed as unsupported: {removed_counts['locations']}")
    print(f"Contact values removed as unsupported: {removed_counts['contact']}")
    print("----------------------------")


# ---------------------------------------------------------------------------
# HTML portfolio generation
# ---------------------------------------------------------------------------

def _escape(value):
    """
    Escapes a value for safe insertion into HTML.

    Uses html.escape() from the Python standard library. Gemini output is
    untrusted text, so EVERY string that came from the resume/API is escaped
    before it is placed into the generated HTML.
    """
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _is_safe_url(url):
    """
    Returns True only for safe HTTP/HTTPS URLs.

    Blocks dangerous schemes like javascript:, data:, and vbscript: so that
    untrusted Gemini-provided links cannot inject executable content.
    """
    if not url:
        return False
    url = url.strip()
    if " " in url:
        return False
    lowered = url.lower()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _render_date_range(start_date, end_date):
    """
    Builds a display date string from the available pieces.

    start/end dates are combined into "start - end"; a lone start or end date
    is shown on its own. Missing pieces are simply omitted - dates are never
    guessed or invented.
    """
    if start_date and end_date:
        return f"{_escape(start_date)} - {_escape(end_date)}"
    if end_date:
        return _escape(end_date)
    if start_date:
        return _escape(start_date)
    return ""


def _render_skills(skills):
    """
    Builds the skill badge fragment for the template's <ul class="skills-list">.

    Each skill becomes an <li class="skill-tag"> badge. No skill names are
    hardcoded - everything comes from the normalized data.
    """
    if not skills:
        return ""
    badges = []
    for skill in normalize_list(skills):
        text = _escape(skill)
        if text:
            badges.append(f'<li class="skill-tag">{text}</li>')
    return "\n".join(badges)


def _render_bullets(items):
    """
    Builds a <ul class="item-description"> bullet list fragment.

    Empty items are skipped; None/empty input produces an empty string.
    """
    bullets = []
    for item in normalize_list(items):
        text = _escape(item)
        if text:
            bullets.append(f"<li>{text}</li>")
    if not bullets:
        return ""
    lines = ['<ul class="item-description">']
    lines.extend(bullets)
    lines.append("</ul>")
    return "\n".join(lines)


def _render_education(education):
    """
    Builds the education cards fragment.

    Uses: institution, degree, field_of_study, start_date, end_date, gpa,
    location, highlights. Empty fields are omitted entirely.
    """
    if not education:
        return ""
    cards = []
    for edu in normalize_list(education):
        if not isinstance(edu, dict):
            continue
        lines = ['<article class="item-card education-card">']

        # Header: institution (title) + date range (right side).
        header = []
        institution = _escape(edu.get("institution"))
        date_str = _render_date_range(
            edu.get("start_date"),
            edu.get("end_date"),
        )
        if institution:
            header.append(f'<h3 class="item-title">{institution}</h3>')
        if date_str:
            header.append(f'<span class="item-date">{date_str}</span>')
        if header:
            lines.append('<div class="item-header">')
            lines.extend(header)
            lines.append("</div>")

        # Subtitle: degree + field of study.
        degree = _escape(edu.get("degree"))
        field = _escape(edu.get("field_of_study"))
        subtitle = ", ".join(part for part in (degree, field) if part)
        if subtitle:
            lines.append(f'<div class="item-subtitle">{subtitle}</div>')

        # Location.
        location = _escape(edu.get("location"))
        if location:
            lines.append(f'<p class="item-meta">{location}</p>')

        # GPA (only when present).
        gpa = _escape(edu.get("gpa"))
        if gpa:
            lines.append(f'<p class="item-meta">GPA: {gpa}</p>')

        # Highlights as a bullet list (only when present).
        highlights = list(normalize_list(edu.get("highlights")))
        bullets = _render_bullets(highlights)
        if bullets:
            lines.append(bullets)

        lines.append("</article>")
        cards.append("\n".join(lines))
    return "\n".join(cards)


def _render_experience(experience):
    """
    Builds the experience cards fragment.

    Uses: role, company, location, start_date, end_date, description,
    technologies. Empty fields are omitted.
    """
    if not experience:
        return ""
    cards = []
    for exp in normalize_list(experience):
        if not isinstance(exp, dict):
            continue
        lines = ['<article class="item-card experience-card">']

        # Header: role (title) + date range (right side).
        header = []
        role = _escape(exp.get("role"))
        date_str = _render_date_range(
            exp.get("start_date"),
            exp.get("end_date"),
        )
        if role:
            header.append(f'<h3 class="item-title">{role}</h3>')
        if date_str:
            header.append(f'<span class="item-date">{date_str}</span>')
        if header:
            lines.append('<div class="item-header">')
            lines.extend(header)
            lines.append("</div>")

        # Subtitle: company.
        company = _escape(exp.get("company"))
        if company:
            lines.append(f'<div class="item-subtitle">{company}</div>')

        # Location.
        location = _escape(exp.get("location"))
        if location:
            lines.append(f'<p class="item-meta">{location}</p>')

        # Description as a bullet list.
        bullets = _render_bullets(exp.get("description"))
        if bullets:
            lines.append(bullets)

        # Technologies badges (only when present).
        tech = _render_skills(exp.get("technologies"))
        if tech:
            lines.append('<ul class="skills-list">')
            lines.append(tech)
            lines.append("</ul>")

        lines.append("</article>")
        cards.append("\n".join(lines))
    return "\n".join(cards)


def _render_projects(projects):
    """
    Builds the project cards fragment.

    Uses: title, description (string OR list of strings), technologies
    (list OR comma-separated string), link, start_date, end_date. Links are
    only generated for safe http/https URLs and open in a new tab.
    """
    if not projects:
        return ""
    cards = []
    for proj in normalize_list(projects):
        if not isinstance(proj, dict):
            continue
        lines = ['<article class="project-card">']

        # Title (linked when a safe URL exists).
        title = _escape(proj.get("title"))
        link = proj.get("link")
        if _is_safe_url(link):
            link_escaped = _escape(link.strip())
            if title:
                lines.append(
                    f'<h3 class="project-title"><a href="{link_escaped}" '
                    'target="_blank" rel="noopener noreferrer">'
                    f"{title}</a></h3>"
                )
            else:
                lines.append(
                    f'<h3 class="project-title"><a href="{link_escaped}" '
                    'target="_blank" rel="noopener noreferrer">View Project</a></h3>'
                )
        elif title:
            lines.append(f'<h3 class="project-title">{title}</h3>')

        # Date (only when present).
        date_str = _render_date_range(
            proj.get("start_date"),
            proj.get("end_date"),
        )
        if date_str:
            lines.append(f'<span class="item-date">{date_str}</span>')

        # Description: string -> paragraph, list -> bullet list.
        description = proj.get("description")
        if isinstance(description, str) and description.strip():
            lines.append(f'<p class="project-desc">{_escape(description)}</p>')
        else:
            bullets = _render_bullets(description)
            if bullets:
                lines.append(bullets)

        # Technologies badges (only when present).
        tech = _render_skills(proj.get("technologies"))
        if tech:
            lines.append('<ul class="skills-list">')
            lines.append(tech)
            lines.append("</ul>")

        lines.append("</article>")
        cards.append("\n".join(lines))
    return "\n".join(cards)


def _render_achievements(achievements):
    """
    Builds the achievements list fragment (<li> items for the template's
    <ul class="achievements-list">).
    """
    items = []
    for achievement in normalize_list(achievements):
        text = _escape(achievement)
        if text:
            items.append(f"<li>{text}</li>")
    return "\n".join(items)


def _render_contact(contact):
    """
    Builds the contact details fragment.

    Uses: email, phone, location, links. Only present fields are shown.
    mailto:/tel: links are generated only for non-empty values; external
    links only for safe http/https URLs.
    """
    if not isinstance(contact, dict):
        return ""
    parts = []

    email = _escape(contact.get("email"))
    if email:
        parts.append(f'<span class="contact-item">Email: <a href="mailto:{email}">{email}</a></span>')

    phone = _escape(contact.get("phone"))
    if phone:
        parts.append(f'<span class="contact-item">Phone: <a href="tel:{phone}">{phone}</a></span>')

    location = _escape(contact.get("location"))
    if location:
        parts.append(f'<span class="contact-item">Location: {location}</span>')

    for link in normalize_list(contact.get("links")):
        if not isinstance(link, dict):
            continue
        url = link.get("url")
        if not _is_safe_url(url):
            continue  # Never emit a link for an unsafe URL.
        url_escaped = _escape(url.strip())
        platform = _escape(link.get("platform")) or url_escaped
        parts.append(
            f'<span class="contact-item"><a href="{url_escaped}" '
            'target="_blank" rel="noopener noreferrer">'
            f"{platform}</a></span>"
        )

    return "\n".join(parts)


def render_html(data, template_path="template.html", css_path="style.css"):
    """
    Renders the normalized resume data into a complete HTML document.

    Steps:
    1. Read template.html from disk (and style.css to verify it exists -
       the CSS stays a separate file referenced via <link>).
    2. Build HTML fragments for every portfolio section from the data.
    3. Remove entire section blocks that have no meaningful content
       (using the template's existing <!-- SECTION:X --> markers).
    4. Replace the template placeholders ({{NAME}}, {{SKILLS_CONTENT}}, ...).
    5. Verify that no known placeholders remain; error if any are left.

    Returns the complete HTML document as a string.
    """
    # 1. Read the template.
    try:
        with open(template_path, "r", encoding="utf-8") as file:
            template = file.read()
    except OSError as error:
        print(f"\nError: Could not read template file '{template_path}': {error}")
        sys.exit(1)

    # 2. Verify the stylesheet exists (it is referenced, not inlined).
    try:
        with open(css_path, "r", encoding="utf-8") as file:
            file.read()
    except OSError as error:
        print(f"\nError: Could not read stylesheet file '{css_path}': {error}")
        sys.exit(1)

    if not isinstance(data, dict):
        raise GeminiAPIError("HTML rendering error", "Normalized data is not a valid dictionary.")

    # 3. Build the section fragments.
    name = _escape(data.get("name"))
    headline = _escape(data.get("headline"))
    summary = _escape(data.get("summary"))
    skills = _render_skills(data.get("skills"))
    education = _render_education(data.get("education"))
    experience = _render_experience(data.get("experience"))
    projects = _render_projects(data.get("projects"))
    achievements = _render_achievements(data.get("achievements"))
    contact = _render_contact(data.get("contact"))

    # 4. Conditional sections: drop the whole section block (between its
    #    <!-- SECTION:X --> and <!-- END_SECTION:X --> markers) when it has
    #    no meaningful content.
    sections = {
        "CONTACT": contact,
        "SUMMARY": summary,
        "SKILLS": skills,
        "EXPERIENCE": experience,
        "EDUCATION": education,
        "PROJECTS": projects,
        "ACHIEVEMENTS": achievements,
    }
    for section_name, content in sections.items():
        if content:
            continue
        # Remove the whole block, including the standalone comment that labels
        # the section (e.g. <!-- Professional Summary Section -->) when present.
        pattern = re.compile(
            rf"(?:<!--[^>]*?Section\s*-->\s*)?"
            rf"<!--\s*SECTION:{section_name}\s*-->.*?"
            rf"<!--\s*END_SECTION:{section_name}\s*-->",
            re.DOTALL,
        )
        template = pattern.sub("", template)

    # 5. Replace the placeholders.
    html = template
    html = html.replace("{{NAME}}", name)
    html = html.replace("{{HEADLINE}}", headline)
    replacements = {
        "{{SUMMARY_CONTENT}}": summary,
        "{{SKILLS_CONTENT}}": skills,
        "{{EDUCATION_CONTENT}}": education,
        "{{EXPERIENCE_CONTENT}}": experience,
        "{{PROJECTS_CONTENT}}": projects,
        "{{ACHIEVEMENTS_CONTENT}}": achievements,
        "{{CONTACT_CONTENT}}": contact,
    }
    for placeholder, content in replacements.items():
        html = html.replace(placeholder, content)

    # 6. Safety check: no {{...}} placeholder tokens may remain.
    unresolved = sorted(set(re.findall(r"\{\{.*?\}\}", html)))
    if unresolved:
        raise GeminiAPIError(
            "HTML rendering error",
            f"Unresolved placeholders remain in the generated HTML: {', '.join(unresolved)}",
        )

    return html


def save_portfolio(html_content, output_path="portfolio.html"):
    """
    Writes the generated HTML document to portfolio.html (UTF-8).

    Handles file-writing errors gracefully and prints a success message.
    """
    try:
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(html_content)
    except OSError as error:
        print(f"\nError: Could not write portfolio file '{output_path}': {error}")
        sys.exit(1)
    print(f"\nPortfolio generated successfully: {output_path}")


def main():
    """
    Entry point for the full pipeline.

    1. Load the environment (Gemini API key).
    2. Read and clean resume.txt.
    3. Validate the resume.
    4. Send the resume to Gemini and get the raw JSON response.
    5. Parse and validate the Gemini JSON response.
    6. Normalize the JSON into the project's predictable schema.
    7. Grounding validation: remove any extracted fact not explicitly
       supported by resume.txt.
    8. Render portfolio.html from template.html + style.css.
    9. Save portfolio.html.

    IMPORTANT: Gemini's output is a draft and every generated claim MUST be
    verified against the original resume.txt before submission or use. Do not
    automatically assume Gemini is truthful or complete. Always cross-check
    structured data against the source document.
    """
    print("=" * 60)
    print(" AI-Assisted Resume Portfolio Generator ")
    print("=" * 60)

    try:
        # 1. Load the Gemini API key from .env.
        api_key = load_environment()

        # 2 & 3. Read, clean, and validate the resume file.
        resume_text = read_resume_file("resume.txt")
        print("\nResume loaded successfully.")
        print(f"Cleaned resume character count: {len(resume_text)} characters")

        # 4. Send the resume to Gemini and get the raw JSON response text.
        json_response = extract_resume_json(resume_text, api_key)
        print("\nGemini response received successfully.")

        # 5 & 6. Parse and normalize the Gemini JSON response.
        normalized_data = parse_and_validate_json(json_response)
        print("\nGemini JSON parsed and validated successfully.")

        # 7. Grounding validation: keep only facts explicitly supported by
        #    resume.txt. Unsupported values are removed before rendering so
        #    hallucinated information never reaches the portfolio.
        normalized_data, removed_counts = grounding_validate_resume(
            normalized_data, resume_text
        )
        print_grounding_validation(removed_counts)

        # Print the normalized JSON and summary for inspection.
        print("\n--- Normalized Resume Data ---")
        print(json.dumps(normalized_data, indent=2))
        print("-------------------------------")
        print("\n--- Normalization Summary ---")
        print(f"Education items: {len(normalized_data['education'])}")
        print(f"Experience items: {len(normalized_data['experience'])}")
        print(f"Project items: {len(normalized_data['projects'])}")
        print(f"Skills: {len(normalized_data['skills'])}")
        print(f"Achievements: {len(normalized_data['achievements'])}")
        print(f"Contact links: {len(normalized_data['contact']['links'])}")
        print("-------------------------------")

        # 7. Render the portfolio HTML from template.html + style.css.
        print("\nGenerating portfolio HTML...")
        html_content = render_html(normalized_data)

        # 8. Save portfolio.html.
        save_portfolio(html_content)
        return 0
    except KeyboardInterrupt:
        raise
    except GeminiAPIError as error:
        print(f"\nError: {error.detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
