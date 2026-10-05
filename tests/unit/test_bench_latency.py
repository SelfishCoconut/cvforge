"""The benchmark's own logic: percentile maths, the local-only refusal, timing (NFR-10)."""

import pytest
from scripts.bench.latency import NotLocalError, measure, percentile, require_local

from cvforge.kb.vocab import Provider
from cvforge.llm.settings_store import ProviderSettings


def test_percentile_is_nearest_rank() -> None:
    values = list(range(1, 21))

    assert percentile(values, 50) == 10
    assert percentile(values, 95) == 19
    assert percentile(values, 100) == 20
    assert percentile([7.0], 95) == 7.0


@pytest.mark.parametrize(("values", "q"), [([], 50), ([1.0], 0), ([1.0], 101)])
def test_percentile_rejects_bad_input(values: list[float], q: float) -> None:
    with pytest.raises(ValueError):
        percentile(values, q)


def test_local_ollama_is_accepted() -> None:
    require_local(ProviderSettings())
    require_local(ProviderSettings(base_url="http://localhost:11434"))


@pytest.mark.parametrize(
    "settings",
    [
        ProviderSettings(provider=Provider.ANTHROPIC, allow_external=True, api_key_env="K"),
        ProviderSettings(base_url="http://example.com:11434"),
        ProviderSettings(base_url=None),
    ],
)
def test_anything_external_is_refused(settings: ProviderSettings) -> None:
    with pytest.raises(NotLocalError):
        require_local(settings)


def test_measure_times_every_message_every_run() -> None:
    sent: list[str] = []

    durations = measure(sent.append, ["a", "b"], runs=3)

    assert sent == ["a", "b"] * 3 and len(durations) == 6 and min(durations) >= 0
