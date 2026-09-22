# Completion manifest

```json
{
  "items": [
    {"id": "W1", "required": true, "complete": true, "evidence": "cargo test: OK"},
    {"id": "A1", "required": true, "complete": false, "evidence": ""}
  ]
}
```

Required items need both `complete: true` and non-empty evidence. Optional items never block completion.
