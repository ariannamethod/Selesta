from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import claude


def test_claude_model_constant():
    """Verify that Claude model is set to claude-sonnet-4-20250514."""
    assert claude.CLAUDE_MODEL == "claude-sonnet-4-20250514"


def test_no_fallback_model():
    """Verify that no fallback model constant exists."""
    assert not hasattr(claude, "CLAUDE_MODEL_FALLBACK")


def test_api_key_configuration():
    """Verify that API key configuration is present."""
    # Just check the constant exists, don't check the actual value
    assert hasattr(claude, "ANTHROPIC_API_KEY")
