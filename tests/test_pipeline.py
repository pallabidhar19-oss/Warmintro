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
