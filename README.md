# Job Application Copilot

Compliant CLI and local web dashboard for manual-controlled job application preparation, ATS prediction, tailored resume review, interview prep, application field suggestions, question-bank reuse, and tracking.

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

- Manual-controlled workflow: the user searches jobs outside the app, then pastes a single job URL/JD into Job Intake.
- Profile page with first name, last name, email, phone, address, city, state, zip, country, LinkedIn, portfolio, GitHub, education, certifications, skills, experience, current title, work authorization, sponsorship, relocation, and work-mode preferences.
- Resume Upload page for PDF, DOCX, and TXT master resumes, with parsed text preview, replacement uploads, versions, and optimized resume download.
- Portal Sessions page for local session status only:
  - LinkedIn
  - Indeed
  - Dice
  - Monster
  - ZipRecruiter
  - Workday
  - Greenhouse
  - Lever
  - iCIMS
  - Taleo
  - SuccessFactors
  - company career sites
  - unknown job sites
- No portal usernames or passwords are stored.
- Reads job postings from JSON exports or manually saved job descriptions.
- Extracts visible job details from a user-pasted URL when access is allowed.
- Shows specific intake status and next action for login-required, active, closed/filled, incomplete JD, and manual-JD-required pages.
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
- Builds a review-only Application Assist draft using saved profile fields and answer bank.
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

Sidebar pages:

- Dashboard
- Profile
- Resume Upload
- Portal Sessions
- Job Intake
- ATS Analysis
- Resume Optimizer
- Application Assist
- Question Bank
- Interview Prep
- Applications
- Recruiters
- Reminders
- Analytics
- Settings

## Profile Details

Open `Profile` in the sidebar.

Use:

- Save Profile
- Edit Profile
- Clear Profile

Profile data is used for:

- application field suggestions
- question-bank answers
- resume tailoring context
- interview question generation context

## Resume Upload

Open `Resume Upload` in the sidebar.

Supported:

- PDF
- DOCX
- TXT

Features:

- upload master resume
- parse resume text
- show resume preview
- replace resume with a new upload
- create resume versions
- download optimized resume as text

Stored:

- original file name
- parsed resume text
- upload date
- version number
- linked company/job
- ATS before score
- ATS after score

## Portal Sessions

Open `Portal Sessions`.

The user logs in manually in their browser. The app stores only a local status note:

- Logged in
- Not connected
- Session expired

Rules:

- no username/password storage
- no CAPTCHA bypass
- no auto-submit
- no mass scrape
- only process the single URL provided by the user
- ask login again if session expires

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

Input options:

- paste job URL
- open portal manually using a saved logged-in browser session
- paste job description manually
- upload a TXT JD file

Auto-run full workflow after job intake is ON by default. The pipeline progress UI shows:

- Extract Job Details
- Validate JD
- ATS Before Score
- Resume Suggestions
- ATS After Score
- Interview Questions
- Application Assist
- Save Tracker

General pipeline statuses:

- Pending
- Running
- Completed

Job intake itself uses reason-specific labels instead of a generic failure label.

If the page cannot be read, the dashboard shows:

```text
Unable to extract full JD from page. Please paste JD manually or upload JD file.
```

Job intake statuses:

- `Login Required` — shows `Login required. Please login manually and click Continue.`
- `Page Accessible` — shown after Continue After Login successfully reaches the job page.
- `Job Active` — extraction succeeded and ATS workflow can continue.
- `Job Closed/Filled` — shows `This job appears to be closed or filled.`
- `JD Extraction Incomplete` — asks the user to paste JD manually or upload a JD file.
- `Manual JD Required` — no usable URL/JD was available.

The app never shows only `Failed` for job intake; it gives a reason and next action.

When `Login Required` appears, the UI shows:

- Open Job Portal
- Continue After Login
- Paste JD Manually

The user logs in manually in the job portal tab, then clicks Continue After Login to retry the same job URL.

Resume preview behavior:

- TXT files preview as text.
- DOCX files are parsed into readable text and never show raw ZIP/XML internals like `PK`, `[Content_Types].xml`, or `word/document.xml`.
- PDF files preview in the browser PDF viewer instead of showing raw binary text.

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

Validation rejects login/search/invalid pages, including pages where:

- job title is Login, Sign In, or website name
- full job description is missing or too short
- page contains only sign-in/join/forgot-password style text

## Application Assist

Application Assist suggests/fills review-only values from saved Profile and Question Bank:

- first name
- last name
- email
- phone
- address
- city
- state
- zip
- country
- LinkedIn
- portfolio
- education
- experience
- work authorization
- sponsorship answer
- saved question-bank answers

Output includes:

- profile fields ready
- missing profile fields
- saved answers found
- unanswered questions found

The user reviews final application fields manually.

## Experience Point Library

Experience points live in:

```text
experience_points_library/
```

Folders are role-based:

- `data_engineer`
- `data_analyst`
- `business_analyst`
- `project_manager`
- `product_manager`
- `software_engineer`
- `qa_engineer`
- `cloud_engineer`
- `data_governance`
- `data_migration`
- `master_data_management`
- `generic`

After ATS analysis, missing skills are matched against the library. The user must select and approve points with `Allow Selected`; skipped points are not added. Before resume generation, the user must assign each approved point to the real employer/project. The system never assigns employers automatically.

## Question Bank

Question Bank has:

- Answered Questions
- Unanswered Questions

When a new application question appears, the app saves:

- question
- options, if visible
- company
- job title
- job URL
- unanswered status

When the user answers it, the app marks it answered and reuses similar answers later.

Delete behavior:

- each question has a delete/trash button
- confirmation prompt before deletion
- deleted questions are not reused
- bulk delete selected questions
- clear all unanswered questions

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
