# nodex.pw song downloader

качает с youtube / spotify / apple music, конвертирует на лету, вшивает обложку и теги

---

## что нужно

- python 3.10+
- ffmpeg (см. ниже)

---

## установка

```
pip install -r requirements.txt
python nodex_dl.py setup-ffmpeg
```

`setup-ffmpeg` сам скачает ffmpeg и положит в папку `ffmpeg\`  
на linux/mac — `sudo apt install ffmpeg` или `brew install ffmpeg`

---

## запуск

```
python nodex_dl.py
```

интерактивный режим — вставляешь ссылку, выбираешь формат, скачивается

---

## команды

```
python nodex_dl.py download URL
python nodex_dl.py download URL -f flac
python nodex_dl.py download URL -f mp3 -q 320 -o C:\Music
python nodex_dl.py search "artist - song" -f flac
```

---

## форматы

| # | формат | качество |
|---|--------|----------|
| 1 | MP3 | 320 kbps |
| 2 | MP3 | 256 kbps |
| 3 | MP3 | 128 kbps |
| 4 | FLAC | lossless |
| 5 | WAV | lossless |
| 6 | M4A | best |
| 7 | ALAC | lossless |
| 8 | OGG | best |
| 9 | OPUS | best |
| 10 | MP4 | видео + аудио |

---

## платформы

**YouTube** — качает напрямую  
**Spotify** — без api ключей, метаданные + обложка с spotify, аудио с youtube  
**Apple Music** — через itunes api, так же

---

## структура папки

```
nodex_dl.py
platforms.py
converter.py
requirements.txt
ffmpeg\
  ffmpeg.exe
  ffprobe.exe
```
