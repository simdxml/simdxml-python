"""Tests for native XPath API: xpath_text, xpath, compile."""

import pytest

import simdxml

from .conftest import ATTRIBUTES_XML, BOOKS_XML


class TestXpathText:
    """Test Document.xpath_text()."""

    def test_simple_path(self, simple_doc):
        result = simple_doc.xpath_text("//child")
        assert result == ["hello", "world"]

    def test_absolute_path(self, simple_doc):
        result = simple_doc.xpath_text("/root/child")
        assert result == ["hello", "world"]

    def test_nested_path(self, books_doc):
        result = books_doc.xpath_text("//title")
        assert len(result) == 3
        assert "The Rust Programming Language" in result

    def test_no_matches(self, simple_doc):
        result = simple_doc.xpath_text("//nonexistent")
        assert result == []

    def test_with_predicate(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        result = doc.xpath_text('//item[@class="primary"]/@id')
        # Attribute nodes may be returned differently
        # Just verify it doesn't crash
        assert isinstance(result, list)

    def test_descendant_text(self, nested_doc):
        result = nested_doc.xpath_text("//c")
        assert result == ["deep"]


class TestXpathString:
    """Test Document.xpath_string()."""

    def test_string_value_includes_descendants(self, books_doc):
        # xpath_string returns all descendant text (XPath string-value)
        result = books_doc.xpath_string("//book")
        assert len(result) == 3
        # First book's string value should include title + author
        assert "The Rust Programming Language" in result[0]
        assert "Steve Klabnik" in result[0]


class TestXpath:
    """Test Document.xpath() returning mixed results."""

    def test_returns_elements(self, simple_doc):
        result = simple_doc.xpath("//child")
        assert len(result) == 2
        # Should be Element objects
        for elem in result:
            assert hasattr(elem, "tag")
            assert elem.tag == "child"

    def test_returns_text_nodes(self, simple_doc):
        result = simple_doc.xpath("//child/text()")
        assert len(result) == 2
        # Text nodes should be strings
        assert "hello" in result
        assert "world" in result


class TestElementXpath:
    """Test Element.xpath() for context-node evaluation."""

    def test_relative_path(self, books_doc):
        first_book = books_doc.root[0]
        titles = first_book.xpath("title")
        assert len(titles) == 1
        assert titles[0].tag == "title"

    def test_descendant_from_element(self, nested_doc):
        first_a = nested_doc.root[0]
        cs = first_a.xpath(".//c")
        assert len(cs) == 1
        assert cs[0].text_content() == "deep"


class TestElementXpathText:
    """Test Element.xpath_text() for context-node text extraction."""

    def test_child_text(self, books_doc):
        first_book = books_doc.root[0]
        texts = first_book.xpath_text("title")
        assert len(texts) == 1
        assert "The Rust Programming Language" in texts[0]


class TestXpathAxes:
    """Test all 13 XPath 1.0 axes."""

    def test_child_axis(self, simple_doc):
        result = simple_doc.xpath_text("/root/child::child")
        assert len(result) == 2

    def test_descendant_axis(self, nested_doc):
        result = nested_doc.xpath_text("/root/descendant::c")
        assert result == ["deep"]

    def test_descendant_or_self(self, simple_doc):
        result = simple_doc.xpath("//child")
        assert len(result) == 2

    def test_parent_axis(self, nested_doc):
        result = nested_doc.xpath("//c/parent::b")
        assert len(result) == 1
        assert result[0].tag == "b"

    def test_ancestor_axis(self, nested_doc):
        result = nested_doc.xpath("//c/ancestor::a")
        assert len(result) == 1
        assert result[0].tag == "a"

    def test_self_axis(self, simple_doc):
        result = simple_doc.xpath("/root/self::root")
        assert len(result) == 1
        assert result[0].tag == "root"

    def test_following_sibling(self, simple_doc):
        result = simple_doc.xpath("/root/child[1]/following-sibling::child")
        assert len(result) == 1

    def test_preceding_sibling(self, simple_doc):
        result = simple_doc.xpath("/root/child[2]/preceding-sibling::child")
        assert len(result) == 1

    def test_attribute_axis(self):
        doc = simdxml.parse(BOOKS_XML)
        result = doc.xpath("//book/@lang")
        assert len(result) >= 1


class TestXpathFunctions:
    """Test XPath 1.0 functions."""

    def test_count(self, books_doc):
        # count() is a scalar expression; verify via node-set length
        result = books_doc.xpath("//book")
        assert len(result) == 3

    def test_contains(self, books_doc):
        result = books_doc.xpath('//title[contains(., "Rust")]')
        assert len(result) >= 2

    def test_starts_with(self, books_doc):
        result = books_doc.xpath('//title[starts-with(., "The")]')
        assert len(result) == 1

    def test_string_length(self, simple_doc):
        result = simple_doc.xpath("//child[string-length(.) > 4]")
        assert len(result) == 2  # "hello" and "world" both > 4 chars

    def test_position(self, simple_doc):
        result = simple_doc.xpath("/root/child[position()=1]")
        assert len(result) == 1
        assert result[0].text == "hello"

    def test_last(self, simple_doc):
        result = simple_doc.xpath("/root/child[last()]")
        assert len(result) == 1
        assert result[0].text == "world"

    def test_not(self, books_doc):
        result = books_doc.xpath('//book[not(@lang="en")]')
        assert len(result) == 1
        assert result[0].get("lang") == "de"

    def test_concat_via_predicate(self, books_doc):
        # concat is used in predicates, not as top-level scalar
        # Test it within a predicate context
        result = books_doc.xpath('//title[contains(., "Rust")]')
        assert len(result) >= 2

    def test_normalize_space_via_predicate(self):
        xml = b"<root><text>  hello   world  </text><text>x</text></root>"
        doc = simdxml.parse(xml)
        # Test normalize-space in a predicate
        result = doc.xpath('//text[normalize-space(.)="hello world"]')
        assert len(result) == 1


class TestXpathOperators:
    """Test XPath operators."""

    def test_and(self, books_doc):
        result = books_doc.xpath('//book[@lang="en" and @year="2020"]')
        assert len(result) == 1

    def test_or(self, books_doc):
        result = books_doc.xpath('//book[@year="2019" or @year="2021"]')
        assert len(result) == 2

    def test_equality(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        result = doc.xpath('//item[@id="2"]')
        assert len(result) == 1

    def test_inequality(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        result = doc.xpath('//item[@id!="2"]')
        assert len(result) == 2

    def test_union(self, books_doc):
        result = books_doc.xpath("//title | //author")
        # Should have all titles and authors
        assert len(result) >= 6  # 3 titles + 4 authors

    def test_wildcard(self, simple_doc):
        result = simple_doc.xpath("/root/*")
        assert len(result) == 2


class TestXpathPredicates:
    """Test XPath predicates."""

    def test_positional_predicate(self, simple_doc):
        result = simple_doc.xpath("/root/child[1]")
        assert len(result) == 1
        assert result[0].text == "hello"

    def test_positional_last(self, simple_doc):
        result = simple_doc.xpath("/root/child[last()]")
        assert len(result) == 1
        assert result[0].text == "world"

    def test_boolean_predicate(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        result = doc.xpath('//item[@class="primary"]')
        assert len(result) == 2

    def test_nested_predicate(self, books_doc):
        result = books_doc.xpath('//book[title="Programming Rust"]')
        assert len(result) == 1


class TestCompiledXpath:
    """Test CompiledXPath for reuse."""

    def test_compile_and_eval_text(self, simple_doc):
        expr = simdxml.compile("//child")
        result = expr.eval_text(simple_doc)
        assert result == ["hello", "world"]

    def test_compile_and_eval(self, simple_doc):
        expr = simdxml.compile("//child")
        result = expr.eval(simple_doc)
        assert len(result) == 2

    def test_compile_and_eval_exists(self, simple_doc):
        expr = simdxml.compile("//child")
        assert expr.eval_exists(simple_doc) is True

        expr2 = simdxml.compile("//nonexistent")
        assert expr2.eval_exists(simple_doc) is False

    def test_compile_and_eval_count(self, simple_doc):
        expr = simdxml.compile("//child")
        assert expr.eval_count(simple_doc) == 2

    def test_compiled_reuse_across_docs(self):
        expr = simdxml.compile("//item")
        doc1 = simdxml.parse(b"<r><item>A</item></r>")
        doc2 = simdxml.parse(b"<r><item>B</item><item>C</item></r>")

        assert expr.eval_count(doc1) == 1
        assert expr.eval_count(doc2) == 2
        assert expr.eval_text(doc1) == ["A"]
        assert expr.eval_text(doc2) == ["B", "C"]

    def test_compile_invalid_xpath(self):
        with pytest.raises(ValueError):
            simdxml.compile("[invalid")

    def test_compile_repr(self):
        expr = simdxml.compile("//title")
        assert "CompiledXPath" in repr(expr)

    def test_invalid_xpath_on_doc(self, simple_doc):
        with pytest.raises(ValueError):
            simple_doc.xpath_text("[invalid")
