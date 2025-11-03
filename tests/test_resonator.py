from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import resonator


@pytest.fixture(autouse=True)
def reset_encoder_state():
    """Сбрасывает состояние энкодера между тестами."""

    original_encoder = resonator._ENCODER
    original_attempted = resonator._ENCODER_ATTEMPTED
    original_warning = resonator._ENCODER_ERROR_LOGGED
    try:
        resonator._ENCODER = None
        resonator._ENCODER_ATTEMPTED = False
        resonator._ENCODER_ERROR_LOGGED = False
        yield
    finally:
        resonator._ENCODER = original_encoder
        resonator._ENCODER_ATTEMPTED = original_attempted
        resonator._ENCODER_ERROR_LOGGED = original_warning


def test_build_system_prompt_without_tiktoken(monkeypatch, capsys):
    """Проверяем, что при отсутствии tiktoken промпт всё равно строится."""

    monkeypatch.setattr(resonator, "tiktoken", None, raising=False)

    prompt = resonator.build_system_prompt(
        chat_id="test-chat",
        is_group=False,
        message_context="Привет, Селеста",
    )

    out, _ = capsys.readouterr()
    assert "tiktoken is not available" in out
    assert "You are Selesta" in prompt


def test_build_system_prompt_encoder_failure(monkeypatch, capsys):
    """Даже при ошибке загрузки энкодера промпт создаётся."""

    if resonator.tiktoken is None:
        pytest.skip("tiktoken is not available in this environment")

    def raise_error(*_, **__):
        raise RuntimeError("network down")

    monkeypatch.setattr(resonator.tiktoken, "get_encoding", raise_error)

    prompt = resonator.build_system_prompt(
        chat_id="test-chat",
        is_group=True,
        message_context="Hello Selesta",
    )

    out, _ = capsys.readouterr()
    assert "failed to load tiktoken encoding" in out
    assert "You are Selesta" in prompt
