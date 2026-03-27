use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::pybacked::PyBackedBytes;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};
use self_cell::self_cell;
use simdxml::xpath::XPathNode;
use simdxml::XmlIndex;

// ---------------------------------------------------------------------------
// Self-referential Document: owns bytes + XmlIndex
// ---------------------------------------------------------------------------

/// Owner type: either zero-copy from Python bytes or owned from str input.
enum DocumentOwner {
    ZeroCopy(PyBackedBytes),
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

self_cell!(
    struct DocumentInner {
        owner: DocumentOwner,
        #[covariant]
        dependent: XmlIndex,
    }
);

/// A parsed XML document.
///
/// Created by `parse()`. Use `root` to get the root element,
/// or query directly with `xpath_text()` and `xpath()`.
#[pyclass]
struct Document {
    inner: DocumentInner,
    /// Interned tag names: name_id -> Python str (created once at parse).
    interned_names: Vec<Py<PyString>>,
}

impl Document {
    fn index(&self) -> &XmlIndex<'_> {
        self.inner.borrow_dependent()
    }

    /// Look up interned tag name. Uses upstream name_ids directly.
    fn interned_tag(&self, py: Python<'_>, index: &XmlIndex<'_>, tag_idx: usize) -> Py<PyString> {
        if tag_idx < index.name_ids.len() {
            let name_id = index.name_ids[tag_idx];
            if (name_id as usize) < self.interned_names.len() && name_id != u16::MAX {
                return self.interned_names[name_id as usize].clone_ref(py);
            }
        }
        // Fallback for tags without interned names (comments, PIs, etc.)
        PyString::new(py, index.tag_name(tag_idx)).unbind()
    }

    fn make_element(py: Python<'_>, doc: &Py<Document>, tag_idx: usize) -> Element {
        let doc_ref = doc.borrow(py);
        Self::make_element_borrowed(py, doc, &doc_ref, tag_idx)
    }

    fn make_element_borrowed(
        py: Python<'_>,
        doc: &Py<Document>,
        doc_ref: &Document,
        tag_idx: usize,
    ) -> Element {
        let index = doc_ref.index();
        let cached_tag = doc_ref.interned_tag(py, index, tag_idx);
        Element {
            doc: doc.clone_ref(py),
            tag_idx,
            cached_tag,
        }
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
                    let attrs = index.attributes(*tag_idx);
                    if let Some((_, val)) = attrs.first() {
                        result.append(*val)?;
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
        // Uses upstream direct_text_first — zero-alloc, no Vec
        index.direct_text_first(self.tag_idx).map(|s| {
            let decoded = XmlIndex::decode_entities(s);
            PyString::new(py, &decoded).unbind()
        })
    }

    /// Text content after this element's closing tag, or None.
    ///
    /// For `<p>Hello <b>world</b> more</p>`, `b.tail` is `' more'`.
    #[getter]
    fn tail(&self, py: Python<'_>) -> Option<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        // Uses upstream tail_text — proper implementation using text_ranges
        index.tail_text(self.tag_idx).map(|s| {
            let decoded = XmlIndex::decode_entities(s);
            PyString::new(py, &decoded).unbind()
        })
    }

    /// Dictionary of this element's attributes.
    #[getter]
    fn attrib(&self, py: Python<'_>) -> PyResult<Py<pyo3::types::PyDict>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let dict = pyo3::types::PyDict::new(py);
        // Single-pass attribute parsing via upstream attributes()
        for (name, val) in index.attributes(self.tag_idx) {
            dict.set_item(name, val)?;
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
            .attributes(self.tag_idx)
            .into_iter()
            .map(|(name, _)| PyString::new(py, name).unbind())
            .collect()
    }

    /// (name, value) attribute pairs.
    fn items(&self, py: Python<'_>) -> Vec<(Py<PyString>, Py<PyString>)> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        index
            .attributes(self.tag_idx)
            .into_iter()
            .map(|(name, val)| {
                (
                    PyString::new(py, name).unbind(),
                    PyString::new(py, val).unbind(),
                )
            })
            .collect()
    }

    /// Number of direct child elements (zero allocation).
    fn __len__(&self, py: Python<'_>) -> usize {
        let doc = self.doc.borrow(py);
        doc.index().child_count(self.tag_idx)
    }

    /// Get a child element by index. Supports negative indexing.
    fn __getitem__(&self, py: Python<'_>, index: isize) -> PyResult<Element> {
        let doc = self.doc.borrow(py);
        let idx = doc.index();
        let len = idx.child_count(self.tag_idx) as isize;
        let i = if index < 0 { len + index } else { index };
        if i < 0 || i >= len {
            return Err(pyo3::exceptions::PyIndexError::new_err(
                "element index out of range",
            ));
        }
        let child = idx.child_at(self.tag_idx, i as usize).ok_or_else(|| {
            pyo3::exceptions::PyIndexError::new_err("element index out of range")
        })?;
        Ok(Document::make_element_borrowed(py, &self.doc, &doc, child))
    }

    /// Iterate over direct child elements.
    fn __iter__(&self, py: Python<'_>) -> ElementIterator {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let children: Vec<usize> = index
            .child_slice(self.tag_idx)
            .iter()
            .map(|&c| c as usize)
            .collect();
        ElementIterator::new(py, &self.doc, children)
    }

    /// Iterate descendant elements, optionally filtered by tag name.
    ///
    /// When filtered by tag, uses posting list binary search: O(log n + k)
    /// instead of O(subtree_size).
    #[pyo3(signature = (tag=None))]
    fn iter(&self, py: Python<'_>, tag: Option<&str>) -> ElementIterator {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let start = self.tag_idx;

        let descendants = if let Some(filter) = tag {
            // Fast path: use posting list for filtered iteration
            let mut result = Vec::new();
            // Include self if tag matches
            if index.tag_name_eq(start, filter) {
                result.push(start);
            }
            // Descendants via posting list
            result.extend(descendants_by_name(index, start, filter));
            result
        } else {
            // Unfiltered: linear scan (all elements)
            let close = index.matching_close(start).unwrap_or(start);
            let mut result = Vec::with_capacity(
                (close - start).min(1024),
            );
            // Include self
            let self_tt = index.tag_type(start);
            if self_tt == simdxml::index::TagType::Open
                || self_tt == simdxml::index::TagType::SelfClose
            {
                result.push(start);
            }
            for i in (start + 1)..=close {
                let tt = index.tag_type(i);
                if tt == simdxml::index::TagType::Open
                    || tt == simdxml::index::TagType::SelfClose
                {
                    result.push(i);
                }
            }
            result
        };
        ElementIterator::new(py, &self.doc, descendants)
    }

    /// All direct child tag names as a list (single FFI call, interned).
    fn child_tags(&self, py: Python<'_>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        index
            .child_slice(self.tag_idx)
            .iter()
            .map(|&child| doc.interned_tag(py, index, child as usize))
            .collect()
    }

    /// All descendant tag names, optionally filtered.
    #[pyo3(signature = (tag=None))]
    fn descendant_tags(&self, py: Python<'_>, tag: Option<&str>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let start = self.tag_idx;
        let close = index.matching_close(start).unwrap_or(start);

        let mut result = Vec::new();
        for i in (start + 1)..=close {
            let tt = index.tag_type(i);
            if tt == simdxml::index::TagType::Open || tt == simdxml::index::TagType::SelfClose {
                match tag {
                    Some(filter) if index.tag_name(i) != filter => {}
                    _ => result.push(doc.interned_tag(py, index, i)),
                }
            }
        }
        result
    }

    /// All text content within this element, depth-first.
    fn itertext(&self, py: Python<'_>) -> Vec<Py<PyString>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        // Single Rust call: flat text_ranges scan, no per-element callbacks
        index
            .itertext_collect(self.tag_idx)
            .into_iter()
            .map(|s| {
                let decoded = XmlIndex::decode_entities(s);
                PyString::new(py, &decoded).unbind()
            })
            .collect()
    }

    /// All descendant text concatenated into a single string.
    fn text_content(&self, py: Python<'_>) -> Py<PyString> {
        let doc = self.doc.borrow(py);
        let text = doc.index().all_text(self.tag_idx);
        PyString::new(py, &text).unbind()
    }

    /// Evaluate an XPath 1.0 expression with this element as context.
    fn xpath(&self, py: Python<'_>, expr: &str) -> PyResult<ElementList> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let nodes = index
            .xpath_from(expr, self.tag_idx)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let indices: Vec<usize> = nodes
            .into_iter()
            .filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            })
            .collect();
        Ok(ElementList {
            doc: self.doc.clone_ref(py),
            indices,
        })
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
                    if let Some(first) = index.direct_text_first(*idx) {
                        texts.push(PyString::new(py, first).unbind());
                    }
                }
                XPathNode::Text(idx) => {
                    texts.push(PyString::new(py, index.text_by_index(*idx)).unbind());
                }
                XPathNode::Attribute(tag_idx, _) => {
                    let attrs = index.attributes(*tag_idx);
                    if let Some((_, val)) = attrs.first() {
                        texts.push(PyString::new(py, val).unbind());
                    }
                }
                _ => {}
            }
        }
        Ok(texts)
    }

    /// Find the first matching subelement (ElementTree API).
    ///
    /// Uses index-accelerated lookup for simple paths (O(children) or O(log n)
    /// via posting lists). Falls back to XPath for complex paths.
    #[pyo3(signature = (path, _namespaces=None))]
    fn find(
        &self,
        py: Python<'_>,
        path: &str,
        _namespaces: Option<&Bound<'_, pyo3::PyAny>>,
    ) -> PyResult<Option<Element>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();

        // Fast path: bare tag name → first child with that name
        if is_simple_tag(path) {
            for &child in index.child_slice(self.tag_idx) {
                if index.tag_name_eq(child as usize, path) {
                    return Ok(Some(Document::make_element_borrowed(
                        py, &self.doc, &doc, child as usize,
                    )));
                }
            }
            return Ok(None);
        }

        // Fast path: .//tag or //tag → first descendant via posting list
        if let Some(tag) = descendant_tag_name(path) {
            if let Some(idx) = first_descendant_by_name(index, self.tag_idx, tag) {
                return Ok(Some(Document::make_element_borrowed(
                    py, &self.doc, &doc, idx,
                )));
            }
            return Ok(None);
        }

        // Fast path: * → first child
        if path == "*" {
            return Ok(index
                .child_at(self.tag_idx, 0)
                .map(|idx| Document::make_element_borrowed(py, &self.doc, &doc, idx)));
        }

        // Fallback: full XPath
        let xpath = et_path_to_xpath(path);
        let nodes = index
            .xpath_from(&xpath, self.tag_idx)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        for node in &nodes {
            if let XPathNode::Element(idx) = node {
                return Ok(Some(Document::make_element_borrowed(
                    py, &self.doc, &doc, *idx,
                )));
            }
        }
        Ok(None)
    }

    /// Find all matching subelements (ElementTree API).
    ///
    /// Uses index-accelerated lookup for simple paths. Returns an ElementList
    /// (lazy — elements created on access).
    #[pyo3(signature = (path, _namespaces=None))]
    fn findall(
        &self,
        py: Python<'_>,
        path: &str,
        _namespaces: Option<&Bound<'_, pyo3::PyAny>>,
    ) -> PyResult<ElementList> {
        let doc = self.doc.borrow(py);
        let index = doc.index();

        // Fast path: bare tag name → children with that name
        if is_simple_tag(path) {
            let indices: Vec<usize> = index
                .child_slice(self.tag_idx)
                .iter()
                .filter(|&&c| index.tag_name_eq(c as usize, path))
                .map(|&c| c as usize)
                .collect();
            return Ok(ElementList {
                doc: self.doc.clone_ref(py),
                indices,
            });
        }

        // Fast path: .//tag → descendants via posting list
        if let Some(tag) = descendant_tag_name(path) {
            let indices = descendants_by_name(index, self.tag_idx, tag);
            return Ok(ElementList {
                doc: self.doc.clone_ref(py),
                indices,
            });
        }

        // Fast path: * → all children
        if path == "*" {
            let indices: Vec<usize> = index
                .child_slice(self.tag_idx)
                .iter()
                .map(|&c| c as usize)
                .collect();
            return Ok(ElementList {
                doc: self.doc.clone_ref(py),
                indices,
            });
        }

        // Fallback: full XPath
        let xpath = et_path_to_xpath(path);
        self.xpath(py, &xpath)
    }

    /// Iterate over matching subelements (ElementTree API).
    #[pyo3(signature = (path, _namespaces=None))]
    fn iterfind(
        &self,
        py: Python<'_>,
        path: &str,
        _namespaces: Option<&Bound<'_, pyo3::PyAny>>,
    ) -> PyResult<ElementIterator> {
        let list = self.findall(py, path, _namespaces)?;
        let _doc_ref = self.doc.borrow(py);
        Ok(ElementIterator::new(py, &self.doc, list.indices))
    }

    /// Find text of first matching subelement (ElementTree API).
    ///
    /// Uses index-accelerated lookup for the element, then direct_text_first
    /// for the text. No XPath evaluation for simple paths.
    #[pyo3(signature = (path, default=None, _namespaces=None))]
    fn findtext(
        &self,
        py: Python<'_>,
        path: &str,
        default: Option<&str>,
        _namespaces: Option<&Bound<'_, pyo3::PyAny>>,
    ) -> PyResult<Option<Py<PyString>>> {
        let doc = self.doc.borrow(py);
        let index = doc.index();

        // Find the element using fast paths
        let found = if is_simple_tag(path) {
            index
                .child_slice(self.tag_idx)
                .iter()
                .find(|&&c| index.tag_name_eq(c as usize, path))
                .map(|&c| c as usize)
        } else if let Some(tag) = descendant_tag_name(path) {
            first_descendant_by_name(index, self.tag_idx, tag)
        } else {
            // XPath fallback
            let xpath = et_path_to_xpath(path);
            let nodes = index
                .xpath_from(&xpath, self.tag_idx)
                .map_err(|e| PyValueError::new_err(e.to_string()))?;
            nodes.into_iter().find_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            })
        };

        match found {
            Some(idx) => {
                // Element exists: return text or "" (matching stdlib behavior)
                let text = index.direct_text_first(idx).unwrap_or("");
                let decoded = XmlIndex::decode_entities(text);
                Ok(Some(PyString::new(py, &decoded).unbind()))
            }
            None => Ok(default.map(|s| PyString::new(py, s).unbind())),
        }
    }

    /// Parent element, or None for root.
    fn getparent(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        // Uses upstream parent() directly
        index
            .parent(self.tag_idx)
            .map(|p| Document::make_element_borrowed(py, &self.doc, &doc, p))
    }

    /// Next sibling element, or None.
    fn getnext(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let pos = index.child_position(self.tag_idx)?;
        let parent = index.parent(self.tag_idx)?;
        index
            .child_at(parent, pos + 1)
            .map(|idx| Document::make_element_borrowed(py, &self.doc, &doc, idx))
    }

    /// Previous sibling element, or None.
    fn getprevious(&self, py: Python<'_>) -> Option<Element> {
        let doc = self.doc.borrow(py);
        let index = doc.index();
        let pos = index.child_position(self.tag_idx)?;
        if pos == 0 {
            return None;
        }
        let parent = index.parent(self.tag_idx)?;
        index
            .child_at(parent, pos - 1)
            .map(|idx| Document::make_element_borrowed(py, &self.doc, &doc, idx))
    }

    /// Serialize this element to an XML string.
    fn tostring(&self, py: Python<'_>) -> Py<PyString> {
        let doc = self.doc.borrow(py);
        let raw = doc.index().raw_xml(self.tag_idx);
        PyString::new(py, raw).unbind()
    }

    /// Serialize this element to C14N canonical XML.
    ///
    /// Attributes sorted, empty elements expanded. Single Rust call.
    fn c14n(&self, py: Python<'_>) -> Py<PyString> {
        let doc = self.doc.borrow(py);
        let result = doc.index().canonicalize(self.tag_idx);
        PyString::new(py, &result).unbind()
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
    fn extend(&self, _elements: &Bound<'_, pyo3::PyAny>) -> PyResult<()> {
        Err(readonly_error())
    }

    /// Not supported. Raises TypeError (simdxml elements are read-only).
    fn makeelement(
        &self,
        _tag: &str,
        _attrib: &Bound<'_, pyo3::PyAny>,
    ) -> PyResult<Element> {
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
// ElementIterator — lazy, creates Elements on demand in __next__
// ---------------------------------------------------------------------------

#[pyclass]
struct ElementIterator {
    doc: Py<Document>,
    indices: Vec<usize>,
    pos: usize,
}

impl ElementIterator {
    fn new(py: Python<'_>, doc: &Py<Document>, indices: Vec<usize>) -> Self {
        ElementIterator {
            doc: doc.clone_ref(py),
            indices,
            pos: 0,
        }
    }
}

#[pymethods]
impl ElementIterator {
    fn __iter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    fn __next__(&mut self, py: Python<'_>) -> Option<Element> {
        if self.pos < self.indices.len() {
            let idx = self.indices[self.pos];
            self.pos += 1;
            // Single borrow per __next__: look up interned tag + create Element
            let doc_ref = self.doc.borrow(py);
            let index = doc_ref.index();
            let cached_tag = doc_ref.interned_tag(py, index, idx);
            Some(Element {
                doc: self.doc.clone_ref(py),
                tag_idx: idx,
                cached_tag,
            })
        } else {
            None
        }
    }

    fn __len__(&self) -> usize {
        self.indices.len() - self.pos
    }
}

// ---------------------------------------------------------------------------
// ElementList — lazy sequence returned by xpath/eval
// ---------------------------------------------------------------------------

/// A lazy list of elements. Holds one Document reference and a Vec of tag
/// indices. Element objects are created on demand when accessed.
#[pyclass(sequence)]
struct ElementList {
    doc: Py<Document>,
    indices: Vec<usize>,
}

#[pymethods]
impl ElementList {
    fn __len__(&self) -> usize {
        self.indices.len()
    }

    fn __getitem__(&self, py: Python<'_>, index: isize) -> PyResult<Element> {
        let len = self.indices.len() as isize;
        let i = if index < 0 { len + index } else { index };
        if i < 0 || i >= len {
            return Err(pyo3::exceptions::PyIndexError::new_err(
                "list index out of range",
            ));
        }
        Ok(Document::make_element(
            py,
            &self.doc,
            self.indices[i as usize],
        ))
    }

    fn __iter__(&self, py: Python<'_>) -> ElementIterator {
        let _doc_ref = self.doc.borrow(py);
        ElementIterator::new(py, &self.doc, self.indices.clone())
    }

    fn __bool__(&self) -> bool {
        !self.indices.is_empty()
    }

    fn __eq__(&self, _py: Python<'_>, other: &Bound<'_, pyo3::PyAny>) -> bool {
        if let Ok(list) = other.cast::<pyo3::types::PyList>() {
            if list.len() != self.indices.len() {
                return false;
            }
            for (i, item) in list.iter().enumerate() {
                if let Ok(elem) = item.cast::<Element>() {
                    let elem_ref = elem.borrow();
                    if elem_ref.tag_idx != self.indices[i] || !elem_ref.doc.is(&self.doc) {
                        return false;
                    }
                } else {
                    return false;
                }
            }
            return true;
        }
        if let Ok(other_list) = other.cast::<ElementList>() {
            let other_ref = other_list.borrow();
            return self.doc.is(&other_ref.doc) && self.indices == other_ref.indices;
        }
        false
    }

    fn __repr__(&self) -> String {
        format!("ElementList(len={})", self.indices.len())
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

    /// Evaluate and return matching elements as an ElementList (lazy).
    fn eval(slf: &Bound<'_, Self>, doc: &Bound<'_, Document>) -> PyResult<ElementList> {
        let this = slf.borrow();
        let doc_ref = doc.borrow();
        let doc_py: Py<Document> = doc.clone().unbind();
        let index = doc_ref.index();
        let nodes = this
            .inner
            .eval(index)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;

        let indices: Vec<usize> = nodes
            .into_iter()
            .filter_map(|n| match n {
                XPathNode::Element(idx) => Some(idx),
                _ => None,
            })
            .collect();
        Ok(ElementList {
            doc: doc_py,
            indices,
        })
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

/// Check if a path is a simple bare tag name (no axes, predicates, wildcards).
/// Conservative: excludes namespaced tags ({ns}tag, ns:tag) and anything
/// that could be a complex ET path. Falls through to XPath for those cases.
fn is_simple_tag(path: &str) -> bool {
    !path.is_empty()
        && !path.contains('/')
        && !path.contains('[')
        && !path.contains('(')
        && !path.contains('*')
        && !path.contains('.')
        && !path.contains(':')
        && !path.contains('@')
        && !path.contains('{')
}

/// Extract tag name from `.//tag` or `//tag` patterns.
/// Returns None for complex paths.
fn descendant_tag_name(path: &str) -> Option<&str> {
    let rest = path.strip_prefix(".//").or_else(|| path.strip_prefix("//"))?;
    if is_simple_tag(rest) {
        Some(rest)
    } else {
        None
    }
}

/// Find first descendant with a given tag name using the posting list.
/// O(log n) via binary search on the sorted posting list.
fn first_descendant_by_name(index: &XmlIndex<'_>, parent_idx: usize, tag: &str) -> Option<usize> {
    let close = index.matching_close(parent_idx).unwrap_or(parent_idx);
    let posting = index.tags_by_name(tag);
    if posting.is_empty() {
        return None;
    }
    // Binary search for first posting entry > parent_idx
    let start = posting.partition_point(|&p| (p as usize) <= parent_idx);
    for &p in &posting[start..] {
        let idx = p as usize;
        if idx > close {
            break;
        }
        return Some(idx);
    }
    None
}

/// Find all descendants with a given tag name using the posting list.
/// O(k + log n) where k = number of matches.
fn descendants_by_name(index: &XmlIndex<'_>, parent_idx: usize, tag: &str) -> Vec<usize> {
    let close = index.matching_close(parent_idx).unwrap_or(parent_idx);
    let posting = index.tags_by_name(tag);
    if posting.is_empty() {
        return Vec::new();
    }
    let start = posting.partition_point(|&p| (p as usize) <= parent_idx);
    posting[start..]
        .iter()
        .take_while(|&&p| (p as usize) <= close)
        .map(|&p| p as usize)
        .collect()
}

/// Convert ElementTree path syntax to XPath.
///
/// ET paths are a limited subset of XPath:
/// - `tag` → `./tag` (child)
/// - `{ns}tag` → pass through
/// - `*` → `*` (wildcard)
/// - `.` → `.` (self)
/// - `..` → `..` (parent)
/// - `.//tag` → `.//tag` (descendant)
/// - `//tag` → `.//tag` (descendant from context)
/// - `[tag]` → `[tag]` (child element predicate)
/// - `[@attrib]` → `[@attrib]` (attribute predicate)
/// - `[tag='text']` → `[tag='text']` (child text predicate)
fn et_path_to_xpath(path: &str) -> String {
    // Already valid XPath (starts with / or ( or .)
    if path.starts_with('/') || path.starts_with('(') {
        if path.starts_with("//") {
            // ET `//tag` means descendant from context → `.//tag`
            return format!(".{path}");
        }
        return path.to_string();
    }
    if path.starts_with('.') {
        return path.to_string();
    }
    // Bare tag name or path without leading dot → make relative
    format!("./{path}")
}

fn readonly_error() -> PyErr {
    PyTypeError::new_err(
        "simdxml Elements are read-only. Use xml.etree.ElementTree for XML construction.",
    )
}


// ---------------------------------------------------------------------------
// Module-level functions
// ---------------------------------------------------------------------------

/// Parse XML into a Document.
///
/// Accepts bytes or str. For bytes input, the buffer is used directly (zero-copy).
/// For str input, the string is encoded to UTF-8 bytes.
///
/// Set `parallel=True` to use multi-threaded parsing for large documents
/// (>256KB). Splits SIMD structural indexing across available cores.
#[pyfunction]
#[pyo3(signature = (data, *, parallel=false))]
fn parse(py: Python<'_>, data: &Bound<'_, PyAny>, parallel: bool) -> PyResult<Document> {
    let owner = if data.is_instance_of::<PyBytes>() {
        let backed: PyBackedBytes = data.extract()?;
        DocumentOwner::ZeroCopy(backed)
    } else if let Ok(s) = data.extract::<String>() {
        DocumentOwner::Owned(s.into_bytes())
    } else {
        return Err(PyTypeError::new_err("parse() requires bytes or str"));
    };

    let inner = DocumentInner::try_new(owner, |owner| {
        let mut index = if parallel {
            let threads = std::thread::available_parallelism()
                .map(|n| n.get())
                .unwrap_or(4);
            simdxml::parallel::parse_parallel(owner, threads)
                .map_err(|e| PyValueError::new_err(e.to_string()))?
        } else {
            simdxml::parse(owner).map_err(|e| PyValueError::new_err(e.to_string()))?
        };
        index.ensure_indices();
        index.build_name_index();
        Ok::<_, PyErr>(index)
    })?;

    // Build interned Python strings from upstream's name_table.
    // name_table[id] = (byte_offset, length) into input. We need to resolve
    // these to actual strings. Since input is private, we find one tag per
    // name_id and use tag_name() on it.
    let interned_names = {
        let index = inner.borrow_dependent();
        let n_names = index.name_table.len();
        let mut names: Vec<Py<PyString>> = Vec::with_capacity(n_names);
        let mut found = vec![false; n_names];

        for i in 0..index.tag_count() {
            if index.name_ids.is_empty() {
                break;
            }
            let nid = index.name_ids[i];
            if nid != u16::MAX && (nid as usize) < n_names && !found[nid as usize] {
                found[nid as usize] = true;
                // Ensure we have enough slots
                while names.len() <= nid as usize {
                    names.push(PyString::new(py, "").unbind());
                }
                names[nid as usize] = PyString::new(py, index.tag_name(i)).unbind();
            }
            if found.iter().all(|&f| f) {
                break; // All names found
            }
        }
        names
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

/// Evaluate an XPath expression across multiple documents with bloom prefilter.
///
/// Skips documents that can't match at ~10 GiB/s, then parses only
/// those that might. Returns one list of text results per document.
/// This is the fastest path for ETL workloads over many files.
#[pyfunction]
fn batch_xpath_text(
    py: Python<'_>,
    docs: &Bound<'_, pyo3::types::PyList>,
    expr: &CompiledXPath,
) -> PyResult<Vec<Vec<Py<PyString>>>> {
    let byte_vecs: Vec<Vec<u8>> = docs
        .iter()
        .map(|item| {
            if let Ok(b) = item.cast::<PyBytes>() {
                Ok(b.as_bytes().to_vec())
            } else if let Ok(s) = item.extract::<String>() {
                Ok(s.into_bytes())
            } else {
                Err(PyTypeError::new_err("batch items must be bytes or str"))
            }
        })
        .collect::<PyResult<Vec<_>>>()?;
    let doc_refs: Vec<&[u8]> = byte_vecs.iter().map(|v| v.as_slice()).collect();
    let results = simdxml::batch::eval_batch_text_bloom(&doc_refs, &expr.inner)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|doc_results| {
            doc_results
                .into_iter()
                .map(|s| PyString::new(py, &s).unbind())
                .collect()
        })
        .collect())
}

/// Evaluate an XPath expression across multiple documents in parallel.
///
/// Uses multiple threads for both parsing and evaluation. Best for
/// large batches of medium-to-large documents.
#[pyfunction]
#[pyo3(signature = (docs, expr, max_threads=None))]
fn batch_xpath_text_parallel(
    py: Python<'_>,
    docs: &Bound<'_, pyo3::types::PyList>,
    expr: &CompiledXPath,
    max_threads: Option<usize>,
) -> PyResult<Vec<Vec<Py<PyString>>>> {
    let byte_vecs: Vec<Vec<u8>> = docs
        .iter()
        .map(|item| {
            if let Ok(b) = item.cast::<PyBytes>() {
                Ok(b.as_bytes().to_vec())
            } else if let Ok(s) = item.extract::<String>() {
                Ok(s.into_bytes())
            } else {
                Err(PyTypeError::new_err("batch items must be bytes or str"))
            }
        })
        .collect::<PyResult<Vec<_>>>()?;
    let doc_refs: Vec<&[u8]> = byte_vecs.iter().map(|v| v.as_slice()).collect();
    let threads = max_threads.unwrap_or_else(|| {
        std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(4)
    });
    let results = simdxml::batch::eval_batch_parallel(&doc_refs, &expr.inner, threads)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|doc_results| {
            doc_results
                .into_iter()
                .map(|s| PyString::new(py, &s).unbind())
                .collect()
        })
        .collect())
}

// ---------------------------------------------------------------------------
// Module
// ---------------------------------------------------------------------------

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Document>()?;
    m.add_class::<Element>()?;
    m.add_class::<ElementList>()?;
    m.add_class::<CompiledXPath>()?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(compile, m)?)?;
    m.add_function(wrap_pyfunction!(batch_xpath_text, m)?)?;
    m.add_function(wrap_pyfunction!(batch_xpath_text_parallel, m)?)?;
    Ok(())
}
