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
.venv\Scripts\python explorar.py E:\ --conferir-arquivos
```
