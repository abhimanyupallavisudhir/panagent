# Claude browser/export fallback

Claude share URLs sometimes return an anti-bot challenge to command-line HTTP clients. Do not save that challenge page and treat it as a transcript. Use a normal browser to complete the challenge, then export only the rendered conversation.

## Option 1: one-conversation JSON export

If a Claude export or browser tool produces JSON, isolate one conversation object with this shape:

```json
{
  "uuid": "conversation-id",
  "name": "Conversation title",
  "source_url": "https://claude.ai/share/…",
  "chat_messages": [
    {"uuid": "message-1", "sender": "human", "created_at": "…", "text": "Question"},
    {"uuid": "message-2", "sender": "assistant", "created_at": "…", "text": "Answer"}
  ]
}
```

Then convert it normally:

```bash
panagent convert claude-export.json --from claude-share --to ir -o conversation.agent.json
```

`content: [{"type": "text", "text": "…"}]` is also accepted. A bulk export containing multiple conversations must be reduced to one object so the output session has an unambiguous identity.

## Option 2: copy rendered messages from the browser

Open the public share in Chrome/Firefox, complete any challenge yourself, and wait for the full conversation to render. In Developer Tools → Console, run:

```javascript
const candidates = document.querySelectorAll(
  '[data-message-author-role], [data-author-role], [data-testid*="user-message"], [data-testid*="human-message"], [data-testid*="assistant-message"]'
);
const chat_messages = [...candidates].map((element, index) => {
  const testid = (element.getAttribute('data-testid') || '').toLowerCase();
  const nativeRole = element.getAttribute('data-message-author-role') ||
    element.getAttribute('data-author-role') ||
    (testid.includes('user') || testid.includes('human') ? 'human' : 'assistant');
  return {
    uuid: element.getAttribute('data-message-id') || `browser-${index}`,
    sender: nativeRole === 'user' ? 'human' : nativeRole,
    text: element.innerText
  };
});
copy(JSON.stringify({
  name: document.title.replace(/^Claude\s*[-–]\s*/, ''),
  source_url: location.href,
  chat_messages
}, null, 2));
```

Paste the clipboard into `claude-export.json`, inspect it for duplicate/nested message containers, and run the command above. Provider DOM attributes can change; if the array is empty, inspect a user and assistant message element and update only the selectors. Never paste cookies, local storage, authorization headers, or access tokens.

## Option 3: rendered HTML

If the rendered message containers have `data-message-author-role`, `data-author-role`, or recognizable `data-testid` attributes, copy the conversation container’s rendered `outerHTML` from the Elements panel into a local HTML file:

```bash
panagent convert claude-rendered.html --from claude-share --to codex -o imported.jsonl
```

DOM extraction preserves visible text only. It emits `dom_fallback` plus the standard share limitations. JSON is preferred because it can retain message IDs and timestamps.
