"""Serwer lokalny KADR: FastAPI na 127.0.0.1:4321 (sekcja 9 spec).

Endpointy to cienkie nakładki na skrypty pipeline (jedna ścieżka kodu z CLI).
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from pipeline import config, edl as edl_mod, probe, proxy, render, subtitles, transcribe, versions

UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def _versions_index(project: Path) -> list[dict]:
    out = []
    for name in versions.list_versions(project):
        vdir = versions.versions_dir(project) / name
        manifest_path = vdir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        outputs = {p.name.removeprefix("out-").removesuffix(".mp4"): f"/media/versions/{name}/{p.name}"
                   for p in sorted(vdir.glob("out-*.mp4"))}
        out.append({"version": name, "manifest": manifest, "outputs": outputs})
    return out


def create_app(project: Path) -> FastAPI:
    project = Path(project).resolve()
    app = FastAPI(title="KADR", docs_url=None, redoc_url=None)
    jobs = {
        "render": {"running": False, "progress_pct": 0, "log_path": None,
                   "last_version": None, "error": None},
        "transcribe": {"running": False, "error": None},
    }
    lock = threading.Lock()

    @app.get("/api/state")
    def api_state():
        media = probe.load_media(project)
        edl_file = edl_mod.edl_path(project)
        edl = json.loads(edl_file.read_text()) if edl_file.exists() else None
        return {
            "project": project.name,
            "preferences": config.load_preferences(project),
            "edl": edl,
            "media": media,
            "transcripts_index": transcribe.load_transcripts(project),
            "versions": _versions_index(project),
        }

    @app.put("/api/edl")
    async def api_put_edl(request: Request, force: bool = False):
        incoming = await request.json()
        edl_file = edl_mod.edl_path(project)
        if edl_file.exists() and not force:
            on_disk = json.loads(edl_file.read_text())
            disk_ts = on_disk.get("meta", {}).get("updated_at")
            sent_ts = incoming.get("meta", {}).get("updated_at")
            if disk_ts and sent_ts != disk_ts:
                return JSONResponse(
                    status_code=409,
                    content={"detail": "EDL zmieniony poza UI", "disk_updated_at": disk_ts},
                )
        try:
            saved = edl_mod.save_edl(project, incoming, created_by="ui")
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return saved

    @app.put("/api/preferences")
    async def api_put_preferences(request: Request):
        prefs = await request.json()
        try:
            config.save_preferences(project, prefs)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        return config.load_preferences(project)

    @app.post("/api/render")
    async def api_render(request: Request):
        body = await request.json() if int(request.headers.get("content-length") or 0) else {}
        edl_file = edl_mod.edl_path(project)
        if not edl_file.exists():
            raise HTTPException(status_code=400, detail="Brak edl.json")
        edl = json.loads(edl_file.read_text())
        if not edl.get("approved"):
            raise HTTPException(status_code=400,
                                detail="Render tylko po approved: true (przycisk w UI)")
        with lock:
            if jobs["render"]["running"]:
                raise HTTPException(status_code=409, detail="Render już trwa")
            jobs["render"].update(running=True, progress_pct=0, error=None)

        def progress_cb(pct: int) -> None:
            jobs["render"]["progress_pct"] = pct

        def run() -> None:
            try:
                result = render.render_project(
                    project,
                    proxy_render=bool(body.get("proxy")),
                    formats=body.get("formats"),
                    note=body.get("note", ""),
                    progress_cb=progress_cb,
                )
                jobs["render"].update(last_version=result["version"],
                                      log_path=result["log"], progress_pct=100)
            except Exception as e:  # błąd trafia do statusu, nie ubija serwera
                jobs["render"]["error"] = str(e)
            finally:
                jobs["render"]["running"] = False

        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    @app.get("/api/render/status")
    def api_render_status():
        job = jobs["render"]
        log_tail = ""
        if job["log_path"] and Path(job["log_path"]).exists():
            log_tail = "\n".join(Path(job["log_path"]).read_text().splitlines()[-30:])
        else:
            logs = sorted((config.edit_dir(project) / "log").glob("render-*.log"))
            if logs:
                log_tail = "\n".join(logs[-1].read_text().splitlines()[-30:])
        return {
            "running": job["running"],
            "progress_pct": job["progress_pct"],
            "log_tail": log_tail,
            "last_version": job["last_version"],
            "error": job["error"],
        }

    @app.post("/api/transcribe")
    def api_transcribe():
        with lock:
            if jobs["transcribe"]["running"]:
                raise HTTPException(status_code=409, detail="Transkrypcja już trwa")
            jobs["transcribe"].update(running=True, error=None)

        def run() -> None:
            try:
                import kadr

                sources = kadr.find_sources(project)
                media = probe.probe_project(project, sources)
                transcribe.transcribe_project(project, media)
                proxy.proxy_project(project, media)
            except Exception as e:
                jobs["transcribe"]["error"] = str(e)
            finally:
                jobs["transcribe"]["running"] = False

        threading.Thread(target=run, daemon=True).start()
        return {"started": True}

    @app.get("/api/transcribe/status")
    def api_transcribe_status():
        return jobs["transcribe"]

    @app.get("/api/fonts")
    def api_fonts():
        return {"fonts": subtitles.list_system_fonts()}

    @app.get("/api/frame")
    def api_frame(
        source: str,
        t: float = Query(ge=0),
        crop_x: float | None = Query(default=None, ge=0, le=1),
        format: str | None = None,
        height: int = Query(default=540, ge=32, le=1080),
    ):
        media = probe.load_media(project)
        entry = media["sources"].get(source)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Nieznane źródło: {source}")
        src = project / entry["file"]
        vf = []
        if format and crop_x is not None and format in render.FORMAT_SPECS:
            crop_expr, _dims = render.FORMAT_SPECS[format]
            if crop_expr:
                vf.append(crop_expr.format(crop_x=crop_x))
        vf.append(f"scale=-2:{height}")
        proc = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{t:.4f}", "-i", str(src),
             "-frames:v", "1", "-vf", ",".join(vf), "-f", "image2", "-c:v", "mjpeg",
             "-q:v", "4", "-"],
            capture_output=True,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise HTTPException(status_code=500, detail=proc.stderr.decode()[-500:])
        return Response(content=proc.stdout, media_type="image/jpeg")

    app.mount("/media", StaticFiles(directory=config.edit_dir(project)), name="media")
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")
    return app
