"""Model configuration for WarmIntro.

WarmIntro is model-provider agnostic — that's a Strands Agents feature, and
this file is where it's actually exercised, not just claimed. Set
WARMINTRO_MODEL_PROVIDER to switch every agent in the pipeline between:

- "anthropic" (default) — calls the Anthropic API directly. Fastest path for
  local development and demoing without an AWS account. Requires
  ANTHROPIC_API_KEY.
- "bedrock" — calls the same Claude models through Amazon Bedrock, using
  standard AWS credential resolution (environment variables, an AWS CLI
  profile, or an IAM role when running on AWS infrastructure like EC2, ECS,
  or Lambda). Requires WARMINTRO_AWS_REGION (or AWS_REGION) and Bedrock model
  access enabled for the target account/region.

No code in agents.py or pipeline.py changes when you switch providers — they
only ever call get_model(). That's the point of building on Strands.
"""

import os

MODEL_PROVIDER = os.environ.get("WARMINTRO_MODEL_PROVIDER", "anthropic").strip().lower()

# Override with your own model id via env var if Anthropic/AWS ship a newer
# one by the time you're reading this.
# Anthropic model ids: https://docs.claude.com
DEFAULT_ANTHROPIC_MODEL_ID = os.environ.get(
    "WARMINTRO_MODEL_ID", "claude-sonnet-4-5-20250929"
)
# Bedrock model ids (these use the cross-region inference profile prefix,
# e.g. "us."): https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
DEFAULT_BEDROCK_MODEL_ID = os.environ.get(
    "WARMINTRO_BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)


def _build_anthropic_model(temperature: float, max_tokens: int):
    from strands.models.anthropic import AnthropicModel

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "WARMINTRO_MODEL_PROVIDER=anthropic (the default) but ANTHROPIC_API_KEY "
            "is not set. Copy .env.example to .env, add your key, and "
            "`export $(cat .env | xargs)` (or use python-dotenv) before running "
            "WarmIntro. Or set WARMINTRO_MODEL_PROVIDER=bedrock to use AWS "
            "credentials instead."
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


def get_model(temperature: float = 0.7, max_tokens: int = 1500):
    """Build the model used by every WarmIntro agent.

    Reads WARMINTRO_MODEL_PROVIDER ("anthropic" or "bedrock") to decide which
    backend to build. Every agent in agents.py calls this function and never
    imports a provider SDK directly — that's what makes the swap one env var
    instead of a code change.
    """
    if MODEL_PROVIDER == "bedrock":
        return _build_bedrock_model(temperature, max_tokens)
    if MODEL_PROVIDER == "anthropic":
        return _build_anthropic_model(temperature, max_tokens)

    raise RuntimeError(
        f"Unknown WARMINTRO_MODEL_PROVIDER={MODEL_PROVIDER!r}. Use 'anthropic' or "
        "'bedrock'."
    )
