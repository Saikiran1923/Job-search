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
