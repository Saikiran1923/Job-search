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


def _question(
    text: str,
    level: str,
    source: str,
    keywords: list[str],
    answer_hint: str,
    confidence: int,
) -> dict[str, object]:
    return {
        "question": text,
        "difficulty_level": level,
        "source": source,
        "suggested_answer": answer_hint,
        "keywords_to_include": keywords[:8],
        "confidence_score": confidence,
    }


def generate_interview_prep(
    optimized_resume: str,
    job_description: str,
    role: str = "IT Role",
) -> dict[str, list[dict[str, object]]]:
    """Generate Level 1 and Level 2 interview prep from resume and JD."""

    jd_skills = extract_known_skills(job_description)
    resume_skills = extract_known_skills(optimized_resume)
    shared = [skill for skill in jd_skills if skill in resume_skills]
    missing = [skill for skill in jd_skills if skill not in resume_skills]
    resume_terms = important_terms(optimized_resume, limit=10)
    jd_terms = important_terms(job_description, limit=12)

    level_1 = [
        _question(
            "Tell me about yourself and summarize why your background fits this role.",
            "Level 1",
            "Both",
            shared[:6] or resume_terms[:6],
            "Use a concise summary: current background, most relevant skills, and why the role is a strong fit.",
            88 if optimized_resume and job_description else 60,
        ),
        _question(
            f"Why are you interested in this {role} role?",
            "Level 1",
            "Job Description",
            jd_terms[:6],
            "Connect the company/role responsibilities to your experience and career direction.",
            82,
        ),
        _question(
            "Explain your most relevant experience for this job.",
            "Level 1",
            "Resume",
            shared[:6] or resume_terms[:6],
            "Pick one or two resume experiences and describe responsibilities, actions, and results.",
            84,
        ),
        _question(
            "Which basic skills from the job description have you used before?",
            "Level 1",
            "Both",
            shared[:8],
            "Name the skills truthfully and give short examples of how you used each one.",
            86 if shared else 65,
        ),
        _question(
            "Are you authorized and available to work according to this role's requirements?",
            "Level 1",
            "Job Description",
            ["work authorization", "availability"],
            "Answer directly and consistently with your saved application profile.",
            78,
        ),
    ]

    level_2: list[dict[str, object]] = []
    for skill in jd_skills[:8]:
        source = "Both" if skill in resume_skills else "Job Description"
        confidence = 86 if skill in resume_skills else 68
        level_2.append(
            _question(
                f"How would you apply {skill} to deliver one of the responsibilities in this role?",
                "Level 2",
                source,
                [skill, *jd_terms[:5]],
                "Explain a concrete project, design choice, troubleshooting step, or learning plan tied to the role.",
                confidence,
            )
        )
    for gap in missing[:4]:
        level_2.append(
            _question(
                f"The job mentions {gap}. How would you handle this if it is a weaker area?",
                "Level 2",
                "Job Description",
                [gap, "learning plan", "transferable experience"],
                "Be honest about depth, connect transferable skills, and describe a clear ramp-up plan.",
                72,
            )
        )

    return {"level_1": level_1, "level_2": level_2[:12]}


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
