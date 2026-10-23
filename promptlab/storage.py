"""Local storage for the prompt library.

The library is an ordinary folder on disk, so everything stays readable,
portable, and easy to back up:

    <library>/
      config.json
      prompts/
        plain-explainer/
          meta.json          (tags, notes, description, version list)
          versions/0001.md   (prompt text for version 1)
          versions/0002.md
          tests.json         (optional saved test inputs)

No database. No cloud. Just files.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    if not slug:
        raise ValueError(
            "That prompt name doesn't have any usable characters. "
            "Try letters, numbers, and hyphens, like 'my-prompt'."
        )
    return slug


def version_dir_name(version_id):
    return f"{int(version_id):04d}"


class StorageError(Exception):
    pass


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.prompts_dir = self.root / "prompts"

    # ------------------------------------------------------------- lifecycle

    def exists(self):
        return self.prompts_dir.is_dir()

    def init(self):
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        return self.root

    def populate_from(self, source_root):
        source_root = Path(source_root)
        if not source_root.is_dir():
            raise StorageError(f"Sample library not found at: {source_root}")
        return self._merge_dir(source_root, self.root)

    def _merge_dir(self, src, dest):
        copied = []
        dest.mkdir(parents=True, exist_ok=True)
        for item in sorted(src.iterdir()):
            target = dest / item.name
            if item.is_dir():
                copied.extend(self._merge_dir(item, target))
            else:
                if not target.exists():
                    shutil.copy2(item, target)
                    copied.append(target)
        return copied

    # ------------------------------------------------------------ prompt list

    def prompt_names(self):
        if not self.exists():
            return []
        return sorted(
            p.name for p in self.prompts_dir.iterdir()
            if p.is_dir() and (p / "meta.json").is_file()
        )

    def load_meta(self, name):
        slug = slugify(name)
        path = self._meta_path(slug)
        if not path.is_file():
            raise StorageError(f"No prompt named '{slug}' in this library.")
        return _read_json(path)

    def save_meta(self, slug, meta):
        meta["name"] = slug
        meta["updated"] = utc_now()
        _write_json(self._meta_path(slug), meta)

    def _prompt_dir(self, slug):
        return self.prompts_dir / slug

    def _meta_path(self, slug):
        return self._prompt_dir(slug) / "meta.json"

    # ------------------------------------------------------------- mutations

    def add_prompt(self, name, content, notes="", tags=None, description="", test_inputs=None):
        slug = slugify(name)
        meta_path = self._meta_path(slug)
        if meta_path.is_file():
            raise StorageError(
                f"A prompt named '{slug}' already exists. "
                "Add a new version with: promptlab update"
            )
        meta = {
            "name": slug,
            "description": description.strip(),
            "notes": notes.strip(),
            "tags": list(tags),
            "created": utc_now(),
            "updated": utc_now(),
            "versions": [],
        }
        self._write_version_file(slug, 1, content)
        meta["versions"].append({"id": 1, "created": utc_now(), "notes": notes.strip()})
        self.save_meta(slug, meta)
        if test_inputs is not None:
            self.write_tests(slug, test_inputs)
        return slug

    def add_version(self, name, content, notes=""):
        slug = slugify(name)
        meta = self.load_meta(slug)
        new_id = max(v["id"] for v in meta["versions"]) + 1 if meta["versions"] else 1
        self._write_version_file(slug, new_id, content)
        meta["versions"].append({"id": new_id, "created": utc_now(), "notes": notes.strip()})
        self.save_meta(slug, meta)
        return new_id

    def _write_version_file(self, slug, version_id, content):
        vdir = self._prompt_dir(slug) / "versions"
        vdir.mkdir(parents=True, exist_ok=True)
        path = vdir / f"{version_dir_name(version_id)}.md"
        path.write_text(content, encoding="utf-8")
        return path

    # -------------------------------------------------------------- reading

    def read_version(self, name, version_id):
        slug = slugify(name)
        meta = self.load_meta(slug)
        vid = self.resolve_version(meta, version_id)
        path = self._prompt_dir(slug) / "versions" / f"{version_dir_name(vid)}.md"
        if not path.is_file():
            raise StorageError(f"Version {vid} of '{slug}' is missing its content file: {path}")
        return path.read_text(encoding="utf-8")

    def resolve_version(self, meta, version_id):
        """Accept an int, '2', 'v2', or 'latest'; return the resolved int id."""
        versions = meta.get("versions") or []
        if not versions:
            raise StorageError(f"Prompt '{meta.get('name')}' has no versions yet.")
        if version_id is None or (isinstance(version_id, str) and version_id.lower() == "latest"):
            return max(v["id"] for v in versions)
        try:
            vid = int(str(version_id).lstrip("vV"))
        except ValueError as exc:
            raise StorageError(
                f"Unknown version '{version_id}'. Use a number (like 1) or 'latest'."
            ) from exc
        known = {v["id"] for v in versions}
        if vid not in known:
            known_ids = ", ".join(str(v["id"]) for v in sorted(versions, key=lambda v: v["id"]))
            raise StorageError(
                f"Prompt '{meta.get('name')}' has no version {vid}. Known versions: {known_ids}"
            )
        return vid

    def latest_version_id(self, meta):
        return self.resolve_version(meta, "latest")

    # ------------------------------------------------------------- test inputs

    def tests_path(self, name):
        return self._prompt_dir(slugify(name)) / "tests.json"

    def read_tests(self, name):
        path = self.tests_path(name)
        if not path.is_file():
            return None
        return load_test_inputs(path)

    def write_tests(self, name, test_inputs):
        slug = slugify(name)
        self.load_meta(slug)
        normalized = [
            {"name": t["name"], "input": t["input"]} for t in normalize_test_inputs(test_inputs)
        ]
        _write_json(self.tests_path(slug), {"tests": normalized})
        return self.tests_path(slug)

    # ------------------------------------------------------------------ diff

    def diff(self, name, from_id, to_id):
        slug = slugify(name)
        meta = self.load_meta(slug)
        if len(meta["versions"]) < 2 and (from_id is None or to_id is None):
            raise StorageError(
                f"'{slug}' has only {len(meta['versions'])} version(s). "
                "A diff needs two."
            )
        if from_id is None:
            ordered = sorted(v["id"] for v in meta["versions"])
            from_id = ordered[-2] if len(ordered) >= 2 else ordered[0]
        if to_id is None:
            to_id = "latest"
        a = self.resolve_version(meta, from_id)
        b = self.resolve_version(meta, to_id)
        text_a = self.read_version(slug, a)
        text_b = self.read_version(slug, b)
        if a == b and text_a == text_b:
            raise StorageError(
                f"Nothing to compare: {from_id} and {to_id} both point to version {a}."
            )
        return a, b, text_a, text_b


# ------------------------------------------------------------------ helpers

def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StorageError(f"Could not read JSON file {path}: {exc}") from exc


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def normalize_test_inputs(raw):
    """Accept ['string'] or [{'name','input'}] or {'tests': any of those}. Return [{name,input}]."""
    if isinstance(raw, dict) and isinstance(raw.get("tests"), (list, tuple)):
        raw = raw["tests"]
    if not isinstance(raw, (list, tuple)):
        raise StorageError(
            "Test inputs must be a list, or an object with a 'tests' list "
            "(see tests.json in the sample library)."
        )
    normalized = []
    for i, item in enumerate(raw, start=1):
        if isinstance(item, str):
            text = item.strip()
            label = None
        elif isinstance(item, dict):
            text = str(item.get("input", "")).strip()
            label = item.get("name")
        else:
            raise StorageError(f"Test #{i} is not a string or an object.")
        if not text:
            raise StorageError(f"Test #{i} has empty input text.")
        normalized.append({"name": label or f"test-{i}", "input": text})
    return normalized


def load_test_inputs(path):
    return normalize_test_inputs(_read_json(Path(path)))
