# AI Resume Screening System

A portfolio-ready, locally runnable recruiter workflow demo. It parses PDF and DOCX resumes, compares them with a role's required and preferred skills, shows evidence and gaps, and records application and human-review history in a local SQLite database.

> **Demo only:** this is not a validated hiring test, production ATS, or legal compliance tool. It does not make hiring decisions. Use the synthetic profiles included here for demonstrations.

## India recruiting and compliance context

Recruiting teams often need to review many applications against a specific role. This project demonstrates a structured review workflow using job-related criteria, evidence-backed summaries, a pseudonymous comparison queue, reviewer dispositions, and an exportable session log. AI-assisted evaluation can introduce accessibility, bias, privacy, and notice risks.

The app is intentionally transparent: the recruiter sets the criteria, the score formula is visible, every skill match links to resume text, and a person records the review status. The demo does not infer protected traits or claim to predict job performance. It is a portfolio prototype, not a production selection system or legal compliance tool.

For use in India, employers should assess applicant-data processing against the Digital Personal Data Protection Act, 2023 and the rules and notifications in force, along with applicable employment, equal-opportunity, and accessibility requirements. Applicability depends on the organization and use case. Check current commencement and requirements, and obtain India-qualified legal advice before processing real applicant data.

Official India references reviewed **2 November 2026**:

- [Digital Personal Data Protection Act, 2023 — India Code](https://www.indiacode.nic.in/bitstream/123456789/22029/1/a2023-22.pdf)
- [Ministry of Electronics and Information Technology — Data Protection Framework](https://www.meity.gov.in/data-protection-framework)
- [India Code — Central Acts](https://www.indiacode.nic.in/)

## Features

- Batch upload PDF and DOCX resumes (10 MB maximum per file)
- Extract resume text locally; no LLM or external API required
- Store candidate name, email, previous/latest job role, application date, score signals, and review history in a local SQLite database
- Browse older applications, filter by role/date, update review decisions, and view status totals
- Retain application records for at least one year; extracted resume text storage is optional and off by default
- Editable role title, experience range, work mode, primary responsibilities, generated job-description draft, required skills, and preferred skills
- Explainable match signal based on skill evidence and local TF-IDF text similarity
- Separate ATS-readiness signal based on text extraction and common resume section headings
- Candidate comparison table, evidence snippets, missing criteria, and extracted text review
- Human-owned review statuses and a persistent review history, with CSV export
- Separate Selected, Rejected, and On hold candidate lists and CSV downloads
- Included synthetic candidates for an immediate walkthrough

## Run locally

Requires Python 3.10 or newer.

```powershell
cd AI_Resume_Screening_System
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit. Role criteria start blank with **Select a role**, **Select experience range**, and **Select work mode** placeholders. Choose a role template (including **AI Engineer**) to fill in its title and responsibilities; then choose an experience range and work mode and select **Generate job description draft**. Choosing **Custom role** clears the role fields so HR can enter the criteria from scratch; complete the fields and select **Add role** at the bottom to apply them for the current session. Review the draft before saving.

To add an applicant, provide their name, email, previous job role, latest job role, and one PDF/DOCX resume. Application and review details are saved to `data/applications.sqlite3`; extracted resume text is saved only if you opt in. Use **Application history** to see all-time status totals, filter and browse older records, update their status, and export the filtered history. Records are not automatically deleted and are retained for at least one year. **Clear session data** does not remove database history. To try the demo, select **Load sample candidates**, inspect the ranked signals, and save a human review status.

## Scoring model

| Signal | Default weight | How it is calculated |
|---|---:|---|
| Required skill coverage | 70% | Fraction of required skills with an exact name or listed alias found in resume text |
| Preferred skill coverage | 20% | Fraction of preferred skills with an exact name or listed alias found in resume text |
| Role text similarity | 10% | TF-IDF cosine similarity between the job title/description and resume text |

Weights for categories not configured are redistributed across the active categories. A result is a **match signal**, not a probability, qualification, or recommendation to reject. Exact phrase matching can miss equivalent experience, context, and skills expressed with unfamiliar terminology. Scanned PDFs need OCR before upload.

The separate **ATS readiness (demo)** signal awards 20 points for extractable text and 20 points each for recognizable Summary/Profile, Experience, Education, and Skills headings. This is a limited text-structure check, not a standardized ATS score; it cannot verify how a specific ATS handles formatting or layout, and it does not assess candidate suitability. Do not use it as an automatic shortlisting threshold.

## Privacy and safeguards

- The app parses resumes locally and does not save the original PDF/DOCX files or call external AI APIs.
- Candidate name, email, previous/latest role, application date, job criteria, score signals, review status, reviewer notes, and status history are stored in a local SQLite database for at least one year.
- Extracted resume text is optional to store and off by default. If it is not stored, the app retains the application details and scores but cannot reopen the resume text after its session ends.
- The database is not encrypted by the app. Secure the computer and database file with appropriate access controls and backups. Do not commit the database to source control.
- The candidate comparison table uses candidate IDs; the Application history view contains personally identifying applicant details.
- The app does not explicitly extract protected traits or personality. Role-text similarity reads all extracted resume text, so personal details or proxy terms could still affect that signal; this demo cannot guarantee proxy-free scoring. Resume content can contain personal data.
- The reviewer must inspect context and own the decision; the score never changes a candidate's review status.
- Do not use real applicant data until the app has appropriate access controls, retention/deletion policies, security review, monitoring, accessibility support, candidate notices, and has been assessed against applicable Indian data-protection, employment, and accessibility requirements.

## Project structure

```text
AI_Resume_Screening_System/
├── streamlit_app.py
├── src/
│   ├── application_store.py
│   └── resume_screening.py
├── data/                       # local SQLite application history (created on first run)
├── sample_data/resumes/       # synthetic DOCX demo profiles
├── .streamlit/config.toml
├── requirements.txt
```

## Resume bullet you can adapt

> Built an explainable AI-assisted resume review dashboard in Streamlit, parsing PDF/DOCX resumes and ranking job-related skill evidence with configurable criteria and TF-IDF similarity; added persistent applicant history, human review tracking, status-specific CSV exports, and optional resume-text retention.

For an interview or resume, describe this accurately as a **portfolio prototype**. The matching logic is deterministic NLP and keyword evidence, not a trained hiring model or production ATS integration.
