# simdxml

SIMD-accelerated XML parser with full XPath 1.0 support for Python.

`simdxml` parses XML into flat arrays instead of a DOM tree, then evaluates
XPath expressions against those arrays. The approach adapts
[simdjson](https://simdjson.org/)'s structural indexing architecture to XML:
SIMD instructions classify structural characters in parallel, producing a
compact index that supports all 13 XPath 1.0 axes via array operations.

## Installation

```bash
pip install simdxml
```

Pre-built wheels for Linux (x86_64, aarch64), macOS (arm64, x86_64), and Windows.

## Quick start

```python
import simdxml

doc = simdxml.parse(b"<library><book><title>Rust</title></book></library>")
titles = doc.xpath_text("//title")
assert titles == ["Rust"]
```

## API

### Native API

The native API gives you direct access to the SIMD-accelerated engine:

```python
import simdxml

# Parse bytes or str
doc = simdxml.parse(xml_bytes)

# XPath queries
doc.xpath_text("//title")          # -> list[str] (direct child text)
doc.xpath_string("//title")        # -> list[str] (all descendant text, like XPath string())
doc.xpath("//book[@lang='en']")    # -> list[Element | str]

# Element traversal
root = doc.root
root.tag                           # "library"
root.text                          # direct text content or None
root.attrib                        # {"lang": "en", ...}
root.get("lang")                   # "en"
root[0]                            # first child element
len(root)                          # number of child elements
list(root)                         # all child elements

# Navigation (lxml-compatible)
elem.getparent()                   # parent element or None
elem.getnext()                     # next sibling or None
elem.getprevious()                 # previous sibling or None

# XPath from any element
elem.xpath(".//title")             # context-node evaluation
elem.xpath_text("author")         # text extraction from context

# Compiled XPath (like re.compile)
expr = simdxml.compile("//title")
expr.eval_text(doc)                # -> list[str]
expr.eval_count(doc)               # -> int
expr.eval_exists(doc)              # -> bool
expr.eval(doc)                     # -> list[Element]
```

### ElementTree compatibility

Drop-in replacement for `xml.etree.ElementTree` (read-only):

```python
from simdxml.etree import ElementTree as ET

tree = ET.parse("books.xml")
root = tree.getroot()

# stdlib-compatible API
root.tag                           # element tag name
root.text                          # direct text content
root.attrib                        # attribute dict
root.get("key")                    # attribute access
root.iter("title")                 # descendant iterator
root.itertext()                    # text iterator

# Full XPath 1.0 (lxml-compatible extension)
root.xpath("//book[contains(title, 'XML')]")
```

### Read-only by design

simdxml Elements are immutable views into the structural index. Mutation
operations raise `TypeError` with a helpful message:

```python
root.text = "new"  # TypeError: simdxml Elements are read-only.
                    #   Use xml.etree.ElementTree for XML construction.
```

## XPath 1.0 support

Full conformance with XPath 1.0:

- **327/327** libxml2 conformance tests (100%)
- **1015/1023** pugixml conformance tests (99.2%)
- All 13 axes: `child`, `descendant`, `parent`, `ancestor`, `following-sibling`,
  `preceding-sibling`, `following`, `preceding`, `self`, `attribute`, `namespace`,
  `descendant-or-self`, `ancestor-or-self`
- All 25 functions: `string()`, `contains()`, `count()`, `position()`, `last()`,
  `starts-with()`, `substring()`, `concat()`, `normalize-space()`, etc.
- Operators: `and`, `or`, `=`, `!=`, `<`, `>`, `+`, `-`, `*`, `div`, `mod`, `|`
- Predicates: positional `[1]`, `[last()]`, boolean `[@attr='val']`, nested

## Benchmarks

Measured on Apple Silicon (M-series), Python 3.14, comparing against
lxml 6.0 and stdlib `xml.etree.ElementTree`. Run with `uv run python bench/bench_parse.py`.

### Parse throughput

| Document | simdxml | lxml | stdlib ET | vs lxml | vs stdlib |
|----------|---------|------|-----------|---------|-----------|
| 20 KB (100 items) | 0.05 ms | 0.09 ms | 0.15 ms | 1.8x | 3.0x |
| 2 MB (10K items) | 3.3 ms | 8.5 ms | 16.7 ms | 2.6x | 5.0x |
| 20 MB (100K items) | 40 ms | 87 ms | 181 ms | **2.2x** | **4.5x** |

### XPath query: `//name`

| Document | simdxml | lxml | stdlib findall | vs lxml | vs stdlib |
|----------|---------|------|----------------|---------|-----------|
| 2 MB | 0.3 ms | 1.0 ms | 0.7 ms | 3.1x | 2.1x |
| 20 MB | 3.8 ms | 19.7 ms | 7.3 ms | **5.2x** | **1.9x** |

### XPath query with predicate: `//item[@category="cat5"]`

| Document | simdxml | lxml | stdlib findall | vs lxml |
|----------|---------|------|----------------|---------|
| 2 MB | 0.2 ms | 2.8 ms | 0.8 ms | 16x |
| 20 MB | 2.0 ms | 46 ms | 9.1 ms | **23x** |

The predicate speedup is dramatic because simdxml's structural index enables
direct attribute comparison without materializing DOM nodes.

## How it works

Instead of building a DOM tree with heap-allocated nodes and pointer-chasing,
simdxml represents XML structure as parallel arrays (struct-of-arrays layout).
Each tag gets an entry in flat arrays for starts, ends, types, names, depths,
and parents -- all indexed by the same position.

- ~16 bytes per tag vs ~35 bytes per DOM node
- O(1) ancestor/descendant checks via pre/post-order numbering
- O(1) child enumeration via CSR (Compressed Sparse Row) indices
- SIMD-accelerated structural parsing (NEON on ARM, AVX2 on x86)
- Lazy index building: CSR indices built on first query, not at parse time

## Platform support

| Platform | SIMD Backend | Status |
|----------|-------------|--------|
| aarch64 (Apple Silicon, ARM) | NEON 128-bit | Production |
| x86_64 | AVX2 256-bit / SSE4.2 | Production |
| Other | Scalar (memchr-accelerated) | Working |

## Development

```bash
git clone https://github.com/simdxml/simdxml-python
cd simdxml-python

make dev        # build extension (debug mode)
make test       # run tests
make lint       # ruff check + format
make typecheck  # pyright
```

Requires Rust toolchain and Python 3.9+.

## License

MIT OR Apache-2.0 (same as the simdxml Rust crate)
