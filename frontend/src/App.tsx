import { useEffect, useState } from "react";
import { api, Operation, Project, Release } from "./api";

type Tool = Release["tools"][number];

function sampleValue(schema: Record<string, unknown>): unknown {
  const type = schema.type;
  if (type === "integer" || type === "number") return 1;
  if (type === "boolean") return true;
  if (type === "array") return [];
  if (type === "object") {
    const properties = schema.properties && typeof schema.properties === "object" ? schema.properties as Record<string, Record<string, unknown>> : {};
    return Object.fromEntries(Object.entries(properties).map(([key, value]) => [key, sampleValue(value)]));
  }
  return "sample";
}

function defaultArguments(tool: Tool): string {
  const schema = tool.input_schema;
  const properties = schema.properties && typeof schema.properties === "object" ? schema.properties as Record<string, Record<string, unknown>> : {};
  const value: Record<string, unknown> = Object.fromEntries(Object.entries(properties).map(([key, property]) => [key, sampleValue(property)]));
  if ("product_id" in value) value.product_id = "p-1";
  if ("body" in value && typeof value.body === "object" && value.body !== null && !Array.isArray(value.body)) {
    value.body = { id: "p-2", name: "Growth plan", price: 79 };
  }
  return JSON.stringify(value, null, 2);
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [release, setRelease] = useState<Release | null>(null);
  const [message, setMessage] = useState("Ready to create an MCP.");
  const [busy, setBusy] = useState(false);
  const [toolArgs, setToolArgs] = useState<Record<string, string>>({});
  const [form, setForm] = useState({ name: "Demo Store", base_url: "http://127.0.0.1:9000", auth_type: "none", api_key_header: "Authorization", upstream_api_key: "" });

  useEffect(() => { api.projects().then((value) => setProjects(value.projects)).catch((error) => setMessage(error.message)); }, []);
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));

  async function create() {
    setBusy(true); setMessage("Creating project...");
    try { const value = await api.createProject(form); setProject(value); setProjects((items) => [value, ...items]); setMessage("Project created. Upload an OpenAPI document."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create project."); } finally { setBusy(false); }
  }

  async function upload(file: File) {
    if (!project) return; setBusy(true); setMessage("Discovering API operations...");
    try {
      const value = await api.uploadOpenapi(project.project_id, file);
      setOperations(value.operations);
      setSelected(value.operations.filter((item) => item.supported).map((item) => item.operation_id));
      setMessage("Operations discovered. Review the generated CRUD tools.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not read OpenAPI."); } finally { setBusy(false); }
  }

  async function makeRelease() {
    if (!project) return; setBusy(true); setMessage("Saving tool policy and compiling MCP...");
    try {
      await api.select(project.project_id, selected);
      const value = await api.release(project.project_id);
      setRelease(value);
      setToolArgs(Object.fromEntries(value.tools.map((tool) => [tool.name, defaultArguments(tool)])));
      setMessage("MCP release created. Test a tool below.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create release."); } finally { setBusy(false); }
  }

  async function testTool(tool: string) {
    if (!release) return; setBusy(true); setMessage(`Calling ${tool}...`);
    try {
      const args = JSON.parse(toolArgs[tool] || "{}");
      const value = await api.test(release.release_id, tool, args);
      setMessage(JSON.stringify(value.result, null, 2));
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Tool call failed."); } finally { setBusy(false); }
  }

  return <main>
    <header><div className="eyebrow">PRODUCT-TO-MCP - PROTOTYPE</div><h1>Turn an API into an MCP server.</h1><p>Upload an OpenAPI definition, choose generated CRUD tools, test the generated MCP, and publish it to Smithery.</p></header>
    <section className="grid">
      <article><h2>1. Create project</h2><label>Project name<input value={form.name} onChange={(event) => update("name", event.target.value)} /></label><label>API base URL<input value={form.base_url} onChange={(event) => update("base_url", event.target.value)} /></label><label>Authentication<select value={form.auth_type} onChange={(event) => update("auth_type", event.target.value)}><option value="none">None</option><option value="bearer">Bearer token</option><option value="api_key">API key</option></select></label>{form.auth_type !== "none" && <><label>Credential<input type="password" value={form.upstream_api_key} onChange={(event) => update("upstream_api_key", event.target.value)} placeholder="Stored only for this prototype process" /></label><label>Credential header<input value={form.api_key_header} onChange={(event) => update("api_key_header", event.target.value)} /></label></>}<button onClick={create} disabled={busy}>Create project</button></article>
      <article><h2>2. Upload API definition</h2>{project ? <><p className="muted">Connected to <strong>{project.name}</strong>.</p><input type="file" accept=".json,.yaml,.yml,application/json,text/yaml" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} /><p className="status">{message}</p></> : <p className="muted">Create a project first.</p>}</article>
    </section>
    {operations.length > 0 && <section className="panel"><h2>3. Review generated tools</h2><p className="muted">GET, HEAD, POST, PUT, PATCH, and DELETE operations are enabled in this prototype. OPTIONS remains disabled.</p>{operations.map((operation) => <label className={`operation ${!operation.supported ? "disabled" : ""}`} key={operation.operation_id}><input type="checkbox" disabled={!operation.supported} checked={selected.includes(operation.operation_id)} onChange={() => setSelected((items) => items.includes(operation.operation_id) ? items.filter((item) => item !== operation.operation_id) : [...items, operation.operation_id])} /><span><strong>{operation.tool_name}</strong><small>{operation.method} {operation.path} - {operation.description}</small>{!operation.supported && <small className="warning">{operation.reason}</small>}</span></label>)}<button onClick={makeRelease} disabled={busy || selected.length === 0}>Generate MCP release</button></section>}
    {release && <section className="panel release"><h2>4. MCP release ready</h2><p><strong>Endpoint:</strong> <code>{window.location.origin}/mcp/{release.deployment_slug}/mcp</code></p><p><strong>Manifest:</strong> <code>{release.manifest_hash.slice(0, 16)}</code></p>{release.tools.map((tool) => <div className="tool-test" key={tool.name}><strong>{tool.name}</strong><small>{tool.method} {tool.path}</small><textarea value={toolArgs[tool.name] || "{}"} onChange={(event) => setToolArgs((current) => ({ ...current, [tool.name]: event.target.value }))} /><button className="secondary" onClick={() => testTool(tool.name)} disabled={busy}>Test {tool.name}</button></div>)}<pre>{message}</pre><p className="muted">Smithery publishing will be enabled once this backend is deployed behind public HTTPS.</p></section>}
    <footer>{projects.length} project{projects.length === 1 ? "" : "s"} in local prototype storage.</footer>
  </main>;
}
