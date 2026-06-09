from pathlib import Path
import tempfile
import unittest

from job_assistant.database import JobAssistantDB
from job_assistant.interview import evaluate_answer, generate_interview_questions
from job_assistant.optimizer import analyze_resume_text


class WebStackTests(unittest.TestCase):
    def test_database_auth_application_and_analytics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db = JobAssistantDB(Path(tmpdir) / "assistant.sqlite3")
            user = db.create_user("Test User", "test@example.com", "password123")
            self.assertEqual(user["email"], "test@example.com")

            authenticated = db.authenticate("test@example.com", "password123")
            self.assertIsNotNone(authenticated)
            assert authenticated is not None
            token = db.create_session(authenticated["id"])
            self.assertEqual(db.get_user_for_token(token)["email"], "test@example.com")

            application = db.create_application(
                user["id"],
                {
                    "role": "Data Engineer",
                    "title": "Data Engineer",
                    "company": "Example Analytics",
                    "url": "https://example.test/data",
                    "status": "applied",
                    "optimized_ats_score": 88,
                    "resume_version": "data-engineer-v1",
                },
            )
            self.assertEqual(application["status"], "applied")

            updated = db.update_application(
                user["id"],
                application["id"],
                {"status": "interviewing", "status_note": "Recruiter screen scheduled"},
            )
            self.assertEqual(updated["status"], "interviewing")

            analytics = db.analytics(user["id"])
            self.assertEqual(analytics["total_applications"], 1)
            self.assertEqual(analytics["by_status"]["interviewing"], 1)
            self.assertEqual(analytics["average_ats_score"], 88)

    def test_optimizer_returns_scores_and_missing_keywords(self) -> None:
        result = analyze_resume_text(
            resume_text="Python SQL ETL AWS analytics experience",
            job_description="Need Python, SQL, Airflow, Spark, AWS, and data warehouse experience.",
            role="Data Engineer",
        )

        self.assertIn("airflow", result["missing_skills"])
        self.assertGreaterEqual(result["optimized_ats_score"], result["original_ats_score"])
        self.assertTrue(result["tailored_summary"])

    def test_interview_helpers_generate_and_evaluate(self) -> None:
        questions = generate_interview_questions(
            "Backend role requiring Python, REST, SQL, Docker, and CI/CD.",
            role="Backend Developer",
        )
        self.assertTrue(questions["technical"])
        self.assertTrue(questions["behavioral"])

        evaluation = evaluate_answer(
            question="Tell me about a backend project.",
            answer=(
                "The situation involved a slow API. My task was improving reliability. "
                "I implemented Python REST API caching and SQL tuning, documented the rollout, "
                "and the result improved response time for users."
            ),
            job_description="Python REST SQL API role",
        )
        self.assertGreaterEqual(evaluation["score"], 60)
        self.assertIn("sql", evaluation["matched_skills"])


if __name__ == "__main__":
    unittest.main()
