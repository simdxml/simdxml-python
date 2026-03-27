"""Tests for Element API: tag, text, tail, attrib, children."""

import pytest

import simdxml

from .conftest import (
    ATTRIBUTES_XML,
    EMPTY_ELEMENTS_XML,
    MIXED_CONTENT_XML,
)


class TestElementTag:
    """Test Element.tag property."""

    def test_root_tag(self, simple_doc):
        assert simple_doc.root.tag == "root"

    def test_child_tag(self, simple_doc):
        children = list(simple_doc.root)
        assert children[0].tag == "child"
        assert children[1].tag == "child"

    def test_nested_tag(self, books_doc):
        books = list(books_doc.root)
        assert books[0].tag == "book"
        titles = list(books[0])
        assert titles[0].tag == "title"


class TestElementText:
    """Test Element.text property."""

    def test_text_content(self, simple_doc):
        children = list(simple_doc.root)
        assert children[0].text == "hello"
        assert children[1].text == "world"

    def test_no_text(self):
        doc = simdxml.parse(b"<root><empty/></root>")
        children = list(doc.root)
        assert children[0].text is None

    def test_empty_text_element(self):
        doc = simdxml.parse(EMPTY_ELEMENTS_XML)
        root = doc.root
        children = list(root)
        # <empty></empty> has no text
        assert children[0].text is None
        # <also-empty/> has no text
        assert children[1].text is None
        # <has-text>content</has-text>
        assert children[2].text == "content"

    def test_mixed_content_text(self):
        """In mixed content, .text is text before first child element."""
        doc = simdxml.parse(MIXED_CONTENT_XML)
        root = doc.root
        assert root.text == "Hello "


class TestElementTail:
    """Test Element.tail property."""

    def test_root_has_no_tail(self, simple_doc):
        assert simple_doc.root.tail is None

    def test_tail_in_mixed_content(self):
        doc = simdxml.parse(MIXED_CONTENT_XML)
        root = doc.root
        children = list(root)
        # <b>bold</b> " and "
        bold = children[0]
        assert bold.tail is not None
        assert "and" in bold.tail


class TestElementAttrib:
    """Test Element attribute access."""

    def test_attrib_dict(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        items = list(doc.root)
        attrib = items[0].attrib
        assert attrib["id"] == "1"
        assert attrib["class"] == "primary"
        assert attrib["data-value"] == "100"

    def test_get_attribute(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        items = list(doc.root)
        assert items[0].get("id") == "1"
        assert items[0].get("missing") is None
        assert items[0].get("missing", "default") == "default"

    def test_keys(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        items = list(doc.root)
        keys = items[0].keys()
        assert "id" in keys
        assert "class" in keys
        assert "data-value" in keys

    def test_items(self):
        doc = simdxml.parse(ATTRIBUTES_XML)
        items_list = list(doc.root)
        pairs = items_list[0].items()
        pair_dict = dict(pairs)
        assert pair_dict["id"] == "1"
        assert pair_dict["class"] == "primary"

    def test_no_attributes(self, simple_doc):
        assert simple_doc.root.attrib == {}
        assert simple_doc.root.keys() == []
        assert simple_doc.root.items() == []

    def test_book_attributes(self, books_doc):
        books = list(books_doc.root)
        assert books[0].get("lang") == "en"
        assert books[0].get("year") == "2020"
        assert books[1].get("lang") == "de"


class TestElementChildren:
    """Test child element access."""

    def test_len(self, simple_doc):
        assert len(simple_doc.root) == 2

    def test_getitem_positive(self, simple_doc):
        first = simple_doc.root[0]
        assert first.tag == "child"
        assert first.text == "hello"

    def test_getitem_negative(self, simple_doc):
        last = simple_doc.root[-1]
        assert last.tag == "child"
        assert last.text == "world"

    def test_getitem_out_of_range(self, simple_doc):
        with pytest.raises(IndexError):
            _ = simple_doc.root[10]

    def test_getitem_negative_out_of_range(self, simple_doc):
        with pytest.raises(IndexError):
            _ = simple_doc.root[-10]

    def test_iter(self, simple_doc):
        children = list(simple_doc.root)
        assert len(children) == 2
        assert all(c.tag == "child" for c in children)

    def test_iter_nested(self, books_doc):
        books = list(books_doc.root)
        assert len(books) == 3
        # Third book has 3 children: title + 2 authors
        third = books[2]
        assert len(third) == 3

    def test_empty_element_has_no_children(self):
        doc = simdxml.parse(b"<root><empty/></root>")
        empty = doc.root[0]
        assert len(empty) == 0
        assert list(empty) == []


class TestElementIter:
    """Test Element.iter() for descendant traversal."""

    def test_iter_all_descendants(self, books_doc):
        all_elems = list(books_doc.root.iter())
        assert len(all_elems) > 3  # books + titles + authors

    def test_iter_by_tag(self, books_doc):
        titles = list(books_doc.root.iter("title"))
        assert len(titles) == 3
        assert all(t.tag == "title" for t in titles)

    def test_iter_by_tag_no_match(self, books_doc):
        nothing = list(books_doc.root.iter("nonexistent"))
        assert nothing == []

    def test_iter_nested(self, nested_doc):
        cs = list(nested_doc.root.iter("c"))
        assert len(cs) == 1
        assert cs[0].text == "deep"


class TestElementItertext:
    """Test Element.itertext() for text content."""

    def test_itertext_simple(self, simple_doc):
        texts = simple_doc.root.itertext()
        assert "hello" in texts
        assert "world" in texts

    def test_itertext_mixed(self):
        doc = simdxml.parse(MIXED_CONTENT_XML)
        texts = doc.root.itertext()
        # Should contain all text fragments
        all_text = "".join(texts)
        assert "Hello" in all_text
        assert "bold" in all_text
        assert "italic" in all_text


class TestElementTextContent:
    """Test Element.text_content() for concatenated text."""

    def test_text_content(self, simple_doc):
        # Root's text_content should contain both children's text
        content = simple_doc.root.text_content()
        assert "hello" in content
        assert "world" in content

    def test_text_content_nested(self, nested_doc):
        root = nested_doc.root
        content = root.text_content()
        assert "deep" in content
        assert "shallow" in content


class TestElementNavigation:
    """Test getparent, getnext, getprevious."""

    def test_getparent(self, simple_doc):
        child = simple_doc.root[0]
        parent = child.getparent()
        assert parent is not None
        assert parent.tag == "root"

    def test_getparent_root_is_none(self, simple_doc):
        assert simple_doc.root.getparent() is None

    def test_getnext(self, simple_doc):
        first = simple_doc.root[0]
        second = first.getnext()
        assert second is not None
        assert second.text == "world"

    def test_getnext_last_is_none(self, simple_doc):
        last = simple_doc.root[-1]
        assert last.getnext() is None

    def test_getprevious(self, simple_doc):
        second = simple_doc.root[1]
        first = second.getprevious()
        assert first is not None
        assert first.text == "hello"

    def test_getprevious_first_is_none(self, simple_doc):
        first = simple_doc.root[0]
        assert first.getprevious() is None

    def test_navigation_chain(self, books_doc):
        """Navigate: root -> first book -> next book -> parent -> root."""
        first_book = books_doc.root[0]
        second_book = first_book.getnext()
        assert second_book is not None
        parent = second_book.getparent()
        assert parent is not None
        assert parent.tag == "library"


class TestElementDunder:
    """Test dunder methods."""

    def test_repr(self, simple_doc):
        r = repr(simple_doc.root)
        assert "Element" in r
        assert "root" in r

    def test_str(self, simple_doc):
        assert str(simple_doc.root) == "root"

    def test_bool_always_true(self, simple_doc):
        assert bool(simple_doc.root) is True
        # Even elements with no children are truthy
        assert bool(simple_doc.root[0]) is True

    def test_equality(self, simple_doc):
        root1 = simple_doc.root
        root2 = simple_doc.root
        assert root1 == root2

    def test_inequality(self, simple_doc):
        root = simple_doc.root
        child = root[0]
        assert root != child

    def test_hash(self, simple_doc):
        root = simple_doc.root
        child = root[0]
        # Should be hashable (usable in sets/dicts)
        s = {root, child}
        assert len(s) == 2

    def test_tostring(self, simple_doc):
        raw = simple_doc.root.tostring()
        assert "<root>" in raw
        assert "</root>" in raw
        assert "hello" in raw
