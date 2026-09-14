#!/usr/bin/env python3
"""Streamlit demo UI for WarmIntro.

This is the live-demo surface for the Agents for Humans Hackathon submission:
upload a lead CSV (or use the bundled sample), watch each lead move through
the drafting agent -> QA agent loop in real time, then download the batch
report.

Run locally:
    streamlit run app.py

Deploy (e.g. Streamlit Community Cloud) the same way Narae is deployed, so
the "Live demo link" field in the Devpost submission can point at a real URL
instead of just a repo.
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path

import streamlit as st

from warmintro.pipeline import (
    LeadResult,
    build_csv_report,
    build_markdown_report,
    compute_impact_summary,
    process_lead,
)
from warmintro.agents import build_drafting_agent, build_qa_agent

st.set_page_config(page_title="WarmIntro", page_icon="✉️", layout="wide")

st.title("✉️ WarmIntro")
st.caption(
    "Turns a spreadsheet of cold leads into ready-to-send, personalized "
    "outreach — end to end, not just chat. Built on the Strands Agents SDK "
    "for the Agents for Humans Hackathon (Professional Agents track)."
)

with st.sidebar:
    st.header("How it works")
    st.markdown(
        "1. **Research tool** pulls 2-4 concrete hooks per lead\n"
        "2. **Drafting agent** writes a first-touch + follow-up\n"
        "3. **QA agent** checks it against compliance rules *and* whether "
        "it's genuinely specific to that lead — sends it back for a rewrite "
        "if not (max 2 rounds)\n"
        "4. You get a batch report, ready to paste into LinkedIn or email"
    )
    st.divider()

    provider = os.environ.get("WARMINTRO_MODEL_PROVIDER", "anthropic").strip().lower()
    _required_key_by_provider = {
        "anthropic": "ANTHROPIC_API_KEY",
        "bedrock": None,  # uses AWS credential resolution, not a single env var
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }
    required_key = _required_key_by_provider.get(provider)

    if provider == "bedrock":
        has_creds = bool(
            os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")
        )
        if has_creds:
            st.success("Model provider: Amazon Bedrock (AWS credentials detected).", icon="✅")
            api_key = "bedrock"  # any truthy value; run button just needs non-empty
        else:
            st.warning(
                "Model provider is set to Bedrock but no AWS credentials were "
                "detected. Set them (see .env.example).",
                icon="⚠️",
            )
            api_key = ""
    else:
        api_key = os.environ.get(required_key or "", "")
        if not api_key:
            st.warning(
                f"No {required_key} found in the environment. Set it before "
                "running (see .env.example) — the agents won't be able to call "
                "the model without it.",
                icon="⚠️",
            )
        else:
            st.success(f"Model provider: {provider} (API key detected).", icon="✅")

st.subheader("1. Load your leads")

col1, col2 = st.columns([2, 1])
with col1:
    uploaded = st.file_uploader(
        "Upload a CSV with columns: name, title, company, notes",
        type=["csv"],
    )
with col2:
    use_sample = st.checkbox("Use bundled sample leads instead", value=uploaded is None)

if uploaded is not None and not use_sample:
    raw_text = uploaded.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(raw_text)))
    source_label = uploaded.name
else:
    sample_path = Path(__file__).parent / "data" / "sample_leads.csv"
    rows = list(csv.DictReader(sample_path.open(encoding="utf-8")))
    source_label = "data/sample_leads.csv (bundled sample)"

st.caption(f"Loaded **{len(rows)}** lead(s) from `{source_label}`.")
st.dataframe(rows, use_container_width=True, hide_index=True)

st.subheader("2. Run the pipeline")
run = st.button("Run WarmIntro on these leads", type="primary", disabled=not api_key)

if run:
    drafting_agent = build_drafting_agent()
    qa_agent = build_qa_agent()

    results: list[LeadResult] = []
    progress = st.progress(0.0, text="Starting...")
    result_area = st.container()

    for i, row in enumerate(rows):
        name = row.get("name", "").strip()
        title = row.get("title", "").strip()
        company = row.get("company", "").strip()
        notes = row.get("notes", "").strip()

        progress.progress(i / max(len(rows), 1), text=f"Processing {name}...")

        result = process_lead(drafting_agent, qa_agent, name, title, company, notes)
        results.append(result)

        with result_area:
            verdict_icon = "✅" if result.qa_verdict == "PASS" else "⚠️"
            with st.expander(
                f"{verdict_icon} {result.name} — {result.title}, {result.company} "
                f"(QA: {result.qa_verdict}, {result.revisions_used} revision(s))",
                expanded=True,
            ):
                if result.hooks:
                    st.caption("Personalization hooks used:")
                    st.markdown("\n".join(f"- {h}" for h in result.hooks))
                st.markdown("**First touch:**")
                st.info(result.first_touch)
                st.markdown("**Follow-up:**")
                st.info(result.follow_up)
                if result.qa_verdict != "PASS":
                    st.warning(f"Outstanding QA note: {result.qa_feedback}")

        time.sleep(0.1)

    progress.progress(1.0, text="Done.")
    summary = compute_impact_summary(results)
    st.success(
        f"{summary['passed']}/{summary['n']} leads passed QA and are ready to send "
        f"({summary['revised']}/{summary['n']} needed at least one QA-driven rewrite)."
    )

    st.subheader("Estimated impact on this batch")
    icol1, icol2, icol3 = st.columns(3)
    icol1.metric("Pipeline time", f"{summary['pipeline_seconds']:.0f}s")
    icol2.metric(
        "Manual-equivalent time",
        f"{summary['manual_hours_equivalent']:.1f}h",
        help=(
            f"Assumes ~{summary['assumed_manual_minutes_per_lead']} minutes per "
            "lead to manually research, draft, and self-review a comparably "
            "personalized message — a common B2B outreach benchmark, not a "
            "measurement of any specific team's actual speed."
        ),
    )
    if summary["speedup_factor"]:
        icol3.metric("Estimated speedup", f"{summary['speedup_factor']:.0f}x")
    st.caption(
        "The manual-time figure above is a stated assumption (see the ⓘ on "
        "\"Manual-equivalent time\"), used consistently in the downloadable "
        "report below — it's shown so the time savings are quantified, not "
        "just asserted."
    )

    # Build downloadable outputs — reuses the exact same report-building code
    # as the CLI (warmintro/pipeline.py), so the two surfaces never diverge.
    md_report = build_markdown_report(results)
    csv_report = build_csv_report(results)

    st.subheader("3. Download results")
    dcol1, dcol2 = st.columns(2)
    with dcol1:
        st.download_button("Download drafts.md", md_report, file_name="drafts.md", mime="text/markdown")
    with dcol2:
        st.download_button("Download drafts.csv", csv_report, file_name="drafts.csv", mime="text/csv")

st.divider()
st.caption(
    "WarmIntro · Strands Agents SDK · Agents for Humans Hackathon 2026 · "
    "MIT licensed — see LICENSE"
)
