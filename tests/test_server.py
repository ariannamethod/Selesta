from pathlib import Path
import sys
import inspect

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import webhook
from typing import Dict, Any


def test_webhook_return_type():
    """Verify that webhook function returns Dict[str, Any] instead of MessageResponse."""
    sig = inspect.signature(webhook)
    return_annotation = sig.return_annotation
    
    # Check that the return annotation is Dict[str, Any]
    assert return_annotation == Dict[str, Any], f"Expected Dict[str, Any] but got {return_annotation}"
