from types import SimpleNamespace
from unittest.mock import MagicMock

from pxreview.models import ReviewDraft
from pxreview.provider import OpenAIReviewProvider


def test_openai_provider_uses_responses_structured_output():
    provider = OpenAIReviewProvider(
        model="gpt-5.6-terra",
        api_key="test",
        reasoning_effort="medium",
    )
    parsed = ReviewDraft(summary="No actionable PX finding in this change.")
    provider._client = MagicMock()
    provider._client.responses.parse.return_value = SimpleNamespace(
        output_parsed=parsed
    )

    result = provider.review("system", "user")

    assert result is parsed
    _, kwargs = provider._client.responses.parse.call_args
    assert kwargs["model"] == "gpt-5.6-terra"
    assert kwargs["text_format"] is ReviewDraft
    assert kwargs["reasoning"] == {"effort": "medium"}
    assert kwargs["store"] is False

