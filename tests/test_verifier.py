"""Tests for the reference verifier module."""

from __future__ import annotations

import pytest

from src.reference_verifier.doi_resolver import DOIResolver
from src.reference_verifier.format_checker import FormatChecker
from src.knowledge_base.models import Reference


class TestFormatChecker:
    def setup_method(self):
        self.checker = FormatChecker()
        self.sample_ref = Reference(
            title="Conjectures on World Literature",
            authors=["Franco Moretti"],
            year=2000,
            journal="New Left Review",
            volume="1",
            pages="54-68",
            doi="10.1234/example",
        )
        self.sample_book = Reference(
            title="Death of a Discipline",
            authors=["Gayatri Chakravorty Spivak"],
            year=2003,
            publisher="Columbia University Press",
        )

    def test_format_mla_article(self):
        result = self.checker.format_reference(self.sample_ref, "MLA")
        assert "Moretti, Franco" in result
        assert "Conjectures on World Literature" in result
        assert "New Left Review" in result
        assert "2000" in result
        assert "54-68" in result

    def test_format_mla_book(self):
        result = self.checker.format_reference(self.sample_book, "MLA")
        assert "Spivak, Gayatri Chakravorty" in result
        assert "Death of a Discipline" in result
        assert "Columbia University Press" in result

    def test_format_chicago_article(self):
        result = self.checker.format_reference(self.sample_ref, "Chicago")
        assert "Moretti" in result
        assert "2000" in result

    def test_format_gb_article(self):
        result = self.checker.format_reference(self.sample_ref, "GB/T 7714")
        assert "Franco Moretti" in result
        assert "[J]" in result
        assert "2000" in result

    def test_format_french_article(self):
        ref = Reference(
            title="De l'imagerie culturelle",
            authors=["Daniel-Henri Pageaux"],
            year=1989,
            journal="Précis de littérature comparée",
            volume="1",
            pages="133-161",
        )
        result = self.checker.format_reference(ref, "French academic")
        assert "Pageaux" in result
        assert "\u00ab" in result  # French guillemets
        assert "1989" in result

    def test_format_multiple_authors_mla(self):
        ref = Reference(
            title="Collaborative Work",
            authors=["Author One", "Author Two", "Author Three", "Author Four"],
            year=2020,
            journal="Test Journal",
        )
        result = self.checker.format_reference(ref, "MLA")
        assert "et al" in result

    def test_check_bibliography(self):
        bib = """Moretti, Franco. "Conjectures on World Literature." *New Left Review* 1 (2000): 54-68.
Spivak, Gayatri Chakravorty. *Death of a Discipline*. Columbia UP, 2003."""
        issues = self.checker.check_bibliography(bib, "MLA")
        # Should find no major errors in well-formatted bibliography
        error_issues = [i for i in issues if i["severity"] == "error"]
        assert len(error_issues) == 0


class TestDOIResolver:
    def test_title_match_exact(self):
        assert DOIResolver._is_title_match(
            "Conjectures on World Literature",
            ["Conjectures on World Literature"],
        )

    def test_title_match_case_insensitive(self):
        assert DOIResolver._is_title_match(
            "conjectures on world literature",
            ["Conjectures on World Literature"],
        )

    def test_title_match_subset(self):
        assert DOIResolver._is_title_match(
            "World Literature",
            ["Conjectures on World Literature"],
        )

    def test_title_no_match(self):
        assert not DOIResolver._is_title_match(
            "Completely Different Title",
            ["Conjectures on World Literature"],
        )
