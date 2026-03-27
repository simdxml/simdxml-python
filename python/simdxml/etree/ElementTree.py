"""Drop-in replacement for xml.etree.ElementTree (read-only).

Provides the same API as xml.etree.ElementTree for parsing and querying XML,
backed by simdxml's SIMD-accelerated structural index.

Usage::

    from simdxml.etree import ElementTree as ET

    tree = ET.parse("books.xml")
    root = tree.getroot()
    titles = root.findall(".//title")

Note: simdxml Elements are read-only. Mutation operations (append, remove,
set, text assignment) raise TypeError.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import IO

import simdxml._core as _core

# Re-export Element and Document
Element = _core.Element


class ElementTree:
    """An XML element hierarchy backed by simdxml.

    This is a read-only wrapper matching the stdlib ElementTree API.
    """

    def __init__(
        self,
        element: Element | None = None,
        file: str | os.PathLike[str] | IO[bytes] | None = None,
    ) -> None:
        if file is not None:
            if not isinstance(file, (str, os.PathLike)):
                # File-like object
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
            raise ValueError("ElementTree has no root element")
        return self._root

    def find(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> Element | None:
        """Find first matching element by path."""
        root = self.getroot()
        return _find(root, path, namespaces)

    def findall(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> list[Element]:
        """Find all matching elements by path."""
        root = self.getroot()
        return _findall(root, path, namespaces)

    def iterfind(
        self, path: str, namespaces: dict[str, str] | None = None
    ) -> Iterator[Element]:
        """Iterate over matching elements."""
        return iter(self.findall(path, namespaces))


def parse(
    source: str | os.PathLike[str] | IO[bytes],
) -> ElementTree:
    """Parse an XML file into an ElementTree."""
    return ElementTree(file=source)


def fromstring(text: str | bytes) -> Element:
    """Parse XML from a string, return root Element."""
    doc = _core.parse(text)
    root = doc.root
    if root is None:
        raise ValueError("no root element found")
    return root


def tostring(
    element: Element,
    encoding: str | None = None,
    method: str | None = None,
) -> bytes | str:
    """Serialize an Element to XML.

    Returns bytes by default, or str if encoding="unicode".
    """
    raw = element.tostring()
    if encoding == "unicode":
        return raw
    enc = encoding or "us-ascii"
    return raw.encode(enc)


# ---------------------------------------------------------------------------
# ET path → XPath translation for find/findall
# ---------------------------------------------------------------------------


def _path_to_xpath(path: str) -> str:
    """Convert ET path syntax to XPath.

    ET paths are a subset of XPath with some differences:
    - {ns}tag → namespace handling (we pass through as-is for now)
    - .  → self
    - .. → parent
    - // → descendant-or-self
    - * → wildcard
    - [tag] → child element predicate
    - [@attrib] → attribute exists
    - [tag='text'] → child text match
    - [@attrib='value'] → attribute value match
    """
    # If it already looks like XPath, pass through
    if path.startswith("/") or path.startswith("("):
        return path

    # Ensure relative paths start with ./ for XPath context
    if not path.startswith("."):
        path = "./" + path

    return path


def _find(
    element: Element,
    path: str,
    namespaces: dict[str, str] | None = None,
) -> Element | None:
    """Find first matching subelement."""
    xpath = _path_to_xpath(path)
    try:
        results = element.xpath(xpath)
        return results[0] if results else None
    except ValueError:
        return None


def _findall(
    element: Element,
    path: str,
    namespaces: dict[str, str] | None = None,
) -> list[Element]:
    """Find all matching subelements."""
    xpath = _path_to_xpath(path)
    try:
        return element.xpath(xpath)
    except ValueError:
        return []
