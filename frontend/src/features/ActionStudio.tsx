import { useMemo, useState } from "react";
import {
  api, type ActionDefinition, type ActionStep, type ArgumentBinding,
  type JsonSchema, type ReleaseMode, type ToolProfile, type Workspace,
} from "../api";

type StudioTab = "catalog" | "actions" | "profiles";

type Props = {
  projectId: string;
  workspace: Workspace;
  selectedToolsetIds: string[];
  onSelectedToolsetIds: (ids: string[]) => void;
  toolsetsNeedReview: boolean;
  onToolsetsReviewed: () => void;
  onWorkspace: (workspace: Workspace) => void;
  onRelease: (profile: ToolProfile | null, toolMode: ReleaseMode, confirmLarge: boolean, selectedToolsetIds: string[]) => Promise<void>;
  onMessage: (message: string) => void;
};

const CONDITION_OPERATORS = [
  "equals", "not_equals", "exists", "not_exists", "empty", "not_empty",
  "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal",
];

export function ActionStudio({ projectId, workspace, selectedToolsetIds, onSelectedToolsetIds, toolsetsNeedReview, onToolsetsReviewed, onWorkspace, onRelease, onMessage }: Props) {
  const [tab, setTab] = useState<StudioTab>("catalog");
  const [search, setSearch] = useState("");
  const [method, setMethod] = useState("ALL");
  const [toolsetFilter, setToolsetFilter] = useState("ALL");
  const [catalogFilter, setCatalogFilter] = useState("ALL");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [chainSelection, setChainSelection] = useState<string[]>([]);
  const [customSelection, setCustomSelection] = useState<string[]>([]);
  const [customName, setCustomName] = useState("");
  const [editingCustomId, setEditingCustomId] = useState<string | null>(null);
  const [editing, setEditing] = useState<ActionDefinition | null>(null);
  const [schemaText, setSchemaText] = useState({ input: "", output: "" });
  const [validationErrors, setValidationErrors] = useState<Array<{ path: string; message: string }>>([]);
  const [testArgs, setTestArgs] = useState("{}");
  const [testResult, setTestResult] = useState("");
  const [stepOperationId, setStepOperationId] = useState("");
  const [profileDraft, setProfileDraft] = useState({ name: "", description: "", action_ids: [] as string[] });
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [profileReleaseModes, setProfileReleaseModes] = useState<Record<string, ReleaseMode>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const busy = busyAction !== null;

  const operationsById = useMemo(() => Object.fromEntries(workspace.operations.map((item) => [item.operation_id, item])), [workspace.operations]);
  const actionByOperation = useMemo(() => {
    const result: Record<string, string[]> = {};
    workspace.actions.forEach((action) => action.steps.forEach((step) => {
      result[step.operation_id] = [...(result[step.operation_id] || []), action.name];
    }));
    return result;
  }, [workspace.actions]);
  const selectedApiOperations = workspace.operations.filter((operation) => operation.supported && workspace.toolsets.some((toolset) => selectedToolsetIds.includes(toolset.toolset_id) && toolset.operation_ids.includes(operation.operation_id)));
  const selectedApiToolNames = selectedApiOperations.map((operation) => operation.tool_name);
  const selectedNeedsReview = workspace.toolsets.some((item) => selectedToolsetIds.includes(item.toolset_id) && item.needs_review);

  async function refresh(selectActionId?: string) {
    const value = await api.workspace(projectId);
    onWorkspace(value);
    if (selectActionId) openEditor(value.actions.find((item) => item.action_id === selectActionId) || null);
  }

  function openEditor(action: ActionDefinition | null) {
    setEditing(action ? structuredClone(action) : null);
    setSchemaText(action ? { input: JSON.stringify(action.input_schema, null, 2), output: JSON.stringify(action.output_schema, null, 2) } : { input: "", output: "" });
    setValidationErrors([]);
    setTestResult("");
  }

  async function execute(actionKey: string, message: string, work: () => Promise<void>) {
    setBusyAction(actionKey); onMessage(message);
    try { await work(); }
    catch (error) { onMessage(error instanceof Error ? error.message : "The action could not be completed."); }
    finally { setBusyAction(null); }
  }

  async function createAction(operationIds: string[]) {
    if (!operationIds.length) return;
    const actionKey = operationIds.length === 1 ? `create-action:${operationIds[0]}` : "create-chain";
    await execute(actionKey, operationIds.length === 1 ? "Creating action draft..." : "Creating chained action draft...", async () => {
      const action = await api.createAction(projectId, operationIds);
      await refresh(action.action_id);
      setChainSelection([]); setTab("actions");
      onMessage("Action draft created. Review mappings, then validate and approve it.");
    });
  }

  function editCustomToolset(toolsetId: string) {
    const item = workspace.toolsets.find((toolset) => toolset.toolset_id === toolsetId);
    if (!item?.custom) return;
    setEditingCustomId(item.toolset_id); setCustomName(item.name); setCustomSelection([...item.operation_ids]);
  }

  async function saveCustomToolset() {
    await execute("save-custom-toolset", editingCustomId ? "Updating custom toolset..." : "Creating custom toolset...", async () => {
      const body = { name: customName.trim(), operation_ids: customSelection };
      const saved = editingCustomId
        ? await api.updateCustomToolset(projectId, editingCustomId, body)
        : await api.createCustomToolset(projectId, body);
      await refresh();
      setEditingCustomId(null); setCustomName(""); setCustomSelection([]);
      onMessage(`Custom toolset '${saved.name}' saved. Select it in Release MCP to expose its API tools.`);
    });
  }

  async function removeCustomToolset(toolsetId: string) {
    await execute(`delete-custom:${toolsetId}`, "Deleting custom toolset...", async () => {
      await api.deleteCustomToolset(projectId, toolsetId);
      onSelectedToolsetIds(selectedToolsetIds.filter((id) => id !== toolsetId));
      if (editingCustomId === toolsetId) { setEditingCustomId(null); setCustomName(""); setCustomSelection([]); }
      await refresh(); onMessage("Custom toolset deleted. Existing releases are unchanged.");
    });
  }

  function updateStep(index: number, values: Partial<ActionStep>) {
    if (!editing) return;
    setEditing({ ...editing, steps: editing.steps.map((step, stepIndex) => stepIndex === index ? { ...step, ...values } : step) });
  }

  function updateBinding(stepIndex: number, bindingIndex: number, values: Partial<ArgumentBinding>) {
    if (!editing) return;
    const step = editing.steps[stepIndex];
    updateStep(stepIndex, { argument_bindings: step.argument_bindings.map((binding, index) => index === bindingIndex ? { ...binding, ...values } : binding) });
  }

  function moveStep(index: number, direction: -1 | 1) {
    if (!editing) return;
    const target = index + direction;
    if (target < 0 || target >= editing.steps.length) return;
    const steps = [...editing.steps];
    [steps[index], steps[target]] = [steps[target], steps[index]];
    setEditing({ ...editing, steps });
  }

  function addOperationStep() {
    if (!editing || !stepOperationId) return;
    if (editing.steps.length >= workspace.limits.max_chain_steps) {
      onMessage(`An action can contain at most ${workspace.limits.max_chain_steps} steps.`);
      return;
    }
    const operation = operationsById[stepOperationId];
    if (!operation?.supported) return;
    const existingIds = new Set(editing.steps.map((step) => step.step_id));
    const base = operation.tool_name || operation.operation_id;
    let stepId = base; let suffix = 2;
    while (existingIds.has(stepId)) { stepId = `${base}_${suffix}`; suffix += 1; }
    const properties = operation.input_schema.properties || {};
    const bindings = Object.keys(properties).map((target_path) => ({
      target_path,
      value: { source: "action_input" as const, source_path: target_path, source_step_id: null },
    }));
    let inputSchema = editing.input_schema;
    try { inputSchema = JSON.parse(schemaText.input); } catch { /* Save will report malformed JSON. */ }
    const mergedSchema = {
      ...inputSchema,
      type: "object",
      properties: { ...Object.fromEntries(Object.entries(properties).map(([key, value]) => [key, cleanSchema(value)])), ...(inputSchema.properties || {}) },
      required: [...new Set([...(inputSchema.required || []), ...(operation.input_schema.required || [])])],
      additionalProperties: false,
    };
    setEditing({ ...editing, input_schema: mergedSchema, steps: [...editing.steps, { step_id: stepId, operation_id: operation.operation_id, argument_bindings: bindings, condition: null }] });
    setSchemaText({ ...schemaText, input: JSON.stringify(mergedSchema, null, 2) });
    setStepOperationId("");
    onMessage(`${operation.tool_name} added to the action draft. Review its mappings before validation.`);
  }

  async function saveAction() {
    if (!editing) return;
    await execute("save-action", "Saving action draft...", async () => {
      let inputSchema; let outputSchema;
      try { inputSchema = JSON.parse(schemaText.input); outputSchema = JSON.parse(schemaText.output); }
      catch { throw new Error("Input and output schemas must contain valid JSON."); }
      const saved = await api.updateAction(projectId, { ...editing, input_schema: inputSchema, output_schema: outputSchema });
      await refresh(saved.action_id); onMessage("Action draft saved. Validation is required before approval.");
    });
  }

  async function validateCurrent() {
    if (!editing) return;
    await execute("validate-action", "Validating action structure and mappings...", async () => {
      const value = await api.validateAction(projectId, editing.action_id);
      await refresh(value.action.action_id);
      setValidationErrors(value.errors);
      onMessage(value.valid ? "Action is valid and ready for approval." : `Action has ${value.errors.length} validation issue${value.errors.length === 1 ? "" : "s"}.`);
    });
  }

  async function approveCurrent() {
    if (!editing) return;
    await execute("approve-action", "Approving action...", async () => {
      const action = await api.approveAction(projectId, editing.action_id);
      await refresh(action.action_id); onMessage("Action approved for publishing profiles.");
    });
  }

  async function testCurrent() {
    if (!editing) return;
    await execute("test-action", "Testing action against the connected API...", async () => {
      let args: Record<string, unknown>;
      try { args = JSON.parse(testArgs); } catch { throw new Error("Test arguments must be valid JSON."); }
      const result = await api.testAction(projectId, editing.action_id, args);
      setTestResult(JSON.stringify(result, null, 2)); onMessage("Action test completed.");
    });
  }

  async function removeAction(action: ActionDefinition) {
    await execute(`delete-action:${action.action_id}`, `Deleting ${action.name}...`, async () => {
      await api.deleteAction(projectId, action.action_id); openEditor(null); await refresh(); onMessage("Action deleted.");
    });
  }

  async function createProfile() {
    await execute("save-profile", editingProfileId ? "Updating publishing profile..." : "Creating publishing profile...", async () => {
      const existing = workspace.profiles.find((item) => item.profile_id === editingProfileId);
      const profile = existing
        ? await api.updateProfile(projectId, { ...existing, ...profileDraft })
        : await api.createProfile(projectId, profileDraft);
      setEditingProfileId(null); setProfileDraft({ name: "", description: "", action_ids: [] }); await refresh();
      onMessage(`Publishing profile '${profile.name}' saved.`);
    });
  }

  function editProfile(profile: ToolProfile) {
    setEditingProfileId(profile.profile_id);
    setProfileDraft({ name: profile.name, description: profile.description, action_ids: [...profile.action_ids] });
  }

  async function removeProfile(profile: ToolProfile) {
    await execute(`delete-profile:${profile.profile_id}`, `Deleting ${profile.name}...`, async () => {
      await api.deleteProfile(projectId, profile.profile_id); await refresh(); onMessage("Publishing profile deleted.");
    });
  }

  async function releaseProfile(profile: ToolProfile, toolMode: ReleaseMode, confirmLarge: boolean) {
    const actionKey = `release:${profile.profile_id}`;
    setBusyAction(actionKey);
    try { await onRelease(profile, toolMode, confirmLarge, selectedToolsetIds); }
    finally { setBusyAction(null); }
  }

  async function releaseApiOnly() {
    const actionKey = "release:api-only";
    setBusyAction(actionKey);
    try { await onRelease(null, "api_only", false, selectedToolsetIds); }
    finally { setBusyAction(null); }
  }

  function operationMatches(operation: Workspace["operations"][number]) {
    const query = search.trim().toLowerCase();
    const used = Boolean(actionByOperation[operation.operation_id]?.length);
    const catalogMatches = catalogFilter === "ALL"
      || (catalogFilter === "READ" && ["GET", "HEAD"].includes(operation.method))
      || (catalogFilter === "WRITE" && !["GET", "HEAD"].includes(operation.method))
      || (catalogFilter === "USED" && used)
      || (catalogFilter === "UNUSED" && !used)
      || (catalogFilter === "UNSUPPORTED" && !operation.supported);
    return (method === "ALL" || operation.method === method)
      && catalogMatches
      && (!query || `${operation.tool_name} ${operation.path} ${operation.description}`.toLowerCase().includes(query));
  }

  const filteredToolsets = workspace.toolsets.filter((toolset) => !toolset.custom).map((toolset) => ({
    toolset,
    operations: toolset.operation_ids.map((id) => operationsById[id]).filter(Boolean).filter(operationMatches),
  })).filter(({ toolset, operations }) => toolsetFilter !== "UNSUPPORTED" && (toolsetFilter === "ALL" || toolset.toolset_id === toolsetFilter) && operations.length > 0);
  const unsupportedOperations = workspace.operations.filter((operation) => !operation.supported && operationMatches(operation));

  return <div className="action-studio">
    <div className="studio-tabs" role="tablist" aria-label="Action Studio">
      {(["catalog", "actions", "profiles"] as StudioTab[]).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>
        <span>{item === "catalog" ? "API toolsets" : item === "actions" ? "Optional actions" : "Release MCP"}</span>
        <small>{item === "catalog" ? workspace.operations.length : item === "actions" ? workspace.actions.length : workspace.profiles.length}</small>
      </button>)}
    </div>

    {tab === "catalog" && <section className="studio-section">
      <div className="catalog-toolbar">
        <input aria-label="Search operations" placeholder="Search operation, path, or description" value={search} onChange={(event) => setSearch(event.target.value)} />
        <select aria-label="Filter toolset" value={toolsetFilter} onChange={(event) => setToolsetFilter(event.target.value)}>
          <option value="ALL">All toolsets</option>{workspace.toolsets.filter((item) => !item.custom).map((item) => <option key={item.toolset_id} value={item.toolset_id}>{item.name}</option>)}
          {workspace.operations.some((operation) => !operation.supported) && <option value="UNSUPPORTED">Unsupported</option>}
        </select>
        <select aria-label="Filter method" value={method} onChange={(event) => setMethod(event.target.value)}>
          <option value="ALL">All methods</option>{["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"].map((item) => <option key={item}>{item}</option>)}
        </select>
        <select aria-label="Filter usage and safety" value={catalogFilter} onChange={(event) => setCatalogFilter(event.target.value)}>
          <option value="ALL">All operations</option><option value="READ">Read only</option><option value="WRITE">Writes</option><option value="USED">Used in actions</option><option value="UNUSED">Unused</option><option value="UNSUPPORTED">Unsupported</option>
        </select>
      </div>
      <div className="optional-builders">
        <div>
          <span className="status-label">Optional action</span>
          <strong>Chain selected API tools</strong>
          <small>A chain runs the selected operations in order as one additional MCP tool.</small>
          <button className={`secondary ${busyAction === "create-chain" ? "loading-button" : ""}`} disabled={!chainSelection.length || busy} onClick={() => void createAction(chainSelection)}>{busyAction === "create-chain" ? "Creating chain..." : `Create chain (${chainSelection.length})`}</button>
        </div>
        <div className="custom-toolset-builder">
          <span className="status-label">Custom toolset</span>
          <strong>{editingCustomId ? "Edit custom toolset" : "Create custom toolset"}</strong>
          <small>Choose individual API tools below, then save them as a reusable release selection.</small>
          <input aria-label="Custom toolset name" placeholder="e.g. Support essentials" maxLength={120} value={customName} onChange={(event) => setCustomName(event.target.value)} />
          <div className="custom-toolset-actions"><button className={`secondary ${busyAction === "save-custom-toolset" ? "loading-button" : ""}`} disabled={busy || !customName.trim() || !customSelection.length} onClick={() => void saveCustomToolset()}>{busyAction === "save-custom-toolset" ? "Saving..." : `Save toolset (${customSelection.length})`}</button>{editingCustomId && <button className="ghost-action" disabled={busy} onClick={() => { setEditingCustomId(null); setCustomName(""); setCustomSelection([]); }}>Cancel</button>}</div>
          {workspace.toolsets.filter((item) => item.custom).map((item) => <div className="saved-custom-toolset" key={item.toolset_id}><span>{item.name} ({item.operation_ids.length}){item.needs_review ? " - needs review" : ""}</span><button className="ghost-action" disabled={busy} onClick={() => editCustomToolset(item.toolset_id)}>Edit</button><button className="danger-link" disabled={busy} onClick={() => void removeCustomToolset(item.toolset_id)}>Delete</button></div>)}
        </div>
      </div>
      <p className="studio-guidance">Toolsets from OpenAPI tags or paths are available automatically. Custom toolsets let you choose individual API tools. Actions and chains are optional additional tools.</p>
      <div className="group-stack">
        {filteredToolsets.map(({ toolset, operations }) => <article className="operation-group" key={toolset.toolset_id}>
          <header>
            <button className="collapse-button" onClick={() => setCollapsed((value) => ({ ...value, [toolset.toolset_id]: !value[toolset.toolset_id] }))} aria-label={`Toggle ${toolset.name} toolset`} aria-expanded={!collapsed[toolset.toolset_id]}>{collapsed[toolset.toolset_id] ? "+" : "−"}</button>
            <strong>{toolset.name}</strong>
            <span>{operations.length} operations</span>
          </header>
          {!collapsed[toolset.toolset_id] && <div className="compact-operation-list">{operations.map((operation) => <div className="compact-operation" key={operation.operation_id}>
            <div className="operation-picks">
              <label className="operation-pick"><input type="checkbox" aria-label={`Select ${operation.tool_name} for chaining`} checked={chainSelection.includes(operation.operation_id)} onChange={() => setChainSelection((items) => items.includes(operation.operation_id) ? items.filter((item) => item !== operation.operation_id) : [...items, operation.operation_id])} /><span>Chain</span></label>
              <label className="operation-pick"><input type="checkbox" aria-label={`Add ${operation.tool_name} to custom toolset`} checked={customSelection.includes(operation.operation_id)} onChange={() => setCustomSelection((items) => items.includes(operation.operation_id) ? items.filter((item) => item !== operation.operation_id) : [...items, operation.operation_id])} /><span>Toolset</span></label>
            </div>
            <span className={`method-pill ${operation.method.toLowerCase()}`}>{operation.method}</span>
            <div><strong>{operation.tool_name}</strong><small>{operation.path} · {operation.description}</small>{actionByOperation[operation.operation_id]?.length ? <em>Used by {actionByOperation[operation.operation_id].join(", ")}</em> : null}</div>
            <button className={`secondary compact-button ${busyAction === `create-action:${operation.operation_id}` ? "loading-button" : ""}`} disabled={busy} onClick={() => void createAction([operation.operation_id])}>{busyAction === `create-action:${operation.operation_id}` ? "Creating..." : "Create action"}</button>
          </div>)}</div>}
        </article>)}
      </div>
      {(toolsetFilter === "ALL" || toolsetFilter === "UNSUPPORTED" || catalogFilter === "UNSUPPORTED") && unsupportedOperations.length > 0 && <article className="operation-group unsupported-group"><header><strong>Unsupported operations</strong><span>{unsupportedOperations.length} operations</span></header><div className="compact-operation-list">{unsupportedOperations.map((operation) => <div className="compact-operation unsupported-operation" key={operation.operation_id}><span className={`method-pill ${operation.method.toLowerCase()}`}>{operation.method}</span><div><strong>{operation.tool_name}</strong><small>{operation.path} · {operation.description}</small><em>{operation.reason || "This operation cannot be used in deterministic actions."}</em></div></div>)}</div></article>}
    </section>}

    {tab === "actions" && <section className="studio-section action-layout">
      <aside className="action-list"><div className="list-heading"><strong>Agent actions</strong><small>Drafts must be validated and approved.</small></div>{workspace.actions.map((action) => <button className={editing?.action_id === action.action_id ? "selected" : ""} key={action.action_id} onClick={() => openEditor(action)}><span>{action.title}</span><small>{action.name} · {action.steps.length} step{action.steps.length === 1 ? "" : "s"}</small><em className={`status-badge ${action.status}`}>{action.status}</em></button>)}</aside>
      <div className="action-editor">{editing ? <>
        <div className="editor-heading"><div><span className={`status-badge ${editing.status}`}>{editing.status}</span><h3>{editing.title}</h3><p>Configure exactly what the agent sees and how the approved API workflow runs.</p></div><button className={`danger-link ${busyAction === `delete-action:${editing.action_id}` ? "loading-button" : ""}`} disabled={busy} onClick={() => void removeAction(editing)}>{busyAction === `delete-action:${editing.action_id}` ? "Deleting..." : "Delete"}</button></div>
        <div className="form-grid"><label>Tool name<input value={editing.name} onChange={(event) => setEditing({ ...editing, name: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })} /></label><label>Title<input value={editing.title} onChange={(event) => setEditing({ ...editing, title: event.target.value })} /></label></div>
        <label>Description<textarea className="description-input" value={editing.description} onChange={(event) => setEditing({ ...editing, description: event.target.value })} /></label>
        <div className="schema-grid"><label>Agent input schema<textarea value={schemaText.input} onChange={(event) => setSchemaText({ ...schemaText, input: event.target.value })} /></label><label>Action data schema<textarea value={schemaText.output} onChange={(event) => setSchemaText({ ...schemaText, output: event.target.value })} /></label></div>
        <div className="steps-heading"><div><strong>Execution steps</strong><small>Maximum one write and {workspace.limits.max_chain_steps} total steps.</small></div><div className="step-add-control"><select aria-label="Operation to add to this action" value={stepOperationId} onChange={(event) => setStepOperationId(event.target.value)}><option value="">Add API operation…</option>{workspace.operations.filter((operation) => operation.supported).map((operation) => <option key={operation.operation_id} value={operation.operation_id}>{operation.method} · {operation.tool_name}</option>)}</select><button className="ghost-action" disabled={!stepOperationId || editing.steps.length >= workspace.limits.max_chain_steps} onClick={addOperationStep}>Add step</button></div><span>{editing.steps.filter((step) => !["GET", "HEAD"].includes(operationsById[step.operation_id]?.method)).length} write</span></div>
        <div className="step-stack">{editing.steps.map((step, stepIndex) => { const operation = operationsById[step.operation_id]; const previous = editing.steps.slice(0, stepIndex); return <article className="chain-step" key={`${step.step_id}-${stepIndex}`}>
          <header><span className="step-number">{stepIndex + 1}</span><div><strong>{step.step_id}</strong><small>{operation?.method} {operation?.path}</small></div><div className="group-controls"><button aria-label={`Move ${step.step_id} up`} onClick={() => moveStep(stepIndex, -1)}>↑</button><button aria-label={`Move ${step.step_id} down`} onClick={() => moveStep(stepIndex, 1)}>↓</button>{editing.steps.length > 1 && <button onClick={() => setEditing({ ...editing, steps: editing.steps.filter((_, index) => index !== stepIndex) })}>Remove</button>}</div></header>
          <div className="binding-list">{step.argument_bindings.map((binding, bindingIndex) => { const selectedPrevious = editing.steps.find((item) => item.step_id === binding.value.source_step_id); const sourcePaths = binding.value.source === "action_input" ? schemaPaths(editing.input_schema) : binding.value.source === "previous_step" && selectedPrevious ? schemaPaths(operationsById[selectedPrevious.operation_id]?.output_schema || {}, "data") : []; const suggestionsId = `binding-path-${stepIndex}-${bindingIndex}`; return <div className="binding-row" key={`${binding.target_path}-${bindingIndex}`}><code>{binding.target_path}</code><span>←</span><select value={binding.value.source} onChange={(event) => updateBinding(stepIndex, bindingIndex, { value: { source: event.target.value as ArgumentBinding["value"]["source"], source_path: "", source_step_id: null, constant_value: "" } })}><option value="action_input">Action input</option><option value="previous_step" disabled={!previous.length}>Previous step</option><option value="constant">Constant</option></select>{binding.value.source === "previous_step" && <select value={binding.value.source_step_id || ""} onChange={(event) => updateBinding(stepIndex, bindingIndex, { value: { ...binding.value, source_step_id: event.target.value } })}><option value="">Choose step</option>{previous.map((item) => <option key={item.step_id}>{item.step_id}</option>)}</select>}<input list={binding.value.source === "constant" ? undefined : suggestionsId} value={binding.value.source === "constant" ? String(binding.value.constant_value ?? "") : binding.value.source_path || ""} placeholder={binding.value.source === "constant" ? "Constant value" : "Select or enter field path"} onChange={(event) => updateBinding(stepIndex, bindingIndex, { value: binding.value.source === "constant" ? { ...binding.value, constant_value: parseConstant(event.target.value) } : { ...binding.value, source_path: event.target.value } })} />{sourcePaths.length > 0 && <datalist id={suggestionsId}>{sourcePaths.map((path) => <option key={path} value={path} />)}</datalist>}</div>; })}</div>
          {stepIndex > 0 && <div className="condition-editor"><label><input type="checkbox" checked={Boolean(step.condition)} onChange={(event) => updateStep(stepIndex, { condition: event.target.checked ? { left: { source: "previous_step", source_step_id: previous[previous.length - 1].step_id, source_path: "data" }, operator: "exists", right: null, on_false: "fail", failure_message: "Action condition was not satisfied." } : null })} /> Run condition</label>{step.condition && <><select value={step.condition.left.source_step_id || ""} onChange={(event) => updateStep(stepIndex, { condition: { ...step.condition!, left: { ...step.condition!.left, source_step_id: event.target.value } } })}>{previous.map((item) => <option key={item.step_id}>{item.step_id}</option>)}</select><input value={step.condition.left.source_path || ""} placeholder="data.field" onChange={(event) => updateStep(stepIndex, { condition: { ...step.condition!, left: { ...step.condition!.left, source_path: event.target.value } } })} /><select value={step.condition.operator} onChange={(event) => updateStep(stepIndex, { condition: { ...step.condition!, operator: event.target.value } })}>{CONDITION_OPERATORS.map((item) => <option key={item}>{item}</option>)}</select>{!["exists", "not_exists", "empty", "not_empty"].includes(step.condition.operator) && <input value={String(step.condition.right?.constant_value ?? "")} placeholder="Compare value" onChange={(event) => updateStep(stepIndex, { condition: { ...step.condition!, right: { source: "constant", constant_value: parseConstant(event.target.value) } } })} />}<select value={step.condition.on_false} onChange={(event) => updateStep(stepIndex, { condition: { ...step.condition!, on_false: event.target.value as "skip" | "fail" } })}><option value="fail">Stop if false</option><option value="skip">Skip if false</option></select></>}</div>}
        </article>; })}</div>
        <div className="output-mapping-heading"><div><strong>Normalized output</strong><small>Leave empty to return the final API response, or select exact fields for the agent.</small></div><button className="ghost-action" onClick={() => setEditing({ ...editing, output_bindings: [...editing.output_bindings, { target_path: "result", value: { source: "previous_step", source_step_id: editing.steps[editing.steps.length - 1]?.step_id, source_path: "data" } }] })}>Add output field</button></div>
        {editing.output_bindings.length > 0 && <div className="output-binding-list">{editing.output_bindings.map((binding, index) => <div className="binding-row" key={`output-${index}`}><input value={binding.target_path} placeholder="Output field" onChange={(event) => setEditing({ ...editing, output_bindings: editing.output_bindings.map((item, itemIndex) => itemIndex === index ? { ...item, target_path: event.target.value } : item) })} /><span>←</span><select value={binding.value.source_step_id || ""} onChange={(event) => setEditing({ ...editing, output_bindings: editing.output_bindings.map((item, itemIndex) => itemIndex === index ? { ...item, value: { ...item.value, source: "previous_step", source_step_id: event.target.value } } : item) })}>{editing.steps.map((step) => <option key={step.step_id}>{step.step_id}</option>)}</select><input value={binding.value.source_path || ""} placeholder="data.field" onChange={(event) => setEditing({ ...editing, output_bindings: editing.output_bindings.map((item, itemIndex) => itemIndex === index ? { ...item, value: { ...item.value, source_path: event.target.value } } : item) })} /><button className="danger-link" onClick={() => setEditing({ ...editing, output_bindings: editing.output_bindings.filter((_, itemIndex) => itemIndex !== index) })}>Remove</button></div>)}</div>}
        {validationErrors.length > 0 && <div className="validation-errors"><strong>Fix these validation issues</strong>{validationErrors.map((error, index) => <p key={`${error.path}-${index}`}><code>{error.path}</code> {error.message}</p>)}</div>}
        <div className="editor-actions"><button className={`secondary ${busyAction === "save-action" ? "loading-button" : ""}`} disabled={busy} onClick={() => void saveAction()}>{busyAction === "save-action" ? "Saving..." : "Save draft"}</button><button className={`secondary ${busyAction === "validate-action" ? "loading-button" : ""}`} disabled={busy} onClick={() => void validateCurrent()}>{busyAction === "validate-action" ? "Validating..." : "Validate saved draft"}</button><button className={`primary-action ${busyAction === "approve-action" ? "loading-button" : ""}`} disabled={busy || editing.status !== "valid"} onClick={() => void approveCurrent()}>{busyAction === "approve-action" ? "Approving..." : "Approve action"}</button></div>
        <div className="inline-test"><div><strong>Test action</strong><small>Runs against the connected API and includes a redacted step trace.</small></div><textarea value={testArgs} onChange={(event) => setTestArgs(event.target.value)} /><button className={`secondary ${busyAction === "test-action" ? "loading-button" : ""}`} disabled={busy} onClick={() => void testCurrent()}>{busyAction === "test-action" ? "Running..." : "Run test"}</button>{testResult && <pre>{testResult}</pre>}</div>
      </> : <div className="editor-empty"><strong>Select an action</strong><p>Create an action from the operation catalog or select an existing draft to configure it.</p></div>}</div>
    </section>}

    {tab === "profiles" && <section className="studio-section profile-layout">
      <div className="profile-builder"><span className="status-label">{editingProfileId ? "Edit publishing profile" : "New publishing profile"}</span><h3>Choose the actions this agent should receive</h3><label>Profile name<input value={profileDraft.name} onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })} placeholder="Customer Support" /></label><label>Description<textarea value={profileDraft.description} onChange={(event) => setProfileDraft({ ...profileDraft, description: event.target.value })} placeholder="Focused tools for the customer support agent." /></label><div className="profile-actions">{workspace.actions.map((action) => { const selected = profileDraft.action_ids.includes(action.action_id); return <label className={action.status !== "approved" ? "disabled" : ""} key={action.action_id}><input type="checkbox" disabled={action.status !== "approved" && !selected} checked={selected} onChange={() => setProfileDraft({ ...profileDraft, action_ids: selected ? profileDraft.action_ids.filter((item) => item !== action.action_id) : [...profileDraft.action_ids, action.action_id] })} /><span><strong>{action.title}</strong><small>{action.name} · {action.status}</small></span></label>; })}</div>{profileDraft.action_ids.length > workspace.limits.warn_profile_tools && <p className="notice warning-notice">This profile has {profileDraft.action_ids.length} tools. Focused profiles are easier for agents to use.</p>}<div className="profile-edit-actions">{editingProfileId && <button className="ghost-action" onClick={() => { setEditingProfileId(null); setProfileDraft({ name: "", description: "", action_ids: [] }); }}>Cancel</button>}<button className={`primary-action ${busyAction === "save-profile" ? "loading-button" : ""}`} disabled={busy || !profileDraft.name.trim() || !profileDraft.description.trim() || !profileDraft.action_ids.length} onClick={() => void createProfile()}>{busyAction === "save-profile" ? "Saving profile..." : editingProfileId ? "Save profile" : "Create profile"}</button></div></div>
      <div className="profile-list">
        <div className="list-heading"><strong>Saved profiles</strong><small>Each release gets its own immutable MCP URL.</small></div>
        <div className="toolset-picker" aria-label="API toolsets for release">
          <div className="toolset-picker-header"><div><strong>API toolsets to expose</strong><small>Only selected API tools will appear to the agent. Chains are selected separately.</small></div><div><button type="button" className="ghost-action" onClick={() => { onSelectedToolsetIds(workspace.toolsets.map((item) => item.toolset_id)); onToolsetsReviewed(); }}>Select all</button><button type="button" className="ghost-action" onClick={() => { onSelectedToolsetIds([]); onToolsetsReviewed(); }}>Clear</button></div></div>
          <div className="toolset-options">{workspace.toolsets.map((toolset) => <label key={toolset.toolset_id}><input type="checkbox" checked={selectedToolsetIds.includes(toolset.toolset_id)} onChange={() => { onSelectedToolsetIds(selectedToolsetIds.includes(toolset.toolset_id) ? selectedToolsetIds.filter((id) => id !== toolset.toolset_id) : [...selectedToolsetIds, toolset.toolset_id]); onToolsetsReviewed(); }} /><span><strong>{toolset.name}</strong><small>{toolset.operation_ids.length} API tools{toolset.write_count ? ` · ${toolset.write_count} write` : ""}</small></span></label>)}</div>
          <p className="toolset-selection-summary">{selectedApiOperations.length} API tools selected{selectedToolsetIds.length === workspace.toolsets.length ? " (all toolsets; no reduction)" : ""}{selectedApiOperations.some((item) => !["GET", "HEAD"].includes(item.method)) ? " · Includes write operations" : ""}</p>
          {(toolsetsNeedReview || selectedNeedsReview) && <p className="warning">OpenAPI toolsets changed. Review the selection before generating another release. Edit any custom toolset with missing operations.</p>}
          <details><summary>Exact API tools</summary><div className="profile-tool-names">{selectedApiToolNames.map((name) => <code key={name}>{name}</code>)}</div></details>
        </div>
        <article className="profile-card">
          <span className="status-label">{selectedApiOperations.length} API tools</span>
          <h3>API tools only</h3>
          <p>Generate an MCP with the selected OpenAPI toolsets and no custom actions.</p>
          <div className="profile-card-actions">
            <div><small>Useful when the customer wants the original API surface.</small></div>
            <button className={`primary-action ${busyAction === "release:api-only" ? "loading-button" : ""}`} disabled={busy || !selectedApiOperations.length || toolsetsNeedReview || selectedNeedsReview} onClick={() => void releaseApiOnly()}>{busyAction === "release:api-only" ? "Generating..." : "Generate API-only release"}</button>
          </div>
        </article>
        {workspace.profiles.map((profile) => {
          const unavailable = profile.action_ids.filter((id) => workspace.actions.find((action) => action.action_id === id)?.status !== "approved");
          const releaseMode = profileReleaseModes[profile.profile_id] || "api_and_actions";
          const supportedApiTools = selectedApiOperations.length;
          const releasePreview = releaseMode === "api_and_actions"
            ? `${supportedApiTools} API tools + ${profile.action_ids.length} actions`
            : releaseMode === "actions_only" ? `0 API tools + ${profile.action_ids.length} actions` : `${supportedApiTools} API tools + 0 actions`;
          const releaseButton = releaseMode === "api_and_actions" ? "Generate API + actions release" : releaseMode === "actions_only" ? "Generate actions-only release" : "Generate API-only release";
          return <article className="profile-card" key={profile.profile_id}>
            <span className="status-label">{profile.action_ids.length} actions</span>
            <h3>{profile.name}</h3>
            <p>{profile.description}</p>
            <label className="release-mode-field">
              <span>Release contents</span>
              <select aria-label={`Release contents for ${profile.name}`} value={releaseMode} onChange={(event) => setProfileReleaseModes((current) => ({ ...current, [profile.profile_id]: event.target.value as ReleaseMode }))}>
                <option value="api_and_actions">Selected API toolsets + actions</option>
                <option value="actions_only">Actions only</option>
                <option value="api_only">Selected API toolsets only</option>
              </select>
              <small className="release-mode-summary">Will generate: {releasePreview}</small>
            </label>
            <div className="profile-tool-names">{profile.action_ids.map((id) => <code key={id}>{workspace.actions.find((action) => action.action_id === id)?.name || id}</code>)}</div>
            {profile.action_ids.length > workspace.limits.warn_profile_tools && <p className="warning">Large profile: consider splitting it by agent role.</p>}
            {releaseMode !== "api_only" && unavailable.length > 0 && <p className="warning">Blocked: {unavailable.length} action{unavailable.length === 1 ? " needs" : "s need"} validation and approval again.</p>}
            <div className="profile-card-actions">
              <div><button className="ghost-action" disabled={busy} onClick={() => editProfile(profile)}>Edit</button><button className={`danger-link ${busyAction === `delete-profile:${profile.profile_id}` ? "loading-button" : ""}`} disabled={busy} onClick={() => void removeProfile(profile)}>{busyAction === `delete-profile:${profile.profile_id}` ? "Deleting..." : "Delete"}</button></div>
              <button className={`primary-action ${busyAction === `release:${profile.profile_id}` ? "loading-button" : ""}`} disabled={busy || (releaseMode !== "actions_only" && (!selectedApiOperations.length || toolsetsNeedReview || selectedNeedsReview)) || (releaseMode !== "api_only" && unavailable.length > 0)} onClick={() => void releaseProfile(profile, releaseMode, releaseMode !== "api_only" && profile.action_ids.length > workspace.limits.confirm_profile_tools)}>{busyAction === `release:${profile.profile_id}` ? "Generating..." : releaseButton}</button>
            </div>
          </article>;
        })}
      </div>
    </section>}
  </div>;
}

function parseConstant(value: string): unknown {
  if (value === "true") return true;
  if (value === "false") return false;
  if (value === "null") return null;
  if (value !== "" && !Number.isNaN(Number(value))) return Number(value);
  return value;
}

function cleanSchema(value: JsonSchema): JsonSchema {
  return JSON.parse(JSON.stringify(value, (key, child) => key.startsWith("x-") ? undefined : child)) as JsonSchema;
}

function schemaPaths(schema: JsonSchema, prefix = ""): string[] {
  const properties = schema.properties || {};
  return Object.entries(properties).flatMap(([name, child]) => {
    const path = prefix ? `${prefix}.${name}` : name;
    const nested = child.type === "array" && child.items ? schemaPaths(child.items, `${path}.0`) : schemaPaths(child, path);
    return [path, ...nested];
  });
}
