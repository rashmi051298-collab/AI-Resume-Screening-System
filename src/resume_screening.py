"""Transparent, job-related resume matching helpers for the portfolio demo.

This module does not make hiring decisions. It compares recruiter-defined skills
and role text with resume text, then returns evidence for a human reviewer.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any


SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "python 3"),
    "sql": ("sql", "structured query language"),
    "excel": ("excel", "microsoft excel"),
    "power bi": ("power bi", "powerbi"),
    "tableau": ("tableau",),
    "looker": ("looker", "looker studio"),
    "dbt": ("dbt", "data build tool"),
    "apache spark": ("apache spark", "pyspark", "spark"),
    "airflow": ("airflow", "apache airflow"),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure", "microsoft azure"),
    "gcp": ("gcp", "google cloud platform", "google cloud"),
    "snowflake": ("snowflake",),
    "bigquery": ("bigquery", "big query"),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "mongodb": ("mongodb", "mongo db"),
    "git": ("git", "github", "gitlab"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "linux": ("linux",),
    "rest apis": ("rest api", "rest apis", "restful api", "restful apis"),
    "fastapi": ("fastapi",),
    "flask": ("flask",),
    "django": ("django",),
    "java": ("java",),
    "javascript": ("javascript", "ecmascript"),
    "typescript": ("typescript",),
    "react": ("react", "react.js", "reactjs"),
    "node.js": ("node.js", "nodejs"),
    "html/css": ("html", "css", "html/css"),
    "machine learning": ("machine learning", "ml"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch", "py torch"),
    "natural language processing": ("natural language processing", "nlp"),
    "scikit-learn": ("scikit-learn", "scikit learn", "sklearn"),
    "statistics": ("statistics", "statistical analysis", "statistical methods"),
    "a/b testing": ("a/b testing", "ab testing", "controlled experiments"),
    "experimentation": ("experimentation", "experiment design", "experiments"),
    "data visualization": ("data visualization", "data visualisation"),
    "stakeholder management": ("stakeholder management", "stakeholder communication"),
    "project management": ("project management", "project planning"),
    "communication": ("communication", "written communication", "presentation skills"),
    "agile": ("agile", "scrum", "kanban"),
    "cybersecurity": ("cybersecurity", "information security", "application security"),
    "ci/cd": ("ci/cd", "continuous integration", "continuous delivery", "continuous deployment"),
    "data storytelling": ("data storytelling", "storytelling with data"),
}

STOP_WORDS = {
    "a", "about", "above", "after", "again", "all", "also", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "of",
    "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves", "out", "over",
    "own", "same", "she", "should", "so", "some", "such", "than", "that", "the", "their",
    "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "will", "with", "would", "you", "your", "years",
    "year", "work", "working", "experience", "role", "team", "including", "using", "used", "use",
}

ATS_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "summary": re.compile(r"^(?:professional\s+)?(?:summary|profile|objective)$", re.IGNORECASE),
    "experience": re.compile(
        r"^(?:(?:professional|work)\s+)?(?:experience|employment(?:\s+history)?)$",
        re.IGNORECASE,
    ),
    "education": re.compile(r"^(?:education|academic\s+background)$", re.IGNORECASE),
    "skills": re.compile(
        r"^(?:(?:(?:technical|core)\s+)?skills|competencies)$",
        re.IGNORECASE,
    ),
}


def normalize_skill_list(raw_value: str) -> list[str]:
    """Split skill input and de-duplicate it without changing display casing."""
    skills: list[str] = []
    seen: set[str] = set()
    for raw_skill in re.split(r"[,;\n]+", raw_value):
        skill = re.sub(r"\s+", " ", raw_skill).strip()
        key = skill.casefold()
        if skill and key not in seen:
            skills.append(skill)
            seen.add(key)
    return skills


def assess_ats_readiness(text: str) -> dict[str, Any]:
    """Return a transparent, text-only resume parsing and section-structure signal."""
    normalized_lines = [
        re.sub(r"^[\W_]+|[\W_]+$", "", line).strip()
        for line in text.splitlines()
    ]
    sections = [
        name
        for name, pattern in ATS_SECTION_PATTERNS.items()
        if any(pattern.fullmatch(line) for line in normalized_lines)
    ]
    text_extractable = len(text.strip()) >= 40
    score = (20 if text_extractable else 0) + len(sections) * 20
    return {
        "score": score,
        "text_extractable": text_extractable,
        "sections_found": sections,
        "sections_total": len(ATS_SECTION_PATTERNS),
    }


def _skill_pattern(alias: str) -> re.Pattern[str]:
    escaped = re.escape(alias.strip()).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def _aliases_for(skill: str) -> tuple[str, ...]:
    aliases = SKILL_ALIASES.get(skill.casefold(), (skill,))
    return tuple(sorted(aliases, key=len, reverse=True))


def find_skill_evidence(text: str, skill: str) -> str | None:
    """Return the first sentence supporting an exact skill alias match."""
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    for alias in _aliases_for(skill):
        pattern = _skill_pattern(alias)
        for sentence in sentences:
            if pattern.search(sentence):
                return sentence[:360]
    return None


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+#./-]*", text)
        if len(token) > 1 and token.casefold() not in STOP_WORDS
    ]


def _tfidf_similarity_scores(job_text: str, resume_texts: list[str]) -> list[float]:
    """Compute local TF-IDF cosine similarity without an external service."""
    documents = [_tokens(job_text), *[_tokens(text) for text in resume_texts]]
    if not documents[0]:
        return [0.0] * len(resume_texts)

    document_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(set(document))
    document_count = len(documents)

    vectors: list[dict[str, float]] = []
    for document in documents:
        counts = Counter(document)
        vector = {
            token: (1.0 + math.log(count))
            * (math.log((document_count + 1) / (document_frequency[token] + 1)) + 1.0)
            for token, count in counts.items()
        }
        vectors.append(vector)

    query = vectors[0]
    query_norm = math.sqrt(sum(weight * weight for weight in query.values()))
    scores: list[float] = []
    for vector in vectors[1:]:
        norm = math.sqrt(sum(weight * weight for weight in vector.values()))
        if not query_norm or not norm:
            scores.append(0.0)
            continue
        dot = sum(weight * vector.get(token, 0.0) for token, weight in query.items())
        scores.append(max(0.0, min(1.0, dot / (query_norm * norm))))
    return scores


def rank_candidates(
    job: dict[str, Any], candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Score candidates against recruiter-defined criteria; highest first."""
    required = job.get("required_skills", [])
    preferred = job.get("preferred_skills", [])
    job_text = " ".join(part for part in (job.get("title", ""), job.get("description", "")) if part)
    context_scores = _tfidf_similarity_scores(
        job_text, [candidate.get("text", "") for candidate in candidates]
    )
    active_weights: dict[str, float] = {}
    if required:
        active_weights["required"] = 0.70
    if preferred:
        active_weights["preferred"] = 0.20
    if _tokens(job_text):
        active_weights["context"] = 0.10
    weight_total = sum(active_weights.values()) or 1.0
    active_weights = {key: value / weight_total for key, value in active_weights.items()}

    ranked: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        text = candidate.get("text", "")
        ats_readiness = assess_ats_readiness(text)
        required_evidence = {skill: find_skill_evidence(text, skill) for skill in required}
        preferred_evidence = {skill: find_skill_evidence(text, skill) for skill in preferred}
        required_match = sum(value is not None for value in required_evidence.values()) / len(required) if required else None
        preferred_match = sum(value is not None for value in preferred_evidence.values()) / len(preferred) if preferred else None
        context_match = context_scores[index] if index < len(context_scores) else 0.0

        parts: dict[str, float] = {}
        if required_match is not None:
            parts["required"] = required_match
        if preferred_match is not None:
            parts["preferred"] = preferred_match
        if "context" in active_weights:
            parts["context"] = context_match
        score = sum(parts[key] * active_weights[key] for key in parts) * 100

        ranked.append(
            {
                **candidate,
                "score": round(score),
                "ats_readiness_score": ats_readiness["score"],
                "ats_sections_found": ats_readiness["sections_found"],
                "ats_sections_total": ats_readiness["sections_total"],
                "ats_text_extractable": ats_readiness["text_extractable"],
                "required_evidence": required_evidence,
                "preferred_evidence": preferred_evidence,
                "required_matched": sum(value is not None for value in required_evidence.values()),
                "preferred_matched": sum(value is not None for value in preferred_evidence.values()),
                "required_total": len(required),
                "preferred_total": len(preferred),
                "context_similarity": context_match,
                "score_weights": active_weights,
            }
        )
    return sorted(ranked, key=lambda row: (-row["score"], row["candidate_id"]))


def parse_resume(filename: str, content: bytes) -> str:
    """Extract text from a PDF or DOCX resume held in memory."""
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("This PDF is password-protected. Export an unlocked copy to continue.")
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()

    if suffix == ".docx":
        from docx import Document

        document = Document(BytesIO(content))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
        return "\n".join(parts).strip()

    raise ValueError("Unsupported file type. Add a PDF or DOCX resume.")


def content_fingerprint(content: bytes) -> str:
    """Return a duplicate-detection hash; raw file bytes are not persisted."""
    return hashlib.sha256(content).hexdigest()
