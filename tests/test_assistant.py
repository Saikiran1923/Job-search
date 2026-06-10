from pathlib import Path
import tempfile
import unittest

from job_assistant.answers import AnswerBank
from job_assistant.ats import score_job
from job_assistant.models import CandidateProfile, JobPosting, RoleLibrary
from job_assistant.search import build_search_plan
from job_assistant.storage import ApplicationStore, application_key


class AssistantTests(unittest.TestCase):
    def test_score_job_selects_relevant_bullets(self) -> None:
        profile = CandidateProfile.from_path(Path("data/candidate_profile.example.json"))
        job = JobPosting.from_dict(
            {
                "role": "Data Engineer",
                "title": "Data Engineer",
                "company": "Example Analytics",
                "url": "https://example.test/job",
                "description": "Need SQL, Python, ETL, Airflow, Spark, AWS, and data warehouse experience.",
            }
        )
        library = RoleLibrary.from_path(Path("data/roles/data_engineer.json"), "Data Engineer")

        analysis = score_job(profile, job, library, threshold=85)

        self.assertGreaterEqual(analysis.ats_score, 70)
        self.assertIn("sql", analysis.matched_skills)
        self.assertIn("airflow", analysis.missing_skills)
        self.assertTrue(any("ETL" in bullet or "data" in bullet for bullet in analysis.selected_bullets))
        self.assertLessEqual(analysis.original_ats_score, analysis.optimized_ats_score)

    def test_duplicate_key_blocks_same_company_and_role(self) -> None:
        first = JobPosting.from_dict(
            {
                "role": "Backend Developer",
                "title": "Backend Developer",
                "company": "Example Software",
                "url": "https://example.test/job-1",
                "description": "Build REST APIs with Python and SQL.",
            }
        )
        second = JobPosting.from_dict(
            {
                "role": "Backend Developer",
                "title": "Backend Engineer",
                "company": "Example Software",
                "url": "https://example.test/job-2",
                "description": "Build REST APIs with Python and SQL.",
            }
        )

        self.assertEqual(application_key(first), application_key(second))
        self.assertNotEqual(
            application_key(first, allow_reposts=True),
            application_key(second, allow_reposts=True),
        )

    def test_store_reads_empty_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ApplicationStore(Path(tmpdir) / "applications.jsonl")
            self.assertEqual(store.summary(), {})

    def test_answer_bank_matches_question_options(self) -> None:
        bank = AnswerBank(Path("data/application_answers.example.json"))

        match = bank.match(
            "Do you require visa sponsorship now or in the future?",
            ["Yes", "No"],
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.answer, "No")

    def test_search_plan_is_portal_ordered(self) -> None:
        plan = build_search_plan(
            roles=["Data Engineer", "Backend Developer"],
            platforms=["linkedin", "indeed"],
            location="Remote",
        )

        self.assertEqual(plan[0]["platform"], "linkedin")
        self.assertEqual(plan[1]["platform"], "linkedin")
        self.assertEqual(plan[2]["platform"], "indeed")
        self.assertEqual(plan[0]["minimum_manual_review_seconds"], 180)


if __name__ == "__main__":
    unittest.main()
