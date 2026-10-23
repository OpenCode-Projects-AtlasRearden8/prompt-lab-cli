"""The Prompt Lab command line interface.

Everything here is plain argparse and the standard library.
Exit codes: 0 = success, 1 = something went wrong, 2 = usage problem.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path

from . import __version__, config, report, runner, storage

PROG = "promptlab"
SAMPLE_RELPATH = Path("samples") / "library"


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    args = parser.parse_args(list(argv))
    if args.show_version:
        print(f"{PROG} {__version__}")
        return 0
    if not args.command:
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except storage.StorageError as exc:
        return _fail(str(exc))
    except KeyboardInterrupt:
        return _fail("Interrupted.")
    except BrokenPipeError:
        return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Prompt Lab: a friendly, local-first CLI for a versioned prompt library. "
            "Save prompts with notes and tags, diff versions, and run saved test "
            "inputs against any OpenAI-compatible endpoint (Ollama by default). "
            "No API keys, ever."
        ),
        epilog=(
            "Examples:\n"
            "  promptlab init --samples\n"
            "  promptlab add everyday-explainer --file e.txt --tags writing,education\n"
            "  promptlab diff everyday-explainer\n"
            "  promptlab run everyday-explainer --report --report-format json"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--library",
        metavar="DIR",
        help="path to the library folder (default ~/.promptlab, or $PROMPTLAB_LIBRARY)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        dest="show_version",
        help="print the Prompt Lab version and exit",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="create a new library folder")
    p.add_argument("--samples", action="store_true", help="copy the bundled sample prompts in")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("list", help="list prompts in the library")
    p.add_argument("--tag", help="only show prompts with this tag")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="add a new prompt (version 1)")
    p.add_argument("name")
    p.add_argument("--file", help="read the prompt text from this file")
    p.add_argument("--stdin", action="store_true", help="read the prompt text from stdin")
    p.add_argument("--notes", default="", help="notes for version 1")
    p.add_argument("--tags", default="", help="comma-separated tags")
    p.add_argument("--description", default="", help="one-line description of the prompt")
    p.add_argument(
        "--save-tests",
        metavar="FILE",
        help="also save a tests.json (list of texts, or objects with name/input)",
    )
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="add a new version of an existing prompt")
    p.add_argument("name")
    p.add_argument("--file", help="read the new prompt text from this file")
    p.add_argument("--stdin", action="store_true", help="read the new prompt text from stdin")
    p.add_argument("--notes", default="", help="notes describing what changed")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("show", help="print a prompt's text")
    p.add_argument("name")
    p.add_argument("version", nargs="?", default=None, help="version number or 'latest'")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("versions", help="list a prompt's versions and notes")
    p.add_argument("name")
    p.set_defaults(func=cmd_versions)

    p = sub.add_parser("diff", help="show a unified diff between two versions")
    p.add_argument("name")
    p.add_argument("from_version", nargs="?", default=None, help="e.g. 1 (default: second-latest)")
    p.add_argument("to_version", nargs="?", default=None, help="e.g. 2 (default: latest)")
    p.add_argument("--context", type=int, default=3, help="lines of context (default 3)")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("meta", help="edit a prompt's tags, description, or notes")
    p.add_argument("name")
    p.add_argument("--tags", help="replace all tags (comma-separated)")
    p.add_argument("--add-tag", metavar="TAG", help="add one tag")
    p.add_argument("--remove-tag", metavar="TAG", help="remove one tag")
    p.add_argument("--description", help="set the description")
    p.add_argument("--notes", help="set the overall notes")
    p.add_argument("--save-tests", metavar="FILE", help="(re)write the prompt's tests.json from a file")
    p.set_defaults(func=cmd_meta)

    p = sub.add_parser("run", help="run test inputs against the chat endpoint")
    p.add_argument("name")
    p.add_argument("--version", default=None, help="prompt version to run (default latest)")
    p.add_argument("--input", help="run one ad-hoc input instead of the saved tests.json")
    p.add_argument("--tests", metavar="FILE", help="use this test input file instead of tests.json")
    p.add_argument("--base-url", help=f"endpoint base URL (default {config.DEFAULT_BASE_URL})")
    p.add_argument("--model", help="model name at the endpoint")
    p.add_argument("--system", help="system message")
    p.add_argument("--temperature", type=float)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--timeout", type=float, help="per-request timeout in seconds")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print rendered prompts; do not call the endpoint at all",
    )
    p.add_argument("--show-renders", action="store_true", help="also print each rendered prompt")
    p.add_argument(
        "--report",
        nargs="?",
        const="default",
        default=None,
        metavar="PATH",
        help="write a run report (default path: reports/run-NAME-TIMESTAMP)",
    )
    p.add_argument("--report-format", choices=("markdown", "json"), default="markdown")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("models", help="list models the endpoint offers")
    p.add_argument("--base-url", help=f"endpoint base URL (default {config.DEFAULT_BASE_URL})")
    p.add_argument("--timeout", type=float, default=10.0)
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("config", help="show the running configuration")
    p.set_defaults(func=cmd_config)

    return parser


# ------------------------------------------------------------------ helpers

def _root_from_args(args):
    if getattr(args, "library", None):
        return Path(args.library).expanduser()
    return config.default_library_root()


def _require_library(args):
    lib = storage.Library(_root_from_args(args))
    if not lib.exists():
        raise storage.StorageError(
            f"No Prompt Lab library found at {lib.root}.\n"
            f"Create one first: {PROG} init [--samples]  (or pass --library DIR)"
        )
    return lib


def _read_content(args):
    if getattr(args, "file", None):
        path = Path(args.file)
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise storage.StorageError(f"Could not read {path}: {exc}") from exc
    if getattr(args, "stdin", None) or not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return text
        raise storage.StorageError(
            f"No prompt text found. Pipe it in (echo 'your text' | {PROG} add NAME) or pass --file."
        )
    raise storage.StorageError(
        f"No prompt text given. Try a pipe: echo 'your text' | {PROG} add NAME --notes 'first draft'"
    )


def _tests_from_args(args, lib, slug):
    if getattr(args, "tests", None):
        if getattr(args, "input", None):
            raise storage.StorageError("Use either --input or --tests, not both.")
        lib.load_meta(slug)
        return storage.load_test_inputs(args.tests)
    if getattr(args, "input", None):
        return [{"name": "input", "input": args.input}]
    saved = lib.read_tests(slug)
    if saved:
        return saved
    raise storage.StorageError(
        f"No test inputs found for '{slug}'. Save some with "
        f"`{PROG} meta {slug} --save-tests FILE`, or run once with --input 'text here'."
    )


def _report_path(args, slug):
    if args.report is None:
        return None
    if args.report == "default":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        ext = "json" if args.report_format == "json" else "md"
        return Path("reports") / f"run-{slug}-{stamp}.{ext}"
    return Path(args.report).expanduser()


def _endpoint_settings(args, lib):
    cfg = config.load_config(lib.root)
    return {
        "base_url": args.base_url or cfg["base_url"],
        "model": args.model or cfg["model"],
        "temperature": args.temperature if args.temperature is not None else cfg["temperature"],
        "timeout": args.timeout if args.timeout is not None else cfg["timeout"],
        "max_tokens": args.max_tokens if args.max_tokens is not None else cfg["max_tokens"],
        "system": args.system if args.system is not None else cfg["system"],
    }


def _fail(message):
    print(f"error: {message}", file=sys.stderr)
    return 1


# ------------------------------------------------------------------ commands

def cmd_init(args):
    root = _root_from_args(args)
    lib = storage.Library(root)
    created = not lib.exists()
    lib.init()
    config.write_defaults(root)
    if getattr(args, "samples", False):
        sample_root = _samples_root()
        if sample_root is None:
            raise storage.StorageError(
                "Could not find the bundled samples folder; it ships with the source repo."
            )
        lib.populate_from(sample_root)
    actions = "Created" if created else "Reusing"
    print(f"{actions} library at: {root}")
    print("")
    print("Next steps:")
    print(f"  {PROG} list")
    print(f"  {PROG} add my-prompt --file my-prompt.txt --tags writing --notes 'first try'")
    print(f"  {PROG} run my-prompt --input 'test text' --dry-run   (preview, nothing sent)")
    print(f"  {PROG} run my-prompt   (send saved tests to the endpoint)")
    return 0


def _samples_root():
    here = Path(__file__).resolve().parent
    for base in (here.parent, *here.parents):
        candidate = base / SAMPLE_RELPATH
        if candidate.is_dir():
            return candidate
    return None


def cmd_list(args):
    lib = _require_library(args)
    names = lib.prompt_names()
    if not names:
        print("This library is empty.")
        print("")
        print(f"Try: {PROG} init --samples   or   {PROG} add my-prompt --file my-prompt.txt")
        return 0
    wanted_tag = getattr(args, "tag", None)
    shown = 0
    for name in names:
        meta = lib.load_meta(name)
        tags = meta.get("tags") or []
        if wanted_tag and wanted_tag not in tags:
            continue
        shown += 1
        ids = [v["id"] for v in meta.get("versions", [])]
        latest = max(ids) if ids else "-"
        plural = "" if len(ids) == 1 else "s"
        tags_text = ", ".join(tags) if tags else "-"
        updated = (meta.get("updated") or "")[:10]
        print(
            f"{name}  [{tags_text}]  v{latest}"
            f" ({len(ids)} version{plural}, updated {updated})"
        )
        if meta.get("description"):
            print(f"  {meta['description']}")
    if wanted_tag and shown == 0:
        print(f"No prompts tagged '{wanted_tag}'.")
    return 0


def cmd_add(args):
    lib = _require_library(args)
    content = _read_content(args)
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    test_inputs = storage.load_test_inputs(args.save_tests) if args.save_tests else None
    slug = lib.add_prompt(
        args.name,
        content,
        notes=args.notes,
        tags=tags,
        description=args.description,
        test_inputs=test_inputs,
    )
    print(f"Saved '{slug}' as version 1.")
    if test_inputs is not None:
        print(f"Saved {len(test_inputs)} test input(s) to {lib.tests_path(slug)}")
    print(f"Try: {PROG} show {slug}  |  {PROG} run {slug} --input 'test text'")
    return 0


def cmd_update(args):
    lib = _require_library(args)
    content = _read_content(args)
    slug = lib.add_version(args.name, content, notes=args.notes)
    print(f"Saved '{slug}' as a new version.")
    print(f"Compare with: {PROG} diff {slug}")
    return 0


def cmd_show(args):
    lib = _require_library(args)
    meta = lib.load_meta(args.name)
    vid = lib.resolve_version(meta, args.version)
    content = lib.read_version(args.name, vid)
    tags = ", ".join(meta.get("tags") or []) or "-"
    print(f"# {meta['name']} (version {vid})")
    print(f"# tags: {tags}")
    if meta.get("description"):
        print(f"# {meta['description']}")
    print("")
    sys.stdout.write(content if content.endswith("\n") else content + "\n")
    return 0


def cmd_versions(args):
    lib = _require_library(args)
    meta = lib.load_meta(args.name)
    latest = lib.latest_version_id(meta)
    print(f"{meta['name']} — {len(meta['versions'])} version(s)")
    for v in sorted(meta["versions"], key=lambda v: v["id"]):
        current = "  (current)" if v["id"] == latest else ""
        notes = v.get("notes") or ""
        notes_line = f" — {notes}" if notes else ""
        print(f"  v{v['id']}  {v.get('created', '')}{notes_line}{current}")
    return 0


def cmd_diff(args):
    lib = _require_library(args)
    slug = storage.slugify(args.name)
    a, b, text_a, text_b = lib.diff(slug, args.from_version, args.to_version)
    diff = unified_diff(
        text_a.splitlines(keepends=True),
        text_b.splitlines(keepends=True),
        fromfile=f"{slug} v{a}",
        tofile=f"{slug} v{b}",
        n=args.context,
    )
    sys.stdout.writelines(diff)
    return 0


def cmd_meta(args):
    lib = _require_library(args)
    slug = storage.slugify(args.name)
    meta = lib.load_meta(slug)
    if args.description is not None:
        meta["description"] = args.description.strip()
    if args.notes is not None:
        meta["notes"] = args.notes.strip()
    if args.tags is not None:
        meta["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.add_tag and args.add_tag.strip() not in meta.get("tags", []):
        meta.setdefault("tags", []).append(args.add_tag.strip())
    if args.remove_tag and args.remove_tag.strip() in meta.get("tags", []):
        meta["tags"].remove(args.remove_tag.strip())
    lib.save_meta(slug, meta)
    if args.save_tests:
        lib.write_tests(slug, storage.load_test_inputs(args.save_tests))
        print(f"Saved test inputs to {lib.tests_path(slug)}")
    tags = ", ".join(meta.get("tags") or []) or "-"
    print(f"{slug}: tags [{tags}] — {len(meta['versions'])} version(s)")
    return 0


def cmd_run(args):
    lib = _require_library(args)
    slug = storage.slugify(args.name)
    meta = lib.load_meta(slug)
    version_id = lib.resolve_version(meta, args.version)
    template = lib.read_version(slug, version_id)
    tests = _tests_from_args(args, lib, slug)
    settings = _endpoint_settings(args, lib)

    if not runner.render(template, "placeholder-check")[1]:
        print(
            "note: this prompt has no {{input}} placeholder, "
            "so every test will run essentially the same text.",
            file=sys.stderr,
        )

    print(f"Running '{slug}' (version {version_id}) on {settings['base_url']} (model {settings['model']})")
    print("")
    if args.dry_run:
        return _run_dry(args, slug, tests, template)
    return _run_live(args, lib, slug, version_id, tests, template, settings)


def _run_dry(args, slug, tests, template):
    for i, test in enumerate(tests, start=1):
        rendered, _ = runner.render(template, test["input"])
        if args.show_renders:
            print(f"--- rendered: {test['name']} ---")
            print(rendered)
            print("")
        print(f"[{i}/{len(tests)}] {test['name']} … dry-run preview:")
        print(rendered)
        print("")
    print(f"Dry-run complete. Nothing was sent anywhere. ({len(tests)} test(s) rendered)")
    return 0


def _run_live(args, lib, slug, version_id, tests, template, settings):
    print(f"{len(tests)} test(s) to run.\n")
    results = []
    for i, test in enumerate(tests, start=1):
        rendered, _ = runner.render(template, test["input"])
        if args.show_renders:
            print(f"--- rendered ({test['name']}) ---")
            print(rendered)
            print("")
        outcome = runner.chat(
            settings["base_url"],
            settings["model"],
            rendered,
            system=settings["system"],
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"],
            timeout=settings["timeout"],
        )
        if outcome["ok"]:
            print(f"[{i}/{len(tests)}] {test['name']} … ok ({outcome['latency']:.2f}s)")
        else:
            print(f"[{i}/{len(tests)}] {test['name']} … FAILED — {outcome['error']}")
        results.append(outcome)

    entries = report.build_entries(results, tests)
    report_path = _report_path(args, slug)
    if report_path is not None:
        meta_report = {
            "prompt": slug,
            "prompt_version": version_id,
            "base_url": settings["base_url"],
            "model": settings["model"],
        }
        body = (
            report.build_json(meta_report, entries)
            if args.report_format == "json"
            else report.build_markdown(meta_report, entries)
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(body, encoding="utf-8")
        print("")
        print(f"Report written: {report_path}")

    for entry in entries:
        if entry["status"] == "ok":
            print("")
            print(f"=== {entry['name']} ===")
            print(entry["output"])

    failed = sum(1 for e in entries if e["status"] != "ok")
    print("")
    if failed:
        print(f"Done with problems: {failed} of {len(entries)} test(s) failed.")
        return 1
    print(f"Done: all {len(entries)} test(s) succeeded.")
    return 0


def cmd_models(args):
    cfg = config.load_config(_root_from_args(args))
    base_url = args.base_url or cfg["base_url"]
    try:
        models = runner.list_models(base_url, timeout=args.timeout)
    except OSError as exc:
        reason = getattr(exc, "reason", exc)
        return _fail(f"Could not reach {base_url}: {reason}. Is the server running?")
    except ValueError as exc:
        return _fail(str(exc))
    if not models:
        print(f"The endpoint {base_url} returned no models.")
        return 0
    print(f"Models at {base_url}:")
    for m in models:
        print(f"  {m}")
    return 0


def cmd_config(args):
    cfg = config.load_config(_root_from_args(args))
    print(json.dumps(cfg, indent=2))
    return 0
