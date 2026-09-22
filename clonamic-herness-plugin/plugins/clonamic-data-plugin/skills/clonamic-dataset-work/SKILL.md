---
name: clonamic-dataset-work
description: "Build, clean, convert, validate, or publish datasets and finetuning data with proportional storage checks, streaming, JSONL validation, and bounded Hugging Face operations."
---

# Dataset Work

Procedure for dataset pipelines and Hugging Face Hub work. Storage and memory pre-flight is mandatory
for large jobs, but the check must use the current host's native interface.

## 1. Proportional pre-flight

Tiny inputs that fit comfortably in measured memory and have bounded output skip storage forecasting
and checkpoint setup; validate them directly. Apply the following pre-flight only when input size,
expansion, temporary artifacts, or runtime duration creates a material capacity or restart risk.

- Estimate output size before generating (rows × average record size), including temporary and
  checkpoint files.
- Measure free space with a portable runtime such as Python's `shutil.disk_usage(workspace)` or the
  host's equivalent. Require the estimate plus a proportional safety margin; do not impose one fixed
  capacity threshold on every job or operating system.
- Use the current project workspace or a directory explicitly supplied by the user. Use temporary
  storage only for small disposable files, never for a large implicit dataset workspace.
- When capacity is insufficient, stop new writes and report the measured shortfall. Never delete
  snapshots, caches, or unrelated files automatically.

## 2. Hugging Face connection

- Reuse an explicitly configured authenticated interface already available on the host, such as the
  `hf` CLI or a connected Hugging Face tool. Confirm identity through that interface without printing
  or reading secret values.
- Reads: `hf download <repo> --repo-type dataset [--include ...]` or an equivalent connected read
  tool. Writes: `hf upload <repo> <local> --repo-type dataset`. New repo: `hf repo create <name>
  --repo-type dataset --private`.
- If publishing requires authentication and none is available, treat the host credential action as a
  blocker. Never request a token value in chat, arguments, logs, or files.

## 3. Processing discipline

- Stream line-by-line or in chunks when the dataset is large relative to measured memory.
- For long or expensive jobs, checkpoint at a measured interval to a resumable intermediate file.
  Tiny bounded transforms need no checkpoint artifact.
- Delete intermediates as soon as the next stage is verified.
- Ladder applies: stdlib `json`/`csv` first; pandas/pyarrow only when the operation needs it.

## 4. Validation gate (before any upload / handoff)

- Every JSONL line parses; schema keys consistent across a sampled 1% + first/last 100 lines.
- Record counts: in == out (± documented dedup/filter delta — print the numbers).
- Eyeball 5–10 random records for content sanity (encoding, truncation, label correctness).
- UTF-8 encoding confirmed (`file` + a non-ASCII sample check).

## 5. Upload checklist

- Default **private** repo; minimal dataset card (source, size, schema, license).
- After upload: verify with the HF MCP repo-details tool (file count + sizes match local) or the file list printed by `hf upload` itself. Never invent CLI flags — check `hf <cmd> --help` before using an unfamiliar option.

## Failure playbook

Disk full mid-run → stop writes immediately, remove only job-owned verified intermediates, then resume
from the last checkpoint. OOM → reduce chunk size based on measured memory pressure. Upload
interrupted → use the authenticated interface's documented resume behavior or verify remote state
before retrying.
