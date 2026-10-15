# Changelog

## Unreleased

- **Codex: imported messages carry no item ids.** Assistant messages written for Codex had an invented `msg_…` id. Codex sends item ids back to the model, and OpenAI's Responses API now looks up any id it did not issue, refusing the turn with `400 Supplied input item IDs require persisted-item lookup`. Codex reads, resumes and forks the history without them. The pinned-Codex compatibility test now runs a turn against a local stand-in for the API and checks what is sent.

## 0.3.0

- **tavya share links.** `https://tavya.io/share/conversations/…`, and the same path on any self-hosted karmax server, convert like ChatGPT and Claude shares. Message text is kept exactly, including Markdown, code and math.
- **`--install`.** Writes a converted session into Claude Code's or Codex's own history and prints the command that resumes it (`claude --resume …` / `codex resume …`).
- **ChatGPT and Claude data exports.** `conversations.json` from either provider is detected. `--conversation ID|TITLE` picks one conversation, and `panagent list` shows them. ChatGPT exports follow the active branch, leave out hidden system messages and custom-instruction context, and keep code-interpreter output. Claude exports keep thinking, tool calls and results (paired, each result in its own message) and the text extracted from attachments.
- **Library API.** `panagent.load`, `parse`, `render` and `install`. The CLI is now a thin layer over them.
- `--mode auto` decides by the source's kind: web snapshots (shares, exports) become guarded context, and agent sessions become transcripts. This also applies when the source is neutral JSON made from a share.
- A share link that was deleted or unshared reports "share not found" (HTTP 404/410). Browser fallback decisions use the HTTP status rather than matching error text, and only ChatGPT and Claude shares ever fall back to a browser.
- Redirects must stay within the same kind of share. `chat.openai.com/share/…` links are accepted.
- The CLI prints one line per warning code, with a count, instead of one line per record.
- The conversion report's `source_format` is the conversation's own source format (for example `claude-code-jsonl`).
- Packaging: PyPI metadata, `py.typed`, a build check in CI, and a release workflow. Merging a new `__version__` to master publishes it to PyPI through trusted publishing, then tags it and creates a GitHub release.
- Tests: the Claude Code compatibility test no longer inherits the parent shell's Claude configuration or credentials. It now checks that the resumed history is actually sent to the model, using a local stand-in for the API.

## 0.2.0

- Native Claude Code ⇄ Codex conversion with tool pairing, compaction handling and images; ChatGPT and Claude share links with browser-assisted acquisition; neutral JSON and Markdown output.
