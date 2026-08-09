"""Claude client wrapper.

Thin wrapper around the Anthropic SDK. Everything that talks to the LLM goes
through here so prompts, model choice, and retries live in one place.

Core principle: the AI *proposes* against citable methodology; a human confirms
every judgment call. This client never executes anything — it only produces text.

STATUS: stub — signatures only. Implement file-by-file with review.
"""

from app.config import settings
from app.models.schemas import Artifact, ProposedTest


class ClaudeClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        # self.client = anthropic.Anthropic(api_key=self.api_key)

    def propose_statistical_test(
        self, data_summary: str, protocol: str
    ) -> ProposedTest:
        """Given a data summary and research protocol, propose a test."""
        raise NotImplementedError

    def write_results_section(
        self, proposed_test: ProposedTest, artifacts: list[Artifact]
    ) -> str:
        """Write a Results section grounded strictly in the given artifacts.

        Returns Markdown. Nothing outside the artifacts may be asserted.
        """
        raise NotImplementedError
