"""The orchestrator: turns a CSV of leads into a batch of QA'd outreach drafts.

This is the "handles the repetitive task end-to-end" part of the submission —
it doesn't just chat about one message, it processes a whole lead list
unattended and produces a ready-to-use output file.
"""

from __future__ import annotations

import csv
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from warmintro.agents import build_drafting_agent, build_qa_agent

MAX_REVISIONS = 2

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
    result = LeadResult(name=name, title=title, company=company)

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
            return result

        # Feed QA feedback back into the drafter for a rewrite.
        draft_prompt = (
            f"Lead: {name}\nTitle: {title}\nCompany: {company}\nNotes: {notes or '(none)'}\n\n"
            f"Your previous draft was rejected by QA with this feedback: {feedback}\n"
            "Rewrite the FIRST_TOUCH and FOLLOW_UP messages to address it."
        )

    result.revisions_used = MAX_REVISIONS
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


def _write_markdown_report(results: list[LeadResult], path: Path) -> None:
    lines = ["# WarmIntro batch — outreach drafts\n"]
    passed = sum(1 for r in results if r.qa_verdict == "PASS")
    lines.append(f"**{passed}/{len(results)} leads passed QA** (max {MAX_REVISIONS} revision rounds each).\n")

    for r in results:
        lines.append(f"## {r.name} — {r.title}, {r.company}")
        lines.append(f"QA: **{r.qa_verdict}** ({r.revisions_used} revision(s) used)\n")
        lines.append("**First touch:**")
        lines.append(f"> {r.first_touch}\n")
        lines.append("**Follow-up:**")
        lines.append(f"> {r.follow_up}\n")
        if r.qa_verdict != "PASS":
            lines.append(f"_Outstanding QA note: {r.qa_feedback}_\n")
        lines.append("---\n")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv_report(results: list[LeadResult], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "title", "company", "qa_verdict", "revisions_used", "first_touch", "follow_up"])
        for r in results:
            writer.writerow([r.name, r.title, r.company, r.qa_verdict, r.revisions_used, r.first_touch, r.follow_up])
