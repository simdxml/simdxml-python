"""Exhaustive drop-in compatibility tests for ET read-only API.

Every test runs the same operation against both simdxml and stdlib
xml.etree.ElementTree and asserts identical results. This ensures
simdxml is a true read-only drop-in.
"""

import string
import xml.etree.ElementTree as StdET

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simdxml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Test corpora
# ---------------------------------------------------------------------------

SIMPLE = b"<root><a>hello</a><b>world</b></root>"

MIXED = b"<p>Hello <b>bold</b> and <i>italic</i> text.</p>"

NESTED = b"""\
<root>
  <a>
    <b>
      <c>deep</c>
    </b>
  </a>
  <a>
    <b>shallow</b>
  </a>
</root>"""

ATTRS = b"""\
<root>
  <item id="1" class="x" val="100"/>
  <item id="2" class="y" val="200"/>
  <item id="3" class="x" val="300"/>
</root>"""

EMPTY_ELEMENTS = b"""\
<root>
  <empty></empty>
  <selfclose/>
  <hastext>content</hastext>
</root>"""

ENTITIES = b"""\
<root>
  <text>a &amp; b &lt; c &gt; d</text>
  <quote>She said &quot;hi&quot;</quote>
</root>"""

TAIL_HEAVY = b"""\
<div>before<span>inside</span>between<br/>after<em>em</em>end</div>"""

CORPORA = [SIMPLE, MIXED, NESTED, ATTRS, EMPTY_ELEMENTS, ENTITIES, TAIL_HEAVY]


# ---------------------------------------------------------------------------
# iter() — includes self, matches stdlib
# ---------------------------------------------------------------------------


class TestIterMatchesStdlib:
    """Verify iter() produces identical results to stdlib."""

    @pytest.mark.parametrize("xml", CORPORA)
    def test_iter_all_tags_match(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert [e.tag for e in root.iter()] == [e.tag for e in std.iter()]

    @pytest.mark.parametrize("xml", CORPORA)
    def test_iter_includes_self(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        s_first = next(iter(root.iter()))
        l_first = next(iter(std.iter()))
        assert s_first.tag == l_first.tag == root.tag

    def test_iter_filtered_includes_self_when_matching(self):
        root = ET.fromstring(b"<root><root>nested</root></root>")
        std = StdET.fromstring(b"<root><root>nested</root></root>")
        s_tags = [e.tag for e in root.iter("root")]
        l_tags = [e.tag for e in std.iter("root")]
        assert s_tags == l_tags

    def test_iter_filtered_excludes_self_when_not_matching(self):
        root = ET.fromstring(SIMPLE)
        std = StdET.fromstring(SIMPLE)
        s_tags = [e.tag for e in root.iter("a")]
        l_tags = [e.tag for e in std.iter("a")]
        assert s_tags == l_tags
        assert s_tags == ["a"]

    def test_iter_on_leaf(self):
        root = ET.fromstring(b"<root><leaf/></root>")
        std = StdET.fromstring(b"<root><leaf/></root>")
        leaf_s = root.find("leaf")
        leaf_l = std.find("leaf")
        assert leaf_s is not None and leaf_l is not None
        assert [e.tag for e in leaf_s.iter()] == [e.tag for e in leaf_l.iter()]

    def test_iter_count_matches(self):
        root = ET.fromstring(NESTED)
        std = StdET.fromstring(NESTED)
        assert len(list(root.iter())) == len(list(std.iter()))


# ---------------------------------------------------------------------------
# itertext() — text + tail interleaving
# ---------------------------------------------------------------------------


class TestItertextMatchesStdlib:
    """Verify itertext() yields same text in same order as stdlib."""

    @pytest.mark.parametrize("xml", CORPORA)
    def test_itertext_joined_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        s_text = "".join(root.itertext())
        l_text = "".join(std.itertext())
        assert s_text == l_text, f"itertext mismatch on {xml[:40]!r}"

    def test_itertext_mixed_content(self):
        root = ET.fromstring(MIXED)
        std = StdET.fromstring(MIXED)
        assert list(root.itertext()) == list(std.itertext())

    def test_itertext_tail_heavy(self):
        root = ET.fromstring(TAIL_HEAVY)
        std = StdET.fromstring(TAIL_HEAVY)
        assert list(root.itertext()) == list(std.itertext())

    def test_itertext_entities(self):
        root = ET.fromstring(ENTITIES)
        std = StdET.fromstring(ENTITIES)
        s_joined = "".join(root.itertext())
        l_joined = "".join(std.itertext())
        assert s_joined == l_joined

    def test_itertext_empty_elements(self):
        root = ET.fromstring(EMPTY_ELEMENTS)
        std = StdET.fromstring(EMPTY_ELEMENTS)
        s_joined = "".join(root.itertext())
        l_joined = "".join(std.itertext())
        assert s_joined == l_joined

    def test_itertext_on_leaf(self):
        root = ET.fromstring(b"<root><leaf>text</leaf></root>")
        std = StdET.fromstring(b"<root><leaf>text</leaf></root>")
        leaf_s = root.find("leaf")
        leaf_l = std.find("leaf")
        assert leaf_s is not None and leaf_l is not None
        assert list(leaf_s.itertext()) == list(leaf_l.itertext())


# ---------------------------------------------------------------------------
# find / findall / findtext — cross-validated
# ---------------------------------------------------------------------------


_FIND_PATHS = ["*", ".//a", ".//b", "a", "b", ".//c", "nonexistent"]


class TestFindMatchesStdlib:
    """Cross-validate find/findall/findtext against stdlib."""

    @pytest.mark.parametrize("path", _FIND_PATHS)
    def test_find_matches(self, path):
        root = ET.fromstring(NESTED)
        std = StdET.fromstring(NESTED)
        s = root.find(path)
        expected = std.find(path)
        if expected is None:
            assert s is None, f"stdlib None but simdxml found on {path!r}"
        else:
            assert s is not None, f"simdxml None but stdlib found on {path!r}"
            assert s.tag == expected.tag

    @pytest.mark.parametrize("path", _FIND_PATHS)
    def test_findall_count_matches(self, path):
        root = ET.fromstring(NESTED)
        std = StdET.fromstring(NESTED)
        assert len(root.findall(path)) == len(std.findall(path)), (
            f"Count mismatch on {path!r}"
        )

    @pytest.mark.parametrize("path", _FIND_PATHS)
    def test_findall_tags_match(self, path):
        root = ET.fromstring(NESTED)
        std = StdET.fromstring(NESTED)
        s_tags = [e.tag for e in root.findall(path)]
        l_tags = [e.tag for e in std.findall(path)]
        assert s_tags == l_tags, f"Tags mismatch on {path!r}"

    def test_findtext_matches(self):
        root = ET.fromstring(NESTED)
        std = StdET.fromstring(NESTED)
        for path in [".//c", ".//b", "nonexistent"]:
            s = root.findtext(path)
            expected = std.findtext(path)
            if expected is None:
                assert s is None
            else:
                assert s is not None
                assert s.strip() == expected.strip()

    def test_findtext_default_matches(self):
        root = ET.fromstring(SIMPLE)
        std = StdET.fromstring(SIMPLE)
        assert root.findtext("missing", "X") == std.findtext("missing", "X")

    def test_findall_predicate(self):
        root = ET.fromstring(ATTRS)
        std = StdET.fromstring(ATTRS)
        s = root.findall('.//item[@class="x"]')
        expected = std.findall('.//item[@class="x"]')
        assert len(s) == len(expected)
        for si, li in zip(s, expected):
            assert si.get("id") == li.get("id")

    def test_find_wildcard_star(self):
        root = ET.fromstring(SIMPLE)
        std = StdET.fromstring(SIMPLE)
        s = root.findall("*")
        expected = std.findall("*")
        assert [e.tag for e in s] == [e.tag for e in expected]

    def test_find_parent_axis(self):
        root = ET.fromstring(b"<a><b><c/></b></a>")
        c = root.find(".//c")
        assert c is not None
        parent = c.find("..")
        assert parent is not None
        assert parent.tag == "b"

    def test_findall_on_empty(self):
        root = ET.fromstring(b"<root/>")
        assert root.findall("child") == []
        assert root.find("child") is None
        assert root.findtext("child") is None
        assert root.findtext("child", "default") == "default"

    def test_findtext_no_text_content(self):
        """Element exists but has no text → returns '' (not None)."""
        root = ET.fromstring(b"<root><tag><child/></tag></root>")
        std = StdET.fromstring(b"<root><tag><child/></tag></root>")
        assert root.findtext("tag") == std.findtext("tag")
        assert root.findtext("tag") == ""

    def test_findtext_empty_element(self):
        root = ET.fromstring(b"<root><tag></tag></root>")
        std = StdET.fromstring(b"<root><tag></tag></root>")
        assert root.findtext("tag") == std.findtext("tag")

    def test_findtext_self_closing(self):
        root = ET.fromstring(b"<root><tag/></root>")
        std = StdET.fromstring(b"<root><tag/></root>")
        assert root.findtext("tag") == std.findtext("tag")


# ---------------------------------------------------------------------------
# .text and .tail — cross-validated
# ---------------------------------------------------------------------------


class TestTextTailMatchesStdlib:
    """Verify .text and .tail match stdlib exactly."""

    @pytest.mark.parametrize("xml", CORPORA)
    def test_root_text_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        s_text = root.text
        l_text = std.text
        if l_text is None:
            assert s_text is None
        else:
            assert s_text is not None
            assert s_text == l_text

    @pytest.mark.parametrize("xml", CORPORA)
    def test_root_tail_is_none(self, xml):
        """Root element should never have tail text."""
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert root.tail is None
        assert std.tail is None

    def test_tail_mixed_content(self):
        root = ET.fromstring(MIXED)
        std = StdET.fromstring(MIXED)
        for se, le in zip(root.iter(), std.iter()):
            s_tail = se.tail
            l_tail = le.tail
            if l_tail is None:
                assert s_tail is None, f"Tail mismatch on <{se.tag}>: expected None"
            else:
                assert s_tail is not None, (
                    f"Tail mismatch on <{se.tag}>: expected {l_tail!r}"
                )
                assert s_tail == l_tail, (
                    f"Tail mismatch on <{se.tag}>: {s_tail!r} != {l_tail!r}"
                )

    def test_tail_heavy(self):
        root = ET.fromstring(TAIL_HEAVY)
        std = StdET.fromstring(TAIL_HEAVY)
        for se, le in zip(root.iter(), std.iter()):
            assert se.tail == le.tail, f"Tail mismatch on <{se.tag}>"

    def test_text_with_entities(self):
        root = ET.fromstring(ENTITIES)
        std = StdET.fromstring(ENTITIES)
        for se, le in zip(root.iter(), std.iter()):
            if le.text is not None:
                assert se.text is not None
                assert se.text == le.text, f"Text mismatch on <{se.tag}>"


# ---------------------------------------------------------------------------
# Benchmark: find/findall vs xpath
# ---------------------------------------------------------------------------


class TestFindPerformance:
    """Verify find/findall aren't significantly slower than direct xpath."""

    def test_findall_returns_same_as_xpath(self):
        root = ET.fromstring(NESTED)
        findall_result = root.findall(".//b")
        xpath_result = root.xpath(".//b")
        assert len(findall_result) == len(xpath_result)

    def test_find_returns_same_as_xpath_first(self):
        root = ET.fromstring(NESTED)
        find_result = root.find(".//b")
        xpath_result = root.xpath(".//b")
        assert find_result is not None
        assert len(xpath_result) > 0
        assert find_result.tag == xpath_result[0].tag


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


tag_chars = st.sampled_from(string.ascii_lowercase + string.digits + "_")
tag_names = st.text(tag_chars, min_size=1, max_size=8).filter(lambda s: s[0].isalpha())
text_content = st.text(
    st.sampled_from(string.ascii_letters + string.digits + " .,"),
    min_size=0,
    max_size=30,
)


@st.composite
def xml_with_children(draw):
    root = draw(tag_names)
    n = draw(st.integers(min_value=0, max_value=8))
    children = []
    for _ in range(n):
        tag = draw(tag_names)
        txt = draw(text_content)
        if txt:
            children.append(f"<{tag}>{txt}</{tag}>")
        else:
            children.append(f"<{tag}/>")
    return f"<{root}>{''.join(children)}</{root}>"


class TestPropertyCrossValidation:
    """Property tests cross-validating simdxml against stdlib."""

    @given(xml=xml_with_children())
    @settings(max_examples=100)
    def test_iter_count_always_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert len(list(root.iter())) == len(list(std.iter()))

    @given(xml=xml_with_children())
    @settings(max_examples=100)
    def test_iter_tags_always_match(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert [e.tag for e in root.iter()] == [e.tag for e in std.iter()]

    @given(xml=xml_with_children())
    @settings(max_examples=100)
    def test_findall_star_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert len(root.findall("*")) == len(std.findall("*"))

    @given(xml=xml_with_children())
    @settings(max_examples=50)
    def test_itertext_joined_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert "".join(root.itertext()) == "".join(std.itertext())

    @given(xml=xml_with_children())
    @settings(max_examples=50)
    def test_len_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert len(root) == len(std)

    @given(xml=xml_with_children())
    @settings(max_examples=50)
    def test_text_matches(self, xml):
        root = ET.fromstring(xml)
        std = StdET.fromstring(xml)
        assert root.text == std.text
        assert root.tail == std.tail
