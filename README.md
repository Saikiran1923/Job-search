# Job Application Assistant

Compliant CLI assistant for job discovery support, ATS-style matching, tailored resume and cover-letter generation, and application tracking.

The assistant is designed to prepare high-quality application materials from a stored candidate profile and role bullet libraries. It does **not** bypass job-board protections, evade bot detection, or submit applications deceptively. Use generated materials with official application flows, company APIs, or manual review.

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
- Extracts required skills and high-signal keywords.
- Compares each job with the stored candidate profile.
- Calculates an ATS-style match score.
- Selects relevant bullets from `data/roles/{role}.json` or `/data/roles/{role}.json`.
- Generates a tailored resume and cover letter for jobs that pass or need review.
- Tracks applications in JSONL with:
  - job role
  - company name
  - job URL
  - ATS score
  - resume path
  - cover letter path
  - application status
- Prevents duplicate processing of the same company and role by default.

## Install / run

This project uses only the Python standard library.

```bash
python -m job_assistant.cli --help
```

Optionally install the CLI entrypoint:

```bash
python -m pip install -e .
job-assistant --help
```

## Candidate profile

Create an editable profile:

```bash
python -m job_assistant.cli init-profile
```

Then edit:

```text
data/candidate_profile.json
```

If a mounted profile exists at `/data/candidate_profile.json`, the CLI uses it by default. Otherwise it uses `data/candidate_profile.json`.

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
python -m job_assistant.cli search-links --all-it --location "Remote"
```

Use specific roles:

```bash
python -m job_assistant.cli search-links "Data Engineer" "Backend Developer" --location "Dallas, TX"
```

Limit platforms:

```bash
python -m job_assistant.cli search-links --all-it --platforms linkedin indeed dice
```

## Process job postings

Create a jobs JSON file using `data/jobs/jobs.example.json` as a template. Each job needs:

- `role`
- `title`
- `company`
- `url`
- `description`

Run:

```bash
python -m job_assistant.cli process \
  --profile data/candidate_profile.json \
  --jobs data/jobs/jobs.example.json \
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

## Safety and compliance

This tool intentionally avoids:

- hidden browser automation
- bot-detection evasion
- fake mouse or keyboard behavior
- credential handling for job sites
- automatic third-party form submission without user review

Use it to prepare accurate materials and organize applications. Submit through official channels and verify each tailored claim before applying.
