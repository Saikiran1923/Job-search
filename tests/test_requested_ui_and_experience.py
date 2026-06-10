from pathlib import Path
import unittest

from job_assistant.ats_prediction import apply_approved_suggestions, predict_ats_score
from job_assistant.experience_library import group_points_by_employer, search_experience_points


class RequestedUiAndExperienceTests(unittest.TestCase):
    def test_login_required_ui_buttons_exist(self) -> None:
        html = Path("job_assistant/static/index.html").read_text(encoding="utf-8")

        self.assertIn("loginRequiredPanel", html)
        self.assertIn("Open Job Portal", html)
        self.assertIn("Continue After Login", html)
        self.assertIn("Paste JD Manually", html)

    def test_open_portal_and_continue_handlers_exist(self) -> None:
        script = Path("job_assistant/static/app.js").read_text(encoding="utf-8")

        self.assertIn("openJobPortalBtn", script)
        self.assertIn("window.open", script)
        self.assertIn("continueAfterLoginBtn", script)
        self.assertIn("requestSubmit", script)

    def test_manual_jd_section_is_visible(self) -> None:
        html = Path("job_assistant/static/index.html").read_text(encoding="utf-8")

        self.assertIn("Manual Job Description", html)
        self.assertIn("If extraction is blocked", html)
        self.assertIn("jdFileInput", html)

    def test_experience_point_library_lookup(self) -> None:
        matches = search_experience_points(["Data Integration"], role="data_engineer")

        self.assertIn("Data Integration", matches)
        self.assertTrue(matches["Data Integration"])
        self.assertEqual(matches["Data Integration"][0]["role_folder"], "data_engineer")
        self.assertIn("point", matches["Data Integration"][0])
        self.assertNotIn("employer", matches["Data Integration"][0])

    def test_employer_based_placement_grouping(self) -> None:
        points = [
            {
                "assigned_employer": "Employer A",
                "assigned_project": "Project One",
                "skill": "Data Integration",
                "point": "Built data integration pipelines.",
            },
            {
                "assigned_employer": "Employer B",
                "assigned_project": "Project Two",
                "skill": "Data Quality",
                "point": "Created validation checks.",
            },
        ]
        grouped = group_points_by_employer(points)

        self.assertIn("Employer A", grouped)
        self.assertIn("Employer B", grouped)
        self.assertNotIn("Built data integration pipelines.", [item["point"] for item in grouped["Employer B"]["Project Two"]])

    def test_allow_skip_and_assignment_workflow_ui_exists(self) -> None:
        script = Path("job_assistant/static/app.js").read_text(encoding="utf-8")

        self.assertIn("Allow Selected", script)
        self.assertIn("Skip", script)
        self.assertIn("renderEmployerAssignmentStep", script)
        self.assertIn("data-assignment-employer", script)
        self.assertIn("data-assignment-project", script)

    def test_recruiter_profile_page_fields_exist(self) -> None:
        html = Path("job_assistant/static/index.html").read_text(encoding="utf-8")
        script = Path("job_assistant/static/app.js").read_text(encoding="utf-8")

        self.assertIn("Direct Phone", html)
        self.assertIn("Mobile Number", html)
        self.assertIn("Office Number", html)
        self.assertIn("Recruiter Status", html)
        self.assertIn("recruiterDetails", html)
        self.assertIn("Linked Applications", script)

    def test_global_search_covers_applications_recruiters_and_resumes(self) -> None:
        script = Path("job_assistant/static/app.js").read_text(encoding="utf-8")

        self.assertIn("globalSearchInput", Path("job_assistant/static/index.html").read_text(encoding="utf-8"))
        self.assertIn("allApplications", script)
        self.assertIn("allRecruiters", script)
        self.assertIn("allResumes", script)
        self.assertIn("renderRecruiters(filteredRecruiters)", script)
        self.assertIn("renderResumeVersions(filteredResumes)", script)

    def test_ats_before_after_calculation_with_allowed_points(self) -> None:
        resume = "Summary Data analyst. Skills SQL. Experience supported reporting. Education BS."
        job = {
            "job_title": "Data Engineer",
            "full_job_description": "Required Data Integration, SQL, data migration, and data quality support.",
            "required_skills": ["data integration", "sql", "data migration"],
        }
        point = search_experience_points(["Data Integration"], role="data_engineer")["Data Integration"][0]
        before = predict_ats_score(resume, job)
        optimized = apply_approved_suggestions(
            resume,
            [{**point, "type": "experience_point", "assigned_employer": "Employer A", "assigned_project": "Project One"}],
        )
        after = predict_ats_score(optimized["optimized_resume"], job)

        self.assertGreaterEqual(after["score"], before["score"])
        self.assertIn("Employer A", optimized["optimized_resume"])
        self.assertIn("Project One", optimized["optimized_resume"])


if __name__ == "__main__":
    unittest.main()
