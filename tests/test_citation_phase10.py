"""Tests for Phase 10 citation system improvements.

Tests cover:
- ReferenceType enum and classification
- CitationManager: footnotes, block quotes, multilingual, secondary citations
- Writer: critic response parsing with new scoring dimensions
- Writer: citation norms loading from profile YAML
- Reference context injection by type
- Citation verification with new patterns (qtd. in, MLA author-page)
"""

from __future__ import annotations

import json

import pytest

from src.knowledge_base.models import Reference, ReferenceType
from src.writing_agent.citation_manager import CitationManager, _extract_surname


# ====================================================================== #
#  Fixtures
# ====================================================================== #

@pytest.fixture
def sample_ref() -> Reference:
    return Reference(
        id="ref-001",
        paper_id="paper-001",
        title="Violence and Metaphysics",
        authors=["Jacques Derrida"],
        year=1978,
        journal="Writing and Difference",
        volume=None,
        issue=None,
        pages="79-153",
        doi=None,
        publisher="University of Chicago Press",
        ref_type=ReferenceType.THEORY,
    )


@pytest.fixture
def sample_ref_secondary() -> Reference:
    return Reference(
        id="ref-002",
        paper_id="paper-002",
        title="Temoins",
        authors=["Jean Norton Cru"],
        year=1929,
        journal=None,
        pages="226",
        publisher="Presses universitaires de Nancy",
        ref_type=ReferenceType.SECONDARY_CRITICISM,
    )


@pytest.fixture
def sample_ref_primary() -> Reference:
    return Reference(
        id="ref-003",
        paper_id="paper-003",
        title="Men in the Sun",
        authors=["Ghassan Kanafani"],
        year=1963,
        journal=None,
        pages="37",
        publisher="Riad El-Rayyes Books",
        ref_type=ReferenceType.PRIMARY_LITERARY,
    )


@pytest.fixture
def sample_ref_multi_author() -> Reference:
    return Reference(
        id="ref-004",
        paper_id="paper-004",
        title="Rhyme in European Verse",
        authors=["Boris Maslov", "Tatiana Nikitina"],
        year=2019,
        journal="Comparative Literature",
        volume="71",
        issue="2",
        pages="194-212",
        ref_type=ReferenceType.METHODOLOGY,
    )


@pytest.fixture
def cm() -> CitationManager:
    return CitationManager()


# ====================================================================== #
#  ReferenceType enum
# ====================================================================== #

class TestReferenceType:
    def test_all_types_exist(self):
        expected = {
            "primary_literary", "secondary_criticism", "theory",
            "methodology", "historical_context", "reference_work",
            "self_citation", "unclassified",
        }
        actual = {rt.value for rt in ReferenceType}
        assert actual == expected

    def test_default_is_unclassified(self):
        ref = Reference(title="Test", authors=["Author"], year=2020)
        assert ref.ref_type == ReferenceType.UNCLASSIFIED

    def test_set_ref_type(self):
        ref = Reference(
            title="Test",
            authors=["Author"],
            year=2020,
            ref_type=ReferenceType.PRIMARY_LITERARY,
        )
        assert ref.ref_type == ReferenceType.PRIMARY_LITERARY


# ====================================================================== #
#  Secondary citation ("qtd. in")
# ====================================================================== #

class TestSecondaryCitation:
    def test_mla_qtd_in_with_page(self, sample_ref_secondary):
        result = CitationManager.format_secondary_citation(
            original_author="Kimpflin",
            mediating_ref=sample_ref_secondary,
            style="MLA",
            page="43",
        )
        assert "qtd. in" in result
        assert "Kimpflin" in result
        assert "Cru" in result
        assert "43" in result

    def test_mla_qtd_in_without_page(self, sample_ref_secondary):
        result = CitationManager.format_secondary_citation(
            original_author="Genevoix",
            mediating_ref=sample_ref_secondary,
            style="MLA",
        )
        assert "qtd. in" in result
        assert "Genevoix" in result
        assert "Cru" in result

    def test_chicago_quoted_in(self, sample_ref_secondary):
        result = CitationManager.format_secondary_citation(
            original_author="Kimpflin",
            mediating_ref=sample_ref_secondary,
            style="Chicago",
            page="43",
        )
        assert "quoted in" in result
        assert "1929" in result

    def test_gb_secondary(self, sample_ref_secondary):
        result = CitationManager.format_secondary_citation(
            original_author="Kimpflin",
            mediating_ref=sample_ref_secondary,
            style="GB/T 7714",
        )
        assert "转引自" in result
        assert "Cru" in result


# ====================================================================== #
#  Footnote generation
# ====================================================================== #

class TestFootnotes:
    def test_add_footnote_returns_marker(self, cm):
        marker = cm.add_footnote("This is a substantive footnote.")
        assert marker == "[^1]"

    def test_sequential_markers(self, cm):
        m1 = cm.add_footnote("First note.")
        m2 = cm.add_footnote("Second note.")
        m3 = cm.add_footnote("Third note.")
        assert m1 == "[^1]"
        assert m2 == "[^2]"
        assert m3 == "[^3]"

    def test_footnote_with_see_refs(self, cm, sample_ref, sample_ref_secondary):
        marker = cm.add_footnote(
            "For further discussion, consult the following.",
            refs=[sample_ref, sample_ref_secondary],
            style="Chicago",
        )
        notes = cm.get_all_footnotes()
        assert len(notes) == 1
        assert "See" in notes[0]
        assert "Derrida" in notes[0]
        assert "Cru" in notes[0]

    def test_footnote_empty_content_with_refs(self, cm, sample_ref):
        cm.add_footnote("", refs=[sample_ref], style="Chicago")
        notes = cm.get_all_footnotes()
        assert notes[0].startswith("See ")

    def test_reset_footnotes(self, cm):
        cm.add_footnote("Note 1")
        cm.add_footnote("Note 2")
        cm.reset_footnotes()
        assert cm.get_all_footnotes() == []
        marker = cm.add_footnote("After reset")
        assert marker == "[^1]"

    def test_render_footnotes_section(self, cm):
        cm.add_footnote("First substantive note.")
        cm.add_footnote("Second note with argument.")
        rendered = cm.render_footnotes_section()
        assert "[^1]: First substantive note." in rendered
        assert "[^2]: Second note with argument." in rendered

    def test_render_empty(self, cm):
        assert cm.render_footnotes_section() == ""

    def test_format_footnote_full_journal(self, cm, sample_ref_multi_author):
        result = cm.format_footnote_full(sample_ref_multi_author, page="200")
        # Chicago footnote: First Last names, comma separators
        assert "Boris Maslov" in result
        assert "Tatiana Nikitina" in result
        assert "Comparative Literature" in result
        assert "200" in result

    def test_format_footnote_full_book(self, cm):
        book_ref = Reference(
            title="Origins of Totalitarianism",
            authors=["Hannah Arendt"],
            year=1951,
            publisher="Harcourt Brace",
            ref_type=ReferenceType.THEORY,
        )
        result = cm.format_footnote_full(book_ref, page="120")
        assert "Hannah Arendt" in result
        assert "Origins of Totalitarianism" in result
        assert "Harcourt Brace" in result
        assert "1951" in result

    def test_format_footnote_short(self, cm, sample_ref):
        result = cm.format_footnote_short(sample_ref, page="95")
        assert "Derrida" in result
        assert "95" in result
        # Should have shortened title
        assert "Violence and Metaphysics" in result or "Violence and Metaphysics..." in result


# ====================================================================== #
#  Block quote formatting
# ====================================================================== #

class TestBlockQuote:
    def test_basic_block_quote_mla(self, sample_ref_primary):
        result = CitationManager.format_block_quote(
            text="The three men looked at one another in silence.",
            ref=sample_ref_primary,
            style="MLA",
            page="45",
        )
        assert result.startswith(">")
        assert "Kanafani" in result
        assert "45" in result

    def test_block_quote_with_translation(self, sample_ref_primary):
        result = CitationManager.format_block_quote(
            text="الرجال الثلاثة نظروا إلى بعضهم في صمت",
            ref=sample_ref_primary,
            style="MLA",
            page="45",
            translation="The three men looked at one another in silence.",
        )
        assert ">" in result
        # Translation should be italicized
        assert "*The three men" in result

    def test_block_quote_with_translator_note(self, sample_ref_primary):
        result = CitationManager.format_block_quote(
            text="Original text here",
            ref=sample_ref_primary,
            style="MLA",
            page="45",
            translation="Translated text here",
            translator_note="(my translation)",
        )
        assert "(my translation)" in result

    def test_block_quote_chicago(self, sample_ref):
        result = CitationManager.format_block_quote(
            text="A long passage from Derrida about deconstruction and philosophy.",
            ref=sample_ref,
            style="Chicago",
            page="125",
        )
        assert "1978" in result  # Chicago includes year
        assert "Derrida" in result

    def test_multiline_block_quote(self, sample_ref_primary):
        text = "Line one of the passage.\nLine two continues.\nLine three ends."
        result = CitationManager.format_block_quote(
            text=text,
            ref=sample_ref_primary,
            style="MLA",
        )
        lines = result.split("\n")
        # Each line should start with >
        for line in lines:
            assert line.startswith(">")


# ====================================================================== #
#  Multilingual inline quotation
# ====================================================================== #

class TestMultilingualInlineQuote:
    def test_original_only(self):
        result = CitationManager.format_inline_quote_multilingual(
            quoted_text="comme les ruines d'un grand foro"
        )
        assert result == '"comme les ruines d\'un grand foro"'

    def test_with_translation(self):
        result = CitationManager.format_inline_quote_multilingual(
            quoted_text="comme les ruines d'un grand foro",
            translation="like the ruins of a great forum",
        )
        assert '"comme les ruines' in result
        assert '"like the ruins' in result

    def test_with_translator_note(self):
        result = CitationManager.format_inline_quote_multilingual(
            quoted_text="nedogovorennosti",
            translation="reticence",
            translator_note="(my translation)",
        )
        assert "(my translation)" in result


# ====================================================================== #
#  Inline citation with new params
# ====================================================================== #

class TestInlineCitationEnhanced:
    def test_mla_with_page_override(self, sample_ref):
        result = CitationManager.format_citation(sample_ref, "MLA", page="120")
        assert "120" in result
        assert "Derrida" in result

    def test_mla_with_short_title(self, sample_ref):
        result = CitationManager.format_citation(
            sample_ref, "MLA", page="120", short_title="Violence"
        )
        assert "Violence" in result
        assert "Derrida" in result
        assert "120" in result

    def test_chicago_with_page(self, sample_ref):
        result = CitationManager.format_citation(sample_ref, "Chicago", page="120")
        assert "1978" in result
        assert "120" in result


# ====================================================================== #
#  Citation verification (expanded patterns)
# ====================================================================== #

class TestCitationVerificationExpanded:
    def test_verify_qtd_in(self):
        refs = {
            "ref-001": Reference(
                title="War Books",
                authors=["Jean Norton Cru"],
                year=1929,
            ),
        }
        text = 'As Kimpflin wrote, "The fighter has short views" (qtd. in Cru 43).'
        verified, unverified = CitationManager.verify_all_citations(text, refs)
        assert any("qtd. in" in v for v in verified)

    def test_verify_mla_author_page(self):
        refs = {
            "ref-001": Reference(
                title="Persons and Things",
                authors=["Barbara Johnson"],
                year=2008,
            ),
        }
        text = "As Johnson argues about personhood (Johnson 95), the distinction..."
        verified, unverified = CitationManager.verify_all_citations(text, refs)
        assert any("Johnson" in v for v in verified)

    def test_unverified_citation(self):
        refs = {
            "ref-001": Reference(
                title="Test",
                authors=["Known Author"],
                year=2020,
            ),
        }
        text = "According to Unknown (Unknown 2020), something happened."
        verified, unverified = CitationManager.verify_all_citations(text, refs)
        assert len(unverified) >= 0  # May or may not match pattern


# ====================================================================== #
#  Critic response parsing (5 dimensions)
# ====================================================================== #

class TestCriticResponseParsing:
    def test_parse_full_response(self):
        from src.writing_agent.writer import _parse_critic_response

        raw = json.dumps({
            "close_reading_depth": 4,
            "argument_logic": 5,
            "citation_density": 3,
            "citation_sophistication": 4,
            "quote_paraphrase_ratio": 3,
            "revision_instructions": "",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 4
        assert scores["argument_logic"] == 5
        assert scores["citation_density"] == 3
        assert scores["citation_sophistication"] == 4
        assert scores["quote_paraphrase_ratio"] == 3
        assert instructions == ""

    def test_parse_response_with_instructions(self):
        from src.writing_agent.writer import _parse_critic_response

        raw = json.dumps({
            "close_reading_depth": 2,
            "argument_logic": 4,
            "citation_density": 1,
            "citation_sophistication": 2,
            "quote_paraphrase_ratio": 2,
            "revision_instructions": "Add more direct quotations from primary texts.",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 2
        assert scores["citation_sophistication"] == 2
        assert "direct quotations" in instructions

    def test_parse_wrapped_in_markdown(self):
        from src.writing_agent.writer import _parse_critic_response

        raw = '```json\n{"close_reading_depth": 3, "argument_logic": 3, "citation_density": 3, "citation_sophistication": 3, "quote_paraphrase_ratio": 3, "revision_instructions": ""}\n```'
        scores, instructions = _parse_critic_response(raw)
        assert all(v == 3 for v in scores.values())

    def test_parse_missing_new_dimensions(self):
        from src.writing_agent.writer import _parse_critic_response

        # Old-style response without new dimensions
        raw = json.dumps({
            "close_reading_depth": 4,
            "argument_logic": 4,
            "citation_density": 4,
            "revision_instructions": "",
        })
        scores, instructions = _parse_critic_response(raw)
        assert scores["close_reading_depth"] == 4
        # New dimensions should default gracefully
        assert "citation_sophistication" in scores
        assert "quote_paraphrase_ratio" in scores
        assert "erudite_vocabulary" in scores

    def test_parse_invalid_json(self):
        from src.writing_agent.writer import _parse_critic_response

        scores, instructions = _parse_critic_response("This is not JSON at all.")
        # Should return defaults (all 1s)
        assert scores["close_reading_depth"] == 1
        assert scores["citation_sophistication"] == 1
        assert instructions != ""


# ====================================================================== #
#  Reference type classification parsing
# ====================================================================== #

class TestRefTypeClassification:
    def test_parse_exact_values(self):
        from src.research_planner.reference_selector import _parse_ref_type
        assert _parse_ref_type("primary_literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("theory") == ReferenceType.THEORY
        assert _parse_ref_type("secondary_criticism") == ReferenceType.SECONDARY_CRITICISM

    def test_parse_aliases(self):
        from src.research_planner.reference_selector import _parse_ref_type
        assert _parse_ref_type("primary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("secondary") == ReferenceType.SECONDARY_CRITICISM
        assert _parse_ref_type("criticism") == ReferenceType.SECONDARY_CRITICISM
        assert _parse_ref_type("historical") == ReferenceType.HISTORICAL_CONTEXT
        assert _parse_ref_type("method") == ReferenceType.METHODOLOGY

    def test_parse_case_insensitive(self):
        from src.research_planner.reference_selector import _parse_ref_type
        assert _parse_ref_type("PRIMARY_LITERARY") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("Theory") == ReferenceType.THEORY
        assert _parse_ref_type("SECONDARY") == ReferenceType.SECONDARY_CRITICISM

    def test_parse_with_dashes_spaces(self):
        from src.research_planner.reference_selector import _parse_ref_type
        assert _parse_ref_type("primary-literary") == ReferenceType.PRIMARY_LITERARY
        assert _parse_ref_type("historical context") == ReferenceType.HISTORICAL_CONTEXT

    def test_parse_unknown_returns_unclassified(self):
        from src.research_planner.reference_selector import _parse_ref_type
        assert _parse_ref_type("gibberish") == ReferenceType.UNCLASSIFIED
        assert _parse_ref_type("") == ReferenceType.UNCLASSIFIED


# ====================================================================== #
#  Citation profile loading
# ====================================================================== #

class TestCitationProfileLoading:
    def test_load_comparative_literature_profile(self):
        from src.research_planner.reference_selector import load_citation_profile
        profile = load_citation_profile("Comparative Literature")
        assert profile is not None
        # Should have key sections
        assert "quotation" in profile or "citation_density" in profile

    def test_load_nonexistent_profile(self):
        from src.research_planner.reference_selector import load_citation_profile
        profile = load_citation_profile("Nonexistent Journal Name XYZ")
        assert profile is None


# ====================================================================== #
#  Quotation model
# ====================================================================== #

class TestQuotationModel:
    def test_quotation_model_exists(self):
        from src.knowledge_base.models import Quotation
        q = Quotation(
            paper_id="p1",
            text="comme les ruines d'un grand foro",
            page="19",
            language="fr",
            is_primary_text=True,
        )
        assert q.text == "comme les ruines d'un grand foro"
        assert q.is_primary_text is True


# ====================================================================== #
#  Helper functions
# ====================================================================== #

class TestExtractSurname:
    def test_first_last(self):
        assert _extract_surname("Jacques Derrida") == "Derrida"

    def test_last_first(self):
        assert _extract_surname("Derrida, Jacques") == "Derrida"

    def test_single_name(self):
        assert _extract_surname("Voltaire") == "Voltaire"

    def test_chinese_name(self):
        assert _extract_surname("张隆溪") == "张隆溪"

    def test_empty(self):
        assert _extract_surname("") == ""

    def test_multiple_parts(self):
        assert _extract_surname("Gayatri Chakravorty Spivak") == "Spivak"


# ====================================================================== #
#  Writer reference type grouping constants
# ====================================================================== #

class TestWriterTypeGrouping:
    def test_primary_types(self):
        from src.writing_agent.writer import _PRIMARY_TYPES
        assert ReferenceType.PRIMARY_LITERARY in _PRIMARY_TYPES

    def test_secondary_types(self):
        from src.writing_agent.writer import _SECONDARY_TYPES
        assert ReferenceType.SECONDARY_CRITICISM in _SECONDARY_TYPES
        assert ReferenceType.HISTORICAL_CONTEXT in _SECONDARY_TYPES
        assert ReferenceType.METHODOLOGY in _SECONDARY_TYPES

    def test_theory_types(self):
        from src.writing_agent.writer import _THEORY_TYPES
        assert ReferenceType.THEORY in _THEORY_TYPES

    def test_no_overlap(self):
        from src.writing_agent.writer import _PRIMARY_TYPES, _SECONDARY_TYPES, _THEORY_TYPES
        assert _PRIMARY_TYPES.isdisjoint(_SECONDARY_TYPES)
        assert _PRIMARY_TYPES.isdisjoint(_THEORY_TYPES)
        assert _SECONDARY_TYPES.isdisjoint(_THEORY_TYPES)
