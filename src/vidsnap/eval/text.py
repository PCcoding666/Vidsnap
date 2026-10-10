"""Deterministic text normalisation, keyword matching and error rates."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

_CJK_RANGES = (
    (0x4E00, 0x9FFF),
    (0x3400, 0x4DBF),
    (0xF900, 0xFAFF),
)
_MAX_ALIGN_TOKENS = 4000


def is_cjk(character: str) -> bool:
    code_point = ord(character)
    return any(start <= code_point <= end for start, end in _CJK_RANGES)


def normalize(text: str) -> str:
    """NFKC, case-fold, then keep only letters, digits and combining marks."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in folded if unicodedata.category(character)[0] in "LNM")


_MINUS_SIGNS = str.maketrans({"\u2212": "-", "\uff0d": "-", "\ufe63": "-", "\u2013": "-"})
_MATH_KEEP = frozenset("+-=<>×÷/.≠≤≥")


def normalize_math(text: str) -> str:
    """Like ``normalize`` but keeps signs and relations, so ``x=-2`` differs from ``x=2``."""
    folded = unicodedata.normalize("NFKC", text).translate(_MINUS_SIGNS).casefold()
    return "".join(
        character
        for character in folded
        if unicodedata.category(character)[0] in "LNM" or character in _MATH_KEEP
    )


def matches_math(text: str, groups: Sequence[Sequence[str]]) -> bool:
    """``matches`` under ``normalize_math`` for formulas and answers."""
    normalized = normalize_math(text)
    return all(
        any(
            normalize_math(alternative) and normalize_math(alternative) in normalized
            for alternative in group
        )
        for group in groups
    )


def matches(normalized_text: str, groups: Sequence[Sequence[str]]) -> bool:
    """True when every group has at least one alternative in the normalised text."""
    return all(
        any(
            normalize(alternative) and normalize(alternative) in normalized_text
            for alternative in group
        )
        for group in groups
    )


def cjk_ratio(text: str) -> float:
    """Share of CJK characters among letters (0 when there are none)."""
    letters = [character for character in text if unicodedata.category(character)[0] == "L"]
    if not letters:
        return 0.0
    return sum(1 for character in letters if is_cjk(character)) / len(letters)


def error_tokens(text: str, language: str) -> list[str]:
    """Characters for Chinese (CER), lower-case words for English (WER)."""
    if language == "zh":
        return list(normalize(text))
    folded = unicodedata.normalize("NFKC", text).casefold()
    words: list[str] = []
    current: list[str] = []
    for character in folded:
        if unicodedata.category(character)[0] in "LNM" or character == "'":
            current.append(character)
            continue
        if current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def edit_distance(hypothesis: Sequence[str], reference: Sequence[str]) -> int:
    """Levenshtein distance over token sequences."""
    if not reference:
        return len(hypothesis)
    previous = list(range(len(reference) + 1))
    for index, token in enumerate(hypothesis, start=1):
        current = [index] + [0] * len(reference)
        for position, expected in enumerate(reference, start=1):
            current[position] = min(
                previous[position] + 1,
                current[position - 1] + 1,
                previous[position - 1] + (0 if token == expected else 1),
            )
        previous = current
    return previous[-1]


def error_rate(hypothesis: str, reference: str, language: str) -> tuple[float | None, bool]:
    """CER (zh) or WER (en) of a hypothesis; the flag marks a truncated alignment."""
    reference_tokens = error_tokens(reference, language)
    if not reference_tokens:
        return None, False
    hypothesis_tokens = error_tokens(hypothesis, language)
    truncated = (
        len(reference_tokens) > _MAX_ALIGN_TOKENS or len(hypothesis_tokens) > _MAX_ALIGN_TOKENS
    )
    reference_tokens = reference_tokens[:_MAX_ALIGN_TOKENS]
    hypothesis_tokens = hypothesis_tokens[:_MAX_ALIGN_TOKENS]
    distance = edit_distance(hypothesis_tokens, reference_tokens)
    return round(distance / len(reference_tokens), 4), truncated


def parse_timestamp(value: object) -> object:
    """Accept seconds, or ``MM:SS`` / ``HH:MM:SS`` strings, for timestamp fields."""
    if isinstance(value, str):
        text = value.strip()
        if ":" in text:
            parts = text.split(":")
            try:
                numbers = [float(part) for part in parts]
            except ValueError:
                return value
            seconds = 0.0
            for number in numbers:
                seconds = seconds * 60 + number
            return seconds
        try:
            return float(text.rstrip("s"))
        except ValueError:
            return value
    return value


def format_clock(seconds: float) -> str:
    """``HH:MM:SS`` for display."""
    whole = max(0, int(round(seconds)))
    return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d}"
