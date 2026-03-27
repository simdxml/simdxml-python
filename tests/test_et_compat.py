"""Tests for ElementTree drop-in compatibility."""

import io
import tempfile

from simdxml.etree import ElementTree as ET

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
</library>"""


class TestParse:
    """Test ET.parse() variants."""

    def test_parse_file_path(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(BOOKS_XML)
            f.flush()
            tree = ET.parse(f.name)
            root = tree.getroot()
            assert root.tag == "library"

    def test_parse_file_object(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        root = tree.getroot()
        assert root.tag == "library"

    def test_fromstring_bytes(self):
        root = ET.fromstring(BOOKS_XML)
        assert root.tag == "library"

    def test_fromstring_str(self):
        root = ET.fromstring(BOOKS_XML.decode())
        assert root.tag == "library"


class TestTostring:
    """Test ET.tostring()."""

    def test_tostring_bytes(self):
        root = ET.fromstring(b"<root><child>text</child></root>")
        result = ET.tostring(root)
        assert isinstance(result, bytes)
        assert b"<root>" in result
        assert b"text" in result

    def test_tostring_unicode(self):
        root = ET.fromstring(b"<root><child>text</child></root>")
        result = ET.tostring(root, encoding="unicode")
        assert isinstance(result, str)
        assert "<root>" in result


class TestElementTreeClass:
    """Test ElementTree wrapper class."""

    def test_getroot(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        root = tree.getroot()
        assert root is not None
        assert root.tag == "library"

    def test_find(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        title = tree.find(".//title")
        assert title is not None
        assert title.tag == "title"

    def test_findall(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        titles = tree.findall(".//title")
        assert len(titles) == 2

    def test_iterfind(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        titles = list(tree.iterfind(".//title"))
        assert len(titles) == 2


class TestElementFind:
    """Test Element find/findall via native xpath() method.

    Note: fromstring returns a native Element which has .xpath() but not
    .find()/.findall(). Use xpath() directly with path translation.
    """

    def test_find_child(self):
        root = ET.fromstring(BOOKS_XML)
        # Use xpath for child lookup
        books = root.xpath("book")
        assert len(books) >= 1
        assert books[0].tag == "book"

    def test_findall_children(self):
        root = ET.fromstring(BOOKS_XML)
        books = root.xpath("book")
        assert len(books) == 2

    def test_find_descendant(self):
        root = ET.fromstring(BOOKS_XML)
        titles = root.xpath(".//title")
        assert len(titles) >= 1
        assert "Rust" in titles[0].text_content()

    def test_findall_descendants(self):
        root = ET.fromstring(BOOKS_XML)
        titles = root.xpath(".//title")
        assert len(titles) == 2

    def test_find_no_match(self):
        root = ET.fromstring(BOOKS_XML)
        result = root.xpath("nonexistent")
        assert result == []

    def test_findall_no_match(self):
        root = ET.fromstring(BOOKS_XML)
        result = root.xpath("nonexistent")
        assert result == []

    def test_find_with_predicate(self):
        root = ET.fromstring(BOOKS_XML)
        books = root.xpath('.//book[@lang="de"]')
        assert len(books) == 1
        assert books[0].get("lang") == "de"
