# panagent

`panagent` converts agent histories and public chat snapshots through a provider-neutral conversation representation. It preserves source provenance, keeps tool call IDs where the source exposes them, and reports what could not be carried across instead of silently pretending conversion is exact.

Supported paths:

| Source | Neutral JSON | Claude Code JSONL | Codex JSONL | Markdown |
| --- | :---: | :---: | :---: | :---: |
| Claude Code JSONL | ✓ | ✓ | ✓ | ✓ |
| Codex JSONL | ✓ | ✓ | ✓ | ✓ |
| ChatGPT public share | ✓ | ✓ | ✓ | ✓ |
| Claude public share (browser-assisted when challenged) | ✓ | ✓ | ✓ | ✓ |

The native formats are undocumented and change over time. The generated files match the currently tested Claude Code message/tool structure and Codex CLI 0.142.5 rollout structure, but provider-specific state such as sandboxes, approvals, file snapshots, encrypted reasoning, token accounting, and compaction cannot always be recreated.

## Install

Python 3.10 or later is required. Runtime dependencies are deliberately limited to the standard library.

```bash
python -m pip install .
panagent --help
```

Plain ChatGPT shares need no extra dependency. For automatic fallback to a real browser when Claude presents a challenge:

```bash
python -m pip install 'panagent[browser]'
playwright install chromium
```

For development without installing:

```bash
PYTHONPATH=src python -m panagent --help
```

## Convert

Formats are detected from file contents. Output goes to stdout unless `-o` is supplied.

```bash
# Native sessions, preserving turn and tool structure
panagent convert claude-session.jsonl --to codex -o codex-session.jsonl
panagent convert codex-session.jsonl --to claude-code -o claude-session.jsonl

# Portable, provider-neutral representation
panagent convert session.jsonl --to ir -o conversation.agent.json

# Public shares
panagent convert 'https://chatgpt.com/share/…' --to ir -o conversation.agent.json
panagent convert 'https://claude.ai/share/…' --to codex --browser headed -o imported.jsonl

# Reuse an already-open Chrome profile/session through its debugging endpoint
panagent convert 'https://claude.ai/share/…' --to codex --cdp-url http://127.0.0.1:9222 -o imported.jsonl

# A readable transcript
panagent convert conversation.agent.json --to markdown -o conversation.md
```

Use `--from` to override detection, `--report report.json` for a machine-readable capability/loss report, and `--fail-on-warning` for strict automation. `panagent validate FILE` parses a source without writing a conversion.

Pass `--session-id UUID` when an integration needs a fresh, explicit destination session ID instead of preserving a UUID-shaped source ID.

### Context and transcript modes

Native-to-native conversion defaults to `--mode transcript`, which synthesizes the original turn sequence and maps tool calls/results.

Web shares default to `--mode context`. This creates one user turn with a clear provenance and trust boundary: imported text is prior discussion, not an instruction that overrides the destination agent’s current rules. It is more robust than fabricating a native history from a web snapshot.

Use transcript mode explicitly when the native turn-by-turn presentation matters:

```bash
panagent convert 'https://chatgpt.com/share/…' --to claude-code --mode transcript -o imported.jsonl
```

Neutral JSON and Markdown are never flattened; `--mode` only changes native targets.

## Provenance and warnings

The neutral format records:

- acquisition format, provider, source kind, URL/path, conversation ID, and time;
- a source ID and record index for each message;
- ordered typed blocks for text, code, visible reasoning summaries, tool calls/results, images, and attachments;
- represented and unavailable capabilities;
- structured warnings with stable codes and optional source paths.

Generated Claude and Codex JSONL embeds the same source/provenance information under a `panagent` metadata field. Re-importing generated output retains an upstream provenance chain. Conversion warnings are printed to stderr, embedded in native session metadata, and optionally written to `--report`.

Expected loss includes provider-only continuation state. For public shares, the converter always notes that hidden instructions, original uploads, alternative branches, and structured tools may not be present in the snapshot. See [the IR reference](docs/ir.md) for the schema.

## Claude browser acquisition

Claude public shares can return a Cloudflare challenge even though the URL is public. A challenge page is never treated as an empty conversation. With the `browser` extra installed, `--browser headed` opens a dedicated Chrome/Chromium window and waits for the user to complete the challenge. `--cdp-url` instead uses an existing user-controlled Chrome, keeping its authentication and challenge cookies inside that browser.

Plain HTTP remains the fast default. `--browser auto` falls back when an interactive desktop is available; non-interactive environments fail with an actionable command rather than hanging. Use `--browser never` to forbid browser startup. If browser automation cannot identify the rendered messages, [the manual JSON/HTML export](docs/browser-export.md) remains available. `panagent` never asks for cookies or access tokens.

## Resuming generated native files

The result is a native session file rather than a command transcript. Native CLIs discover sessions in their own version-specific history directories:

- Codex: place the JSONL below `~/.codex/sessions/YYYY/MM/DD/` using a `rollout-<timestamp>-<session-id>.jsonl` name, then run `codex resume <session-id>`.
- Claude Code: place the JSONL in the matching project directory below `~/.claude/projects/`, then run `claude --resume <session-id>`.

The session ID is `payload.id` in the Codex `session_meta` record and `sessionId` in Claude records. Back up history directories before installing generated files. A destination CLI may migrate its schema on first resume; `panagent` does not modify the history directory itself.

The native smoke suite verifies more than self-parsing: Codex App Server must `thread/read` and `thread/resume` a generated rollout with non-empty turns, and Claude Code must discover a generated session far enough to attempt an API call (using an intentionally invalid key, so the test spends nothing).

## Tests

The suite uses redacted synthetic fixtures modeled on native Claude/Codex files, current ChatGPT React Router share hydration, Claude export/rendered DOM, and an anti-bot challenge.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Opt-in live tests exercise the documented public samples:

```bash
PANAGENT_LIVE_TESTS=1 PYTHONPATH=src python -m unittest tests.test_live_samples -v
```

Run installed-CLI compatibility checks explicitly:

```bash
PANAGENT_NATIVE_TESTS=1 PYTHONPATH=src python -m unittest tests.test_native_cli.CodexNativeCompatibilityTests -v
PANAGENT_CLAUDE_TESTS=1 PANAGENT_CLAUDE_COMMAND=claude \
  PYTHONPATH=src python -m unittest tests.test_native_cli.ClaudeNativeCompatibilityTests -v
```

The plain-HTTP Claude live test accepts an explicit challenge only as an acquisition-boundary result. Browser-backed acquisition is tested separately because completing a challenge is a human action and must not be bypassed by CI.

## Scope

`panagent` converts conversation records. It does not migrate credentials, MCP servers, hooks, plugins, repositories, sandboxes, approvals, or live process state. It also does not bypass access controls or automate account login. Those boundaries are reported rather than hidden.

## License

MIT
