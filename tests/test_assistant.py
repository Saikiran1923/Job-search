from pathlib import Path
import tempfile
import unittest

from job_assistant.ats import score_job
from job_assistant.models import CandidateProfile, JobPosting, RoleLibrary
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


if __name__ == "__main__":
    unittest.main()
