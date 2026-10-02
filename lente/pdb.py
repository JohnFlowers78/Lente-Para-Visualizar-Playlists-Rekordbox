"""Leitor do export.pdb (formato DeviceSQL) que o rekordbox grava no pendrive.

Somente leitura. Baseado na análise pública da Deep Symmetry
(https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html).

O arquivo é dividido em páginas de tamanho fixo. Cada tabela (faixas,
artistas, playlists...) é uma corrente de páginas. Dentro de cada página, as
linhas ficam num "heap" que cresce do início, e o índice das linhas cresce de
trás para frente, a partir do fim da página, em grupos de 16.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

# Tipos de tabela
T_TRACKS = 0x00
T_GENRES = 0x01
T_ARTISTS = 0x02
T_ALBUMS = 0x03
T_LABELS = 0x04
T_KEYS = 0x05
T_COLORS = 0x06
T_PLAYLIST_TREE = 0x07
T_PLAYLIST_ENTRIES = 0x08
T_ARTWORK = 0x0D

HEAP_POS = 0x28          # cabeçalho comum (0x20) + cabeçalho de página de dados (0x08)
ROW_GROUP_SIZE = 0x24    # 16 offsets de 2 bytes + flags de presença + flags de transação

# Índices dos textos dentro da linha de faixa
S_DATE_ADDED = 10
S_ANALYZE_PATH = 14
S_COMMENT = 16
S_TITLE = 17
S_FILENAME = 19
S_FILE_PATH = 20

FILE_TYPES = {0x01: "mp3", 0x04: "m4a", 0x05: "flac", 0x0B: "wav", 0x0C: "aiff"}


def _u8(b, o): return b[o]
def _u16(b, o): return struct.unpack_from("<H", b, o)[0]
def _u32(b, o): return struct.unpack_from("<I", b, o)[0]


def read_string(b: bytes, pos: int) -> str:
    """Texto no formato DeviceSQL: curto ASCII, longo ASCII ou longo UTF-16LE."""
    kind = b[pos]
    if kind & 1:  # curto: o próprio byte guarda o tamanho total (byte incluso)
        n = (kind >> 1) - 1
        return b[pos + 1:pos + 1 + n].decode("ascii", "replace")
    length = _u16(b, pos + 1)
    data = b[pos + 4:pos + length]
    if kind == 0x40:
        return data.decode("ascii", "replace")
    if kind == 0x90:
        # ISRC usa 0x90 mas guarda ASCII precedido de 0x03 e terminado em NUL
        if data[:1] == b"\x03":
            return data[1:].split(b"\x00", 1)[0].decode("ascii", "replace")
        return data.decode("utf-16-le", "replace")
    return data.decode("latin-1", "replace")


@dataclass
class Track:
    id: int
    title: str
    artist_id: int
    album_id: int
    file_path: str          # caminho do áudio no pendrive, ex. /Contents/Artista/Album/x.mp3
    analyze_path: str       # caminho do ANLZ, ex. /PIONEER/USBANLZ/P071/00012303/ANLZ0000.DAT
    file_type: str
    tempo: float            # BPM
    duration: int           # segundos
    file_size: int
    date_added: str
    comment: str
    artist: str = ""
    album: str = ""


@dataclass
class PlaylistNode:
    id: int
    parent_id: int
    name: str
    is_folder: bool
    sort_order: int
    children: list["PlaylistNode"] = field(default_factory=list)
    track_ids: list[int] = field(default_factory=list)   # na ordem da playlist


class ExportPDB:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.b = self.path.read_bytes()
        b = self.b
        self.len_page = _u32(b, 0x04)
        num_tables = _u32(b, 0x08)
        self.tables: dict[int, tuple[int, int]] = {}
        for i in range(num_tables):
            o = 0x1C + i * 16
            t = _u32(b, o)
            self.tables[t] = (_u32(b, o + 8), _u32(b, o + 12))  # (primeira, última página)

    # ---- páginas e linhas -------------------------------------------------

    def _pages(self, table: int):
        if table not in self.tables:
            return
        first, last = self.tables[table]
        idx, seen = first, set()
        while idx not in seen:
            seen.add(idx)
            base = idx * self.len_page
            if base + self.len_page > len(self.b):
                return
            yield base
            if idx == last:
                return
            idx = _u32(self.b, base + 0x0C)

    def rows(self, table: int):
        """Devolve o endereço (offset no arquivo) de cada linha presente na tabela."""
        b = self.b
        for base in self._pages(table):
            if _u32(b, base + 0x08) != table:
                continue
            flags = b[base + 0x1B]
            if flags & 0x40:  # página de índice, não de dados
                continue
            packed = b[base + 0x18] | (b[base + 0x19] << 8) | (b[base + 0x1A] << 16)
            num_offsets = packed & 0x1FFF
            if num_offsets == 0:
                continue
            groups = (num_offsets - 1) // 16 + 1
            end = base + self.len_page
            heap = base + HEAP_POS
            for g in range(groups):
                gbase = end - g * ROW_GROUP_SIZE
                present = _u16(b, gbase - 4)
                for r in range(16):
                    if g * 16 + r >= num_offsets:
                        break
                    if (present >> r) & 1:
                        yield heap + _u16(b, gbase - 6 - 2 * r)

    # ---- tabelas ----------------------------------------------------------

    def _named_rows(self, table: int, near_ofs: int, near_subtype: int, id_ofs: int) -> dict[int, str]:
        """Artistas e álbuns: o nome fica 'perto' (offset de 1 byte) ou 'longe' (2 bytes)."""
        b, out = self.b, {}
        for p in self.rows(table):
            subtype = _u16(b, p)
            rid = _u32(b, p + id_ofs)
            if subtype == near_subtype:
                ofs = b[p + near_ofs + 1]
            else:
                ofs = _u16(b, p + near_ofs + 2)
            out[rid] = read_string(b, p + ofs)
        return out

    def artists(self) -> dict[int, str]:
        return self._named_rows(T_ARTISTS, 0x08, 0x0060, 0x04)

    def albums(self) -> dict[int, str]:
        return self._named_rows(T_ALBUMS, 0x14, 0x0080, 0x0C)

    def tracks(self) -> dict[int, Track]:
        b, out = self.b, {}
        artists, albums = self.artists(), self.albums()
        for p in self.rows(T_TRACKS):
            if _u16(b, p) != 0x0024:
                continue
            s = [read_string(b, p + _u16(b, p + 0x5E + 2 * i)) for i in range(21)]
            t = Track(
                id=_u32(b, p + 0x48),
                title=s[S_TITLE],
                artist_id=_u32(b, p + 0x44),
                album_id=_u32(b, p + 0x40),
                file_path=s[S_FILE_PATH],
                analyze_path=s[S_ANALYZE_PATH],
                file_type=FILE_TYPES.get(_u16(b, p + 0x5A), "?"),
                tempo=_u32(b, p + 0x38) / 100,
                duration=_u16(b, p + 0x54),
                file_size=_u32(b, p + 0x10),
                date_added=s[S_DATE_ADDED],
                comment=s[S_COMMENT],
            )
            t.artist = artists.get(t.artist_id, "")
            t.album = albums.get(t.album_id, "")
            out[t.id] = t
        return out

    def playlists(self) -> PlaylistNode:
        """Árvore de pastas/playlists, com as faixas de cada playlist já na ordem."""
        b = self.b
        nodes: dict[int, PlaylistNode] = {}
        for p in self.rows(T_PLAYLIST_TREE):
            n = PlaylistNode(
                id=_u32(b, p + 0x0C),
                parent_id=_u32(b, p + 0x00),
                name=read_string(b, p + 0x14),
                is_folder=_u32(b, p + 0x10) != 0,
                sort_order=_u32(b, p + 0x08),
            )
            nodes[n.id] = n

        entries: dict[int, list[tuple[int, int]]] = {}
        for p in self.rows(T_PLAYLIST_ENTRIES):
            entry_index, track_id, playlist_id = _u32(b, p), _u32(b, p + 4), _u32(b, p + 8)
            entries.setdefault(playlist_id, []).append((entry_index, track_id))
        for pid, lst in entries.items():
            if pid in nodes:
                nodes[pid].track_ids = [tid for _, tid in sorted(lst)]

        root = PlaylistNode(id=0, parent_id=-1, name="", is_folder=True, sort_order=0)
        for n in nodes.values():
            (nodes.get(n.parent_id) or root).children.append(n)
        for n in list(nodes.values()) + [root]:
            n.children.sort(key=lambda c: c.sort_order)
        return root
