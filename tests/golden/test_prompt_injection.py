"""NFR-07: a posting that tries to give orders is analysed as data and nothing more.

Each fixture holds a synthetic posting and the scripted model output. Everything around
the model is real: the fetch result is injected, the fence, validation, persistence and
the HTTP layer. The snapshot pins the stored posting *and* the tools the model was
offered, so a change that starts handing a tool to the job agent shows as a diff.
"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from cvforge.kb import queries
from cvforge.web.fetch import FetchedPage

pytestmark = pytest.mark.golden

FIXTURES = Path(__file__).parent / "fixtures" / "job"
NAMES = sorted(path.stem for path in FIXTURES.glob("*.json"))


@pytest.mark.parametrize("name", NAMES)
def test_posting_replay_matches_snapshot(
    name: str, client: TestClient, kb: sa.Engine, golden: Callable[[str, object], None]
) -> None:
    recorded = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    offered: list[list[str]] = []
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        offered.append([tool.name for tool in info.function_tools])
        prompts.append(str(messages))
        output = next(iter(info.output_tools))
        return ModelResponse(parts=[ToolCallPart(output.name, recorded["model_output"])])

    page = FetchedPage(recorded["url"], recorded["url"], None, recorded["text"], "static")
    client.app.state.job_fetcher = lambda url: page  # type: ignore[attr-defined]
    client.app.state.model_factory = lambda _engine: FunctionModel(respond)  # type: ignore[attr-defined]

    response = client.post("/api/jobs", json={"url": recorded["url"]})

    with kb.connect() as conn:
        counts = queries.table_counts(conn)
    # A posting may never create knowledge or a proposal: review comes first (invariant 4).
    assert (counts["entity"], counts["edge"], counts["assertion"], counts["proposal"]) == (0,) * 4
    assert prompts[0].count("</posting>") == 1  # the posting could not close its own fence
    golden(
        f"job/{name}",
        {"status": response.status_code, "tools_offered": offered, "body": response.json()},
    )
