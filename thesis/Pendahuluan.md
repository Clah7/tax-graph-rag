# BAB I — PENDAHULUAN

## 1.1 Latar Belakang

Peraturan perpajakan di Indonesia bersifat tersebar dan berlapis. Ketentuan atas satu
persoalan pajak jarang berdiri sendiri dalam satu pasal; ia terbentang lintas jenjang
regulasi — Undang-Undang (UU), Peraturan Pemerintah (PP), hingga Peraturan Menteri
Keuangan (PMK) — yang saling merujuk. Norma pokok ditetapkan di UU, ketentuan
pelaksanaannya didelegasikan ke PP, dan tata cara teknisnya diatur lebih lanjut oleh
PMK. Akibatnya, menjawab satu pertanyaan pajak yang utuh sering menuntut penalaran
*multi-hop*: menautkan dua atau lebih pasal, kerap melintasi batas regulasi, melalui
rantai rujukan (keterkaitan antar pasal) yang eksplisit.

> TODO cite: kompleksitas dan keterkaitan regulasi hukum Indonesia; kebutuhan sistem
> temu-kembali untuk domain hukum/regulasi.

*Retrieval-Augmented Generation* (RAG) menjadi pendekatan lazim untuk menjawab
pertanyaan atas korpus regulasi: sistem menemukan potongan teks yang relevan, lalu
sebuah model bahasa menyusun jawaban dari potongan tersebut. Namun RAG dengan
temu-kembali *dense* murni (berbasis kemiripan embedding) kurang andal pada korpus
regulasi pajak. Diagnosis pada penelitian ini menunjukkan kegagalannya bukan terletak
pada *recall* korpus, melainkan pada *pemeringkatan* (*ranking*): dari gold yang
ditelaah, 41 dari 44 pasal jawaban sudah berada di dalam 200 kandidat *dense* teratas,
tetapi terkubur di bawah ambang pemotongan lima teratas (top-5) yang benar-benar
sampai ke model bahasa. Model embedding kecil mengenali pasal yang tepat, namun
memeringkatnya dengan buruk karena istilah yang dikutip regulasi ("Pajak Hotel", nama
peraturan, nomor pasal) cenderung dikaburkan oleh sinyal semantik.

> TODO cite: keterbatasan dense retrieval; peran sinyal leksikal (BM25) dan
> hybrid retrieval / Reciprocal Rank Fusion.

Temuan ini memotivasi dua langkah. Pertama, memperkuat tahap *seeding* (temu-kembali
awal) dengan menggabungkan sinyal leksikal dan *dense* — sebuah baseline hibrida yang
mengangkat kembali pasal yang tepat ke dalam anggaran top-K. Kedua, memanfaatkan
struktur yang unik pada korpus regulasi: graf keterkaitan antar pasal. Dengan
memodelkan rujukan antar pasal (REFERENCES) sebagai tepi graf, sebuah pendekatan
*GraphRAG* dapat menelusuri secara eksplisit dari pasal yang telah ditemukan menuju
pasal pasangannya — termasuk yang berada di regulasi lain — sesuatu yang sulit
dijangkau kemiripan embedding semata.

Persoalannya, klaim keunggulan GraphRAG kerap diuji terhadap baseline yang lemah,
sehingga selisih yang terukur bisa jadi hanya menutupi kekurangan *seeding*, bukan
menunjukkan nilai tambah graf yang sesungguhnya. Celah inilah yang ditutup penelitian
ini: menguji apakah tahap ekspansi graf menambah nilai temu-kembali *di atas* sebuah
baseline hibrida yang sudah kuat, pada kondisi anggaran top-K yang identik — sehingga
setiap selisih yang terukur murni disebabkan oleh tahap graf.

## 1.2 Identifikasi Masalah

Berdasarkan latar belakang di atas, pertanyaan penelitian dirumuskan sebagai berikut:

1. Apakah tahap ekspansi graf atas keterkaitan antar pasal meningkatkan kinerja
   temu-kembali di atas baseline RAG hibrida (leksikal+*dense*), pada kondisi anggaran
   top-K yang sama?
2. Apakah nilai tambah tahap graf bergantung pada kualitas *seed* — yakni bersifat
   nihil ketika *seed* berasal dari temu-kembali *dense* murni, namun menentukan
   ketika *seed* berasal dari temu-kembali hibrida?
3. Apakah konteks yang diperkaya graf memperbaiki kualitas jawaban generatif
   dibanding baseline hibrida? *(Bersifat provisional — pengukuran sisi generasi
   (RAGAS) sedang berjalan dan angkanya belum tersedia.)*

## 1.3 Batasan Masalah

Agar penelitian terfokus dan hasilnya dapat dipertanggungjawabkan, ruang lingkup
dibatasi sebagai berikut:

1. **Korpus.** Data bersumber dari JDIH dan telah melalui deduplikasi menjadi 118.966
   pasal unik. Isu data yang diketahui dilaporkan secara transparan dan tidak
   diperbaiki dalam penelitian ini: kesalahan OCR huruf `O`→angka `0` (~0,2% baris)
   dan ~1.157 tumbukan ID pada undang-undang *omnibus* (yang memakai ulang nomor pasal
   antar regulasi induk). Rujukan yang tidak terselesaikan akibat isu ini menjadi
   batas atas *recall* graf yang dapat dicapai, dan disebutkan eksplisit saat
   membingkai hasil.
2. **Himpunan evaluasi.** *Ground truth* terdiri atas 50 pertanyaan yang diverifikasi
   secara manual (29 multi-hop, 21 single-hop; 13 di antaranya multi-hop
   lintas-regulasi). Ukuran ini menukar skala demi ketelitian konstruksi; daya
   statistiknya moderat (uji pada test n=33), sehingga hasil diperlakukan sebagai
   provisional dan dilaporkan dengan uji berpasangan beserta selang kepercayaan.
3. **Model.** Model bahasa (`qwen3.5:9b`) dan model embedding (`qwen3-embedding:0.6b`,
   1024 dimensi) ditetapkan tetap. Penelitian ini bukan studi perbandingan model,
   melainkan perbandingan metodologi temu-kembali.

## 1.4 Maksud dan Tujuan Penelitian

**Maksud.** Penelitian ini dimaksudkan untuk melakukan analisis komparatif atas nilai
tambah tahap ekspansi graf dalam temu-kembali regulasi perpajakan Indonesia, dengan
membandingkan dua sistem — baseline RAG hibrida dan GraphRAG — yang dirancang setara
sejak awal (*comparable by construction*): keduanya menggunakan tahap *seeding* yang
identik melalui satu titik dispatch (`src/seeding.py`), sehingga perbedaan kinerja
yang terukur dapat diatribusikan sepenuhnya pada tahap graf.

**Tujuan.** Secara khusus, penelitian ini bertujuan untuk:

1. Mengukur apakah ekspansi graf atas keterkaitan antar pasal meningkatkan
   temu-kembali di atas baseline hibrida pada anggaran top-K yang sama, dengan
   metrik recall@5, precision@5, hit@5, dan MRR.
2. Menguji ketergantungan nilai tambah graf pada kualitas *seed* melalui rancangan
   2×2 (seed *dense* vs hibrida) × (dengan vs tanpa graf).
3. Melaporkan setiap selisih secara jujur dengan statistik berpasangan (uji Wilcoxon)
   dan selang kepercayaan 95% berbasis *bootstrap* berpasangan, disertai keterangan
   keterbatasan daya statistik.

## 1.5 Manfaat Penelitian

**Manfaat teoretis.** Penelitian ini memberi bukti mengenai *kapan* GraphRAG unggul,
bukan sekadar *apakah* ia unggul. Temuan menunjukkan nilai tambah graf baru
terealisasi setelah *seed* mendarat di regulasi yang tepat, sehingga ekspansi dapat
menelusuri tepi rujukan lintas-regulasi menuju pasal pasangan. Ini memperjelas syarat
prasyarat keberhasilan GraphRAG dan menegaskan pentingnya baseline yang kuat sebagai
pembanding yang adil.

**Manfaat praktis.** Sistem yang dibangun dapat memperbaiki akses dan penalaran atas
regulasi perpajakan yang saling terkait — membantu praktisi, peneliti, maupun wajib
pajak menautkan norma, ketentuan pelaksana, dan tata cara teknis yang tersebar lintas
UU, PP, dan PMK.

## 1.6 Metodologi Penelitian

Bagian ini menyajikan gambaran ringkas metodologi; rinciannya diuraikan pada BAB III.

Penelitian ini bersifat komparatif-eksperimental, membandingkan dua sistem temu-kembali
atas korpus regulasi perpajakan Indonesia yang dihimpun dari JDIH. Korpus diindeks
secara ganda: ke dalam basis vektor **ChromaDB** (temu-kembali *dense*) dan basis graf
**Neo4j** (keterkaitan antar pasal melalui tepi REFERENCES). Dua sistem yang
dibandingkan adalah: (1) **Baseline RAG hibrida** — *seeding* gabungan leksikal+*dense*
yang difusikan dengan *Reciprocal Rank Fusion*; dan (2) **GraphRAG** — *seed* hibrida
yang sama, diperluas melalui ekspansi graf lalu dipemeringkat-ulang ke dalam anggaran
top-K yang identik. Karena keduanya berbagi tahap *seeding* yang sama persis, selisih
kinerja dapat diatribusikan pada tahap graf semata.

Evaluasi dilakukan atas *ground truth* berisi 50 pertanyaan terverifikasi, dengan
pembagian *dev/test* yang dibekukan sebelum penalaan (*tuning*). Kinerja temu-kembali
diukur dengan recall@5, precision@5, hit@5, dan MRR, dan setiap selisih dilaporkan
memakai uji berpasangan (Wilcoxon) beserta selang kepercayaan 95% berbasis *bootstrap*.
Kualitas jawaban sisi generasi direncanakan diukur dengan RAGAS. Uraian lengkap
mengenai akuisisi data, skema graf, pipeline seeding dan ekspansi, pembekuan split,
serta desain statistik disajikan pada BAB III.

## 1.7 Sistematika Penulisan

Penulisan skripsi ini disusun dalam lima bab sebagai berikut:

- **BAB I Pendahuluan** — memaparkan latar belakang, identifikasi masalah, batasan
  masalah, maksud dan tujuan, manfaat, gambaran ringkas metodologi, serta sistematika
  penulisan.
- **BAB II Tinjauan Pustaka** — membahas landasan teori dan penelitian terdahulu yang
  relevan (RAG, temu-kembali hibrida, GraphRAG, serta pemrosesan teks regulasi).
- **BAB III Metode Penelitian** — menguraikan rancangan penelitian, korpus dan
  praproses, indeksasi ganda, arsitektur kedua sistem, serta desain dan protokol
  evaluasi.
- **BAB IV Hasil dan Pembahasan** — menyajikan dan menganalisis hasil perbandingan,
  termasuk uji statistik berpasangan dan pembahasan keterbatasan.
- **BAB V Kesimpulan dan Saran** — merangkum temuan utama dan memberikan saran bagi
  penelitian lanjutan.
