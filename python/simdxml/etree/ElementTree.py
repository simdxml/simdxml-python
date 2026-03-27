"""Drop-in replacement for xml.etree.ElementTree (read-only).

Provides the same read-only API as xml.etree.ElementTree for parsing and
querying XML, backed by simdxml's SIMD-accelerated structural index.

Usage::

    from simdxml.etree import ElementTree as ET

    tree = ET.parse("books.xml")
    root = tree.getroot()
    titles = root.findall(".//title")

Note: simdxml Elements are read-only. Mutation operations (append, remove,
set, text assignment, SubElement, etc.) raise TypeError.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator, Iterator
from typing import IO, TextIO

import simdxml._core as _core

# Re-export Element for isinstance checks and type annotations
Element = _core.Element
ElementList = _core.ElementList

VERSION = "0.3.0"


class ParseError(SyntaxError):
    """Exception for XML parse errors (compatibility with stdlib)."""


class QName:
    """Qualified name wrapper ({namespace}localname).

    Compatible with xml.etree.ElementTree.QName.
    """

    def __init__(
        self,
        text_or_uri: str | Element,
        tag: str | None = None,
    ) -> None:
        if tag is not None:
            # QName(uri, tag) form
            self.text = f"{{{text_or_uri}}}{tag}"
        elif isinstance(text_or_uri, str):
            self.text = text_or_uri
        else:
            self.text = text_or_uri.tag

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f"QName({self.text!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, QName):
            return self.text == other.text
        if isinstance(other, str):
            return self.text == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)


# ---------------------------------------------------------------------------
# ElementTree
# ---------------------------------------------------------------------------


class ElementTree:
    """An XML element hierarchy backed by simdxml (read-only)."""

    def __init__(
        self,
        element: Element | None = None,
        file: str | os.PathLike[str] | IO[bytes] | None = None,
    ) -> None:
        if file is not None:
            if not isinstance(file, (str, os.PathLike)):
                data: bytes = file.read()
            else:
                from pathlib import Path

                with Path(file).open("rb") as f:
                    data = f.read()
            self._doc = _core.parse(data)
            self._root = self._doc.root
        elif element is not None:
            self._root = element
            self._doc = None  # type: ignore[assignment]
        else:
            self._root = None  # type: ignore[assignment]
            self._doc = None  # type: ignore[assignment]

    def getroot(self) -> Element:
        """Return the root element."""
        if self._root is None:
            msg = "ElementTree has no root element"
            raise ValueError(msg)
        return self._root

    def find(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> Element | None:
        """Find first matching element by path."""
        return self.getroot().find(path, namespaces)

    def findall(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> ElementList:
        """Find all matching elements by path."""
        return self.getroot().findall(path, namespaces)

    def findtext(
        self,
        path: str,
        default: str | None = None,
        namespaces: dict[str, str] | None = None,
    ) -> str | None:
        """Find text of first matching element."""
        return self.getroot().findtext(path, default, namespaces)

    def iterfind(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> Iterator[Element]:
        """Iterate over matching elements."""
        return self.getroot().iterfind(path, namespaces)

    def iter(self, tag: str | None = None) -> Iterator[Element]:
        """Iterate over all elements in the tree."""
        return self.getroot().iter(tag)

    def write(self, *_args: object, **_kwargs: object) -> None:
        """Not supported (read-only)."""
        msg = "simdxml ElementTree is read-only"
        raise TypeError(msg)


# ---------------------------------------------------------------------------
# Module-level functions matching xml.etree.ElementTree
# ---------------------------------------------------------------------------


def parse(
    source: str | os.PathLike[str] | IO[bytes],
    parser: XMLParser | None = None,
) -> ElementTree:
    """Parse an XML file into an ElementTree.

    The ``parser`` argument is accepted for API compatibility but
    simdxml always uses its native SIMD parser.
    """
    return ElementTree(file=source)


def fromstring(text: str | bytes) -> Element:
    """Parse XML from a string, return root Element."""
    doc = _core.parse(text)
    root = doc.root
    if root is None:
        msg = "no root element found"
        raise ValueError(msg)
    return root


XML = fromstring


def XMLID(text: str | bytes) -> tuple[Element, dict[str, Element]]:
    """Parse XML, return (root, id_map).

    The id_map maps "id" attribute values to their elements.
    """
    root = fromstring(text)
    ids: dict[str, Element] = {}
    for elem in root.iter():
        id_val = elem.get("id")
        if id_val is not None:
            ids[id_val] = elem
    return root, ids


def fromstringlist(sequence: list[str | bytes], parser: object = None) -> Element:
    """Parse XML from a sequence of strings."""
    text = b"".join(s.encode() if isinstance(s, str) else s for s in sequence)
    return fromstring(text)


def tostring(
    element: Element,
    encoding: str | None = None,
    method: str | None = None,
    *,
    short_empty_elements: bool = True,
    xml_declaration: bool | None = None,
) -> bytes | str:
    """Serialize an Element to XML.

    Returns bytes by default, or str if encoding="unicode".
    Note: ``method``, ``short_empty_elements``, and ``xml_declaration``
    are accepted for signature compatibility but not yet implemented.
    """
    raw = element.tostring()
    if encoding == "unicode":
        return raw
    enc = encoding or "us-ascii"
    return raw.encode(enc)


def tostringlist(
    element: Element,
    encoding: str | None = None,
    method: str | None = None,
    *,
    short_empty_elements: bool = True,
    xml_declaration: bool | None = None,
) -> list[bytes | str]:
    """Serialize an Element to a list of strings."""
    return [tostring(element, encoding, method)]


def dump(elem: Element | ElementTree) -> None:
    """Write element tree or element to sys.stdout."""
    if isinstance(elem, ElementTree):
        elem = elem.getroot()
    sys.stdout.write(elem.tostring())
    sys.stdout.write("\n")


def iselement(element: object) -> bool:
    """Check if an object is an Element."""
    return isinstance(element, _core.Element)


# ---------------------------------------------------------------------------
# iterparse
# ---------------------------------------------------------------------------


def iterparse(
    source: str | os.PathLike[str] | IO[bytes],
    events: tuple[str, ...] | list[str] | None = None,
    parser: object = None,
) -> Generator[tuple[str, Element], None, None]:
    """Incrementally parse XML, yielding (event, element) pairs.

    Parses the entire document first (using SIMD acceleration), then
    walks the structural index to yield events in document order.

    Supported events: 'start', 'end', 'start-ns', 'end-ns'.
    Default is ('end',) matching stdlib behavior.
    """
    if events is None:
        events = ("end",)
    event_set = set(events)

    # Read the source
    if not isinstance(source, (str, os.PathLike)):
        data: bytes = source.read()
    else:
        from pathlib import Path

        with Path(source).open("rb") as f:
            data = f.read()

    doc = _core.parse(data)
    root = doc.root
    if root is None:
        return

    yield from _walk_events(root, event_set)


def _walk_events(
    element: Element, events: set[str]
) -> Generator[tuple[str, Element], None, None]:
    """Walk element tree yielding events in document order."""
    if "start" in events:
        yield ("start", element)
    for child in element:
        yield from _walk_events(child, events)
    if "end" in events:
        yield ("end", element)


# ---------------------------------------------------------------------------
# XMLPullParser
# ---------------------------------------------------------------------------


class XMLPullParser:
    """Feed-based XML parser that yields events incrementally.

    Buffers all fed data, parses on close() or when events are read.
    """

    def __init__(
        self,
        events: tuple[str, ...] | list[str] | None = None,
        *,
        _parser: object = None,
    ) -> None:
        self._events = set(events) if events else {"end"}
        self._buffer: list[bytes] = []
        self._pending: list[tuple[str, Element]] = []
        self._parsed = False

    def feed(self, data: bytes | str) -> None:
        """Feed XML data to the parser."""
        if isinstance(data, str):
            data = data.encode()
        self._buffer.append(data)
        self._parsed = False

    def _ensure_parsed(self) -> None:
        if self._parsed:
            return
        if not self._buffer:
            return
        xml = b"".join(self._buffer)
        try:
            doc = _core.parse(xml)
            root = doc.root
            if root is not None:
                self._pending.extend(_walk_events(root, self._events))
            self._parsed = True
        except ValueError:
            # Incomplete XML — wait for more data
            pass

    def read_events(self) -> Generator[tuple[str, Element], None, None]:
        """Yield pending (event, element) pairs."""
        self._ensure_parsed()
        events = self._pending
        self._pending = []
        yield from events

    def flush(self) -> None:
        """Flush any pending data (no-op, included for compatibility)."""

    def close(self) -> None:
        """Finalize parsing. Raises ParseError if XML is malformed."""
        if not self._parsed and self._buffer:
            xml = b"".join(self._buffer)
            try:
                doc = _core.parse(xml)
                root = doc.root
                if root is not None:
                    self._pending.extend(_walk_events(root, self._events))
                self._parsed = True
            except ValueError as e:
                raise ParseError(str(e)) from e
        else:
            self._ensure_parsed()


# ---------------------------------------------------------------------------
# canonicalize
# ---------------------------------------------------------------------------


def canonicalize(
    xml_data: str | bytes | None = None,
    *,
    out: TextIO | None = None,
    from_file: str | os.PathLike[str] | IO[bytes] | None = None,
    with_comments: bool = False,
    strip_text: bool = False,
    rewrite_prefixes: bool = False,
    qname_aware_tags: set[str] | None = None,
    qname_aware_attrs: set[str] | None = None,
    exclude_attrs: set[str] | None = None,
    exclude_tags: set[str] | None = None,
) -> str | None:
    """Generate C14N canonical XML.

    Attributes are sorted lexicographically. Empty elements are expanded
    to start/end tag pairs.
    """
    import warnings

    unsupported = []
    if with_comments:
        unsupported.append("with_comments")
    if rewrite_prefixes:
        unsupported.append("rewrite_prefixes")
    if qname_aware_tags is not None:
        unsupported.append("qname_aware_tags")
    if qname_aware_attrs is not None:
        unsupported.append("qname_aware_attrs")
    if unsupported:
        warnings.warn(
            "simdxml.canonicalize: "
            f"{', '.join(unsupported)} not yet implemented, ignored",
            stacklevel=2,
        )
    # Parse the input
    if xml_data is not None:
        if isinstance(xml_data, str):
            xml_data = xml_data.encode()
        doc = _core.parse(xml_data)
    elif from_file is not None:
        if not isinstance(from_file, (str, os.PathLike)):
            data = from_file.read()
        else:
            from pathlib import Path

            with Path(from_file).open("rb") as f:
                data = f.read()
        doc = _core.parse(data)
    else:
        msg = "either xml_data or from_file must be provided"
        raise ValueError(msg)

    root = doc.root
    if root is None:
        result = ""
    elif not strip_text and not exclude_attrs and not exclude_tags:
        # Note: Rust c14n doesn't decode entities before re-escaping yet,
        # so we use the Python path which goes through parsed .text/.tail
        # (already entity-decoded by simdxml).
        result = _c14n_element(root)
    else:
        result = _c14n_element(
            root,
            strip_text=strip_text,
            exclude_attrs=exclude_attrs,
            exclude_tags=exclude_tags,
        )

    if out is not None:
        out.write(result)
        return None
    return result


def _c14n_element(
    elem: Element,
    *,
    strip_text: bool = False,
    exclude_attrs: set[str] | None = None,
    exclude_tags: set[str] | None = None,
) -> str:
    """Serialize one element in C14N form."""
    tag = elem.tag

    if exclude_tags and tag in exclude_tags:
        return ""

    # Sorted attributes
    attrs = elem.items()
    if exclude_attrs:
        attrs = [(k, v) for k, v in attrs if k not in exclude_attrs]
    attrs.sort()
    attr_str = "".join(f' {k}="{_escape_attr(v)}"' for k, v in attrs)

    # Children + text
    children_parts: list[str] = []

    # .text
    text = elem.text
    if text is not None:
        if strip_text:
            text = text.strip()
        if text:
            children_parts.append(_escape_text(text))

    # Child elements + tail
    for child in elem:
        children_parts.append(
            _c14n_element(
                child,
                strip_text=strip_text,
                exclude_attrs=exclude_attrs,
                exclude_tags=exclude_tags,
            )
        )
        tail = child.tail
        if tail is not None:
            if strip_text:
                tail = tail.strip()
            if tail:
                children_parts.append(_escape_text(tail))

    inner = "".join(children_parts)

    # C14N always uses expanded form (no self-closing)
    return f"<{tag}{attr_str}>{inner}</{tag}>"


def _escape_text(text: str) -> str:
    """Escape text content for C14N."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", "&#xD;")
    )


def _escape_attr(text: str) -> str:
    """Escape attribute values for C14N."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace('"', "&quot;")
        .replace("\t", "&#x9;")
        .replace("\n", "&#xA;")
        .replace("\r", "&#xD;")
    )


# ---------------------------------------------------------------------------
# TreeBuilder + XMLParser
# ---------------------------------------------------------------------------


class TreeBuilder:
    """SAX-like target for building element trees.

    Since simdxml is read-only, this is a compatibility stub that
    delegates to stdlib's TreeBuilder internally, then wraps the
    result through simdxml.parse().
    """

    def __init__(
        self,
        element_factory: object = None,
        *,
        comment_factory: object = None,
        pi_factory: object = None,
        insert_comments: bool = False,
        insert_pis: bool = False,
    ) -> None:
        self._data: list[str] = []
        self._result: Element | None = None

    def start(self, tag: str, attrs: dict[str, str]) -> Element:  # type: ignore[return-value]
        """Handle opening tag."""
        attr_str = "".join(f' {k}="{_escape_attr(v)}"' for k, v in attrs.items())
        self._data.append(f"<{tag}{attr_str}>")
        return None  # type: ignore[return-value]

    def end(self, tag: str) -> Element:  # type: ignore[return-value]
        """Handle closing tag."""
        self._data.append(f"</{tag}>")
        return None  # type: ignore[return-value]

    def data(self, data: str) -> None:
        """Handle text content."""
        self._data.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def comment(self, text: str) -> None:
        """Handle comment."""
        self._data.append(f"<!--{text}-->")

    def pi(self, target: str, text: str | None = None) -> None:
        """Handle processing instruction."""
        if text:
            self._data.append(f"<?{target} {text}?>")
        else:
            self._data.append(f"<?{target}?>")

    def close(self) -> Element:
        """Finalize and return root element."""
        xml = "".join(self._data)
        if not xml:
            msg = "no elements"
            raise ValueError(msg)
        self._result = fromstring(xml)
        return self._result


class XMLParser:
    """XML parser wrapping simdxml.

    Accepts feed() calls, parses on close(). Compatible with
    ``ET.parse(source, parser=XMLParser())``.

    Note: Custom ``target`` objects are accepted for API compatibility
    but their callbacks are not invoked. The parsing always uses
    simdxml's native parser.
    """

    def __init__(
        self,
        *,
        target: TreeBuilder | None = None,
        encoding: str | None = None,
    ) -> None:
        self.target = target or TreeBuilder()
        self._buffer: list[bytes] = []
        self.entity: dict[str, str] = {}
        self.version = "1.0"

    def feed(self, data: bytes | str) -> None:
        """Feed data to the parser."""
        if isinstance(data, str):
            data = data.encode()
        self._buffer.append(data)

    def flush(self) -> None:
        """Flush parser buffers (no-op)."""

    def close(self) -> Element:
        """Finalize parsing, return root element."""
        xml = b"".join(self._buffer)
        return fromstring(xml)


# ---------------------------------------------------------------------------
# Read-only stubs for construction APIs
# ---------------------------------------------------------------------------

_READONLY_MSG = "simdxml is read-only. Use xml.etree.ElementTree for XML construction."


def SubElement(
    parent: Element,
    tag: str,
    attrib: dict[str, str] | None = None,
    **extra: str,
) -> Element:
    """Not supported (read-only). Raises TypeError."""
    raise TypeError(_READONLY_MSG)


def Comment(text: str | None = None) -> Element:
    """Not supported (read-only). Raises TypeError."""
    raise TypeError(_READONLY_MSG)


def ProcessingInstruction(target: str, text: str | None = None) -> Element:
    """Not supported (read-only). Raises TypeError."""
    raise TypeError(_READONLY_MSG)


PI = ProcessingInstruction


def indent(
    tree: Element | ElementTree,
    space: str = "  ",
    level: int = 0,
) -> None:
    """Not supported (read-only, modifies tree). Raises TypeError."""
    raise TypeError(_READONLY_MSG)


# Namespace registry (no-op for compatibility)
_namespace_map: dict[str, str] = {}


def register_namespace(prefix: str, uri: str) -> None:
    """Register a namespace prefix (stored but not used for queries)."""
    _namespace_map[prefix] = uri
