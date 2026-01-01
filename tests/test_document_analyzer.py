"""Tests for the Document Analyzer."""

import pytest

from meiliscan.analyzers.document_analyzer import DocumentAnalyzer
from meiliscan.models.finding import FindingCategory, FindingSeverity
from meiliscan.models.index import IndexData, IndexSettings, IndexStats


class TestDocumentAnalyzer:
    """Tests for DocumentAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> DocumentAnalyzer:
        """Create a document analyzer instance."""
        return DocumentAnalyzer()

    @pytest.fixture
    def basic_index(self) -> IndexData:
        """Create a basic index with sample documents."""
        return IndexData(
            uid="test_index",
            primaryKey="id",
            settings=IndexSettings(),
            stats=IndexStats(
                numberOfDocuments=100,
                fieldDistribution={"id": 100, "title": 100, "description": 100},
            ),
            sample_documents=[
                {"id": 1, "title": "Test", "description": "A test document"},
                {"id": 2, "title": "Another", "description": "Another document"},
            ],
        )

    def test_analyzer_name(self, analyzer):
        """Test analyzer name property."""
        assert analyzer.name == "documents"

    def test_no_findings_without_sample_documents(self, analyzer):
        """Test that analyzer returns empty when no sample documents."""
        index = IndexData(uid="test", sample_documents=[])
        findings = analyzer.analyze(index)
        assert len(findings) == 0

    def test_large_documents_detection_d001(self, analyzer):
        """Test detection of large documents (D001)."""
        # Create documents that exceed 10KB average
        large_content = "x" * 15000  # ~15KB each
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "content": large_content},
                {"id": 2, "content": large_content},
            ],
        )

        findings = analyzer.analyze(index)
        d001_findings = [f for f in findings if f.id == "MEILI-D001"]
        assert len(d001_findings) == 1
        assert d001_findings[0].severity == FindingSeverity.WARNING
        assert d001_findings[0].category == FindingCategory.DOCUMENTS

    def test_no_large_documents_with_small_docs(self, analyzer, basic_index):
        """Test no D001 finding with small documents."""
        findings = analyzer.analyze(basic_index)
        d001_findings = [f for f in findings if f.id == "MEILI-D001"]
        assert len(d001_findings) == 0

    def test_inconsistent_schema_detection_d002(self, analyzer):
        """Test detection of inconsistent schema (D002)."""
        # Create documents with inconsistent fields
        # Need at least 10 documents for this check
        docs = [{"id": i, "title": f"Doc {i}"} for i in range(12)]
        # Add extra field to ~50% of documents
        for i in range(6):
            docs[i]["extra_field"] = "value"

        index = IndexData(uid="test", sample_documents=docs)

        findings = analyzer.analyze(index)
        d002_findings = [f for f in findings if f.id == "MEILI-D002"]
        assert len(d002_findings) == 1
        assert d002_findings[0].severity == FindingSeverity.WARNING
        assert "extra_field" in d002_findings[0].current_value

    def test_no_inconsistent_schema_with_uniform_docs(self, analyzer, basic_index):
        """Test no D002 finding with uniform documents."""
        findings = analyzer.analyze(basic_index)
        d002_findings = [f for f in findings if f.id == "MEILI-D002"]
        assert len(d002_findings) == 0

    def test_deep_nesting_detection_d003(self, analyzer):
        """Test detection of deeply nested documents (D003)."""
        deeply_nested = {
            "id": 1,
            "level1": {"level2": {"level3": {"level4": {"value": "deep"}}}},
        }
        index = IndexData(uid="test", sample_documents=[deeply_nested])

        findings = analyzer.analyze(index)
        d003_findings = [f for f in findings if f.id == "MEILI-D003"]
        assert len(d003_findings) == 1
        assert d003_findings[0].severity == FindingSeverity.WARNING
        assert d003_findings[0].current_value > 3

    def test_no_deep_nesting_with_flat_docs(self, analyzer, basic_index):
        """Test no D003 finding with flat documents."""
        findings = analyzer.analyze(basic_index)
        d003_findings = [f for f in findings if f.id == "MEILI-D003"]
        assert len(d003_findings) == 0

    def test_large_arrays_detection_d004(self, analyzer):
        """Test detection of large array fields (D004)."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "tags": list(range(100))},
                {"id": 2, "tags": list(range(80))},
            ],
        )

        findings = analyzer.analyze(index)
        d004_findings = [f for f in findings if f.id == "MEILI-D004"]
        assert len(d004_findings) == 1
        assert d004_findings[0].severity == FindingSeverity.WARNING

    def test_no_large_arrays_with_small_arrays(self, analyzer):
        """Test no D004 finding with small arrays."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "tags": ["a", "b", "c"]},
                {"id": 2, "tags": ["x", "y"]},
            ],
        )

        findings = analyzer.analyze(index)
        d004_findings = [f for f in findings if f.id == "MEILI-D004"]
        assert len(d004_findings) == 0

    def test_markup_content_detection_d005(self, analyzer):
        """Test detection of HTML/Markdown in text fields (D005)."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "content": "<p>This has <strong>HTML</strong> content</p>"},
                {
                    "id": 2,
                    "content": "# Markdown Header\n\nThis is [a link](http://example.com)",
                },
            ],
        )

        findings = analyzer.analyze(index)
        d005_findings = [f for f in findings if f.id == "MEILI-D005"]
        assert len(d005_findings) == 1
        assert d005_findings[0].severity == FindingSeverity.SUGGESTION
        assert "content" in d005_findings[0].current_value

    def test_no_markup_with_plain_text(self, analyzer, basic_index):
        """Test no D005 finding with plain text."""
        findings = analyzer.analyze(basic_index)
        d005_findings = [f for f in findings if f.id == "MEILI-D005"]
        assert len(d005_findings) == 0

    def test_empty_fields_detection_d006(self, analyzer):
        """Test detection of empty field values (D006)."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "title": "Has title", "subtitle": ""},
                {"id": 2, "title": "Also title", "subtitle": None},
                {"id": 3, "title": "Third", "subtitle": ""},
                {"id": 4, "title": "Fourth", "subtitle": ""},
            ],
        )

        findings = analyzer.analyze(index)
        d006_findings = [f for f in findings if f.id == "MEILI-D006"]
        assert len(d006_findings) == 1
        assert d006_findings[0].severity == FindingSeverity.INFO
        # subtitle is empty in 3 of 4 documents (75%)
        assert "subtitle" in d006_findings[0].current_value

    def test_no_empty_fields_with_complete_data(self, analyzer, basic_index):
        """Test no D006 finding with complete data."""
        findings = analyzer.analyze(basic_index)
        d006_findings = [f for f in findings if f.id == "MEILI-D006"]
        assert len(d006_findings) == 0

    def test_mixed_types_detection_d007(self, analyzer):
        """Test detection of mixed types in fields (D007)."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "value": "string"},
                {"id": 2, "value": 123},
                {"id": 3, "value": "another string"},
            ],
        )

        findings = analyzer.analyze(index)
        d007_findings = [f for f in findings if f.id == "MEILI-D007"]
        assert len(d007_findings) == 1
        assert d007_findings[0].severity == FindingSeverity.WARNING

    def test_no_mixed_types_with_int_float(self, analyzer):
        """Test no D007 finding when only mixing int and float."""
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "price": 10},
                {"id": 2, "price": 10.5},
                {"id": 3, "price": 20},
            ],
        )

        findings = analyzer.analyze(index)
        d007_findings = [f for f in findings if f.id == "MEILI-D007"]
        assert len(d007_findings) == 0

    def test_no_mixed_types_with_uniform_types(self, analyzer, basic_index):
        """Test no D007 finding with uniform types."""
        findings = analyzer.analyze(basic_index)
        d007_findings = [f for f in findings if f.id == "MEILI-D007"]
        assert len(d007_findings) == 0

    def test_long_text_detection_d008(self, analyzer):
        """Test detection of very long text fields (D008)."""
        very_long_text = "x" * 70000  # > 65535 chars
        index = IndexData(
            uid="test",
            sample_documents=[
                {"id": 1, "content": very_long_text},
            ],
        )

        findings = analyzer.analyze(index)
        d008_findings = [f for f in findings if f.id == "MEILI-D008"]
        assert len(d008_findings) == 1
        assert d008_findings[0].severity == FindingSeverity.SUGGESTION
        assert "content" in d008_findings[0].current_value

    def test_no_long_text_with_normal_content(self, analyzer, basic_index):
        """Test no D008 finding with normal length content."""
        findings = analyzer.analyze(basic_index)
        d008_findings = [f for f in findings if f.id == "MEILI-D008"]
        assert len(d008_findings) == 0

    def test_get_max_depth_flat(self, analyzer):
        """Test _get_max_depth with flat object."""
        obj = {"a": 1, "b": "string", "c": True}
        assert analyzer._get_max_depth(obj) == 1

    def test_get_max_depth_nested(self, analyzer):
        """Test _get_max_depth with nested object."""
        obj = {"level1": {"level2": {"level3": "value"}}}
        assert analyzer._get_max_depth(obj) == 3

    def test_get_max_depth_with_arrays(self, analyzer):
        """Test _get_max_depth with arrays."""
        obj = {"items": [{"nested": {"deep": "value"}}]}
        assert analyzer._get_max_depth(obj) == 3

    def test_get_max_depth_empty(self, analyzer):
        """Test _get_max_depth with empty structures."""
        assert analyzer._get_max_depth({}) == 0
        assert analyzer._get_max_depth([]) == 0
        assert analyzer._get_max_depth("string") == 0

    def test_html_pattern_matches(self, analyzer):
        """Test that HTML pattern correctly identifies HTML tags."""
        assert analyzer.HTML_PATTERN.search("<p>text</p>") is not None
        assert analyzer.HTML_PATTERN.search("<div class='test'>") is not None
        assert analyzer.HTML_PATTERN.search("no html here") is None

    def test_multiple_findings_combined(self, analyzer):
        """Test that analyzer can return multiple findings."""
        # Create document with multiple issues
        large_nested_doc = {
            "id": 1,
            "content": "<p>" + "x" * 70000 + "</p>",  # Long text with HTML
            "level1": {"level2": {"level3": {"level4": "deep"}}},  # Deep nesting
            "big_array": list(range(100)),  # Large array
        }
        index = IndexData(uid="test", sample_documents=[large_nested_doc])

        findings = analyzer.analyze(index)

        # Should have findings for D001 (large), D003 (deep), D004 (array), D005 (html), D008 (long)
        finding_ids = {f.id for f in findings}
        assert "MEILI-D001" in finding_ids  # Large document
        assert "MEILI-D003" in finding_ids  # Deep nesting
        assert "MEILI-D004" in finding_ids  # Large array
        assert "MEILI-D005" in finding_ids  # HTML content
        assert "MEILI-D008" in finding_ids  # Long text
