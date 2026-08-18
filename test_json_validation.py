"""
Temporary diagnostic test: parse_and_validate_json() robustness check.

This file is for diagnosis only and does not modify any project files.

Goal: demonstrate that malformed or incomplete Gemini responses do NOT
crash the application. For each test case we call parse_and_validate_json()
from main.py, catch any application-level error, and report whether the
function handled the case safely.

The API key is never loaded or printed in this test.
"""

import json

import main as resume_main  # alias so our own main() below does not shadow the module


def run_case(name, raw_input):
    """
    Runs one diagnostic case.

    Calls parse_and_validate_json() with the given raw input, catches the
    expected application-level GeminiAPIError (or any unexpected exception),
    and prints whether the function handled the case safely - without ever
    printing a traceback.
    """
    print("=" * 60)
    print(f"Test case: {name}")
    print("-" * 60)
    print(f"Input: {raw_input!r}")

    try:
        result = resume_main.parse_and_validate_json(raw_input)

        # The call succeeded: the function either normalized the data or
        # filled in safe empty defaults. Verify the result is usable.
        is_dict = isinstance(result, dict)
        print(f"Result type: {type(result).__name__}")
        if is_dict:
            print(f"Normalized keys: {len(result)} top-level fields")
            print(f"  name:       {result.get('name')!r}")
            print(f"  skills:     {result.get('skills')!r}")
            print(f"  education:  {result.get('education')!r}")
            print(f"  experience: {result.get('experience')!r}")
            print(f"  projects:   {result.get('projects')!r}")
            print(f"  contact:    {result.get('contact')!r}")

        if is_dict:
            print("Result: SAFE - handled without crashing, returned a normalized dictionary.")
            return True
        print("Result: SAFE - handled without crashing (unexpected but non-fatal root type).")
        return True

    except resume_main.GeminiAPIError as error:
        # Expected path: a clear application-level error, not a crash.
        print(f"Handled as application error: {error.detail}")
        print("Result: SAFE - rejected gracefully with a clear error, no traceback.")
        return True

    except Exception as error:
        # Unexpected: report it, but still WITHOUT printing a traceback.
        print(f"UNEXPECTED exception type: {type(error).__name__}")
        print(f"Unexpected error message: {error}")
        print("Result: UNSAFE - this case crashed with an uncontrolled exception.")
        return False


def main():
    """Runs all diagnostic cases and prints a summary."""
    print("Diagnostic: parse_and_validate_json() robustness check")
    print("This test never loads or prints an API key.")
    print()

    cases = [
        ("1. Completely invalid JSON", "This is not JSON"),
        ("2. Valid JSON but wrong root type", "[]"),
        ("3. Valid incomplete JSON", json.dumps({"name": "Test User"})),
        ("4. Valid JSON with null values", json.dumps({"name": None, "skills": None, "contact": None})),
    ]

    all_safe = True
    for name, raw_input in cases:
        safe = run_case(name, raw_input)
        all_safe = all_safe and safe
        print()

    print("=" * 60)
    if all_safe:
        print("SUMMARY: All cases handled safely - malformed or incomplete")
        print("Gemini responses do not crash the application.")
    else:
        print("SUMMARY: One or more cases did NOT handle safely.")
    print("=" * 60)

    return 0 if all_safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
