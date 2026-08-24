#!/usr/bin/env python3
"""KADR — CLI: init | transcribe | proxy | plan | render | ui (spec sekcja 4)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SOURCE_EXTS = (".mp4", ".mov", ".MP4", ".MOV")


def find_sources(project: Path) -> list[Path]:
    files = [p for p in sorted(project.iterdir()) if p.suffix in SOURCE_EXTS and p.is_file()]
    return files


def cmd_init(args) -> int:
    from pipeline import config

    project = Path(args.folder).resolve()
    if not project.is_dir():
        print(f"Błąd: {project} nie jest katalogiem", file=sys.stderr)
        return 1
    edit = config.edit_dir(project)
    for sub in ("", "transcripts", "proxy", "versions", "log"):
        (edit / sub).mkdir(parents=True, exist_ok=True)
    prefs_path = config.preferences_path(project)
    if prefs_path.exists():
        print(f"Istnieje: {prefs_path} (nie nadpisuję)")
    else:
        config.write_default_preferences(project)
        print(f"Utworzono: {prefs_path}")
    print(f"Struktura edit/ gotowa w {edit}")
    return 0


def cmd_probe(args) -> int:
    from pipeline import probe

    project = Path(args.project).resolve()
    media = probe.probe_project(project, find_sources(project))
    print(f"media.json: {len(media['sources'])} źródeł")
    return 0


def cmd_transcribe(args) -> int:
    from pipeline import probe, proxy, transcribe

    project = Path(args.project).resolve()
    sources = find_sources(project)
    if not sources:
        print("Brak źródeł (*.mp4|*.mov) w katalogu projektu", file=sys.stderr)
        return 1
    media = probe.probe_project(project, sources)
    done = transcribe.transcribe_project(project, media)
    prox = proxy.proxy_project(project, media)
    print(f"Transkrypcje: {done['transcribed']} nowych, {done['cached']} z cache")
    print(f"Proxy: {prox['built']} nowych, {prox['cached']} z cache")
    return 0


def cmd_proxy(args) -> int:
    from pipeline import probe, proxy

    project = Path(args.project).resolve()
    media = probe.probe_project(project, find_sources(project))
    prox = proxy.proxy_project(project, media)
    print(f"Proxy: {prox['built']} nowych, {prox['cached']} z cache")
    return 0


def cmd_plan(args) -> int:
    from pipeline import edl as edl_mod

    project = Path(args.project).resolve()
    if args.auto:
        path = edl_mod.plan_auto(project)
        print(f"Zapisano naiwny plan: {path}")
        return 0
    if args.check:
        errors = edl_mod.check_project(project)
        if errors:
            print("edl.json NIEPOPRAWNY:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print("edl.json OK")
        return 0
    print("Podaj --auto albo --check", file=sys.stderr)
    return 2


def cmd_render(args) -> int:
    from pipeline import render

    project = Path(args.project).resolve()
    formats = args.formats.split(",") if args.formats else None
    result = render.render_project(
        project, proxy_render=args.proxy, formats=formats, note=args.note or ""
    )
    print(f"Wersja: {result['version']}")
    for fmt, path in result["outputs"].items():
        print(f"  {fmt}: {path}")
    return 0


def cmd_ui(args) -> int:
    import os
    import threading
    import webbrowser

    import uvicorn

    from server.app import create_app

    project = Path(args.project).resolve()
    os.environ["KADR_PROJECT"] = str(project)
    app = create_app(project)
    url = f"http://127.0.0.1:{args.port}/"
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"KADR UI: {url} (projekt: {project})")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kadr",
        description="KADR — lokalny system iteracyjnego montażu krótkich wideo.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="utwórz strukturę edit/ + preferences.yaml w folderze projektu")
    p.add_argument("folder", help="folder projektu z nagraniami")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("probe", help="ffprobe wszystkich źródeł → edit/media.json")
    p.add_argument("--project", default=".", help="folder projektu (domyślnie bieżący)")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("transcribe", help="probe + transkrypcja whisper.cpp + proxy 540p (cache po sha256)")
    p.add_argument("--project", default=".")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("proxy", help="wygeneruj proxy 540p dla źródeł")
    p.add_argument("--project", default=".")
    p.set_defaults(func=cmd_proxy)

    p = sub.add_parser("plan", help="--auto: naiwny edl.json z transkryptów; --check: walidacja edl.json")
    p.add_argument("--project", default=".")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--check", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("render", help="render edl.json → edit/versions/vNNN/")
    p.add_argument("--project", default=".")
    p.add_argument("--proxy", action="store_true", help="szybki render 540p (ultrafast)")
    p.add_argument("--formats", help="np. 9x16,16x9 (domyślnie z preferences)")
    p.add_argument("--note", help="notatka do manifestu wersji")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("ui", help="uruchom serwer Review UI (127.0.0.1:4321) i otwórz przeglądarkę")
    p.add_argument("--project", default=".")
    p.add_argument("--port", type=int, default=4321)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_ui)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
