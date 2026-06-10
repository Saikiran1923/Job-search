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
        self.assertIn("If the portal blocks extraction", html)
        self.assertIn("jdFileInput", html)

    def test_experience_point_library_lookup(self) -> None:
        matches = search_experience_points(["SAP IDocs"])

        self.assertIn("SAP IDocs", matches)
        employers = {point["employer"] for point in matches["SAP IDocs"]}
        self.assertIn("Jack Wolfskin", employers)
        self.assertIn("Topgolf Callaway", employers)

    def test_employer_based_placement_grouping(self) -> None:
        points = [
            {
                "employer": "Jack Wolfskin",
                "project": "SAP S/4HANA Integration",
                "skill": "SAP IDocs",
                "point": "Supported IDocs.",
            },
            {
                "employer": "Topgolf Callaway",
                "project": "Master Data Interface Support",
                "skill": "SAP IDocs",
                "point": "Resolved SAP interface failures.",
            },
        ]
        grouped = group_points_by_employer(points)

        self.assertIn("Jack Wolfskin", grouped)
        self.assertIn("Topgolf Callaway", grouped)
        self.assertNotIn("Supported IDocs.", [item["point"] for item in grouped["Topgolf Callaway"]["Master Data Interface Support"]])

    def test_ats_before_after_calculation_with_allowed_points(self) -> None:
        resume = "Summary Data analyst. Skills SQL. Experience supported reporting. Education BS."
        job = {
            "job_title": "SAP Data Analyst",
            "full_job_description": "Required SAP IDocs, SQL, data migration, and SAP interface support.",
            "required_skills": ["sap idocs", "sql", "data migration"],
        }
        point = search_experience_points(["SAP IDocs"])["SAP IDocs"][0]
        before = predict_ats_score(resume, job)
        optimized = apply_approved_suggestions(resume, [{**point, "type": "experience_point"}])
        after = predict_ats_score(optimized["optimized_resume"], job)

        self.assertGreaterEqual(after["score"], before["score"])
        self.assertIn(point["employer"], optimized["optimized_resume"])


if __name__ == "__main__":
    unittest.main()
