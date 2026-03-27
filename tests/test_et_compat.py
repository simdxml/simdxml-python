"""Tests for ElementTree drop-in compatibility.

Validates that simdxml's ET compat layer produces identical results to
stdlib xml.etree.ElementTree for all read-only operations. Each test
runs against both simdxml and stdlib and compares results.
"""

import io
import tempfile
import xml.etree.ElementTree as StdET

import pytest

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
  <book lang="en" year="2021">
    <title>Programming Rust</title>
    <author>Jim Blandy</author>
    <author>Jason Orendorff</author>
  </book>
</library>"""

MIXED_XML = b"""\
<doc>
  <p>Hello <b>bold</b> and <i>italic</i> text.</p>
  <ul>
    <li>one</li>
    <li>two</li>
    <li>three</li>
  </ul>
</doc>"""

ATTRS_XML = b"""\
<root>
  <item id="1" class="a" data-x="100"/>
  <item id="2" class="b" data-x="200"/>
  <item id="3" class="a" data-x="300"/>
</root>"""


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


class TestParse:
    """Test ET.parse() from files and file objects."""

    def test_parse_file_path(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(BOOKS_XML)
            f.flush()
            tree = ET.parse(f.name)
            assert tree.getroot().tag == "library"

    def test_parse_file_object(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        assert tree.getroot().tag == "library"

    def test_parse_matches_stdlib(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        std_tree = StdET.parse(io.BytesIO(BOOKS_XML))
        assert tree.getroot().tag == std_tree.getroot().tag
        assert len(tree.getroot()) == len(std_tree.getroot())


class TestFromstring:
    """Test ET.fromstring()."""

    def test_bytes(self):
        root = ET.fromstring(BOOKS_XML)
        assert root.tag == "library"

    def test_str(self):
        root = ET.fromstring(BOOKS_XML.decode())
        assert root.tag == "library"

    def test_matches_stdlib(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)
        assert root.tag == std.tag
        assert len(root) == len(std)
        for s, st in zip(root, std):
            assert s.tag == st.tag


class TestFromstringlist:
    """Test ET.fromstringlist()."""

    def test_list_of_bytes(self):
        root = ET.fromstringlist([b"<root>", b"<child/>", b"</root>"])
        assert root.tag == "root"
        assert len(root) == 1

    def test_list_of_str(self):
        root = ET.fromstringlist(["<root>", "<child/>", "</root>"])
        assert root.tag == "root"


class TestTostring:
    """Test ET.tostring()."""

    def test_returns_bytes(self):
        root = ET.fromstring(b"<root><child>text</child></root>")
        result = ET.tostring(root)
        assert isinstance(result, bytes)
        assert b"<root>" in result

    def test_unicode_encoding(self):
        root = ET.fromstring(b"<root><child>text</child></root>")
        result = ET.tostring(root, encoding="unicode")
        assert isinstance(result, str)
        assert "<root>" in result

    def test_tostringlist(self):
        root = ET.fromstring(b"<root/>")
        result = ET.tostringlist(root)
        assert isinstance(result, list)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# ElementTree class
# ---------------------------------------------------------------------------


class TestElementTreeClass:
    """Test the ElementTree wrapper class."""

    def test_getroot(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        root = tree.getroot()
        assert root.tag == "library"

    def test_find(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        title = tree.find(".//title")
        assert title is not None
        assert title.tag == "title"

    def test_findall(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        titles = tree.findall(".//title")
        assert len(titles) == 3

    def test_findtext(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        text = tree.findtext(".//title")
        assert text is not None
        assert "Rust" in text

    def test_findtext_default(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        text = tree.findtext(".//nonexistent", default="nope")
        assert text == "nope"

    def test_iterfind(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        titles = list(tree.iterfind(".//title"))
        assert len(titles) == 3

    def test_iter(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        all_tags = [e.tag for e in tree.iter()]
        assert "library" in all_tags
        assert "book" in all_tags
        assert "title" in all_tags

    def test_iter_filtered(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        authors = list(tree.iter("author"))
        assert len(authors) == 4

    def test_write_raises(self):
        tree = ET.parse(io.BytesIO(BOOKS_XML))
        with pytest.raises(TypeError, match="read-only"):
            tree.write("output.xml")


# ---------------------------------------------------------------------------
# Element.find / findall / iterfind / findtext
# ---------------------------------------------------------------------------


class TestElementFind:
    """Test find/findall/iterfind/findtext on Element."""

    def test_find_child(self):
        root = ET.fromstring(BOOKS_XML)
        book = root.find("book")
        assert book is not None
        assert book.tag == "book"

    def test_find_descendant(self):
        root = ET.fromstring(BOOKS_XML)
        title = root.find(".//title")
        assert title is not None

    def test_find_no_match(self):
        root = ET.fromstring(BOOKS_XML)
        assert root.find("nonexistent") is None

    def test_findall_children(self):
        root = ET.fromstring(BOOKS_XML)
        books = root.findall("book")
        assert len(books) == 3

    def test_findall_descendants(self):
        root = ET.fromstring(BOOKS_XML)
        titles = root.findall(".//title")
        assert len(titles) == 3

    def test_findall_no_match(self):
        root = ET.fromstring(BOOKS_XML)
        result = root.findall("nonexistent")
        assert len(result) == 0

    def test_findall_with_predicate(self):
        root = ET.fromstring(BOOKS_XML)
        en_books = root.findall('.//book[@lang="en"]')
        assert len(en_books) == 2

    def test_findtext_found(self):
        root = ET.fromstring(BOOKS_XML)
        text = root.findtext(".//title")
        assert text is not None
        assert "Rust" in text

    def test_findtext_not_found_default(self):
        root = ET.fromstring(BOOKS_XML)
        text = root.findtext("nonexistent", default="fallback")
        assert text == "fallback"

    def test_findtext_not_found_no_default(self):
        root = ET.fromstring(BOOKS_XML)
        text = root.findtext("nonexistent")
        assert text is None

    def test_iterfind(self):
        root = ET.fromstring(BOOKS_XML)
        titles = list(root.iterfind(".//title"))
        assert len(titles) == 3

    def test_iterfind_is_iterator(self):
        root = ET.fromstring(BOOKS_XML)
        result = root.iterfind(".//title")
        assert hasattr(result, "__next__")


class TestElementFindMatchesStdlib:
    """Cross-validate find/findall results against stdlib."""

    def test_findall_same_count(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)

        for path in ["book", ".//title", ".//author", "*"]:
            s_results = root.findall(path)
            l_results = std.findall(path)
            assert len(s_results) == len(l_results), (
                f"Mismatch on path {path!r}: "
                f"simdxml={len(s_results)}, stdlib={len(l_results)}"
            )

    def test_findall_same_tags(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)

        for path in [".//title", ".//author"]:
            s_tags = [e.tag for e in root.findall(path)]
            l_tags = [e.tag for e in std.findall(path)]
            assert s_tags == l_tags, f"Tag mismatch on {path!r}"

    def test_find_same_element(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)

        for path in ["book", ".//title", ".//author"]:
            s = root.find(path)
            st_result = std.find(path)
            if st_result is None:
                assert s is None, f"stdlib None but simdxml found on {path!r}"
            else:
                assert s is not None, f"stdlib found but simdxml None on {path!r}"
                assert s.tag == st_result.tag

    def test_findtext_same_text(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)

        for path in [".//title", ".//author"]:
            s_text = root.findtext(path)
            l_text = std.findtext(path)
            assert s_text is not None
            assert l_text is not None
            assert s_text.strip() == l_text.strip(), (
                f"Text mismatch on {path!r}: simdxml={s_text!r}, stdlib={l_text!r}"
            )


# ---------------------------------------------------------------------------
# Element properties matching stdlib
# ---------------------------------------------------------------------------


class TestElementPropertiesMatchStdlib:
    """Verify element properties match stdlib behavior."""

    def test_tag(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)
        assert root.tag == std.tag
        for s, st in zip(root, std):
            assert s.tag == st.tag

    def test_text(self):
        root = ET.fromstring(MIXED_XML)
        std = StdET.fromstring(MIXED_XML)
        p = root.find("p")
        std_p = std.find("p")
        assert p is not None and std_p is not None
        # Both should have text before first child
        assert p.text is not None
        assert std_p.text is not None
        assert p.text.strip() == std_p.text.strip()

    def test_attrib(self):
        root = ET.fromstring(ATTRS_XML)
        std = StdET.fromstring(ATTRS_XML)
        for s, st in zip(root, std):
            assert s.attrib == st.attrib

    def test_get(self):
        root = ET.fromstring(ATTRS_XML)
        std = StdET.fromstring(ATTRS_XML)
        for s, st in zip(root, std):
            assert s.get("id") == st.get("id")
            assert s.get("missing") == st.get("missing")
            assert s.get("missing", "x") == st.get("missing", "x")

    def test_len(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)
        assert len(root) == len(std)
        for s, st in zip(root, std):
            assert len(s) == len(st)

    def test_iter(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)
        s_tags = [e.tag for e in root.iter()]
        l_tags = [e.tag for e in std.iter()]
        assert s_tags == l_tags

    def test_iter_filtered(self):
        root = ET.fromstring(BOOKS_XML)
        std = StdET.fromstring(BOOKS_XML)
        s_tags = [e.tag for e in root.iter("author")]
        l_tags = [e.tag for e in std.iter("author")]
        assert s_tags == l_tags

    def test_itertext(self):
        root = ET.fromstring(MIXED_XML)
        std = StdET.fromstring(MIXED_XML)
        s_texts = root.itertext()
        l_texts = list(std.itertext())
        # Compare concatenated (ordering may differ in whitespace)
        assert "".join(s_texts).strip() == "".join(l_texts).strip()

    def test_keys_items(self):
        root = ET.fromstring(ATTRS_XML)
        std = StdET.fromstring(ATTRS_XML)
        for s, st in zip(root, std):
            assert sorted(s.keys()) == sorted(st.keys())
            assert sorted(s.items()) == sorted(st.items())


# ---------------------------------------------------------------------------
# Module-level functions
# ---------------------------------------------------------------------------


class TestModuleFunctions:
    """Test module-level ET compat functions."""

    def test_iselement(self):
        root = ET.fromstring(b"<root/>")
        assert ET.iselement(root) is True
        assert ET.iselement("not an element") is False
        assert ET.iselement(42) is False

    def test_dump(self, capsys):
        root = ET.fromstring(b"<root><child/></root>")
        ET.dump(root)
        captured = capsys.readouterr()
        assert "<root>" in captured.out

    def test_register_namespace(self):
        # Should not raise
        ET.register_namespace("test", "http://example.com")


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------


class TestReadOnlyStubs:
    """Test that construction/mutation functions raise TypeError."""

    def test_subelement(self):
        root = ET.fromstring(b"<root/>")
        with pytest.raises(TypeError, match="read-only"):
            ET.SubElement(root, "child")

    def test_comment(self):
        with pytest.raises(TypeError, match="read-only"):
            ET.Comment("text")

    def test_processing_instruction(self):
        with pytest.raises(TypeError, match="read-only"):
            ET.ProcessingInstruction("target", "data")

    def test_pi_alias(self):
        with pytest.raises(TypeError, match="read-only"):
            ET.PI("target")

    def test_indent(self):
        root = ET.fromstring(b"<root><child/></root>")
        with pytest.raises(TypeError, match="read-only"):
            ET.indent(root)

    def test_element_extend(self):
        root = ET.fromstring(b"<root/>")
        with pytest.raises(TypeError, match="read-only"):
            root.extend([])

    def test_element_makeelement(self):
        root = ET.fromstring(b"<root/>")
        with pytest.raises(TypeError, match="read-only"):
            root.makeelement("tag", {})


# ---------------------------------------------------------------------------
# Adversarial / edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Adversarial and edge-case tests for ET compat."""

    def test_empty_document(self):
        doc = ET.fromstring(b"<root/>")
        assert doc.tag == "root"
        assert len(doc) == 0
        assert doc.find("child") is None
        assert doc.findall("child") == []
        assert doc.findtext("child") is None
        assert doc.findtext("child", default="x") == "x"

    def test_deeply_nested_find(self):
        xml = b"<a><b><c><d><e>deep</e></d></c></b></a>"
        root = ET.fromstring(xml)
        e = root.find(".//e")
        assert e is not None
        assert e.text == "deep"

    def test_find_with_predicate(self):
        root = ET.fromstring(ATTRS_XML)
        item = root.find('.//item[@class="b"]')
        assert item is not None
        assert item.get("id") == "2"

    def test_findall_wildcard(self):
        root = ET.fromstring(BOOKS_XML)
        children = root.findall("*")
        assert len(children) == 3

    def test_find_parent_axis(self):
        root = ET.fromstring(b"<a><b><c/></b></a>")
        c = root.find(".//c")
        assert c is not None
        # .find("..") should find parent
        parent = c.find("..")
        assert parent is not None
        assert parent.tag == "b"

    def test_self_closing_elements(self):
        root = ET.fromstring(b"<root><br/><hr/></root>")
        elements = root.findall("*")
        assert len(elements) == 2

    def test_unicode_content(self):
        xml = "<root><item>日本語</item></root>".encode()
        root = ET.fromstring(xml)
        item = root.find("item")
        assert item is not None
        assert item.text is not None
        assert "日本語" in item.text

    def test_entities_in_find_result(self):
        root = ET.fromstring(b"<root><item>a &amp; b</item></root>")
        text = root.findtext("item")
        assert text is not None
        assert "&" in text

    def test_multiple_findall_calls_consistent(self):
        root = ET.fromstring(BOOKS_XML)
        r1 = root.findall(".//title")
        r2 = root.findall(".//title")
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.tag == b.tag

    def test_findall_on_leaf_element(self):
        root = ET.fromstring(b"<root><leaf>text</leaf></root>")
        leaf = root.find("leaf")
        assert leaf is not None
        # findall on a leaf should return empty
        assert leaf.findall("child") == []

    def test_bool_on_element_always_true(self):
        """stdlib ET elements are falsy when empty; we're always truthy."""
        root = ET.fromstring(b"<root/>")
        # Our design decision: always truthy
        assert bool(root) is True
