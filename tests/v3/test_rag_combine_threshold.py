"""Plan #23: RAG combine path no longer splices weakly-related chunks.

The retrieval threshold (~0.50) admits loosely-related chunks, so the old combine-2
path could glue a 0.51-similarity chunk onto the answer. A second chunk is now only
combined when it is both ≥ 0.60 AND within 0.10 of the top chunk.

Offline — exercises _format_rag_answer directly.
"""

import unittest

from app.tools.v2.get_faq_answer import _format_rag_answer


def _chunk(text, sim, sid):
    return {"text": text, "similarity": sim, "source_type": "faq", "source_id": sid}


class TestRagCombineThreshold(unittest.TestCase):

    def test_single_high_confidence_returns_top_only(self):
        out = _format_rag_answer("x", [_chunk("TOP", 0.80, 1), _chunk("OTHER", 0.79, 2)])
        self.assertEqual(out, "TOP")

    def test_weak_second_chunk_excluded(self):
        # top 0.66, second 0.52 (< 0.60) → second dropped.
        out = _format_rag_answer("x", [_chunk("TOP", 0.66, 1), _chunk("WEAK", 0.52, 2)])
        self.assertEqual(out, "TOP")
        self.assertNotIn("WEAK", out)

    def test_far_second_chunk_excluded(self):
        # second 0.61 (≥ 0.60) but 0.13 below top 0.74 (> 0.10 gap) → dropped.
        out = _format_rag_answer("x", [_chunk("TOP", 0.74, 1), _chunk("FAR", 0.61, 2)])
        self.assertEqual(out, "TOP")

    def test_strong_close_second_chunk_combined(self):
        # second 0.65 ≥ 0.60 and within 0.10 of top 0.70 → combined.
        out = _format_rag_answer("x", [_chunk("TOP", 0.70, 1), _chunk("STRONG", 0.65, 2)])
        self.assertIn("TOP", out)
        self.assertIn("STRONG", out)

    def test_at_most_two_chunks(self):
        chunks = [_chunk("TOP", 0.70, 1), _chunk("A", 0.69, 2), _chunk("B", 0.68, 3)]
        out = _format_rag_answer("x", chunks)
        self.assertEqual(len(out.split("\n\n")), 2)

    def test_same_source_not_duplicated(self):
        # strong+close but SAME source as top → not added.
        out = _format_rag_answer("x", [_chunk("TOP", 0.70, 1), _chunk("DUP", 0.69, 1)])
        self.assertEqual(out, "TOP")


if __name__ == "__main__":
    unittest.main()
