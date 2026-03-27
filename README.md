# simdxml

[![PyPI](https://img.shields.io/pypi/v/simdxml)](https://pypi.org/project/simdxml/)
[![CI](https://github.com/simdxml/simdxml-python/actions/workflows/ci.yml/badge.svg)](https://github.com/simdxml/simdxml-python/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/simdxml)](https://pypi.org/project/simdxml/)
[![License](https://img.shields.io/pypi/l/simdxml)](https://github.com/simdxml/simdxml-python/blob/main/LICENSE)

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

# Batch: process many documents in one call
docs = [open(f).read() for f in xml_files]
expr = simdxml.compile("//title")
simdxml.batch_xpath_text(docs, expr)           # bloom prefilter
simdxml.batch_xpath_text_parallel(docs, expr)  # multithreaded
```

### ElementTree drop-in (read-only)

Full read-only drop-in replacement for `xml.etree.ElementTree`. Every
read-only Element method and module function is supported:

```python
from simdxml.etree import ElementTree as ET

tree = ET.parse("books.xml")
root = tree.getroot()

# All stdlib Element methods work
root.tag, root.text, root.tail, root.attrib
root.find(".//title")              # first match
root.findall(".//book[@lang]")     # all matches
root.findtext(".//title")          # text of first match
root.iterfind(".//author")         # iterator
root.iter("title")                 # descendant iterator
root.itertext()                    # text iterator
root.get("key"), root.keys(), root.items()
len(root), root[0], list(root)

# All stdlib module functions work
ET.parse(file), ET.fromstring(text), ET.tostring(element)
ET.iterparse(file, events=("start", "end"))
ET.canonicalize(xml), ET.dump(element), ET.iselement(obj)
ET.XMLPullParser(events=("end",)), ET.XMLParser(), ET.TreeBuilder()
ET.fromstringlist(seq), ET.tostringlist(elem)
ET.QName(uri, tag), ET.XMLID(text)

# Plus full XPath 1.0 (lxml-compatible extension)
root.xpath("//book[contains(title, 'XML')]")
```

Mutation operations (`append`, `remove`, `set`, `SubElement`, `indent`, etc.)
raise `TypeError` with a helpful message pointing to stdlib.

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

Apple Silicon, Python 3.14, lxml 6.0. GC disabled, 3 warmup + 20 timed
iterations, median reported. 100K-element catalog (5.6 MB).
Run yourself: `uv run python bench/bench_parse.py`

Faster than lxml on every operation. Faster than stdlib on 11 of 14.

| Operation | simdxml | lxml | stdlib | vs lxml | vs stdlib |
|-----------|---------|------|--------|---------|-----------|
| `parse()` | 10 ms | 33 ms | 55 ms | **3x** | **5x** |
| `find("item")` | <1 us | 1 us | <1 us | **faster** | **tied** |
| `find(".//name")` | <1 us | 1 us | 1 us | **faster** | **faster** |
| `findall("item")` | 0.23 ms | 4.8 ms | 0.89 ms | **21x** | **4x** |
| `findall(".//item")` | 0.15 ms | 6.2 ms | 3.0 ms | **42x** | **20x** |
| `findall(predicate)` | 1.5 ms | 12 ms | 4.9 ms | **8x** | **3x** |
| `findtext(".//name")` | <1 us | 1 us | 1 us | **faster** | **faster** |
| `xpath_text("//name")` | 2.1 ms | 19 ms | 4.4 ms | **9x** | **2x** |
| `iter()` | 9.2 ms | 15 ms | 1.3 ms | **2x** | 0.14x |
| `iter("item")` filtered | 4.5 ms | 5.9 ms | 1.9 ms | **1.3x** | 0.4x |
| `itertext()` | 2.6 ms | 33 ms | 1.4 ms | **13x** | 0.5x |
| `child_tags()` | 0.40 ms | 6.2 ms | 1.5 ms | **16x** | **4x** |
| `iterparse()` | 51 ms | 66 ms | 70 ms | **1.3x** | **1.4x** |
| `canonicalize()` | 1.8 ms | 4.7 ms | 4.6 ms | **3x** | **3x** |

The three operations where stdlib is faster (`iter`, `itertext`, `iter` filtered)
involve creating per-element Python objects. The batch alternatives
(`child_tags()`, `xpath_text()`) beat both lxml and stdlib for those workloads.

### Batch processing (multiple documents)

`batch_xpath_text` uses a bloom filter to skip non-matching documents at
~10 GiB/s. `batch_xpath_text_parallel` spreads parse + eval across threads.
Both return all results in a single FFI call — zero per-document Python overhead.

| Workload | Python loop | bloom batch | parallel batch |
|----------|-------------|-------------|----------------|
| 1K small docs | 1.1 ms | **0.37 ms** (3x) | 12 ms |
| 100x 31KB docs | 7.9 ms | 8.2 ms | **2.6 ms** (3x) |

Use bloom batch when many documents won't match the query (ETL filtering).
Use parallel batch when documents are large (>10KB) and most will match.

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
