"""SQLite database operations for the knowledge base."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import (
    Language,
    LLMUsageRecord,
    Manuscript,
    Paper,
    PaperStatus,
    Quotation,
    Reference,
    ReferenceType,
    ReflexionEntry,
    ResearchPlan,
    TopicProposal,
)

DEFAULT_DB_PATH = Path("data/db/research.sqlite")


class Database:
    """SQLite database for storing structured research data."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def initialize(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript(_SCHEMA)
        # Migration: add pdf_url column if missing (existing databases)
        try:
            self.conn.execute("SELECT pdf_url FROM papers LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE papers ADD COLUMN pdf_url TEXT")
        # Migration: add external_ids column if missing
        try:
            self.conn.execute("SELECT external_ids FROM papers LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE papers ADD COLUMN external_ids TEXT DEFAULT '{}'")
        # Migration: add ref_type column to references_ if missing
        try:
            self.conn.execute("SELECT ref_type FROM references_ LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute(
                "ALTER TABLE references_ ADD COLUMN ref_type TEXT NOT NULL DEFAULT 'unclassified'"
            )
        # Migration: create search_sessions tables if missing
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS search_sessions (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                found INTEGER DEFAULT 0,
                downloaded INTEGER DEFAULT 0,
                indexed INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_session_papers (
                session_id TEXT NOT NULL,
                paper_id TEXT NOT NULL,
                recommended INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (session_id, paper_id),
                FOREIGN KEY (session_id) REFERENCES search_sessions(id),
                FOREIGN KEY (paper_id) REFERENCES papers(id)
            );
        """)
        # Migration: add recommended column if missing
        try:
            self.conn.execute("SELECT recommended FROM search_session_papers LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute(
                "ALTER TABLE search_session_papers ADD COLUMN recommended INTEGER NOT NULL DEFAULT 0"
            )
        self.conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # --- Papers ---

    def insert_paper(self, paper: Paper) -> str:
        paper_id = paper.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO papers
            (id, title, authors, abstract, journal, year, volume, issue, pages,
             doi, semantic_scholar_id, openalex_id, language, keywords, status,
             pdf_path, url, pdf_url, external_ids, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                paper_id,
                paper.title,
                json.dumps(paper.authors),
                paper.abstract,
                paper.journal,
                paper.year,
                paper.volume,
                paper.issue,
                paper.pages,
                paper.doi,
                paper.semantic_scholar_id,
                paper.openalex_id,
                paper.language.value,
                json.dumps(paper.keywords),
                paper.status.value,
                paper.pdf_path,
                paper.url,
                paper.pdf_url,
                json.dumps(paper.external_ids),
                now,
                now,
            ),
        )
        self.conn.commit()
        return paper_id

    def get_paper(self, paper_id: str) -> Optional[Paper]:
        row = self.conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if row is None:
            return None
        return _row_to_paper(row)

    def get_paper_by_doi(self, doi: str) -> Optional[Paper]:
        row = self.conn.execute("SELECT * FROM papers WHERE doi = ?", (doi,)).fetchone()
        if row is None:
            return None
        return _row_to_paper(row)

    def search_papers(
        self,
        journal: Optional[str] = None,
        language: Optional[Language] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        status: Optional[PaperStatus] = None,
        limit: int = 100,
    ) -> list[Paper]:
        query = "SELECT * FROM papers WHERE 1=1"
        params: list = []
        if journal:
            query += " AND journal = ?"
            params.append(journal)
        if language:
            query += " AND language = ?"
            params.append(language.value)
        if year_from:
            query += " AND year >= ?"
            params.append(year_from)
        if year_to:
            query += " AND year <= ?"
            params.append(year_to)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY year DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_paper(r) for r in rows]

    def update_paper_status(self, paper_id: str, status: PaperStatus) -> None:
        self.conn.execute(
            "UPDATE papers SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, datetime.utcnow().isoformat(), paper_id),
        )
        self.conn.commit()

    def update_paper_pdf(
        self,
        paper_id: str,
        pdf_url: Optional[str] = None,
        pdf_path: Optional[str] = None,
        status: Optional[PaperStatus] = None,
    ) -> None:
        """Update PDF-related fields on a paper."""
        sets = []
        params: list = []
        if pdf_url is not None:
            sets.append("pdf_url = ?")
            params.append(pdf_url)
        if pdf_path is not None:
            sets.append("pdf_path = ?")
            params.append(pdf_path)
        if status is not None:
            sets.append("status = ?")
            params.append(status.value)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(paper_id)
        self.conn.execute(
            f"UPDATE papers SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()

    def get_papers_needing_pdf(self, limit: int = 200) -> list[Paper]:
        """Return papers that don't have a local PDF yet."""
        rows = self.conn.execute(
            """SELECT * FROM papers
            WHERE (pdf_path IS NULL OR pdf_path = '')
            AND status IN ('discovered', 'metadata_only')
            ORDER BY year DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [_row_to_paper(r) for r in rows]

    def get_paper_by_title_prefix(self, prefix: str) -> Optional[Paper]:
        """Find a paper whose title starts with the given prefix (case-insensitive)."""
        row = self.conn.execute(
            "SELECT * FROM papers WHERE LOWER(title) LIKE ? LIMIT 1",
            (prefix.lower() + "%",),
        ).fetchone()
        if row is None:
            return None
        return _row_to_paper(row)

    def search_papers_by_title(self, query: str, limit: int = 5) -> list[Paper]:
        """Search papers by title substring (case-insensitive LIKE search)."""
        rows = self.conn.execute(
            "SELECT * FROM papers WHERE LOWER(title) LIKE ? LIMIT ?",
            (f"%{query.lower()}%", limit),
        ).fetchall()
        return [_row_to_paper(r) for r in rows]

    def count_papers(self, journal: Optional[str] = None) -> int:
        if journal:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM papers WHERE journal = ?", (journal,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()
        return row[0]

    # --- References ---

    def insert_reference(self, ref: Reference) -> str:
        ref_id = ref.id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT OR IGNORE INTO references_
            (id, paper_id, title, authors, year, journal, volume, issue, pages,
             doi, publisher, ref_type, verified, verification_source,
             formatted_mla, formatted_chicago, formatted_gb)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ref_id,
                ref.paper_id,
                ref.title,
                json.dumps(ref.authors),
                ref.year,
                ref.journal,
                ref.volume,
                ref.issue,
                ref.pages,
                ref.doi,
                ref.publisher,
                ref.ref_type.value,
                ref.verified,
                ref.verification_source,
                ref.formatted_mla,
                ref.formatted_chicago,
                ref.formatted_gb,
            ),
        )
        self.conn.commit()
        return ref_id

    def get_verified_references(self, limit: int = 100) -> list[Reference]:
        rows = self.conn.execute(
            "SELECT * FROM references_ WHERE verified = 1 LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_reference(r) for r in rows]

    def get_reference_by_doi(self, doi: str) -> Optional[Reference]:
        row = self.conn.execute(
            "SELECT * FROM references_ WHERE doi = ?", (doi,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_reference(row)

    def mark_reference_verified(
        self, ref_id: str, source: str, mla: str = "", chicago: str = "", gb: str = ""
    ) -> None:
        self.conn.execute(
            """UPDATE references_ SET verified = 1, verification_source = ?,
            formatted_mla = ?, formatted_chicago = ?, formatted_gb = ?
            WHERE id = ?""",
            (source, mla, chicago, gb, ref_id),
        )
        self.conn.commit()

    def update_reference_type(self, ref_id: str, ref_type: ReferenceType) -> None:
        """Update the ref_type classification for a reference."""
        self.conn.execute(
            "UPDATE references_ SET ref_type = ? WHERE id = ?",
            (ref_type.value, ref_id),
        )
        self.conn.commit()

    def get_references_by_type(
        self, ref_type: ReferenceType, limit: int = 100
    ) -> list[Reference]:
        """Return references matching a given type."""
        rows = self.conn.execute(
            "SELECT * FROM references_ WHERE ref_type = ? LIMIT ?",
            (ref_type.value, limit),
        ).fetchall()
        return [_row_to_reference(r) for r in rows]

    def search_references_by_title(self, query: str, limit: int = 5) -> list[Reference]:
        """Search references by title substring (case-insensitive LIKE search)."""
        rows = self.conn.execute(
            "SELECT * FROM references_ WHERE LOWER(title) LIKE ? LIMIT ?",
            (f"%{query.lower()}%", limit),
        ).fetchall()
        return [_row_to_reference(r) for r in rows]

    # --- Quotations ---

    def insert_quotation(self, quot: Quotation) -> str:
        quot_id = quot.id or str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO quotations
            (id, paper_id, text, page, context, language, is_primary_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                quot_id,
                quot.paper_id,
                quot.text,
                quot.page,
                quot.context,
                quot.language.value,
                quot.is_primary_text,
            ),
        )
        self.conn.commit()
        return quot_id

    def get_quotations_for_paper(self, paper_id: str) -> list[Quotation]:
        rows = self.conn.execute(
            "SELECT * FROM quotations WHERE paper_id = ?", (paper_id,)
        ).fetchall()
        return [_row_to_quotation(r) for r in rows]

    # --- Topic Proposals ---

    def insert_topic(self, topic: TopicProposal) -> str:
        topic_id = topic.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO topic_proposals
            (id, title, research_question, gap_description, evidence_paper_ids,
             target_journals, novelty_score, feasibility_score, journal_fit_score,
             timeliness_score, overall_score, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                topic_id,
                topic.title,
                topic.research_question,
                topic.gap_description,
                json.dumps(topic.evidence_paper_ids),
                json.dumps(topic.target_journals),
                topic.novelty_score,
                topic.feasibility_score,
                topic.journal_fit_score,
                topic.timeliness_score,
                topic.overall_score,
                topic.status,
                now,
            ),
        )
        self.conn.commit()
        return topic_id

    def get_topics(self, status: Optional[str] = None, limit: int = 20) -> list[TopicProposal]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM topic_proposals WHERE status = ? ORDER BY overall_score DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM topic_proposals ORDER BY overall_score DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_topic(r) for r in rows]

    # --- Research Plans ---

    def insert_plan(self, plan: ResearchPlan) -> str:
        plan_id = plan.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO research_plans
            (id, topic_id, thesis_statement, target_journal, target_language,
             outline, reference_ids, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                plan_id,
                plan.topic_id,
                plan.thesis_statement,
                plan.target_journal,
                plan.target_language.value,
                json.dumps([s.model_dump() for s in plan.outline]),
                json.dumps(plan.reference_ids),
                plan.status,
                now,
            ),
        )
        self.conn.commit()
        return plan_id

    def get_plan(self, plan_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM research_plans WHERE id = ?", (plan_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ("outline", "reference_ids"):
            if field in result and isinstance(result[field], str):
                result[field] = json.loads(result[field])
        return result

    # --- Manuscripts ---

    def insert_manuscript(self, ms: Manuscript) -> str:
        ms_id = ms.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO manuscripts
            (id, plan_id, title, target_journal, language, sections, full_text,
             abstract, keywords, reference_ids, word_count, version, status,
             review_scores, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ms_id,
                ms.plan_id,
                ms.title,
                ms.target_journal,
                ms.language.value,
                json.dumps(ms.sections),
                ms.full_text,
                ms.abstract,
                json.dumps(ms.keywords),
                json.dumps(ms.reference_ids),
                ms.word_count,
                ms.version,
                ms.status,
                json.dumps(ms.review_scores),
                now,
                now,
            ),
        )
        self.conn.commit()
        return ms_id

    def update_manuscript(self, ms_id: str, **kwargs) -> None:
        sets = []
        params = []
        for key, value in kwargs.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            sets.append(f"{key} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(ms_id)
        self.conn.execute(
            f"UPDATE manuscripts SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()

    # --- Reflexion Memory ---

    def insert_reflexion(self, entry: ReflexionEntry) -> str:
        entry_id = entry.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO reflexion_memory
            (id, category, observation, source, manuscript_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (entry_id, entry.category, entry.observation, entry.source, entry.manuscript_id, now),
        )
        self.conn.commit()
        return entry_id

    def get_reflexion_memories(
        self, category: Optional[str] = None, limit: int = 50
    ) -> list[ReflexionEntry]:
        if category:
            rows = self.conn.execute(
                "SELECT * FROM reflexion_memory WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM reflexion_memory ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            ReflexionEntry(
                id=r["id"],
                category=r["category"],
                observation=r["observation"],
                source=r["source"],
                manuscript_id=r["manuscript_id"],
                created_at=datetime.fromisoformat(r["created_at"]) if r["created_at"] else None,
            )
            for r in rows
        ]

    # --- LLM Usage ---

    def insert_llm_usage(self, record: LLMUsageRecord) -> str:
        rec_id = record.id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO llm_usage
            (id, model, task_type, prompt_tokens, completion_tokens, total_tokens,
             cost_usd, latency_ms, success, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec_id,
                record.model,
                record.task_type,
                record.prompt_tokens,
                record.completion_tokens,
                record.total_tokens,
                record.cost_usd,
                record.latency_ms,
                record.success,
                now,
            ),
        )
        self.conn.commit()
        return rec_id

    def get_llm_usage_summary(self) -> dict:
        rows = self.conn.execute(
            """SELECT model, task_type, COUNT(*) as calls,
            SUM(total_tokens) as tokens, SUM(cost_usd) as cost
            FROM llm_usage GROUP BY model, task_type"""
        ).fetchall()
        return {f"{r['model']}:{r['task_type']}": dict(r) for r in rows}

    # --- Search Sessions ---

    def insert_search_session(
        self,
        session_id: str,
        query: str,
        paper_ids: list[str],
        found: int = 0,
        downloaded: int = 0,
        indexed: int = 0,
        created_at: Optional[str] = None,
        top_paper_ids: Optional[list[str]] = None,
    ) -> str:
        """Persist a search session and link papers to it.

        Args:
            top_paper_ids: IDs of papers recommended by LLM filtering.
                           If None, all papers are marked as recommended.
        """
        now = created_at or datetime.utcnow().isoformat()
        top_set = set(top_paper_ids) if top_paper_ids is not None else set(paper_ids)
        self.conn.execute(
            """INSERT OR REPLACE INTO search_sessions
            (id, query, found, downloaded, indexed, created_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, query, found, downloaded, indexed, now),
        )
        for pid in paper_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO search_session_papers (session_id, paper_id, recommended) VALUES (?, ?, ?)",
                (session_id, pid, 1 if pid in top_set else 0),
            )
        self.conn.commit()
        return session_id

    def get_search_sessions(self) -> list[dict]:
        """Return all search sessions, newest first.

        Each session includes paper_ids and recommended_ids (LLM-filtered subset).
        """
        rows = self.conn.execute(
            "SELECT * FROM search_sessions ORDER BY created_at DESC"
        ).fetchall()
        sessions = []
        for r in rows:
            links = self.conn.execute(
                "SELECT paper_id, recommended FROM search_session_papers WHERE session_id = ?",
                (r["id"],),
            ).fetchall()
            paper_ids = [row[0] for row in links]
            recommended_ids = [row[0] for row in links if row[1]]
            sessions.append({
                "id": r["id"],
                "query": r["query"],
                "found": r["found"],
                "downloaded": r["downloaded"],
                "indexed": r["indexed"],
                "paper_ids": paper_ids,
                "recommended_ids": recommended_ids,
                "created_at": r["created_at"],
            })
        return sessions

    def get_session_paper_ids(self, session_id: str) -> list[str]:
        """Return paper IDs linked to a session."""
        rows = self.conn.execute(
            "SELECT paper_id FROM search_session_papers WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def add_papers_to_session(
        self, session_id: str, paper_ids: list[str], recommended: bool = False
    ) -> int:
        """Link additional papers to an existing session. Returns count added."""
        added = 0
        for pid in paper_ids:
            try:
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO search_session_papers (session_id, paper_id, recommended) VALUES (?, ?, ?)",
                    (session_id, pid, 1 if recommended else 0),
                )
                added += cursor.rowcount
            except Exception:
                pass
        self.conn.commit()
        return added

    def get_session_papers(self, session_id: str) -> list[Paper]:
        """Return full Paper objects for a session, ordered by year DESC."""
        rows = self.conn.execute(
            """SELECT p.*, ssp.recommended
            FROM papers p
            JOIN search_session_papers ssp ON p.id = ssp.paper_id
            WHERE ssp.session_id = ?
            ORDER BY p.year DESC""",
            (session_id,),
        ).fetchall()
        return [_row_to_paper(r) for r in rows]

    def get_session_papers_with_recommended(self, session_id: str) -> list[tuple[Paper, bool]]:
        """Return (Paper, recommended) tuples for a session, ordered by year DESC."""
        rows = self.conn.execute(
            """SELECT p.*, ssp.recommended
            FROM papers p
            JOIN search_session_papers ssp ON p.id = ssp.paper_id
            WHERE ssp.session_id = ?
            ORDER BY p.year DESC""",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            paper = _row_to_paper(r)
            recommended = bool(r["recommended"])
            result.append((paper, recommended))
        return result


# --- Row converters ---


def _row_to_paper(row: sqlite3.Row) -> Paper:
    return Paper(
        id=row["id"],
        title=row["title"],
        authors=json.loads(row["authors"]),
        abstract=row["abstract"],
        journal=row["journal"],
        year=row["year"],
        volume=row["volume"],
        issue=row["issue"],
        pages=row["pages"],
        doi=row["doi"],
        semantic_scholar_id=row["semantic_scholar_id"],
        openalex_id=row["openalex_id"],
        language=Language(row["language"]),
        keywords=json.loads(row["keywords"]),
        status=PaperStatus(row["status"]),
        pdf_path=row["pdf_path"],
        url=row["url"],
        pdf_url=row["pdf_url"] if "pdf_url" in row.keys() else None,
        external_ids=json.loads(row["external_ids"]) if "external_ids" in row.keys() and row["external_ids"] else {},
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
    )


def _row_to_reference(row: sqlite3.Row) -> Reference:
    ref_type_val = row["ref_type"] if "ref_type" in row.keys() else "unclassified"
    return Reference(
        id=row["id"],
        paper_id=row["paper_id"],
        title=row["title"],
        authors=json.loads(row["authors"]),
        year=row["year"],
        journal=row["journal"],
        volume=row["volume"],
        issue=row["issue"],
        pages=row["pages"],
        doi=row["doi"],
        publisher=row["publisher"],
        ref_type=ReferenceType(ref_type_val),
        verified=bool(row["verified"]),
        verification_source=row["verification_source"],
        formatted_mla=row["formatted_mla"],
        formatted_chicago=row["formatted_chicago"],
        formatted_gb=row["formatted_gb"],
    )


def _row_to_quotation(row: sqlite3.Row) -> Quotation:
    return Quotation(
        id=row["id"],
        paper_id=row["paper_id"],
        text=row["text"],
        page=row["page"],
        context=row["context"],
        language=Language(row["language"]),
        is_primary_text=bool(row["is_primary_text"]),
    )


def _row_to_topic(row: sqlite3.Row) -> TopicProposal:
    return TopicProposal(
        id=row["id"],
        title=row["title"],
        research_question=row["research_question"],
        gap_description=row["gap_description"],
        evidence_paper_ids=json.loads(row["evidence_paper_ids"]),
        target_journals=json.loads(row["target_journals"]),
        novelty_score=row["novelty_score"],
        feasibility_score=row["feasibility_score"],
        journal_fit_score=row["journal_fit_score"],
        timeliness_score=row["timeliness_score"],
        overall_score=row["overall_score"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
    )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    abstract TEXT,
    journal TEXT NOT NULL,
    year INTEGER NOT NULL,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    doi TEXT UNIQUE,
    semantic_scholar_id TEXT,
    openalex_id TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    keywords TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'discovered',
    pdf_path TEXT,
    url TEXT,
    pdf_url TEXT,
    external_ids TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_papers_journal ON papers(journal);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_language ON papers(language);

CREATE TABLE IF NOT EXISTS references_ (
    id TEXT PRIMARY KEY,
    paper_id TEXT,
    title TEXT NOT NULL,
    authors TEXT NOT NULL DEFAULT '[]',
    year INTEGER NOT NULL,
    journal TEXT,
    volume TEXT,
    issue TEXT,
    pages TEXT,
    doi TEXT,
    publisher TEXT,
    ref_type TEXT NOT NULL DEFAULT 'unclassified',
    verified INTEGER NOT NULL DEFAULT 0,
    verification_source TEXT,
    formatted_mla TEXT,
    formatted_chicago TEXT,
    formatted_gb TEXT,
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);

CREATE INDEX IF NOT EXISTS idx_refs_doi ON references_(doi);
CREATE INDEX IF NOT EXISTS idx_refs_verified ON references_(verified);

CREATE TABLE IF NOT EXISTS quotations (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL,
    text TEXT NOT NULL,
    page TEXT,
    context TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    is_primary_text INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);

CREATE TABLE IF NOT EXISTS topic_proposals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    research_question TEXT NOT NULL,
    gap_description TEXT NOT NULL,
    evidence_paper_ids TEXT NOT NULL DEFAULT '[]',
    target_journals TEXT NOT NULL DEFAULT '[]',
    novelty_score REAL DEFAULT 0,
    feasibility_score REAL DEFAULT 0,
    journal_fit_score REAL DEFAULT 0,
    timeliness_score REAL DEFAULT 0,
    overall_score REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS research_plans (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL,
    thesis_statement TEXT NOT NULL,
    target_journal TEXT NOT NULL,
    target_language TEXT NOT NULL DEFAULT 'en',
    outline TEXT NOT NULL DEFAULT '[]',
    reference_ids TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT,
    FOREIGN KEY (topic_id) REFERENCES topic_proposals(id)
);

CREATE TABLE IF NOT EXISTS manuscripts (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    title TEXT NOT NULL,
    target_journal TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    sections TEXT NOT NULL DEFAULT '{}',
    full_text TEXT,
    abstract TEXT,
    keywords TEXT NOT NULL DEFAULT '[]',
    reference_ids TEXT NOT NULL DEFAULT '[]',
    word_count INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'drafting',
    review_scores TEXT NOT NULL DEFAULT '{}',
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (plan_id) REFERENCES research_plans(id)
);

CREATE TABLE IF NOT EXISTS reflexion_memory (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    observation TEXT NOT NULL,
    source TEXT NOT NULL,
    manuscript_id TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reflexion_category ON reflexion_memory(category);

CREATE TABLE IF NOT EXISTS llm_usage (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    task_type TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS search_sessions (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    found INTEGER DEFAULT 0,
    downloaded INTEGER DEFAULT 0,
    indexed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_session_papers (
    session_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    recommended INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, paper_id),
    FOREIGN KEY (session_id) REFERENCES search_sessions(id),
    FOREIGN KEY (paper_id) REFERENCES papers(id)
);
"""
