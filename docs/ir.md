# Provider-neutral conversation IR

The canonical schema identifier is:

```text
https://panagent.dev/schema/conversation/v1
```

The representation is JSON-native and intentionally small. Readers preserve source-specific details in message metadata and provenance; writers consume only portable fields.

```json
{
  "schema": "https://panagent.dev/schema/conversation/v1",
  "id": "conversation-id",
  "title": "Example",
  "created_at": "2026-08-01T12:00:00Z",
  "updated_at": null,
  "source": {
    "format": "chatgpt-share-html",
    "provider": "openai",
    "kind": "public-share-snapshot",
    "uri": "https://chatgpt.com/share/…",
    "conversation_id": "…",
    "acquired_at": "2026-08-01T12:10:00Z"
  },
  "environment": {},
  "messages": [
    {
      "id": "message-id",
      "role": "user",
      "created_at": "2026-08-01T12:00:01Z",
      "content": [{"type": "text", "text": "Hello"}],
      "provenance": {
        "source_format": "chatgpt-share-html",
        "source_message_id": "message-id",
        "source_record_index": 0
      },
      "metadata": {}
    }
  ],
  "capabilities": {
    "source": ["visible_messages"],
    "represented": ["ordered_messages", "text", "timestamps", "provenance"],
    "unavailable": ["continuation_state"]
  },
  "warnings": [
    {
      "code": "share_snapshot_limitations",
      "severity": "info",
      "message": "The public share may omit provider-only state."
    }
  ]
}
```

Roles are `system`, `developer`, `user`, `assistant`, and `tool`. Content block types are:

- `text`: `text`
- `code`: `text`, optional `language`
- `reasoning`: visible `text`, optional `visibility`; opaque/hidden reasoning is never fabricated
- `tool_call`: `id`, `name`, `arguments`
- `tool_result`: `tool_call_id`, `content`, `is_error`
- `image`: source reference and optional alternative text
- `attachment`: name/source reference and metadata

Warnings use stable machine-readable codes. `warning` means a mapping was lossy or needs attention; `info` documents an inherent source limitation. Unknown native records are skipped with a warning rather than copied into a misleading generic message.

The v1 schema models one active ordered branch. If a source exposes alternatives, a reader must select the active branch and add a capability warning. A future schema revision can add branch topology without making provider-native formats canonical.
