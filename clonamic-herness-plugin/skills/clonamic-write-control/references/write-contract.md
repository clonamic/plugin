# Write contract

## Minimal packet

```text
개발명세서 — <target>: <change>; 검증: <check>; 복구: <rollback>
승인:ABC123
```

## Full packet

- `W`: locked user requirement, used only when intent needs a separate gate.
- `D`: exact persistent change.
- `V`: check proving the corresponding acceptance criterion.
- `R`: backup and rollback for external or risky changes.

Reads before the write gate are allowed when they are needed to produce an accurate packet. Do not use that allowance for broad audits, unrelated recommendations, or preloading every skill.

The development specification authorizes a boundary, not an exhaustive command list. It names target roots, operation classes, external effects, checks, and rollback. The implementation may choose and retry the internal commands needed inside that boundary without another approval. A timeout or failure before mutation reuses the same authorization idempotently.

An approved loop ends only when every required item has evidence, the user changes scope, a credential/device action is needed, or the external system is unavailable. An active loop never requests a CMD code, a copied terminal command, or another approval for a same-scope retry. Guards protect only outside-boundary, catastrophic, credential, and platform-owned actions.
