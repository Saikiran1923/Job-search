# API Reference

Start the server:

```bash
python3 -m job_assistant.cli web
```

Base URL:

```text
http://127.0.0.1:8765
```

Authenticated requests use:

```text
Authorization: Bearer <token>
```

## Auth

### Register

```http
POST /api/auth/register
```

```json
{
  "name": "Your Name",
  "email": "you@example.com",
  "password": "password123"
}
```

### Login

```http
POST /api/auth/login
```

```json
{
  "email": "you@example.com",
  "password": "password123"
}
```

## Applications

```http
GET /api/applications
POST /api/applications
GET /api/applications/{id}
PUT /api/applications/{id}
PATCH /api/applications/{id}
DELETE /api/applications/{id}
```

Create example:

```json
{
  "role": "Data Engineer",
  "title": "Data Engineer",
  "company": "Example Analytics",
  "url": "https://example.com/jobs/123",
  "source": "LinkedIn",
  "location": "Remote",
  "status": "applied",
  "optimized_ats_score": 88,
  "resume_version": "data-engineer-v1",
  "notes": "Applied with tailored resume."
}
```

Statuses:

```text
saved, applied, interviewing, offer, rejected
```

## Analytics

```http
GET /api/analytics
```

Returns totals, status counts, monthly counts, average ATS score, response rate, interview conversion rate, offer conversion rate, and resume-version performance.

## Recruiters

```http
GET /api/recruiters
POST /api/recruiters
```

## Reminders

```http
GET /api/reminders
POST /api/reminders
```

## ATS Analyzer

```http
POST /api/ats/analyze
```

```json
{
  "role": "Data Engineer",
  "resume_text": "Paste original resume text here",
  "job_description": "Paste job description here"
}
```

Returns original ATS score, optimized score, matched skills, missing skills, suggested role-library bullets, and a tailored summary.

## Final Workflow APIs

### Job URL Intake

```http
POST /api/job-intake/extract
```

```json
{
  "job_url": "https://company.example/careers/job-id"
}
```

If the URL cannot be read because of login, CAPTCHA, JavaScript rendering, or website restrictions, the API returns:

```text
Unable to extract full job details from URL. Please paste the job description manually.
```

### ATS Prediction Score

```http
POST /api/ats/predict
```

```json
{
  "resume_text": "Current resume text",
  "job_details": {
    "job_title": "Data Engineer",
    "full_job_description": "Full JD text"
  }
}
```

Returns weighted `ATS Prediction Score`, matched keywords, missing keywords, weak resume sections, formatting issues, confidence level, and reviewable resume suggestions.

### Resume Optimization + Version Creation

```http
POST /api/resume/optimize
GET /api/resume/versions
```

```json
{
  "resume_text": "Current resume text",
  "job_details": {
    "job_title": "Data Engineer",
    "company_name": "Example Analytics",
    "job_url": "https://example.test/job",
    "full_job_description": "Full JD text"
  },
  "approved_suggestions": [
    {
      "section_name": "Skills",
      "suggested_text": "Python, SQL, Airflow",
      "keywords_added": ["airflow"]
    }
  ]
}
```

### Question Bank

```http
GET /api/questions
GET /api/questions?status=answered
GET /api/questions?status=unanswered
POST /api/questions/unanswered
POST /api/questions/{id}/answer
```

### Autofill Draft

```http
POST /api/autofill/draft
```

Returns review-only fields from the saved profile and answer bank. It never submits forms.

### Interview Prep

```http
POST /api/interview/prep
GET /api/interview/saved
PATCH /api/interview/questions/{id}
```

Generates Level 1 screening questions and Level 2 technical/role-based questions from optimized resume and full JD.

## Interview Preparation

```http
POST /api/interview/questions
POST /api/interview/evaluate
```

Question generation:

```json
{
  "role": "Backend Developer",
  "job_description": "Paste job description here"
}
```

Answer evaluation:

```json
{
  "question": "Tell me about a backend project.",
  "answer": "Paste your answer here",
  "job_description": "Optional job description"
}
```

## Search Helpers

```http
GET /api/roles
GET /api/platforms
GET /api/search/plan?all_it=true&location=Remote
```

Search helpers generate official search URLs and do not scrape or bypass protected job boards.
