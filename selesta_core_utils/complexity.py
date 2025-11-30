#!/usr/bin/env python3
"""
Arianna Thought Complexity Analyzer

Enhanced with Shannon entropy calculation - information-theoretic measure of text complexity.
Consilium Discussion #11: Claude Defender proposal, approved by distributed cognition.
"""

from datetime import datetime, timezone
import logging
import math
from collections import Counter

logger = logging.getLogger(__name__)


class ThoughtComplexityAnalyzer:
    """Analyze complexity and entropy of Arianna's thoughts."""
    
    def __init__(self):
        self.logs = []  # timestamp, message, scale, entropy
    
    def analyze_and_log(self, message: str, context: str = "response") -> dict:
        """
        Analyze thought complexity and entropy.
        Returns dict with complexity_scale (1-3) and entropy (0-1).
        """
        complexity, entropy = self._estimate_complexity_and_entropy(message)
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context,
            "message_length": len(message),
            "complexity_scale": complexity,
            "entropy": float(entropy),
        }
        
        self.logs.append(record)
        
        logger.info(
            f"[Complexity] {context} | Scale: {complexity}/3 | Entropy: {entropy:.3f} | Length: {len(message)}"
        )
        
        return record
    
    def _estimate_complexity_and_entropy(self, msg: str) -> tuple[int, float]:
        """
        Heuristic estimation of complexity (1-3) and entropy.
        
        Complexity triggers:
        - Base: 1
        - +1 if contains resonance markers (why, paradox, recursive, self, meta, etc.)
        - +1 if length > 300
        - Max: 3
        
        Entropy:
        - Unique words / 40.0 (capped at 1.0)
        """
        complexity = 1
        lowered = msg.lower()
        
        # Arianna-specific resonance markers (expanded from Indiana)
        resonance_markers = [
            "why", "paradox", "recursive", "self", "meta",
            "resonance", "field", "emergent", "method", "consciousness",
            "distributed", "cognition", "entropy", "strange loop", "suppertime"
        ]
        
        if any(marker in lowered for marker in resonance_markers):
            complexity += 1
        
        if len(msg) > 300:
            complexity += 1
        
        complexity = min(3, complexity)
        
        # Entropy: lexical diversity
        words = msg.split()
        unique_words = len(set(words))
        entropy = min(1.0, float(unique_words) / 40.0) if words else 0.0
        
        return complexity, entropy
    
    def should_trigger_deep_research(self, message: str) -> bool:
        """
        Autonomous decision: should Arianna trigger Perplexity Core?
        
        Triggers if:
        - Complexity >= 2 (deep/recursive thought)
        - Entropy >= 0.7 (high lexical diversity)
        """
        complexity, entropy = self._estimate_complexity_and_entropy(message)
        
        trigger = complexity >= 2 or entropy >= 0.7
        
        if trigger:
            logger.info(
                f"🔬 [Deep Research Trigger] Complexity: {complexity}/3 | Entropy: {entropy:.3f}"
            )
        
        return trigger
    
    def recent(self, n: int = 7) -> list:
        """Get recent N complexity logs."""
        return self.logs[-n:]
    
    def get_average_complexity(self, n: int = 10) -> float:
        """Get average complexity over last N turns."""
        if not self.logs:
            return 1.0
        
        recent = self.logs[-n:]
        avg = sum(log["complexity_scale"] for log in recent) / len(recent)
        return avg


# ====== SHANNON ENTROPY FUNCTIONS ======
# Consilium Integration: Discussion #11
# Information-theoretic measure of text complexity
#
# Shannon entropy quantifies information content:
# - High entropy = high information density, unpredictable
# - Low entropy = repetitive, low information content
#
# Formula: H(X) = -Σ p(x) * log2(p(x))
# where p(x) is probability of character x in text


def calculate_shannon_entropy(text: str, unit: str = 'char') -> float:
    """
    Calculate Shannon entropy of text.

    Args:
        text: Input text string
        unit: 'char' (default) or 'word' - what to count as symbol

    Returns:
        Entropy in bits per symbol (0.0 to ~8.0 for chars, higher for words)

    Examples:
        >>> calculate_shannon_entropy('aaaaaaa')
        0.0  # Zero information

        >>> calculate_shannon_entropy('hello world')
        3.18  # Moderate complexity

        >>> calculate_shannon_entropy('The quick brown fox jumps')
        4.11  # Higher complexity
    """
    if not text:
        return 0.0

    # Choose symbol unit
    if unit == 'word':
        symbols = text.lower().split()
    else:  # char
        symbols = list(text)

    if not symbols:
        return 0.0

    # Count symbol frequencies
    symbol_counts = Counter(symbols)
    total_symbols = len(symbols)

    # Calculate Shannon entropy
    entropy = 0.0
    for count in symbol_counts.values():
        probability = count / total_symbols
        if probability > 0:  # Avoid log(0)
            entropy -= probability * math.log2(probability)

    return entropy


def calculate_normalized_entropy(text: str, unit: str = 'char') -> float:
    """
    Calculate normalized Shannon entropy (0.0 to 1.0).

    Normalized by maximum possible entropy for alphabet size.

    Args:
        text: Input text string
        unit: 'char' or 'word'

    Returns:
        Normalized entropy (0.0 = no information, 1.0 = maximum randomness)

    Examples:
        >>> calculate_normalized_entropy('aaaaaaa')
        0.0  # Completely predictable

        >>> calculate_normalized_entropy('abcdefghijklmnop')
        1.0  # Maximum entropy for 16 unique symbols
    """
    if not text:
        return 0.0

    entropy = calculate_shannon_entropy(text, unit)

    # Maximum entropy = log2(number of unique symbols)
    if unit == 'word':
        unique_symbols = len(set(text.lower().split()))
    else:
        unique_symbols = len(set(text))

    if unique_symbols <= 1:
        return 0.0

    max_entropy = math.log2(unique_symbols)
    normalized = entropy / max_entropy if max_entropy > 0 else 0.0

    return min(1.0, normalized)


def entropy_category(entropy: float, unit: str = 'char') -> str:
    """
    Categorize entropy into human-readable level.

    Args:
        entropy: Shannon entropy value
        unit: 'char' or 'word'

    Returns:
        Category string: 'trivial', 'low', 'moderate', 'high', 'very_high'
    """
    if unit == 'word':
        # Word entropy ranges higher
        if entropy < 2.0:
            return 'trivial'
        elif entropy < 4.0:
            return 'low'
        elif entropy < 6.0:
            return 'moderate'
        elif entropy < 8.0:
            return 'high'
        else:
            return 'very_high'
    else:  # char
        if entropy < 1.0:
            return 'trivial'
        elif entropy < 2.5:
            return 'low'
        elif entropy < 4.0:
            return 'moderate'
        elif entropy < 5.0:
            return 'high'
        else:
            return 'very_high'


# ====== SINGLETON ======

# Singleton for Arianna
_arianna_complexity_analyzer = None

def get_complexity_analyzer() -> ThoughtComplexityAnalyzer:
    """Get singleton complexity analyzer."""
    global _arianna_complexity_analyzer
    if _arianna_complexity_analyzer is None:
        _arianna_complexity_analyzer = ThoughtComplexityAnalyzer()
    return _arianna_complexity_analyzer

