from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import streamlit as st

from src.application_store import (
    application_exists,
    create_application,
    initialize_database,
    list_applications,
    list_review_history,
    update_application_scores,
    update_review,
)
from src.resume_screening import content_fingerprint, normalize_skill_list, parse_resume, rank_candidates


PROJECT_DIR = Path(__file__).parent
DATABASE_PATH = Path(
    os.environ.get(
        "RESUME_SCREENING_DB",
        str(PROJECT_DIR / "data" / "applications.sqlite3"),
    )
)
MAX_FILE_BYTES = 10 * 1024 * 1024
EXPERIENCE_RANGES = [
    "Select experience range",
    "0-2 years",
    "2-5 years",
    "5-8 years",
    "8-12 years",
    "12+ years",
]
WORK_MODES = ["Select work mode", "On-site", "Hybrid", "Remote", "Flexible"]
ROLE_TEMPLATE_PLACEHOLDER = "Select a role"
REVIEW_STATUSES = ["Needs review", "Selected", "Rejected", "On hold"]
STATUS_MIGRATIONS = {
    "Advance": "Selected",
    "Do not advance": "Rejected",
    "Hold": "On hold",
}
SAMPLE_JOB = {
    "title": "Product Data Analyst",
    "description": (
        "We are looking for a Product Data Analyst to help product teams make evidence-led decisions. "
        "You will define metrics, write reliable SQL, use Python for analysis, design and interpret "
        "A/B tests, and communicate findings through clear dashboards. You will partner with product "
        "managers and engineers to improve activation and retention. Experience with experimentation, "
        "Tableau or Power BI, and a modern data stack such as dbt and Snowflake is useful."
    ),
    "experience_range": "5-8 years",
    "work_mode": "Hybrid",
    "responsibilities": (
        "Define product metrics and build reliable SQL models.\n"
        "Use Python to analyze product usage and experiment results.\n"
        "Create clear dashboards and communicate findings to product teams."
    ),
    "required_skills": ["SQL", "Python", "Statistics", "A/B testing", "Data visualization"],
    "preferred_skills": ["dbt", "Snowflake", "Experimentation", "Stakeholder management", "Data storytelling"],
}
EMPTY_JOB = {
    "title": "",
    "description": "",
    "experience_range": EXPERIENCE_RANGES[0],
    "work_mode": WORK_MODES[0],
    "responsibilities": "",
    "required_skills": [],
    "preferred_skills": [],
}
ROLE_TEMPLATES = {
    "AI Engineer": (
        "Develop, train, and evaluate machine-learning models for product and business use cases.\n"
        "Build and integrate AI services and data pipelines into production applications.\n"
        "Measure model quality, monitor performance, and improve reliability, latency, and responsible use.\n"
        "Collaborate with product, data, and engineering teams to translate requirements into AI features."
    ),
    "Data Scientist": (
        "Analyze structured and unstructured data to answer business and product questions.\n"
        "Design experiments and develop statistical or machine-learning models.\n"
        "Validate model performance and communicate assumptions, limitations, and findings.\n"
        "Partner with product and business teams to turn analysis into measurable improvements."
    ),
    "Product Data Analyst": (
        "Define product metrics and build reliable SQL models.\n"
        "Use Python to analyze product usage and experiment results.\n"
        "Create clear dashboards and communicate findings to product teams."
    ),
    "Software Engineer": (
        "Design, implement, test, and maintain reliable software services.\n"
        "Review code and improve application performance, security, and observability.\n"
        "Work with product and engineering partners to deliver well-scoped features.\n"
        "Document technical decisions and participate in production support."
    ),
}


def build_job_description(
    role_title: str,
    experience_range: str,
    work_mode: str,
    responsibilities: str,
) -> str:
    """Create an editable job-description draft from recruiter-provided details."""
    title = role_title.strip() or "Untitled role"
    responsibility_items = [
        re.sub(r"^[-*•]\s*", "", item.strip())
        for item in responsibilities.splitlines()
        if item.strip()
    ]
    responsibility_text = "\n".join(f"- {item}" for item in responsibility_items)
    if not responsibility_text:
        responsibility_text = "- Deliver the core work and outcomes agreed for this role."
    article = "an" if title.casefold().startswith(("a", "e", "i", "o", "u")) else "a"

    return (
        f"We are seeking {article} {title} with {experience_range} of relevant experience. "
        f"This is a {work_mode.lower()} position.\n\n"
        "Primary responsibilities:\n"
        f"{responsibility_text}\n\n"
        "The successful candidate will collaborate with relevant stakeholders, communicate "
        "progress clearly, and deliver these responsibilities to agreed quality standards."
    )


def apply_role_template() -> None:
    """Update the role form fields and draft when a role template is selected."""
    title = st.session_state["role_template_input"]
    responsibilities = ROLE_TEMPLATES.get(title)
    if responsibilities is None:
        st.session_state.job = EMPTY_JOB.copy()
        st.session_state["role_title_input"] = ""
        st.session_state["experience_range_input"] = EXPERIENCE_RANGES[0]
        st.session_state["work_mode_input"] = WORK_MODES[0]
        st.session_state["responsibilities_input"] = ""
        st.session_state["job_description_input"] = ""
        st.session_state["required_skills_input"] = ""
        st.session_state["preferred_skills_input"] = ""
        return

    experience_range = st.session_state["experience_range_input"]
    work_mode = st.session_state["work_mode_input"]
    if title == "Product Data Analyst":
        required_skills = SAMPLE_JOB["required_skills"]
        preferred_skills = SAMPLE_JOB["preferred_skills"]
    else:
        required_skills = []
        preferred_skills = []
    description = (
        build_job_description(title, experience_range, work_mode, responsibilities)
        if experience_range != EXPERIENCE_RANGES[0] and work_mode != WORK_MODES[0]
        else ""
    )
    st.session_state.job.update(
        {
            "title": title,
            "responsibilities": responsibilities,
            "description": description,
            "required_skills": required_skills,
            "preferred_skills": preferred_skills,
        }
    )
    st.session_state["role_title_input"] = title
    st.session_state["responsibilities_input"] = responsibilities
    st.session_state["job_description_input"] = description
    st.session_state["required_skills_input"] = ", ".join(required_skills)
    st.session_state["preferred_skills_input"] = ", ".join(preferred_skills)


def generate_job_description_draft() -> None:
    """Generate a draft from the current role-form values before the form reruns."""
    title = st.session_state["role_title_input"].strip() or "Untitled role"
    experience_range = st.session_state["experience_range_input"]
    work_mode = st.session_state["work_mode_input"]
    responsibilities = st.session_state["responsibilities_input"].strip()
    if experience_range == EXPERIENCE_RANGES[0] or work_mode == WORK_MODES[0]:
        st.session_state["job_description_generated"] = False
        st.session_state["role_form_error"] = (
            "Select an experience range and work mode before generating the job description."
        )
        return
    description = build_job_description(title, experience_range, work_mode, responsibilities)
    st.session_state.job.update(
        {
            "title": title,
            "experience_range": experience_range,
            "work_mode": work_mode,
            "responsibilities": responsibilities,
            "description": description,
            "required_skills": normalize_skill_list(st.session_state["required_skills_input"]),
            "preferred_skills": normalize_skill_list(st.session_state["preferred_skills_input"]),
        }
    )
    st.session_state["job_description_input"] = description
    st.session_state["job_description_generated"] = True


def init_state() -> None:
    st.session_state.setdefault("job", EMPTY_JOB.copy())
    for key, value in SAMPLE_JOB.items():
        st.session_state.job.setdefault(key, EMPTY_JOB.get(key, value))
    st.session_state.setdefault("candidates", {})
    st.session_state.setdefault("seen_hashes", set())
    st.session_state.setdefault("audit_log", [])
    for candidate in st.session_state.candidates.values():
        candidate["review_status"] = STATUS_MIGRATIONS.get(
            candidate.get("review_status", "Needs review"),
            candidate.get("review_status", "Needs review"),
        )


def add_candidate(
    content: bytes,
    source_name: str,
    source_label: str,
    applicant: dict[str, str],
    store_resume_text: bool,
) -> tuple[bool, str]:
    if Path(source_name).suffix.casefold() not in {".pdf", ".docx"}:
        return False, f"{source_label}: only PDF and DOCX resumes are accepted."
    if not all(
        applicant.get(key, "").strip()
        for key in ("full_name", "email", "previous_job_role", "latest_job_role")
    ):
        return False, "Enter the candidate name, email, previous role, and latest role."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", applicant["email"].strip()):
        return False, "Enter a valid email address."
    if len(content) > MAX_FILE_BYTES:
        return False, f"{source_label}: file exceeds the 10 MB limit."
    fingerprint = content_fingerprint(content)
    if fingerprint in st.session_state.seen_hashes:
        return False, f"{source_label}: duplicate file skipped."
    try:
        resume_text = parse_resume(source_name, content)
    except Exception as exc:  # parser errors should not stop the rest of a batch
        return False, f"{source_label}: could not read the file ({exc})."
    if len(resume_text.strip()) < 40:
        return False, f"{source_label}: no readable text found. Scanned PDFs need OCR before upload."

    persisted = create_application(
        DATABASE_PATH,
        applicant,
        st.session_state.job,
        resume_text if store_resume_text else None,
    )
    candidate_id = persisted["candidate_id"]
    st.session_state.candidates[candidate_id] = {
        "candidate_id": candidate_id,
        "full_name": applicant["full_name"].strip(),
        "email": applicant["email"].strip().casefold(),
        "previous_job_role": applicant["previous_job_role"].strip(),
        "latest_job_role": applicant["latest_job_role"].strip(),
        "text": resume_text,
        "review_status": "Needs review",
        "review_note": "",
        "source": source_label,
    }
    st.session_state.seen_hashes.add(fingerprint)
    if not store_resume_text:
        message = f"{candidate_id} added. Resume text was not saved to the database."
    else:
        message = f"{candidate_id} added. Resume text was saved for future review."
    return True, message


def submit_application() -> None:
    upload_key = f"applicant_resume_upload_{st.session_state['resume_upload_version']}"
    uploaded_resume = st.session_state.get(upload_key)
    if uploaded_resume is None:
        st.session_state["application_form_error"] = (
            "Upload a PDF or DOCX resume to calculate the candidate's review signals."
        )
        return

    applicant_details = {
        "full_name": st.session_state["applicant_name_input"],
        "email": st.session_state["applicant_email_input"],
        "previous_job_role": st.session_state["previous_job_role_input"],
        "latest_job_role": st.session_state["latest_job_role_input"],
    }
    ok, message = add_candidate(
        uploaded_resume.getvalue(),
        uploaded_resume.name,
        "Resume upload",
        applicant_details,
        st.session_state["store_resume_text_input"],
    )
    if not ok:
        st.session_state["application_form_error"] = message
        return

    st.session_state["application_added_message"] = message
    st.session_state["application_form_error"] = ""
    for key in (
        "applicant_name_input",
        "applicant_email_input",
        "previous_job_role_input",
        "latest_job_role_input",
    ):
        st.session_state[key] = ""
    st.session_state["resume_upload_version"] += 1
    st.session_state["store_resume_text_input"] = False


def make_csv(rows: list[dict[str, object]]) -> bytes:
    buffer = StringIO(newline="")
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def candidate_summary_rows(ranked: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = []
    for row in ranked:
        rows.append(
            {
                "candidate_id": row["candidate_id"],
                "job_title": st.session_state.job["title"],
                "match_signal_percent": row["score"],
                "ats_readiness_signal_percent": row["ats_readiness_score"],
                "required_skills_matched": row["required_matched"],
                "required_skills_total": row["required_total"],
                "preferred_skills_matched": row["preferred_matched"],
                "preferred_skills_total": row["preferred_total"],
                "human_review_status": row["review_status"],
            }
        )
    return rows


st.set_page_config(page_title="AI Resume Screening System", page_icon="📄", layout="wide")
initialize_database(DATABASE_PATH)
init_state()
stored_applications = list_applications(DATABASE_PATH)
if not st.session_state.get("role_form_initialized", False):
    st.session_state.job = EMPTY_JOB.copy()
    st.session_state["role_template_input"] = ROLE_TEMPLATE_PLACEHOLDER
    st.session_state["role_title_input"] = ""
    st.session_state["experience_range_input"] = EXPERIENCE_RANGES[0]
    st.session_state["work_mode_input"] = WORK_MODES[0]
    st.session_state["responsibilities_input"] = ""
    st.session_state["job_description_input"] = ""
    st.session_state["required_skills_input"] = ""
    st.session_state["preferred_skills_input"] = ""
    st.session_state["role_form_initialized"] = True
st.session_state.setdefault("role_template_input", ROLE_TEMPLATE_PLACEHOLDER)
st.session_state.setdefault("role_title_input", "")
st.session_state.setdefault(
    "experience_range_input", EXPERIENCE_RANGES[0]
)
st.session_state.setdefault("work_mode_input", WORK_MODES[0])
st.session_state.setdefault("responsibilities_input", "")
st.session_state.setdefault("job_description_input", "")
st.session_state.setdefault(
    "required_skills_input", ""
)
st.session_state.setdefault(
    "preferred_skills_input", ""
)
st.session_state.setdefault("resume_upload_version", 0)
st.title("AI Resume Screening System")
st.caption("An explainable, human-reviewed candidate matching demo for skill-based hiring.")
if message := st.session_state.pop("application_added_message", None):
    st.success(message)

with st.sidebar:
    st.subheader("Recruiter workspace")
    st.write(f"**Role:** {st.session_state.job['title'] or ROLE_TEMPLATE_PLACEHOLDER}")
    st.write(f"**Candidates:** {len(st.session_state.candidates)}")
    st.write(f"**Applications in database:** {len(stored_applications)}")
    st.info("Application details and review status are stored in a local SQLite database. Resume text is stored only when you opt in.")
    st.caption("Records are retained for at least 1 year. Clearing session data does not delete database records.")
    if st.button("Clear session data", type="secondary", width="stretch"):
        for key in ("candidates", "seen_hashes", "audit_log"):
            st.session_state[key] = {} if key == "candidates" else set() if key == "seen_hashes" else []
        st.session_state["resume_upload_version"] += 1
        st.rerun()

with st.container(border=True):
    st.subheader("1. Set the role criteria")
    st.caption("Keep criteria specific to the work. Skills below are the only explicit requirements used in the match score.")
    st.caption("The job-description draft uses a local template, not an AI model. Review it for accuracy before saving.")
    st.selectbox(
        "Choose a role template",
        [ROLE_TEMPLATE_PLACEHOLDER, "Custom role", *ROLE_TEMPLATES],
        key="role_template_input",
        on_change=apply_role_template,
        help="Selecting a role updates the title, responsibilities, and editable job-description draft. Choose Custom role to enter a role from scratch.",
    )
    with st.form("role_form"):
        role_title = st.text_input(
            "Role title",
            key="role_title_input",
            placeholder="Enter a role title",
        )
        experience_range = st.selectbox(
            "Experience range",
            EXPERIENCE_RANGES,
            key="experience_range_input",
        )
        work_mode = st.selectbox(
            "Work mode",
            WORK_MODES,
            key="work_mode_input",
        )
        responsibilities = st.text_area(
            "Primary responsibilities",
            key="responsibilities_input",
            height=110,
            help="Enter the main outcomes and duties, one per line.",
        )
        job_description = st.text_area(
            "Job description",
            key="job_description_input",
            height=145,
            help="This editable draft is used for a low-weight text similarity signal. Personal details or proxy terms in resumes could still affect that signal.",
        )
        required_input = st.text_input(
            "Required skills (comma-separated)",
            key="required_skills_input",
        )
        preferred_input = st.text_input(
            "Preferred skills (comma-separated)",
            key="preferred_skills_input",
        )
        st.form_submit_button(
            "Generate job description draft",
            on_click=generate_job_description_draft,
        )
        role_submit_label = (
            "Add role"
            if st.session_state["role_template_input"] == "Custom role"
            else "Save role criteria"
        )
        save_job = st.form_submit_button(role_submit_label, type="primary")
    if st.session_state.pop("job_description_generated", False):
        st.success("Draft generated locally. Review and edit it before saving the role criteria.")
    if role_form_error := st.session_state.pop("role_form_error", None):
        st.error(role_form_error)
    if save_job:
        required_skills = normalize_skill_list(required_input)
        preferred_skills = normalize_skill_list(preferred_input)
        if st.session_state["role_template_input"] == ROLE_TEMPLATE_PLACEHOLDER:
            st.error("Select a role or choose Custom role before saving criteria.")
        elif not role_title.strip():
            st.error("Enter a role title before adding the role.")
        elif experience_range == EXPERIENCE_RANGES[0]:
            st.error("Select an experience range before adding the role.")
        elif work_mode == WORK_MODES[0]:
            st.error("Select a work mode before adding the role.")
        elif not required_skills and not preferred_skills:
            st.error("Add at least one required or preferred skill before comparing candidates.")
        else:
            st.session_state.job = {
                "title": role_title.strip() or "Untitled role",
                "description": job_description.strip(),
                "experience_range": experience_range,
                "work_mode": work_mode,
                "responsibilities": responsibilities.strip(),
                "required_skills": required_skills,
                "preferred_skills": preferred_skills,
            }
            if role_submit_label == "Add role":
                st.success("Custom role added for this session. Candidate signals have been refreshed.")
            else:
                st.success("Role criteria saved. Candidate signals have been refreshed.")

with st.container(border=True):
    st.subheader("2. Add candidates")
    st.caption("Add one applicant at a time so their required details stay linked to the correct resume.")
    with st.form("applicant_form"):
        st.text_input("Candidate name", key="applicant_name_input")
        st.text_input("Email address", key="applicant_email_input")
        st.text_input("Previous job role", key="previous_job_role_input")
        st.text_input("Latest job role", key="latest_job_role_input")
        st.file_uploader(
            "Resume (PDF or DOCX, 10 MB maximum)",
            type=["pdf", "docx"],
            accept_multiple_files=False,
            key=f"applicant_resume_upload_{st.session_state['resume_upload_version']}",
        )
        st.checkbox(
            "Store extracted resume text in the database for future reviews",
            value=False,
            key="store_resume_text_input",
            help="Off by default. Candidate identity and application details are stored regardless.",
        )
        st.form_submit_button(
            "Add applicant",
            type="primary",
            on_click=submit_application,
        )
    if error_message := st.session_state.pop("application_form_error", ""):
        st.error(error_message)

    sample_col = st.container()
    with sample_col:
        load_samples = st.button("Load sample candidates", disabled=bool(st.session_state.candidates))

    if load_samples:
        sample_dir = PROJECT_DIR / "sample_data" / "resumes"
        sample_messages = []
        for sample_path in sorted(sample_dir.glob("*.docx")):
            sample_label = sample_path.stem[-1].upper()
            sample_applicant = {
                "full_name": f"Synthetic Candidate {sample_label}",
                "email": f"candidate.{sample_label.casefold()}@example.invalid",
                "previous_job_role": "Data Analyst",
                "latest_job_role": "Product Data Analyst",
            }
            if application_exists(
                DATABASE_PATH,
                sample_applicant["email"],
                st.session_state.job["title"],
            ):
                sample_messages.append(
                    f"{sample_applicant['full_name']} is already in this role's history."
                )
                continue
            ok, message = add_candidate(
                sample_path.read_bytes(),
                sample_path.name,
                "Synthetic demo profile",
                sample_applicant,
                False,
            )
            sample_messages.append(message)
        st.session_state["application_added_message"] = "\n".join(sample_messages)
        st.rerun()

st.divider()

ranked = rank_candidates(st.session_state.job, list(st.session_state.candidates.values()))
for ranked_candidate in ranked:
    update_application_scores(
        DATABASE_PATH,
        ranked_candidate["candidate_id"],
        ranked_candidate["score"],
        ranked_candidate["ats_readiness_score"],
    )

review_tab, history_tab, log_tab, method_tab = st.tabs(
    ["Candidate review", "Application history", "Review log", "Method & safeguards"]
)

with review_tab:
    if not ranked:
        st.info("Add resumes or load the synthetic sample candidates to start a review.")
    else:
        required_n = len(st.session_state.job["required_skills"])
        preferred_n = len(st.session_state.job["preferred_skills"])
        metric_cols = st.columns(4)
        metric_cols[0].metric("Candidates", len(ranked))
        metric_cols[1].metric("Required skills", required_n)
        metric_cols[2].metric("Preferred skills", preferred_n)
        metric_cols[3].metric("Awaiting review", sum(row["review_status"] == "Needs review" for row in ranked))

        st.subheader("Role match signals")
        st.caption("Sorted by a transparent job-text and skill-match score. Treat this as a review queue aid, not a hiring decision.")
        table_rows = [
            {
                "Candidate": row["candidate_id"],
                "Match signal": row["score"],
                "ATS readiness (demo)": row["ats_readiness_score"],
                "Required skills": f"{row['required_matched']} / {row['required_total']}",
                "Preferred skills": f"{row['preferred_matched']} / {row['preferred_total']}",
                "Human review": row["review_status"],
            }
            for row in ranked
        ]
        st.dataframe(
            table_rows,
            hide_index=True,
            width="stretch",
            column_config={
                "Match signal": st.column_config.ProgressColumn("Match signal", min_value=0, max_value=100, format="%d%%"),
                "ATS readiness (demo)": st.column_config.ProgressColumn(
                    "ATS readiness (demo)", min_value=0, max_value=100, format="%d%%"
                ),
            },
        )

        st.subheader("Decision groups")
        status_tabs = st.tabs(["Selected", "Rejected", "On hold"])
        for status, status_tab in zip(REVIEW_STATUSES[1:], status_tabs):
            with status_tab:
                status_rows = candidate_summary_rows(
                    [row for row in ranked if row["review_status"] == status]
                )
                st.caption(f"{len(status_rows)} candidate(s) marked {status.lower()}.")
                if status_rows:
                    st.dataframe(status_rows, hide_index=True, width="stretch")
                else:
                    st.info(f"No candidates are currently marked {status.lower()}.")
                st.download_button(
                    f"Download {status.lower()} candidates (CSV)",
                    data=make_csv(status_rows),
                    file_name=f"{status.lower().replace(' ', '_')}_candidates.csv",
                    mime="text/csv",
                    disabled=not status_rows,
                )

        candidate_ids = [row["candidate_id"] for row in ranked]
        selected_id = st.selectbox("Open a candidate for evidence review", candidate_ids)
        selected = next(row for row in ranked if row["candidate_id"] == selected_id)

        st.markdown(f"### {selected_id}")
        st.caption("Candidate IDs are pseudonymous. The original filename is not shown in the review table.")
        detail_cols = st.columns(4)
        detail_cols[0].metric("Match signal", f"{selected['score']}%")
        detail_cols[1].metric("ATS readiness (demo)", f"{selected['ats_readiness_score']}%")
        detail_cols[2].metric("Required skills found", f"{selected['required_matched']} / {selected['required_total']}")
        detail_cols[3].metric("Preferred skills found", f"{selected['preferred_matched']} / {selected['preferred_total']}")
        st.caption(
            "ATS readiness checks text extraction and common resume section headings only. "
            f"Detected: {', '.join(selected['ats_sections_found']) or 'no standard headings'}."
        )
        st.caption("It is not a universal ATS score and does not measure candidate suitability or actual compatibility with a specific ATS.")

        evidence_col, gap_col = st.columns(2)
        with evidence_col:
            st.markdown("#### Evidence found")
            found_any = False
            for heading, evidence_map in (
                ("Required", selected["required_evidence"]),
                ("Preferred", selected["preferred_evidence"]),
            ):
                for skill, evidence in evidence_map.items():
                    if evidence:
                        found_any = True
                        st.markdown(f"**{heading}: {skill}**")
                        st.caption(evidence)
            if not found_any:
                st.write("No configured skill evidence was found in this resume.")
        with gap_col:
            st.markdown("#### Criteria not found")
            missing_required = [skill for skill, evidence in selected["required_evidence"].items() if evidence is None]
            missing_preferred = [skill for skill, evidence in selected["preferred_evidence"].items() if evidence is None]
            st.markdown("**Required**")
            st.write(", ".join(missing_required) if missing_required else "All configured required skills had matching text.")
            st.markdown("**Preferred**")
            st.write(", ".join(missing_preferred) if missing_preferred else "All configured preferred skills had matching text.")
            st.caption(f"Role text similarity: {selected['context_similarity']:.0%} (supporting signal)")

        with st.expander("Read extracted resume text"):
            st.warning("Resume text may contain personal information. Open it only when needed for a human review.")
            st.text(selected["text"])

        st.markdown("#### Record a human review")
        with st.form(f"review_form_{selected_id}"):
            current_status_index = REVIEW_STATUSES.index(selected["review_status"])
            new_status = st.selectbox("Review status", REVIEW_STATUSES, index=current_status_index, key=f"status_{selected_id}")
            st.caption("Keep the note job-related. Avoid sensitive personal information.")
            review_note = st.text_area("Reviewer note", value=selected["review_note"], key=f"note_{selected_id}", height=80)
            submit_review = st.form_submit_button("Save review", type="primary")
        if submit_review:
            saved_candidate = st.session_state.candidates[selected_id]
            update_review(
                DATABASE_PATH,
                selected_id,
                new_status,
                review_note.strip(),
            )
            saved_candidate["review_status"] = new_status
            saved_candidate["review_note"] = review_note.strip()
            st.session_state.audit_log.append(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "candidate_id": selected_id,
                    "human_review_status": new_status,
                    "match_signal_percent": selected["score"],
                }
            )
            st.session_state["review_saved"] = True
            st.rerun()
        if st.session_state.pop("review_saved", False):
            st.success("Human review saved to the local application history.")

        st.download_button(
            "Export pseudonymous review summary (CSV)",
            data=make_csv(candidate_summary_rows(ranked)),
            file_name="candidate_review_summary.csv",
            mime="text/csv",
        )

with history_tab:
    st.subheader("Application history")
    st.caption(
        "Application details and status changes are stored locally for at least 1 year. "
        "Records are not automatically deleted."
    )
    status_counts = {
        status: sum(record["review_status"] == status for record in stored_applications)
        for status in REVIEW_STATUSES
    }
    count_columns = st.columns(5)
    count_columns[0].metric("Applications", len(stored_applications))
    count_columns[1].metric("Needs review", status_counts["Needs review"])
    count_columns[2].metric("Selected", status_counts["Selected"])
    count_columns[3].metric("Rejected", status_counts["Rejected"])
    count_columns[4].metric("On hold", status_counts["On hold"])

    if not stored_applications:
        st.info("No applications are stored yet. Add a candidate to start building history.")
    else:
        available_roles = sorted({record["job_title"] for record in stored_applications})
        selected_roles = st.multiselect("Filter by role", available_roles)
        application_dates = [
            datetime.fromisoformat(record["applied_at_utc"]).date()
            for record in stored_applications
        ]
        date_range = st.date_input(
            "Filter by application date",
            value=(min(application_dates), max(application_dates)),
            min_value=min(application_dates),
            max_value=max(application_dates),
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range
        filtered_applications = [
            record
            for record in stored_applications
            if (not selected_roles or record["job_title"] in selected_roles)
            and start_date
            <= datetime.fromisoformat(record["applied_at_utc"]).date()
            <= end_date
        ]
        history_rows = [
            {
                "Candidate ID": record["candidate_id"],
                "Name": record["full_name"],
                "Email": record["email"],
                "Previous job role": record["previous_job_role"],
                "Latest job role": record["latest_job_role"],
                "Applied for": record["job_title"],
                "Applied on (UTC)": record["applied_at_utc"],
                "Match signal": record["match_signal_percent"],
                "ATS readiness": record["ats_readiness_percent"],
                "Status": record["review_status"],
                "Reviewed on (UTC)": record["reviewed_at_utc"] or "",
                "Reviewer note": record["reviewer_note"],
            }
            for record in filtered_applications
        ]
        st.caption(f"Showing {len(history_rows)} of {len(stored_applications)} applications.")
        if history_rows:
            st.dataframe(history_rows, hide_index=True, width="stretch")
            st.download_button(
                "Download filtered application history (CSV)",
                data=make_csv(history_rows),
                file_name="application_history.csv",
                mime="text/csv",
            )
        else:
            st.info("No applications match these filters.")

        application_ids = [record["candidate_id"] for record in filtered_applications]
        if application_ids:
            application_by_id = {
                record["candidate_id"]: record for record in filtered_applications
            }
            history_candidate_id = st.selectbox(
                "Open an older application",
                application_ids,
                format_func=lambda candidate_id: (
                    f"{application_by_id[candidate_id]['full_name']} — "
                    f"{application_by_id[candidate_id]['job_title']} "
                    f"({candidate_id})"
                ),
            )
            history_candidate = application_by_id[history_candidate_id]
            st.markdown(f"#### {history_candidate['full_name']} ({history_candidate_id})")
            st.write(
                f"**Email:** {history_candidate['email']} · "
                f"**Previous role:** {history_candidate['previous_job_role']} · "
                f"**Latest role:** {history_candidate['latest_job_role']}"
            )
            if history_candidate["resume_text"]:
                with st.expander("Read stored resume text"):
                    st.warning("Stored resume text may contain personal information.")
                    st.text(history_candidate["resume_text"])
            else:
                st.info("Resume text was not retained for this application.")

            with st.form(f"historical_review_form_{history_candidate_id}"):
                history_status = st.selectbox(
                    "Update review status",
                    REVIEW_STATUSES,
                    index=REVIEW_STATUSES.index(history_candidate["review_status"]),
                    key=f"history_status_{history_candidate_id}",
                )
                history_note = st.text_area(
                    "Reviewer note",
                    value=history_candidate["reviewer_note"],
                    key=f"history_note_{history_candidate_id}",
                )
                update_history_status = st.form_submit_button("Save historical review")
            if update_history_status:
                updated_record = update_review(
                    DATABASE_PATH,
                    history_candidate_id,
                    history_status,
                    history_note.strip(),
                )
                if history_candidate_id in st.session_state.candidates:
                    st.session_state.candidates[history_candidate_id][
                        "review_status"
                    ] = updated_record["review_status"]
                    st.session_state.candidates[history_candidate_id][
                        "review_note"
                    ] = updated_record["reviewer_note"]
                st.rerun()

with log_tab:
    st.subheader("Persistent review log")
    st.caption("Review status changes are kept with the application history in the local database.")
    persistent_review_history = list_review_history(DATABASE_PATH)
    if persistent_review_history:
        st.dataframe(persistent_review_history, hide_index=True, width="stretch")
        st.download_button(
            "Download review history (CSV)",
            data=make_csv(persistent_review_history),
            file_name="review_history.csv",
            mime="text/csv",
        )
    else:
        st.info("No review decisions have been recorded yet.")

with method_tab:
    st.subheader("How the match signal works")
    st.markdown(
        """
        1. **Required skills (70%)** compare recruiter-entered must-have skills to exact skill names and a small built-in alias list in the resume text.
        2. **Preferred skills (20%)** use the same evidence-based matching.
        3. **Role text similarity (10%)** compares job-description terms to the resume with local TF-IDF cosine similarity.

        When a category is empty, its weight is redistributed across the categories that remain. The score is rounded to a whole percent. The UI shows the evidence, gaps, and supporting role-text signal so a reviewer can challenge a match.
        """
    )
    st.markdown(
        """
        **ATS readiness (demo)** is separate from the role match signal. It awards 20 points for extractable resume text and 20 points each for recognizable Summary/Profile, Experience, Education, and Skills headings. It checks extracted text only; it cannot determine how a particular ATS parses layout, tables, columns, or formatting.
        """
    )
    st.warning("ATS readiness is not a standardized or validated hiring score. Treat it as a limited document-structure check only—not a standalone shortlisting threshold or an automatic selection/rejection criterion. Review the resume and job-related evidence directly.")
    st.warning("The score does not establish candidate quality, job performance, or fairness. It must not automatically reject or select applicants. Criteria and any selection process need job-specific validation and ongoing review.")
    st.subheader("Privacy and accessibility")
    st.markdown(
        """
        - Uploaded PDF/DOCX files are parsed locally and the original files are not saved. Candidate name, email, previous/latest job role, application details, score signals, and review history are stored in the local SQLite database for at least 1 year.
        - Extracted resume text is not stored unless the recruiter opts in. Without stored resume text, older application details and status remain available, but the resume itself cannot be reopened for review.
        - The SQLite database is not encrypted by this app. Protect the computer and database file with appropriate access controls, and back it up securely.
        - The app does not explicitly extract protected traits or personality. Its role-text similarity does read all extracted resume text, so personal details or proxy terms could still affect that signal. Resume content may contain personal data; use authorized data and clear the session when finished.
        - Scanned image-only PDFs need OCR before upload. This demo does not assess accommodation needs or replace accessible application channels.
        - A deployed service would need appropriate access control, retention rules, security review, monitoring, and applicant notice before processing real resumes.
        """
    )
    st.subheader("Recruiting and compliance context")
    st.markdown(
        """
        This portfolio demo illustrates structured, job-related criteria with human review. It is not a production selection system or a legal compliance tool. For use in India, employers should assess applicant-data processing against the Digital Personal Data Protection Act, 2023 and the rules and notifications in force, as well as applicable employment, equal-opportunity, and accessibility requirements. Applicability and obligations depend on the organization and use case; obtain India-qualified legal advice before processing real applicant data.
        """
    )
    st.markdown(
        "Sources: [Digital Personal Data Protection Act, 2023 — India Code](https://www.indiacode.nic.in/bitstream/123456789/22029/1/a2023-22.pdf) · "
        "[MeitY — Data Protection Framework](https://www.meity.gov.in/data-protection-framework) · "
        "[India Code — Central Acts](https://www.indiacode.nic.in/)"
    )
    st.caption("India-focused references reviewed 2 November 2026. Laws, rules, and their commencement can change; verify current applicability with qualified Indian counsel.")

st.divider()
st.caption("Portfolio demo · Synthetic candidates · No automated hiring decisions")
