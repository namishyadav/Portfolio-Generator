"""
Temporary diagnostic test for grounding validation.

Tests grounding_validate_resume() from main.py directly using artificial
resume text. Does NOT call the Gemini API and never touches the API key.

Verifies that:
- Unsupported extracted facts (skills, technologies, companies, URLs) are removed.
- Supported extracted facts are preserved.
"""

import sys

import main as resume_main

PASSED = 0
FAILED = 0


def check(description, condition):
    """Records a pass/fail and prints the result."""
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS: {description}")
    else:
        FAILED += 1
        print(f"  FAIL: {description}")


def build_data(skills=None, experience=None, projects=None, contact=None):
    """Builds a minimal normalized-schema dict for testing."""
    return {
        "name": "",
        "headline": "",
        "summary": "",
        "skills": skills if skills is not None else [],
        "education": [],
        "experience": experience if experience is not None else [],
        "projects": projects if projects is not None else [],
        "achievements": [],
        "contact": contact
        if contact is not None
        else {"email": "", "phone": "", "location": "", "links": []},
    }


def case1_unsupported_skill_removed():
    print("\nCASE 1: Unsupported skill removed")
    resume = "Skills: Python, Git, HTML"
    data = build_data(skills=["Python", "Git", "HTML", "Docker"])
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("Docker removed", "Docker" not in filtered["skills"])
    check("Python/Git/HTML preserved", filtered["skills"] == ["Python", "Git", "HTML"])
    check("removed count is 1", removed["skills"] == 1)


def case2_supported_company_preserved():
    print("\nCASE 2: Supported company preserved")
    resume = "Worked at ABC Technologies."
    data = build_data(
        experience=[
            {
                "company": "ABC Technologies",
                "role": "Engineer",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": [],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "ABC Technologies preserved",
        filtered["experience"][0]["company"] == "ABC Technologies",
    )
    check("removed count is 0", removed["companies"] == 0)


def case3_unsupported_company_removed():
    print("\nCASE 3: Unsupported company removed")
    resume = "Worked at ABC Technologies."
    data = build_data(
        experience=[
            {
                "company": "Google",
                "role": "Engineer",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": [],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("Google removed", filtered["experience"][0]["company"] == "")
    check("removed count is 1", removed["companies"] == 1)


def case4_supported_url_preserved():
    print("\nCASE 4: Supported URL preserved")
    resume = "GitHub: https://github.com/testuser"
    data = build_data(
        contact={
            "email": "",
            "phone": "",
            "location": "",
            "links": [{"platform": "GitHub", "url": "https://github.com/testuser"}],
        }
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "URL preserved",
        filtered["contact"]["links"]
        == [{"platform": "GitHub", "url": "https://github.com/testuser"}],
    )
    check("removed count is 0", removed["contact"] == 0)


def case5_unsupported_url_removed():
    print("\nCASE 5: Unsupported URL removed")
    resume = "GitHub: https://github.com/testuser"
    data = build_data(
        contact={
            "email": "",
            "phone": "",
            "location": "",
            "links": [{"platform": "GitHub", "url": "https://github.com/fakeuser"}],
        }
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("fake URL removed", filtered["contact"]["links"] == [])
    check("removed count is 1", removed["contact"] == 1)


def case6_unsupported_technology_removed():
    print("\nCASE 6: Unsupported technology removed")
    resume = "Python and Git were used in the project."
    data = build_data(
        projects=[
            {
                "title": "Sample Project",
                "description": [],
                "technologies": ["Python", "Git", "Docker"],
                "link": "",
                "start_date": "",
                "end_date": "",
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "Docker removed",
        "Docker" not in filtered["projects"][0]["technologies"],
    )
    check(
        "Python/Git preserved",
        filtered["projects"][0]["technologies"] == ["Python", "Git"],
    )
    check("removed count is 1", removed["technologies"] == 1)


def case7_related_skill_not_accepted():
    print("\nCASE 7: Semantically related skills are NOT accepted")
    resume = "Skills: Python, Git"
    data = build_data(skills=["Python", "Python Developer", "GitHub"])
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("only Python survives", filtered["skills"] == ["Python"])
    check(
        "Python Developer rejected (not equivalent to Python)",
        "Python Developer" not in filtered["skills"],
    )
    check(
        "GitHub rejected (not equivalent to Git)",
        "GitHub" not in filtered["skills"],
    )
    check("removed count is 2", removed["skills"] == 2)


def case8_related_company_rejected():
    print("\nCASE 8: Only the exact supported company survives")
    resume = "Worked at ABC Technologies."
    data = build_data(
        experience=[
            {
                "company": company,
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": [],
            }
            for company in ["ABC Technologies", "ABC Technology Solutions", "Google"]
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    companies = [item["company"] for item in filtered["experience"]]
    check(
        "ABC Technologies preserved, others blanked",
        companies == ["ABC Technologies", "", ""],
    )
    check("removed count is 2", removed["companies"] == 2)


def case9_related_project_title_rejected():
    print("\nCASE 9: Only the exact supported project title survives")
    resume = "Project: Smart Study Planner"
    data = build_data(
        projects=[
            {
                "title": title,
                "description": [],
                "technologies": [],
                "link": "",
                "start_date": "",
                "end_date": "",
            }
            for title in ["Smart Study Planner", "Smart Study Manager"]
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    titles = [item["title"] for item in filtered["projects"]]
    check(
        "Smart Study Planner preserved, Manager blanked",
        titles == ["Smart Study Planner", ""],
    )
    check("removed count is 1", removed["projects"] == 1)


def case10_related_location_rejected():
    print("\nCASE 10: Only the exact supported location survives")
    resume = "Location: Delhi, India"
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": location,
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": [],
            }
            for location in ["Delhi, India", "Mumbai, India"]
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    locations = [item["location"] for item in filtered["experience"]]
    check(
        "Delhi, India preserved, Mumbai blanked",
        locations == ["Delhi, India", ""],
    )
    check("removed count is 1", removed["locations"] == 1)


def case11_supported_email_preserved():
    print("\nCASE 11: Supported email preserved")
    resume = "Email: student@example.com"
    data = build_data(
        contact={"email": "student@example.com", "phone": "", "location": "", "links": []}
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("email preserved", filtered["contact"]["email"] == "student@example.com")
    check("removed count is 0", removed["contact"] == 0)


def case12_unsupported_email_removed():
    print("\nCASE 12: Unsupported email removed")
    resume = "Email: student@example.com"
    data = build_data(
        contact={"email": "alex@example.com", "phone": "", "location": "", "links": []}
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("email removed", filtered["contact"]["email"] == "")
    check("removed count is 1", removed["contact"] == 1)


def case13_unsupported_technology_removed_from_list():
    print("\nCASE 13: Unsupported technology removed from a longer list")
    resume = "Python, Git and HTML were used."
    data = build_data(
        projects=[
            {
                "title": "",
                "description": [],
                "technologies": ["Python", "Git", "HTML", "Java"],
                "link": "",
                "start_date": "",
                "end_date": "",
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "Java removed, Python/Git/HTML preserved",
        filtered["projects"][0]["technologies"] == ["Python", "Git", "HTML"],
    )
    check("removed count is 1", removed["technologies"] == 1)


def case14_supported_url_preserved():
    print("\nCASE 14: Supported URL preserved")
    resume = "GitHub: https://github.com/student"
    data = build_data(
        contact={
            "email": "",
            "phone": "",
            "location": "",
            "links": [{"platform": "GitHub", "url": "https://github.com/student"}],
        }
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "URL preserved",
        filtered["contact"]["links"]
        == [{"platform": "GitHub", "url": "https://github.com/student"}],
    )
    check("removed count is 0", removed["contact"] == 0)


def case15_unsupported_url_removed():
    print("\nCASE 15: Unsupported URL removed")
    resume = "GitHub: https://github.com/student"
    data = build_data(
        contact={
            "email": "",
            "phone": "",
            "location": "",
            "links": [{"platform": "GitHub", "url": "https://github.com/another-user"}],
        }
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("URL removed", filtered["contact"]["links"] == [])
    check("removed count is 1", removed["contact"] == 1)


def case16_case_insensitive_matching():
    print("\nCASE 16: Case-insensitive matching preserves values")
    resume = "Skills: Python, Git"
    data = build_data(skills=["python", "GIT"])
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("both preserved (original casing kept)", filtered["skills"] == ["python", "GIT"])
    check("removed count is 0", removed["skills"] == 0)


def case18_inferred_technology_rejected():
    print("\nCASE 18: Inferred technology rejected")
    resume = "Built a dashboard in Python."
    data = build_data(
        projects=[
            {
                "title": "",
                "description": [],
                "technologies": ["Python", "Data Analysis"],
                "link": "",
                "start_date": "",
                "end_date": "",
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "Data Analysis rejected (not in resume)",
        filtered["projects"][0]["technologies"] == ["Python"],
    )
    check("removed count is 1", removed["technologies"] == 1)


def case19_generalized_technology_rejected():
    print("\nCASE 19: Generalized technology rejected even when the phrase is in prose")
    resume = "Using Git and Agile methodologies to deliver weekly sprints."
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": ["Git", "Agile methodologies"],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "Agile methodologies rejected (prose phrase, not an enumerated skill)",
        filtered["experience"][0]["technologies"] == ["Git"],
    )
    check("removed count is 1", removed["technologies"] == 1)


def case20_paraphrased_technology_rejected():
    print("\nCASE 20: Paraphrased technology rejected")
    resume = "Worked with the React library for frontend."
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": ["React", "React Library"],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "React Library rejected (paraphrase of 'the React library')",
        filtered["experience"][0]["technologies"] == ["React"],
    )
    check("removed count is 1", removed["technologies"] == 1)


def case21_exact_technology_preserved():
    print("\nCASE 21: Exact technology preserved")
    resume = "Skills: Python, Git"
    data = build_data(skills=["Python", "Git"])
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("both preserved", filtered["skills"] == ["Python", "Git"])
    check("removed count is 0", removed["skills"] == 0)


def case22_case_insensitive_exact_technology_preserved():
    print("\nCASE 22: Case-insensitive exact technology preserved")
    resume = "Skills: Python, Git"
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": ["python", "GIT"],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "both preserved (original casing kept)",
        filtered["experience"][0]["technologies"] == ["python", "GIT"],
    )
    check("removed count is 0", removed["technologies"] == 0)


def case23_whitespace_normalized_technology_preserved():
    print("\nCASE 23: Whitespace-normalized exact technology preserved")
    resume = "Skills: Python, Git"
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": ["  Python  ", "Git"],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "both preserved after trimming",
        filtered["experience"][0]["technologies"] == ["Python", "Git"],
    )
    check("removed count is 0", removed["technologies"] == 0)


def case24_listed_multiword_technology_preserved():
    print("\nCASE 24: Enumerated multi-word technology preserved (no over-filtering)")
    resume = "Skills: Data Structures, Object-Oriented Programming"
    data = build_data(
        experience=[
            {
                "company": "",
                "role": "",
                "location": "",
                "start_date": "",
                "end_date": "",
                "description": [],
                "technologies": ["Object-Oriented Programming"],
            }
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check(
        "Object-Oriented Programming preserved (comma-listed in resume)",
        filtered["experience"][0]["technologies"] == ["Object-Oriented Programming"],
    )
    check("removed count is 0", removed["technologies"] == 0)


def case17_whitespace_normalization():
    print("\nCASE 17: Whitespace normalization preserves values")
    resume = "Skills: Python, Git"
    data = build_data(skills=["  Python  ", "Git"])
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    check("both preserved after trimming", filtered["skills"] == ["Python", "Git"])
    check("removed count is 0", removed["skills"] == 0)


def case25_real_resume_enumerated_only():
    print("\nCASE 25: Real resume.txt - only explicitly enumerated skills survive")
    with open("resume.txt", "r", encoding="utf-8") as file:
        resume = file.read()
    data = build_data(
        skills=[
            # Explicitly enumerated in resume.txt SKILLS section (must survive).
            "Python", "Git", "Docker Basics", "Data Structures", "REST APIs",
            # Prose phrases embedded in resume sentences (must be rejected).
            "modern web technologies", "Agile methodologies",
            # Hallucinations (must be rejected).
            "Machine Learning", "React",
        ]
    )
    filtered, removed = resume_main.grounding_validate_resume(data, resume)
    surviving = filtered["skills"]
    check(
        "enumerated skills preserved",
        surviving == ["Python", "Git", "Docker Basics", "Data Structures", "REST APIs"],
    )
    check(
        "prose phrases rejected (modern web technologies / Agile methodologies)",
        "modern web technologies" not in surviving and "Agile methodologies" not in surviving,
    )
    check(
        "hallucinations rejected (Machine Learning / React)",
        "Machine Learning" not in surviving and "React" not in surviving,
    )
    check("removed count is 4", removed["skills"] == 4)


def main():
    """Runs every grounding validation case and prints a summary."""
    print("Grounding validation tests (no Gemini API calls)")
    case1_unsupported_skill_removed()
    case2_supported_company_preserved()
    case3_unsupported_company_removed()
    case4_supported_url_preserved()
    case5_unsupported_url_removed()
    case6_unsupported_technology_removed()
    case7_related_skill_not_accepted()
    case8_related_company_rejected()
    case9_related_project_title_rejected()
    case10_related_location_rejected()
    case11_supported_email_preserved()
    case12_unsupported_email_removed()
    case13_unsupported_technology_removed_from_list()
    case14_supported_url_preserved()
    case15_unsupported_url_removed()
    case16_case_insensitive_matching()
    case17_whitespace_normalization()
    case18_inferred_technology_rejected()
    case19_generalized_technology_rejected()
    case20_paraphrased_technology_rejected()
    case21_exact_technology_preserved()
    case22_case_insensitive_exact_technology_preserved()
    case23_whitespace_normalized_technology_preserved()
    case24_listed_multiword_technology_preserved()
    case25_real_resume_enumerated_only()

    print("\n============================================")
    print(f"Total passed: {PASSED}")
    print(f"Total failed: {FAILED}")
    print("============================================")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
