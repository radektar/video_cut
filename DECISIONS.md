# DECISIONS.md — log decyzji wdrożeniowych

- **D-001 (F0):** Wdrożenie wykonywane w kontenerze Linux (Claude Code remote), nie na
  macOS. Kod celuje w macOS Apple Silicon zgodnie ze spec; różnice środowiskowe
  obsłużone tak, by działało na obu: detekcja binarki whispera (`whisper-cli` z brew
  na macOS, dowolna binarka przez `KADR_WHISPER_BIN` / `whisper.binary` w preferences),
  lista fontów przez `fc-list` z fallbackiem na `system_profiler` (macOS).
- **D-002 (F0):** Fixtures testowe (2 syntetyczne klipy: `testsrc2` + ton sinus) nie są
  commitowane jako binaria — generuje je `tests/fixtures/make_fixtures.py` (wywoływany
  automatycznie z `tests/conftest.py`). Repo pozostaje czysto tekstowe. TTS `say`
  z macOS niedostępny w kontenerze; mowa symulowana tonem, a transkrypty w testach
  pochodzą ze stubu whispera (patrz D-003).
- **D-003 (F1):** Do testów i kryteriów akceptacji używany jest stub `whisper-cli`
  (skrypt generujący poprawny JSON w formacie `--output-json-full` z tokenami),
  podstawiany przez `KADR_WHISPER_BIN`. Ćwiczy pełną ścieżkę parsowania
  (tokeny BPE → słowa). Prawdziwy whisper.cpp uruchamiany jest na maszynie docelowej
  (macOS, brew `whisper-cpp`, model `ggml-large-v3-turbo`).
- **D-004 (F1):** `plan --auto` tworzy jeden zakres per segment transkryptu (zdanie),
  z paddingiem `pacing.pad_before_ms`/`pad_after_ms`, przyciętym do granic źródła.
  Źródła bez transkryptu (brak mowy) dostają jeden zakres na cały klip z `subtitles`
  wg preferencji.
- **D-005 (F1):** Konkatenacja segmentów: każdy segment enkodowany osobno z identycznymi
  parametrami kodeka, potem `concat -c copy`, a napisy + loudnorm + grade w ostatnim
  przebiegu (napisy wypalane na końcu łańcucha — reguła video-use). Oznacza to jedną
  dodatkową re-enkodę całości na końcu; przy długościach social-media koszt pomijalny,
  a offsety napisów są liczone w osi wyjścia.
- **D-006 (F1):** `fps: source` w preferences → fps pierwszego źródła w `order`
  (wszystkie segmenty muszą mieć wspólny fps, żeby `concat -c copy` był poprawny).
- **D-007 (F2):** Dodatkowy endpoint `GET /api/fonts` (lista fontów systemowych) dla
  dropdownu w panelu preferencji — spec wymienia go w sekcji 10.5/14, ale nie w tabeli
  sekcji 9; dopisany jako najprostsza interpretacja.
- **D-008 (F1):** Hash `edl_sha256` w manifeście liczony z kanonicznego JSON
  (sort_keys) pliku `edl.json` skopiowanego do wersji.
