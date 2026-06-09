"""Interview preparation helpers."""

from __future__ import annotations

from .keywords import extract_known_skills, important_terms


def generate_interview_questions(
    job_description: str,
    role: str = "IT Role",
    count: int = 8,
) -> dict[str, list[str]]:
    """Generate behavioral, technical, and mock interview prompts from a JD."""

    skills = extract_known_skills(job_description)[:8]
    keywords = important_terms(job_description, limit=8)

    technical = [
        f"How have you used {skill} in a production or project environment?"
        for skill in skills[:count]
    ]
    if len(technical) < count:
        technical.extend(
            [
                f"How would you approach a {role} task involving {keyword}?"
                for keyword in keywords[: count - len(technical)]
            ]
        )

    behavioral = [
        "Tell me about a time you had to learn a new technology quickly for a project.",
        "Describe a time you resolved a difficult production or delivery issue.",
        "Tell me about a time you worked with stakeholders to clarify ambiguous requirements.",
        "Describe a time you improved a process, system, or workflow.",
        "Tell me about a time you received feedback and changed your approach.",
    ][:count]

    mock = [
        f"Walk me through your background and why it fits this {role} role.",
        "Which requirement in this job description best matches your strongest experience?",
        "What is one gap you noticed in the job description, and how would you ramp up?",
        "What questions would you ask the hiring manager about success in this role?",
    ]

    return {
        "technical": technical[:count],
        "behavioral": behavioral,
        "mock_interview": mock,
    }


def evaluate_answer(question: str, answer: str, job_description: str = "") -> dict[str, object]:
    """Evaluate an interview answer with simple explainable heuristics."""

    answer_lower = answer.lower()
    skills = extract_known_skills(job_description)
    matched_skills = [skill for skill in skills if skill.lower() in answer_lower]
    star_markers = {
        "situation": any(word in answer_lower for word in ["situation", "context", "problem"]),
        "task": any(word in answer_lower for word in ["task", "goal", "responsibility"]),
        "action": any(word in answer_lower for word in ["action", "built", "implemented", "led", "created"]),
        "result": any(word in answer_lower for word in ["result", "impact", "improved", "reduced", "increased"]),
    }
    length_score = min(35, max(0, len(answer.split()) // 4))
    star_score = sum(10 for present in star_markers.values() if present)
    skill_score = min(25, len(matched_skills) * 5)
    score = min(100, length_score + star_score + skill_score)

    suggestions = []
    if not star_markers["situation"]:
        suggestions.append("Add brief situation/context.")
    if not star_markers["task"]:
        suggestions.append("Clarify your task or responsibility.")
    if not star_markers["action"]:
        suggestions.append("Describe specific actions you personally took.")
    if not star_markers["result"]:
        suggestions.append("End with measurable or observable results.")
    if skills and not matched_skills:
        suggestions.append("Mention relevant job-description skills where truthful.")

    return {
        "question": question,
        "score": score,
        "matched_skills": matched_skills,
        "star_markers": star_markers,
        "suggestions": suggestions,
    }
