# panagent

`panagent` converts agent histories and public chat snapshots through a provider-neutral conversation representation. It preserves source provenance, keeps tool call IDs where the source exposes them, and reports what could not be carried across instead of silently pretending conversion is exact.

Supported paths:

| Source | Neutral JSON | Claude Code JSONL | Codex JSONL | Markdown |
| --- | :---: | :---: | :---: | :---: |
| Claude Code JSONL | ✓ | ✓ | ✓ | ✓ |
| Codex JSONL | ✓ | ✓ | ✓ | ✓ |
| ChatGPT public share | ✓ | ✓ | ✓ | ✓ |
| Claude public share/browser export | ✓ | ✓ | ✓ | ✓ |

The native formats are undocumented and change over time. The generated files match the currently tested Claude Code message/tool structure and Codex CLI 0.142.5 rollout structure, but provider-specific state such as sandboxes, approvals, file snapshots, encrypted reasoning, token accounting, and compaction cannot always be recreated.

## Install

Python 3.10 or later is required. Runtime dependencies are deliberately limited to the standard library.

```bash
python -m pip install .
panagent --help
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
panagent convert 'https://claude.ai/share/…' --to codex -o imported.jsonl

# A readable transcript
panagent convert conversation.agent.json --to markdown -o conversation.md
```

Use `--from` to override detection, `--report report.json` for a machine-readable capability/loss report, and `--fail-on-warning` for strict automation. `panagent validate FILE` parses a source without writing a conversion.

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

## Claude anti-bot fallback

Claude public shares can return a Cloudflare challenge even though the URL is public. A challenge page is an acquisition failure—not a successfully parsed empty conversation. `panagent` exits with status 2 and points to [the browser/export fallback](docs/browser-export.md).

The fallback keeps authentication and challenge completion in the user’s normal browser. It accepts either a one-conversation Claude JSON export or rendered message HTML; cookies and access tokens are never given to `panagent`.

## Resuming generated native files

The result is a native session file rather than a command transcript. Native CLIs discover sessions in their own version-specific history directories:

- Codex: place the JSONL below `~/.codex/sessions/YYYY/MM/DD/` using a `rollout-<timestamp>-<session-id>.jsonl` name, then run `codex resume <session-id>`.
- Claude Code: place the JSONL in the matching project directory below `~/.claude/projects/`, then run `claude --resume <session-id>`.

The session ID is `payload.id` in the Codex `session_meta` record and `sessionId` in Claude records. Back up history directories before installing generated files. A destination CLI may migrate its schema on first resume; `panagent` does not modify the history directory itself.

## Tests

The suite uses redacted synthetic fixtures modeled on native Claude/Codex files, current ChatGPT React Router share hydration, Claude export/rendered DOM, and an anti-bot challenge.

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Opt-in live tests exercise the documented public samples:

```bash
PANAGENT_LIVE_TESTS=1 PYTHONPATH=src python -m unittest tests.test_live_samples -v
```

Live tests accept an explicit Claude challenge error as the expected acquisition outcome; they never count the challenge as parser success.

## Scope

`panagent` converts conversation records. It does not migrate credentials, MCP servers, hooks, plugins, repositories, sandboxes, approvals, or live process state. It also does not bypass access controls or automate account login. Those boundaries are reported rather than hidden.

## License

MIT
