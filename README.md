# Lente Rekordbox

Um explorador de arquivos que olha um pendrive/HD exportado pelo rekordbox e mostra
as **playlists reais**, não só as pastas `Contents/Artista/Álbum`.

A Lente só lê e mostra. Quem copia os arquivos é o próprio Windows, com a mesma
janela e a mesma velocidade de sempre.

## Como o pendrive guarda as coisas

```
PIONEER/rekordbox/export.pdb      banco (DeviceSQL): faixas, playlists, pastas, ordem
PIONEER/rekordbox/exportExt.pdb   dados extras (tags)
PIONEER/rekordbox/exportLibrary.db banco novo do rekordbox 7 (criptografado, SQLCipher)
PIONEER/USBANLZ/Pxxx/xxxxxxxx/    análise por faixa: beatgrid, hotcues, loops, waveform
Contents/Artista/Álbum/arquivo    o áudio
```

Cada faixa no `export.pdb` aponta para o seu áudio (`/Contents/...`) e para a sua
análise (`/PIONEER/USBANLZ/...`). Uma playlist é só uma lista ordenada de ids de faixa.

## Regra

O pendrive original **nunca** é aberto para escrita. Os testes usam uma cópia em `amostra/`.

## Rodar

```
python -m venv .venv
.venv\Scripts\pip install PySide6
```

- Janela: clique duplo em `Abrir Lente.bat` (abre o último disco usado; Ctrl+O escolhe outro).
- Terminal: `.venv\Scripts\python explorar.py E:\ --conferir-arquivos`

## Na janela

- Esquerda: a coleção inteira e as playlists. Direita: as músicas, na ordem da playlist.
- Arrastar músicas ou playlists inteiras para o Explorer: **o Windows copia** (só cópia, nunca mover).
- Ctrl+C e depois Ctrl+V no Explorer faz o mesmo.
- Ctrl+F busca, Ctrl+N abre outra janela, clique duplo toca a música, botão direito → "Mostrar no Explorer".
- Música em vermelho = está no banco mas o arquivo não está no disco.

## Alvo: o pendrive do club

O pendrive de destino precisa tocar em qualquer CDJ/XDJ, então tem que levar
os dois bancos (`export.pdb` e `exportLibrary.db`), além do áudio e da análise.
O Windows copia os arquivos; a Lente grava os bancos do destino. Ainda não feito.
