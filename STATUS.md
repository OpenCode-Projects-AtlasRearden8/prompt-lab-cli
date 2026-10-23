# Prompt Lab — STATUS

Last verified: 2026-10-22

## What was built

**Prompt Lab** (`prompt-lab` v0.1.0) — a friendly, local-first Python CLI for a
versioned prompt library. Zero third-party dependencies (standard library
only, Python 3.10+). Built by Asdale Dynamics, LLC for beginner-friendly, no-
nonsense AI work.

Features:

- **Versioned prompt library** stored as plain files in a folder on disk
  (`~/.promptlab` by default, or any folder via `--library` / `PROMPTLAB_LIBRARY`).
  Each prompt keeps a description, tags, notes, per-version notes, and one
  markdown file per version (`versions/0001.md`, ...). No database, no cloud.
- **Commands**: `init` (with `--samples` starter prompts), `list` (`--tag`
  filtering), `add` (file or stdin, with notes/tags/description, optional
  `--save-tests`), `update` (new version + note), `show`, `versions`,
  `diff` (unified diff, defaults to last two versions), `meta` (edit
  tags/description/notes/test inputs without a new version), `run`, `models`,
  `config`.
- **Test running**: `run` sends each test input to an OpenAI-compatible
  chat endpoint. Inputs come from `--input`, a `--tests FILE`, or the
  prompt's saved `tests.json`. Prompts use a single `{{input}}` placeholder;
  `--dry-run` renders without calling anything; `--show-renders` previews.
  Flags for `--system`, `--temperature`, `--max-tokens`, `--timeout`.
- **Endpoint config** (never a key): defaults to Ollama at
  `http://localhost:11434/v1` with model `llama3.2`. Overridable per command
  (`--base-url`, `--model`) or in the library's `config.json` (plus
  `PROMPTLAB_BASE_URL` / `PROMPTLAB_MODEL` env vars). The HTTP layer sends no
  `Authorization` header at all, and config files or env vars carrying API
  keys are rejected loudly.
- **Run reports**: `--report [PATH]` writes a Markdown (default) or JSON
  (`--report-format json`) report with prompt version, endpoint/model, per-test
  input/output/error, latency, and an ok/failed summary — with exit code 1 if
  any test failed. `--report` with no path writes `reports/run-NAME-<timestamp>`.
- **Sample library** (3 prompts, each with versions + test inputs):
  `everyday-explainer` (v1, v2), `summarize-notes` (v1, v2), `email-polisher`.

## Layout

```
prompt-lab-cli/
  promptlab/            # package: cli.py, storage.py, config.py, runner.py, report.py
  tests/                # offline unittest suite (54 tests)
  samples/library/      # bundled sample prompts + config
  README.md, LICENSE (MIT), pyproject.toml, .gitignore
```

## How to run it

No install needed from this folder:

```bash
python3 -m promptlab init --samples      # creates ~/.promptlab with samples
python3 -m promptlab list
python3 -m promptlab run everyday-explainer --input "what a token is" --dry-run
python3 -m promptlab run everyday-explainer --report   # against localhost:11434/v1 (Ollama)
```

Any other folder: add `--library DIR`. Any other server: add
`--base-url http://host:port/v1 --model NAME` (LM Studio, llama.cpp, vLLM —
anything OpenAI-compatible).

Installable with `pip install .` (provides the `promptlab` command); the
wheel build was verified to a target directory.

## Verification results

- `python3 -m unittest discover -s tests -v` — **54 tests, all OK** (~1.1s).
- Full-repo `python3 -m compileall` — clean.
- Shell smoke tests (all passed):
  - `init --samples` + `list` + `versions` + `diff everyday-explainer` —
    samples load, diff shows the v1→v2 changes.
  - `run ... --dry-run` — renders and exits 0 without touching the network.
  - `run` against a **fake localhost OpenAI endpoint** — correct
    `/chat/completions` payload, outputs echoed, exit 0.
  - `run` against an unreachable port — friendly "Is the server running?"
    message, per-test FAILED lines, report still written, exit 1.
  - `--report` Markdown examined by hand: header, per-test sections, and
    the Asdale Dynamics footer present; JSON report parses and sums ok/error.
  - `config` shows resolved settings; a config file containing `api_key` is
    rejected with a clear message (exit 1).
  - `pip install . --target` build → `promptlab --version` works from the
    installed console script and `python -m promptlab`.
- Tests themselves run fully offline: endpoint calls are either mocked at the
  socket layer or served by a fake `http.server` on 127.0.0.1. No test
  touches the internet, and no test needs Ollama installed.

## Known gaps

- The `{{input}}` placeholder is the only template variable (no conditionals,
  loops, or multi-variable templates). Deliberate: it keeps beginners safe.
- One HTTP call per test run (sequential, no concurrency, no streaming
  output); each test is a separate chat completion.
- `run` prints outputs after the fact rather than step-by-step with the
  response; the console log intentionally stays short.
- No `edit` command opening an interactive editor yet (use `update --file`
  or stdin); no import/export of whole libraries beyond copying the folder,
  no search across prompt versions, no `rerun` report-comparison view.
- The samples default to model `llama3.2`; users on other Ollama models
  should change `config.json` or pass `--model`.
- Report Markdown escapes nothing (raw prompt/model text is inserted); fine
  for local use, but treat as plain text, not sanitized HTML.
- `models`/`run` assume OpenAI-style `/models` and `/chat/completions`
  suffixes on the base URL; a server that deviates from that layout needs a
  base_url tweak.
- pytest is not installed in this environment, so the suite uses stdlib
  `unittest` (works everywhere; runs with `python3 -m unittest discover -s tests`).

## License / credit

MIT — `LICENSE`, copyright line exactly `Copyright (c) 2026 Asdale Dynamics, LLC`.
Asdale Dynamics, LLC is credited in `README.md` and in the report footer.
