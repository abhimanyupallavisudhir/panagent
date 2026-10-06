# panagent

**Take an AI conversation anywhere.** Turn a ChatGPT, Claude or tavya share link, a ChatGPT or Claude data export, or a Claude Code or Codex session into a session that Claude Code or Codex can resume. One command does it:

```console
$ panagent convert https://chatgpt.com/share/6a781aea-… --to claude --install
cd /home/me/project && claude --resume 0b6d1c1e-5f0e-4d43-9a8e-2f8f5e0c7a11
```

panagent converts through a small provider-neutral format. It keeps source provenance and tool-call IDs where the source has them. When something cannot be carried across, panagent reports it instead of pretending the conversion is exact. It has no dependencies beyond the Python standard library.

| From ↓ / to → | Claude Code | Codex | Neutral JSON | Markdown |
| --- | :---: | :---: | :---: | :---: |
| Claude Code session (`~/.claude/projects/…/*.jsonl`) | ✓ | ✓ | ✓ | ✓ |
| Codex session (`~/.codex/sessions/…/rollout-*.jsonl`) | ✓ | ✓ | ✓ | ✓ |
| ChatGPT share link or data export (`conversations.json`) | ✓ | ✓ | ✓ | ✓ |
| Claude share link or data export (`conversations.json`) | ✓ | ✓ | ✓ | ✓ |
| tavya share link (`tavya.io/share/conversations/…`, or any karmax server) | ✓ | ✓ | ✓ | ✓ |

## Install

```bash
pipx install panagent        # or: uv tool install panagent, or: pip install panagent
```

Python 3.10 or later is required. ChatGPT and tavya links need nothing else. Claude share pages sometimes need a real browser (see [Claude share links](#claude-share-links)):

```bash
pipx install 'panagent[browser]' && playwright install chromium
```

## Use

### Continue a conversation in Claude Code or Codex

`--install` writes the converted session into the CLI's own history and prints the command that resumes it:

```bash
panagent convert 'https://claude.ai/share/…' --to claude --install      # resume in Claude Code
panagent convert 'https://tavya.io/share/conversations/…' --to codex --install
panagent convert ~/.claude/projects/-home-me-app/1f0c….jsonl --to codex --install
```

Claude Code keeps sessions per project directory. `--install` uses the current directory; pass `--cwd DIR` to choose another one. Each install creates a new session ID, and an existing session file is never overwritten. `$CLAUDE_CONFIG_DIR` and `$CODEX_HOME` are honored.

### Convert to a file

The source format is detected from the URL or the file's contents. Output goes to stdout unless you pass `-o`.

```bash
panagent convert codex-session.jsonl --to claude-code -o claude-session.jsonl
panagent convert 'https://chatgpt.com/share/…' --to markdown -o chat.md
panagent convert session.jsonl --to ir -o conversation.agent.json        # neutral JSON
```

### Data exports

ChatGPT (*Settings → Data controls → Export*) and Claude (*Settings → Privacy → Export data*) both email you a `conversations.json` with every conversation. List the conversations, then pick one by ID or exact title:

```bash
panagent list conversations.json
panagent convert conversations.json --conversation 'Plot the data' --to claude --install
```

Claude exports keep text extracted from uploaded files, so attachments are carried across as text. ChatGPT exports refer to images that the export does not contain; these become named attachment placeholders.

### From Python

```python
import panagent

conversation = panagent.load("https://tavya.io/share/conversations/…")    # or a path
print(panagent.render(conversation, "markdown").text)
session = panagent.install(conversation, "codex")
print(session.command)                                                    # codex resume …
```

`panagent.parse(text)` reads a string you already have. Each function raises a `panagent.PanagentError` with an actionable message. Library calls never start a browser unless you pass `browser="auto"`, `"headed"` or `"headless"`.

## How web chats arrive

A web chat was never an agent session. It has no tool state, sandbox or hidden instructions to resume. By default (`--mode auto`), Claude Code and Codex therefore receive a share or an export as **one guarded context message**. That message says the imported text is prior discussion and does not override the agent's current instructions. Agent sessions keep their turn-by-turn structure, including tool calls and results.

Pass `--mode transcript` to rebuild a web chat turn by turn, or `--mode context` to flatten an agent session. Markdown and neutral JSON always keep every message.

## Provenance and warnings

The neutral format ([reference](https://github.com/abhimanyupallavisudhir/panagent/blob/master/docs/ir.md)) records:

- where the conversation came from: format, provider, source kind, URL or file name, conversation ID and acquisition time;
- the source ID and record index of every message;
- ordered, typed blocks: text, code, visible reasoning, tool calls and results, images and attachments;
- what the source could represent and what it could not;
- warnings with stable codes.

Generated Claude Code and Codex files embed the same provenance under a `panagent` field, so a session converted twice still remembers its original source. Warnings go to stderr. `--report FILE` writes them as JSON, and `--fail-on-warning` exits with status 3 for strict automation. Use `panagent validate FILE` to check that a file parses without converting it.

## Claude share links

Claude share pages may show a Cloudflare challenge, or an app shell that only renders in a browser. panagent never treats either one as an empty conversation. Plain HTTPS is tried first. With the `browser` extra, `--browser auto` falls back to a Chrome window where you complete the challenge yourself. Two alternatives:

- `--browser headed` opens a browser window straight away;
- `--cdp-url http://127.0.0.1:9222` reuses a Chrome you already have open.

Non-interactive runs fail with the command to run instead of hanging, and `--browser never` forbids the fallback. panagent never asks for cookies or tokens and never automates a challenge. If browser extraction stops recognizing Claude's page, the [manual export recipe](https://github.com/abhimanyupallavisudhir/panagent/blob/master/docs/browser-export.md) still works.

## Limits

The native Claude Code and Codex formats are undocumented and change over time. The test suite checks the output against real CLIs: Codex must read and resume a session written by `--install`, and Claude Code must resume one and send its history to a local stand-in for the API, so the test spends nothing. Provider-only state cannot be recreated: sandboxes, approvals, file snapshots, encrypted reasoning, token accounting and compaction state.

panagent converts conversations only. It does not migrate credentials, MCP servers, hooks, plugins, repositories or running processes, and it does not bypass access controls. Anything it cannot carry over is reported as a warning.

## Development

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The fixtures are redacted, synthetic copies of each source format. The tavya fixture is the output of tavya's own share renderer. Optional suites:

```bash
PANAGENT_LIVE_TESTS=1 PYTHONPATH=src python -m unittest tests.test_live_samples -v         # public sample links
PANAGENT_NATIVE_TESTS=1 PYTHONPATH=src python -m unittest tests.test_native_cli -v         # installed codex
PANAGENT_CLAUDE_TESTS=1 PANAGENT_CLAUDE_COMMAND=claude \
  PYTHONPATH=src python -m unittest tests.test_native_cli.ClaudeNativeCompatibilityTests -v
```

When a sibling `../karmax` checkout has its dependencies installed, the default suite also runs the Codex release that checkout pins. Point `PANAGENT_PINNED_CODEX` at another binary to use that one instead.

To make a release, bump `__version__` in `src/panagent/__init__.py`, add a `CHANGELOG.md` entry and push a `vX.Y.Z` tag. GitHub Actions then tests, builds and publishes the release to PyPI.

## License

MIT
