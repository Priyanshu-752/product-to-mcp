# Agent-Useful Toolsets From OpenAPI

Status: implemented 2026-09-14. Legacy group records and the deprecated group
editing API remain for compatibility; the new UI and release path use derived
toolsets. The release preview and generation share one resolver.

Extension: owners may also save named custom toolsets from supported operations.
They are persisted per project and selectable alongside derived toolsets. A
custom toolset is a release filter, not an additional MCP tool. Overlapping
members compile once. Removing or changing a custom toolset never changes an
existing immutable release. After reimport, a custom toolset with unavailable
members requires explicit editing before it can be selected for a new release.

## Goal

Replace editable, UI-only operation groups with automatically derived toolsets
that let a product owner choose which API capabilities an MCP release exposes.
Selecting fewer toolsets must produce fewer API tools in the immutable release
and in MCP `tools/list`. Toolsets are a release configuration, not an MCP tool
and not an executable chain.

Keep optional actions/chains as separate executable tools. A user can still
publish API-only, actions-only, or API-plus-actions releases. No action or
chain is required to publish an API MCP.

## Why this change is needed

Today, `sync_groups` creates or preserves editable `OperationGroup` records.
The Step 3 UI can create, rename, merge, hide, and move those groups. However,
`POST /v1/projects/{id}/releases` compiles all supported operations for
`api_only` and `api_and_actions`, without reading groups. The gateway lists
only manifest tools. Therefore a user's grouping work does not change what an
agent sees. It is organization for the builder only.

The desired behavior is similar to the GitHub MCP server's configurable
toolsets: a selected capability area determines which tools are available.
The final MCP tool list remains flat and standard. Do not add a nonstandard
`groups/list` method or claim that MCP clients understand toolset metadata.

## User journey

1. The user uploads an OpenAPI document. Discovery automatically shows
   toolsets such as `Products`, `Orders`, and `Billing`, with supported API
   tool counts and read/write counts. No group-making task is presented.
2. The user may inspect operations within each toolset. Search, method
   filters, and the ability to create a single action or chain remain.
3. In Release MCP, the user chooses `API tools only`, `API tools + actions`,
   or `Actions only`.
4. When API tools are included, the user selects one or more toolsets. A
   clear preview shows exactly which API tools will be exposed and whether
   write/destructive operations are included. Selecting a toolset selects
   its supported operations; unsupported operations never compile.
5. When actions are included, the user selects approved actions via the
   existing profile. Actions are selected independently of API toolsets:
   deselecting `Orders` API tools does not silently remove an approved
   `place_order` action that internally uses an Orders endpoint.
6. Before generating, the user sees `N API tools + M actions = T MCP tools`
   and a searchable exact-name list. The button is disabled if the result is
   empty. The release is immutable. In Step 4, tests list the same tools.
7. To change the selection, the user creates a new release and MCP URL.

Example: importing a 50-operation API yields `Products (12)`, `Orders (8)`,
`Billing (10)`, and other toolsets. Selecting only Products and Orders plus
two approved actions produces 22 tools, not 52. `tools/list` returns those
22 tools; calls to the omitted tools are rejected.

## Automatic toolset derivation

- Use the operation's first nonempty OpenAPI tag as the toolset key. If no
  tag exists, use the first stable non-parameter path segment. Otherwise use
  `General`. Preserve the human-readable label for display.
- Normalize whitespace/case for matching and create deterministic IDs from
  the normalized source key. Resolve label/slug collisions deterministically;
  IDs must not depend on database insertion order or random tokens.
- Each supported operation belongs to exactly one derived toolset. Multiple
  tags remain searchable metadata, but do not duplicate an operation across
  toolsets or in a release.
- Show unsupported operations separately, with reasons, and exclude them
  from selectable counts.
- Recompute toolsets on each OpenAPI import. A changed tag/path may move an
  operation. Existing releases retain their manifest. A saved draft selection
  must be re-reviewed against the new inventory; never silently substitute a
  different toolset or broaden exposure.
- Do not treat imported tags as permission. Imported tags/descriptions are
  untrusted display data. The owner must review the release selection.

## Release contract and behavior

Extend `ReleaseBody` with `selected_toolset_ids: tuple[str, ...] | None`.
`None` means the current compatibility behavior: all supported API tools.
An explicit empty list means no API tools and is valid only for `actions_only`.
This distinction avoids silently changing older API clients. The frontend
must always send an explicit selection for new releases.

For `api_only` and `api_and_actions`:

- Validate every supplied ID against the current project's derived toolsets.
- Resolve selected IDs to supported operation IDs in stable OpenAPI order,
  deduplicate IDs, and require at least one API operation.
- Compile only those operation IDs. `api_and_actions` additionally compiles
  the profile's approved action IDs. `actions_only` ignores API toolsets and
  should reject a nonempty toolset selection rather than implying it applies.
- Preserve existing action-name collision handling, action validation,
  one-write limits, authorization boundaries, and upstream credential rules.
- Return preview/count data from a server-side endpoint or a shared resolver
  before generation; the backend is authoritative. After generation, compare
  returned manifest names/counts to the preview and surface a mismatch.
- Snapshot the resolved operation IDs and action IDs into the release
  manifest. Optionally store selected toolset IDs/labels as provenance, but
  never resolve them dynamically during `tools/list` or `tools/call`.

Keep API-only as a first-class path with no profile. Keep existing releases,
release URLs, and old request bodies working. Write operations selected via a
toolset must be clearly flagged in the preview; any current write approval or
confirmation policy must still apply. Toolset selection must never bypass it.

## Frontend changes

- Rename the catalog heading from `API tools & groups` to `API tools` or
  `API toolsets`. Show auto-derived toolset sections with counts, search, and
  expand/collapse. Keep the per-operation `Create action` control and chain
  selection.
- Remove `Group selected API tools`, new-group name, rename, merge, move,
  hide/restore, and move-operation controls. These edits currently imply MCP
  impact that does not exist. Do not replace them with another manual folder
  workflow.
- In Release MCP, add toolset checkboxes for modes containing API tools,
  `Select all`, and `Clear` controls. Default to all supported toolsets for
  continuity with the existing `All API tools + actions` behavior, but show
  that this gives no tool-list reduction. The user's selection is explicit
  when they generate a release.
- Put API toolsets and approved actions in separate selection areas. Make
  clear that a toolset is not an extra tool; it controls which API tools are
  included. Show exact names, counts, write warnings, and empty-state errors.
- Keep profile editing for action selection. Remove the "Add all approved
  actions from a group" control unless replaced with a deterministic filter
  over auto-derived action categories; this is not required for the first
  implementation.
- In Step 4, use only the release manifest for the generated tool inventory
  and tests. Never rebuild the test list from current workspace toolsets.

## Existing group and action data

Old editable group data can remain in storage temporarily for backward
compatibility, but the new UI and release compiler must not consume it.
Do not delete tables or user data in the first migration. Mark
`PUT /v1/projects/{id}/groups` deprecated and stop calling it from the new UI;
remove it in a later breaking API version.

Existing actions have nullable `group_id`. Preserve the field when loading
and executing old actions. Do not use it as a release filter. For new actions,
derive a display category from the first referenced operation's toolset, or
leave it uncategorized; an action spanning toolsets still remains one action.
Do not rewrite approved action definitions or old releases to attach new
toolset IDs. Document this compatibility boundary in the API and UI.

## Implementation ownership

1. `openapi`: extract deterministic toolset keys and membership from the
   discovered `Operation` records. Add tests for tags, tagless paths,
   `General`, collisions, unsupported operations, and reimports.
2. `domain`/`storage`: expose derived toolsets in workspace responses. Avoid
   persisting derived membership unless there is a concrete performance need.
3. `api`: validate release selections and return a server-authoritative
   preview/count. Keep request compatibility and return specific 4xx errors
   for unknown IDs, empty selections, and mode conflicts.
4. `compiler`: accept resolved operation IDs as it already does. Ensure
   deterministic order and no duplicates. Keep release manifest hashing and
   immutability.
5. `frontend`: replace manual group controls with selection and preview in
   Release MCP; keep the optional action/chain workflow intact.
6. `gateway`: no new protocol surface is needed. Verify `tools/list` and
   `tools/call` use only the immutable release manifest.

## Test matrix

- OpenAPI import: auto-derived toolsets and counts match operations, including
  missing/multiple tags, duplicate labels, unsupported operations, and
  reimport changes.
- `api_only`: selected toolsets compile only their supported API tools;
  unselected tool names cannot be called.
- `api_and_actions`: selected API tools plus exactly the approved profile
  actions compile. An action may reference an API operation from an
  unselected toolset and still execute through its approved manifest.
- `actions_only`: no raw API tools, irrespective of current toolset inventory.
- Validation: unknown/foreign toolset IDs, explicit empty selection in API
  modes, nonempty selection in actions-only mode, duplicate IDs, empty result,
  write warnings/approval, and stale selections after reimport.
- Compatibility: omitted selection keeps existing API behavior; previously
  created releases remain byte-for-byte equivalent in `tools/list`.
- Frontend: toolset selection changes preview/count and submitted request;
  manual group-making UI is absent; Step 4 test inventory equals manifest.
- Live end-to-end: import a fixture with at least three toolsets, select one,
  create API-only and API-plus-action releases, call an included tool, and
  confirm an excluded tool returns `Tool is not enabled in this release.`

## Acceptance criteria

1. Users never need to create groups to obtain an organized API catalog.
2. Selecting fewer toolsets visibly and measurably reduces `tools/list`.
3. Group/toolset selection never creates a fake catch-all tool, changes the
   behavior of an action, or duplicates operations.
4. All three release modes work, including API-only with no action.
5. Preview, generated counts, Step 4 tests, and direct MCP `tools/list` agree.
6. Existing releases and old API clients continue to work.

## Out of scope

- First-class MCP group/filter protocol extensions; client support is not
  portable enough to make this the product's core behavior.
- Dynamic per-conversation toolset switching. Each release has a fixed set of
  tools; changing it requires a new release.
- Automatically merging a category into one `operation`-selector tool.
- AI-generated tag remapping or auto-approval of imported capabilities.
