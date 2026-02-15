"""Tests for Phase 10.3 (CitationManager new features) and Phase 10.4 (writer/critic changes).

Covers:
- Footnote generation: add_footnote, format_footnote_full/short, render_footnotes_section, reset
- Block quote formatting with multilingual support
- Secondary citation ("qtd. in" / "quoted in" / "转引自")
- Multilingual inline quotation
- Extended format_citation with page override and short_title disambiguation
- Extended verify_all_citations with MLA author-page, "qtd. in", and deduplication
- _parse_critic_response with 5 scoring dimensions
- _load_citation_norms profile injection
- Reference type grouping constants
"""

from __future__ import annotations

import json

import pytest

from src.knowledge_base.models import Reference, ReferenceType
from src.writing_agent.citation_manager import CitationManager, _extract_surname
from src.writing_agent.writer import _parse_critic_response, _PRIMARY_TYPES, _SECONDARY_TYPES, _THEORY_TYPES


# ---------------------------------------------------------------------------
#  Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cm():
    """Fresh CitationManager instance with clean footnote state."""
    return CitationManager()


@pytest.fixture
def ref_moretti():
    return Reference(
        title="Conjectures on World Literature",
        authors=["Franco Moretti"],
        year=2000,
        journal="New Left Review",
        volume="1",
        pages="54-68",
        doi="10.1234/nlr.2000.01",
    )


@pytest.fixture
def ref_damrosch():
    return Reference(
        title="What Is World Literature?",
        authors=["David Damrosch"],
        year=2003,
        publisher="Princeton University Press",
    )


@pytest.fixture
def ref_auerbach():
    return Reference(
        title="Mimesis: The Representation of Reality in Western Literature",
        authors=["Erich Auerbach"],
        year=1946,
        publisher="Princeton University Press",
        pages="3-23",
    )


@pytest.fixture
def ref_chinese():
    return Reference(
        title="The Tao and the Logos",
        authors=["张隆溪"],
        year=1992,
        journal="Critical Inquiry",
        volume="19",
        issue="1",
        pages="1-17",
    )


@pytest.fixture
def ref_multi_author():
    return Reference(
        title="Collaborative Study of Narrative",
        authors=["Alice Smith", "Bob Jones", "Carol Lee", "Dan Park"],
        year=2021,
        journal="Narrative",
        volume="29",
        issue="2",
        pages="100-125",
    )


# ===========================================================================
#  Phase 10.3: Footnote Generation
# ===========================================================================


class TestFootnoteGeneration:
    def test_add_footnote_returns_marker(self, cm):
        marker = cm.add_footnote("On the history of this concept, see the following.")
        assert marker == "[^1]"

    def test_add_multiple_footnotes_increments(self, cm):
        m1 = cm.add_footnote("First note.")
        m2 = cm.add_footnote("Second note.")
        m3 = cm.add_footnote("Third note.")
        assert m1 == "[^1]"
        assert m2 == "[^2]"
        assert m3 == "[^3]"

    def test_add_footnote_stores_content(self, cm):
        cm.add_footnote("A substantive discussion.")
        notes = cm.get_all_footnotes()
        assert len(notes) == 1
        assert notes[0] == "A substantive discussion."

    def test_add_footnote_with_refs_appends_see_cluster(self, cm, ref_moretti, ref_damrosch):
        cm.add_footnote(
            "This point has been debated extensively.",
            refs=[ref_moretti, ref_damrosch],
            style="Chicago",
        )
        notes = cm.get_all_footnotes()
        assert len(notes) == 1
        note = notes[0]
        assert "This point has been debated extensively." in note
        assert "See " in note
        assert "Moretti" in note
        assert "Damrosch" in note
        # Chicago style: should include title and year
        assert "(2000)" in note or "2000" in note

    def test_add_footnote_refs_only_no_content(self, cm, ref_moretti):
        cm.add_footnote("", refs=[ref_moretti], style="MLA")
        notes = cm.get_all_footnotes()
        assert notes[0].startswith("See ")
        assert "Moretti" in notes[0]

    def test_add_footnote_refs_mla_uses_pages(self, cm, ref_moretti):
        cm.add_footnote("", refs=[ref_moretti], style="MLA")
        note = cm.get_all_footnotes()[0]
        # MLA footnote refs use surname + pages
        assert "54-68" in note

    def test_reset_footnotes(self, cm):
        cm.add_footnote("Note 1.")
        cm.add_footnote("Note 2.")
        assert len(cm.get_all_footnotes()) == 2

        cm.reset_footnotes()
        assert len(cm.get_all_footnotes()) == 0

        # Counter also resets
        marker = cm.add_footnote("After reset.")
        assert marker == "[^1]"

    def test_render_footnotes_section_empty(self, cm):
        assert cm.render_footnotes_section() == ""

    def test_render_footnotes_section(self, cm):
        cm.add_footnote("First substantive note.")
        cm.add_footnote("Second note with extended argument.")
        rendered = cm.render_footnotes_section()
        assert "[^1]: First substantive note." in rendered
        assert "[^2]: Second note with extended argument." in rendered

    def test_render_footnotes_section_markdown_format(self, cm):
        cm.add_footnote("Note A.")
        cm.add_footnote("Note B.")
        rendered = cm.render_footnotes_section()
        lines = rendered.split("\n")
        assert len(lines) == 2
        assert lines[0].startswith("[^1]: ")
        assert lines[1].startswith("[^2]: ")


class TestFootnoteFullFormat:
    """Chicago-style full footnote citations (first occurrence)."""

    def test_single_author_journal(self, cm, ref_moretti):
        result = cm.format_footnote_full(ref_moretti)
        assert "Franco Moretti" in result  # First Last in notes
        assert '"Conjectures on World Literature,"' in result
        assert "*New Left Review*" in result
        assert "(2000)" in result
        assert result.endswith(".")

    def test_single_author_book(self, cm, ref_damrosch):
        result = cm.format_footnote_full(ref_damrosch)
        assert "David Damrosch" in result
        assert "Princeton University Press" in result

    def test_page_override(self, cm, ref_moretti):
        result = cm.format_footnote_full(ref_moretti, page="60")
        assert ": 60" in result

    def test_no_authors(self, cm):
        ref = Reference(title="Anonymous Work", year=1500)
        result = cm.format_footnote_full(ref)
        assert "Unknown Author" in result

    def test_two_authors(self, cm):
        ref = Reference(
            title="Joint Article",
            authors=["Alice Smith", "Bob Jones"],
            year=2020,
            journal="PMLA",
            volume="135",
            pages="1-20",
        )
        result = cm.format_footnote_full(ref)
        assert "Alice Smith and Bob Jones" in result

    def test_three_authors(self, cm):
        ref = Reference(
            title="Triple Article",
            authors=["Alice Smith", "Bob Jones", "Carol Lee"],
            year=2020,
            journal="PMLA",
        )
        result = cm.format_footnote_full(ref)
        assert "Alice Smith, Bob Jones, and Carol Lee" in result

    def test_four_plus_authors_uses_et_al(self, cm, ref_multi_author):
        result = cm.format_footnote_full(ref_multi_author)
        assert "Alice Smith et al." in result
        assert "Bob Jones" not in result

    def test_book_with_page(self, cm, ref_damrosch):
        result = cm.format_footnote_full(ref_damrosch, page="45")
        assert ", 45" in result


class TestFootnoteShortFormat:
    """Chicago-style shortened footnote (subsequent occurrences)."""

    def test_basic_short(self, cm, ref_moretti):
        result = cm.format_footnote_short(ref_moretti)
        assert "Moretti" in result
        # Short title: first 4 words
        assert "Conjectures on World Literature" in result
        # Should include pages
        assert "54-68" in result

    def test_short_title_truncated(self, cm):
        ref = Reference(
            title="A Very Long Title That Goes On and On",
            authors=["Jane Doe"],
            year=2020,
        )
        result = cm.format_footnote_short(ref)
        assert "Doe" in result
        assert "A Very Long Title..." in result
        assert "Goes" not in result

    def test_short_with_page_override(self, cm, ref_moretti):
        result = cm.format_footnote_short(ref_moretti, page="62")
        assert "62" in result
        assert result.endswith(".")

    def test_chinese_author(self, cm, ref_chinese):
        result = cm.format_footnote_short(ref_chinese)
        assert "张隆溪" in result


# ===========================================================================
#  Phase 10.3: Block Quote Formatting
# ===========================================================================


class TestBlockQuoteFormatting:
    def test_basic_block_quote_mla(self, cm, ref_moretti):
        text = "World literature is not an object, it is a problem."
        result = cm.format_block_quote(text, ref_moretti, "MLA", page="55")
        assert result.startswith("> ")
        assert "World literature is not an object" in result
        assert "(Moretti 55)" in result

    def test_block_quote_chicago(self, cm, ref_moretti):
        text = "Some passage from the article."
        result = cm.format_block_quote(text, ref_moretti, "Chicago", page="60")
        assert "(Moretti 2000, 60)" in result

    def test_block_quote_gb(self, cm, ref_chinese):
        text = "A passage for GB/T citation."
        result = cm.format_block_quote(text, ref_chinese, "GB/T 7714", page="5")
        assert "(张隆溪, 1992, 5)" in result

    def test_block_quote_with_translation(self, cm, ref_chinese):
        text = "道可道，非常道"
        translation = "The way that can be spoken of is not the constant way"
        result = cm.format_block_quote(
            text, ref_chinese, "MLA", page="10",
            translation=translation,
        )
        # Original text in block
        assert "> 道可道，非常道" in result
        # Translation in italics
        assert "> *The way that can be spoken of" in result

    def test_block_quote_with_translator_note(self, cm, ref_chinese):
        text = "原文"
        translation = "translation"
        result = cm.format_block_quote(
            text, ref_chinese, "MLA",
            translation=translation,
            translator_note="(my translation)",
        )
        assert "(my translation)" in result

    def test_block_quote_multiline(self, cm, ref_auerbach):
        text = "First line.\nSecond line.\nThird line."
        result = cm.format_block_quote(text, ref_auerbach, "MLA")
        lines = result.split("\n")
        # Each original line should be block-quoted
        assert sum(1 for l in lines if l.startswith("> ") and "line." in l) == 3

    def test_block_quote_no_page(self, cm, ref_damrosch):
        text = "A passage without page number."
        result = cm.format_block_quote(text, ref_damrosch, "MLA")
        assert "(Damrosch)" in result

    def test_block_quote_no_page_chicago(self, cm, ref_damrosch):
        text = "A passage."
        result = cm.format_block_quote(text, ref_damrosch, "Chicago")
        assert "(Damrosch 2003)" in result


# ===========================================================================
#  Phase 10.3: Secondary Citation ("qtd. in")
# ===========================================================================


class TestSecondaryCitation:
    def test_qtd_in_mla_with_page(self, cm, ref_moretti):
        result = cm.format_secondary_citation("Benjamin", ref_moretti, "MLA", page="57")
        assert result == "(Benjamin, qtd. in Moretti 57)"

    def test_qtd_in_mla_no_page(self, cm, ref_damrosch):
        result = cm.format_secondary_citation("Goethe", ref_damrosch, "MLA")
        assert result == "(Goethe, qtd. in Damrosch)"

    def test_quoted_in_chicago_with_page(self, cm, ref_moretti):
        result = cm.format_secondary_citation("Benjamin", ref_moretti, "Chicago", page="57")
        assert result == "(Benjamin, quoted in Moretti 2000, 57)"

    def test_quoted_in_chicago_no_page(self, cm, ref_damrosch):
        result = cm.format_secondary_citation("Goethe", ref_damrosch, "Chicago")
        assert result == "(Goethe, quoted in Damrosch 2003)"

    def test_zhuanyinzi_gb_with_page(self, cm, ref_chinese):
        result = cm.format_secondary_citation("孔子", ref_chinese, "GB/T 7714", page="5")
        assert result == "(孔子, 转引自 张隆溪, 1992, 5)"

    def test_zhuanyinzi_gb_no_page(self, cm):
        ref_no_pages = Reference(
            title="The Tao and the Logos",
            authors=["张隆溪"],
            year=1992,
            journal="Critical Inquiry",
        )
        result = cm.format_secondary_citation("孔子", ref_no_pages, "GB")
        assert result == "(孔子, 转引自 张隆溪, 1992)"

    def test_default_style_falls_back_to_mla(self, cm, ref_moretti):
        result = cm.format_secondary_citation("Benjamin", ref_moretti, "Unknown Style", page="57")
        assert "qtd. in" in result

    def test_mediating_ref_uses_ref_pages_when_no_override(self, cm, ref_moretti):
        result = cm.format_secondary_citation("Marx", ref_moretti, "MLA")
        # ref_moretti.pages = "54-68", no page override
        assert result == "(Marx, qtd. in Moretti 54-68)"


# ===========================================================================
#  Phase 10.3: Multilingual Inline Quotation
# ===========================================================================


class TestMultilingualInlineQuotation:
    def test_original_only(self, cm):
        result = cm.format_inline_quote_multilingual("道可道，非常道")
        assert result == '"道可道，非常道"'

    def test_original_with_translation(self, cm):
        result = cm.format_inline_quote_multilingual(
            "道可道，非常道",
            translation="The way that can be spoken of is not the constant way",
        )
        assert '"道可道，非常道"' in result
        assert '("The way that can be spoken of' in result

    def test_original_with_translation_and_note(self, cm):
        result = cm.format_inline_quote_multilingual(
            "le monde",
            translation="the world",
            translator_note="(my translation)",
        )
        assert '"le monde"' in result
        assert '("the world" (my translation))' in result

    def test_no_translator_note(self, cm):
        result = cm.format_inline_quote_multilingual(
            "Weltliteratur",
            translation="world literature",
        )
        assert '"Weltliteratur" ("world literature")' == result


# ===========================================================================
#  Phase 10.3: Extended format_citation
# ===========================================================================


class TestExtendedFormatCitation:
    def test_mla_with_page_override(self, cm, ref_moretti):
        result = cm.format_citation(ref_moretti, "MLA", page="60")
        assert result == "(Moretti 60)"

    def test_mla_with_short_title(self, cm, ref_moretti):
        result = cm.format_citation(ref_moretti, "MLA", short_title="Conjectures")
        assert "(Moretti, *Conjectures* 54-68)" == result

    def test_mla_with_short_title_and_page(self, cm, ref_moretti):
        result = cm.format_citation(ref_moretti, "MLA", page="60", short_title="Conjectures")
        assert "(Moretti, *Conjectures* 60)" == result

    def test_chicago_page_override(self, cm, ref_moretti):
        result = cm.format_citation(ref_moretti, "Chicago", page="62")
        assert "(Moretti 2000, 62)" == result

    def test_gb_page_override(self, cm, ref_chinese):
        result = cm.format_citation(ref_chinese, "GB", page="5")
        assert result == "(张隆溪, 1992, 5)"

    def test_page_override_takes_precedence(self, cm, ref_moretti):
        # ref_moretti.pages = "54-68" but page="60" should override
        result = cm.format_citation(ref_moretti, "MLA", page="60")
        assert "60" in result
        assert "54-68" not in result


# ===========================================================================
#  Phase 10.3: Extended verify_all_citations
# ===========================================================================


class TestExtendedVerifyCitations:
    def _make_known_refs(self):
        return {
            "ref1": Reference(
                title="Conjectures on World Literature",
                authors=["Franco Moretti"],
                year=2000,
            ),
            "ref2": Reference(
                title="What Is World Literature?",
                authors=["David Damrosch"],
                year=2003,
            ),
            "ref3": Reference(
                title="The Tao and the Logos",
                authors=["张隆溪"],
                year=1992,
            ),
        }

    def test_author_year_verified(self):
        known = self._make_known_refs()
        text = "As Moretti argues (Moretti, 2000), world literature is a problem."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("Moretti" in v and "2000" in v for v in verified)
        assert len(unverified) == 0

    def test_mla_author_page_verified(self):
        known = self._make_known_refs()
        text = "World literature is a 'problem' (Moretti 55)."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("Moretti 55" in v for v in verified)

    def test_mla_author_page_unverified(self):
        known = self._make_known_refs()
        text = "As argued by (Smith 42), the concept is flawed."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("Smith" in u for u in unverified)

    def test_qtd_in_verified(self):
        known = self._make_known_refs()
        text = "Benjamin remarks (qtd. in Moretti 57) that translation is crucial."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("qtd. in Moretti" in v for v in verified)

    def test_quoted_in_verified(self):
        known = self._make_known_refs()
        text = "Goethe wrote (quoted in Damrosch 2003, 45) about world literature."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("quoted in Damrosch" in v for v in verified)

    def test_zhuanyinzi_verified(self):
        known = self._make_known_refs()
        text = "孔子说 (转引自 张隆溪, 1992, 5) 关于道的论述。"
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert any("转引自" in v for v in verified)

    def test_deduplication(self):
        known = self._make_known_refs()
        text = (
            "Moretti argues (Moretti, 2000) that world literature is a problem. "
            "He further contends (Moretti, 2000) that distant reading is necessary."
        )
        verified, unverified = CitationManager.verify_all_citations(text, known)
        moretti_cites = [v for v in verified if "Moretti" in v and "2000" in v]
        assert len(moretti_cites) == 1  # Deduplication

    def test_numeric_bracket_verified(self):
        known = {"1": Reference(title="Test", authors=["A"], year=2020)}
        text = "As shown [1], the method works."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert "[1]" in verified

    def test_numeric_bracket_unverified(self):
        known = {"1": Reference(title="Test", authors=["A"], year=2020)}
        text = "As shown [1, 2], the method works."
        verified, unverified = CitationManager.verify_all_citations(text, known)
        # "2" is not in known_refs so the whole [1, 2] should be unverified
        assert "[1, 2]" in unverified

    def test_mixed_citation_types(self):
        known = self._make_known_refs()
        text = (
            "Moretti argues (Moretti, 2000) about world literature, "
            "a concept explored by Damrosch (Damrosch 45). "
            "Unknown author (Unknown 1999) disagrees."
        )
        verified, unverified = CitationManager.verify_all_citations(text, known)
        assert len(verified) >= 2
        assert len(unverified) >= 1


# ===========================================================================
#  Phase 10.3: Private helper _extract_surname
# ===========================================================================


class TestExtractSurname:
    def test_first_last(self):
        assert _extract_surname("Franco Moretti") == "Moretti"

    def test_last_first(self):
        assert _extract_surname("Moretti, Franco") == "Moretti"

    def test_single_name(self):
        assert _extract_surname("Voltaire") == "Voltaire"

    def test_chinese_name(self):
        assert _extract_surname("张隆溪") == "张隆溪"

    def test_empty_string(self):
        assert _extract_surname("") == ""

    def test_whitespace(self):
        assert _extract_surname("  ") == ""

    def test_multi_word_surname(self):
        assert _extract_surname("Gayatri Chakravorty Spivak") == "Spivak"


# ===========================================================================
#  Phase 10.4: _parse_critic_response with 6 dimensions
# ===========================================================================


class TestParseCriticResponse:
    def test_full_json(self):
        raw = json.dumps({
            "close_reading_depth": 4,
            "argument_logic": 5,
            "citation_density": 3,
            "citation_sophistication": 4,
            "quote_paraphrase_ratio": 3,
            "erudite_vocabulary": 5,
            "revision_instructions": "",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 4
        assert scores["argument_logic"] == 5
        assert scores["citation_density"] == 3
        assert scores["citation_sophistication"] == 4
        assert scores["quote_paraphrase_ratio"] == 3
        assert scores["erudite_vocabulary"] == 5
        assert instructions == ""

    def test_backward_compatible_defaults(self):
        """Old 3-dimension responses should default new dimensions to 3."""
        raw = json.dumps({
            "close_reading_depth": 4,
            "argument_logic": 5,
            "citation_density": 3,
            "revision_instructions": "",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 4
        assert scores["citation_sophistication"] == 3  # default
        assert scores["quote_paraphrase_ratio"] == 3  # default
        assert scores["erudite_vocabulary"] == 3  # default

    def test_with_revision_instructions(self):
        raw = json.dumps({
            "close_reading_depth": 2,
            "argument_logic": 3,
            "citation_density": 1,
            "citation_sophistication": 2,
            "quote_paraphrase_ratio": 4,
            "revision_instructions": "Deepen close reading and add more citations.",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 2
        assert scores["citation_density"] == 1
        assert "close reading" in instructions

    def test_json_in_markdown_fences(self):
        raw = '```json\n{"close_reading_depth": 5, "argument_logic": 4, "citation_density": 4, "citation_sophistication": 5, "quote_paraphrase_ratio": 4, "revision_instructions": ""}\n```'
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 5
        assert scores["citation_sophistication"] == 5

    def test_invalid_json_returns_defaults(self):
        scores, instructions = _parse_critic_response("This is not JSON at all.")
        assert scores["close_reading_depth"] == 1
        assert scores["argument_logic"] == 1
        assert scores["citation_density"] == 1
        assert scores["citation_sophistication"] == 1
        assert scores["quote_paraphrase_ratio"] == 1
        assert scores["erudite_vocabulary"] == 1
        assert instructions != ""

    def test_empty_response(self):
        scores, instructions = _parse_critic_response("")
        assert all(v == 1 for v in scores.values())

    def test_all_six_keys_present(self):
        raw = json.dumps({
            "close_reading_depth": 3,
            "argument_logic": 3,
            "citation_density": 3,
            "citation_sophistication": 3,
            "quote_paraphrase_ratio": 3,
            "erudite_vocabulary": 3,
            "revision_instructions": "",
        })
        scores, _ = _parse_critic_response(raw)
        expected_keys = {
            "close_reading_depth",
            "argument_logic",
            "citation_density",
            "citation_sophistication",
            "quote_paraphrase_ratio",
            "erudite_vocabulary",
        }
        assert set(scores.keys()) == expected_keys


# ===========================================================================
#  Phase 10.4: Reference type grouping constants
# ===========================================================================


class TestReferenceTypeGrouping:
    def test_primary_types(self):
        assert ReferenceType.PRIMARY_LITERARY in _PRIMARY_TYPES
        assert len(_PRIMARY_TYPES) == 1

    def test_theory_types(self):
        assert ReferenceType.THEORY in _THEORY_TYPES
        assert len(_THEORY_TYPES) == 1

    def test_secondary_types_contains_expected(self):
        assert ReferenceType.SECONDARY_CRITICISM in _SECONDARY_TYPES
        assert ReferenceType.HISTORICAL_CONTEXT in _SECONDARY_TYPES
        assert ReferenceType.METHODOLOGY in _SECONDARY_TYPES
        assert ReferenceType.REFERENCE_WORK in _SECONDARY_TYPES
        assert ReferenceType.SELF_CITATION in _SECONDARY_TYPES

    def test_no_overlap_between_groups(self):
        assert _PRIMARY_TYPES & _SECONDARY_TYPES == set()
        assert _PRIMARY_TYPES & _THEORY_TYPES == set()
        assert _SECONDARY_TYPES & _THEORY_TYPES == set()

    def test_unclassified_not_in_any_group(self):
        assert ReferenceType.UNCLASSIFIED not in _PRIMARY_TYPES
        assert ReferenceType.UNCLASSIFIED not in _SECONDARY_TYPES
        assert ReferenceType.UNCLASSIFIED not in _THEORY_TYPES


# ===========================================================================
#  Phase 10.3: Bibliography formatting (existing + regression)
# ===========================================================================


class TestBibliographyFormatting:
    def test_mla_journal_article(self, ref_moretti):
        result = CitationManager.format_bibliography_entry(ref_moretti, "MLA")
        assert "Moretti, Franco" in result
        assert '"Conjectures on World Literature."' in result
        assert "*New Left Review*" in result
        assert "vol. 1" in result
        assert "pp. 54-68" in result
        assert "2000" in result

    def test_chicago_journal_article(self, ref_moretti):
        result = CitationManager.format_bibliography_entry(ref_moretti, "Chicago")
        assert "Moretti, Franco" in result
        assert "(2000)" in result
        assert ": 54-68" in result

    def test_gb_journal_article(self, ref_chinese):
        result = CitationManager.format_bibliography_entry(ref_chinese, "GB")
        assert "张隆溪" in result
        assert "[J]" in result
        assert "Critical Inquiry" in result

    def test_cached_format_used(self):
        ref = Reference(
            title="Test",
            authors=["A"],
            year=2020,
            formatted_mla="Cached MLA entry.",
        )
        result = CitationManager.format_bibliography_entry(ref, "MLA")
        assert result == "Cached MLA entry."

    def test_doi_included_mla(self, ref_moretti):
        result = CitationManager.format_bibliography_entry(ref_moretti, "MLA")
        assert "https://doi.org/10.1234/nlr.2000.01" in result

    def test_doi_included_gb(self, ref_moretti):
        result = CitationManager.format_bibliography_entry(ref_moretti, "GB")
        assert "DOI:10.1234/nlr.2000.01" in result
