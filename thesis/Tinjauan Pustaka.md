# BAB II — TINJAUAN PUSTAKA

> **Aturan sitasi (penting).** Seluruh referensi pada bab ini **ditulis tangan** dan
> hanya mengutip sumber yang benar-benar dibaca. Penanda `> TODO cite:` menandai
> tempat sebuah rujukan wajib dilengkapi — **jangan mengarang referensi.** Isi
> penjelasan di bawah bersifat konseptual/teknis dan sudah bersandar pada sistem yang
> dibangun; yang belum ada hanyalah pengait ke literatur formal.

Urutan subbab disusun dari yang fondasional ke yang spesifik: domain → dasar
temu-kembali → RAG → hibrida → graf → GraphRAG → multi-hop → evaluasi → penelitian
terdahulu.

## 2.1 Regulasi Perpajakan Indonesia dan Keterkaitan Antar Pasal

Uraikan hierarki peraturan perpajakan Indonesia (UU → PP → PMK, serta Perpu/PER) dan
pola pendelegasian: norma pokok pada UU, ketentuan pelaksana pada PP, tata cara teknis
pada PMK. Jelaskan fenomena *keterkaitan antar pasal* — satu ketentuan kerap menautkan
beberapa pasal, kerap melintasi batas regulasi, melalui rujukan eksplisit — yang
menjadi sasaran utama GraphRAG. Sebutkan pula karakteristik korpus yang relevan bagi
pemodelan: undang-undang *omnibus* yang memakai ulang nomor pasal antar regulasi induk,
serta pemisahan *batang tubuh* vs *penjelasan*.

> TODO cite: sumber hukum tata urutan perundang-undangan (mis. UU 12/2011); literatur
> kompleksitas/legal-informatics regulasi perpajakan Indonesia.

## 2.2 Temu-Kembali Informasi: Leksikal (BM25) dan Dense (Embedding)

Jelaskan dua paradigma temu-kembali. **Leksikal**: pencocokan istilah dengan pembobotan
BM25 (parameter k1, b; IDF), kuat pada istilah yang dikutip persis (nama peraturan,
"Pajak Hotel", nomor pasal). **Dense**: representasi teks sebagai vektor embedding dan
pencarian berbasis kemiripan kosinus, kuat pada kedekatan semantik namun dapat
mengaburkan istilah spesifik. Kontras inilah yang memotivasi pendekatan hibrida
(subbab 2.5).

> TODO cite: Robertson & Zaragoza (BM25 / Okapi); Karpukhin dkk. (Dense Passage
> Retrieval) atau sumber dense retrieval yang dibaca.

## 2.3 Model Bahasa Besar (LLM) dan Embedding

Jelaskan model bahasa besar (LLM) berbasis Transformer dan perannya dalam menghasilkan
jawaban dari konteks, serta model *embedding* yang memetakan teks ke ruang vektor.
Kaitkan dengan implementasi: LLM generasi `qwen3.5:9b` dan model embedding
`qwen3-embedding:0.6b` (1024 dimensi) yang dilayani secara lokal melalui Ollama.
Sorot keterbatasan model embedding kecil: mengenali dokumen yang tepat namun
memeringkatnya kurang tajam (dasar diagnosis pada BAB I/IV).

> TODO cite: Vaswani dkk. (Transformer); sumber embedding teks / sentence embeddings.

## 2.4 Retrieval-Augmented Generation (RAG)

Definisikan RAG: menambatkan (*ground*) keluaran LLM pada dokumen yang ditemukan dari
korpus, alih-alih hanya mengandalkan parameter model — mengurangi halusinasi dan
memungkinkan jawaban atas korpus yang tidak terlihat saat pelatihan. Uraikan pipeline
umum: *indexing* → *retrieval* → *augmentation* → *generation*. Posisikan tahap
temu-kembali (*seeding*) sebagai penentu batas atas kualitas jawaban.

> TODO cite: Lewis dkk. 2020 (RAG); survei RAG bila digunakan.

## 2.5 Temu-Kembali Hibrida dan Reciprocal Rank Fusion (RRF)

Jelaskan penggabungan sinyal leksikal dan dense. Uraikan **Reciprocal Rank Fusion
(RRF)** sebagai metode fusi peringkat yang menjumlahkan `1/(k + rank)` antar daftar,
dengan konstanta `k` (di sini 60, nilai standar yang tidak ditala pada data evaluasi).
Kaitkan dengan rancangan sistem: kumpulan (*pool*) top-200 dense di-*rerank* dengan BM25
lalu difusikan RRF, sehingga istilah yang dikutip kembali terangkat ke anggaran top-K.

> TODO cite: Cormack dkk. 2009 (Reciprocal Rank Fusion); literatur hybrid retrieval.

## 2.6 Basis Data Graf dan Neo4j

Jelaskan model data graf berlabel (*labeled property graph*): simpul, relasi,
properti; keunggulannya untuk data yang kaya relasi. Perkenalkan **Neo4j** dan bahasa
kueri **Cypher**, termasuk *variable-length path* untuk penelusuran multi-hop. Kaitkan
dengan skema yang dipakai: simpul `Regulation`, `Article`/`Pasal`, `Concept`; relasi
`BELONGS_TO`, `REFERENCES`, `AMENDS`, `DEFINES` — dengan `REFERENCES` sebagai tulang
punggung ekspansi graf.

> TODO cite: dokumentasi/《buku》Neo4j atau sumber property-graph model yang dibaca.

## 2.7 Graph Retrieval-Augmented Generation (GraphRAG)

Definisikan GraphRAG: memperkaya RAG dengan struktur graf pengetahuan sehingga
temu-kembali dapat menelusuri relasi eksplisit antar entitas, bukan hanya kemiripan
embedding. Bandingkan dengan RAG datar. Tekankan hipotesis penelitian ini: pada korpus
regulasi, ekspansi sepanjang tepi `REFERENCES` memungkinkan sistem menjangkau pasal
pasangan lintas-regulasi. Catat pula desain *strict-parity re-rank* (ekspansi
dipemeringkat-ulang ke anggaran top-K yang sama) sebagai kontribusi rancangan yang
menjaga perbandingan tetap adil.

> TODO cite: Edge dkk. 2024 (Microsoft GraphRAG) atau karya GraphRAG lain yang dibaca;
> knowledge-graph-augmented retrieval / KG-QA.

## 2.8 Penjawaban Pertanyaan Multi-hop dan Kriteria Non-skippability

Jelaskan *multi-hop question answering*: pertanyaan yang jawabannya menuntut
penggabungan bukti dari beberapa dokumen/pasal. Uraikan kriteria **non-skippability**
(kriteria MuSiQue): sebuah pertanyaan multi-hop hanya sahih bila menghapus salah satu
pasal gold membuat jawaban salah/tak lengkap — jika satu pasal saja cukup, hop
tersebut "skippable" dan harus direklasifikasi. Kriteria ini menjadi dasar
pengonstruksian *ground truth* penelitian (lihat BAB III), khususnya penekanan pada
multi-hop *lintas-regulasi* sebagai kasus tertajam GraphRAG.

> TODO cite: Trivedi dkk. 2022 (MuSiQue, arXiv 2011.01060); HotpotQA / MultiHop-RAG
> sebagai benchmark pembanding.

## 2.9 Evaluasi Temu-Kembali dan Sisi Generasi

**Metrik temu-kembali.** Definisikan recall@k, precision@k, hit@k, dan MRR (Mean
Reciprocal Rank) terhadap gold. **Sisi generasi.** Perkenalkan evaluasi kualitas
jawaban dengan pendekatan *LLM-as-judge* (mis. RAGAS: *faithfulness*, *answer
correctness*), termasuk risiko bias *self-judge* dan mitigasinya (memakai model
penilai berbeda dari generator). **Uji signifikansi.** Jelaskan uji berpasangan
(Wilcoxon *signed-rank*) dan selang kepercayaan berbasis *bootstrap* berpasangan, serta
pentingnya melaporkan besar efek + CI, bukan nilai p semata — relevan bagi himpunan uji
berukuran moderat.

> TODO cite: definisi metrik IR (buku Manning dkk., *Introduction to Information
> Retrieval*); RAGAS (Es dkk. 2023); Wilcoxon 1945 / metode bootstrap (Efron).

## 2.10 Penelitian Terdahulu

Sajikan ringkasan karya terdahulu yang relevan (RAG, hybrid retrieval, GraphRAG,
multi-hop QA, NLP hukum) dalam bentuk tabel perbandingan: pendekatan, korpus/domain,
metrik, dan celah yang ditinggalkan. Posisikan penelitian ini terhadap celah tersebut:
menguji nilai tambah tahap graf **di atas baseline hibrida yang kuat**, pada anggaran
top-K identik, dengan pelaporan statistik berpasangan pada domain regulasi perpajakan
Indonesia.

> TODO cite: **hanya** sumber yang benar-benar dibaca. Isi tabel setelah studi
> literatur; jangan mengisi baris dengan referensi yang belum dibaca.

---

### Catatan penyusunan (hapus sebelum final)

- Setiap subbab di atas siap diperluas menjadi 2–4 paragraf; isi teknis sudah selaras
  dengan `docs/context-packs/METHODOLOGY.md` dan `GLOSSARY.md`.
- Jaga konsistensi istilah dengan GLOSSARY (mis. "seeding", "ekspansi graf",
  "baseline hibrida", "keterkaitan antar pasal").
- Prioritas penulisan: 2.1, 2.4, 2.7, 2.8 (paling dekat dengan kontribusi); sisanya
  fondasi yang lebih ringkas.
