# Product-to-MCP Work Prompt

## Session start

1. Read `critical_prompt.md` and `context.md`.
2. Read the active plan in `plans/`.
3. Read the relevant architecture component document.
4. Inspect the current source and tests before editing.
5. State the changed subsystem, risks, and validation command.

## Before source changes

- Identify the owning folder and interface.
- Keep the smallest coherent change.
- Add tests for user-visible and failure behavior.
- Confirm no secret or customer data enters tracked files.

## Completion

- Run backend tests and frontend typecheck/build where applicable.
- Validate the real local HTTP path when runtime behavior changes.
- Update `context.md`, the active plan, architecture anchors, and test index.
- Create a dated log and checkpoint for meaningful implementation sessions.

