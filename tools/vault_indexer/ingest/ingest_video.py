"""Video ingestion via yt-dlp + openai-whisper. Markdown into Videos/<author>/."""
from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .common import iso_week, slug, write_note
from ..config import CONFIG


def download_audio(url: str, out_dir: Path) -> Path:
    out = out_dir / "audio.%(ext)s"
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", str(out),
        url,
    ]
    subprocess.run(cmd, check=True)
    matches = list(out_dir.glob("audio.*"))
    if not matches:
        raise RuntimeError("yt-dlp produced no output")
    return matches[0]


def transcribe(audio_path: Path, model_name: str = "small") -> tuple[str, str]:
    """Return (title-hint, transcript). title-hint pulled from yt-dlp metadata is harder
    to wire; we leave title to the operator's --title flag and fall back to the URL hash."""
    import whisper

    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path))
    return "", result.get("text", "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="YouTube/podcast URL (yt-dlp compatible).")
    ap.add_argument("--author", required=True)
    ap.add_argument("--horizon", type=int, default=3)
    ap.add_argument("--published", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--whisper-model", default="small")
    args = ap.parse_args()

    if shutil.which("yt-dlp") is None:
        print("yt-dlp not on PATH (pip install yt-dlp)", file=sys.stderr)
        return 1

    published = args.published or datetime.date.today().isoformat()
    title = args.title or f"{args.author}-{iso_week()}"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        audio = download_audio(args.url, tmp_path)
        _, body = transcribe(audio, args.whisper_model)

    week = iso_week(datetime.date.fromisoformat(published))
    rel_dir = f"Videos/{slug(args.author)}"
    filename = f"{week}-{slug(title)}.md"
    write_note(
        vault_root=CONFIG.vault_path,
        rel_dir=rel_dir,
        filename=filename,
        body=f"# {title}\n\n[Source]({args.url})\n\n{body}",
        metadata={
            "kind": "video",
            "title": title,
            "author": args.author,
            "source_url": args.url,
            "published_at": published,
            "horizon_months": args.horizon,
            "tags": [],
        },
    )
    print(f"ingested → {rel_dir}/{filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
