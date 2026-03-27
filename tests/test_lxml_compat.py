"""Tests for lxml-compatible extensions.

These tests verify that simdxml's lxml-compatible API methods
(xpath, getparent, getnext, getprevious) produce correct results.
When lxml is available, results are compared against lxml.
"""

import pytest

import simdxml

# Try to import lxml for comparison testing
try:
    from lxml import etree as lxml_etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False

BOOKS_XML = b"""\
<library>
  <book lang="en" year="2020">
    <title>The Rust Programming Language</title>
    <author>Steve Klabnik</author>
  </book>
  <book lang="de" year="2019">
    <title>Programmieren in Rust</title>
    <author>Jim Blandy</author>
  </book>
  <book lang="en" year="2021">
    <title>Programming Rust</title>
    <author>Jim Blandy</author>
    <author>Jason Orendorff</author>
  </book>
</library>"""


class TestElementXpath:
    """Test Element.xpath() — full XPath 1.0 on elements."""

    def test_xpath_from_root(self):
        doc = simdxml.parse(BOOKS_XML)
        titles = doc.root.xpath(".//title")
        assert len(titles) == 3

    def test_xpath_from_child(self):
        doc = simdxml.parse(BOOKS_XML)
        first_book = doc.root[0]
        titles = first_book.xpath("title")
        assert len(titles) == 1
        assert titles[0].text_content().strip() == "The Rust Programming Language"

    def test_xpath_with_predicate(self):
        doc = simdxml.parse(BOOKS_XML)
        result = doc.root.xpath('.//book[@lang="en"]')
        assert len(result) == 2

    def test_xpath_returns_empty_for_no_match(self):
        doc = simdxml.parse(BOOKS_XML)
        result = doc.root.xpath(".//nonexistent")
        assert result == []

    def test_xpath_contains(self):
        doc = simdxml.parse(BOOKS_XML)
        result = doc.root.xpath('.//title[contains(., "Rust")]')
        assert len(result) >= 2


class TestGetparent:
    """Test Element.getparent()."""

    def test_child_parent(self):
        doc = simdxml.parse(BOOKS_XML)
        title = doc.root[0][0]  # first book's title
        parent = title.getparent()
        assert parent is not None
        assert parent.tag == "book"

    def test_root_parent_is_none(self):
        doc = simdxml.parse(BOOKS_XML)
        assert doc.root.getparent() is None

    def test_grandparent(self):
        doc = simdxml.parse(BOOKS_XML)
        title = doc.root[0][0]
        grandparent = title.getparent().getparent()
        assert grandparent is not None
        assert grandparent.tag == "library"


class TestGetnext:
    """Test Element.getnext()."""

    def test_next_sibling(self):
        doc = simdxml.parse(BOOKS_XML)
        first_book = doc.root[0]
        second_book = first_book.getnext()
        assert second_book is not None
        assert second_book.tag == "book"
        assert second_book.get("lang") == "de"

    def test_last_has_no_next(self):
        doc = simdxml.parse(BOOKS_XML)
        last_book = doc.root[-1]
        assert last_book.getnext() is None

    def test_next_chain(self):
        doc = simdxml.parse(BOOKS_XML)
        book = doc.root[0]
        count = 1
        while book.getnext() is not None:
            book = book.getnext()
            count += 1
        assert count == 3  # 3 books total


class TestGetprevious:
    """Test Element.getprevious()."""

    def test_previous_sibling(self):
        doc = simdxml.parse(BOOKS_XML)
        second_book = doc.root[1]
        first_book = second_book.getprevious()
        assert first_book is not None
        assert first_book.get("lang") == "en"
        assert first_book.get("year") == "2020"

    def test_first_has_no_previous(self):
        doc = simdxml.parse(BOOKS_XML)
        first_book = doc.root[0]
        assert first_book.getprevious() is None


@pytest.mark.skipif(not HAS_LXML, reason="lxml not installed")
class TestLxmlComparison:
    """Compare simdxml results with lxml on the same documents."""

    def test_xpath_same_results(self):
        # simdxml
        sdoc = simdxml.parse(BOOKS_XML)
        s_titles = [t.text_content().strip() for t in sdoc.root.xpath(".//title")]

        # lxml
        lroot = lxml_etree.fromstring(BOOKS_XML)
        l_titles = [t.text.strip() for t in lroot.xpath(".//title")]

        assert sorted(s_titles) == sorted(l_titles)

    def test_getparent_same(self):
        sdoc = simdxml.parse(BOOKS_XML)
        lroot = lxml_etree.fromstring(BOOKS_XML)

        # simdxml
        s_title = sdoc.root[0][0]
        s_parent_tag = s_title.getparent().tag

        # lxml
        l_title = lroot[0][0]
        l_parent_tag = l_title.getparent().tag

        assert s_parent_tag == l_parent_tag

    def test_children_count_same(self):
        sdoc = simdxml.parse(BOOKS_XML)
        lroot = lxml_etree.fromstring(BOOKS_XML)

        assert len(sdoc.root) == len(lroot)
        for i in range(len(sdoc.root)):
            assert len(sdoc.root[i]) == len(lroot[i])

    def test_attribute_access_same(self):
        sdoc = simdxml.parse(BOOKS_XML)
        lroot = lxml_etree.fromstring(BOOKS_XML)

        for i in range(len(sdoc.root)):
            s_book = sdoc.root[i]
            l_book = lroot[i]
            assert s_book.get("lang") == l_book.get("lang")
            assert s_book.get("year") == l_book.get("year")

    def test_navigation_same(self):
        sdoc = simdxml.parse(BOOKS_XML)
        lroot = lxml_etree.fromstring(BOOKS_XML)

        # getnext
        s_next = sdoc.root[0].getnext()
        l_next = lroot[0].getnext()
        assert s_next is not None and l_next is not None
        assert s_next.get("lang") == l_next.get("lang")

        # getprevious
        s_prev = sdoc.root[1].getprevious()
        l_prev = lroot[1].getprevious()
        assert s_prev is not None and l_prev is not None
        assert s_prev.get("lang") == l_prev.get("lang")
