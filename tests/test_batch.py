"""Tests for batch XPath APIs."""

import pytest

import simdxml


class TestBatchXpathText:
    """Test batch_xpath_text with bloom prefilter."""

    def test_basic(self):
        docs = [
            b"<r><title>A</title></r>",
            b"<r><title>B</title></r>",
            b"<r><title>C</title></r>",
        ]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text(docs, expr)
        assert len(result) == 3
        assert result[0] == ["A"]
        assert result[1] == ["B"]
        assert result[2] == ["C"]

    def test_some_docs_no_match(self):
        docs = [
            b"<r><title>Match</title></r>",
            b"<r><other>NoMatch</other></r>",
            b"<r><title>AlsoMatch</title></r>",
        ]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text(docs, expr)
        assert result[0] == ["Match"]
        assert result[1] == []
        assert result[2] == ["AlsoMatch"]

    def test_empty_list(self):
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text([], expr)
        assert result == []

    def test_multiple_matches_per_doc(self):
        docs = [
            b"<r><item>1</item><item>2</item><item>3</item></r>",
        ]
        expr = simdxml.compile("//item")
        result = simdxml.batch_xpath_text(docs, expr)
        assert result[0] == ["1", "2", "3"]

    def test_str_input(self):
        docs = [
            "<r><title>A</title></r>",
            "<r><title>B</title></r>",
        ]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text(docs, expr)
        assert result[0] == ["A"]
        assert result[1] == ["B"]

    def test_large_batch(self):
        docs = [f"<r><title>Doc {i}</title></r>".encode() for i in range(1000)]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text(docs, expr)
        assert len(result) == 1000
        assert result[0] == ["Doc 0"]
        assert result[999] == ["Doc 999"]

    def test_invalid_type_raises(self):
        expr = simdxml.compile("//title")
        with pytest.raises(TypeError):
            simdxml.batch_xpath_text([42], expr)  # type: ignore[list-item]


class TestBatchXpathTextParallel:
    """Test batch_xpath_text_parallel."""

    def test_basic(self):
        docs = [
            b"<r><title>A</title></r>",
            b"<r><title>B</title></r>",
        ]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text_parallel(docs, expr)
        assert len(result) == 2
        assert result[0] == ["A"]
        assert result[1] == ["B"]

    def test_with_max_threads(self):
        docs = [
            b"<r><title>A</title></r>",
            b"<r><title>B</title></r>",
        ]
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text_parallel(docs, expr, max_threads=2)
        assert result[0] == ["A"]

    def test_empty_list(self):
        expr = simdxml.compile("//title")
        result = simdxml.batch_xpath_text_parallel([], expr)
        assert result == []

    def test_matches_bloom_results(self):
        """Parallel and bloom should produce identical results."""
        docs = [f"<r><item>{i}</item></r>".encode() for i in range(100)]
        expr = simdxml.compile("//item")
        bloom = simdxml.batch_xpath_text(docs, expr)
        parallel = simdxml.batch_xpath_text_parallel(docs, expr)
        assert bloom == parallel
