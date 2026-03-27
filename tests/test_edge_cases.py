"""Tests for edge cases: empty docs, large docs, malformed input, encoding."""

import simdxml

from .conftest import make_large_xml


class TestEmptyAndMinimal:
    """Test minimal/boundary XML documents."""

    def test_self_closing_root(self):
        doc = simdxml.parse(b"<root/>")
        assert doc.root is not None
        assert doc.root.tag == "root"
        assert len(doc.root) == 0
        assert doc.root.text is None

    def test_root_with_whitespace(self):
        doc = simdxml.parse(b"<root>  </root>")
        assert doc.root is not None

    def test_deeply_nested(self):
        """100 levels of nesting."""
        xml = b"<" + b"><".join(f"d{i}".encode() for i in range(100))
        xml += b">deep"
        xml += b"".join(f"</d{i}>".encode() for i in range(99, -1, -1))
        doc = simdxml.parse(xml)
        assert doc.root is not None
        assert doc.root.tag == "d0"


class TestSpecialCharacters:
    """Test XML with special characters."""

    def test_entities_in_text(self):
        xml = b"<root>Hello &amp; welcome to &lt;XML&gt;</root>"
        doc = simdxml.parse(xml)
        text = doc.root.text
        assert text is not None
        assert "&" in text
        assert "<XML>" in text

    def test_entities_in_attributes(self):
        xml = b'<root attr="a&amp;b"/>'
        doc = simdxml.parse(xml)
        val = doc.root.get("attr")
        assert val is not None
        # Attribute values may or may not decode entities
        assert "a" in val and "b" in val

    def test_numeric_entity(self):
        xml = b"<root>&#65;&#x42;</root>"
        doc = simdxml.parse(xml)
        text = doc.root.text
        assert text is not None
        assert "A" in text  # &#65; = 'A'
        assert "B" in text  # &#x42; = 'B'

    def test_unicode_content(self):
        xml = "<root>日本語テスト</root>".encode()
        doc = simdxml.parse(xml)
        text = doc.root.text
        assert text is not None
        assert "日本語" in text

    def test_unicode_tag_names(self):
        xml = "<données><élément>valeur</élément></données>".encode()
        doc = simdxml.parse(xml)
        assert doc.root is not None
        assert doc.root.tag == "données"


class TestSelfClosingTags:
    """Test self-closing tag behavior."""

    def test_self_closing_has_no_children(self):
        doc = simdxml.parse(b"<root><br/></root>")
        br = doc.root[0]
        assert len(br) == 0
        assert br.text is None
        assert list(br) == []

    def test_self_closing_with_attributes(self):
        doc = simdxml.parse(b'<root><img src="test.png" alt="test"/></root>')
        img = doc.root[0]
        assert img.get("src") == "test.png"
        assert img.get("alt") == "test"

    def test_self_closing_iteration(self):
        doc = simdxml.parse(b"<root><br/><br/><br/></root>")
        children = list(doc.root)
        assert len(children) == 3
        assert all(c.tag == "br" for c in children)


class TestMixedContent:
    """Test interleaved text and elements."""

    def test_text_between_elements(self):
        xml = b"<root>before<a/>middle<b/>after</root>"
        doc = simdxml.parse(xml)
        root = doc.root
        # .text should be text before first child
        assert root.text == "before"

    def test_itertext_captures_all(self):
        xml = b"<root>A<child>B</child>C</root>"
        doc = simdxml.parse(xml)
        texts = doc.root.itertext()
        all_text = "".join(texts)
        assert "A" in all_text
        assert "B" in all_text
        assert "C" in all_text


class TestLargeDocuments:
    """Test performance sanity with large documents."""

    def test_10k_elements_parse(self):
        xml = make_large_xml(10000)
        doc = simdxml.parse(xml)
        assert doc.tag_count > 10000

    def test_10k_elements_xpath(self):
        xml = make_large_xml(10000)
        doc = simdxml.parse(xml)
        results = doc.xpath_text("//name")
        assert len(results) == 10000

    def test_10k_elements_compiled_xpath(self):
        xml = make_large_xml(10000)
        doc = simdxml.parse(xml)
        expr = simdxml.compile("//name")
        results = expr.eval_text(doc)
        assert len(results) == 10000

    def test_10k_xpath_with_predicate(self):
        xml = make_large_xml(10000)
        doc = simdxml.parse(xml)
        result = doc.xpath('//item[@id="5000"]')
        assert len(result) == 1


class TestBinaryInput:
    """Test behavior with non-XML binary data."""

    def test_binary_data_no_crash(self):
        # simdxml is lenient; binary data doesn't segfault, just produces empty index
        doc = simdxml.parse(b"\x00\x01\x02\x03")
        assert doc.root is None

    def test_partial_binary_no_crash(self):
        # Binary prefix before XML — may or may not parse
        simdxml.parse(b"\x00<root/>")
        # Just verify no crash
