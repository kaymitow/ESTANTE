"""Prancha de conferência visual: junta páginas de um PDF numa imagem só.
  python ferramentas/prancha.py arquivo.pdf saida.png 1 5 9 40   (números de página, base 1)"""
import sys, pymupdf
pdf, out, *pgs = sys.argv[1:]
d = pymupdf.open(pdf); pgs = [int(p) - 1 for p in pgs] or range(min(6, len(d)))
pix = [d[p].get_pixmap(dpi=70) for p in pgs]
w, h = pix[0].width, pix[0].height; cols = min(len(pix), 3); rows = -(-len(pix) // cols)
sheet = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w * cols, h * rows), False); sheet.set_rect(sheet.irect, (255, 255, 255))
for i, p in enumerate(pix):
    p.set_origin((i % cols) * w, (i // cols) * h); sheet.copy(p, p.irect)
sheet.save(out)
