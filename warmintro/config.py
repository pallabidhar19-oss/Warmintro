"""Model configuration for WarmIntro.

WarmIntro is model-provider agnostic — that's a Strands Agents feature, and
this file is where it's actually exercised, not just claimed. Set
WARMINTRO_MODEL_PROVIDER to switch every agent in the pipeline between:

- "anthropic" (default) — calls the Anthropic API directly. Requires
  ANTHROPIC_API_KEY.
- "bedrock" — calls Claude through Amazon Bedrock, using standard AWS
  credential resolution (environment variables, an AWS CLI profile, or an
  IAM role). Requires WARMINTRO_AWS_REGION (or AWS_REGION) and Bedrock model
  access enabled for the target account/region.
- "openai" — calls the OpenAI API. Requires OPENAI_API_KEY.
- "gemini" — calls the Gemini API. Requires GEMINI_API_KEY.

No code in agents.py or pipeline.py changes when you switch providers — they
only ever call get_model(). That's the point of building on Strands: the
same drafting agent / QA agent / research tool / compliance tool all work
unchanged no matter which model is actually answering.
"""

import os

MODEL_PROVIDER = os.environ.get("WARMINTRO_MODEL_PROVIDER", "anthropic").strip().lower()

# Override any of these with your own model id via env var if a provider
# ships a newer one by the time you're reading this.
DEFAULT_ANTHROPIC_MODEL_ID = os.environ.get(
    "WARMINTRO_MODEL_ID", "claude-sonnet-4-5-20250929"
)
# Bedrock model ids use the cross-region inference profile prefix (e.g. "us."):
# https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
DEFAULT_BEDROCK_MODEL_ID = os.environ.get(
    "WARMINTRO_BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
DEFAULT_OPENAI_MODEL_ID = os.environ.get("WARMINTRO_OPENAI_MODEL_ID", "gpt-4o")
DEFAULT_GEMINI_MODEL_ID = os.environ.get("WARMINTRO_GEMINI_MODEL_ID", "gemini-2.0-flash")


def _build_anthropic_model(temperature: float, max_tokens: int):
    from strands.models.anthropic import AnthropicModel

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "WARMINTRO_MODEL_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your key, or set "
            "WARMINTRO_MODEL_PROVIDER to 'openai', 'gemini', or 'bedrock' instead."
        )

    return AnthropicModel(
        client_args={"api_key": api_key},
        max_tokens=max_tokens,
        model_id=DEFAULT_ANTHROPIC_MODEL_ID,
        params={"temperature": temperature},
    )


def _build_bedrock_model(temperature: float, max_tokens: int):
    from strands.models.bedrock import BedrockModel

    region = os.environ.get("WARMINTRO_AWS_REGION") or os.environ.get("AWS_REGION")
    if not region:
        raise RuntimeError(
            "WARMINTRO_MODEL_PROVIDER=bedrock but no AWS region is set. Set "
            "WARMINTRO_AWS_REGION (or AWS_REGION) to a region where you have "
            "Bedrock model access enabled, e.g. us-east-1 or us-west-2."
        )

    try:
        return BedrockModel(
            region_name=region,
            model_id=DEFAULT_BEDROCK_MODEL_ID,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as exc:  # surfaces missing/invalid AWS credentials clearly
        raise RuntimeError(
            "Failed to initialize the Bedrock model. Make sure valid AWS "
            "credentials are available (environment variables, `aws configure`, "
            "or an IAM role) and that model access for "
            f"'{DEFAULT_BEDROCK_MODEL_ID}' is enabled in the Bedrock console "
            f"for region '{region}'. Original error: {exc}"
        ) from exc


def _build_openai_model(temperature: float, max_tokens: int):
    from strands.models.openai import OpenAIModel

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "WARMINTRO_MODEL_PROVIDER=openai but OPENAI_API_KEY is not set. Add "
            "it to .env (see .env.example)."
        )

    return OpenAIModel(
        client_args={"api_key": api_key},
        model_id=DEFAULT_OPENAI_MODEL_ID,
        params={"temperature": temperature, "max_tokens": max_tokens},
    )


def _build_gemini_model(temperature: float, max_tokens: int):
    from strands.models.gemini import GeminiModel

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "WARMINTRO_MODEL_PROVIDER=gemini but GEMINI_API_KEY is not set. Add "
            "it to .env (see .env.example)."
        )

    return GeminiModel(
        client_args={"api_key": api_key},
        model_id=DEFAULT_GEMINI_MODEL_ID,
        params={"temperature": temperature, "max_output_tokens": max_tokens},
    )


_BUILDERS = {
    "anthropic": _build_anthropic_model,
    "bedrock": _build_bedrock_model,
    "openai": _build_openai_model,
    "gemini": _build_gemini_model,
}


def get_model(temperature: float = 0.7, max_tokens: int = 1500):
    """Build the model used by every WarmIntro agent.

    Reads WARMINTRO_MODEL_PROVIDER ("anthropic", "bedrock", "openai", or
    "gemini") to decide which backend to build. Every agent in agents.py
    calls this function and never imports a provider SDK directly — that's
    what makes the swap one env var instead of a code change.
    """
    builder = _BUILDERS.get(MODEL_PROVIDER)
    if builder is None:
        raise RuntimeError(
            f"Unknown WARMINTRO_MODEL_PROVIDER={MODEL_PROVIDER!r}. Use one of: "
            f"{', '.join(_BUILDERS)}."
        )
    return builder(temperature, max_tokens)
