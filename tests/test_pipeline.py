"""Smoke tests for the WarmIntro pipeline that don't require a live API key.

These stub out the two LLM agents with scripted callables so we can verify
the orchestration logic (parsing, revision looping, report writing) works
correctly without spending API calls. Run with: python -m pytest tests/ -v
"""

import csv
from pathlib import Path

from warmintro import pipeline


class FakeAgent:
    """Stands in for a strands.Agent: a callable that returns scripted text."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, prompt):
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else self._responses[-1]


def test_parse_draft():
    text = "FIRST_TOUCH:\nHello there, quick question.\nFOLLOW_UP:\nJust bumping this up!"
    first_touch, follow_up = pipeline._parse_draft(text)
    assert first_touch == "Hello there, quick question."
    assert follow_up == "Just bumping this up!"


def test_parse_qa_pass():
    text = "VERDICT: PASS\nFEEDBACK: None"
    verdict, feedback = pipeline._parse_qa(text)
    assert verdict == "PASS"
    assert feedback == "None"


def test_process_lead_passes_on_first_try():
    drafting_agent = FakeAgent([
        "FIRST_TOUCH:\nSaw your post about customs delays — curious how you're handling it?\nFOLLOW_UP:\nStill curious if you found a workaround!"
    ])
    qa_agent = FakeAgent(["VERDICT: PASS\nFEEDBACK: None"])

    result = pipeline.process_lead(
        drafting_agent, qa_agent, "Jordan Reyes", "Director of Logistics", "Fictional Freight Co", "customs delays"
    )

    assert result.qa_verdict == "PASS"
    assert result.revisions_used == 0
    assert "customs delays" in result.first_touch.lower()
    assert len(drafting_agent.calls) == 1
    assert len(qa_agent.calls) == 1


def test_process_lead_revises_once_then_passes():
    drafting_agent = FakeAgent([
        "FIRST_TOUCH:\nact now, guaranteed results!\nFOLLOW_UP:\ncircling back",
        "FIRST_TOUCH:\nSaw your recent expansion news — what's been the trickiest part?\nFOLLOW_UP:\nNo pressure, just curious!",
    ])
    qa_agent = FakeAgent([
        "VERDICT: REVISE\nFEEDBACK: Remove banned phrases and add a real question.",
        "VERDICT: PASS\nFEEDBACK: None",
    ])

    result = pipeline.process_lead(
        drafting_agent, qa_agent, "Amara Okafor", "VP Business Development", "Northwind Commerce", "European expansion"
    )

    assert result.qa_verdict == "PASS"
    assert result.revisions_used == 1
    assert len(drafting_agent.calls) == 2
    assert "previous draft was rejected" in drafting_agent.calls[1]


def test_process_lead_captures_hooks_and_timing():
    drafting_agent = FakeAgent([
        "FIRST_TOUCH:\nSaw your post about customs delays — curious how you're handling it?\nFOLLOW_UP:\nStill curious!"
    ])
    qa_agent = FakeAgent(["VERDICT: PASS\nFEEDBACK: None"])

    result = pipeline.process_lead(
        drafting_agent, qa_agent, "Jordan Reyes", "Director of Logistics", "Fictional Freight Co", "customs delays"
    )

    assert result.hooks, "expected the research tool's hooks to be captured on the result"
    assert any("customs delays" in h for h in result.hooks)
    assert result.elapsed_seconds >= 0


def test_compute_impact_summary_math():
    results = [
        pipeline.LeadResult(
            name="A", title="T", company="C", qa_verdict="PASS",
            revisions_used=0, first_touch="one two three", elapsed_seconds=1.0,
        ),
        pipeline.LeadResult(
            name="B", title="T", company="C", qa_verdict="PASS",
            revisions_used=1, first_touch="one two three four", elapsed_seconds=2.0,
        ),
    ]

    summary = pipeline.compute_impact_summary(results)

    assert summary["n"] == 2
    assert summary["passed"] == 2
    assert summary["revised"] == 1
    assert summary["revision_rate_pct"] == 50.0
    assert summary["pipeline_seconds"] == 3.0
    assert summary["assumed_manual_minutes_per_lead"] == pipeline.ASSUMED_MANUAL_MINUTES_PER_LEAD
    expected_manual_minutes = 2 * pipeline.ASSUMED_MANUAL_MINUTES_PER_LEAD
    assert summary["speedup_factor"] == expected_manual_minutes / (3.0 / 60)


def test_build_markdown_report_includes_impact_and_hooks():
    results = [
        pipeline.LeadResult(
            name="Jordan Reyes", title="Director of Logistics", company="Fictional Freight Co",
            qa_verdict="PASS", revisions_used=0, first_touch="Hi Jordan", follow_up="Following up",
            hooks=["customs delays"], elapsed_seconds=1.5,
        ),
    ]

    report = pipeline.build_markdown_report(results)

    assert "Estimated impact" in report
    assert "customs delays" in report
    assert "Jordan Reyes" in report


def test_build_csv_report_includes_hooks_column():
    results = [
        pipeline.LeadResult(
            name="Jordan Reyes", title="Director of Logistics", company="Fictional Freight Co",
            qa_verdict="PASS", revisions_used=0, first_touch="Hi Jordan", follow_up="Following up",
            hooks=["customs delays", "Company: Fictional Freight Co"], elapsed_seconds=1.5,
        ),
    ]

    csv_text = pipeline.build_csv_report(results)

    assert "hooks_used" in csv_text
    assert "customs delays" in csv_text


def test_run_pipeline_end_to_end(tmp_path, monkeypatch):
    input_csv = tmp_path / "leads.csv"
    with open(input_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "title", "company", "notes"])
        writer.writerow(["Test Lead", "CFO", "Acme Corp", "raised a new fund"])

    fake_draft = FakeAgent(["FIRST_TOUCH:\nCurious how Acme is thinking about cash cycles?\nFOLLOW_UP:\nStill curious!"])
    fake_qa = FakeAgent(["VERDICT: PASS\nFEEDBACK: None"])

    monkeypatch.setattr(pipeline, "build_drafting_agent", lambda: fake_draft)
    monkeypatch.setattr(pipeline, "build_qa_agent", lambda: fake_qa)

    output_dir = tmp_path / "output"
    results = pipeline.run_pipeline(input_csv, output_dir)

    assert len(results) == 1
    assert results[0].qa_verdict == "PASS"
    assert (output_dir / "drafts.md").exists()
    assert (output_dir / "drafts.csv").exists()
    assert "Test Lead" in (output_dir / "drafts.md").read_text()
