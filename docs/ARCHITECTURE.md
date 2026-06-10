# Architecture

```text
Browser Dashboard
  |
  | HTTP JSON API
  v
job_assistant.web
  |
  +--> job_assistant.database  ----> SQLite database
  |
  +--> job_assistant.optimizer ----> ATS matching + role bullet libraries
  |
  +--> job_assistant.interview ----> interview questions + answer evaluation
  |
  +--> job_assistant.search -------> role/platform search plans
  |
  +--> job_assistant.documents ----> tailored resume + cover letter generation
```

## Components

### Frontend

Location:

```text
job_assistant/static/
```

Provides:

- login/register forms
- Kanban application board
- analytics cards
- recruiter contact form
- follow-up reminder form
- ATS analyzer
- interview question generator
- answer evaluator

### Backend API

Location:

```text
job_assistant/web.py
```

Uses Python standard-library `http.server` and JSON endpoints.

### Database

Location:

```text
job_assistant/database.py
```

Default local database:

```text
applications/job_assistant.sqlite3
```

Tables:

- `users`
- `sessions`
- `applications`
- `status_history`
- `recruiters`
- `reminders`
- `resume_versions`
- `audit_logs`

### Resume Optimization

Location:

```text
job_assistant/optimizer.py
job_assistant/ats.py
data/roles/
```

Flow:

1. Extract known skills from job description.
2. Extract known skills from resume text.
3. Calculate original ATS score.
4. Select matching role-library bullets for missing skills.
5. Calculate optimized ATS score.
6. Return missing keywords, suggested bullets, and tailored summary.

### Interview Preparation

Location:

```text
job_assistant/interview.py
```

Generates:

- technical questions
- behavioral questions
- mock interview prompts

Evaluates answers using:

- STAR structure markers
- answer depth
- job-skill keyword coverage

## Safety Boundaries

The system does not implement:

- stealth automation
- bot-detection bypass
- fake human mouse/keyboard behavior
- unauthorized scraping
- hidden job-site form submission

It supports reviewable, official workflows:

- search planning
- job analysis
- resume/cover-letter preparation
- application tracking
- reminders
- interview preparation
