# Prompt Lab

A friendly, local-first command-line tool for a **versioned prompt library**.

Save your prompts with notes and tags, keep every revision, diff any two
versions, and run saved test inputs against any OpenAI-compatible endpoint —
with **Ollama on your own machine** as the default. Then export a run report
so you can see exactly what changed and how each version behaved.

Built the way a friend would build it: plain English, step by step, nothing
to sign up for. Prompt Lab **never asks for an API key** — it is designed for
local or self-hosted servers, so there is nothing sensitive to leak.

From [Asdale Dynamics, LLC](https://dylanasdale.github.io) — AI explained like
a friend would. MIT licensed.

---

## Why Prompt Lab?

If you write prompts, you already know the pain: you tweak a line, the
results change, and two weeks later you can't remember what version worked.
Prompt Lab fixes that with three habits:

1. **Save** each version with a note about what changed.
2. **Diff** versions the same way you'd diff code.
3. **Test** each version against the same inputs, and export a report.

Everything lives in an ordinary folder on your disk. No database, no cloud,
no account.

## Requirements

- Python 3.10 or newer (nothing else — no third-party packages)
- *Optional:* [Ollama](https://ollama.com) running locally (or LM Studio,
  llama.cpp server, vLLM — anything that speaks the OpenAI
  `/v1/chat/completions` format)

## Getting started

```bash
# from this folder, with no installation needed:
python3 -m promptlab init --samples   # creates ~/.promptlab with sample prompts
python3 -m promptlab list             # see what's in the library
```

`--samples` gives you three ready-made prompts, each with saved versions and
test inputs, so you can see the whole workflow before writing anything of
your own.

A one-off test that never touches the network (renders the prompt, prints
what *would* be sent):

```bash
python3 -m promptlab run everyday-explainer --input "what a token is" --dry-run
```

Small local models do better with shorter, structured prompts — the samples
show that style, and version 2 of each sample shows a common improvement.

## The basics

### Save a prompt (and every version after it)

```bash
echo 'Explain {{input}} in one friendly sentence.' \
  | promptlab add my-explainer --tags writing,beginner --notes 'first try'

promptlab update my-explainer --file my-explainer.txt --notes 'made it warmer'
```

Notes travel with each version, so `promptlab versions my-explainer` reads
like a changelog you wrote to your future self.

### Look around

```bash
promptlab list                 # everything in the library
promptlab list --tag writing   # filtered by tag
promptlab show my-explainer    # latest version
promptlab show my-explainer 1  # a specific version
promptlab versions my-explainer
```

### Diff two versions

```bash
promptlab diff my-explainer        # last two versions
promptlab diff my-explainer 1 3    # any two you like
```

### Run saved tests against your endpoint

Each prompt can carry a `tests.json` (plain text inputs, one per case). Then:

```bash
promptlab run my-explainer                          # runs the saved tests
promptlab run my-explainer --report                 # also writes a Markdown report
promptlab run my-explainer --report r.json --report-format json
promptlab run my-explainer --input 'one-off text'   # ad-hoc test instead
```

The report records which prompt version you ran, where, the input, output,
and latency for each test — handy evidence when you're deciding whether the
new wording actually helped.

### Point it at your server

The defaults are Ollama-ish: `base_url http://localhost:11434/v1` and model
`llama3.2`. Override per command:

```bash
promptlab run my-explainer --base-url http://localhost:8080/v1 --model qwen2.5
promptlab models --base-url http://localhost:8080/v1   # see what the server offers
```

...or set it once in your library's `config.json`:

```json
{ "base_url": "http://localhost:11434/v1", "model": "qwen2.5" }
```

Environment variables work too: `PROMPTLAB_LIBRARY` (folder), `PROMPTLAB_BASE_URL`,
`PROMPTLAB_MODEL`. Command-line flags beat config, which beats defaults.

> **No API keys, by design.** Prompt Lab sends plain HTTP requests with no
> `Authorization` header, and it will refuse a config file that tries to give
> it one. If your endpoint needs a key, that service isn't the point of this
> tool — a local server is.

## Templates

Use `{{input}}` anywhere in a prompt; every test input is swapped in there.
If your prompt has no `{{input}}`, Prompt Lab warns you, since every test
would then run the exact same text.

## Where your library lives

Default: `~/.promptlab`. Use `--library DIR` to work with any other folder
(great for keeping one library per project, or syncing your own way).

```
Library layout:
~/.promptlab/
  config.json              # endpoint defaults
  prompts/
    everyday-explainer/
      meta.json            # description, tags, version notes
      versions/0001.md     # each version's full prompt text
      versions/0002.md
      tests.json           # saved test inputs (optional)
```

It's all plain files — open them in any editor, copy the folder to back it
up, drop it in a repo.

## Command reference

| Command | What it does |
| --- | --- |
| `init [--samples]` | Create a library; optionally copy in the sample prompts |
| `list [--tag T]` | List prompts, newest-updated first |
| `add NAME --file F` | New prompt: version 1 (or pipe text via stdin) |
| `update NAME --file F` | New version of an existing prompt |
| `show NAME [VER]` | Print a prompt's text |
| `versions NAME` | List versions with notes |
| `diff NAME [FROM] [TO]` | Unified diff between versions |
| `meta NAME --add-tag T` | Edit tags/description/notes without a new version |
| `run NAME` | Run saved tests (see flags: `--input`, `--dry-run`, `--report`...) |
| `models` | List models the endpoint offers |
| `config` | Show the running configuration |

Run any command with `--help` for the full flag list.

## Privacy in one sentence

Prompt Lab reads and writes only the library folder you point it at, talks
only to the endpoint you configure, and contains no telemetry, accounts, or
key material.

## Testing

The test suite is offline — endpoint calls are either mocked or served by a
fake localhost server:

```bash
python3 -m unittest discover -s tests -v
```

## License & credit

MIT License — see [LICENSE](LICENSE). Copyright (c) 2026 Asdale Dynamics, LLC.

Prompt Lab is part of the Asdale Dynamics family of beginner-friendly AI
tools and guides. Visit [dylanasdale.github.io](https://dylanasdale.github.io)
for more, including *The Massive AI Manual*.
