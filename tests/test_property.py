"""Property-based tests using Hypothesis."""

import string

from hypothesis import given, settings
from hypothesis import strategies as st

import simdxml

# ---------------------------------------------------------------------------
# Strategies for generating valid XML
# ---------------------------------------------------------------------------

tag_name_chars = st.sampled_from(string.ascii_lowercase + string.digits + "_")
tag_names = st.text(tag_name_chars, min_size=1, max_size=10).filter(
    lambda s: s[0].isalpha()
)
text_content = st.text(
    st.sampled_from(string.ascii_letters + string.digits + " .,!?"),
    min_size=0,
    max_size=50,
)


@st.composite
def simple_xml(draw):
    """Generate a simple valid XML document."""
    root_tag = draw(tag_names)
    n_children = draw(st.integers(min_value=0, max_value=10))
    children = []
    for _ in range(n_children):
        child_tag = draw(tag_names)
        child_text = draw(text_content)
        if child_text:
            children.append(f"<{child_tag}>{child_text}</{child_tag}>")
        else:
            children.append(f"<{child_tag}/>")
    body = "".join(children)
    return f"<{root_tag}>{body}</{root_tag}>"


@st.composite
def nested_xml(draw, max_depth=5):
    """Generate nested XML with configurable depth."""
    root_tag = draw(tag_names)

    def build_tree(depth):
        tag = draw(tag_names)
        if depth >= max_depth or draw(st.booleans()):
            text = draw(text_content)
            if text:
                return f"<{tag}>{text}</{tag}>"
            return f"<{tag}/>"
        n_children = draw(st.integers(min_value=1, max_value=3))
        children = "".join(build_tree(depth + 1) for _ in range(n_children))
        return f"<{tag}>{children}</{tag}>"

    body = build_tree(0)
    return f"<{root_tag}>{body}</{root_tag}>"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestParseProperties:
    """Property: parse never crashes on valid XML."""

    @given(xml=simple_xml())
    @settings(max_examples=100)
    def test_parse_valid_xml_succeeds(self, xml):
        doc = simdxml.parse(xml)
        assert doc.root is not None

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_root_has_valid_tag(self, xml):
        doc = simdxml.parse(xml)
        tag = doc.root.tag
        assert isinstance(tag, str)
        assert len(tag) > 0

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_text_is_str_or_none(self, xml):
        doc = simdxml.parse(xml)
        text = doc.root.text
        assert text is None or isinstance(text, str)

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_attrib_is_dict(self, xml):
        doc = simdxml.parse(xml)
        attrib = doc.root.attrib
        assert isinstance(attrib, dict)


class TestNavigationProperties:
    """Property: navigation invariants hold."""

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_root_parent_is_none(self, xml):
        doc = simdxml.parse(xml)
        assert doc.root.getparent() is None

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_child_parent_is_self(self, xml):
        doc = simdxml.parse(xml)
        root = doc.root
        for child in root:
            parent = child.getparent()
            assert parent is not None
            assert parent == root

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_len_matches_iter(self, xml):
        doc = simdxml.parse(xml)
        root = doc.root
        assert len(root) == len(list(root))

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_getitem_matches_iter(self, xml):
        doc = simdxml.parse(xml)
        root = doc.root
        children = list(root)
        for i, child in enumerate(children):
            assert root[i] == child


class TestXpathProperties:
    """Property: XPath queries don't crash."""

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_xpath_wildcard_never_crashes(self, xml):
        doc = simdxml.parse(xml)
        result = doc.xpath("//*")
        assert isinstance(result, list)

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_xpath_text_never_crashes(self, xml):
        doc = simdxml.parse(xml)
        result = doc.xpath_text("//*")
        assert isinstance(result, list)
        assert all(isinstance(s, str) for s in result)

    @given(xml=simple_xml())
    @settings(max_examples=50)
    def test_compiled_xpath_consistent(self, xml):
        """Compiled and inline XPath give the same results."""
        doc = simdxml.parse(xml)
        expr = simdxml.compile("//*")
        inline = doc.xpath_text("//*")
        compiled = expr.eval_text(doc)
        assert inline == compiled
