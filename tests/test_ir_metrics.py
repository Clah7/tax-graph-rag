"""
test_ir_metrics.py — Hand-computed unit tests for the IR metric functions.

These metrics are the thesis's primary measuring instrument (did the system
retrieve the correct Pasal?). A silent bug here would invalidate the
Baseline-vs-GraphRAG comparison, so every value below is computed by hand and
asserted exactly.

Run:
    python -m unittest tests.test_ir_metrics
"""
import unittest

from src.evaluation.ir_metrics import (
    hit_at_k,
    mrr,
    precision_at_k,
    recall_at_k,
    score_row,
)


class TestRecallAtK(unittest.TestCase):
    # gold has 2 items; retrieved interleaves them at ranks 2 and 4.
    GOLD = ["a", "b"]
    RETRIEVED = ["x", "a", "y", "b", "z"]

    def test_recall_at_1_no_hit(self):
        # top-1 = {x}; 0 of 2 gold found
        self.assertEqual(recall_at_k(self.GOLD, self.RETRIEVED, 1), 0.0)

    def test_recall_at_3_partial(self):
        # top-3 = {x,a,y}; 1 of 2 gold found
        self.assertEqual(recall_at_k(self.GOLD, self.RETRIEVED, 3), 0.5)

    def test_recall_at_5_full(self):
        # top-5 contains both gold
        self.assertEqual(recall_at_k(self.GOLD, self.RETRIEVED, 5), 1.0)

    def test_recall_empty_gold(self):
        self.assertEqual(recall_at_k([], self.RETRIEVED, 5), 0.0)

    def test_recall_k_exceeds_retrieved(self):
        # only "a" retrieved, single gold -> full recall
        self.assertEqual(recall_at_k(["a"], ["a"], 5), 1.0)

    def test_recall_ignores_order_of_gold(self):
        self.assertEqual(
            recall_at_k(["b", "a"], self.RETRIEVED, 3),
            recall_at_k(["a", "b"], self.RETRIEVED, 3),
        )

    def test_recall_dedupes_retrieved(self):
        # duplicate gold hit in top-k must not exceed 1.0
        self.assertEqual(recall_at_k(["a"], ["a", "a", "a"], 3), 1.0)


class TestPrecisionAtK(unittest.TestCase):
    GOLD = ["a", "b"]
    RETRIEVED = ["x", "a", "y", "b", "z"]

    def test_precision_at_1_no_hit(self):
        self.assertEqual(precision_at_k(self.GOLD, self.RETRIEVED, 1), 0.0)

    def test_precision_at_3(self):
        # top-3 = {x,a,y}; 1 hit / 3
        self.assertAlmostEqual(precision_at_k(self.GOLD, self.RETRIEVED, 3), 1 / 3)

    def test_precision_at_5(self):
        # 2 hits / 5
        self.assertEqual(precision_at_k(self.GOLD, self.RETRIEVED, 5), 0.4)

    def test_precision_k_zero(self):
        self.assertEqual(precision_at_k(self.GOLD, self.RETRIEVED, 0), 0.0)

    def test_precision_k_negative(self):
        self.assertEqual(precision_at_k(self.GOLD, self.RETRIEVED, -1), 0.0)

    def test_precision_empty_retrieved(self):
        self.assertEqual(precision_at_k(self.GOLD, [], 5), 0.0)

    def test_precision_denominator_caps_at_retrieved_len(self):
        # 1 hit, only 1 retrieved, k=5 -> divide by min(5,1)=1, not 5
        self.assertEqual(precision_at_k(["a"], ["a"], 5), 1.0)


class TestMRR(unittest.TestCase):
    def test_first_gold_at_rank_2(self):
        self.assertEqual(mrr(["a", "b"], ["x", "a", "y", "b"]), 0.5)

    def test_first_gold_at_rank_1(self):
        self.assertEqual(mrr(["a"], ["a", "b", "c"]), 1.0)

    def test_first_gold_at_rank_3(self):
        self.assertAlmostEqual(mrr(["c"], ["a", "b", "c"]), 1 / 3)

    def test_no_gold_retrieved(self):
        self.assertEqual(mrr(["z"], ["a", "b", "c"]), 0.0)

    def test_empty_gold(self):
        self.assertEqual(mrr([], ["a", "b"]), 0.0)

    def test_empty_retrieved(self):
        self.assertEqual(mrr(["a"], []), 0.0)

    def test_uses_earliest_hit(self):
        # both gold present; rank of the earliest (rank 2) wins
        self.assertEqual(mrr(["b", "d"], ["a", "d", "c", "b"]), 0.5)


class TestHitAtK(unittest.TestCase):
    GOLD = ["a", "b"]
    RETRIEVED = ["x", "a", "y", "b", "z"]

    def test_hit_at_1_miss(self):
        self.assertEqual(hit_at_k(self.GOLD, self.RETRIEVED, 1), 0.0)

    def test_hit_at_2(self):
        self.assertEqual(hit_at_k(self.GOLD, self.RETRIEVED, 2), 1.0)

    def test_hit_empty_gold(self):
        self.assertEqual(hit_at_k([], self.RETRIEVED, 5), 0.0)

    def test_hit_no_overlap(self):
        self.assertEqual(hit_at_k(["z"], ["a", "b"], 2), 0.0)


class TestScoreRow(unittest.TestCase):
    def test_keys_present(self):
        out = score_row(["a"], ["a", "b"], k_values=(1, 3))
        self.assertEqual(
            set(out),
            {"mrr", "recall@1", "precision@1", "hit@1",
             "recall@3", "precision@3", "hit@3"},
        )

    def test_perfect_retrieval(self):
        out = score_row(["a"], ["a"], k_values=(1,))
        self.assertEqual(out["mrr"], 1.0)
        self.assertEqual(out["recall@1"], 1.0)
        self.assertEqual(out["precision@1"], 1.0)
        self.assertEqual(out["hit@1"], 1.0)

    def test_complete_miss(self):
        out = score_row(["z"], ["a", "b"], k_values=(1, 2))
        for v in out.values():
            self.assertEqual(v, 0.0)


if __name__ == "__main__":
    unittest.main()
