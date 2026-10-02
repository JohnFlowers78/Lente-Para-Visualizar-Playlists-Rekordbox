"""Janela da Lente: playlists do rekordbox à esquerda, músicas à direita.

A Lente nunca copia nada sozinha. Arrastar ou Ctrl+C entrega ao Windows a lista
de arquivos, e quem copia é o próprio Explorer (mesma janela, mesma velocidade).
O arrasto só oferece COPIAR: nunca mover, para a coleção não sair do lugar.
"""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QMimeData, QModelIndex, QSettings,
                            QSortFilterProxyModel, Qt, QUrl)
from PySide6.QtGui import QAction, QBrush, QColor, QDrag, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHeaderView,
                               QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QSplitter, QTableView, QToolBar, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .pdb import ExportPDB, PlaylistNode, Track

PDB_REL = Path("PIONEER") / "rekordbox" / "export.pdb"
DROPEFFECT_COPY = 1


class Biblioteca:
    """O que foi lido de um disco exportado pelo rekordbox."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        pdb = ExportPDB(raiz / PDB_REL)
        self.tracks: dict[int, Track] = pdb.tracks()
        self.arvore: PlaylistNode = pdb.playlists()

    def arquivo(self, t: Track) -> Path:
        return self.raiz / t.file_path.lstrip("/")


def mime_de_arquivos(caminhos: list[Path]) -> QMimeData:
    """Lista de arquivos no formato que o Explorer entende (CF_HDROP), marcada como CÓPIA."""
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(p)) for p in caminhos])
    m.setData('application/x-qt-windows-mime;value="Preferred DropEffect"',
              struct.pack("<I", DROPEFFECT_COPY))
    return m


def arrastar(origem: QWidget, caminhos: list[Path]):
    if not caminhos:
        return
    drag = QDrag(origem)
    drag.setMimeData(mime_de_arquivos(caminhos))
    drag.exec(Qt.CopyAction)


def duracao(seg: int) -> str:
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ---- tabela de músicas -------------------------------------------------------

COLUNAS = ["#", "Título", "Artista", "Álbum", "BPM", "Duração", "Tipo", "Adicionada"]


class ModeloFaixas(QAbstractTableModel):
    def __init__(self, bib: Biblioteca):
        super().__init__()
        self.bib = bib
        self.faixas: list[Track] = []
        self.existe: list[bool] = []

    def mostrar(self, faixas: list[Track]):
        self.beginResetModel()
        self.faixas = faixas
        self.existe = [self.bib.arquivo(t).exists() for t in faixas]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.faixas)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUNAS)

    def headerData(self, sec, orient, role=Qt.DisplayRole):
        if orient == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUNAS[sec]
        return None

    def data(self, idx, role=Qt.DisplayRole):
        t = self.faixas[idx.row()]
        c = idx.column()
        if role == Qt.DisplayRole:
            return [str(idx.row() + 1), t.title, t.artist, t.album, f"{t.tempo:.2f}",
                    duracao(t.duration), t.file_type, t.date_added][c]
        if role == Qt.UserRole:  # valor usado para ordenar
            return [idx.row(), t.title.lower(), t.artist.lower(), t.album.lower(),
                    t.tempo, t.duration, t.file_type, t.date_added][c]
        if role == Qt.TextAlignmentRole and c in (0, 4, 5):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and not self.existe[idx.row()]:
            return QBrush(QColor("#c0392b"))
        if role == Qt.ToolTipRole:
            falta = "" if self.existe[idx.row()] else "\n(ARQUIVO NÃO ENCONTRADO NO DISCO)"
            return f"{t.file_path}{falta}"
        return None


class FiltroFaixas(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.setSortRole(Qt.UserRole)
        self.setFilterKeyColumn(-1)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)


class TabelaFaixas(QTableView):
    def __init__(self, janela: "Janela"):
        super().__init__()
        self.janela = janela
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setSortingEnabled(True)
        self.setAlternatingRowColors(True)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(22)
        self.setWordWrap(False)

    def startDrag(self, actions):
        arrastar(self, self.janela.arquivos_selecionados())


# ---- árvore de playlists -----------------------------------------------------

class ArvorePlaylists(QTreeWidget):
    def __init__(self, janela: "Janela"):
        super().__init__()
        self.janela = janela
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def startDrag(self, actions):
        arrastar(self, self.janela.arquivos_das_playlists(self.selectedItems()))


# ---- janela ------------------------------------------------------------------

class Janela(QMainWindow):
    abertas: list["Janela"] = []

    def __init__(self, raiz: Path | None = None):
        super().__init__()
        Janela.abertas.append(self)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.destroyed.connect(lambda *_: Janela.abertas.remove(self) if self in Janela.abertas else None)
        self.resize(1400, 820)
        self.bib: Biblioteca | None = None

        barra = QToolBar()
        barra.setMovable(False)
        self.addToolBar(barra)
        self._acao(barra, "Abrir disco…", self.escolher_disco, QKeySequence.Open)
        self._acao(barra, "Nova janela", lambda: Janela(self.bib.raiz if self.bib else None).show(),
                   QKeySequence.New)
        barra.addSeparator()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar título, artista, álbum…  (Ctrl+F)")
        self.busca.setClearButtonEnabled(True)
        self.busca.setMaximumWidth(420)
        self.busca.textChanged.connect(lambda txt: self.bib and self.filtro.setFilterFixedString(txt))
        barra.addWidget(self.busca)
        self._acao(self, "", lambda: (self.busca.setFocus(), self.busca.selectAll()), QKeySequence.Find)
        self._acao(self, "", self.copiar, QKeySequence.Copy)

        self.arvore = ArvorePlaylists(self)
        self.tabela = TabelaFaixas(self)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size: 15px; font-weight: 600; padding: 6px 4px;")

        direita = QWidget()
        lay = QVBoxLayout(direita)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.titulo)
        lay.addWidget(self.tabela)

        div = QSplitter()
        div.addWidget(self.arvore)
        div.addWidget(direita)
        div.setSizes([330, 1070])
        self.setCentralWidget(div)

        self.arvore.currentItemChanged.connect(lambda item, _: self.abrir_item(item))
        self.tabela.doubleClicked.connect(self.tocar)
        self.tabela.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabela.customContextMenuRequested.connect(self.menu_tabela)

        if raiz:
            self.carregar(raiz)
        else:
            self.setWindowTitle("Lente Rekordbox")
            self.statusBar().showMessage("Abra um disco exportado pelo rekordbox (Ctrl+O).")

    def _acao(self, onde, texto, func, atalho=None):
        a = QAction(texto, self)
        a.triggered.connect(func)
        if atalho is not None:
            a.setShortcut(atalho)
        onde.addAction(a)
        return a

    # -- disco --

    def escolher_disco(self):
        inicio = str(self.bib.raiz) if self.bib else ""
        pasta = QFileDialog.getExistingDirectory(self, "Raiz do disco exportado pelo rekordbox", inicio)
        if pasta:
            self.carregar(Path(pasta))

    def carregar(self, raiz: Path):
        if not (raiz / PDB_REL).exists():
            QMessageBox.warning(self, "Lente Rekordbox",
                                f"Não achei {PDB_REL} em {raiz}.\n"
                                "Escolha a raiz do disco (a pasta que contém PIONEER e Contents).")
            return
        self.bib = Biblioteca(raiz)
        QSettings("Lente", "Rekordbox").setValue("ultimo_disco", str(raiz))
        self.setWindowTitle(f"Lente Rekordbox — {raiz}")

        self.modelo = ModeloFaixas(self.bib)
        self.filtro = FiltroFaixas()
        self.filtro.setSourceModel(self.modelo)
        self.filtro.setFilterFixedString(self.busca.text())
        self.filtro.rowsInserted.connect(self.atualizar_status)
        self.filtro.rowsRemoved.connect(self.atualizar_status)
        self.filtro.modelReset.connect(self.atualizar_status)
        self.filtro.layoutChanged.connect(self.atualizar_status)
        self.tabela.setModel(self.filtro)
        h = self.tabela.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.Interactive)
        for col, larg in zip(range(len(COLUNAS)), (44, 380, 220, 220, 64, 64, 50, 90)):
            h.resizeSection(col, larg)
        h.setStretchLastSection(True)

        self.montar_arvore()

    def montar_arvore(self):
        a = self.arvore
        a.clear()
        bib = self.bib
        todas = QTreeWidgetItem(a, [f"Coleção inteira  ({len(bib.tracks)})"])
        todas.setData(0, Qt.UserRole, "todas")

        def adicionar(pai_item, no: PlaylistNode):
            for c in no.children:
                if c.is_folder:
                    it = QTreeWidgetItem(pai_item, [f"📁 {c.name}"])
                    it.setData(0, Qt.UserRole, c)
                    adicionar(it, c)
                else:
                    it = QTreeWidgetItem(pai_item, [f"{c.name}  ({len(c.track_ids)})"])
                    it.setData(0, Qt.UserRole, c)

        playlists = QTreeWidgetItem(a, ["Playlists"])
        playlists.setData(0, Qt.UserRole, bib.arvore)
        adicionar(playlists, bib.arvore)
        playlists.setExpanded(True)

        usadas = set()
        pilha = [bib.arvore]
        while pilha:
            n = pilha.pop()
            usadas.update(n.track_ids)
            pilha.extend(n.children)
        soltas = [t for t in bib.tracks if t not in usadas]
        if soltas:
            it = QTreeWidgetItem(a, [f"Fora de playlists  ({len(soltas)})"])
            it.setData(0, Qt.UserRole, ("soltas", soltas))
        a.setCurrentItem(todas)

    # -- conteúdo --

    def faixas_do_item(self, item) -> list[Track]:
        d = item.data(0, Qt.UserRole)
        tr = self.bib.tracks
        if d == "todas":
            return sorted(tr.values(), key=lambda t: (t.artist.lower(), t.title.lower()))
        if isinstance(d, tuple):
            return [tr[i] for i in d[1]]
        if isinstance(d, PlaylistNode):
            if d.is_folder:  # pasta: tudo que está embaixo dela, sem repetir
                vistos, out, pilha = set(), [], [d]
                while pilha:
                    n = pilha.pop(0)
                    for i in n.track_ids:
                        if i in tr and i not in vistos:
                            vistos.add(i)
                            out.append(tr[i])
                    pilha[:0] = n.children
                return out
            return [tr[i] for i in d.track_ids if i in tr]
        return []

    def abrir_item(self, item):
        if item is None or self.bib is None:
            return
        self.tabela.sortByColumn(-1, Qt.AscendingOrder)  # volta para a ordem da playlist
        self.modelo.mostrar(self.faixas_do_item(item))
        nome = item.text(0).rsplit("  (", 1)[0]
        self.titulo.setText(nome)
        self.atualizar_status()

    def atualizar_status(self, *_):
        if self.bib is None:
            return
        n = self.filtro.rowCount()
        idx = [self.filtro.mapToSource(self.filtro.index(r, 0)).row() for r in range(n)]
        fx = [self.modelo.faixas[i] for i in idx]
        tam = sum(t.file_size for t in fx) / 1024 ** 3
        dur = sum(t.duration for t in fx)
        falta = sum(1 for i in idx if not self.modelo.existe[i])
        aviso = f"   ·   {falta} arquivo(s) não encontrado(s)" if falta else ""
        self.statusBar().showMessage(f"{n} músicas   ·   {tam:.2f} GB   ·   {duracao(dur)} de música{aviso}")

    # -- seleção → arquivos --

    def faixas_selecionadas(self) -> list[Track]:
        linhas = sorted({i.row() for i in self.tabela.selectionModel().selectedRows()})
        return [self.modelo.faixas[self.filtro.mapToSource(self.filtro.index(r, 0)).row()]
                for r in linhas]

    def arquivos_selecionados(self) -> list[Path]:
        return [p for p in (self.bib.arquivo(t) for t in self.faixas_selecionadas()) if p.exists()]

    def arquivos_das_playlists(self, itens) -> list[Path]:
        vistos, out = set(), []
        for it in itens:
            for t in self.faixas_do_item(it):
                p = self.bib.arquivo(t)
                if p not in vistos and p.exists():
                    vistos.add(p)
                    out.append(p)
        return out

    def copiar(self):
        if self.bib is None:
            return
        if self.arvore.hasFocus():
            arqs = self.arquivos_das_playlists(self.arvore.selectedItems())
        else:
            arqs = self.arquivos_selecionados()
        if arqs:
            QApplication.clipboard().setMimeData(mime_de_arquivos(arqs))
            self.statusBar().showMessage(f"{len(arqs)} arquivo(s) copiado(s) — cole no Explorer com Ctrl+V", 6000)

    # -- ações na música --

    def tocar(self, idx):
        t = self.modelo.faixas[self.filtro.mapToSource(idx).row()]
        p = self.bib.arquivo(t)
        if p.exists():
            os.startfile(p)

    def menu_tabela(self, pos):
        fx = self.faixas_selecionadas()
        if not fx:
            return
        m = QMenu(self)
        m.addAction("Copiar (Ctrl+C)", self.copiar)
        m.addAction("Mostrar no Explorer", lambda: subprocess.Popen(
            ["explorer", "/select,", str(self.bib.arquivo(fx[0]))]))
        m.addAction("Tocar", lambda: os.startfile(self.bib.arquivo(fx[0])))
        m.exec(self.tabela.viewport().mapToGlobal(pos))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Lente Rekordbox")
    app.setStyle("Fusion")
    if len(sys.argv) > 1:
        raiz = Path(sys.argv[1])
    else:
        ultimo = QSettings("Lente", "Rekordbox").value("ultimo_disco", "")
        raiz = Path(ultimo) if ultimo and (Path(ultimo) / PDB_REL).exists() else None
    Janela(raiz).show()
    sys.exit(app.exec())
