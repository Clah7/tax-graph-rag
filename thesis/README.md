# Thesis (Skripsi) — LaTeX source

Comparative analysis of Baseline RAG vs GraphRAG for Indonesian tax regulations.
Uses the Universitas Padjadjaran template layout.

## Build

```bash
cd thesis
make pdf        # one-off build (latexmk: pdflatex + bibtex)
make watch      # rebuild on save
make clean      # remove build artifacts
```

Requires a TeX distribution with `latexmk` (TeX Live / MacTeX). Bibliography uses
`bibtex` with the `ieeetr` (IEEE) style — no biber needed.

## Layout

```
thesis/
├── main.tex                 # preamble + formatting + \input order
├── Header/                  # sampul, pengesahan, prakata, abstrak, abstract, d_isi, d_gambar, d_tabel
├── Isi/                     # Pendahuluan, Tinjauan Pustaka, Metode Penelitian,
│                            #   Hasil dan Pembahasan, Kesimpulan dan Saran, Lampiran
├── figures/                 # figures (generate results figures from ../data/eval_runs)
├── references.bib           # references — ONLY sources actually read
├── latexmkrc, Makefile
```

Formatting (margins 4-3-4-3 cm, Times 12pt, double spacing, "BAB" + Roman chapter
numbers, IEEE citations) comes from the Unpad template in `main.tex`.

## Discipline

- Never fabricate citations; only add sources to `references.bib` that were read.
- Results numbers are provisional until the eval set is frozen; pull them verbatim
  from `../data/eval_runs/` and `../STATUS.md`.
- Fill placeholders marked with `[ ... ]` and `XXXXX` (NPM, program studi, fakultas).
```
