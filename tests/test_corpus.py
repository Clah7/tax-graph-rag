"""
test_corpus.py — Unit tests for the shared dedup rule (ADR 0006).

Verifies the canonical-record selection that both ingestions now rely on:
prefer the longest non-penjelasan batang tubuh, drop penjelasan/trivial stubs,
and never silently change the set of IDs.
"""
import unittest

from src.corpus import _is_penjelasan, _pick, dedup_articles


def _rec(reg, num, content):
    return {"regulation_id": reg, "article_number": num, "content": content}


class TestPenjelasanHeuristic(unittest.TestCase):
    def test_flags_ayat_opening(self):
        self.assertTrue(_is_penjelasan("Ayat (1) Yang dimaksud dengan ..."))

    def test_flags_cukup_jelas(self):
        self.assertTrue(_is_penjelasan("Cukup jelas."))

    def test_flags_huruf_and_angka(self):
        self.assertTrue(_is_penjelasan("Huruf a Dalam rangka ..."))
        self.assertTrue(_is_penjelasan("Angka 2 Konosemen adalah ..."))

    def test_batang_tubuh_not_flagged(self):
        self.assertFalse(_is_penjelasan("(1) Tarif pajak yang diterapkan ..."))


class TestPick(unittest.TestCase):
    def test_prefers_batang_tubuh_over_last_penjelasan(self):
        # mirrors UU 7/2021::9 — body first, "Cukup jelas." stub last
        body = "(1) " + "Untuk menentukan besarnya Penghasilan Kena Pajak " * 5
        recs = [_rec("UU 7 TAHUN 2021", "9", body),
                _rec("UU 7 TAHUN 2021", "9", "Cukup jelas.")]
        self.assertEqual(_pick(recs)["content"], body)

    def test_prefers_longest_when_two_bodies(self):
        short = "(1) " + "x" * 50
        long = "(1) " + "y" * 500
        recs = [_rec("R", "1", short), _rec("R", "1", long)]
        self.assertEqual(_pick(recs)["content"], long)

    def test_falls_back_to_longest_when_all_penjelasan(self):
        recs = [_rec("R", "1", "Cukup jelas."),
                _rec("R", "1", "Ayat (1) " + "z" * 80)]
        # no usable batang tubuh -> longest non-empty wins
        self.assertTrue(_pick(recs)["content"].startswith("Ayat (1)"))

    def test_keeps_last_when_all_empty(self):
        recs = [_rec("R", "1", ""), _rec("R", "1", "   ")]
        self.assertIs(_pick(recs), recs[-1])


class TestDedupArticles(unittest.TestCase):
    def test_one_record_per_id_and_stable_order(self):
        raw = [
            _rec("A", "1", "(1) " + "a" * 40),
            _rec("A", "1", "Cukup jelas."),
            _rec("B", "2", "(1) " + "b" * 40),
        ]
        out = dedup_articles(raw)
        self.assertEqual([r["regulation_id"] for r in out], ["A", "B"])
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]["content"].startswith("(1)"))

    def test_no_id_dropped(self):
        raw = [_rec("A", "1", "x" * 40), _rec("A", "2", "y" * 40)]
        out = dedup_articles(raw)
        self.assertEqual({(r["regulation_id"], r["article_number"]) for r in out},
                         {("A", "1"), ("A", "2")})


if __name__ == "__main__":
    unittest.main()
