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

# Batch APIs (single FFI call, interned strings)
root.child_tags()                  # -> list[str] of child tag names
root.descendant_tags("item")       # -> list[str] filtered by tag

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

Apple Silicon, Python 3.14, lxml 6.0. GC disabled during timing, 3 warmup +
20 timed iterations, median reported. Three corpus types: data-oriented
(product catalog), document-oriented (PubMed abstracts), config-oriented
(Maven POM). Run yourself: `uv run python bench/bench_parse.py`

### Parse

`simdxml.parse()` eagerly builds structural indices (CSR, name posting).
lxml's `fromstring()` builds a DOM tree without precomputed query indices.
simdxml front-loads more work into parse so queries are faster — both numbers
are real, the trade-off depends on your workload.

| Corpus | Size | simdxml | lxml | vs lxml | vs stdlib |
|--------|------|---------|------|---------|-----------|
| Catalog (data) | 1.6 MB | 2.7 ms | 8.1 ms | **3.0x** | **5.4x** |
| Catalog (data) | 17 MB | 32 ms | 82 ms | **2.6x** | **4.7x** |
| PubMed (doc) | 1.7 MB | 2.3 ms | 6.0 ms | **2.7x** | **5.9x** |
| PubMed (doc) | 17 MB | 27 ms | 61 ms | **2.2x** | **5.0x** |
| POM (config) | 2.1 MB | 2.7 ms | 8.3 ms | **3.1x** | **6.6x** |

### XPath queries (returning Elements — apples-to-apples)

| Query | Corpus | simdxml | lxml | vs lxml |
|-------|--------|---------|------|---------|
| `//item` | Catalog 17 MB | 3.4 ms | 21 ms | **6x** |
| `//item[@category="cat5"]` | Catalog 17 MB | 1.6 ms | 69 ms | **42x** |
| `//PubmedArticle` | PubMed 17 MB | 0.35 ms | 9.8 ms | **28x** |
| `//Author[LastName="Auth0_0"]` | PubMed 17 MB | 13 ms | 29 ms | **2.2x** |
| `//dependency` | POM 2.1 MB | 0.34 ms | 1.1 ms | **3.3x** |
| `//dependency[scope="test"]` | POM 2.1 MB | 2.4 ms | 3.6 ms | **1.5x** |

### XPath text extraction

`xpath_text()` returns strings directly, avoiding Element object creation.
This is the optimized path for ETL / data extraction workloads.

| Query | Corpus | simdxml | lxml xpath+.text | vs lxml |
|-------|--------|---------|------------------|---------|
| `//name` | Catalog 17 MB | 1.8 ms | 37 ms | **20x** |
| `//AbstractText` | PubMed 17 MB | 0.31 ms | 7.1 ms | **23x** |
| `//artifactId` | POM 2.1 MB | 0.21 ms | 2.0 ms | **10x** |

### Element traversal

`child_tags()` and `descendant_tags()` return all tag names in a single
call using interned Python strings. Per-element iteration (`for e in root`)
is also available but creates Element objects with some overhead.

| Corpus | `child_tags()` | lxml `[e.tag]` | vs lxml |
|--------|----------------|-----------------|---------|
| Catalog 17 MB | **0.38 ms** | 6.4 ms | **17x** |
| PubMed 17 MB | **0.03 ms** | 0.60 ms | **17x** |
| POM 2.1 MB | **0.2 us** | 0.5 us | **3x** |

## How it works

Instead of building a DOM tree with heap-allocated nodes and pointer-chasing,
simdxml represents XML structure as parallel arrays (struct-of-arrays layout).
Each tag gets an entry in flat arrays for starts, ends, types, names, depths,
and parents -- all indexed by the same position.

- ~16 bytes per tag vs ~35 bytes per DOM node
- O(1) ancestor/descendant checks via pre/post-order numbering
- O(1) child enumeration via CSR (Compressed Sparse Row) indices
- SIMD-accelerated structural parsing (NEON on ARM, AVX2 on x86)
- Parse eagerly builds all indices (CSR, name posting, parent map) so
  subsequent queries pay zero index construction cost

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
