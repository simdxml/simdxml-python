use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use self_cell::self_cell;
use simdxml::xpath::XPathNode;
use simdxml::XmlIndex;

// ---------------------------------------------------------------------------
// Self-referential Document: owns bytes + XmlIndex + derived data
// ---------------------------------------------------------------------------

struct IndexWithMeta<'a> {
    index: XmlIndex<'a>,
    /// parent[i] = tag index of parent element. u32::MAX = root.
    parents: Vec<u32>,
}

self_cell!(
    struct DocumentInner {
        owner: Vec<u8>,
        #[covariant]
        dependent: IndexWithMeta,
    }
);

/// A parsed XML document backed by a SIMD-accelerated structural index.
#[pyclass]
struct Document {
    inner: DocumentInner,
}

impl Document {
    fn index(&self) -> &XmlIndex<'_> {
        &self.inner.borrow_dependent().index
    }

    fn parents(&self) -> &[u32] {
        &self.inner.borrow_dependent().parents
    }

    fn make_element(py: Python<'_>, doc: &Py<Document>, tag_idx: usize) -> Element {
        Element {
            doc: doc.clone_ref(py),
            tag_idx,
        }
    }

    fn make_elements(
        py: Python<'_>,
        doc: &Py<Document>,
        tag_indices: impl Iterator<Item = usize>,
    ) -> Vec<Element> {
        tag_indices
            .map(|idx| Element {
                doc: doc.clone_ref(py),
                tag_idx: idx,
            })
            .collect()
    }
}

#[pymethods]
impl Document {
    /// Evaluate an XPath expression and return text content of matches.
    fn xpath_text(&self, expr: &str) -> PyResult<Vec<String>> {
        let index = self.index();
        let results = index
            .xpath_text(expr)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(results.into_iter().map(|s| s.to_string()).collect())
    }

    /// Evaluate an XPath expression and return the XPath string-value of matches.
    fn xpath_string(&self, expr: &str) -> PyResult<Vec<String>> {
        let index = self.index();
        index
            .xpath_string(expr)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Evaluate an XPath expression. Returns Element list for node-sets,
    /// strings for text/attribute nodes.
    fn xpath(slf: &Bound<'_, Self>, expr: &str) -> PyResult<Py<pyo3::types::PyList>> {
        let py = slf.py();
        let doc_py: Py<Document> = slf.clone().unbind();
        let this = slf.borrow();
        let index = this.index();
        let nodes = index
            .xpath(expr)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let result = pyo3::types::PyList::empty(py);
        for node in &nodes {
            match node {
                XPathNode::Element(idx) => {
                    let elem = Document::make_element(py, &doc_py, *idx);
                    result.append(elem.into_pyobject(py)?)?;
                }
                XPathNode::Text(idx) => {
                    let text = index.text_by_index(*idx);
                    result.append(text)?;
                }
                XPathNode::Attribute(tag_idx, _) => {
                    if let Some(val) = get_first_attribute(index, *tag_idx) {
                        result.append(val)?;
                    }
                }
                XPathNode::Namespace(_, _) => {}
            }
        }
        Ok(result.unbind())
    }

    /// The root element of the document.
    #[getter]
    fn root(slf: &Bound<'_, Self>) -> Option<Element> {
        let py = slf.py();
        let doc_py: Py<Document> = slf.clone().unbind();
        let this = slf.borrow();
        let index = this.index();
        for i in 0..index.tag_count() {
            if index.depth(i) == 0
                && (index.tag_type(i) == simdxml::index::TagType::Open
                    || index.tag_type(i) == simdxml::index::TagType::SelfClose)
            {
                return Some(Document::make_element(py, &doc_py, i));
            }
        }
        None
    }

    /// Number of tags in the structural index.
    #[getter]
    fn tag_count(&self) -> usize {
        self.index().tag_count()
    }

    fn __repr__(&self) -> String {
        let index = self.index();
        format!(
            "Document(tags={}, text_ranges={})",
            index.tag_count(),
            index.text_count()
        )
    }
}

// ---------------------------------------------------------------------------
// Element — lightweight flyweight handle into a Document
// ---------------------------------------------------------------------------

/// A read-only element in a parsed XML document.
///
/// Holds a Python reference to the Document (preventing GC) plus a tag index.
#[pyclass(skip_from_py_object)]
struct Element {
    /// Python-ref-counted handle to the owning Document.
    doc: Py<Document>,
    tag_idx: usize,
}

impl Element {
    fn with_index<'py, R>(&self, py: Python<'py>, f: impl FnOnce(&XmlIndex<'_>, &[u32]) -> R) -> R {
        let doc = self.doc.borrow(py);
        f(doc.index(), doc.parents())
    }
}

#[pymethods]
impl Element {
    /// The tag name.
    #[getter]
    fn tag(&self, py: Python<'_>) -> String {
        self.with_index(py, |index, _| index.tag_name(self.tag_idx).to_string())
    }

    /// Direct text content, or None.
    #[getter]
    fn text(&self, py: Python<'_>) -> Option<String> {
        self.with_index(py, |index, _| {
            let texts = index.direct_text(self.tag_idx);
            if texts.is_empty() {
                return None;
            }
            let first = texts[0];
            if first.is_empty() {
                None
            } else {
                Some(XmlIndex::decode_entities(first).into_owned())
            }
        })
    }

    /// Text after this element's closing tag (before next sibling).
    #[getter]
    fn tail(&self, py: Python<'_>) -> Option<String> {
        self.with_index(py, |index, parents| {
            let parent = parents[self.tag_idx];
            if parent == u32::MAX {
                return None;
            }

            let parent_raw = index.raw_xml(parent as usize);
            let my_raw = index.raw_xml(self.tag_idx);

            if let Some(pos) = parent_raw.find(my_raw) {
                let after = &parent_raw[pos + my_raw.len()..];
                if let Some(lt) = after.find('<') {
                    let text = &after[..lt];
                    if !text.is_empty() {
                        return Some(XmlIndex::decode_entities(text).into_owned());
                    }
                }
            }
            None
        })
    }

    /// Dictionary of attributes.
    #[getter]
    fn attrib(&self, py: Python<'_>) -> PyResult<Py<pyo3::types::PyDict>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let dict = pyo3::types::PyDict::new(py);
        for name in index.get_all_attribute_names(self.tag_idx) {
            if let Some(val) = index.get_attribute(self.tag_idx, name) {
                dict.set_item(name, val)?;
            }
        }
        Ok(dict.unbind())
    }

    /// Get an attribute value by name, with optional default.
    #[pyo3(signature = (key, default=None))]
    fn get(&self, py: Python<'_>, key: &str, default: Option<&str>) -> Option<String> {
        self.with_index(py, |index, _| {
            index
                .get_attribute(self.tag_idx, key)
                .map(|s| s.to_string())
                .or_else(|| default.map(|s| s.to_string()))
        })
    }

    /// Attribute names.
    fn keys(&self, py: Python<'_>) -> Vec<String> {
        self.with_index(py, |index, _| {
            index
                .get_all_attribute_names(self.tag_idx)
                .into_iter()
                .map(|s| s.to_string())
                .collect()
        })
    }

    /// (name, value) attribute pairs.
    fn items(&self, py: Python<'_>) -> Vec<(String, String)> {
        self.with_index(py, |index, _| {
            index
                .get_all_attribute_names(self.tag_idx)
                .into_iter()
                .filter_map(|name| {
                    index
                        .get_attribute(self.tag_idx, name)
                        .map(|val| (name.to_string(), val.to_string()))
                })
                .collect()
        })
    }

    /// Number of direct child elements.
    fn __len__(&self, py: Python<'_>) -> usize {
        self.with_index(py, |index, _| index.children(self.tag_idx).len())
    }

    /// Get the i-th child element.
    fn __getitem__(&self, py: Python<'_>, index: isize) -> PyResult<Element> {
        let doc = self.doc.borrow(py);
        let children = doc.index().children(self.tag_idx);
        let len = children.len() as isize;
        let i = if index < 0 { len + index } else { index };
        if i < 0 || i >= len {
            return Err(pyo3::exceptions::PyIndexError::new_err(
                "element index out of range",
            ));
        }
        Ok(Document::make_element(py, &self.doc, children[i as usize]))
    }

    /// Iterate over direct child elements.
    fn __iter__(&self, py: Python<'_>) -> ElementIterator {
        let doc = self.doc.borrow(py);
        ElementIterator {
            doc: self.doc.clone_ref(py),
            children: doc.index().children(self.tag_idx),
            pos: 0,
        }
    }

    /// Iterate descendant elements, optionally filtered by tag name.
    #[pyo3(signature = (tag=None))]
    fn iter(&self, py: Python<'_>, tag: Option<&str>) -> ElementIterator {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let start = self.tag_idx;
        let close = index.matching_close(start).unwrap_or(start);

        let mut descendants = Vec::new();
        for i in (start + 1)..=close {
            let tt = index.tag_type(i);
            if tt == simdxml::index::TagType::Open || tt == simdxml::index::TagType::SelfClose {
                match tag {
                    Some(filter) if index.tag_name(i) != filter => {}
                    _ => descendants.push(i),
                }
            }
        }
        ElementIterator {
            doc: self.doc.clone_ref(py),
            children: descendants,
            pos: 0,
        }
    }

    /// All text content (depth-first) as a list of strings.
    fn itertext(&self, py: Python<'_>) -> Vec<String> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let mut texts = Vec::new();
        collect_text(index, self.tag_idx, &mut texts);
        texts
    }

    /// Concatenation of all descendant text.
    fn text_content(&self, py: Python<'_>) -> String {
        self.with_index(py, |index, _| index.all_text(self.tag_idx))
    }

    /// Evaluate full XPath 1.0 from this element as context node.
    fn xpath(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<Element>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let nodes = index
            .xpath_from(expr, self.tag_idx)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        Ok(Document::make_elements(
            py,
            &self.doc,
            nodes.into_iter().filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            }),
        ))
    }

    /// XPath text extraction from this element as context.
    fn xpath_text(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<String>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let results = index
            .xpath_from(expr, self.tag_idx)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let mut texts = Vec::new();
        for node in &results {
            match node {
                XPathNode::Element(idx) => {
                    let dt = index.direct_text(*idx);
                    if !dt.is_empty() {
                        texts.push(dt.join(""));
                    }
                }
                XPathNode::Text(idx) => {
                    texts.push(index.text_by_index(*idx).to_string());
                }
                XPathNode::Attribute(tag_idx, _) => {
                    if let Some(val) = get_first_attribute(index, *tag_idx) {
                        texts.push(val);
                    }
                }
                _ => {}
            }
        }
        Ok(texts)
    }

    /// Parent element, or None for root.
    fn getparent(&self, py: Python<'_>) -> Option<Element> {
        self.with_index(py, |_, parents| {
            let parent = parents[self.tag_idx];
            if parent == u32::MAX {
                None
            } else {
                Some(Document::make_element(py, &self.doc, parent as usize))
            }
        })
    }

    /// Next sibling element, or None.
    fn getnext(&self, py: Python<'_>) -> Option<Element> {
        self.with_index(py, |index, parents| {
            let parent = parents[self.tag_idx];
            if parent == u32::MAX {
                return None;
            }
            let siblings = index.children(parent as usize);
            let pos = siblings.iter().position(|&s| s == self.tag_idx)?;
            siblings
                .get(pos + 1)
                .map(|&idx| Document::make_element(py, &self.doc, idx))
        })
    }

    /// Previous sibling element, or None.
    fn getprevious(&self, py: Python<'_>) -> Option<Element> {
        self.with_index(py, |index, parents| {
            let parent = parents[self.tag_idx];
            if parent == u32::MAX {
                return None;
            }
            let siblings = index.children(parent as usize);
            let pos = siblings.iter().position(|&s| s == self.tag_idx)?;
            if pos > 0 {
                Some(Document::make_element(py, &self.doc, siblings[pos - 1]))
            } else {
                None
            }
        })
    }

    /// Raw XML for this element (opening through closing tag).
    fn tostring(&self, py: Python<'_>) -> String {
        self.with_index(py, |index, _| index.raw_xml(self.tag_idx).to_string())
    }

    // -- Read-only enforcement --

    #[setter]
    fn set_tag(&self, _value: &str) -> PyResult<()> {
        Err(readonly_error())
    }

    #[setter]
    fn set_text(&self, _value: &str) -> PyResult<()> {
        Err(readonly_error())
    }

    #[setter]
    fn set_tail(&self, _value: &str) -> PyResult<()> {
        Err(readonly_error())
    }

    #[pyo3(name = "set")]
    fn set_attr(&self, _key: &str, _value: &str) -> PyResult<()> {
        Err(readonly_error())
    }

    fn append(&self, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    fn remove(&self, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    #[pyo3(signature = (_index, _element))]
    fn insert(&self, _index: isize, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    fn clear(&self) -> PyResult<()> {
        Err(readonly_error())
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let tag = self.with_index(py, |index, _| index.tag_name(self.tag_idx).to_string());
        format!("Element('{tag}')")
    }

    fn __str__(&self, py: Python<'_>) -> String {
        self.with_index(py, |index, _| index.tag_name(self.tag_idx).to_string())
    }

    fn __bool__(&self) -> bool {
        true
    }

    fn __eq__(&self, _py: Python<'_>, other: &Element) -> bool {
        self.doc.is(&other.doc) && self.tag_idx == other.tag_idx
    }

    fn __hash__(&self, _py: Python<'_>) -> isize {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        self.doc.as_ptr().hash(&mut hasher);
        self.tag_idx.hash(&mut hasher);
        hasher.finish() as isize
    }
}

// ---------------------------------------------------------------------------
// Element iterator
// ---------------------------------------------------------------------------

#[pyclass]
struct ElementIterator {
    doc: Py<Document>,
    children: Vec<usize>,
    pos: usize,
}

#[pymethods]
impl ElementIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> Option<Element> {
        if self.pos < self.children.len() {
            let idx = self.children[self.pos];
            self.pos += 1;
            Some(Document::make_element(py, &self.doc, idx))
        } else {
            None
        }
    }
}

// ---------------------------------------------------------------------------
// CompiledXPath
// ---------------------------------------------------------------------------

/// A compiled XPath expression for repeated evaluation.
#[pyclass]
struct CompiledXPath {
    inner: simdxml::CompiledXPath,
}

#[pymethods]
impl CompiledXPath {
    /// Evaluate and return text content of matches.
    fn eval_text(&self, doc: &Document) -> PyResult<Vec<String>> {
        let index = doc.index();
        let results = self
            .inner
            .eval_text(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(results.into_iter().map(|s| s.to_string()).collect())
    }

    /// Evaluate and return matching Element nodes.
    fn eval(slf: &Bound<'_, Self>, doc: &Bound<'_, Document>) -> PyResult<Vec<Element>> {
        let this = slf.borrow();
        let doc_ref = doc.borrow();
        let doc_py: Py<Document> = doc.clone().unbind();
        let index = doc_ref.index();
        let nodes = this
            .inner
            .eval(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let py = slf.py();
        Ok(Document::make_elements(
            py,
            &doc_py,
            nodes.into_iter().filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            }),
        ))
    }

    /// Check if any nodes match.
    fn eval_exists(&self, doc: &Document) -> PyResult<bool> {
        let index = doc.index();
        let nodes = self
            .inner
            .eval(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(!nodes.is_empty())
    }

    /// Count matching nodes.
    fn eval_count(&self, doc: &Document) -> PyResult<usize> {
        let index = doc.index();
        let nodes = self
            .inner
            .eval(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(nodes.len())
    }

    fn __repr__(&self) -> &'static str {
        "CompiledXPath(...)"
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn readonly_error() -> PyErr {
    PyTypeError::new_err(
        "simdxml Elements are read-only. Use xml.etree.ElementTree for XML construction.",
    )
}

fn get_first_attribute(index: &XmlIndex<'_>, tag_idx: usize) -> Option<String> {
    let names = index.get_all_attribute_names(tag_idx);
    names
        .first()
        .and_then(|name| index.get_attribute(tag_idx, name))
        .map(|s| s.to_string())
}

/// Build a parent map from the public children() API.
fn build_parent_map(index: &XmlIndex<'_>) -> Vec<u32> {
    let n = index.tag_count();
    let mut parents = vec![u32::MAX; n];
    for i in 0..n {
        let tt = index.tag_type(i);
        if tt == simdxml::index::TagType::Open {
            for child in index.children(i) {
                if child < n {
                    parents[child] = i as u32;
                }
            }
        }
    }
    parents
}

/// Recursively collect text content depth-first (for itertext).
fn collect_text(index: &XmlIndex<'_>, tag_idx: usize, out: &mut Vec<String>) {
    for text in index.direct_text(tag_idx) {
        if !text.is_empty() {
            out.push(XmlIndex::decode_entities(text).into_owned());
        }
    }
    for child in index.children(tag_idx) {
        collect_text(index, child, out);
    }
}

// ---------------------------------------------------------------------------
// Module-level functions
// ---------------------------------------------------------------------------

/// Parse XML bytes or string into a Document.
#[pyfunction]
fn parse(data: &Bound<'_, PyAny>) -> PyResult<Document> {
    let bytes: Vec<u8> = if let Ok(b) = data.cast_exact::<PyBytes>() {
        b.as_bytes().to_vec()
    } else if let Ok(s) = data.extract::<String>() {
        s.into_bytes()
    } else {
        return Err(PyTypeError::new_err("parse() requires bytes or str"));
    };

    let inner = DocumentInner::try_new(bytes, |owner| {
        let mut index =
            simdxml::parse(owner).map_err(|e| PyValueError::new_err(e.to_string()))?;
        index.ensure_indices();
        index.build_name_index();
        let parents = build_parent_map(&index);
        Ok::<_, PyErr>(IndexWithMeta { index, parents })
    })?;

    Ok(Document { inner })
}

/// Compile an XPath expression for repeated evaluation.
#[pyfunction]
fn compile(expr: &str) -> PyResult<CompiledXPath> {
    let inner =
        simdxml::CompiledXPath::compile(expr).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(CompiledXPath { inner })
}

// ---------------------------------------------------------------------------
// Module
// ---------------------------------------------------------------------------

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Document>()?;
    m.add_class::<Element>()?;
    m.add_class::<CompiledXPath>()?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(compile, m)?)?;
    Ok(())
}
