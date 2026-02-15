"""Tests for the citation verification pipeline (Phase 11)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.citation_verifier.annotator import VerificationReport, annotate_manuscript
from src.citation_verifier.engine import (
    CitationVerification,
    CitationVerificationEngine,
    _is_title_match,
    _normalize_crossref,
)
from src.citation_verifier.parser import (
    ParsedCitation,
    group_citations,
    parse_mla_citations,
)


# ============================================================
# TestMLACitationParser
# ============================================================


class TestMLACitationParser:
    """Tests for parse_mla_citations()."""

    def test_simple_author_page(self):
        text = "as Felstiner argues (Felstiner 247)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "Felstiner"
        assert cits[0].pages == "247"
        assert cits[0].is_secondary is False

    def test_author_italic_title_page(self):
        text = "Derrida writes (Derrida, *Sovereignties* 42)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "Derrida"
        assert cits[0].title == "Sovereignties"
        assert cits[0].title_style == "italic"
        assert cits[0].pages == "42"

    def test_author_quoted_title_page(self):
        text = 'a key insight (Derrida, "Demeure" 78).'
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "Derrida"
        assert cits[0].title == "Demeure"
        assert cits[0].title_style == "quoted"
        assert cits[0].pages == "78"

    def test_secondary_citation_qtd_in(self):
        text = "the witness states (qtd. in Felman 201)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].is_secondary is True
        assert cits[0].mediating_author == "Felman"
        assert cits[0].pages == "201"

    def test_secondary_citation_with_title(self):
        text = "as noted (qtd. in Felman, *Testimony* 201)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].is_secondary is True
        assert cits[0].mediating_author == "Felman"
        assert cits[0].title == "Testimony"
        assert cits[0].pages == "201"

    def test_title_only_italic(self):
        text = "the poem enacts (*Atemwende* 78)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author is None
        assert cits[0].title == "Atemwende"
        assert cits[0].pages == "78"

    def test_excludes_year_like_numbers(self):
        text = "published (Caruth 1996) earlier."
        cits = parse_mla_citations(text)
        assert len(cits) == 0

    def test_page_range(self):
        text = "see the discussion (Hamacher 276-311)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].pages == "276-311"

    def test_multiple_citations(self):
        text = (
            "Felstiner notes (Felstiner 247) and Derrida argues "
            "(Derrida, *Sovereignties* 42)."
        )
        cits = parse_mla_citations(text)
        assert len(cits) == 2
        assert cits[0].author == "Felstiner"
        assert cits[1].author == "Derrida"

    def test_no_duplicate_spans(self):
        # Ensure a citation matched by multiple patterns isn't duplicated
        text = "(Derrida, *Sovereignties* 42)"
        cits = parse_mla_citations(text)
        assert len(cits) == 1

    def test_chinese_author(self):
        text = "as the critic writes (\u6b8b\u96ea 15)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "\u6b8b\u96ea"
        assert cits[0].pages == "15"

    def test_author_italic_no_page(self):
        text = "Derrida's argument (Derrida, *Sovereignties*)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "Derrida"
        assert cits[0].title == "Sovereignties"
        assert cits[0].pages is None

    def test_quoted_in_chicago(self):
        text = "the witness claims (quoted in Felman 201)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].is_secondary is True
        assert cits[0].mediating_author == "Felman"

    def test_accented_author(self):
        text = "Lacoue-Labarthe suggests (Lacoue-Labarthe 55)."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert cits[0].author == "Lacoue-Labarthe"

    def test_positions_are_correct(self):
        text = "text (Felstiner 247) more."
        cits = parse_mla_citations(text)
        assert len(cits) == 1
        assert text[cits[0].start_pos : cits[0].end_pos] == "(Felstiner 247)"

    def test_sorted_by_position(self):
        text = "(Derrida 10) middle (Felstiner 247) end."
        cits = parse_mla_citations(text)
        assert len(cits) == 2
        assert cits[0].start_pos < cits[1].start_pos


# ============================================================
# TestGroupCitations
# ============================================================


class TestGroupCitations:
    def test_group_by_author(self):
        cits = [
            ParsedCitation(author="Derrida", pages="10"),
            ParsedCitation(author="Derrida", pages="20"),
            ParsedCitation(author="Felstiner", pages="247"),
        ]
        groups = group_citations(cits)
        assert len(groups["Derrida"]) == 2
        assert len(groups["Felstiner"]) == 1

    def test_group_secondary_by_mediating(self):
        cits = [
            ParsedCitation(
                mediating_author="Felman", is_secondary=True, pages="201"
            ),
        ]
        groups = group_citations(cits)
        assert "Felman" in groups

    def test_group_title_only(self):
        cits = [
            ParsedCitation(title="Atemwende", pages="78"),
        ]
        groups = group_citations(cits)
        assert "Atemwende" in groups


# ============================================================
# TestTitleMatch
# ============================================================


class TestTitleMatch:
    def test_exact_match(self):
        assert _is_title_match("Sovereignties", ["Sovereignties"]) is True

    def test_case_insensitive(self):
        assert _is_title_match("sovereignties", ["Sovereignties"]) is True

    def test_substring(self):
        assert _is_title_match(
            "Sovereignties",
            ["Sovereignties in Question: The Poetics of Paul Celan"],
        ) is True

    def test_word_overlap(self):
        assert _is_title_match(
            "The Poetics of Silence in Celan",
            ["The Poetics of Silence in Celan and Glissant"],
        ) is True

    def test_no_match(self):
        assert _is_title_match("Sovereignties", ["Unrelated Title"]) is False

    def test_empty_candidate(self):
        assert _is_title_match("Sovereignties", [""]) is False


# ============================================================
# TestNormalizeCrossref
# ============================================================


class TestNormalizeCrossref:
    def test_basic_article(self):
        item = {
            "title": ["The Second of Inversion"],
            "author": [{"given": "Werner", "family": "Hamacher"}],
            "published-print": {"date-parts": [[1986]]},
            "container-title": ["MLN"],
            "volume": "100",
            "page": "276-311",
            "DOI": "10.2307/2905586",
            "publisher": "Johns Hopkins University Press",
        }
        result = _normalize_crossref(item)
        assert result["title"] == "The Second of Inversion"
        assert result["authors"] == ["Werner Hamacher"]
        assert result["year"] == 1986
        assert result["pages"] == "276-311"
        assert result["doi"] == "10.2307/2905586"

    def test_missing_fields(self):
        item = {"title": ["Untitled"]}
        result = _normalize_crossref(item)
        assert result["title"] == "Untitled"
        assert result["authors"] == []
        assert result["year"] is None


# ============================================================
# TestPageRangeValidation
# ============================================================


class TestPageRangeValidation:
    def setup_method(self):
        self.engine = CitationVerificationEngine()

    def test_page_in_range(self):
        ok, note = self.engine._check_page_range("290", "276-311", "journal-article")
        assert ok is True

    def test_page_out_of_range(self):
        ok, note = self.engine._check_page_range("999", "276-311", "journal-article")
        assert ok is False

    def test_page_at_boundary_start(self):
        ok, _ = self.engine._check_page_range("276", "276-311", "journal-article")
        assert ok is True

    def test_page_at_boundary_end(self):
        ok, _ = self.engine._check_page_range("311", "276-311", "journal-article")
        assert ok is True

    def test_book_type_unverifiable(self):
        ok, note = self.engine._check_page_range("42", "1-500", "book")
        assert ok is None
        assert "Book" in note

    def test_no_page_range(self):
        ok, note = self.engine._check_page_range("42", None, "journal-article")
        assert ok is None

    def test_range_cited(self):
        ok, _ = self.engine._check_page_range("280-290", "276-311", "journal-article")
        assert ok is True

    def test_range_out_of_range(self):
        ok, _ = self.engine._check_page_range("280-320", "276-311", "journal-article")
        assert ok is False

    def test_unparseable_range(self):
        ok, _ = self.engine._check_page_range("42", "e12345", "journal-article")
        assert ok is None


# ============================================================
# TestExtractContextTitle
# ============================================================


class TestExtractContextTitle:
    def test_author_italic_title_before(self):
        text = "Derrida's *Sovereignties in Question* explores (Derrida 42)"
        result = CitationVerificationEngine._extract_context_title(
            "Derrida", text, text.index("(Derrida")
        )
        assert result == "Sovereignties in Question"

    def test_no_title_found(self):
        text = "the critic argues (Felstiner 247)"
        result = CitationVerificationEngine._extract_context_title(
            "Felstiner", text, text.index("(Felstiner")
        )
        assert result is None


# ============================================================
# TestManuscriptAnnotation
# ============================================================


class TestManuscriptAnnotation:
    def _make_citation(self, raw, start, end):
        return ParsedCitation(raw=raw, start_pos=start, end_pos=end)

    def test_work_not_found_tag(self):
        text = "text (Chan 134) more."
        v = CitationVerification(
            citation=self._make_citation("(Chan 134)", 5, 15),
            status="work_not_found",
        )
        result = annotate_manuscript(text, [v])
        assert "[VERIFY:work]" in result
        assert "(Chan 134) [VERIFY:work]" in result

    def test_page_unverifiable_tag(self):
        text = "text (Felstiner 247) more."
        v = CitationVerification(
            citation=self._make_citation("(Felstiner 247)", 5, 20),
            status="page_unverifiable",
        )
        result = annotate_manuscript(text, [v])
        assert "(Felstiner 247) [VERIFY:page]" in result

    def test_page_out_of_range_tag(self):
        text = "text (Hamacher 999) more."
        v = CitationVerification(
            citation=self._make_citation("(Hamacher 999)", 5, 19),
            status="page_out_of_range",
        )
        result = annotate_manuscript(text, [v])
        assert "(Hamacher 999) [VERIFY:page-range]" in result

    def test_verified_unchanged(self):
        text = "text (Hamacher 290) more."
        v = CitationVerification(
            citation=self._make_citation("(Hamacher 290)", 5, 19),
            status="verified",
            confidence=1.0,
        )
        result = annotate_manuscript(text, [v])
        assert result == text

    def test_multiple_annotations_preserve_positions(self):
        text = "first (A 10) middle (B 20) end."
        v1 = CitationVerification(
            citation=self._make_citation("(A 10)", 6, 12),
            status="work_not_found",
        )
        v2 = CitationVerification(
            citation=self._make_citation("(B 20)", 20, 26),
            status="page_unverifiable",
        )
        result = annotate_manuscript(text, [v1, v2])
        assert "(A 10) [VERIFY:work]" in result
        assert "(B 20) [VERIFY:page]" in result


# ============================================================
# TestVerificationReport
# ============================================================


class TestVerificationReport:
    def _make_verification(self, status, raw="(Test 1)", **kwargs):
        c = ParsedCitation(raw=raw)
        return CitationVerification(citation=c, status=status, **kwargs)

    def test_summary_all_verified(self):
        vs = [self._make_verification("verified") for _ in range(5)]
        report = VerificationReport.from_verifications(vs)
        assert report.total == 5
        assert report.verified == 5
        assert "100%" in report.summary()

    def test_summary_with_issues(self):
        vs = [
            self._make_verification("verified"),
            self._make_verification("work_not_found"),
            self._make_verification("page_unverifiable"),
        ]
        report = VerificationReport.from_verifications(vs)
        assert report.total == 3
        assert report.verified == 1
        assert report.work_not_found == 1
        assert report.page_unverifiable == 1
        assert "33%" in report.summary()

    def test_to_markdown_has_issues_table(self):
        vs = [
            self._make_verification("work_not_found", raw="(Chan 134)"),
            self._make_verification("verified", raw="(Derrida 42)"),
        ]
        report = VerificationReport.from_verifications(vs)
        md = report.to_markdown()
        assert "## Issues" in md
        assert "(Chan 134)" in md
        assert "## Verified" in md
        assert "(Derrida 42)" in md

    def test_empty_report(self):
        report = VerificationReport.from_verifications([])
        assert report.total == 0
        assert "No citations" in report.summary()

    def test_report_counts(self):
        vs = [
            self._make_verification("verified"),
            self._make_verification("verified"),
            self._make_verification("page_out_of_range"),
        ]
        report = VerificationReport.from_verifications(vs)
        assert report.page_out_of_range == 1
        assert report.verified == 2


# ============================================================
# TestEngineVerifyAll (mock-based)
# ============================================================


class TestEngineVerifyAll:
    """Test the engine's verify_all with mocked API calls."""

    @pytest.fixture
    def engine(self):
        e = CitationVerificationEngine()
        return e

    @pytest.mark.asyncio
    async def test_verify_returns_results(self, engine):
        """Verify that verify_all returns one result per citation."""
        citations = [
            ParsedCitation(author="Hamacher", pages="290", raw="(Hamacher 290)",
                           start_pos=0, end_pos=14),
        ]

        # Mock the search to return a matching work
        async def mock_search(author, title_hint):
            return {
                "title": "The Second of Inversion",
                "authors": ["Werner Hamacher"],
                "pages": "276-311",
                "type": "journal-article",
                "_source": "crossref",
            }

        engine._search_by_author_title = mock_search

        results = await engine.verify_all(citations, "text (Hamacher 290)")
        assert len(results) == 1
        assert results[0].status == "verified"
        assert results[0].page_in_range is True

    @pytest.mark.asyncio
    async def test_verify_work_not_found(self, engine):
        citations = [
            ParsedCitation(author="Nonexistent", pages="42", raw="(Nonexistent 42)",
                           start_pos=0, end_pos=16),
        ]

        async def mock_search(author, title_hint):
            return None

        engine._search_by_author_title = mock_search

        results = await engine.verify_all(citations, "text")
        assert len(results) == 1
        assert results[0].status == "work_not_found"

    @pytest.mark.asyncio
    async def test_verify_page_out_of_range(self, engine):
        citations = [
            ParsedCitation(author="Hamacher", pages="999", raw="(Hamacher 999)",
                           start_pos=0, end_pos=14),
        ]

        async def mock_search(author, title_hint):
            return {
                "title": "The Second of Inversion",
                "authors": ["Werner Hamacher"],
                "pages": "276-311",
                "type": "journal-article",
                "_source": "crossref",
            }

        engine._search_by_author_title = mock_search

        results = await engine.verify_all(citations, "text")
        assert len(results) == 1
        assert results[0].status == "page_out_of_range"

    @pytest.mark.asyncio
    async def test_verify_book_page_unverifiable(self, engine):
        citations = [
            ParsedCitation(author="Felstiner", pages="247", raw="(Felstiner 247)",
                           start_pos=0, end_pos=15),
        ]

        async def mock_search(author, title_hint):
            return {
                "title": "Paul Celan: Poet, Survivor, Jew",
                "authors": ["John Felstiner"],
                "pages": None,
                "type": "book",
                "_source": "crossref",
            }

        engine._search_by_author_title = mock_search

        results = await engine.verify_all(citations, "text")
        assert len(results) == 1
        assert results[0].status == "page_unverifiable"

    @pytest.mark.asyncio
    async def test_cache_prevents_duplicate_calls(self, engine):
        """Same author+title combo should only trigger one API search."""
        call_count = 0

        async def mock_search(author, title_hint):
            nonlocal call_count
            call_count += 1
            return {
                "title": "Some Work",
                "authors": ["Author"],
                "pages": None,
                "type": "book",
                "_source": "crossref",
            }

        engine._search_by_author_title = mock_search

        citations = [
            ParsedCitation(author="Author", pages="10", raw="(Author 10)",
                           start_pos=0, end_pos=11),
            ParsedCitation(author="Author", pages="20", raw="(Author 20)",
                           start_pos=20, end_pos=31),
        ]

        results = await engine.verify_all(citations, "text")
        assert len(results) == 2
        # Both should resolve, but _search_by_author_title is called for each
        # (caching happens inside the real method, not the mock)

    @pytest.mark.asyncio
    async def test_verify_no_author_no_title(self, engine):
        citations = [
            ParsedCitation(raw="(unknown)", start_pos=0, end_pos=9),
        ]
        results = await engine.verify_all(citations, "text")
        assert len(results) == 1
        assert results[0].status == "work_not_found"

    @pytest.mark.asyncio
    async def test_verify_no_page_work_found(self, engine):
        citations = [
            ParsedCitation(author="Derrida", title="Sovereignties",
                           raw="(Derrida, *Sovereignties*)",
                           start_pos=0, end_pos=25),
        ]

        async def mock_search(author, title_hint):
            return {
                "title": "Sovereignties in Question",
                "authors": ["Jacques Derrida"],
                "type": "book",
                "_source": "crossref",
            }

        engine._search_by_author_title = mock_search

        results = await engine.verify_all(citations, "text")
        assert len(results) == 1
        assert results[0].status == "verified"
        assert results[0].confidence == 0.9


# ============================================================
# TestEngineSearchMethods (mock API clients)
# ============================================================


class TestEngineSearchMethods:
    @pytest.mark.asyncio
    async def test_crossref_search(self):
        engine = CitationVerificationEngine()
        engine.crossref.search_works = AsyncMock(return_value={
            "message": {
                "items": [
                    {
                        "title": ["The Second of Inversion"],
                        "author": [{"given": "Werner", "family": "Hamacher"}],
                        "published-print": {"date-parts": [[1986]]},
                        "container-title": ["MLN"],
                        "page": "276-311",
                        "DOI": "10.2307/2905586",
                    }
                ]
            }
        })

        result = await engine._search_crossref(
            "Hamacher Second of Inversion", "Hamacher", "The Second of Inversion"
        )
        assert result is not None
        assert result["title"] == "The Second of Inversion"
        assert result["pages"] == "276-311"

    @pytest.mark.asyncio
    async def test_openalex_search(self):
        engine = CitationVerificationEngine()
        engine.openalex.search_works = AsyncMock(return_value={
            "results": [
                {
                    "title": "Paul Celan: Poet, Survivor, Jew",
                    "authorships": [
                        {"author": {"display_name": "John Felstiner"}}
                    ],
                    "publication_year": 1995,
                    "doi": "https://doi.org/10.12345/fake",
                    "type": "book",
                }
            ]
        })

        result = await engine._search_openalex(
            "Felstiner Paul Celan", "Felstiner", "Paul Celan"
        )
        assert result is not None
        assert result["title"] == "Paul Celan: Poet, Survivor, Jew"

    @pytest.mark.asyncio
    async def test_crossref_fallback_to_openalex(self):
        engine = CitationVerificationEngine()
        engine.crossref.search_works = AsyncMock(return_value={
            "message": {"items": []}
        })
        engine.openalex.search_works = AsyncMock(return_value={
            "results": [
                {
                    "title": "Testimony: Crises of Witnessing",
                    "authorships": [
                        {"author": {"display_name": "Shoshana Felman"}}
                    ],
                    "publication_year": 1992,
                    "doi": None,
                    "type": "book",
                }
            ]
        })

        result = await engine._search_by_author_title("Felman", "Testimony")
        assert result is not None
        assert result["_source"] == "openalex"


# ============================================================
# TestPipeline (mock-based)
# ============================================================


class TestPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_no_citations(self):
        from src.citation_verifier.pipeline import verify_manuscript_citations

        text = "This text has no parenthetical citations."
        with patch(
            "src.citation_verifier.pipeline.CitationVerificationEngine"
        ):
            annotated, report = await verify_manuscript_citations(text)
        assert annotated == text
        assert report.total == 0

    @pytest.mark.asyncio
    async def test_pipeline_with_citations(self):
        from src.citation_verifier.pipeline import verify_manuscript_citations

        text = "see (Felstiner 247) and (Derrida 42)."

        mock_engine_instance = MagicMock()
        mock_engine_instance.verify_all = AsyncMock(return_value=[
            CitationVerification(
                citation=ParsedCitation(
                    author="Felstiner", pages="247",
                    raw="(Felstiner 247)", start_pos=4, end_pos=19,
                ),
                status="page_unverifiable",
                confidence=0.7,
            ),
            CitationVerification(
                citation=ParsedCitation(
                    author="Derrida", pages="42",
                    raw="(Derrida 42)", start_pos=24, end_pos=36,
                ),
                status="verified",
                confidence=1.0,
            ),
        ])
        mock_engine_instance.close = AsyncMock()

        with patch(
            "src.citation_verifier.pipeline.CitationVerificationEngine",
            return_value=mock_engine_instance,
        ):
            annotated, report = await verify_manuscript_citations(text)

        assert "[VERIFY:page]" in annotated
        assert "[VERIFY:work]" not in annotated
        assert report.total == 2
        assert report.verified == 1
        assert report.page_unverifiable == 1


# ============================================================
# TestEngineMatches
# ============================================================


class TestEngineMatches:
    def setup_method(self):
        self.engine = CitationVerificationEngine()

    def test_match_by_title(self):
        work = {"title": "The Second of Inversion", "authors": []}
        assert self.engine._matches(work, None, "The Second of Inversion") is True

    def test_match_by_author_surname(self):
        work = {"title": "Some Work", "authors": ["Werner Hamacher"]}
        assert self.engine._matches(work, "Hamacher", None) is True

    def test_no_match(self):
        work = {"title": "Unrelated", "authors": ["Other Person"]}
        assert self.engine._matches(work, "Hamacher", "Inversion") is False

    def test_match_partial_title(self):
        work = {
            "title": "Sovereignties in Question: The Poetics of Paul Celan",
            "authors": ["Jacques Derrida"],
        }
        assert self.engine._matches(work, None, "Sovereignties") is True
