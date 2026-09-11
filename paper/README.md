# Twig Academic Paper

This folder contains the complete academic research paper draft for **Twig**:

- `paper.tex`: The LaTeX source code.
- `paper.bib`: The BibTeX bibliography file.

## Paper Title
> **Twig: A Parent-Pointer Relational Serialization Format for Token-Efficient Structured Data in Large Language Model Contexts**

## How to Compile to PDF

### Option 1: Overleaf (Recommended, Zero Setup)
1. Go to [Overleaf.com](https://www.overleaf.com) and create a New Project $\to$ Upload Project.
2. Upload the `paper/` folder (or zip `paper.tex` and `paper.bib`).
3. Click **Recompile** to get the publication-ready PDF.

### Option 2: Local CLI (pdflatex)
If you have TeX Live / MiKTeX installed:
```bash
cd paper
pdflatex paper.tex
bibtex paper
pdflatex paper.tex
pdflatex paper.tex
```

## How to Publish / Submit

1. **arXiv Preprint (Immediate, ~24-48 hours)**:
   - Go to [arxiv.org/submit](https://arxiv.org/submit).
   - Category: `cs.CL` (Computation and Language) or `cs.AI` (Artificial Intelligence).
   - Upload `paper.tex` and `paper.bib`.
   - Once published, you receive an official, citable DOI.

2. **Conference Venues**:
   - **ACL / EMNLP / NAACL System Demonstrations Track**: Perfect match because Twig has a working open-source library and live web playground.
   - **MLSys / NeurIPS Workshops** (e.g. *Workshop on Efficient Systems for Foundation Models*).
