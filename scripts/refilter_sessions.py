#!/usr/bin/env python3
"""Re-filter historical search sessions using LLM to mark only relevant papers as recommended."""

import json
import re
import sqlite3
import time
from pathlib import Path

import httpx

DB_PATH = Path("data/db/research.sqlite")
OPENROUTER_API_KEY = "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"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MODEL = "google/gemini-2.0-flash-001"

# Sessions to skip (small/misc)
SKIP_QUERIES = {
    "Earlier CLI searches (2/14)",
    "Earlier searches (2/15 misc)",
}

BATCH_SIZE = 100


def get_sessions(conn: sqlite3.Connection) -> list[dict]:
    """Get all search sessions."""
    cur = conn.execute(
        "SELECT id, query, found, created_at FROM search_sessions ORDER BY created_at"
    )
    rows = cur.fetchall()
    return [
        {"id": row[0], "query": row[1], "found": row[2], "created_at": row[3]}
        for row in rows
    ]


def get_session_papers(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """Get all papers linked to a session."""
    cur = conn.execute(
        """
        SELECT ssp.paper_id, p.title, ssp.recommended
        FROM search_session_papers ssp
        JOIN papers p ON p.id = ssp.paper_id
        WHERE ssp.session_id = ?
        ORDER BY p.title
        """,
        (session_id,),
    )
    rows = cur.fetchall()
    return [
        {"paper_id": row[0], "title": row[1], "recommended": row[2]}
        for row in rows
    ]


def call_llm(query: str, titles: list[str], retries: int = 3) -> list[int]:
    """Call OpenRouter LLM to filter papers. Returns 1-indexed list of relevant paper numbers."""
    numbered_list = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))

    prompt = f"""You are an academic research assistant. Given a search query and a numbered list of paper titles, select ONLY the papers that are clearly relevant to the research topic.

Search query: {query}

Papers:
{numbered_list}

Return ONLY a JSON array of the relevant paper numbers (1-indexed). Be selective — only include papers that are genuinely about the topic, not tangentially related."""

    for attempt in range(retries):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    f"{OPENROUTER_BASE}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Parse JSON array from response — handle markdown fences
                content = re.sub(r"```json\s*", "", content)
                content = re.sub(r"```\s*", "", content)
                content = content.strip()

                # Find the JSON array in the response
                match = re.search(r"\[[\s\S]*?\]", content)
                if match:
                    indices = json.loads(match.group())
                    # Validate all are ints and in range
                    valid = [
                        int(x) for x in indices
                        if isinstance(x, (int, float)) and 1 <= int(x) <= len(titles)
                    ]
                    return valid
                else:
                    print(f"    WARNING: No JSON array found in response: {content[:200]}")
                    return list(range(1, len(titles) + 1))  # Keep all if parse fails

        except Exception as e:
            wait = 5 * (2 ** attempt)
            print(f"    ERROR (attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                print(f"    Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print("    FAILED after all retries — keeping all papers as recommended")
                return list(range(1, len(titles) + 1))

    return list(range(1, len(titles) + 1))


def filter_session(conn: sqlite3.Connection, session: dict) -> dict:
    """Filter papers in a session using LLM. Returns stats."""
    session_id = session["id"]
    query = session["query"]
    papers = get_session_papers(conn, session_id)

    if not papers:
        return {"total": 0, "selected": 0, "removed": 0}

    total = len(papers)
    print(f"\n  Session: {query}")
    print(f"  Papers: {total}")

    # Process in batches
    all_selected_ids = set()

    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch = papers[batch_start:batch_end]
        batch_titles = [p["title"] for p in batch]

        if total > BATCH_SIZE:
            print(f"    Batch {batch_start // BATCH_SIZE + 1}: papers {batch_start+1}-{batch_end}")

        selected_indices = call_llm(query, batch_titles)

        # Map 1-indexed back to paper_ids
        for idx in selected_indices:
            paper = batch[idx - 1]  # 1-indexed to 0-indexed
            all_selected_ids.add(paper["paper_id"])

        # Rate limit between batches
        if batch_end < total:
            time.sleep(1)

    # Update database: set recommended=0 for all, then recommended=1 for selected
    conn.execute(
        "UPDATE search_session_papers SET recommended = 0 WHERE session_id = ?",
        (session_id,),
    )
    if all_selected_ids:
        placeholders = ",".join("?" for _ in all_selected_ids)
        conn.execute(
            f"UPDATE search_session_papers SET recommended = 1 WHERE session_id = ? AND paper_id IN ({placeholders})",
            [session_id] + list(all_selected_ids),
        )
    conn.commit()

    selected = len(all_selected_ids)
    removed = total - selected
    print(f"  Result: {selected} selected, {removed} removed")

    return {"total": total, "selected": selected, "removed": removed}


def main():
    print("=" * 70)
    print("Re-filtering search sessions with LLM relevance check")
    print("=" * 70)

    conn = sqlite3.connect(str(DB_PATH))

    sessions = get_sessions(conn)
    print(f"\nFound {len(sessions)} sessions total")

    # Show what we'll skip
    skip_sessions = [s for s in sessions if s["query"] in SKIP_QUERIES]
    work_sessions = [s for s in sessions if s["query"] not in SKIP_QUERIES]
    print(f"Skipping {len(skip_sessions)} misc sessions:")
    for s in skip_sessions:
        print(f"  - {s['query']}")
    print(f"Processing {len(work_sessions)} sessions")

    total_stats = {"total": 0, "selected": 0, "removed": 0}

    for session in work_sessions:
        stats = filter_session(conn, session)
        total_stats["total"] += stats["total"]
        total_stats["selected"] += stats["selected"]
        total_stats["removed"] += stats["removed"]

    # Final summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total papers processed: {total_stats['total']}")
    print(f"Selected as relevant:   {total_stats['selected']}")
    print(f"Removed as irrelevant:  {total_stats['removed']}")
    if total_stats["total"] > 0:
        pct = total_stats["selected"] / total_stats["total"] * 100
        print(f"Selection rate:         {pct:.1f}%")

    # Show final state per session
    print("\nFinal state per session:")
    for session in sessions:
        cur = conn.execute(
            "SELECT COUNT(*), SUM(recommended) FROM search_session_papers WHERE session_id = ?",
            (session["id"],),
        )
        row = cur.fetchone()
        total_p = row[0] or 0
        rec_p = row[1] or 0
        marker = " (skipped)" if session["query"] in SKIP_QUERIES else ""
        print(f"  [{rec_p}/{total_p}] {session['query']}{marker}")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
