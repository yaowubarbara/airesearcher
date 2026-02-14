"""Streamlit dashboard for the AI Academic Research Agent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("data/db/research.sqlite")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def safe_query(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    """Run a query and return results as list of dicts, empty list on error."""
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


# --- Page config ---

st.set_page_config(
    page_title="AI Researcher",
    page_icon="📚",
    layout="wide",
)

st.title("AI Academic Research Agent")

# Sidebar navigation
page = st.sidebar.radio(
    "Navigation",
    ["Overview", "Papers", "Topics", "Manuscripts", "LLM Usage"],
)

conn = get_conn()

# =============================================================================
# Overview page
# =============================================================================
if page == "Overview":
    st.header("Dashboard Overview")

    # Key metrics
    paper_count = safe_query(conn, "SELECT COUNT(*) as n FROM papers")
    topic_count = safe_query(conn, "SELECT COUNT(*) as n FROM topic_proposals")
    plan_count = safe_query(conn, "SELECT COUNT(*) as n FROM research_plans")
    ms_count = safe_query(conn, "SELECT COUNT(*) as n FROM manuscripts")
    memory_count = safe_query(conn, "SELECT COUNT(*) as n FROM reflexion_memory")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Papers", paper_count[0]["n"] if paper_count else 0)
    col2.metric("Topics", topic_count[0]["n"] if topic_count else 0)
    col3.metric("Plans", plan_count[0]["n"] if plan_count else 0)
    col4.metric("Manuscripts", ms_count[0]["n"] if ms_count else 0)
    col5.metric("Memories", memory_count[0]["n"] if memory_count else 0)

    st.divider()

    # Papers by journal
    st.subheader("Papers by Journal")
    journal_data = safe_query(
        conn, "SELECT journal, COUNT(*) as count FROM papers GROUP BY journal ORDER BY count DESC"
    )
    if journal_data:
        df = pd.DataFrame(journal_data)
        st.bar_chart(df.set_index("journal"))
    else:
        st.info("No papers indexed yet. Run `ai-researcher monitor` to get started.")

    # Papers by year
    st.subheader("Papers by Year")
    year_data = safe_query(
        conn,
        "SELECT year, COUNT(*) as count FROM papers WHERE year > 0 GROUP BY year ORDER BY year",
    )
    if year_data:
        df = pd.DataFrame(year_data)
        st.line_chart(df.set_index("year"))

    # Papers by language
    st.subheader("Papers by Language")
    lang_data = safe_query(
        conn, "SELECT language, COUNT(*) as count FROM papers GROUP BY language ORDER BY count DESC"
    )
    if lang_data:
        df = pd.DataFrame(lang_data)
        st.bar_chart(df.set_index("language"))

    # LLM cost summary
    st.subheader("LLM Cost Summary")
    cost_data = safe_query(
        conn,
        """SELECT model, SUM(total_tokens) as total_tokens,
           SUM(cost_usd) as total_cost, COUNT(*) as calls
           FROM llm_usage GROUP BY model ORDER BY total_cost DESC""",
    )
    if cost_data:
        df = pd.DataFrame(cost_data)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No LLM usage recorded yet.")


# =============================================================================
# Papers page
# =============================================================================
elif page == "Papers":
    st.header("Indexed Papers")

    # Filters
    col1, col2, col3 = st.columns(3)
    journals = safe_query(conn, "SELECT DISTINCT journal FROM papers ORDER BY journal")
    journal_names = ["All"] + [r["journal"] for r in journals]
    selected_journal = col1.selectbox("Journal", journal_names)

    languages = safe_query(conn, "SELECT DISTINCT language FROM papers ORDER BY language")
    lang_names = ["All"] + [r["language"] for r in languages]
    selected_lang = col2.selectbox("Language", lang_names)

    limit = col3.slider("Max results", 10, 500, 100)

    # Build query
    query = "SELECT id, title, authors, journal, year, language, doi FROM papers WHERE 1=1"
    params: list = []
    if selected_journal != "All":
        query += " AND journal = ?"
        params.append(selected_journal)
    if selected_lang != "All":
        query += " AND language = ?"
        params.append(selected_lang)
    query += " ORDER BY year DESC LIMIT ?"
    params.append(limit)

    papers = safe_query(conn, query, tuple(params))
    if papers:
        for p in papers:
            try:
                p["authors"] = ", ".join(json.loads(p["authors"])[:3])
            except (json.JSONDecodeError, TypeError):
                pass
        df = pd.DataFrame(papers)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No papers found. Run `ai-researcher monitor` to index papers.")

    # Paper detail
    if papers:
        st.subheader("Paper Detail")
        paper_id = st.selectbox(
            "Select paper", [p["id"] for p in papers], format_func=lambda x: next(
                (p["title"][:80] for p in papers if p["id"] == x), x
            )
        )
        if paper_id:
            detail = safe_query(conn, "SELECT * FROM papers WHERE id = ?", (paper_id,))
            if detail:
                d = detail[0]
                st.write(f"**Title:** {d['title']}")
                st.write(f"**Journal:** {d['journal']} ({d['year']})")
                st.write(f"**DOI:** {d.get('doi', 'N/A')}")
                if d.get("abstract"):
                    st.write(f"**Abstract:** {d['abstract'][:500]}...")
                keywords = json.loads(d.get("keywords", "[]"))
                if keywords:
                    st.write(f"**Keywords:** {', '.join(keywords)}")


# =============================================================================
# Topics page
# =============================================================================
elif page == "Topics":
    st.header("Research Topics & Gaps")

    topics = safe_query(
        conn,
        """SELECT id, title, research_question, overall_score, novelty_score,
           feasibility_score, journal_fit_score, timeliness_score, status
           FROM topic_proposals ORDER BY overall_score DESC LIMIT 50""",
    )

    if topics:
        df = pd.DataFrame(topics)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Topic detail
        st.subheader("Topic Detail")
        topic_id = st.selectbox(
            "Select topic",
            [t["id"] for t in topics],
            format_func=lambda x: next(
                (t["title"][:60] for t in topics if t["id"] == x), x
            ),
        )
        if topic_id:
            detail = safe_query(
                conn, "SELECT * FROM topic_proposals WHERE id = ?", (topic_id,)
            )
            if detail:
                t = detail[0]
                st.write(f"**Research Question:** {t['research_question']}")
                st.write(f"**Gap Description:** {t['gap_description']}")

                # Score breakdown
                scores = {
                    "Novelty": t["novelty_score"],
                    "Feasibility": t["feasibility_score"],
                    "Journal Fit": t["journal_fit_score"],
                    "Timeliness": t["timeliness_score"],
                    "Overall": t["overall_score"],
                }
                score_df = pd.DataFrame(
                    {"Score": list(scores.keys()), "Value": list(scores.values())}
                )
                st.bar_chart(score_df.set_index("Score"))

                # Associated plans
                plans = safe_query(
                    conn,
                    "SELECT id, thesis_statement, target_journal, status FROM research_plans WHERE topic_id = ?",
                    (topic_id,),
                )
                if plans:
                    st.write("**Research Plans:**")
                    for p in plans:
                        st.write(f"- [{p['status']}] {p['thesis_statement'][:100]} -> {p['target_journal']}")
    else:
        st.info("No topics discovered yet. Run `ai-researcher discover` to find research gaps.")


# =============================================================================
# Manuscripts page
# =============================================================================
elif page == "Manuscripts":
    st.header("Manuscripts")

    manuscripts = safe_query(
        conn,
        """SELECT id, title, target_journal, language, word_count, version, status
           FROM manuscripts ORDER BY created_at DESC LIMIT 20""",
    )

    if manuscripts:
        df = pd.DataFrame(manuscripts)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Manuscript detail
        st.subheader("Manuscript Detail")
        ms_id = st.selectbox(
            "Select manuscript",
            [m["id"] for m in manuscripts],
            format_func=lambda x: next(
                (m["title"][:60] for m in manuscripts if m["id"] == x), x
            ),
        )
        if ms_id:
            detail = safe_query(conn, "SELECT * FROM manuscripts WHERE id = ?", (ms_id,))
            if detail:
                m = detail[0]
                st.write(f"**Title:** {m['title']}")
                st.write(f"**Journal:** {m['target_journal']}")
                st.write(f"**Language:** {m['language']}")
                st.write(f"**Word Count:** {m['word_count']}")
                st.write(f"**Version:** {m['version']}")
                st.write(f"**Status:** {m['status']}")

                if m.get("abstract"):
                    st.subheader("Abstract")
                    st.write(m["abstract"])

                # Review scores
                scores = json.loads(m.get("review_scores", "{}"))
                if scores:
                    st.subheader("Review Scores")
                    score_df = pd.DataFrame(
                        {"Criterion": list(scores.keys()), "Score": list(scores.values())}
                    )
                    st.bar_chart(score_df.set_index("Criterion"))

                # Full text (expandable)
                if m.get("full_text"):
                    with st.expander("Full Text"):
                        st.text(m["full_text"][:10000])
    else:
        st.info("No manuscripts yet. Run `ai-researcher write <plan_id>` to generate one.")


# =============================================================================
# LLM Usage page
# =============================================================================
elif page == "LLM Usage":
    st.header("LLM Usage & Costs")

    # Summary by model
    st.subheader("Usage by Model")
    model_data = safe_query(
        conn,
        """SELECT model, COUNT(*) as calls, SUM(prompt_tokens) as prompt_tokens,
           SUM(completion_tokens) as completion_tokens, SUM(total_tokens) as total_tokens,
           SUM(cost_usd) as total_cost_usd, AVG(latency_ms) as avg_latency_ms,
           SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
           FROM llm_usage GROUP BY model ORDER BY total_cost_usd DESC""",
    )
    if model_data:
        df = pd.DataFrame(model_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Cost chart
        if any(r["total_cost_usd"] and r["total_cost_usd"] > 0 for r in model_data):
            cost_df = pd.DataFrame(
                {"Model": [r["model"] for r in model_data],
                 "Cost (USD)": [r["total_cost_usd"] or 0 for r in model_data]}
            )
            st.bar_chart(cost_df.set_index("Model"))

    # By task type
    st.subheader("Usage by Task Type")
    task_data = safe_query(
        conn,
        """SELECT task_type, COUNT(*) as calls, SUM(total_tokens) as total_tokens,
           SUM(cost_usd) as total_cost_usd
           FROM llm_usage GROUP BY task_type ORDER BY calls DESC""",
    )
    if task_data:
        df = pd.DataFrame(task_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # Recent calls
    st.subheader("Recent LLM Calls")
    recent = safe_query(
        conn,
        """SELECT model, task_type, prompt_tokens, completion_tokens,
           cost_usd, latency_ms, success, created_at
           FROM llm_usage ORDER BY created_at DESC LIMIT 50""",
    )
    if recent:
        df = pd.DataFrame(recent)
        st.dataframe(df, use_container_width=True, hide_index=True)

    if not model_data and not task_data:
        st.info("No LLM usage recorded yet. Run any AI-powered command to start tracking.")

    # Reflexion memories
    st.subheader("Reflexion Memory")
    memories = safe_query(
        conn,
        """SELECT category, observation, source, created_at
           FROM reflexion_memory ORDER BY created_at DESC LIMIT 30""",
    )
    if memories:
        df = pd.DataFrame(memories)
        st.dataframe(df, use_container_width=True, hide_index=True)

conn.close()
