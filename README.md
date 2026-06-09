# Job Application Assistant

Compliant CLI and local web dashboard for manual job application preparation, ATS prediction, tailored resume review, interview prep, analytics, and application tracking.

The assistant is designed to prepare high-quality application materials from a stored candidate profile and role bullet libraries. It does **not** search jobs automatically, bypass job-board protections, evade bot detection, solve CAPTCHA, or submit applications. The user manually pastes a job URL, reviews everything, uploads the final resume, solves CAPTCHA, and submits manually.

## Final Manual Workflow

```text
Login
↓
Load saved profile and resume
↓
User pastes job URL
↓
System extracts visible job details including JD, or asks user to paste JD manually
↓
System runs ATS Prediction Score against current resume
↓
System shows missing keywords and weak sections
↓
System suggests resume improvements with current text, suggested text, and reason
↓
User accepts/rejects/edits suggestions
↓
System generates optimized resume
↓
System runs ATS Prediction Score again
↓
System shows before vs after improvement
↓
System generates Level 1 and Level 2 interview questions from resume + JD
↓
System fills a review-only autofill draft from saved profile and answer bank
↓
System saves new unanswered questions
↓
User reviews everything
↓
User uploads final resume
↓
User solves CAPTCHA
↓
User submits manually
↓
Application is saved in tracker
↓
Dashboard analytics update
```

## Project Rating

```text
Current: 8/10
After updates: 9.5/10 to 10/10
```

## Time Saving Estimate

```text
Before: around 15 minutes per application
After: around 4-7 minutes per application
Estimated saving: 60-75%
```

## What it does

- Generates search URLs for broad IT roles across:
  - LinkedIn
  - Indeed
  - Dice
  - Glassdoor
  - Monster
  - CareerBuilder
  - ZipRecruiter
  - Company career portal discovery
- Reads job postings from JSON exports or manually saved job descriptions.
- Extracts visible job details from a user-pasted URL when access is allowed.
- Shows the exact fallback message when URL extraction is blocked:
  - `Unable to extract full job details from URL. Please paste the job description manually.`
- Extracts required skills and high-signal keywords.
- Compares each job with the stored candidate profile.
- Calculates original and optimized `ATS Prediction Score` values using weighted scoring:
  - skill match: 30%
  - experience match: 15%
  - keyword context: 15%
  - role/title match: 10%
  - resume section completeness: 10%
  - ATS formatting check: 10%
  - achievement/impact score: 5%
  - critical missing requirement penalty: 5%
- Selects relevant bullets from `data/roles/{role}.json` or `/data/roles/{role}.json`.
- Shows resume suggestions before modification with:
  - section name
  - current text
  - suggested text
  - reason for change
- Lets the user accept, reject, or edit suggestions before generating an optimized resume.
- Stores resume versions with original resume, optimized resume, version number, linked job/company, ATS before score, ATS after score, keywords added, and created date.
- Reuses saved application answers for repeated questions with multiple-choice options.
- Tracks answered and unanswered application questions.
- Builds a review-only autofill draft using saved profile fields and answer bank.
- Generates Level 1 screening and Level 2 technical interview questions from optimized resume and full JD.
- Tracks applications in JSONL with:
  - job role
  - company name
  - job URL
  - ATS score
  - resume path
  - cover letter path
  - application status
- Prevents duplicate processing of the same company and role by default.

## Full Backend API + Frontend Dashboard

Start the local dashboard:

```bash
python3 -m job_assistant.cli web
```

On Windows, use:

```bat
python -m job_assistant.cli web
```

Then open:

```text
http://127.0.0.1:8765
```

The web app includes:

- secure local user registration/login
- SQLite database at `applications/job_assistant.sqlite3`
- left sidebar navigation
- Kanban board:
  - Saved
  - Applied
  - Interviewing
  - Offer
  - Rejected
- application CRUD/status updates
- ATS before/after comparison
- resume suggestion approval screen
- question bank page
- interview prep page
- application tracker table
- analytics charts
- response/interview/offer conversion rates
- recruiter contact management
- follow-up reminders
- ATS Prediction Score engine
- AI resume optimizer with accept/reject/edit flow
- review-only autofill assistant
- Level 1 and Level 2 interview question generator
- answer evaluation helper
- audit logs in the database

Docker run:

```bash
docker compose up --build
```

Open:

```text
http://127.0.0.1:8765
```

Additional docs:

- `docs/API.md`
- `docs/ARCHITECTURE.md`

## Job URL Intake

Paste a job URL in the dashboard under `Job Intake`.

The system tries a simple visible HTML extraction. It does not render JavaScript, log in, solve CAPTCHA, or bypass restrictions.

If the page cannot be read, the dashboard shows:

```text
Unable to extract full job details from URL. Please paste the job description manually.
```

Extracted fields include:

- job title
- company name
- job URL
- source
- location
- work mode
- employment type
- salary range
- full job description
- responsibilities
- required qualifications
- preferred qualifications
- required skills
- preferred skills
- benefits
- visible application questions

Main API endpoints:

```text
POST /api/auth/register
POST /api/auth/login
GET  /api/applications
POST /api/applications
PUT  /api/applications/{id}
GET  /api/analytics
GET  /api/recruiters
POST /api/recruiters
GET  /api/reminders
POST /api/reminders
POST /api/ats/analyze
POST /api/interview/questions
POST /api/interview/evaluate
```

## Install / run

This project uses only the Python standard library.

```bash
python3 -m job_assistant.cli --help
```

Optionally install the CLI entrypoint:

```bash
python3 -m pip install -e .
job-assistant --help
```

## Candidate profile

Create an editable profile:

```bash
python3 -m job_assistant.cli init-profile
```

Then edit:

```text
data/candidate_profile.json
```

If a mounted profile exists at `/data/candidate_profile.json`, the CLI uses it by default. Otherwise it uses `data/candidate_profile.json`.

## Application answer bank

Create an editable answer bank:

```bash
python3 -m job_assistant.cli init-answers
```

Then edit:

```text
data/application_answers.json
```

Add or replace one answer from the CLI:

```bash
python3 -m job_assistant.cli answers add \
  --question "Will you now or in the future require sponsorship?" \
  --answer "No" \
  --options Yes No \
  --keywords sponsorship visa \
  --replace
```

Test answer matching:

```bash
python3 -m job_assistant.cli answers match \
  --question "Do you require visa sponsorship now or in the future?" \
  --options Yes No
```

When a job entry includes `application_questions`, the process command adds matching saved answers to the result and tracking record for reuse.

## Role bullet libraries

Role bullets live in:

```text
data/roles/{normalized_role}.json
```

The CLI also uses `/data/roles` automatically when that directory exists.

Examples:

- `data/roles/data_engineer.json`
- `data/roles/backend_developer.json`
- `data/roles/azure_data_engineer.json`
- `data/roles/general_it.json`

Bullets should only describe experience the candidate can truthfully claim. When tailoring improves the match but remains below the threshold, generated output is marked `needs_truthfulness_review`.

## Generate all-IT search links

```bash
python3 -m job_assistant.cli search-links --all-it --location "Remote"
```

List selectable IT role categories and sub-roles:

```bash
python3 -m job_assistant.cli roles
```

Use specific roles:

```bash
python3 -m job_assistant.cli search-links "Data Engineer" "Backend Developer" --location "Dallas, TX"
```

Use a role category with sub-roles:

```bash
python3 -m job_assistant.cli search-links \
  --categories "Data and AI" "Cloud and DevOps" \
  --location "Remote"
```

Limit platforms:

```bash
python3 -m job_assistant.cli search-links --all-it --platforms linkedin indeed dice
```

## Portal-by-portal search process

Generate an ordered plan that checks each portal one by one for the selected roles:

```bash
python3 -m job_assistant.cli search-plan \
  --categories "Data and AI" \
  --location "Remote" \
  --platforms linkedin glassdoor dice monster indeed careerbuilder ziprecruiter company_portals
```

Each step includes:

- platform
- role/sub-role
- search URL
- suggested minimum manual review time, default `180` seconds
- note to save relevant job descriptions for processing

This command plans the search flow. It does not scrape protected pages or submit applications.

## Process job postings

Create a jobs JSON file using `data/jobs/jobs.example.json` as a template. Each job needs:

- `role`
- `title`
- `company`
- `url`
- `description`
- optional `application_questions`

Run:

```bash
python3 -m job_assistant.cli process \
  --profile data/candidate_profile.json \
  --jobs data/jobs/jobs.example.json \
  --answers data/application_answers.json \
  --threshold 85
```

Generated files are written under:

```text
applications/{company-role}/resume.md
applications/{company-role}/cover_letter.md
```

Tracking records are appended to:

```text
applications/applications.jsonl
```

## Duplicate behavior

Default behavior skips the same `company + role`, even if the URL differs.

If you want reposts or distinct URLs at the same company and role to be processed, add:

```bash
--allow-reposts
```

Different roles at the same company are processed separately.

## End-to-end safe process notes

1. Create your real candidate profile with `init-profile`.
2. Edit `data/candidate_profile.json`.
3. Create reusable application answers with `init-answers` and `answers add`.
4. List all IT roles/sub-roles with `roles`.
5. Pick roles or categories for search.
6. Generate a portal-by-portal plan with `search-plan`.
7. Open each portal/search URL, review jobs, and save relevant descriptions into a jobs JSON file.
8. Run `process` to check the original resume ATS score and optimized score.
9. If missing skills are found, the assistant selects truthful matching bullets from `data/roles/{role}.json`.
10. Review the generated resume, cover letter, and suggested answers.
11. Submit through the official job application page or approved API after review.

The assistant records prepared applications so the same company + same role is not processed again unless `--allow-reposts` is used.

## Safety and compliance

This tool intentionally avoids:

- hidden browser automation
- bot-detection evasion
- fake mouse or keyboard behavior
- credential handling for job sites
- automatic job search
- automatic third-party form submission
- CAPTCHA bypass
- mass apply workflows

Use it to prepare accurate materials and organize applications. The user reviews everything, uploads the final resume, solves CAPTCHA, and submits manually through official channels.
