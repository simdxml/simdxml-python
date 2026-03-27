"""Tests for read-only enforcement."""

import pytest

import simdxml


@pytest.fixture
def doc():
    return simdxml.parse(b"<root><child>text</child></root>")


class TestReadonlySetters:
    """Test that property setters raise TypeError."""

    def test_set_tag(self, doc):
        with pytest.raises(TypeError, match="read-only"):
            doc.root.tag = "new_tag"

    def test_set_text(self, doc):
        with pytest.raises(TypeError, match="read-only"):
            doc.root.text = "new text"

    def test_set_tail(self, doc):
        with pytest.raises(TypeError, match="read-only"):
            doc.root[0].tail = "new tail"


class TestReadonlyMutators:
    """Test that mutation methods raise TypeError."""

    def test_set_attribute(self, doc):
        with pytest.raises(TypeError, match="read-only"):
            doc.root.set("key", "value")

    def test_append(self, doc):
        child = doc.root[0]
        with pytest.raises(TypeError, match="read-only"):
            doc.root.append(child)

    def test_remove(self, doc):
        child = doc.root[0]
        with pytest.raises(TypeError, match="read-only"):
            doc.root.remove(child)

    def test_insert(self, doc):
        child = doc.root[0]
        with pytest.raises(TypeError, match="read-only"):
            doc.root.insert(0, child)

    def test_clear(self, doc):
        with pytest.raises(TypeError, match="read-only"):
            doc.root.clear()


class TestReadonlyErrorMessage:
    """Test that error messages are helpful."""

    def test_mentions_stdlib(self, doc):
        with pytest.raises(TypeError, match=r"xml\.etree\.ElementTree"):
            doc.root.text = "x"
