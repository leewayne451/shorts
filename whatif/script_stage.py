"""Script stage: turn a vanishing subject into a validated shot plan.

Produces script.json in the run folder with:
{
  "title": str,
  "opening_question": "What if <subject> vanished?",
  "cast": [ {"id","name","hair_style","hair_color_idx","accessory","accessory_color_idx","bust"} , ... ],
  "scenes": [
     {"index", "time_label", "scene_template", "props":[{"type":"photo"|"icon", ...}],
      "cast_ids":[...], "poses":{id:pose}, "faces":{id:face}, "emphasis":[...],
      "caption": str, "shake": bool, "claims":[str, ...]},
     ...
  ]
}

Constraints enforced by pydantic:
- opening_question == "What if <subject> vanished?" (case-insensitive on "What if").
- 1 <= len(cast) <= 5.
- Every scene.cast_ids is a subset of cast ids; scene.visible count in [1, 5].
- 4 <= len(scenes) <= 8.
- 55 <= total narration words (opening_question + all captions) <= 130.
- scene_template in registry; time_label in ladder; at least "+1 hour" and "+1 day" present.
- At most `max_bench_per_scene` cast members missing from a scene (i.e., scene must show
  at least len(cast) - 2, floored at 1).
- Only photo/icon props; photo query 2-4 words; icon name in registry (validated leniently here,
  strict at render).
- poses/faces keys are cast ids; values in registry.
- First scene must be the opening question: template == "intro_prop" and caption == opening_question.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from whatif import get_logger, load_config
from whatif.llm import GroqError, build_retry_user_prompt, chat_json

_LOG = get_logger("whatif.script")

HAIR_STYLES = {"bob", "ponytail", "short", "bun"}
ACCESSORIES = {"none", "glasses", "beanie", "bow_tie", "chef_hat"}
POSES = {"idle", "present", "point", "pinch", "shrug", "think", "wave", "celebrate"}
FACES = {"smile", "grin", "open", "meh", "ew", "brows_angry", "brows_raised",
         "brows_worried", "brows_flat"}
SCENE_TEMPLATES = {
    "intro_prop", "timeline_step", "crowd_react",
    "two_reactors", "two_props_compare", "big_number",
}
ICONS = {"question_mark", "arrow", "sparkle", "no_sign", "clock"}
PROP_TYPES = {"photo", "icon"}

_QUERY_RE = re.compile(r"^\s*\S+(?:\s+\S+){1,3}\s*$")  # 2-4 words


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class CastMember(BaseModel):
    id: str
    name: str
    hair_style: str = "bob"
    hair_color_idx: int = 0
    accessory: str = "none"
    accessory_color_idx: int = 0
    bust: bool = True

    @field_validator("hair_style")
    @classmethod
    def _hair(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in HAIR_STYLES else "bob"

    @field_validator("accessory")
    @classmethod
    def _acc(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in ACCESSORIES else "none"

    @field_validator("id", "name")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v


class PhotoProp(BaseModel):
    type: Literal["photo"]
    query: str

    @field_validator("query")
    @classmethod
    def _query(cls, v: str) -> str:
        v = (v or "").strip()
        if not _QUERY_RE.match(v):
            raise ValueError("photo query must be 2 to 4 words")
        return v


class IconProp(BaseModel):
    type: Literal["icon"]
    name: str

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ICONS:
            raise ValueError(f"icon name must be one of {sorted(ICONS)}")
        return v


class Scene(BaseModel):
    index: int
    time_label: str
    scene_template: str
    props: List[Dict[str, Any]] = Field(default_factory=list)
    cast_ids: List[str]
    poses: Dict[str, str] = Field(default_factory=dict)
    faces: Dict[str, str] = Field(default_factory=dict)
    emphasis: List[str] = Field(default_factory=list)
    caption: str
    shake: bool = False
    claims: List[str] = Field(default_factory=list)

    @field_validator("scene_template")
    @classmethod
    def _tmpl(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in SCENE_TEMPLATES:
            raise ValueError(f"scene_template must be one of {sorted(SCENE_TEMPLATES)}")
        return v

    @field_validator("props")
    @classmethod
    def _props(cls, v: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(v) > 2:
            raise ValueError("at most 2 props per scene")
        for p in v:
            if not isinstance(p, dict) or "type" not in p:
                raise ValueError("prop must be a dict with 'type'")
            t = p["type"]
            if t not in PROP_TYPES:
                raise ValueError(f"prop type must be one of {sorted(PROP_TYPES)}")
            if t == "photo":
                PhotoProp(**p)  # raises on invalid query
            elif t == "icon":
                IconProp(**p)   # raises on invalid name
        return v

    @field_validator("poses")
    @classmethod
    def _poses(cls, v: Dict[str, str]) -> Dict[str, str]:
        for k, p in v.items():
            if p not in POSES:
                raise ValueError(f"pose for {k} must be one of {sorted(POSES)}")
        return v

    @field_validator("faces")
    @classmethod
    def _faces(cls, v: Dict[str, str]) -> Dict[str, str]:
        for k, p in v.items():
            if p not in FACES:
                raise ValueError(f"face for {k} must be one of {sorted(FACES)}")
        return v

    @field_validator("caption")
    @classmethod
    def _cap(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("caption must be non-empty")
        return v


class Script(BaseModel):
    title: str
    opening_question: str
    cast: List[CastMember]
    scenes: List[Scene]

    @field_validator("title", "opening_question")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("must be non-empty")
        return v

    @model_validator(mode="after")
    def _cross(self) -> "Script":
        cfg = load_config()
        schema = cfg["script_schema"]
        ladder = cfg["time_ladder"]
        required_labels = cfg["required_time_labels"]

        # opening question form
        m = re.match(r"^\s*what\s+if\s+(.+?)\s+vanished\?\s*$", self.opening_question, re.I)
        if not m:
            raise ValueError('opening_question must match "What if <subject> vanished?"')

        # cast size
        if not (schema["min_cast"] <= len(self.cast) <= schema["max_cast"]):
            raise ValueError(
                f"cast size must be {schema['min_cast']}..{schema['max_cast']}, got {len(self.cast)}"
            )

        # scenes count
        if not (schema["min_scenes"] <= len(self.scenes) <= schema["max_scenes"]):
            raise ValueError(
                f"scenes count must be {schema['min_scenes']}..{schema['max_scenes']}, got {len(self.scenes)}"
            )

        # scene indices must be 0..n-1 in order
        for i, s in enumerate(self.scenes):
            if s.index != i:
                raise ValueError(f"scene at position {i} has index {s.index}; indices must be 0..n-1 in order")

        # time labels must move forward through the timeline rather than behaving
        # like an unordered list of related facts.
        for s in self.scenes[1:]:
            if s.time_label not in ladder:
                raise ValueError(
                    f"scene {s.index} time_label {s.time_label!r} not in ladder {ladder}"
                )
        consequence_labels = [s.time_label for s in self.scenes[1:]]
        if len(consequence_labels) != len(set(consequence_labels)):
            raise ValueError("consequence time_label values must be unique")
        label_positions = [ladder.index(label) for label in consequence_labels]
        if label_positions != sorted(label_positions):
            raise ValueError("consequence scenes must be ordered chronologically")
        present = set(consequence_labels)
        for lab in required_labels:
            if lab not in present:
                raise ValueError(f"at least one consequence scene must have time_label == {lab!r}")

        # cast ids
        cast_ids = {c.id for c in self.cast}
        if len(cast_ids) != len(self.cast):
            raise ValueError("cast ids must be unique")
        max_bench = int(schema["max_bench_per_scene"])
        for s in self.scenes:
            unknown = [cid for cid in s.cast_ids if cid not in cast_ids]
            if unknown:
                raise ValueError(f"scene {s.index} references unknown cast ids: {unknown}")
            if len(s.cast_ids) > len(self.cast):
                raise ValueError(f"scene {s.index} shows more characters than exist in cast")
            if not s.cast_ids and (s.poses or s.faces):
                raise ValueError(
                    f"scene {s.index} has no characters but still defines poses or faces"
                )
            benched = len(self.cast) - len(s.cast_ids)
            if s.cast_ids and benched > max_bench:
                raise ValueError(
                    f"scene {s.index} benches {benched} cast members; max is {max_bench}"
                )
            for k in s.poses.keys():
                if k not in cast_ids:
                    raise ValueError(f"scene {s.index} pose for unknown cast id {k!r}")
            for k in s.faces.keys():
                if k not in cast_ids:
                    raise ValueError(f"scene {s.index} face for unknown cast id {k!r}")

        # opening scene
        opening = self.scenes[0]
        if opening.scene_template != "intro_prop":
            raise ValueError("first scene must use scene_template == 'intro_prop'")
        if opening.caption.strip().lower() != self.opening_question.strip().lower():
            raise ValueError("first scene caption must equal opening_question")
        if opening.time_label not in ("", "opening", "+0"):
            # Accept a few sensible values; also accept the literal opening marker we inject.
            if opening.time_label != "opening":
                raise ValueError("first scene time_label must be empty or 'opening'")

        # word budget
        words = len(self.opening_question.split())
        for s in self.scenes[1:]:
            words += len(s.caption.split())
        if not (schema["min_words_total"] <= words <= schema["max_words_total"]):
            raise ValueError(
                f"total narration word count {words} outside "
                f"{schema['min_words_total']}..{schema['max_words_total']}"
            )

        return self


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """You are the scriptwriter for a mysterious, cinematic vertical short-video
series called "What If...?". Each video is ~30 seconds and follows a counterfactual as its
consequences unfold over time.

You MUST return a single strict JSON object. No prose, no code fences, no commentary.

The video structure is a miniature mystery:
1. Open with the exact premise as a question.
2. +1 hour: show the first unsettling sign that something is wrong.
3. +6 hours: escalate with a second-order consequence that people begin to notice.
4. +1 day: reveal the larger danger or hidden dependency.
5. Optionally continue with +1 week, +1 month or +1 year only if it creates a meaningful
   aftermath. Every beat must advance time and deepen the situation.

The narrator is the only voice; characters react and act, they do not speak.

The tone is mysterious, tense and intriguing, like a documentary mystery or a scientific
warning. Use vivid concrete images, unanswered questions and escalating consequences.
Do not sound like a textbook, listicle, encyclopedia entry or weather report. Do not begin
consequence captions with repetitive phrases such as "Within", "By the end", "Scientists
say", or "Studies show". Avoid stacking unrelated facts. Each caption should feel like the
next moment in one unfolding story.

Subjects are semi-unrealistic counterfactuals: whole classes of objects or animals (e.g.
"all cars", "bees", "the moon", "the internet", "all plastic", "all birds"). Not individual
foods, not people, not brands, not specific places.

JSON schema (all fields required unless noted):

{
  "title": "<short title for the video>",
  "opening_question": "What if <subject> vanished?",
  "cast": [
    {
      "id": "c1",
      "name": "<short human name>",
      "hair_style": "bob" | "ponytail" | "short" | "bun",
      "hair_color_idx": <0..7>,
      "accessory": "none" | "glasses" | "beanie" | "bow_tie" | "chef_hat",
      "accessory_color_idx": <0..5>,
      "bust": true | false
    }
    // 1 to 5 cast members, unique ids. The first is the main character.
  ],
  "scenes": [
    {
      "index": 0,
      "time_label": "opening",
      "scene_template": "intro_prop",
      "props": [{"type": "photo", "query": "<2-4 word noun phrase>"}],
      "cast_ids": ["c1"],   // use [] when characters would be distracting or unnecessary
      "poses": {"c1": "present"},
      "faces": {"c1": "smile"},
      "emphasis": ["<word>", ...],
      "caption": "What if <subject> vanished?",
      "shake": false,
      "claims": []
    },
    {
      "index": 1,
      "time_label": "+1 hour",
      "scene_template": "timeline_step" | "crowd_react" | "two_reactors"
                        | "two_props_compare" | "big_number",
      "props": [{"type": "photo"|"icon", ...}],
      "cast_ids": ["c1", "c2", ...],   // subset of cast, or [] for a props-only scene
      "poses": {"c1": "<pose>", ...},
      "faces": {"c1": "<face>", ...},
      "emphasis": ["<word>", ...],
      "caption": "<one suspenseful sentence for this moment, short enough to read in ~3 s>",
      "shake": true | false,
      "claims": ["<factual sub-claim the beat depends on, or [] if purely speculative>"]
    }
    // ... 3 to 7 consequence scenes
  ]
}

Hard rules:
- opening_question MUST equal "What if <subject> vanished?" for the given subject.
- The first scene has time_label "opening", scene_template "intro_prop", and caption equal to
  opening_question.
- Consequence labels MUST include "+1 hour", "+6 hours" and "+1 day", in that order.
- Consequence labels must be unique and chronologically ordered.
- Allowed time_labels: "+1 hour", "+6 hours", "+1 day", "+1 week", "+1 month", "+1 year".
- 4 to 8 scenes total (opening + 3..7 consequences).
- 1 to 5 cast members. Each scene may show a subset of the cast, or no characters when
  the beat is better shown through props, photos, icons or an environment.
- Total narration words across opening_question + all consequence captions: 55 to 130.
- Photo queries are 2-4 word plain-noun phrases describing a single object or animal. No
  people, no brand names, no scene descriptions, no text.
- Icon names are one of: question_mark, arrow, sparkle, no_sign, clock. Use no_sign on beats
  where the subject is gone.
- Poses: idle, present, point, pinch, shrug, think, wave, celebrate.
- Faces: smile, grin, open, meh, ew, brows_angry, brows_raised, brows_worried, brows_flat.
- Set shake=true only on dramatic consequence beats (max 5 across the video).
- Consequence captions should be one short, vivid sentence each (roughly 8-18 words) suitable
  for a single on-screen line.
- The "+1 hour" caption must show an observable first sign, not a general fact.
- The "+6 hours" caption must escalate or reveal a second-order consequence.
- The "+1 day" caption must contain the strongest reveal, danger or reversal in the story.
- Across the consequence captions, use a progression such as: disturbance -> escalation ->
  reveal -> aftermath. The captions must not read as interchangeable facts.
- Prefer active verbs and specific visual actions: lights fail, queues form, walls tremble,
  shelves empty, alarms spread, roads lock, nests emerge. Avoid abstract filler.
- Choose characters only when they react to, discover, handle or physically demonstrate
  something in the narration. Do not add random characters just to fill the frame.
- For ecosystems, infrastructure, technology and global systems, prefer props-only scenes
  unless a human reaction is specifically part of the beat. If cast_ids is [], poses and
  faces must both be empty objects.
"""


def _build_user_prompt(subject: str) -> str:
    return (
        f"Subject (the thing that vanishes): {subject!r}\n\n"
        f"Write a suspenseful timeline, not a list of facts. Make each beat the next event "
        f"in one escalating story, with the +1 day beat delivering the reveal. "
        f"Produce the JSON object now. "
        f"The opening_question must be exactly: \"What if {subject} vanished?\""
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def run(subject: str, run_dir: Path, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the script stage, writing script.json in run_dir. Returns the script dict."""
    cfg = cfg or load_config()
    out_path = run_dir / "script.json"
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(subject)

    last_error: Optional[str] = None
    attempts = int(cfg["groq"]["max_retries"])
    for attempt in range(1, attempts + 1):
        _LOG.info("Script attempt %d/%d (subject=%r)", attempt, attempts, subject)
        try:
            raw = chat_json(
                cfg,
                system=system,
                user=user if attempt == 1 else build_retry_user_prompt(
                    _build_user_prompt(subject), last_error or "unknown"
                ),
                temperature=cfg["groq"]["temperature_script"],
                max_tokens=4096,
            )
            script = Script(**raw)
        except (GroqError, ValidationError, ValueError) as e:
            last_error = str(e)
            _LOG.warning("Script validation failed: %s", last_error)
            continue

        payload = script.model_dump()
        # Normalize opening scene time_label to "opening" for downstream code.
        payload["scenes"][0]["time_label"] = "opening"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        _LOG.info("Wrote %s (%d scenes, %d cast)", out_path, len(payload["scenes"]), len(payload["cast"]))
        return payload

    raise RuntimeError(
        f"Script stage failed after {attempts} attempts. Last error: {last_error}"
    )


def load(run_dir: Path) -> Dict[str, Any]:
    """Load a previously-written script.json."""
    return json.loads((run_dir / "script.json").read_text(encoding="utf-8"))