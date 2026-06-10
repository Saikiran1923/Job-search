from io import BytesIO
from pathlib import Path
import unittest
import zipfile

from job_assistant.resume_parser import parse_resume_upload


class OptionALoginAndResumePreviewTests(unittest.TestCase):
    def test_continue_after_login_wires_page_accessible_status(self) -> None:
        web = Path("job_assistant/web.py").read_text(encoding="utf-8")
        app = Path("job_assistant/static/app.js").read_text(encoding="utf-8")
        extractor = Path("job_assistant/job_extractor.py").read_text(encoding="utf-8")

        self.assertIn("PAGE_ACCESSIBLE", extractor)
        self.assertIn("continue_after_login", web)
        self.assertIn("Page Accessible", web)
        self.assertIn("continueAfterLoginRetry = true", app)
        self.assertIn("payload.continue_after_login = true", app)

    def test_docx_preview_extracts_readable_text_without_zip_internals(self) -> None:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "word/document.xml",
                "<w:document><w:body><w:p><w:r><w:t>Readable Resume Text</w:t></w:r></w:p></w:body></w:document>",
            )

        parsed = parse_resume_upload("resume.docx", content_base64=_b64(buffer.getvalue()))

        self.assertEqual(parsed["file_type"], "DOCX")
        self.assertEqual(parsed["preview_type"], "text")
        self.assertIn("Readable Resume Text", parsed["resume_text"])
        self.assertNotIn("PK", parsed["resume_text"])
        self.assertNotIn("[Content_Types].xml", parsed["resume_text"])
        self.assertNotIn("word/document.xml", parsed["resume_text"])

    def test_pdf_preview_uses_pdf_container_not_raw_text(self) -> None:
        app = Path("job_assistant/static/app.js").read_text(encoding="utf-8")
        html = Path("job_assistant/static/index.html").read_text(encoding="utf-8")
        parsed = parse_resume_upload("resume.pdf", content_base64=_b64(b"%PDF-1.4\nbinary-ish-pdf"))

        self.assertEqual(parsed["file_type"], "PDF")
        self.assertEqual(parsed["preview_type"], "pdf")
        self.assertIn("PDF preview available", parsed["resume_text"])
        self.assertNotIn("%PDF-", parsed["resume_text"])
        self.assertIn("resumePdfPreview", html)
        self.assertIn("showResumePdfPreview", app)
        self.assertIn("URL.createObjectURL", app)

    def test_txt_preview_reads_text_directly(self) -> None:
        parsed = parse_resume_upload("resume.txt", content_text="Plain resume text")

        self.assertEqual(parsed["file_type"], "TXT")
        self.assertEqual(parsed["preview_type"], "text")
        self.assertEqual(parsed["resume_text"], "Plain resume text")


def _b64(value: bytes) -> str:
    import base64

    return base64.b64encode(value).decode("ascii")


if __name__ == "__main__":
    unittest.main()
