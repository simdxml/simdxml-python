use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::pybacked::PyBackedBytes;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};
use self_cell::self_cell;
use simdxml::xpath::XPathNode;
use simdxml::XmlIndex;

// ---------------------------------------------------------------------------
// Self-referential Document: owns bytes + XmlIndex + derived data
// ---------------------------------------------------------------------------

/// Owner type: either zero-copy from Python bytes or owned from str input.
enum DocumentOwner {
    /// Zero-copy: borrows directly from Python bytes object's internal buffer.
    ZeroCopy(PyBackedBytes),
    /// Owned: copied from str input (Python str -> UTF-8 bytes).
    Owned(Vec<u8>),
}

impl std::ops::Deref for DocumentOwner {
    type Target = [u8];
    fn deref(&self) -> &[u8] {
        match self {
            DocumentOwner::ZeroCopy(b) => b,
            DocumentOwner::Owned(v) => v,
        }
    }
}

struct IndexWithMeta<'a> {
    index: XmlIndex<'a>,
    /// parent[i] = tag index of parent element. u32::MAX = root.
    parents: Vec<u32>,
    /// name_id[i] = index into interned names for tag i. usize::MAX = none.
    name_ids: Vec<usize>,
    /// Unique tag name strings (used to build Python interned strings at parse time).
    unique_names: Vec<String>,
}

self_cell!(
    struct DocumentInner {
        owner: DocumentOwner,
        #[covariant]
        dependent: IndexWithMeta,
    }
);

/// A parsed XML document.
///
/// Created by `parse()`. Use `root` to get the root element,
/// or query directly with `xpath_text()` and `xpath()`.
#[pyclass]
struct Document {
    inner: DocumentInner,
    /// Interned tag names: unique tag name -> Python str (created once at parse).
    interned_names: Vec<Py<PyString>>,
}

impl Document {
    fn index(&self) -> &XmlIndex<'_> {
        &self.inner.borrow_dependent().index
    }

    fn meta(&self) -> &IndexWithMeta<'_> {
        self.inner.borrow_dependent()
    }

    /// Look up interned tag when you already have a meta borrow (hot path).
    fn interned_tag_fast(
        &self,
        py: Python<'_>,
        meta: &IndexWithMeta<'_>,
        tag_idx: usize,
    ) -> Py<PyString> {
        let name_id = meta.name_ids[tag_idx];
        if name_id < self.interned_names.len() {
            self.interned_names[name_id].clone_ref(py)
        } else {
            PyString::new(py, meta.index.tag_name(tag_idx)).unbind()
        }
    }

    /// Create an Element when you don't already hold a borrow.
    fn make_element(py: Python<'_>, doc: &Py<Document>, tag_idx: usize) -> Element {
        let doc_ref = doc.borrow(py);
        Self::make_element_borrowed(py, doc, &doc_ref, tag_idx)
    }

    /// Create an Element when you already hold a borrow (avoids double-borrow).
    fn make_element_borrowed(
        py: Python<'_>,
        doc: &Py<Document>,
        doc_ref: &Document,
        tag_idx: usize,
    ) -> Element {
        let meta = doc_ref.meta();
        let cached_tag = doc_ref.interned_tag_fast(py, meta, tag_idx);
        Element {
            doc: doc.clone_ref(py),
            tag_idx,
            cached_tag,
        }
    }

    fn make_elements(
        py: Python<'_>,
        doc: &Py<Document>,
        doc_ref: &Document,
        tag_indices: impl Iterator<Item = usize>,
    ) -> Vec<Element> {
        let meta = doc_ref.meta();
        tag_indices
            .map(|idx| {
                let cached_tag = doc_ref.interned_tag_fast(py, meta, idx);
                Element {
                    doc: doc.clone_ref(py),
                    tag_idx: idx,
                    cached_tag,
                }
            })
            .collect()
    }
}

#[pymethods]
impl Document {
    /// Evaluate an XPath expression and return text content of matches.
    ///
    /// Returns the direct child text of each matching element.
    fn xpath_text(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<Py<PyString>>> {
        let index = self.index();
        let results = index
            .xpath_text(expr)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        // Return Py<PyString> directly from &str — avoids Rust String intermediary
        Ok(results
            .into_iter()
            .map(|s| PyString::new(py, s).unbind())
            .collect())
    }

    /// Evaluate an XPath expression and return string-values of matches.
    ///
    /// Returns all descendant text for each match (XPath `string()` semantics).
    fn xpath_string(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<Py<PyString>>> {
        let index = self.index();
        let results = index
            .xpath_string(expr)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(results
            .into_iter()
            .map(|s| PyString::new(py, &s).unbind())
            .collect())
    }

    /// Evaluate an XPath expression.
    ///
    /// Returns Element objects for element nodes, strings for text/attribute nodes.
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
                    let elem = Document::make_element_borrowed(py, &doc_py, &this, *idx);
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

    /// The root element of the document, or None if empty.
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
                return Some(Document::make_element_borrowed(py, &doc_py, &this, i));
            }
        }
        None
    }

    /// Total number of XML tags in the document.
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
// Element
// ---------------------------------------------------------------------------

/// A read-only XML element.
///
/// Supports the ElementTree API (.tag, .text, .attrib, .get(), len(),
/// indexing, iteration) plus lxml extensions (.xpath(), .getparent(),
/// .getnext(), .getprevious()).
#[pyclass(skip_from_py_object)]
struct Element {
    doc: Py<Document>,
    tag_idx: usize,
    /// Cached tag name (interned Python string).
    cached_tag: Py<PyString>,
}

#[pymethods]
impl Element {
    /// The element's tag name (e.g., 'book', 'title').
    #[getter]
    fn tag(&self, py: Python<'_>) -> Py<PyString> {
        self.cached_tag.clone_ref(py)
    }

    /// Text content before the first child element, or None.
    ///
    /// For `<p>Hello <b>world</b></p>`, `p.text` is `'Hello '`.
    #[getter]
    fn text(&self, py: Python<'_>) -> Option<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let texts = index.direct_text(self.tag_idx);
        if texts.is_empty() {
            return None;
        }
        let first = texts[0];
        if first.is_empty() {
            None
        } else {
            let decoded = XmlIndex::decode_entities(first);
            Some(PyString::new(py, &decoded).unbind())
        }
    }

    /// Text content after this element's closing tag, or None.
    ///
    /// For `<p>Hello <b>world</b> more</p>`, `b.tail` is `' more'`.
    #[getter]
    fn tail(&self, py: Python<'_>) -> Option<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let meta = doc.meta();
        let parent = meta.parents[self.tag_idx];
        if parent == u32::MAX {
            return None;
        }

        let index = &meta.index;
        let parent_raw = index.raw_xml(parent as usize);
        let my_raw = index.raw_xml(self.tag_idx);

        if let Some(pos) = parent_raw.find(my_raw) {
            let after = &parent_raw[pos + my_raw.len()..];
            if let Some(lt) = after.find('<') {
                let text = &after[..lt];
                if !text.is_empty() {
                    let decoded = XmlIndex::decode_entities(text);
                    return Some(PyString::new(py, &decoded).unbind());
                }
            }
        }
        None
    }

    /// Dictionary of this element's attributes.
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
    fn get(&self, py: Python<'_>, key: &str, default: Option<&str>) -> Option<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        index
            .get_attribute(self.tag_idx, key)
            .map(|s| PyString::new(py, s).unbind())
            .or_else(|| default.map(|s| PyString::new(py, s).unbind()))
    }

    /// Attribute names.
    fn keys(&self, py: Python<'_>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        index
            .get_all_attribute_names(self.tag_idx)
            .into_iter()
            .map(|s| PyString::new(py, s).unbind())
            .collect()
    }

    /// (name, value) attribute pairs.
    fn items(&self, py: Python<'_>) -> Vec<(Py<PyString>, Py<PyString>)> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        index
            .get_all_attribute_names(self.tag_idx)
            .into_iter()
            .filter_map(|name| {
                index.get_attribute(self.tag_idx, name).map(|val| {
                    (
                        PyString::new(py, name).unbind(),
                        PyString::new(py, val).unbind(),
                    )
                })
            })
            .collect()
    }

    /// Number of direct child elements.
    fn __len__(&self, py: Python<'_>) -> usize {
        let doc = self.doc.borrow(py);
        doc.index().children(self.tag_idx).len()
    }

    /// Get a child element by index. Supports negative indexing.
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
        Ok(Document::make_element_borrowed(
            py,
            &self.doc,
            &doc,
            children[i as usize],
        ))
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

        // Linear scan over tag range (not index-accelerated).
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

    /// All direct child tag names as a list.
    ///
    /// More efficient than `[e.tag for e in element]` for bulk access.
    fn child_tags(&self, py: Python<'_>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let meta = doc.meta();
        meta.index
            .children(self.tag_idx)
            .iter()
            .map(|&child| doc.interned_tag_fast(py, meta, child))
            .collect()
    }

    /// All descendant tag names, optionally filtered.
    ///
    /// More efficient than `[e.tag for e in element.iter(tag)]` for bulk access.
    #[pyo3(signature = (tag=None))]
    fn descendant_tags(&self, py: Python<'_>, tag: Option<&str>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let meta = doc.meta();
        let index = &meta.index;
        let start = self.tag_idx;
        let close = index.matching_close(start).unwrap_or(start);

        let mut result = Vec::new();
        for i in (start + 1)..=close {
            let tt = index.tag_type(i);
            if tt == simdxml::index::TagType::Open || tt == simdxml::index::TagType::SelfClose {
                match tag {
                    Some(filter) if index.tag_name(i) != filter => {}
                    _ => result.push(doc.interned_tag_fast(py, meta, i)),
                }
            }
        }
        result
    }

    /// All text content within this element, depth-first.
    fn itertext(&self, py: Python<'_>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let mut texts = Vec::new();
        collect_text_py(py, index, self.tag_idx, &mut texts);
        texts
    }

    /// All descendant text concatenated into a single string.
    fn text_content(&self, py: Python<'_>) -> Py<PyString> {
        let doc = self.doc.borrow(py);
        let text = doc.index().all_text(self.tag_idx);
        PyString::new(py, &text).unbind()
    }

    /// Evaluate an XPath 1.0 expression with this element as context.
    ///
    /// Returns a list of matching Element objects.
    fn xpath(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<Element>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let nodes = index
            .xpath_from(expr, self.tag_idx)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        Ok(Document::make_elements(
            py,
            &self.doc,
            &doc,
            nodes.into_iter().filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            }),
        ))
    }

    /// Evaluate an XPath expression and return text content of matches.
    fn xpath_text(&self, py: Python<'_>, expr: &str) -> PyResult<Vec<Py<PyString>>> {
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
                        // Build PyString directly from &str slices
                        let joined: String = dt.iter().copied().collect();
                        texts.push(PyString::new(py, &joined).unbind());
                    }
                }
                XPathNode::Text(idx) => {
                    texts.push(PyString::new(py, index.text_by_index(*idx)).unbind());
                }
                XPathNode::Attribute(tag_idx, _) => {
                    if let Some(s) = get_first_attribute_str(index, *tag_idx) {
                        texts.push(PyString::new(py, s).unbind());
                    }
                }
                _ => {}
            }
        }
        Ok(texts)
    }

    /// Parent element, or None for root.
    fn getparent(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let parent = doc.meta().parents[self.tag_idx];
        if parent == u32::MAX {
            None
        } else {
            Some(Document::make_element_borrowed(
                py,
                &self.doc,
                &doc,
                parent as usize,
            ))
        }
    }

    /// Next sibling element, or None.
    fn getnext(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let meta = doc.meta();
        let parent = meta.parents[self.tag_idx];
        if parent == u32::MAX {
            return None;
        }
        let siblings = meta.index.children(parent as usize);
        let pos = siblings.iter().position(|&s| s == self.tag_idx)?;
        siblings
            .get(pos + 1)
            .map(|&idx| Document::make_element_borrowed(py, &self.doc, &doc, idx))
    }

    /// Previous sibling element, or None.
    fn getprevious(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let meta = doc.meta();
        let parent = meta.parents[self.tag_idx];
        if parent == u32::MAX {
            return None;
        }
        let siblings = meta.index.children(parent as usize);
        let pos = siblings.iter().position(|&s| s == self.tag_idx)?;
        if pos > 0 {
            Some(Document::make_element_borrowed(
                py,
                &self.doc,
                &doc,
                siblings[pos - 1],
            ))
        } else {
            None
        }
    }

    /// Serialize this element to an XML string.
    fn tostring(&self, py: Python<'_>) -> Py<PyString> {
        let doc = self.doc.borrow(py);
        let raw = doc.index().raw_xml(self.tag_idx);
        PyString::new(py, raw).unbind()
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

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    #[pyo3(name = "set")]
    fn set_attr(&self, _key: &str, _value: &str) -> PyResult<()> {
        Err(readonly_error())
    }

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    fn append(&self, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    fn remove(&self, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    #[pyo3(signature = (_index, _element))]
    fn insert(&self, _index: isize, _element: &Element) -> PyResult<()> {
        Err(readonly_error())
    }

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    fn clear(&self) -> PyResult<()> {
        Err(readonly_error())
    }

    fn __repr__(&self, py: Python<'_>) -> String {
        let tag_str = self.cached_tag.bind(py).to_cow().unwrap_or_default();
        format!("Element('{tag_str}')")
    }

    fn __str__(&self, py: Python<'_>) -> Py<PyString> {
        self.cached_tag.clone_ref(py)
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

/// A compiled XPath expression for repeated use.
///
/// Like `re.compile()` -- parse the expression once, evaluate many times
/// across different documents.
#[pyclass]
struct CompiledXPath {
    inner: simdxml::CompiledXPath,
}

#[pymethods]
impl CompiledXPath {
    /// Evaluate and return text content of matching nodes.
    fn eval_text(&self, py: Python<'_>, doc: &Document) -> PyResult<Vec<Py<PyString>>> {
        let index = doc.index();
        let results = self
            .inner
            .eval_text(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(results
            .into_iter()
            .map(|s| PyString::new(py, s).unbind())
            .collect())
    }

    /// Evaluate and return matching Element objects.
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
            &doc_ref,
            nodes.into_iter().filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            }),
        ))
    }

    /// Check whether any nodes match.
    fn eval_exists(&self, doc: &Document) -> PyResult<bool> {
        let index = doc.index();
        let nodes = self
            .inner
            .eval(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(!nodes.is_empty())
    }

    /// Count the number of matching nodes.
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

fn get_first_attribute_str<'a>(index: &'a XmlIndex<'_>, tag_idx: usize) -> Option<&'a str> {
    let names = index.get_all_attribute_names(tag_idx);
    names
        .first()
        .and_then(|name| index.get_attribute(tag_idx, name))
}

/// Build parent map, name-id map, and unique name list from the public API.
fn build_meta(index: &XmlIndex<'_>) -> (Vec<u32>, Vec<usize>, Vec<String>) {
    let n = index.tag_count();

    // Parent map
    let mut parents = vec![u32::MAX; n];
    for i in 0..n {
        if index.tag_type(i) == simdxml::index::TagType::Open {
            for child in index.children(i) {
                if child < n {
                    parents[child] = i as u32;
                }
            }
        }
    }

    // Name interning: borrow tag names from the index to avoid extra clones.
    let mut unique_names: Vec<String> = Vec::new();
    let mut name_map: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    let mut name_ids = vec![usize::MAX; n];

    for i in 0..n {
        let tt = index.tag_type(i);
        if tt == simdxml::index::TagType::Open || tt == simdxml::index::TagType::SelfClose {
            let name = index.tag_name(i);
            if !name.is_empty() {
                let id = *name_map.entry(name).or_insert_with(|| {
                    let id = unique_names.len();
                    unique_names.push(name.to_string());
                    id
                });
                name_ids[i] = id;
            }
        }
    }

    (parents, name_ids, unique_names)
}

/// Build interned Python strings from the unique name list.
fn build_interned_names(py: Python<'_>, unique_names: &[String]) -> Vec<Py<PyString>> {
    unique_names
        .iter()
        .map(|s| PyString::new(py, s).unbind())
        .collect()
}

/// Recursively collect text content depth-first, building PyStrings directly.
fn collect_text_py(py: Python<'_>, index: &XmlIndex<'_>, tag_idx: usize, out: &mut Vec<Py<PyString>>) {
    for text in index.direct_text(tag_idx) {
        if !text.is_empty() {
            let decoded = XmlIndex::decode_entities(text);
            out.push(PyString::new(py, &decoded).unbind());
        }
    }
    for child in index.children(tag_idx) {
        collect_text_py(py, index, child, out);
    }
}

// ---------------------------------------------------------------------------
// Module-level functions
// ---------------------------------------------------------------------------

/// Parse XML into a Document.
///
/// Accepts bytes or str. Returns a Document that can be queried
/// with XPath or traversed element-by-element.
///
/// For bytes input, the buffer is used directly (zero-copy).
/// For str input, the string is encoded to UTF-8 bytes.
#[pyfunction]
fn parse(py: Python<'_>, data: &Bound<'_, PyAny>) -> PyResult<Document> {
    let owner = if data.is_instance_of::<PyBytes>() {
        // Zero-copy: PyBackedBytes borrows from the Python bytes object
        let backed: PyBackedBytes = data.extract()?;
        DocumentOwner::ZeroCopy(backed)
    } else if let Ok(s) = data.extract::<String>() {
        DocumentOwner::Owned(s.into_bytes())
    } else {
        return Err(PyTypeError::new_err("parse() requires bytes or str"));
    };

    let inner = DocumentInner::try_new(owner, |owner| {
        let mut index =
            simdxml::parse(owner).map_err(|e| PyValueError::new_err(e.to_string()))?;
        index.ensure_indices();
        index.build_name_index();
        let (parents, name_ids, unique_names) = build_meta(&index);
        Ok::<_, PyErr>(IndexWithMeta {
            index,
            parents,
            name_ids,
            unique_names,
        })
    })?;

    // Build interned Python strings (one copy per unique name)
    let interned_names = {
        let meta = inner.borrow_dependent();
        build_interned_names(py, &meta.unique_names)
    };

    Ok(Document {
        inner,
        interned_names,
    })
}

/// Compile an XPath expression for repeated use.
///
/// Like `re.compile()` -- parse the expression once, evaluate many times
/// across different documents.
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
