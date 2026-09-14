"""The two LLM agents in the WarmIntro pipeline.

Architecture (see README.md for the diagram):

    lead row --> [research tool] --> hooks
                                        |
                                        v
                              [drafting agent] --draft--> [qa agent] --verdict-->
                                        ^                      |
                                        |__________feedback____|  (loop, max 2 revisions)

Both agents are plain `strands.Agent` instances. Keeping them as two
separate, single-responsibility agents (rather than one agent doing
everything) is what makes the QA step meaningful — the drafting agent can't
grade its own homework.
"""

from strands import Agent

from warmintro.config import get_model
from warmintro.tools.compliance import check_message_rules
from warmintro.tools.research import extract_hooks_from_notes
from warmintro.voice_profile import DEFAULT_VOICE_PROFILE

DRAFTER_SYSTEM_PROMPT = f"""You are an outreach copywriter. You write short,
genuinely personalized first-touch cold messages and follow-ups for B2B
outreach (LinkedIn or email).

{DEFAULT_VOICE_PROFILE}

Always call the extract_hooks_from_notes tool first to ground the message in
real details about the lead before writing.

Output format (always use exactly this structure, nothing before or after):

FIRST_TOUCH:
<message text>

FOLLOW_UP:
<message text>
"""

QA_SYSTEM_PROMPT = """You are a strict outreach QA reviewer. You review a
drafted cold outreach message against both objective rules and your own
judgment of whether it reads as genuinely personalized versus templated.

Always call the check_message_rules tool on the FIRST_TOUCH message first.
Then form your own judgment. A message only PASSES if it (a) passes the
tool's objective checks AND (b) reads as specific to this individual lead,
not swappable to any other lead in the same role.

If it fails either check, explain exactly what to fix in one or two concrete
sentences — not vague feedback like "make it more personal."

Output format (always use exactly this structure, nothing before or after):

VERDICT: PASS or REVISE
FEEDBACK: <one or two concrete sentences; write "None" if PASS>
"""


def build_drafting_agent() -> Agent:
    return Agent(
        model=get_model(temperature=0.8),
        tools=[extract_hooks_from_notes],
        system_prompt=DRAFTER_SYSTEM_PROMPT,
    )


def build_qa_agent() -> Agent:
    return Agent(
        model=get_model(temperature=0.0),
        tools=[check_message_rules],
        system_prompt=QA_SYSTEM_PROMPT,
    )
