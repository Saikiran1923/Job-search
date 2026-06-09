from pathlib import Path
import tempfile
import unittest

from job_assistant.ats_prediction import (
    apply_approved_suggestions,
    generate_resume_suggestions,
    predict_ats_score,
)
from job_assistant.database import JobAssistantDB
from job_assistant.interview import generate_interview_prep
from job_assistant.job_extractor import FALLBACK_MESSAGE, extract_job_from_url


JOB_DETAILS = {
    "job_title": "Data Engineer",
    "company_name": "Example Analytics",
    "job_url": "https://example.test/data-engineer",
    "full_job_description": (
        "Required Python, SQL, Airflow, Spark, AWS, ETL, data warehouse, and data quality. "
        "Responsibilities include building pipelines, improving reliability, and partnering with analysts."
    ),
    "required_skills": ["python", "sql", "airflow", "spark", "aws", "etl", "data warehouse"],
    "preferred_skills": ["data quality"],
}

RESUME = """
# Candidate
## Summary
Data professional with Python and SQL experience.
## Skills
Python, SQL, ETL
## Experience
- Built reports and data workflows for analytics teams.
## Education
BS Computer Science
"""


class FinalWorkflowTests(unittest.TestCase):
    def test_full_job_url_extraction_fallback(self) -> None:
        result = extract_job_from_url(
            "https://example.test/protected",
            fetcher=lambda _: "<html><body>Please enable JavaScript and verify you are human CAPTCHA</body></html>",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["message"], FALLBACK_MESSAGE)

    def test_ats_before_and_after_score(self) -> None:
        before = predict_ats_score(RESUME, JOB_DETAILS)
        suggestions = generate_resume_suggestions(RESUME, JOB_DETAILS)
        optimized = apply_approved_suggestions(RESUME, suggestions)
        after = predict_ats_score(optimized["optimized_resume"], JOB_DETAILS)

        self.assertEqual(before["label"], "ATS Prediction Score")
        self.assertGreaterEqual(after["score"], before["score"])
        self.assertIn("airflow", before["missing_keywords"])

    def test_resume_version_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = JobAssistantDB(Path(tmpdir) / "assistant.sqlite3")
            user = db.create_user("Test User", "version@example.com", "password123")
            version = db.create_resume_version(
                user["id"],
                {
                    "original_resume": RESUME,
                    "optimized_resume": RESUME + "\nAirflow Spark AWS",
                    "job_title": "Data Engineer",
                    "company": "Example Analytics",
                    "job_url": JOB_DETAILS["job_url"],
                    "ats_before": 55,
                    "ats_after": 88,
                    "keywords_added": ["airflow", "spark", "aws"],
                },
            )

            self.assertEqual(version["version_number"], 1)
            self.assertEqual(version["ats_before"], 55)
            self.assertEqual(version["ats_after"], 88)
            self.assertIn("airflow", version["keywords_added"])

    def test_unanswered_question_saving_and_answer_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = JobAssistantDB(Path(tmpdir) / "assistant.sqlite3")
            user = db.create_user("Test User", "questions@example.com", "password123")
            saved = db.save_unanswered_questions(
                user["id"],
                [{"question": "Will you now or in the future require sponsorship?", "options": ["Yes", "No"]}],
                company_name="Example Analytics",
                job_title="Data Engineer",
                job_url=JOB_DETAILS["job_url"],
            )
            self.assertEqual(saved[0]["status"], "unanswered")

            answered = db.answer_question(user["id"], saved[0]["id"], "No")
            self.assertEqual(answered["status"], "answered")

            reused = db.find_answer_for_question(
                user["id"],
                "Do you require visa sponsorship now or in the future?",
            )
            self.assertIsNotNone(reused)
            assert reused is not None
            self.assertEqual(reused["answer"], "No")

    def test_level_1_and_level_2_interview_question_generation(self) -> None:
        questions = generate_interview_prep(
            optimized_resume=RESUME + "\nAirflow Spark AWS data warehouse project experience.",
            job_description=JOB_DETAILS["full_job_description"],
            role="Data Engineer",
        )

        self.assertTrue(questions["level_1"])
        self.assertTrue(questions["level_2"])
        self.assertEqual(questions["level_1"][0]["difficulty_level"], "Level 1")
        self.assertEqual(questions["level_2"][0]["difficulty_level"], "Level 2")
        self.assertIn("suggested_answer", questions["level_1"][0])


if __name__ == "__main__":
    unittest.main()
