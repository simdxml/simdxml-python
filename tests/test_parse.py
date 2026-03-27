"""Tests for parsing: bytes, str, files, encoding, errors."""

import tempfile

import pytest

import simdxml

from .conftest import (
    BOOKS_XML,
    CDATA_XML,
    ENTITIES_XML,
    SELF_CLOSING_XML,
    SIMPLE_XML,
    make_large_xml,
)


class TestParseInput:
    """Test various input types for parse()."""

    def test_parse_bytes(self):
        doc = simdxml.parse(b"<root/>")
        assert doc.root is not None

    def test_parse_str(self):
        doc = simdxml.parse("<root/>")
        assert doc.root is not None

    def test_parse_bytes_with_content(self):
        doc = simdxml.parse(SIMPLE_XML)
        assert doc.root is not None
        assert doc.root.tag == "root"

    def test_parse_str_with_content(self):
        doc = simdxml.parse(SIMPLE_XML.decode())
        assert doc.root is not None
        assert doc.root.tag == "root"

    def test_parse_invalid_type(self):
        with pytest.raises(TypeError, match="requires bytes or str"):
            simdxml.parse(42)  # type: ignore[arg-type]

    def test_parse_invalid_type_list(self):
        with pytest.raises(TypeError):
            simdxml.parse([1, 2, 3])  # type: ignore[arg-type]


class TestParseXmlDeclaration:
    """Test XML declaration handling."""

    def test_xml_declaration_utf8(self):
        xml = b'<?xml version="1.0" encoding="UTF-8"?><root>text</root>'
        doc = simdxml.parse(xml)
        assert doc.root is not None

    def test_xml_declaration_standalone(self):
        xml = b'<?xml version="1.0" standalone="yes"?><root/>'
        doc = simdxml.parse(xml)
        assert doc.root is not None


class TestParseErrors:
    """Test error handling for malformed XML."""

    def test_empty_input(self):
        # simdxml produces an empty index for empty input; root is None
        doc = simdxml.parse(b"")
        assert doc.root is None

    def test_empty_string(self):
        doc = simdxml.parse("")
        assert doc.root is None

    def test_not_xml(self):
        # Non-XML text produces an index with no elements
        doc = simdxml.parse(b"this is not xml")
        assert doc.root is None

    def test_unclosed_tag(self):
        # simdxml is lenient about unclosed tags (structural parser)
        # It may still parse — just verify it doesn't segfault
        doc = simdxml.parse(b"<root><child></root>")
        assert doc.root is not None

    def test_mismatched_tags(self):
        # Lenient parsing — verify no crash
        doc = simdxml.parse(b"<root></wrong>")
        assert doc.root is not None


class TestParseDocumentFeatures:
    """Test various XML document features."""

    def test_self_closing_tags(self):
        doc = simdxml.parse(SELF_CLOSING_XML)
        root = doc.root
        assert root is not None
        children = list(root)
        assert len(children) == 3
        assert children[0].tag == "br"
        assert children[1].tag == "hr"
        assert children[2].tag == "img"

    def test_cdata_section(self):
        doc = simdxml.parse(CDATA_XML)
        root = doc.root
        assert root is not None
        code = next(iter(root))
        assert code.tag == "code"

    def test_entities(self):
        doc = simdxml.parse(ENTITIES_XML)
        root = doc.root
        assert root is not None
        text_elem = next(iter(root))
        text = text_elem.text
        assert text is not None
        assert "&" in text
        assert "<XML>" in text

    def test_comments_preserved(self):
        xml = b"<root><!-- comment --><child/></root>"
        doc = simdxml.parse(xml)
        assert doc.root is not None

    def test_processing_instruction(self):
        xml = b'<?xml version="1.0"?><?pi target?><root/>'
        doc = simdxml.parse(xml)
        assert doc.root is not None


class TestParseDocumentProperties:
    """Test Document object properties."""

    def test_tag_count(self):
        doc = simdxml.parse(SIMPLE_XML)
        assert doc.tag_count > 0

    def test_repr(self):
        doc = simdxml.parse(SIMPLE_XML)
        r = repr(doc)
        assert "Document" in r
        assert "tags=" in r

    def test_root_is_first_element(self):
        doc = simdxml.parse(BOOKS_XML)
        assert doc.root is not None
        assert doc.root.tag == "library"


class TestParseLargeDocuments:
    """Test parsing larger documents."""

    def test_1000_elements(self):
        xml = make_large_xml(1000)
        doc = simdxml.parse(xml)
        assert doc.root is not None
        assert doc.tag_count > 1000

    def test_10000_elements(self):
        xml = make_large_xml(10000)
        doc = simdxml.parse(xml)
        assert doc.root is not None
        results = doc.xpath_text("//name")
        assert len(results) == 10000

    def test_parse_from_file(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(BOOKS_XML)
            f.flush()
            with open(f.name, "rb") as rf:
                data = rf.read()
            doc = simdxml.parse(data)
            assert doc.root is not None
            assert doc.root.tag == "library"
