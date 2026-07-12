# BAB IV — HASIL DAN PEMBAHASAN

> Semua angka diambil verbatim dari `data/eval_runs/` dan
> `docs/context-packs/RESULTS.md`; sudah terverifikasi terhadap artefak run, bukan
> ingatan. Bagian ini baru memuat draf subbab kualitas jawaban sisi-generasi (§4.x);
> subbab lain menyusul.

## 4.x Kualitas Jawaban Sisi-Generasi (RAGAS)

Uji temu-kembali (§4.2) menakar apakah pasal *gold* sampai ke jendela konteks LLM,
tetapi tidak menakar apakah **jawaban** yang dihasilkan menjadi lebih baik. Untuk
menutup poros ini, jawaban yang telah disinggahkan (*cached*) dari kedua sistem pada
split uji v50 (n=33) dinilai dengan lima metrik RAGAS berbasis *LLM-judge*:
*faithfulness*, *answer relevancy*, *answer correctness*, *context precision*, dan
*context recall*. Sebagai hakim digunakan `claude-haiku-4-5` — model yang **berbeda**
dari generator `qwen3.5:9b`, sehingga *faithfulness* dan *answer correctness* bukan
penilaian-diri (*self-judge*) dan bias penilaian-diri dihindari; penyematan
(*embedding*) tetap lokal (`qwen3-embedding:0.6b`). Signifikansi diuji dengan
prosedur berpasangan yang sama seperti metrik IR (uji Wilcoxon berpasangan + selang
kepercayaan 95% *bootstrap*), agar kedua poros berpijak pada landasan statistik yang
setara.

Secara keseluruhan, GraphRAG **unggul secara arah pada kelima metrik**, namun **tidak
satu pun mencapai signifikansi statistik**: seluruh selang kepercayaan memuat nol dan
seluruh nilai-p > 0,05. Selisih terbesar terdapat pada *answer relevancy*
(0,461 → 0,538; Δ=+0,078; SK [−0,002, +0,166]; p=0,179). Pola ini konsisten dengan
temuan IR: pada ukuran sampel uji yang moderat (n=33, dan hanya n=19 untuk irisan
*multi-hop*), skala penilaian *LLM-judge* yang lebih bising belum menyediakan daya
uji (*statistical power*) yang cukup untuk mengangkat tren menjadi kemenangan yang
signifikan. Oleh karena itu, hasil ini dilaporkan sebagai **tren yang searah dan
konsisten**, bukan sebagai kemenangan sisi-generasi yang berdiri sendiri.

Keunggulan arah tersebut **terkonsentrasi pada pertanyaan *multi-hop*** — poros yang
sama dengan tempat kenaikan *recall* IR berada. Pada irisan ini, *faithfulness* naik
+0,068 (0,569 → 0,637), *answer relevancy* naik +0,096 (0,488 → 0,584), dan *context
recall* naik +0,085 (0,645 → 0,730). Interpretasinya lurus dengan mekanisme graf:
ekspansi menyusuri sisi rujukan lintas-regulasi menarik masuk pasal pasangan yang
tepat, sehingga jawaban menjadi lebih terlandasi (*grounded*) dan lebih lengkap. Pada
pertanyaan *single-hop* yang berperan sebagai **kontrol**, metrik nyaris tak bergerak
(mis. *faithfulness* Δ=+0,004; p=1,000) — sesuai harapan uji spesifisitas bahwa graf
tidak seharusnya mengangkat pertanyaan yang tak membutuhkannya.

Satu temuan perlu dilaporkan secara jujur, tidak dihaluskan: pada irisan *multi-hop*,
**context precision justru turun −0,037** (0,496 → 0,459; tidak signifikan). Ini
adalah imbas klasik dari ekspansi graf — memperluas konteks untuk menaikkan *recall*
sekaligus memasukkan sebagian pasal yang kurang relevan, sehingga presisi konteks
sedikit tergerus. Efeknya kecil dan tidak signifikan, tetapi menegaskan bahwa
manfaat graf berupa kelengkapan konteks datang dengan ongkos presisi yang wajar.

Secara ringkas, evaluasi sisi-generasi **mengukuhkan arah temuan utama IR dan tidak
bertentangan dengannya**: graf tidak menurunkan kualitas jawaban, dan bergerak ke
arah yang benar tepat di tempat yang diharapkan (*multi-hop*), meski belum
menghasilkan kemenangan yang signifikan secara statistik pada ukuran sampel saat ini.
