"""Default voice profile / tone rules for WarmIntro's drafting agent.

This encodes a specific, opinionated outreach philosophy (warm, curiosity-led,
no pitching, no confidential claims) rather than generic "friendly sales
copy" — that specificity is what makes the drafts sound like a real person
and not a mail-merge. Treat this file as the thing a buyer customizes per
client when you resell WarmIntro as a service: swap this text, keep the
pipeline.
"""

DEFAULT_VOICE_PROFILE = """
Tone rules for all outreach messages:
1. Warm and role-specific, never generic. Reference something concrete about
   the person's role or company — not "I noticed your profile."
2. Seek the recipient's perspective rather than pitching a product. Frame the
   message as genuine curiosity about how they handle a specific challenge,
   not as a sales pitch.
3. No confidential, proprietary, or unverifiable claims about what "we" do —
   keep any description of the sender's work general and outcome-agnostic.
4. Never promise guaranteed results, use urgency language, or open with
   "I hope this finds you well" / "Dear Sir/Madam."
5. End with a single, low-effort ask (a short question, not "let's hop on a
   30-min call this week").
6. Keep the first-touch message under 100 words. The follow-up should be
   under 50 words and reference the first message rather than repeating it.
""".strip()
