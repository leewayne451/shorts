"""Frame rendering engine.

Short path (render):
    Reads script.json (3 sentences, 3 beats) + 04_voice/words.json
    Writes final.mp4

Story path (render_story):
    Reads story.json (N chapters, cast-driven) + 04_voice/words.json
    Writes final.mp4 + clips/clip_NN.mp4 + clips.json
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import skia

from foodfacts.render import captions, photos, scenes

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- shared
def _cast_from_script(cfg: Dict[str, Any], script: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    palette = {k: tuple(v) for k, v in cfg["hair_colors"].items()}
    for m in script["cast"]:
        hair_color = palette.get(m.get("hair_color", "yellow"), (255, 208, 0))
        out.append({
            "name": m["name"],
            "hair_style": m.get("hair_style", "bob"),
            "hair_color": hair_color,
            "accessory": m.get("accessory", "none"),
            "accessory_color": (230, 40, 40),
            "bust": bool(m.get("bust", True)),
            "timeline": [(0.0, "idle")],
        })
    return out


def _emphasis_words(script: Dict[str, Any], beats: List[Dict[str, Any]],
                    word_times: Dict[str, Any]) -> Dict[int, set]:
    out: Dict[int, set] = {}
    for bi, beat in enumerate(beats):
        emph = {e.lower() for e in (beat.get("emphasis") or [])}
        out[bi] = emph
        times = []
        for w in word_times.get("_words", []):
            if w.get("sentence") == bi and w["word"].lower() in emph:
                times.append(w["start"])
        word_times[f"_emph_{bi}"] = times
        sent_words = [w for w in word_times.get("_words", []) if w.get("sentence") == bi]
        word_times[f"_show_{bi}"] = [sent_words[0]["start"]] if sent_words else [0.3]
    return out


def _preload_photos(cfg, beats, pixabay_key) -> tuple[dict, list]:
    cache_dir = Path(cfg["photo"]["cache_dir"])
    cards: Dict[str, Any] = {}
    credits: List[Dict[str, Any]] = []
    for beat in beats:
        for prop in beat.get("props", []):
            if prop.get("type") == "photo":
                q = prop["query"]
                if q in cards:
                    continue
                size = int(cfg["photo"]["card_size"])
                cards[q] = photos.load_photo_card(q, cache_dir, pixabay_key, cfg, size)
                got = photos.fetch_photo(q, cache_dir, pixabay_key, cfg)
                if got:
                    credits.append(got[1])
    return cards, credits


# ================================================================ short path
def render(cfg: Dict[str, Any], run_dir: Path, pixabay_key: Optional[str]) -> Path:
    W = int(cfg["video"]["width"])
    H = int(cfg["video"]["height"])
    FPS = int(cfg["video"]["fps"])
    DUR = float(cfg["video"]["duration"])
    total_frames = int(round(DUR * FPS))

    script = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    words = json.loads((run_dir / "04_voice" / "words.json").read_text(encoding="utf-8"))
    audio = run_dir / "05_audio" / "mix.wav"
    if not audio.exists():
        raise FileNotFoundError(f"missing {audio}; run music stage first")

    sentence_starts = [s[0] for s in words["sentences"]]
    beats = script["beats"]

    word_times: Dict[str, Any] = {"_words": words["words"]}
    emphasis = _emphasis_words(script, beats, word_times)

    cast = _cast_from_script(cfg, script)
    # short path: one timeline per cast member from the beats
    for ci, member in enumerate(cast):
        tl = [(0.0, "idle")]
        for bi, beat in enumerate(beats):
            t_start = sentence_starts[bi] if bi < len(sentence_starts) else 0.0
            t_end = sentence_starts[bi + 1] - 0.05 if bi + 1 < len(sentence_starts) else 9.9
            pose = (beat.get("poses") or {}).get(member["name"], "idle")
            tl.append((t_start + 0.45, pose))
            tl.append((t_end, "idle"))
        member["timeline"] = tl

    cards, credits = _preload_photos(cfg, beats, pixabay_key)
    photos.record_credits(run_dir, credits)

    scene_assets = scenes.SceneAssets(
        photos=cards, icons=[], beats=words["beats"],
        word_times=word_times, cast=cast,
        base_y=1570.0, prop_y=1190.0,
    )
    scene_draws = []
    for beat in beats:
        builder = scenes.BUILDERS.get(beat.get("scene", "intro_prop"), scenes.build_intro_prop)
        scene_draws.append(builder(scene_assets, beat))

    layout = captions.CaptionLayout(script, words["words"], emphasis)
    label_text = cfg["layout"].get("channel_label", "STORIES")

    out_path = run_dir / "final.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(audio),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", str(cfg["video"].get("crf", 18)),
        "-preset", cfg["video"].get("preset", "medium"),
        "-c:a", "aac", "-b:a", "160k",
        "-t", str(DUR), "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    surf = skia.Surface(W, H)
    cv = surf.getCanvas()

    def current_scene_index(t: float) -> int:
        idx = 0
        for i, s in enumerate(sentence_starts):
            if s <= t:
                idx = i
        return idx

    for f in range(total_frames):
        t = f / FPS
        cv.clear(skia.Color(0, 0, 0, 255))
        cv.save()
        scene_draws[current_scene_index(t)](cv, t)
        cv.restore()
        captions.draw_channel_label(cv, label_text)
        layout.draw(cv, t, sentence_starts)
        proc.stdin.write(surf.makeImageSnapshot().toarray().tobytes())

    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")
    log.info("Rendered %d frames -> %s", total_frames, out_path)
    return out_path


# ================================================================ story path
def _chapter_word_times(all_words: List[Dict[str, Any]], ci: int,
                        chapter_start: float) -> Dict[str, Any]:
    """Build the word_times dict a story builder expects for chapter ci."""
    ws = [w for w in all_words if w.get("chapter") == ci]
    emph_global = set()
    return {
        "_words": ws,
        "_chapter_start": [chapter_start],
        "_chapter_words": ws,
        # _emph is filled in by render_story once emphasis is known
        "_emph": [],
    }


def _chapter_index_at(spans: List[List[float]], t: float) -> int:
    idx = 0
    for i, (a, _b) in enumerate(spans):
        if a <= t:
            idx = i
    return idx


def _split_clips(final: Path, spans: List[List[float]], clip_dir: Path) -> List[Dict[str, Any]]:
    clip_dir.mkdir(parents=True, exist_ok=True)
    out: List[Dict[str, Any]] = []
    for ci, (a, b) in enumerate(spans):
        target = clip_dir / f"clip_{ci+1:02d}.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-ss", f"{a:.3f}", "-to", f"{b:.3f}",
             "-i", str(final),
             "-c", "copy", "-avoid_negative_ts", "make_zero",
             str(target)],
            check=True,
        )
        out.append({"index": ci, "file": str(target), "start": float(a), "end": float(b)})
    return out


def _chapter_caption_layout(chapter_sentences: List[str], all_words: List[Dict[str, Any]],
                            chapter_start: float) -> "captions.CaptionLayout":
    """Build a CaptionLayout scoped to one chapter.

    We rewrite the word timings to be relative to chapter_start, and set the
    caption sentence index to 0 because each chapter has exactly one layout.
    """
    scoped = []
    for w in all_words:
        scoped.append({
            "word": w["word"],
            "start": w["start"] - chapter_start,
            "end": w["end"] - chapter_start,
            "sentence": 0,
        })
    # caption layout expects a script-like dict with `sentences`
    script = {"sentences": [" ".join(chapter_sentences)]}
    emph = {0: set()}
    return captions.CaptionLayout(script, scoped, emph)


def render_story(cfg: Dict[str, Any], run_dir: Path,
                 pixabay_key: Optional[str] = None) -> Dict[str, Any]:
    """Story mode: render the whole 4-5 min video and split at chapter boundaries."""
    W = int(cfg["video"]["width"])
    H = int(cfg["video"]["height"])
    FPS = int(cfg["video"]["fps"])
    total = float(cfg["story"]["total_duration"])
    total_frames = int(round(total * FPS))

    story = json.loads((run_dir / "story.json").read_text(encoding="utf-8"))
    words = json.loads((run_dir / "04_voice" / "words.json").read_text(encoding="utf-8"))
    audio = run_dir / "05_audio" / "mix.wav"
    if not audio.exists():
        raise FileNotFoundError(f"missing {audio}; run music stage first")

    if words.get("mode") != "story":
        raise RuntimeError("words.json is not story mode; run voice stage with story.enabled=true")
    chapter_spans = words["chapters"]
    if len(chapter_spans) != len(story["chapters"]):
        raise RuntimeError(
            f"chapter count mismatch: story has {len(story['chapters'])}, "
            f"voice produced {len(chapter_spans)}"
        )

    cast = _cast_from_script(cfg, story)
    # no per-chapter timeline here: each chapter builds its own from poses
    cast_by_name = {m["name"]: m for m in cast}

    # preload photos (story path currently no photos, but keep it wired in case a
    # chapter in the future adds a photo — cheap and harmless)
    all_props = [p for ch in story["chapters"] for p in (ch.get("props") or [])]
    cards, credits = _preload_photos(cfg, [{"props": all_props}], pixabay_key)
    photos.record_credits(run_dir, credits)

    # build one scene draw + one caption layout per chapter
    chapter_draws: List[Dict[str, Any]] = []
    for ci, ch in enumerate(story["chapters"]):
        span = chapter_spans[ci]
        wt: Dict[str, Any] = {
            "_words": [w for w in words["words"] if w.get("chapter") == ci],
            "_chapter_start": [span[0]],
        }
        # emphasis: first emphasized word in this chapter, if any
        emph_words = {e.lower() for e in (ch.get("emphasis") or [])}
        emph_times = [
            w["start"] for w in words["words"]
            if w.get("chapter") == ci and w["word"].lower() in emph_words
        ]
        wt["_emph"] = emph_times

        assets = scenes.SceneAssets(
            photos=cards, icons=[], beats=words["beats"],
            word_times=wt, cast=cast,
            base_y=1570.0, prop_y=1190.0,
        )
        builder = scenes.BUILDERS[ch["scene"]]
        draw_fn = builder(assets, ch)

        chapter_words = [w for w in words["words"] if w.get("chapter") == ci]
        layout = _chapter_caption_layout(ch["sentences"], chapter_words, span[0])
        chapter_draws.append({
            "span": span,
            "draw": draw_fn,
            "layout": layout,
            "sentences": ch["sentences"],
        })

    label_text = cfg["layout"].get("channel_label", "STORIES")
    out_path = run_dir / "final.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", str(audio),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", str(cfg["video"].get("crf", 18)),
        "-preset", cfg["video"].get("preset", "medium"),
        "-c:a", "aac", "-b:a", "160k",
        "-t", f"{total:.3f}", "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    surf = skia.Surface(W, H)
    cv = surf.getCanvas()

    for f in range(total_frames):
        t = f / FPS
        ci = _chapter_index_at(chapter_spans, t)
        cd = chapter_draws[ci]
        cv.clear(skia.Color(0, 0, 0, 255))
        cv.save()
        cd["draw"](cv, t)
        cv.restore()
        captions.draw_channel_label(cv, label_text)
        # caption layout uses local time (t - chapter_start)
        cd["layout"].draw(cv, t - cd["span"][0], [0.0])
        proc.stdin.write(surf.makeImageSnapshot().toarray().tobytes())

    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed with code {proc.returncode}")
    log.info("Rendered story: %d frames -> %s", total_frames, out_path)

    clip_dir = run_dir / cfg["story"].get("clip_dir_name", "clips")
    clips = _split_clips(out_path, chapter_spans, clip_dir)
    (run_dir / "clips.json").write_text(json.dumps(clips, indent=2), encoding="utf-8")
    log.info("Split into %d clips in %s", len(clips), clip_dir)

    return {"video": str(out_path), "clips": clips}