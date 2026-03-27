"""ElementTree compatibility layer.

Usage::

    from simdxml.etree import ElementTree as ET

    tree = ET.parse("books.xml")
    root = tree.getroot()
"""

from simdxml.etree import ElementTree

__all__ = ["ElementTree"]
