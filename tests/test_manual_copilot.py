from pathlib import Path
import tempfile
import unittest

from job_assistant.ats_prediction import apply_approved_suggestions, generate_resume_suggestions, predict_ats_score
from job_assistant.autofill import build_application_assist
from job_assistant.copilot import job_details_from_manual_jd, run_manual_pipeline, validate_job_details
from job_assistant.database import JobAssistantDB
from job_assistant.interview import generate_interview_prep
from job_assistant.job_extractor import extract_job_from_url
from job_assistant.portal_sessions import detect_portal
from job_assistant.resume_parser import parse_resume_upload


RESUME = """
## Summary
Data Engineer with Python SQL ETL experience.
## Skills
Python, SQL, ETL
## Experience
- Built analytics pipelines and improved data quality for reporting teams.
## Education
BS Computer Science
"""

JD = """
Data Engineer
Responsibilities:
- Build reliable data pipelines and partner with analysts.
Required Qualifications:
- Python, SQL, Airflow, Spark, AWS, ETL, data warehouse, and data quality experience.
Preferred Qualifications:
- Dashboarding and stakeholder communication.
Application Questions:
Are you legally authorized to work in the United States?
Will you require sponsorship now or in the future?
"""


class ManualCopilotTests(unittest.TestCase):
    def _db_user(self) -> tuple[JobAssistantDB, int, tempfile.TemporaryDirectory]:
        tmpdir = tempfile.TemporaryDirectory()
        db = JobAssistantDB(Path(tmpdir.name) / "assistant.sqlite3")
        user = db.create_user("Test User", "copilot@example.com", "password123")
        return db, user["id"], tmpdir

    def test_profile_save_update_and_application_fields_ready(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)

        profile = db.save_profile(
            user_id,
            {
                "first_name": "Sai",
                "last_name": "Kiran",
                "email": "sai@example.com",
                "phone": "555",
                "city": "Dallas",
                "skills": "Python, SQL",
                "work_authorization": "Authorized",
            },
        )
        updated = db.save_profile(user_id, {**profile, "phone": "777"})

        self.assertEqual(updated["phone"], "777")
        self.assertGreaterEqual(db.profile_fields_ready_count(user_id), 6)

    def test_resume_upload_and_parsing(self) -> None:
        parsed = parse_resume_upload("resume.txt", content_text=RESUME)
        self.assertEqual(parsed["file_type"], "TXT")
        self.assertIn("Python", parsed["resume_text"])

        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)
        upload = db.create_resume_upload(
            user_id,
            {"original_file_name": "resume.txt", "file_type": "TXT", "resume_text": parsed["resume_text"]},
        )
        self.assertEqual(upload["version_number"], 1)

    def test_portal_session_status(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)

        self.assertEqual(detect_portal("https://www.linkedin.com/jobs/view/1"), "LinkedIn")
        session = db.upsert_portal_session(user_id, "LinkedIn", "Logged in")

        self.assertEqual(session["status"], "Logged in")
        self.assertTrue(any(item["portal"] == "LinkedIn" for item in db.list_portal_sessions(user_id)))

    def test_linkedin_login_page_and_invalid_page_rejection(self) -> None:
        login = extract_job_from_url(
            "https://linkedin.com/jobs/view/1",
            fetcher=lambda _: "<html><title>LinkedIn Login</title><body>Sign in Forgot password Join now</body></html>",
        )
        self.assertFalse(login["success"])

        invalid = {"job_title": "Sign In", "full_job_description": "Forgot password login join now"}
        self.assertFalse(validate_job_details(invalid)[0])

    def test_valid_jd_pipeline_auto_run_and_tracker_creation(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)
        job = job_details_from_manual_jd(JD, job_url="https://example.com/job", job_title="Data Engineer", company_name="Example")
        run = run_manual_pipeline(db, user_id, job, RESUME)

        self.assertEqual(run["statuses"]["ATS Before Score"], "Completed")
        self.assertEqual(run["statuses"]["Save Tracker"], "Completed")
        apps = db.list_applications(user_id)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["company"], "Example")
        self.assertGreater(apps[0]["interview_questions_generated"], 0)

    def test_ats_before_after_and_resume_version_creation(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)
        job = job_details_from_manual_jd(JD, job_title="Data Engineer", company_name="Example")
        before = predict_ats_score(RESUME, job)
        suggestions = generate_resume_suggestions(RESUME, job)
        optimized = apply_approved_suggestions(RESUME, suggestions)
        after = predict_ats_score(optimized["optimized_resume"], job)
        version = db.create_resume_version(
            user_id,
            {
                "original_resume": RESUME,
                "optimized_resume": optimized["optimized_resume"],
                "job_title": "Data Engineer",
                "company": "Example",
                "ats_before": before["score"],
                "ats_after": after["score"],
                "keywords_added": optimized["keywords_added"],
            },
        )

        self.assertGreaterEqual(after["score"], before["score"])
        self.assertEqual(version["version_number"], 1)

    def test_unanswered_question_delete_and_answered_reuse(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)
        saved = db.save_unanswered_questions(user_id, [{"question": "Will you require sponsorship?", "options": ["Yes", "No"]}])
        self.assertEqual(saved[0]["status"], "unanswered")
        self.assertTrue(db.delete_question(user_id, saved[0]["id"]))
        self.assertEqual(db.list_questions(user_id, status="unanswered"), [])

        answered = db.save_unanswered_questions(user_id, [{"question": "Are you authorized to work?", "options": ["Yes", "No"]}])[0]
        db.answer_question(user_id, answered["id"], "Yes")
        reused = db.find_answer_for_question(user_id, "Are you legally authorized to work in the United States?")
        self.assertIsNotNone(reused)
        assert reused is not None
        self.assertEqual(reused["answer"], "Yes")

    def test_level_1_level_2_and_application_assist(self) -> None:
        db, user_id, tmpdir = self._db_user()
        self.addCleanup(tmpdir.cleanup)
        db.save_profile(
            user_id,
            {
                "first_name": "Sai",
                "last_name": "Kiran",
                "email": "sai@example.com",
                "phone": "555",
                "work_authorization": "Authorized",
                "sponsorship_required": "No",
            },
        )
        questions = generate_interview_prep(RESUME, JD, role="Data Engineer")
        assist = build_application_assist(
            db.get_profile(user_id),
            [{"question": "Are you authorized to work?", "options": ["Yes", "No"]}],
            {"Are you authorized to work?": "Yes"},
        )

        self.assertTrue(questions["level_1"])
        self.assertTrue(questions["level_2"])
        self.assertIn("email", assist["profile_fields_ready"])
        self.assertEqual(len(assist["saved_answers_found"]), 1)


if __name__ == "__main__":
    unittest.main()
