"""Benchmark: simdxml vs lxml vs stdlib xml.etree.ElementTree.

Usage:
    uv run python bench/bench_parse.py
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as StdET

import simdxml

try:
    from lxml import etree as lxml_etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False


def generate_xml(n_items: int) -> bytes:
    """Generate a catalog XML with n_items."""
    items = "\n".join(
        f'  <item id="{i}" category="cat{i % 10}">'
        f"<name>Item {i}</name>"
        f"<description>Description for item {i} with some text content</description>"
        f"<price>{i * 1.5:.2f}</price>"
        f"<tags><tag>tag{i % 5}</tag><tag>tag{i % 3}</tag></tags>"
        f"</item>"
        for i in range(n_items)
    )
    return f"<catalog>\n{items}\n</catalog>".encode()


def bench(label: str, fn, iterations: int = 10) -> float:
    """Run fn `iterations` times, return median time in ms."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    times.sort()
    median = times[len(times) // 2]
    return median


def print_row(label: str, time_ms: float, baseline_ms: float | None = None) -> None:
    speedup = ""
    if baseline_ms is not None and time_ms > 0:
        ratio = baseline_ms / time_ms
        lib = "lxml" if HAS_LXML else "stdlib"
        speedup = f"  ({ratio:.1f}x vs {lib})"
    print(f"  {label:<30s} {time_ms:8.2f} ms{speedup}")


def run_benchmarks(xml: bytes, label: str) -> None:
    size_mb = len(xml) / (1024 * 1024)
    print(f"\n{'=' * 60}")
    print(f"  {label} ({size_mb:.1f} MB, {len(xml):,} bytes)")
    print(f"{'=' * 60}")

    # --- Parse ---
    print("\n  Parse:")
    simdxml_parse = bench("simdxml", lambda: simdxml.parse(xml))
    print_row("simdxml.parse()", simdxml_parse)

    if HAS_LXML:
        lxml_parse = bench("lxml", lambda: lxml_etree.fromstring(xml))
        print_row("lxml.etree.fromstring()", lxml_parse)

    std_parse = bench("stdlib", lambda: StdET.fromstring(xml))
    print_row("ET.fromstring()", std_parse)

    baseline = lxml_parse if HAS_LXML else std_parse
    lib = "lxml" if HAS_LXML else "stdlib"
    print(f"\n  Parse speedup: {baseline / simdxml_parse:.1f}x vs {lib}")

    # --- XPath: //name (simple descendant) ---
    print("\n  XPath: //name")
    doc = simdxml.parse(xml)
    compiled = simdxml.compile("//name")

    simdxml_xpath = bench("simdxml.xpath_text", lambda: doc.xpath_text("//name"))
    print_row("doc.xpath_text()", simdxml_xpath)

    simdxml_compiled = bench("simdxml.compiled", lambda: compiled.eval_text(doc))
    print_row("compiled.eval_text()", simdxml_compiled)

    if HAS_LXML:
        lxml_root = lxml_etree.fromstring(xml)
        lxml_xpath = bench("lxml.xpath", lambda: lxml_root.xpath("//name"))
        print_row("lxml_root.xpath()", lxml_xpath)
        baseline_xpath = lxml_xpath
    else:
        baseline_xpath = None

    std_root = StdET.fromstring(xml)
    std_findall = bench("stdlib.findall", lambda: std_root.findall(".//name"))
    print_row("std_root.findall()", std_findall)

    if baseline_xpath:
        print(f"\n  XPath speedup: {baseline_xpath / simdxml_xpath:.1f}x vs lxml")

    # --- XPath: predicate query ---
    print('\n  XPath: //item[@category="cat5"]')
    pred_expr = '//item[@category="cat5"]'
    simdxml_pred = bench("simdxml", lambda: doc.xpath(pred_expr))
    print_row("doc.xpath()", simdxml_pred)

    if HAS_LXML:
        lxml_pred = bench("lxml", lambda: lxml_root.xpath(pred_expr))
        print_row("lxml_root.xpath()", lxml_pred)

    std_pred = bench("stdlib", lambda: std_root.findall('.//item[@category="cat5"]'))
    print_row("std_root.findall()", std_pred)

    # --- Element traversal ---
    print("\n  Traversal: iterate all children of root")
    simdxml_iter = bench("simdxml", lambda: [e.tag for e in doc.root])
    print_row("for e in doc.root", simdxml_iter)

    if HAS_LXML:
        lxml_iter = bench("lxml", lambda: [e.tag for e in lxml_root])
        print_row("for e in lxml_root", lxml_iter)

    std_iter = bench("stdlib", lambda: [e.tag for e in std_root])
    print_row("for e in std_root", std_iter)


def main() -> None:
    print("simdxml benchmark")
    print(f"  lxml available: {HAS_LXML}")
    if HAS_LXML:
        print(f"  lxml version: {lxml_etree.LXML_VERSION}")

    # Small document
    small = generate_xml(100)
    run_benchmarks(small, "Small (100 items)")

    # Medium document
    medium = generate_xml(10_000)
    run_benchmarks(medium, "Medium (10K items)")

    # Large document
    large = generate_xml(100_000)
    run_benchmarks(large, "Large (100K items)")


if __name__ == "__main__":
    main()
