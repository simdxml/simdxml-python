"""Tests for iterparse, XMLPullParser, canonicalize, TreeBuilder, XMLParser.

Cross-validates against stdlib xml.etree.ElementTree on all operations.
"""

import io
import xml.etree.ElementTree as StdET

import pytest

from simdxml.etree import ElementTree as ET

SIMPLE = b"<root><a>hello</a><b>world</b></root>"
NESTED = b"<root><a><b><c>deep</c></b></a></root>"
MIXED = b"<p>Hello <b>bold</b> and <i>italic</i> text.</p>"
ATTRS = b'<root><item id="1" z="last" a="first"/></root>'


# ---------------------------------------------------------------------------
# iterparse
# ---------------------------------------------------------------------------


class TestIterparse:
    """Test iterparse() against stdlib."""

    def test_default_events_are_end(self):
        events = list(ET.iterparse(io.BytesIO(SIMPLE)))
        assert all(e == "end" for e, _ in events)

    def test_end_events_match_stdlib(self):
        s_events = [(e, el.tag) for e, el in ET.iterparse(io.BytesIO(SIMPLE))]
        expected_events = [(e, el.tag) for e, el in StdET.iterparse(io.BytesIO(SIMPLE))]
        assert s_events == expected_events

    def test_start_events_match_stdlib(self):
        s = [
            (e, el.tag) for e, el in ET.iterparse(io.BytesIO(SIMPLE), events=("start",))
        ]
        expected = [
            (e, el.tag)
            for e, el in StdET.iterparse(io.BytesIO(SIMPLE), events=("start",))
        ]
        assert s == expected

    def test_start_end_events_match_stdlib(self):
        s = [
            (e, el.tag)
            for e, el in ET.iterparse(io.BytesIO(SIMPLE), events=("start", "end"))
        ]
        expected = [
            (e, el.tag)
            for e, el in StdET.iterparse(io.BytesIO(SIMPLE), events=("start", "end"))
        ]
        assert s == expected

    def test_nested_events_match_stdlib(self):
        s = [
            (e, el.tag)
            for e, el in ET.iterparse(io.BytesIO(NESTED), events=("start", "end"))
        ]
        expected = [
            (e, el.tag)
            for e, el in StdET.iterparse(io.BytesIO(NESTED), events=("start", "end"))
        ]
        assert s == expected

    def test_elements_are_accessible(self):
        for _event, elem in ET.iterparse(io.BytesIO(SIMPLE)):
            assert hasattr(elem, "tag")
            assert hasattr(elem, "text")

    def test_event_count(self):
        events = list(ET.iterparse(io.BytesIO(SIMPLE), events=("start", "end")))
        std_events = list(StdET.iterparse(io.BytesIO(SIMPLE), events=("start", "end")))
        assert len(events) == len(std_events)

    def test_mixed_content_events(self):
        s = [
            (e, el.tag)
            for e, el in ET.iterparse(io.BytesIO(MIXED), events=("start", "end"))
        ]
        expected = [
            (e, el.tag)
            for e, el in StdET.iterparse(io.BytesIO(MIXED), events=("start", "end"))
        ]
        assert s == expected


# ---------------------------------------------------------------------------
# XMLPullParser
# ---------------------------------------------------------------------------


class TestXMLPullParser:
    """Test XMLPullParser against stdlib."""

    def test_basic_feed_and_close(self):
        p = ET.XMLPullParser(events=("start", "end"))
        p.feed(SIMPLE)
        p.close()
        events = list(p.read_events())
        assert len(events) > 0
        tags = [(e, el.tag) for e, el in events]
        assert ("start", "root") in tags
        assert ("end", "root") in tags

    def test_incremental_feed(self):
        p = ET.XMLPullParser(events=("start", "end"))
        p.feed(b"<root>")
        p.feed(b"<a>hello</a>")
        p.feed(b"</root>")
        p.close()
        events = list(p.read_events())
        tags = [(e, el.tag) for e, el in events]
        assert ("start", "root") in tags
        assert ("end", "a") in tags

    def test_events_match_stdlib(self):
        s_parser = ET.XMLPullParser(events=("start", "end"))
        s_parser.feed(SIMPLE)
        s_parser.close()
        s_events = [(e, el.tag) for e, el in s_parser.read_events()]

        l_parser = StdET.XMLPullParser(events=("start", "end"))
        l_parser.feed(SIMPLE)
        l_parser.close()
        expected_events = [(e, el.tag) for e, el in l_parser.read_events()]

        assert s_events == expected_events

    def test_default_events_are_end(self):
        p = ET.XMLPullParser()
        p.feed(SIMPLE)
        p.close()
        events = list(p.read_events())
        assert all(e == "end" for e, _ in events)

    def test_flush_does_not_error(self):
        p = ET.XMLPullParser()
        p.flush()  # should not raise

    def test_str_feed(self):
        p = ET.XMLPullParser(events=("end",))
        p.feed("<root><a/></root>")
        p.close()
        events = list(p.read_events())
        assert len(events) > 0


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


class TestCanonicalize:
    """Test C14N canonicalization against stdlib."""

    def test_sorted_attributes(self):
        xml = '<root z="2" a="1" m="3"/>'
        s = ET.canonicalize(xml)
        expected = StdET.canonicalize(xml)
        assert s == expected

    def test_expanded_empty_elements(self):
        xml = "<root><empty/></root>"
        s = ET.canonicalize(xml)
        assert "<empty></empty>" in s
        # No self-closing in C14N
        assert "/>" not in s

    def test_simple_matches_stdlib(self):
        xml = "<root><a>text</a><b/></root>"
        s = ET.canonicalize(xml)
        expected = StdET.canonicalize(xml)
        assert s == expected

    def test_nested_matches_stdlib(self):
        s = ET.canonicalize(NESTED)
        expected = StdET.canonicalize(NESTED)
        assert s == expected

    def test_with_attributes_matches_stdlib(self):
        s = ET.canonicalize(ATTRS)
        expected = StdET.canonicalize(ATTRS)
        assert s == expected

    def test_entities_escaped(self):
        xml = "<root>a &amp; b</root>"
        s = ET.canonicalize(xml)
        assert "&amp;" in s

    def test_output_to_file(self):
        buf = io.StringIO()
        result = ET.canonicalize("<root/>", out=buf)
        assert result is None
        assert "<root>" in buf.getvalue()

    def test_from_file(self):
        s = ET.canonicalize(from_file=io.BytesIO(SIMPLE))
        expected = StdET.canonicalize(from_file=io.BytesIO(SIMPLE))
        assert s == expected

    def test_strip_text(self):
        xml = "<root>  hello  </root>"
        s = ET.canonicalize(xml, strip_text=True)
        expected = StdET.canonicalize(xml, strip_text=True)
        assert s == expected

    def test_mixed_content_matches_stdlib(self):
        s = ET.canonicalize(MIXED)
        expected = StdET.canonicalize(MIXED)
        assert s == expected


# ---------------------------------------------------------------------------
# TreeBuilder
# ---------------------------------------------------------------------------


class TestTreeBuilder:
    """Test TreeBuilder compatibility."""

    def test_basic_build(self):
        tb = ET.TreeBuilder()
        tb.start("root", {})
        tb.start("child", {"id": "1"})
        tb.data("hello")
        tb.end("child")
        tb.end("root")
        root = tb.close()
        assert root.tag == "root"
        assert len(root) == 1
        assert root[0].tag == "child"
        assert root[0].text == "hello"

    def test_attributes(self):
        tb = ET.TreeBuilder()
        tb.start("root", {"a": "1", "b": "2"})
        tb.end("root")
        root = tb.close()
        assert root.get("a") == "1"
        assert root.get("b") == "2"

    def test_nested(self):
        tb = ET.TreeBuilder()
        tb.start("a", {})
        tb.start("b", {})
        tb.start("c", {})
        tb.data("deep")
        tb.end("c")
        tb.end("b")
        tb.end("a")
        root = tb.close()
        assert root.find(".//c") is not None

    def test_empty_raises(self):
        tb = ET.TreeBuilder()
        with pytest.raises(ValueError):
            tb.close()


# ---------------------------------------------------------------------------
# XMLParser
# ---------------------------------------------------------------------------


class TestXMLParser:
    """Test XMLParser compatibility."""

    def test_basic_feed_close(self):
        p = ET.XMLParser()
        p.feed(b"<root><a>hello</a></root>")
        root = p.close()
        assert root.tag == "root"
        assert root[0].text == "hello"

    def test_incremental_feed(self):
        p = ET.XMLParser()
        p.feed(b"<root>")
        p.feed(b"<a>hello</a>")
        p.feed(b"</root>")
        root = p.close()
        assert root.tag == "root"
        assert len(root) == 1

    def test_str_feed(self):
        p = ET.XMLParser()
        p.feed("<root/>")
        root = p.close()
        assert root.tag == "root"

    def test_flush_does_not_error(self):
        p = ET.XMLParser()
        p.flush()

    def test_has_entity_dict(self):
        p = ET.XMLParser()
        assert isinstance(p.entity, dict)

    def test_has_version(self):
        p = ET.XMLParser()
        assert p.version == "1.0"

    def test_parse_with_parser(self):
        """ET.parse(source, parser=XMLParser()) should work."""
        p = ET.XMLParser()
        tree = ET.parse(io.BytesIO(SIMPLE), parser=p)
        assert tree.getroot().tag == "root"


# ---------------------------------------------------------------------------
# XML alias
# ---------------------------------------------------------------------------


class TestXMLAlias:
    """Test that ET.XML is an alias for ET.fromstring."""

    def test_xml_alias(self):
        root = ET.XML(b"<root><a/></root>")
        assert root.tag == "root"
        assert len(root) == 1


# ---------------------------------------------------------------------------
# Adversarial / edge cases
# ---------------------------------------------------------------------------


class TestStreamingEdgeCases:
    """Edge cases for streaming APIs."""

    def test_iterparse_empty_root(self):
        events = list(ET.iterparse(io.BytesIO(b"<root/>")))
        assert len(events) == 1
        assert events[0][0] == "end"
        assert events[0][1].tag == "root"

    def test_pullparser_empty_feed(self):
        p = ET.XMLPullParser()
        p.close()
        events = list(p.read_events())
        assert events == []

    def test_canonicalize_self_closing(self):
        s = ET.canonicalize("<br/>")
        assert s == "<br></br>"

    def test_canonicalize_no_input_raises(self):
        with pytest.raises(ValueError, match="either xml_data or from_file"):
            ET.canonicalize()

    def test_iterparse_large(self):
        xml = b"<root>" + b"<item/>" * 10000 + b"</root>"
        events = list(ET.iterparse(io.BytesIO(xml)))
        assert len(events) == 10001  # 10000 items + root

    def test_canonicalize_special_chars(self):
        xml = "<root>a &lt; b &amp; c</root>"
        s = ET.canonicalize(xml)
        expected = StdET.canonicalize(xml)
        assert s == expected
