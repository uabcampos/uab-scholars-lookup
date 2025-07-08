import pytest
from uab_scholars.utils import slugify, clean_text

def test_slugify_basic():
    assert slugify("Andrea Cherrington") == "andrea-cherrington"


def test_slugify_punctuation():
    assert slugify("F. Stanford Massie, Jr.") == "f-stanford-massie-jr"


def test_clean_text_reduces_whitespace():
    text = "Hello   world\nthis  is  a\t test"
    assert clean_text(text) == "Hello world this is a test" 