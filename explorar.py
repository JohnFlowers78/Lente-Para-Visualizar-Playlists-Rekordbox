"""Mostra no terminal o que o export.pdb guarda: a árvore de playlists e uma conferência das faixas.

Uso:  python explorar.py [pasta-raiz-do-pendrive]   (padrão: amostra/)
Só lê. Nunca grava nada na pasta indicada.
"""

import sys
from collections import Counter
from pathlib import Path

from lente.pdb import ExportPDB

raiz = Path(sys.argv[1] if len(sys.argv) > 1 else "amostra")
pdb = ExportPDB(raiz / "PIONEER" / "rekordbox" / "export.pdb")
tracks = pdb.tracks()
root = pdb.playlists()

print(f"Página: {pdb.len_page} bytes | tabelas: {sorted(pdb.tables)}")
print(f"Faixas no banco: {len(tracks)}")
print(f"Tipos: {dict(Counter(t.file_type for t in tracks.values()))}")
print()


def mostrar(no, nivel=0):
    for c in no.children:
        recuo = "    " * nivel
        if c.is_folder:
            print(f"{recuo}[pasta] {c.name}")
            mostrar(c, nivel + 1)
        else:
            sem = sum(1 for t in c.track_ids if t not in tracks)
            extra = f"  (!! {sem} ids sem faixa)" if sem else ""
            print(f"{recuo}{c.name}  — {len(c.track_ids)} músicas{extra}")


mostrar(root)

def todas(no):
    yield no
    for c in no.children:
        yield from todas(c)


em_alguma = {t for n in todas(root) for t in n.track_ids}
print()
print(f"Faixas em pelo menos uma playlist: {len(em_alguma & tracks.keys())} de {len(tracks)}")

print("\nAmostra de 3 faixas:")
for t in list(tracks.values())[:3]:
    print(f"  #{t.id} {t.artist} — {t.title} | {t.tempo:.2f} BPM | {t.duration}s")
    print(f"     áudio: {t.file_path}")
    print(f"     ANLZ : {t.analyze_path}")

if len(sys.argv) > 2 and sys.argv[2] == "--conferir-arquivos":
    falta = [t for t in tracks.values() if not (raiz / t.file_path.lstrip("/")).exists()]
    falta_anlz = [t for t in tracks.values() if t.analyze_path and not (raiz / t.analyze_path.lstrip("/")).exists()]
    print(f"\nÁudios ausentes no disco: {len(falta)} | ANLZ ausentes: {len(falta_anlz)}")
    for t in falta[:10]:
        print("   faltando:", t.file_path)
