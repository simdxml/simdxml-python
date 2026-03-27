"""SIMD-accelerated XML parser with full XPath 1.0 support.

A drop-in replacement for xml.etree.ElementTree with the performance of
SIMD-accelerated structural indexing. Inspired by simdjson's approach of
matching the stdlib API while providing a native power-user API.

Quick start::

    import simdxml

    doc = simdxml.parse(b"<library><book><title>Rust</title></book></library>")
    titles = doc.xpath_text("//title")
    assert titles == ["Rust"]

    # Compiled queries for batch use
    expr = simdxml.compile("//title")
    assert expr.eval_text(doc) == ["Rust"]

    # Element traversal
    root = doc.root
    for child in root:
        print(child.tag)

For ElementTree compatibility::

    from simdxml.etree import ElementTree as ET

    tree = ET.parse("books.xml")
    root = tree.getroot()
    root.findall(".//title")
"""

from simdxml._core import (
    CompiledXPath,
    Document,
    Element,
    ElementList,
    compile,
    parse,
)

__all__ = [
    "CompiledXPath",
    "Document",
    "Element",
    "ElementList",
    "compile",
    "parse",
]

__version__ = "0.2.0"
