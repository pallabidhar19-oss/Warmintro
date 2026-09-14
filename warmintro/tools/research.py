"""Research tool: turns raw lead fields into a short list of personalization hooks.

In this reference build the tool works from fields you already have in your
CRM/spreadsheet export (title, company, notes, a pasted LinkedIn/company
blurb). That keeps the demo deterministic and API-key-free.

Production extension point: swap `extract_hooks_from_notes` for a real
enrichment call (e.g. a Clay/Apollo/Bright Data lookup, or Strands' own
`http_request` / web-search community tools) — the rest of the pipeline
doesn't change, because the tool's contract (return a short list of hook
strings) stays the same. That swap is the main thing to point to if you're
pitching this as a paid Upwork build: "bring your own enrichment source."
"""

from strands import tool


@tool
def extract_hooks_from_notes(
    company: str,
    title: str,
    notes: str = "",
) -> list[str]:
    """Extract 2-4 short, concrete personalization hooks for a cold outreach message.

    A "hook" is a specific, verifiable detail about the person or company that
    makes a message read as researched rather than templated — e.g. a recent
    product launch, a role-specific priority, a shared connection, or a
    mutual pain point implied by their title.

    Args:
        company: The lead's company name.
        title: The lead's job title.
        notes: Any free-text context you already have — a LinkedIn bio
            snippet, recent company news, a mutual contact, prior interaction
            history. Pass an empty string if you have nothing yet; the tool
            will fall back to role-based hooks.

    Returns:
        A list of 2-4 short hook strings the drafting agent can weave into
        the outreach message. This is a plain data tool (no LLM call) so the
        pipeline stays fast and cheap to run over long lead lists; the LLM
        reasoning happens downstream in the drafting agent.
    """
    hooks: list[str] = []

    if notes.strip():
        # Surface the notes as-is as the strongest hook — real research beats
        # a generic guess every time.
        hooks.append(notes.strip())

    # Lightweight role-based fallback hooks so the pipeline never produces an
    # empty hook list, even for a bare title+company row.
    title_lower = title.lower()
    if any(k in title_lower for k in ["logistics", "supply chain", "operations"]):
        hooks.append(
            f"As {title} at {company}, cross-border shipment visibility and "
            "customs delays are likely a recurring headache worth a quick "
            "compare-notes conversation."
        )
    elif any(k in title_lower for k in ["sales", "business development", "bd", "partnerships"]):
        hooks.append(
            f"As {title} at {company}, pipeline predictability and outbound "
            "response rates are probably top of mind right now."
        )
    elif any(k in title_lower for k in ["cfo", "finance", "treasury"]):
        hooks.append(
            f"As {title} at {company}, cash visibility and vendor/customer "
            "payment cycles are a natural area to compare notes on."
        )
    else:
        hooks.append(f"{company} is doing interesting work in its space worth learning more about.")

    hooks.append(f"Company: {company}")
    return hooks[:4]
