# BAB III — METODE PENELITIAN

> Isi bab ini bersandar langsung pada sistem yang dibangun (lihat
> `docs/context-packs/METHODOLOGY.md`); angka dan parameter sudah terverifikasi
> terhadap kode, bukan ingatan. Penanda `> TODO cite:` hanya untuk metode standar yang
> perlu rujukan pustaka — jangan mengarang referensi.

## 3.1 Alur Penelitian

Penelitian ini merupakan studi komparatif-eksperimental yang membandingkan dua sistem
temu-kembali atas korpus regulasi perpajakan Indonesia:

1. **Baseline RAG (hibrida)** — temu-kembali gabungan leksikal+*dense*.
2. **GraphRAG** — *seed* hibrida yang sama, diperluas melalui ekspansi graf atas
   rujukan antar pasal, lalu dipemeringkat-ulang ke dalam anggaran top-K yang sama.

**Keystone komparabilitas.** Kedua sistem menjalani tahap *seeding* yang **identik**
melalui satu titik dispatch, `src/seeding.py::seed_search`. Konsekuensinya, setiap
perbedaan kinerja yang terukur dapat diatribusikan **semata pada tahap graf**, bukan
pada pergeseran *seeding*. Sifat "setara sejak konstruksi" (*comparable by
construction*) inilah tulang punggung metodologis penelitian.

Alur keseluruhan: akuisisi & praproses korpus (3.2) → indeksasi ganda dan pemodelan
graf (3.3) → tahap *seeding* bersama (3.4) → dua sistem yang dibandingkan (3.5, 3.6) →
rancangan dan protokol evaluasi (3.7) → lingkungan implementasi (3.8).

> Catatan pembingkaian (keputusan 2026-07-01): "Baseline RAG" dalam skripsi ini =
> hibrida leksikal+*dense*. Konfigurasi *dense* murni dipertahankan sebagai **lantai
> ablasi** (`USE_HYBRID_SEEDING=False`), bukan sebagai baseline.

## 3.2 Sumber Data dan Praproses

**Akuisisi.** Korpus dikumpulkan dengan *scraping* dari JDIH
(`src/data_acquisition/jdih_scraper.py`) lalu diurai menjadi `articles.json` dan
`regulations.json` (`parser.py`).

**Deduplikasi dan pembersihan** (`src/corpus.py`). Sebanyak 144.329 rekaman pasal
mentah dideduplikasi menjadi **118.966 pasal unik** berdasarkan kunci
`(regulation_id, article_number)`. Aturan dedup: pertahankan teks *batang tubuh*
terpanjang yang **bukan** *penjelasan*. Aturan ini memperbaiki kasus di mana teks
penjelasan (mis. `"Cukup jelas."`) keliru menimpa isi pasal (18.255 dokumen terdampak,
di-*embed* ulang).

**Format ID pasal.** `"<regulation_id>::<article_number>"`, dipakai identik sebagai id
dokumen ChromaDB, `:Article.id` pada Neo4j, dan `gold_article_ids` pada data evaluasi —
sehingga pencocokan antar-komponen konsisten.

**Isu data yang dilaporkan transparan** (tidak diperbaiki; menjadi batas atas kinerja):

- **Tumbukan ID *omnibus*** (~1.157 tersisa): undang-undang omnibus (mis. UU 7/2021
  HPP yang mengubah KUP/PPh/PPN) memakai ulang nomor pasal antar regulasi induk.
- **Kesalahan OCR `O`→`0`** (~0,2% baris, ~287): huruf kapital `O` menggantikan angka
  `0`; merusak pencocokan ID dan meracuni tepi `REFERENCES` (~20 ribu dari ~107 ribu
  tepi yang dicoba tidak terselesaikan). Ditangguhkan karena biaya *re-embedding*.

## 3.3 Ekstraksi, Indeksasi Ganda, dan Pemodelan Graf

Korpus yang sama diindeks ke dua penyimpanan.

**ChromaDB** — koleksi `tax_articles`: 118.966 dokumen pasal, embedding 1024 dimensi
(`qwen3-embedding:0.6b`).

**Neo4j** — dibangun dari korpus dedup yang sama dan **diverifikasi sinkron** dengan
ChromaDB (gold ID resolve 13/13; teks pasal tersampel *byte-identical* antar
penyimpanan).

**Skema graf.**

*Simpul:*
- `Regulation` (id, type, title, year)
- `Article`/`Pasal` (id, text, regulation_id)
- `Concept` (name)

*Relasi:*
- `(Article)-[:BELONGS_TO]->(Regulation)`
- `(Article)-[:REFERENCES]->(Article)` — **tulang punggung ekspansi graf**
- `(Article)-[:AMENDS]->(Article)`
- `(Article)-[:DEFINES]->(Concept)`

**Statistik graf** (rebuild 2026-06-29):

| Elemen | Jumlah |
|---|---|
| `:Article` | 118.966 |
| `:Regulation` | 5.908 (termasuk 549 stub target `AMENDS`) |
| `:Concept` | 9.765 |
| `:BELONGS_TO` | 118.966 |
| `:REFERENCES` | 81.315 (intra + lintas regulasi) |
| `:AMENDS` | 852 |
| `:DEFINES` | 29.661 |

## 3.4 Tahap Seeding Bersama

`seed_search(query, top_k)` memilih strategi berdasarkan `config.USE_HYBRID_SEEDING`
(dibaca saat pemanggilan, sehingga *driver* ablasi dapat mengubahnya dalam proses).

**Pipeline *seeding* hibrida** (bawaan; tanpa indeks BM25 global — hanya *pool* yang
diskor):

1. Kueri *dense* untuk `HYBRID_POOL=200` kandidat teratas (id, teks, kosinus).
2. *Rerank* BM25 atas dokumen *pool* terhadap kueri. Parameter k1=1.5, b=0.75; IDF
   dihitung atas *pool*. Tokenizer mempertahankan digit (agar "Pasal 17", "0,5%"
   tetap bersinyal).
3. **Reciprocal Rank Fusion (RRF)** atas urutan *dense* dan leksikal, `HYBRID_RRF_K=60`
   (konstanta standar, **tidak** ditala pada data evaluasi).
4. Kembalikan top-k hasil fusi.

**Rasional** (diagnosis 2026-07-01): model embedding 0,6b menarik pasal yang tepat ke
*pool* yang dalam tetapi memeringkatnya di bawah ambang top-5; sinyal leksikal
menambatkan istilah yang dikutip ("Pajak Hotel", nama peraturan) yang dikaburkan model
*dense*. Setiap pasal hasil mengangkut `score` (kosinus *dense*, untuk perhitungan
*boost* graf), `fused_score` (RRF), dan `source="hybrid"`.

> TODO cite: Robertson & Zaragoza (BM25); Cormack dkk. 2009 (RRF).

## 3.5 Sistem 1 — Baseline RAG (Hibrida)

`seed_search` (hibrida) → rakit konteks top-5 → generasi dengan `qwen3.5:9b`. Baseline
ini **kuat** (tidak sengaja dilemahkan), sehingga perbandingan terhadap GraphRAG
bersifat konservatif.

## 3.6 Sistem 2 — GraphRAG (Ekspansi Graf)

`src/graph_rag/retriever.py`, tiga tahap:

1. **Seed** — `seed_search` yang identik dengan Sistem 1.
2. **Ekspansi graf** (`_graph_expand`) — dari *seed*, telusuri tepi `REFERENCES` hingga
   `GRAPH_HOP_DEPTH=2` hop (jalur panjang-variabel Cypher). Untuk tiap pasal yang
   dijangkau dicatat: *seed* mana yang menjangkaunya, hop terpendek per *seed*, dan
   derajat `REFERENCES` pasal tersebut.
3. **Pemeringkatan-ulang paritas-ketat** ke anggaran yang sama
   (`GRAPH_CONTEXT_BUDGET == TOP_K_VECTOR = 5`), sehingga tetangga tertaut hanya dapat
   masuk konteks bila mengungguli *seed* yang lemah.

**Skema penilaian:**

```
score(x)  = query_sim(x) + alpha * boost(x)
boost(x)  = ( Σ_{seed s → x} sim(s) / hop(s, x) ) / (1 + log(1 + degree(x)))
```

- **Simetris**: *seed* pun diberi *boost* (sebuah *seed* yang dijangkau *seed* lain
  memperoleh *boost*), sehingga *seed* gold yang relevan tidak tergeser tak adil.
- **Peredaman derajat** (`/(1+log(1+degree))`): *hub* amendemen (mis. UU 1/2022)
  memperoleh *boost* kecil per tautan — memperbaiki regresi versi naif alpha=0.5 (MRR
  test 0,41→0,19) saat *hub* menggeser *seed* gold.
- `alpha=0` mereproduksi baseline persis.
- `GRAPH_RERANK_ALPHA=0.10` (ditala pada split *dev* **hibrida**; 0,15 untuk *dense*).
  **Alpha ditala hanya pada split *dev*, tidak pernah pada *test*.**

*Catatan implementasi:* `gather()` melakukan seluruh I/O yang tak bergantung alpha
(embed, seed, graf, embedding tetangga); `rerank()` murni-Python dan bergantung alpha,
sehingga `scripts/tune_alpha.py` dapat menyapu alpha atas kandidat yang di-*cache*.

## 3.7 Rancangan Evaluasi

**Ground truth** `data/ground_truth/eval.jsonl`: **50 entri terverifikasi** (29
multi-hop, 21 single-hop; 13 multi-hop lintas-regulasi). Tiap baris berformat
`{id, question, gold_article_ids, gold_answer, hop_type, notes}`, ditambatkan verbatim
pada teks sumber dan diverifikasi manual (78 gold ID unik, seluruhnya resolve sebagai
`:Article` Neo4j maupun dokumen ChromaDB; gold mengarah ke *batang tubuh*).
Baris single-hop berfungsi sebagai **kontrol** (graf tidak seharusnya mengangkatnya —
uji spesifisitas).

**Kriteria non-skippability** (kriteria MuSiQue) diberlakukan dalam pengonstruksian:
sebuah baris multi-hop hanya sahih bila menghapus salah satu pasal gold membuat jawaban
salah/tak lengkap; kalau tidak, direklasifikasi single-hop.

**Split *dev/test* dibekukan SEBELUM penalaan** (ADR 0007): `scripts/make_split.py`,
distratifikasi menurut `hop_type`, *seed* 20260701 → **dev=17** (7 single, 10 multi)
dan **test=33** (14 single, 19 multi; 8 multi lintas-regulasi). Penalaan dilakukan di
*dev*, pelaporan di *test*. **Alpha dibekukan (0,10 hibrida / 0,15 *dense*) dan TIDAK
ditala ulang** setelah *re-split* — menjamin pelaporan bebas kebocoran.

**Metrik.** recall@5, precision@5, hit@5, dan MRR terhadap `gold_article_ids`. Setiap
selisih dilaporkan dengan **uji Wilcoxon *signed-rank*** dan **selang kepercayaan 95%
berbasis *bootstrap* berpasangan** (10.000 *resample*) — besar efek + CI, bukan nilai p
semata (himpunan uji berukuran moderat).

**Sisi generasi (RAGAS).** Kualitas jawaban terhadap `gold_answer` diukur dengan
pendekatan *LLM-as-judge* (faithfulness, correctness); *sedang berjalan*, dengan
rencana memakai model penilai berbeda dari generator untuk menghindari bias
*self-judge* (jawaban sudah di-*cache*).

**Harness.** `eval run --hybrid/--alpha/--split` menjalankan rancangan **2×2** —
(seed *dense* vs hibrida) × (dengan vs tanpa graf) — pada split *test*; tiap baris
hasil dicap `meta={seeding, alpha, split}` demi keterlacakan.

> TODO cite: Trivedi dkk. 2022 (MuSiQue / non-skippability); definisi metrik IR
> (Manning dkk.); Wilcoxon 1945; metode bootstrap (Efron); RAGAS (Es dkk. 2023).

## 3.8 Lingkungan Implementasi

- **Bahasa & pustaka:** Python; ChromaDB (basis vektor); Neo4j (driver resmi, Cypher).
- **Ollama:** `qwen3.5:9b` (LLM generasi, `num_ctx`=16384); `qwen3-embedding:0.6b`
  (embedding, 1024 dimensi).
- **Konfigurasi temu-kembali:** `TOP_K_VECTOR=5`, `GRAPH_HOP_DEPTH=2`,
  `HYBRID_POOL=200`, `HYBRID_RRF_K=60`.
- **Kredensial** Neo4j dibaca dari `.env` (tidak pernah di-*commit*).
