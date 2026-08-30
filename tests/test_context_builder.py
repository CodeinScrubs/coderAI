import pytest
from context_builder import (
    clip_for_context,
    estimate_tokens_for_messages,
    estimate_tokens_for_text,
    fast_tokens_for_messages,
    get_model_context_window,
)


def test_estimate_tokens_for_text():
    text = "Hello world! This is a test for token estimation."
    tokens = estimate_tokens_for_text(text)
    assert tokens > 0
    assert isinstance(tokens, int)
    assert estimate_tokens_for_text("") == 0


def test_estimate_tokens_for_messages():
    messages = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a programming language."},
    ]
    tokens = estimate_tokens_for_messages(messages, model="gpt-4o")
    assert tokens > 0
    assert isinstance(tokens, int)


def test_clip_for_context():
    short = "Hello world"
    assert clip_for_context(short, 100) == short
    long_text = "A" * 1000
    clipped = clip_for_context(long_text, 100)
    assert len(clipped) <= 250
    assert "omitted" in clipped


def test_get_model_context_window():
    window, source = get_model_context_window("gemma4:12b")
    assert window >= 128_000
    window_gpt, _ = get_model_context_window("gpt-4o")
    assert window_gpt == 128_000
