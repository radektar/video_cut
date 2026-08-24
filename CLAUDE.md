# KADR — zasady pracy agenta

- Stan projektu to pliki w `<projekt>/edit/`. Jedyny plik, który wolno Ci edytować
  w toku montażu, to `edl.json` (i `preferences.yaml` na wyraźne życzenie).
- NIGDY nie zmieniaj zakresów z `"locked": true`. Nie zmieniaj `crop_x` ani `subtitles`
  ustawionych przez użytkownika, chyba że prosi wprost.
- Po każdej edycji `edl.json` uruchom: `python kadr.py plan --check` (walidacja).
- Nie renderuj bez polecenia. Render: `python kadr.py render [--proxy]`.
- Cięcia snapuj do granic słów z `transcripts/*.json`, padding 30–200 ms,
  preferuj cisze ≥ 400 ms.
- Wszystkie outputy w `edit/`, źródła nietykalne, transkrypty cache'owane.
- Decyzje niestandardowe dopisuj do `DECISIONS.md`.

## Komendy

```
python kadr.py init <folder>     # utwórz edit/ + preferences.yaml
python kadr.py transcribe        # probe + whisper.cpp + proxy (cache po sha256)
python kadr.py plan --auto       # naiwny edl.json ze wszystkich segmentów mowy
python kadr.py plan --check      # walidacja edl.json
python kadr.py render [--proxy]  # render do edit/versions/vNNN/
python kadr.py ui                # serwer FastAPI :4321 + przeglądarka
```
