"""Benchmark: simdxml vs lxml vs stdlib xml.etree.ElementTree.

Methodology:
  - GC disabled during timing to avoid collection noise
  - 3 warmup iterations discarded, then 20 timed iterations
  - Reports median (robust to outliers from page faults, scheduling)
  - All XPath benchmarks compare like-for-like: elements vs elements
  - Both synthetic and real-world-shaped corpora

Note: simdxml.parse() eagerly builds structural indices (CSR, name
posting, parent map). lxml.fromstring() builds a DOM tree without
precomputed indices. This means simdxml front-loads more work into
parse, then queries are faster. Both numbers are real -- the question
is which workload you have.

Usage:
    uv run python bench/bench_parse.py
"""

from __future__ import annotations

import gc
import random
import sys
import time
import xml.etree.ElementTree as StdET

import simdxml

try:
    from lxml import etree as lxml_etree

    HAS_LXML = True
except ImportError:
    HAS_LXML = False


# ---------------------------------------------------------------------------
# Corpus generators
# ---------------------------------------------------------------------------


def gen_catalog(n: int) -> bytes:
    """Data-oriented: uniform structure, many attributes."""
    items = "\n".join(
        "  "
        f'<item id="{i}" category="cat{i % 10}">'
        f"<name>Item {i}</name>"
        f"<description>Desc for item {i}</description>"
        f"<price>{i * 1.5:.2f}</price>"
        f"<tags><tag>t{i % 5}</tag><tag>t{i % 3}</tag></tags>"
        f"</item>"
        for i in range(n)
    )
    return f"<catalog>\n{items}\n</catalog>".encode()


def gen_pubmed(n: int) -> bytes:
    """Document-oriented: mixed depth, varying children."""
    rng = random.Random(42)
    articles = []
    for i in range(n):
        n_auth = rng.randint(1, 8)
        auths = "\n".join(
            "        <Author>"
            f"<LastName>Auth{j}_{i}</LastName>"
            f"<ForeName>F{j}</ForeName>"
            f"<Affiliation>Univ {rng.randint(1, 20)}"
            "</Affiliation>"
            "</Author>"
            for j in range(n_auth)
        )
        n_mesh = rng.randint(2, 12)
        mesh = "\n".join(
            "        <MeshHeading>"
            f'<DescriptorName UI="D{rng.randint(100000, 999999)}">'
            f"Term{k}_{i}</DescriptorName>"
            "</MeshHeading>"
            for k in range(n_mesh)
        )
        kind = "randomized" if i % 2 else "retrospective"
        sents = " ".join(
            f"Sentence {s} about topic {i}." for s in range(rng.randint(3, 8))
        )
        issn = f"{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
        articles.append(
            "  <PubmedArticle>\n"
            '    <MedlineCitation Status="MEDLINE">\n'
            f"      <PMID>{10000000 + i}</PMID>\n"
            "      <Article>\n"
            "        <Journal>"
            f'<ISSN IssnType="Print">{issn}</ISSN>'
            f"<Title>J Example {i % 50}</Title>"
            "</Journal>\n"
            f"        <ArticleTitle>Topic {i}: "
            f"a {kind} study</ArticleTitle>\n"
            "        <Abstract>"
            f"<AbstractText>{sents}</AbstractText>"
            "</Abstract>\n"
            f"        <AuthorList>\n{auths}\n"
            "        </AuthorList>\n"
            "        <Language>eng</Language>\n"
            "      </Article>\n"
            f"      <MeshHeadingList>\n{mesh}\n"
            "      </MeshHeadingList>\n"
            "    </MedlineCitation>\n"
            "  </PubmedArticle>"
        )
    body = "\n".join(articles)
    return f"<PubmedArticleSet>\n{body}\n</PubmedArticleSet>".encode()


def gen_pom(n: int) -> bytes:
    """Config-oriented: deep nesting, namespaces."""
    deps = "\n".join(
        "      <dependency>\n"
        f"        <groupId>com.example.g{i % 20}</groupId>\n"
        f"        <artifactId>art-{i}</artifactId>\n"
        f"        <version>{i % 5}.{i % 10}.{i % 3}</version>\n"
        "        <scope>"
        + ("compile" if i % 3 == 0 else "test" if i % 3 == 1 else "runtime")
        + "</scope>\n"
        + (
            "        <exclusions>\n"
            f"          <exclusion>"
            f"<groupId>com.ex.{i}</groupId>"
            f"<artifactId>bad-{i}</artifactId>"
            "</exclusion>\n"
            "        </exclusions>\n"
            if i % 4 == 0
            else ""
        )
        + "      </dependency>"
        for i in range(n)
    )
    return (
        "<project>\n"
        "  <modelVersion>4.0.0</modelVersion>\n"
        "  <groupId>com.example</groupId>\n"
        "  <artifactId>benchmark</artifactId>\n"
        "  <version>1.0.0</version>\n"
        f"  <dependencies>\n{deps}\n  </dependencies>\n"
        "</project>"
    ).encode()


# ---------------------------------------------------------------------------
# Bench harness
# ---------------------------------------------------------------------------

WARMUP = 3
ITERATIONS = 20


def bench(fn) -> float:
    """Warmup then timed iterations; return median ms."""
    for _ in range(WARMUP):
        fn()

    gc.disable()
    try:
        times = []
        for _ in range(ITERATIONS):
            t0 = time.perf_counter()
            fn()
            times.append((time.perf_counter() - t0) * 1000)
    finally:
        gc.enable()

    times.sort()
    return times[len(times) // 2]


def fmt(ms: float) -> str:
    if ms < 0.01:
        return f"{ms * 1000:6.1f} us"
    if ms < 1:
        return f"{ms:6.2f} ms"
    return f"{ms:6.1f} ms"


def ratio_str(a: float, b: float) -> str:
    if b <= 0:
        return ""
    r = b / a
    if r >= 1:
        return f" \033[32m{r:.1f}x faster\033[0m"
    return f" \033[31m{1 / r:.1f}x slower\033[0m"


# ---------------------------------------------------------------------------
# Benchmark suites
# ---------------------------------------------------------------------------


def bench_parse(xml: bytes, label: str) -> None:
    print(f"\n  \033[1mParse\033[0m  ({label})")
    print("  Note: simdxml.parse() includes index construction (CSR + name posting)")

    t_simd = bench(lambda: simdxml.parse(xml))
    print(f"    simdxml.parse()         {fmt(t_simd)}")

    if HAS_LXML:
        t_lxml = bench(lambda: lxml_etree.fromstring(xml))
        print(f"    lxml.fromstring()       {fmt(t_lxml)}{ratio_str(t_simd, t_lxml)}")

    t_std = bench(lambda: StdET.fromstring(xml))
    print(f"    ET.fromstring()         {fmt(t_std)}{ratio_str(t_simd, t_std)}")


def bench_xpath_elements(xml: bytes, expr: str, label: str) -> None:
    """XPath returning Element objects -- fair comparison."""
    print(f"\n  \033[1mXPath -> Elements\033[0m  {expr}  ({label})")

    doc = simdxml.parse(xml)
    t_simd = bench(lambda: doc.xpath(expr))
    n_results = len(doc.xpath(expr))
    print(f"    simdxml doc.xpath()     {fmt(t_simd)}  ({n_results} results)")

    if HAS_LXML:
        lroot = lxml_etree.fromstring(xml)
        t_lxml = bench(lambda: lroot.xpath(expr))
        print(f"    lxml root.xpath()       {fmt(t_lxml)}{ratio_str(t_simd, t_lxml)}")

    # stdlib findall -- skip complex expressions
    if not any(c in expr for c in ("()", "::", "|")):
        std_expr = expr
        if not expr.startswith("."):
            std_expr = "." + expr if expr.startswith("/") else "./" + expr
        sroot = StdET.fromstring(xml)
        try:
            t_std = bench(lambda: sroot.findall(std_expr))
            print(f"    ET.findall()            {fmt(t_std)}{ratio_str(t_simd, t_std)}")
        except SyntaxError:
            pass


def bench_xpath_text(xml: bytes, expr: str, label: str) -> None:
    """XPath returning text -- simdxml's optimized path."""
    print(f"\n  \033[1mXPath -> Text\033[0m  {expr}  ({label})")

    doc = simdxml.parse(xml)
    compiled = simdxml.compile(expr)

    t_inline = bench(lambda: doc.xpath_text(expr))
    t_compiled = bench(lambda: compiled.eval_text(doc))
    n = len(doc.xpath_text(expr))
    print(f"    simdxml xpath_text()    {fmt(t_inline)}  ({n} results)")
    print(f"    simdxml compiled        {fmt(t_compiled)}")

    if HAS_LXML:
        lroot = lxml_etree.fromstring(xml)
        t_lxml = bench(lambda: [e.text for e in lroot.xpath(expr)])
        print(f"    lxml xpath+.text        {fmt(t_lxml)}{ratio_str(t_inline, t_lxml)}")


def bench_traversal(xml: bytes, label: str) -> None:
    """Element traversal: per-element loop vs batch API."""
    print(f"\n  \033[1mTraversal\033[0m  ({label})")

    doc = simdxml.parse(xml)

    # Batch API (single FFI call, interned strings)
    t_batch = bench(lambda: doc.root.child_tags())
    print(f"    simdxml child_tags()    {fmt(t_batch)}  [batch, 1 FFI call]")

    # Per-element loop (N FFI calls, but tags are interned)
    t_loop = bench(lambda: [e.tag for e in doc.root])
    print(f"    simdxml [e.tag for e]   {fmt(t_loop)}  [per-element FFI]")

    if HAS_LXML:
        lroot = lxml_etree.fromstring(xml)
        t_lxml = bench(lambda: [e.tag for e in lroot])
        print(f"    lxml [e.tag for e]      {fmt(t_lxml)}{ratio_str(t_batch, t_lxml)}")

    sroot = StdET.fromstring(xml)
    t_std = bench(lambda: [e.tag for e in sroot])
    print(f"    stdlib [e.tag for e]    {fmt(t_std)}{ratio_str(t_batch, t_std)}")


def run_corpus(xml: bytes, name: str) -> None:
    size_mb = len(xml) / (1024 * 1024)
    print(f"\n{'=' * 65}")
    print(f"  {name}  ({size_mb:.1f} MB, {len(xml):,} bytes)")
    print(f"{'=' * 65}")

    bench_parse(xml, name)

    if b"<item " in xml:
        bench_xpath_elements(xml, "//item", name)
        bench_xpath_elements(xml, '//item[@category="cat5"]', name)
        bench_xpath_text(xml, "//name", name)
    elif b"<PubmedArticle>" in xml:
        bench_xpath_elements(xml, "//PubmedArticle", name)
        bench_xpath_elements(xml, '//Author[LastName="Auth0_0"]', name)
        bench_xpath_text(xml, "//AbstractText", name)
    elif b"<dependency>" in xml:
        bench_xpath_elements(xml, "//dependency", name)
        bench_xpath_elements(xml, '//dependency[scope="test"]', name)
        bench_xpath_text(xml, "//artifactId", name)

    bench_traversal(xml, name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("simdxml benchmark suite")
    print(f"  Python {sys.version.split()[0]}")
    print(f"  simdxml {simdxml.__version__}")
    if HAS_LXML:
        ver = ".".join(str(x) for x in lxml_etree.LXML_VERSION)
        print(f"  lxml {ver}")
    else:
        print("  lxml: not installed")
    print(f"  Warmup: {WARMUP}, Timed: {ITERATIONS}, Metric: median")

    run_corpus(
        gen_catalog(10_000),
        "Catalog 10K (data-oriented)",
    )
    run_corpus(
        gen_catalog(100_000),
        "Catalog 100K (data-oriented)",
    )
    run_corpus(
        gen_pubmed(1_000),
        "PubMed 1K (document-oriented)",
    )
    run_corpus(
        gen_pubmed(10_000),
        "PubMed 10K (document-oriented)",
    )
    run_corpus(
        gen_pom(1_000),
        "POM 1K (config-oriented)",
    )
    run_corpus(
        gen_pom(10_000),
        "POM 10K (config-oriented)",
    )


if __name__ == "__main__":
    main()
