"""Shared fixtures for simdxml tests."""

import pytest

import simdxml

# ---------------------------------------------------------------------------
# Sample XML documents
# ---------------------------------------------------------------------------

SIMPLE_XML = b"<root><child>hello</child><child>world</child></root>"

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

MIXED_CONTENT_XML = b"""\
<p>Hello <b>bold</b> and <i>italic</i> text.</p>"""

NESTED_XML = b"""\
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

ATTRIBUTES_XML = b"""\
<root>
  <item id="1" class="primary" data-value="100"/>
  <item id="2" class="secondary" data-value="200"/>
  <item id="3" class="primary" data-value="300"/>
</root>"""

NAMESPACED_XML = b"""\
<root xmlns:ns="http://example.com" xmlns:other="http://other.com">
  <ns:item ns:id="1">first</ns:item>
  <other:item other:id="2">second</other:item>
  <plain>third</plain>
</root>"""

SELF_CLOSING_XML = b"""\
<root>
  <br/>
  <hr class="divider"/>
  <img src="test.png" alt="test"/>
</root>"""

CDATA_XML = b"""\
<root>
  <code><![CDATA[if (a < b && c > d) { return true; }]]></code>
</root>"""

ENTITIES_XML = b"""\
<root>
  <text>Hello &amp; welcome to &lt;XML&gt;</text>
  <quote>She said &quot;hello&quot;</quote>
</root>"""

EMPTY_ELEMENTS_XML = b"""\
<root>
  <empty></empty>
  <also-empty/>
  <has-text>content</has-text>
</root>"""

LARGE_XML_TEMPLATE = """\
<catalog>
{items}
</catalog>"""


@pytest.fixture
def simple_doc():
    return simdxml.parse(SIMPLE_XML)


@pytest.fixture
def books_doc():
    return simdxml.parse(BOOKS_XML)


@pytest.fixture
def nested_doc():
    return simdxml.parse(NESTED_XML)


@pytest.fixture
def attrs_doc():
    return simdxml.parse(ATTRIBUTES_XML)


@pytest.fixture
def mixed_doc():
    return simdxml.parse(MIXED_CONTENT_XML)


def make_large_xml(n: int) -> bytes:
    """Generate a large XML document with n items."""
    items = "\n".join(
        f'  <item id="{i}"><name>Item {i}</name><value>{i * 10}</value></item>'
        for i in range(n)
    )
    return LARGE_XML_TEMPLATE.format(items=items).encode()
