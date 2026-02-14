"""Tests for the writing agent and text processing utilities."""

from __future__ import annotations

import pytest

from src.utils.text_processing import (
    chunk_text,
    detect_language,
    extract_citations_from_text,
    normalize_author_name,
    word_count,
)


class TestLanguageDetection:
    def test_detect_english(self):
        text = "This is a paper about comparative literature and world literature theory."
        assert detect_language(text) == "en"

    def test_detect_chinese(self):
        text = "本文探讨了比较文学中的翻译问题，分析了中西文学交流的历史。"
        assert detect_language(text) == "zh"

    def test_detect_french(self):
        text = "Cette étude analyse les rapports entre la littérature comparée et la traduction dans le contexte francophone."
        assert detect_language(text) == "fr"

    def test_detect_empty(self):
        assert detect_language("") == "en"


class TestChunking:
    def test_basic_chunking(self):
        text = "Paragraph one about literature.\n\nParagraph two about theory.\n\nParagraph three about comparison."
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        assert len(chunks) >= 1
        assert all(len(c) > 0 for c in chunks)

    def test_empty_text(self):
        assert chunk_text("") == []

    def test_short_text_single_chunk(self):
        text = "A short paragraph."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1

    def test_overlap_preserved(self):
        paras = [f"Paragraph {i} with some content about literature." for i in range(10)]
        text = "\n\n".join(paras)
        chunks = chunk_text(text, chunk_size=100, overlap=50)
        assert len(chunks) > 1


class TestCitationExtraction:
    def test_parenthetical_citation(self):
        text = "As Moretti argues (Moretti 2000), world literature is..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["author"] == "Moretti"
        assert cites[0]["year"] == 2000

    def test_citation_with_page(self):
        text = "The concept of world literature (Damrosch 2003, p. 45) has..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["pages"] == "45"

    def test_chinese_citation(self):
        text = "在比较诗学的视野下（张隆溪 2006），中西文学的关系..."
        cites = extract_citations_from_text(text)
        assert len(cites) >= 1
        assert cites[0]["type"] == "chinese"
        assert cites[0]["year"] == 2006

    def test_no_citations(self):
        text = "A simple sentence without any citations."
        cites = extract_citations_from_text(text)
        assert len(cites) == 0


class TestAuthorNormalization:
    def test_first_last_to_last_first(self):
        assert normalize_author_name("Franco Moretti") == "Moretti, Franco"

    def test_already_last_first(self):
        assert normalize_author_name("Moretti, Franco") == "Moretti, Franco"

    def test_single_name(self):
        assert normalize_author_name("Voltaire") == "Voltaire"

    def test_multiple_names(self):
        assert normalize_author_name("Gayatri Chakravorty Spivak") == "Spivak, Gayatri Chakravorty"


class TestWordCount:
    def test_english_word_count(self):
        text = "This is a test sentence with eight words total."
        # "total." counts as one word
        assert word_count(text) == 9

    def test_chinese_word_count(self):
        text = "这是一个测试句子"
        count = word_count(text, language="zh")
        assert count == 8  # 8 Chinese characters

    def test_empty_text(self):
        assert word_count("") == 0

    def test_mixed_chinese_english(self):
        text = "比较文学 comparative literature 研究"
        count = word_count(text, language="zh")
        assert count > 0  # Should count both Chinese chars and English words
