"""Compliance tool: objective, rule-based checks the QA agent runs before
(and alongside) its own subjective judgment of a draft message.

Keeping these checks as a plain-code tool rather than folding them into the
QA agent's prompt means they're 100% deterministic and auditable — useful if
you're selling this as a service and a client asks "how do you guarantee it
never promises something we can't deliver."
"""

import re

from strands import tool

BANNED_PHRASES = [
    "guaranteed results",
    "risk-free",
    "act now",
    "limited time offer",
    "dear sir/madam",
    "to whom it may concern",
    "i'm reaching out because i think you'd be a great fit for our product",
    "circling back",
    "just checking in",
]

OVERPROMISE_PATTERNS = [
    r"\bwe (can|will) (guarantee|promise)\b",
    r"\b\d{2,3}%\s?(increase|reduction|roi)\b",  # unverified stat claims
    r"\bconfidential(ly)?\b",
]


@tool
def check_message_rules(message: str, max_words: int = 120) -> dict:
    """Run objective compliance checks against an outreach message.

    Args:
        message: The drafted outreach message text.
        max_words: Maximum acceptable word count for a first-touch cold
            message (default 120 — long cold messages get ignored).

    Returns:
        A dict: {
            "word_count": int,
            "over_length": bool,
            "banned_phrases_found": list[str],
            "overpromise_flags": list[str],
            "has_question": bool,   # a good cold message ends with a low-effort ask
            "passes_objective_checks": bool,
        }
    """
    lower = message.lower()
    word_count = len(message.split())

    banned_found = [p for p in BANNED_PHRASES if p in lower]
    overpromise_found = [p for p in OVERPROMISE_PATTERNS if re.search(p, lower)]
    has_question = "?" in message

    passes = (
        word_count <= max_words
        and not banned_found
        and not overpromise_found
        and has_question
    )

    return {
        "word_count": word_count,
        "over_length": word_count > max_words,
        "banned_phrases_found": banned_found,
        "overpromise_flags": overpromise_found,
        "has_question": has_question,
        "passes_objective_checks": passes,
    }
