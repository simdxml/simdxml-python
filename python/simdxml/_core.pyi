from collections.abc import Iterator

class Document:
    """A parsed XML document.

    Created by `parse()`. Use `root` to get the root element,
    or query directly with `xpath_text()` and `xpath()`.
    """

    @property
    def root(self) -> Element | None:
        """The root element of the document, or None if empty."""
        ...
    @property
    def tag_count(self) -> int:
        """Total number of XML tags in the document."""
        ...
    def xpath_text(self, expr: str) -> list[str]:
        """Evaluate an XPath expression and return text content of matches.

        Returns the direct child text of each matching element.
        """
        ...
    def xpath_string(self, expr: str) -> list[str]:
        """Evaluate an XPath expression and return string-values of matches.

        Returns all descendant text for each match (XPath ``string()`` semantics).
        """
        ...
    def xpath(self, expr: str) -> list[Element | str]:
        """Evaluate an XPath expression.

        Returns Element objects for element nodes, strings for text/attribute nodes.
        """
        ...

class Element:
    """A read-only XML element.

    Supports the ElementTree API (``.tag``, ``.text``, ``.attrib``, ``.get()``,
    ``len()``, indexing, iteration) plus lxml extensions (``.xpath()``,
    ``.getparent()``, ``.getnext()``, ``.getprevious()``).
    """

    @property
    def tag(self) -> str:
        """The element's tag name (e.g., ``'book'``, ``'title'``)."""
        ...
    @property
    def text(self) -> str | None:
        """Text content before the first child element, or None.

        For ``<p>Hello <b>world</b></p>``, ``p.text`` is ``'Hello '``.
        """
        ...
    @property
    def tail(self) -> str | None:
        """Text content after this element's closing tag, or None.

        For ``<p>Hello <b>world</b> more</p>``, ``b.tail`` is ``' more'``.
        """
        ...
    @property
    def attrib(self) -> dict[str, str]:
        """Dictionary of this element's attributes."""
        ...
    def get(self, key: str, default: str | None = None) -> str | None:
        """Get an attribute value by name, with optional default."""
        ...
    def keys(self) -> list[str]:
        """List of attribute names."""
        ...
    def items(self) -> list[tuple[str, str]]:
        """List of ``(name, value)`` attribute pairs."""
        ...
    def iter(self, tag: str | None = None) -> Iterator[Element]:
        """Iterate over descendant elements, optionally filtered by tag name."""
        ...
    def child_tags(self) -> list[str]:
        """All direct child tag names as a list.

        More efficient than ``[e.tag for e in element]`` for bulk access.
        """
        ...
    def descendant_tags(self, tag: str | None = None) -> list[str]:
        """All descendant tag names, optionally filtered.

        More efficient than ``[e.tag for e in element.iter(tag)]`` for bulk access.
        """
        ...
    def itertext(self) -> list[str]:
        """All text content within this element, depth-first."""
        ...
    def text_content(self) -> str:
        """All descendant text concatenated into a single string."""
        ...
    def xpath(self, expr: str) -> list[Element]:
        """Evaluate an XPath 1.0 expression with this element as context.

        Returns a list of matching Element objects.
        """
        ...
    def xpath_text(self, expr: str) -> list[str]:
        """Evaluate an XPath expression and return text content of matches."""
        ...
    def getparent(self) -> Element | None:
        """Parent element, or None if this is the root."""
        ...
    def getnext(self) -> Element | None:
        """Next sibling element, or None if this is the last child."""
        ...
    def getprevious(self) -> Element | None:
        """Previous sibling element, or None if this is the first child."""
        ...
    def tostring(self) -> str:
        """Serialize this element to an XML string."""
        ...
    def set(self, key: str, value: str) -> None:
        """Not supported. Raises TypeError (elements are read-only)."""
        ...
    def append(self, element: Element) -> None:
        """Not supported. Raises TypeError (elements are read-only)."""
        ...
    def remove(self, element: Element) -> None:
        """Not supported. Raises TypeError (elements are read-only)."""
        ...
    def insert(self, index: int, element: Element) -> None:
        """Not supported. Raises TypeError (elements are read-only)."""
        ...
    def clear(self) -> None:
        """Not supported. Raises TypeError (elements are read-only)."""
        ...
    def __len__(self) -> int:
        """Number of direct child elements."""
        ...
    def __getitem__(self, index: int) -> Element:
        """Get a child element by index. Supports negative indexing."""
        ...
    def __iter__(self) -> Iterator[Element]:
        """Iterate over direct child elements."""
        ...
    def __bool__(self) -> bool: ...
    def __eq__(self, other: object) -> bool: ...
    def __hash__(self) -> int: ...

class CompiledXPath:
    """A compiled XPath expression for repeated use.

    Like ``re.compile()`` — parse the expression once, evaluate many times
    across different documents.
    """

    def eval_text(self, doc: Document) -> list[str]:
        """Evaluate and return text content of matching nodes."""
        ...
    def eval(self, doc: Document) -> list[Element]:
        """Evaluate and return matching Element objects."""
        ...
    def eval_exists(self, doc: Document) -> bool:
        """Check whether any nodes match the expression."""
        ...
    def eval_count(self, doc: Document) -> int:
        """Count the number of matching nodes."""
        ...

def parse(data: bytes | str) -> Document:
    """Parse XML into a Document.

    Accepts ``bytes`` or ``str``. For bytes input, the buffer is used
    directly (zero-copy). For str input, the string is encoded to UTF-8.
    """
    ...

def compile(expr: str) -> CompiledXPath:
    """Compile an XPath expression for repeated use.

    Like ``re.compile()`` — parse the expression once, evaluate many times
    across different documents.
    """
    ...
