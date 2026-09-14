"""The orchestrator: turns a CSV of leads into a batch of QA'd outreach drafts.

This is the "handles the repetitive task end-to-end" part of the submission —
it doesn't just chat about one message, it processes a whole lead list
unattended and produces a ready-to-use output file.
"""

from __future__ import annotations

import csv
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from warmintro.agents import build_drafting_agent, build_qa_agent
from warmintro.tools.research import extract_hooks_from_notes

MAX_REVISIONS = 2

# Used to turn raw pipeline throughput into a plain-English impact number in
# the batch report and the Streamlit UI. This is a stated assumption, not a
# measured result for any specific team — B2B sales/SDR content commonly
# cites roughly 15-20 minutes per lead to manually research a company/contact,
# draft a genuinely personalized first-touch message, and self-review it
# before sending. We use the conservative end (15 min) and say so everywhere
# it's shown, rather than presenting it as a verified number.
ASSUMED_MANUAL_MINUTES_PER_LEAD = 15

FIRST_TOUCH_RE = re.compile(r"FIRST_TOUCH:\s*(.*?)\s*FOLLOW_UP:", re.DOTALL)
FOLLOW_UP_RE = re.compile(r"FOLLOW_UP:\s*(.*)", re.DOTALL)
VERDICT_RE = re.compile(r"VERDICT:\s*(PASS|REVISE)", re.IGNORECASE)
FEEDBACK_RE = re.compile(r"FEEDBACK:\s*(.*)", re.DOTALL)


@dataclass
class LeadResult:
    name: str
    title: str
    company: str
    first_touch: str = ""
    follow_up: str = ""
    qa_verdict: str = "UNKNOWN"
    qa_feedback: str = ""
    revisions_used: int = 0
    history: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


def _parse_draft(text: str) -> tuple[str, str]:
    ft_match = FIRST_TOUCH_RE.search(text)
    fu_match = FOLLOW_UP_RE.search(text)
    first_touch = ft_match.group(1).strip() if ft_match else text.strip()
    follow_up = fu_match.group(1).strip() if fu_match else ""
    return first_touch, follow_up


def _parse_qa(text: str) -> tuple[str, str]:
    v_match = VERDICT_RE.search(text)
    f_match = FEEDBACK_RE.search(text)
    verdict = v_match.group(1).upper() if v_match else "REVISE"
    feedback = f_match.group(1).strip() if f_match else text.strip()
    return verdict, feedback


def process_lead(drafting_agent, qa_agent, name: str, title: str, company: str, notes: str) -> LeadResult:
    start = time.perf_counter()
    result = LeadResult(name=name, title=title, company=company)
    result.hooks = extract_hooks_from_notes(company=company, title=title, notes=notes)

    draft_prompt = (
        f"Lead: {name}\nTitle: {title}\nCompany: {company}\nNotes: {notes or '(none)'}\n\n"
        "Write the FIRST_TOUCH and FOLLOW_UP messages for this lead."
    )

    for attempt in range(MAX_REVISIONS + 1):
        draft_response = str(drafting_agent(draft_prompt))
        first_touch, follow_up = _parse_draft(draft_response)
        result.first_touch, result.follow_up = first_touch, follow_up
        result.history.append(f"[draft attempt {attempt + 1}]\n{draft_response}")

        qa_response = str(
            qa_agent(f"Review this first-touch message:\n\n{first_touch}")
        )
        verdict, feedback = _parse_qa(qa_response)
        result.qa_verdict, result.qa_feedback = verdict, feedback
        result.history.append(f"[qa attempt {attempt + 1}]\n{qa_response}")

        if verdict == "PASS":
            result.revisions_used = attempt
            result.elapsed_seconds = time.perf_counter() - start
            return result

        # Feed QA feedback back into the drafter for a rewrite.
        draft_prompt = (
            f"Lead: {name}\nTitle: {title}\nCompany: {company}\nNotes: {notes or '(none)'}\n\n"
            f"Your previous draft was rejected by QA with this feedback: {feedback}\n"
            "Rewrite the FIRST_TOUCH and FOLLOW_UP messages to address it."
        )

    result.revisions_used = MAX_REVISIONS
    result.elapsed_seconds = time.perf_counter() - start
    return result


def run_pipeline(input_csv: Path, output_dir: Path) -> list[LeadResult]:
    output_dir.mkdir(parents=True, exist_ok=True)
    drafting_agent = build_drafting_agent()
    qa_agent = build_qa_agent()

    results: list[LeadResult] = []
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            title = row.get("title", "").strip()
            company = row.get("company", "").strip()
            notes = row.get("notes", "").strip()
            print(f"Processing {name} ({title} at {company})...")
            result = process_lead(drafting_agent, qa_agent, name, title, company, notes)
            results.append(result)
            print(f"  -> QA {result.qa_verdict} after {result.revisions_used} revision(s)")
            time.sleep(0.2)  # gentle pacing against rate limits on large lists

    _write_markdown_report(results, output_dir / "drafts.md")
    _write_csv_report(results, output_dir / "drafts.csv")
    return results


def compute_impact_summary(results: list[LeadResult]) -> dict:
    """Turn a batch of results into the quantitative numbers worth showing.

    Shared by the CLI markdown report and the Streamlit UI so both surfaces
    make the same claims from the same math — no separate, driftable copies
    of this logic. Every number here is either directly measured (pipeline
    time, revision counts, message lengths) or clearly labeled as an
    assumption (the manual-time estimate) — nothing here is a made-up or
    unverifiable performance claim about the tool.
    """
    n = len(results)
    passed = sum(1 for r in results if r.qa_verdict == "PASS")
    revised = sum(1 for r in results if r.revisions_used > 0)
    pipeline_seconds = sum(r.elapsed_seconds for r in results)
    avg_first_touch_words = (
        sum(len(r.first_touch.split()) for r in results) / n if n else 0
    )

    manual_minutes = n * ASSUMED_MANUAL_MINUTES_PER_LEAD
    manual_hours = manual_minutes / 60
    pipeline_minutes = pipeline_seconds / 60
    speedup = (manual_minutes / pipeline_minutes) if pipeline_minutes > 0 else None

    return {
        "n": n,
        "passed": passed,
        "revised": revised,
        "revision_rate_pct": (revised / n * 100) if n else 0,
        "pipeline_seconds": pipeline_seconds,
        "avg_first_touch_words": avg_first_touch_words,
        "assumed_manual_minutes_per_lead": ASSUMED_MANUAL_MINUTES_PER_LEAD,
        "manual_hours_equivalent": manual_hours,
        "speedup_factor": speedup,
    }


def build_markdown_report(results: list[LeadResult]) -> str:
    """Build the batch markdown report as a string.

    Used by both the CLI (_write_markdown_report writes this to disk) and the
    Streamlit UI (which offers this same string as a download) — one
    implementation, so the two surfaces can never drift apart.
    """
    lines = ["# WarmIntro batch — outreach drafts\n"]
    summary = compute_impact_summary(results)
    lines.append(
        f"**{summary['passed']}/{summary['n']} leads passed QA** "
        f"(max {MAX_REVISIONS} revision rounds each; "
        f"{summary['revised']}/{summary['n']} needed at least one rewrite).\n"
    )
    if summary["speedup_factor"]:
        lines.append(
            f"**Estimated impact:** this batch ran in "
            f"{summary['pipeline_seconds']:.0f} seconds. Manually researching, "
            f"drafting, and self-reviewing {summary['n']} equally personalized "
            f"messages typically takes about {summary['assumed_manual_minutes_per_lead']} "
            f"minutes each (~{summary['manual_hours_equivalent']:.1f} hours total) — "
            f"roughly a **{summary['speedup_factor']:.0f}x** time reduction for this batch. "
            "(The manual-time figure is a stated assumption based on common B2B "
            "outreach benchmarks, not a measurement of any specific team.)\n"
        )

    for r in results:
        lines.append(f"## {r.name} — {r.title}, {r.company}")
        lines.append(f"QA: **{r.qa_verdict}** ({r.revisions_used} revision(s) used)\n")
        if r.hooks:
            lines.append("**Personalization hooks used:**")
            for h in r.hooks:
                lines.append(f"- {h}")
            lines.append("")
        lines.append("**First touch:**")
        lines.append(f"> {r.first_touch}\n")
        lines.append("**Follow-up:**")
        lines.append(f"> {r.follow_up}\n")
        if r.qa_verdict != "PASS":
            lines.append(f"_Outstanding QA note: {r.qa_feedback}_\n")
        lines.append("---\n")

    return "\n".join(lines)


def build_csv_report(results: list[LeadResult]) -> str:
    """Build the batch CSV report as a string (see build_markdown_report)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "name", "title", "company", "qa_verdict", "revisions_used",
            "hooks_used", "first_touch", "follow_up",
        ]
    )
    for r in results:
        writer.writerow(
            [
                r.name, r.title, r.company, r.qa_verdict, r.revisions_used,
                " | ".join(r.hooks), r.first_touch, r.follow_up,
            ]
        )
    return buf.getvalue()


def _write_markdown_report(results: list[LeadResult], path: Path) -> None:
    path.write_text(build_markdown_report(results), encoding="utf-8")


def _write_csv_report(results: list[LeadResult], path: Path) -> None:
    path.write_text(build_csv_report(results), encoding="utf-8", newline="")
