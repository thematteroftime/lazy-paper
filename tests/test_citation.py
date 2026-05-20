from llm.citation import process_text, CitationMode


def test_remove_mode_strips_markers():
    text = "Energy density reaches 8.6 J/cm³ [span:doc_1:42-58]."
    out = process_text(text, mode=CitationMode.REMOVE,
                       sources=[{"document_id": "doc_1", "link": None}])
    assert "[span:" not in out
    assert "8.6 J/cm³" in out


def test_keep_mode_preserves_markers():
    text = "Cited result [span:doc_1:0-10]."
    out = process_text(text, mode=CitationMode.KEEP,
                       sources=[{"document_id": "doc_1", "link": None}])
    assert "[span:doc_1:0-10]" in out


def test_hyperlink_mode_emits_anchors():
    text = "See [span:doc_1:0-5]."
    out = process_text(text, mode=CitationMode.HYPERLINK,
                       sources=[{"document_id": "doc_1",
                                  "link": "runs/x/s03_chapter/chapters/doc_1"}])
    # Output is a list of segments: plain text + hyperlink dicts
    assert any(isinstance(seg, dict) and seg.get("href") for seg in out)
