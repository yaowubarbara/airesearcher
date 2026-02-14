"""Style checking for academic manuscripts.

Performs rule-based checks for academic register, voice balance, paragraph
length, quotation integration, and section transitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class StyleIssue:
    """A single style issue detected in the text."""

    location: str  # approximate location (e.g. "paragraph 3", "line 42")
    issue_type: str  # e.g. "passive_voice", "paragraph_length"
    description: str
    suggestion: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Common informal / non-academic words and phrases
_INFORMAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(a lot of)\b", re.IGNORECASE), 'Replace "a lot of" with "numerous", "many", or "substantial".'),
    (re.compile(r"\b(pretty much)\b", re.IGNORECASE), 'Avoid colloquial "pretty much"; use "largely" or "essentially".'),
    (re.compile(r"\b(kind of|sort of)\b", re.IGNORECASE), 'Avoid hedging with "kind of/sort of"; be precise.'),
    (re.compile(r"\b(gonna|wanna|gotta)\b", re.IGNORECASE), "Replace contractions/slang with formal equivalents."),
    (re.compile(r"\b(don't|can't|won't|isn't|aren't|wouldn't|shouldn't|couldn't)\b"), "Avoid contractions in academic writing; spell them out."),
    (re.compile(r"\b(stuff|things)\b", re.IGNORECASE), 'Replace vague nouns ("stuff", "things") with specific terms.'),
    (re.compile(r"\b(basically|obviously|clearly)\b", re.IGNORECASE), "Avoid filler adverbs that weaken academic register."),
]

# Passive voice detection (simple heuristic)
_PASSIVE_RE = re.compile(
    r"\b(is|are|was|were|be|been|being)\s+([\w]+ed|[\w]+en)\b",
    re.IGNORECASE,
)

# Active first-person patterns
_ACTIVE_FIRST_PERSON_RE = re.compile(r"\b(I|we)\s+(argue|contend|suggest|propose|analyze|examine|demonstrate|show|claim|maintain)\b", re.IGNORECASE)

# Quotation patterns: bare quotes without introduction
_BARE_QUOTE_RE = re.compile(r'(?:^|(?<=\.\s))"[A-Z]')

# Transition words
_TRANSITION_WORDS = {
    "however", "moreover", "furthermore", "nevertheless", "consequently",
    "therefore", "thus", "indeed", "similarly", "conversely", "meanwhile",
    "in contrast", "on the other hand", "in addition", "as a result",
}


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs (non-empty blocks separated by blank lines)."""
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip()]


def _word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# StyleChecker
# ---------------------------------------------------------------------------


class StyleChecker:
    """Rule-based style checker for academic manuscripts."""

    def check_style(
        self,
        text: str,
        language: str = "en",
        journal_name: str = "",
    ) -> list[StyleIssue]:
        """Run all style checks and return a list of issues.

        Parameters
        ----------
        text : str
            The manuscript text to check.
        language : str
            Language code (currently ``"en"`` has full support).
        journal_name : str
            Target journal name (used for context in suggestions).

        Returns
        -------
        list[StyleIssue]
            Detected style issues.
        """
        issues: list[StyleIssue] = []

        if language != "en":
            # Only English checks are implemented for now
            return issues

        paragraphs = _split_paragraphs(text)

        issues.extend(self._check_academic_register(text))
        issues.extend(self._check_voice_balance(text, paragraphs))
        issues.extend(self._check_paragraph_length(paragraphs))
        issues.extend(self._check_quotation_integration(text, paragraphs))
        issues.extend(self._check_section_transitions(paragraphs))

        return issues

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_academic_register(text: str) -> list[StyleIssue]:
        """Flag informal language that weakens academic register."""
        issues: list[StyleIssue] = []
        lines = text.split("\n")
        for line_no, line in enumerate(lines, start=1):
            for pattern, suggestion in _INFORMAL_PATTERNS:
                match = pattern.search(line)
                if match:
                    issues.append(
                        StyleIssue(
                            location=f"line {line_no}",
                            issue_type="academic_register",
                            description=f'Found informal expression: "{match.group()}".',
                            suggestion=suggestion,
                        )
                    )
        return issues

    @staticmethod
    def _check_voice_balance(text: str, paragraphs: list[str]) -> list[StyleIssue]:
        """Check passive/active voice balance.

        Academic humanities writing should blend active and passive voice.
        Flag if passive voice dominates (>70 %) or is nearly absent (<10 %).
        """
        issues: list[StyleIssue] = []
        passive_count = len(_PASSIVE_RE.findall(text))
        active_count = len(_ACTIVE_FIRST_PERSON_RE.findall(text))
        total = passive_count + active_count

        if total < 5:
            return issues  # not enough signal

        passive_ratio = passive_count / total

        if passive_ratio > 0.70:
            issues.append(
                StyleIssue(
                    location="overall",
                    issue_type="voice_balance",
                    description=f"Passive voice appears dominant ({passive_ratio:.0%} of detected constructions).",
                    suggestion="Introduce more active-voice constructions to strengthen authorial presence.",
                )
            )
        elif passive_ratio < 0.10:
            issues.append(
                StyleIssue(
                    location="overall",
                    issue_type="voice_balance",
                    description=f"Very little passive voice detected ({passive_ratio:.0%}).",
                    suggestion="Consider using passive voice occasionally for variation and objectivity.",
                )
            )

        return issues

    @staticmethod
    def _check_paragraph_length(paragraphs: list[str]) -> list[StyleIssue]:
        """Flag paragraphs that are too short (<50 words) or too long (>350 words)."""
        issues: list[StyleIssue] = []
        for idx, para in enumerate(paragraphs, start=1):
            wc = _word_count(para)
            if wc < 50:
                issues.append(
                    StyleIssue(
                        location=f"paragraph {idx}",
                        issue_type="paragraph_length",
                        description=f"Paragraph is very short ({wc} words).",
                        suggestion="Consider merging with an adjacent paragraph or expanding the point.",
                    )
                )
            elif wc > 350:
                issues.append(
                    StyleIssue(
                        location=f"paragraph {idx}",
                        issue_type="paragraph_length",
                        description=f"Paragraph is very long ({wc} words).",
                        suggestion="Consider splitting into smaller, more focused paragraphs.",
                    )
                )
        return issues

    @staticmethod
    def _check_quotation_integration(text: str, paragraphs: list[str]) -> list[StyleIssue]:
        """Flag quotations that appear without proper introduction (dropped quotes)."""
        issues: list[StyleIssue] = []
        for idx, para in enumerate(paragraphs, start=1):
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sent in sentences:
                sent_stripped = sent.strip()
                if sent_stripped.startswith('"') and len(sent_stripped) > 10:
                    issues.append(
                        StyleIssue(
                            location=f"paragraph {idx}",
                            issue_type="quotation_integration",
                            description="A quotation appears to begin a sentence without an introductory signal phrase.",
                            suggestion='Integrate the quotation with a signal phrase, e.g., "As Author argues, ...".',
                        )
                    )
        return issues

    @staticmethod
    def _check_section_transitions(paragraphs: list[str]) -> list[StyleIssue]:
        """Flag consecutive paragraphs that lack transition signals."""
        issues: list[StyleIssue] = []

        for idx in range(1, len(paragraphs)):
            para = paragraphs[idx]
            first_sentence_end = re.search(r"[.!?]", para)
            first_sentence = para[: first_sentence_end.end()] if first_sentence_end else para[:200]
            first_sentence_lower = first_sentence.lower()

            has_transition = any(tw in first_sentence_lower for tw in _TRANSITION_WORDS)

            # Also accept anaphoric references
            if not has_transition:
                has_transition = bool(
                    re.match(r"\s*(this|these|such|the foregoing|the above|the preceding)", first_sentence_lower)
                )

            if not has_transition and idx > 0:
                # Only flag if the previous paragraph also had no transition
                # (to avoid excessive noise)
                prev_para = paragraphs[idx - 1]
                last_sentence_match = re.search(r"[^.!?]*[.!?]\s*$", prev_para)
                if last_sentence_match:
                    last_sent = last_sentence_match.group().lower()
                    ends_with_transition = any(tw in last_sent for tw in _TRANSITION_WORDS)
                    if not ends_with_transition:
                        issues.append(
                            StyleIssue(
                                location=f"paragraph {idx + 1}",
                                issue_type="section_transition",
                                description="No transitional signal detected at the start of this paragraph.",
                                suggestion="Add a transition word or phrase to improve flow between paragraphs.",
                            )
                        )

        return issues
