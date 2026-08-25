# STATE — KADR

> Jeden żywy plik stanu projektu. Czytam go przy wejściu, Claude aktualizuje
> na koniec każdej sesji. Commitowany razem z kodem — synchronizuje obie maszyny.

**Ostatnia sesja:** 2026-08-25
**Faza:** test

## Ostatnia decyzja
MVP F0–F5 kompletny (pipeline CLI + serwer FastAPI :4321 + pełne review UI).
Testy na macOS zielone: 38 passed, 1 skipped. Wcześniejszy „czerwony" render z napisami
okazał się problemem ŚRODOWISKA, nie kodu: lokalny homebrew ffmpeg 9.0.1 jest zbudowany
**bez libass** (brak filtra `ass`), więc nie umie wypalić napisów. Kod: dodany preflight
z czytelnym błędem + skip testu, gdy build bez libass. Naprawiony też latentny escaping
ścieżki `.ass` (wewnątrz `'...'` nie escapujemy `:`).

## Następny krok
Render bez napisów zweryfikowany end-to-end na macOS (540×960 h264, manifest OK).
Napisy świadomie odłożone — patrz „Nie ruszać". Otwarte tematy: prawdziwy whisper.cpp
na maszynie docelowej, concat na mieszanym fps.

## Ustalenie o ffmpeg (2026-08-25)
Homebrew-core **wyrzucił libass z regularnej formuły `ffmpeg`** — `brew reinstall ffmpeg`
NIE przywraca napisów. libass jest teraz tylko w `ffmpeg-full` (47 zależności, keg-only,
binarka w `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`, niesie też whisper-cpp). Żeby kod
z niej korzystał, trzeba by sparametryzować ścieżkę ffmpeg (jak `KADR_WHISPER_BIN`).
Decyzja użytkownika: NIE robimy tego teraz.

## Otwarte ryzyka
- Napisy nie działają lokalnie (regularny ffmpeg bez libass) — render z napisami rzuca czytelny błąd; wypalanie zweryfikować dopiero na maszynie z ffmpeg-full/pełnym ffmpeg.
- Cała walidacja whispera na stubie (D-003); prawdziwy whisper.cpp nietestowany na maszynie docelowej.
- ffmpeg concat `-c copy` zakłada wspólny fps/kodek wszystkich segmentów (D-005/D-006) — nietestowane na mieszanym źródle.

## Nie ruszać
- Fixtures generowane, nie commitowane (D-002).
- Stub whispera jako źródło transkryptów w testach (D-003).
- Instalacja ffmpeg-full / parametryzacja `KADR_FFMPEG_BIN` — świadomie odłożone (2026-08-25). Nie proponować z powrotem bez odblokowania.

---

## Re-entry log
> Wypełniam ja przy każdym powrocie po ≥1 dniu: ile minut do momentu
> "wiem, co robię". Metryka skuteczności systemu.

| Data | Minuty do re-entry |
|------|--------------------|
|      |                    |
