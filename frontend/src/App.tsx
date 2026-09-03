import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, type Operation, type Project, type Release, type SmitheryPublishResponse } from "./api";

type Tool = Release["tools"][number];
type AuthType = "bearer" | "api_key" | "none";
type StepId = "setup" | "openapi" | "tools" | "release";

type AuthOption = {
  value: AuthType;
  title: string;
  eyebrow: string;
  description: string;
  headerDefault: string;
  credentialLabel: string;
  placeholder: string;
  requiredDetails: string[];
  whereToFind: string;
};

const authOptions: AuthOption[] = [
  {
    value: "bearer",
    title: "Bearer token",
    eyebrow: "Most API products",
    description: "Use this when API docs say Authorization: Bearer <token>.",
    headerDefault: "Authorization",
    credentialLabel: "Bearer token",
    placeholder: "sk_live_... or product access token",
    requiredDetails: ["API base URL", "Bearer token", "OpenAPI file", "Allowed operations"],
    whereToFind: "Usually in the customer's developer dashboard under API keys, access tokens, or personal tokens.",
  },
  {
    value: "api_key",
    title: "API key header",
    eyebrow: "Header-based APIs",
    description: "Use this when docs say x-api-key, api-key, or another custom header.",
    headerDefault: "x-api-key",
    credentialLabel: "API key value",
    placeholder: "Paste the API key value",
    requiredDetails: ["API base URL", "Header name", "API key value", "OpenAPI file"],
    whereToFind: "The header name is in the API docs. The key value is created in the product's developer or integration settings.",
  },
  {
    value: "none",
    title: "No authentication",
    eyebrow: "Demo or public API",
    description: "Use only for local demo APIs or endpoints that are intentionally public.",
    headerDefault: "Authorization",
    credentialLabel: "No credential needed",
    placeholder: "",
    requiredDetails: ["API base URL", "OpenAPI file"],
    whereToFind: "Only choose this when the API can be called without a token. For customer products, this should be rare.",
  },
];

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

function operationTone(method: string): string {
  if (method === "GET" || method === "HEAD") return "read";
  if (method === "POST") return "create";
  if (method === "PUT" || method === "PATCH") return "update";
  if (method === "DELETE") return "delete";
  return "other";
}

function serverSlug(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return slug || "product-mcp";
}

function InfoTip({ id, text }: { id: string; text: string }) {
  return (
    <span className="t-tt-wrap">
      <button className="info-button t-tt-trigger" type="button" aria-describedby={id}>i</button>
      <span className="t-tt" id={id} role="tooltip">{text}</span>
    </span>
  );
}

export function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [release, setRelease] = useState<Release | null>(null);
  const [activeStep, setActiveStep] = useState<StepId>("setup");
  const [message, setMessage] = useState("Ready. Add the product API details to generate an MCP.");
  const [busy, setBusy] = useState(false);
  const [toolArgs, setToolArgs] = useState<Record<string, string>>({});
  const [toolResults, setToolResults] = useState<Record<string, string>>({});
  const [smitheryResult, setSmitheryResult] = useState<SmitheryPublishResponse | null>(null);
  const [activeHelp, setActiveHelp] = useState<AuthType>("bearer");
  const [form, setForm] = useState({
    name: "Demo Store",
    base_url: "http://127.0.0.1:9000",
    auth_type: "bearer" as AuthType,
    api_key_header: "Authorization",
    upstream_api_key: "",
  });
  const [smitheryForm, setSmitheryForm] = useState({
    namespace: "",
    server_name: "demo-store-mcp",
    smithery_api_key: "",
  });

  const tabRefs = useRef<Record<StepId, HTMLButtonElement | null>>({ setup: null, openapi: null, tools: null, release: null });
  const pillRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => { api.projects().then((value) => setProjects(value.projects)).catch((error) => setMessage(error.message)); }, []);

  const currentAuth = useMemo(() => authOptions.find((item) => item.value === form.auth_type) || authOptions[0], [form.auth_type]);
  const completedSteps = [Boolean(project), operations.length > 0, Boolean(release)].filter(Boolean).length;
  const supportedCount = operations.filter((item) => item.supported).length;
  const writeCount = operations.filter((item) => item.supported && !["GET", "HEAD"].includes(item.method)).length;
  const activeHelpOption = authOptions.find((item) => item.value === activeHelp) || currentAuth;
  const localMcpUrl = release ? `${window.location.origin}/mcp/${release.deployment_slug}/mcp` : "";
  const publicMcpUrl = release?.mcp_url || localMcpUrl;
  const hasPublicHttpsUrl = publicMcpUrl.startsWith("https://");
  const hasSmitheryNamespace = smitheryForm.namespace.trim().length > 0;
  const hasSmitheryApiKey = smitheryForm.smithery_api_key.trim().length > 0;
  const qualifiedSmitheryName = `${smitheryForm.namespace || "@namespace"}/${smitheryForm.server_name || "server-name"}`.replace(/\/+/g, "/");
  const hasToolResults = Object.keys(toolResults).length > 0;

  const steps: Array<{ id: StepId; label: string; detail: string; enabled: boolean; complete: boolean }> = [
    { id: "setup", label: "Product details", detail: "Base URL and auth", enabled: true, complete: Boolean(project) },
    { id: "openapi", label: "OpenAPI import", detail: "Upload API schema", enabled: Boolean(project), complete: operations.length > 0 },
    { id: "tools", label: "Tool approval", detail: "Select MCP tools", enabled: operations.length > 0, complete: Boolean(release) },
    { id: "release", label: "MCP testing", detail: "Call generated tools", enabled: Boolean(release), complete: false },
  ];

  useLayoutEffect(() => {
    const pill = pillRef.current;
    const tab = tabRefs.current[activeStep];
    if (!pill || !tab) return;
    const move = (animate: boolean) => {
      const previous = pill.style.transition;
      if (!animate) pill.style.transition = "none";
      pill.style.transform = `translateX(${tab.offsetLeft}px)`;
      pill.style.width = `${tab.offsetWidth}px`;
      if (!animate) {
        void pill.offsetWidth;
        pill.style.transition = previous;
      }
    };
    move(false);
    const onResize = () => move(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [activeStep, project, operations.length, release]);

  useEffect(() => {
    const pill = pillRef.current;
    const tab = tabRefs.current[activeStep];
    if (!pill || !tab) return;
    pill.style.transform = `translateX(${tab.offsetLeft}px)`;
    pill.style.width = `${tab.offsetWidth}px`;
  }, [activeStep]);

  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const updateSmithery = (key: string, value: string) => setSmitheryForm((current) => ({ ...current, [key]: value }));
  const updateAuth = (value: AuthType) => {
    const option = authOptions.find((item) => item.value === value) || authOptions[0];
    setActiveHelp(value);
    setForm((current) => ({ ...current, auth_type: value, api_key_header: option.headerDefault }));
  };

  async function create() {
    setBusy(true); setMessage("Creating project...");
    try {
      const value = await api.createProject(form);
      setProject(value);
      setProjects((items) => [value, ...items]);
      setOperations([]);
      setRelease(null);
      setToolArgs({});
      setToolResults({});
      setSmitheryResult(null);
      setSmitheryForm((current) => ({ ...current, server_name: `${serverSlug(value.name)}-mcp` }));
      setActiveStep("openapi");
      setMessage("Project created. Upload the OpenAPI document next.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create project."); } finally { setBusy(false); }
  }

  async function upload(file: File) {
    if (!project) return; setBusy(true); setMessage("Reading OpenAPI and discovering operations...");
    try {
      const value = await api.uploadOpenapi(project.project_id, file);
      setOperations(value.operations);
      setSelected(value.operations.filter((item) => item.supported).map((item) => item.operation_id));
      setRelease(null);
      setToolResults({});
      setSmitheryResult(null);
      setActiveStep("tools");
      setMessage("Operations discovered. Review the generated tools before releasing.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not read OpenAPI."); } finally { setBusy(false); }
  }

  async function makeRelease() {
    if (!project) return; setBusy(true); setMessage("Saving selected operations and compiling MCP manifest...");
    try {
      await api.select(project.project_id, selected);
      const value = await api.release(project.project_id);
      setRelease(value);
      setToolArgs(Object.fromEntries(value.tools.map((tool) => [tool.name, defaultArguments(tool)])));
      setSmitheryResult(null);
      setActiveStep("release");
      setMessage("MCP release created. Test any generated tool below.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create release."); } finally { setBusy(false); }
  }

  async function testTool(tool: string) {
    if (!release) return; setBusy(true); setMessage(`Calling ${tool}...`);
    try {
      const args = JSON.parse(toolArgs[tool] || "{}");
      const value = await api.test(release.release_id, tool, args);
      const result = JSON.stringify(value.result, null, 2);
      setToolResults((current) => ({ ...current, [tool]: result }));
      setMessage(`${tool} finished.`);
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Tool call failed."); } finally { setBusy(false); }
  }

  function clearToolResult(tool: string) {
    setToolResults((current) => {
      const next = { ...current };
      delete next[tool];
      return next;
    });
    setMessage(`${tool} test result cleared. Ready to test again.`);
  }

  function clearAllToolResults() {
    setToolResults({});
    setMessage("All tool test results cleared. Ready to test again.");
  }

  async function publishToSmithery() {
    if (!release) return;
    setBusy(true);
    setMessage("Submitting the public MCP endpoint to Smithery...");
    try {
      const value = await api.publish(release.release_id, smitheryForm);
      setSmitheryResult(value);
      setSmitheryForm((current) => ({ ...current, smithery_api_key: "" }));
      setMessage("Smithery publish request accepted. Review the deployment status below.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not publish to Smithery."); } finally { setBusy(false); }
  }

  return (
    <main>
      <section className="hero">
        <div>
          <div className="eyebrow">PRODUCT-TO-MCP - DEPLOYMENT PREP</div>
          <h1>Generate a customer-ready MCP from a product API.</h1>
          <p>Move step by step: connect the API, upload OpenAPI, approve tools, then test the generated MCP release.</p>
        </div>
        <aside className="status-card">
          <span className="status-label">Prototype status</span>
          <strong>{completedSteps}/3 setup stages complete</strong>
          <p>{message}</p>
        </aside>
      </section>

      <nav className="flow t-tabs" role="tablist" aria-label="Product-to-MCP setup steps">
        <span className="t-tabs-pill" aria-hidden="true"></span>
        {steps.map((step, index) => (
          <button
            className="t-tab step-tab"
            key={step.id}
            ref={(node) => { tabRefs.current[step.id] = node; }}
            type="button"
            role="tab"
            aria-selected={activeStep === step.id}
            aria-controls={`step-panel-${step.id}`}
            disabled={!step.enabled}
            data-complete={step.complete}
            onClick={() => step.enabled && setActiveStep(step.id)}
          >
            <span>{index + 1}</span>
            <strong>{step.label}</strong>
            <small>{step.detail}</small>
          </button>
        ))}
      </nav>

      <section className="step-shell">
        {activeStep === "setup" && (
          <article className="panel step-panel" id="step-panel-setup" role="tabpanel">
            <div className="section-title">
              <span>1</span>
              <div>
                <h2>Product API setup</h2>
                <p>Start with the product API base URL and the credential the MCP gateway should inject server-side.</p>
              </div>
            </div>

            <div className="form-grid">
              <label>
                <span>Project name</span>
                <input value={form.name} onChange={(event) => update("name", event.target.value)} />
              </label>
              <label>
                <span className="label-row">API base URL <InfoTip id="base-url-help" text="Use the stable API root, for example https://api.customer.com/v1. Do not paste a single endpoint path here." /></span>
                <input value={form.base_url} onChange={(event) => update("base_url", event.target.value)} />
              </label>
            </div>

            <div className="auth-header">
              <div>
                <h3>Authentication</h3>
                <p>Most real product APIs need credentials. Pick how the gateway should authenticate each upstream call.</p>
              </div>
              <InfoTip id="auth-help" text="Credentials are stored server-side in this prototype flow and injected by the backend when tools run." />
            </div>

            <div className="auth-options">
              {authOptions.map((option) => (
                <button
                  className={`auth-option ${form.auth_type === option.value ? "selected" : ""}`}
                  key={option.value}
                  type="button"
                  onClick={() => updateAuth(option.value)}
                  onMouseEnter={() => setActiveHelp(option.value)}
                  aria-pressed={form.auth_type === option.value}
                >
                  <span>{option.eyebrow}</span>
                  <strong>{option.title}</strong>
                  <small>{option.description}</small>
                  <span className="info-pill">i</span>
                </button>
              ))}
            </div>

            <div className="auth-help-panel">
              <div>
                <span className="status-label">Auth details</span>
                <h3>{activeHelpOption.title}</h3>
                <p>{activeHelpOption.whereToFind}</p>
              </div>
              <ul>
                {activeHelpOption.requiredDetails.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>

            {form.auth_type !== "none" && (
              <div className="credential-grid">
                <label>
                  <span>{currentAuth.credentialLabel}</span>
                  <input type="password" value={form.upstream_api_key} onChange={(event) => update("upstream_api_key", event.target.value)} placeholder={currentAuth.placeholder} />
                </label>
                <label>
                  <span className="label-row">Credential header <InfoTip id="header-help" text="Bearer usually uses Authorization. API key products often use x-api-key, api-key, or a vendor-specific header." /></span>
                  <input value={form.api_key_header} onChange={(event) => update("api_key_header", event.target.value)} />
                </label>
              </div>
            )}

            {form.auth_type === "none" && <p className="notice">No-auth mode is best for the local demo API. For customer APIs, use Bearer token or API key header.</p>}

            <div className="step-actions">
              <button className="primary-action" onClick={create} disabled={busy}>Create project and continue</button>
            </div>
          </article>
        )}

        {activeStep === "openapi" && (
          <article className="panel step-panel" id="step-panel-openapi" role="tabpanel">
            <div className="section-title">
              <span>2</span>
              <div>
                <h2>OpenAPI definition</h2>
                <p>Upload the product API contract. The backend reads operations and turns them into MCP tool candidates.</p>
              </div>
            </div>

            {project ? (
              <div className="upload-box">
                <span className="status-label">Connected project</span>
                <strong>{project.name}</strong>
                <small>{project.base_url}</small>
                <input type="file" accept=".json,.yaml,.yml,application/json,text/yaml" onChange={(event) => event.target.files?.[0] && upload(event.target.files[0])} />
                <p className="notice">For demo testing, upload <code>examples/demo-openapi.yaml</code>.</p>
              </div>
            ) : (
              <div className="empty-state">
                <strong>Create a project first</strong>
                <p>The upload step unlocks after the API base URL and authentication choice are saved.</p>
              </div>
            )}

            <div className="step-actions">
              <button className="secondary" type="button" onClick={() => setActiveStep("setup")}>Back</button>
            </div>
          </article>
        )}

        {activeStep === "tools" && (
          <article className="panel step-panel" id="step-panel-tools" role="tabpanel">
            <div className="review-header">
              <div className="section-title compact">
                <span>3</span>
                <div>
                  <h2>Review generated tools</h2>
                  <p>Only selected operations will be included in the generated MCP release.</p>
                </div>
              </div>
              <div className="metrics">
                <span>{supportedCount} supported</span>
                <span>{writeCount} write tools</span>
                <span>{selected.length} selected</span>
              </div>
            </div>

            {operations.length > 0 ? (
              <div className="operation-list">
                {operations.map((operation) => (
                  <label className={`operation ${!operation.supported ? "disabled" : ""}`} key={operation.operation_id}>
                    <input type="checkbox" disabled={!operation.supported} checked={selected.includes(operation.operation_id)} onChange={() => setSelected((items) => items.includes(operation.operation_id) ? items.filter((item) => item !== operation.operation_id) : [...items, operation.operation_id])} />
                    <span className={`method-pill ${operationTone(operation.method)}`}>{operation.method}</span>
                    <span>
                      <strong>{operation.tool_name}</strong>
                      <small>{operation.path} - {operation.description}</small>
                      {!operation.supported && <small className="warning">{operation.reason}</small>}
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <strong>Upload OpenAPI first</strong>
                <p>Tool approval unlocks after operation discovery finishes.</p>
              </div>
            )}

            <div className="step-actions">
              <button className="secondary" type="button" onClick={() => setActiveStep("openapi")}>Back</button>
              <button className="primary-action" onClick={makeRelease} disabled={busy || selected.length === 0}>Generate MCP release</button>
            </div>
          </article>
        )}

        {activeStep === "release" && (
          <article className="panel step-panel release" id="step-panel-release" role="tabpanel">
            <div className="section-title compact">
              <span>4</span>
              <div>
                <h2>MCP release ready</h2>
                <p>Test generated tools here. After deployment, this endpoint is what Smithery and MCP clients will call.</p>
              </div>
            </div>

            {release ? (
              <>
                <div className="deployment-grid">
                  <div className="endpoint-box primary-endpoint">
                    <span>Public MCP URL for Smithery</span>
                    <code>{publicMcpUrl}</code>
                    <small>Backend uses <code>PRODUCT_TO_MCP_PUBLIC_BASE_URL</code> to build this URL. In local testing it may still point to 127.0.0.1.</small>
                  </div>
                  <div className="endpoint-box">
                    <span>Local testing URL</span>
                    <code>{localMcpUrl}</code>
                    <small>Use this while testing through the local frontend/backend proxy.</small>
                  </div>
                  <div className="endpoint-box">
                    <span>Release identity</span>
                    <code>{release.release_id}</code>
                    <small>Manifest {release.manifest_hash.slice(0, 16)}</small>
                  </div>
                </div>

                <div className="smithery-card">
                  <div className="smithery-heading">
                    <div>
                      <span className="status-label">Smithery deployment</span>
                      <h3>Publish this MCP to the customer’s Smithery account</h3>
                      <p>Smithery needs a public HTTPS Streamable HTTP MCP URL, the customer’s Smithery namespace, server name, and a one-time Smithery API key.</p>
                    </div>
                    <InfoTip id="smithery-publish-help" text="After your backend is deployed, set PRODUCT_TO_MCP_PUBLIC_BASE_URL to that backend domain. Smithery cannot publish localhost URLs." />
                  </div>

                  <div className="requirement-panel">
                    <div className="requirement-panel-title">
                      <span>Publish readiness</span>
                    </div>
                    <div className="smithery-checklist" aria-label="Smithery publish requirements">
                      <div className={`requirement-item ${hasPublicHttpsUrl ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasPublicHttpsUrl ? "✓" : "○"}</span>
                        <div>
                          <strong>Public HTTPS URL</strong>
                          <small>{hasPublicHttpsUrl ? "Ready" : "Needs deployed HTTPS backend"}</small>
                        </div>
                      </div>
                      <div className="requirement-item ready">
                        <span className="requirement-icon">✓</span>
                        <div>
                          <strong>Streamable HTTP endpoint</strong>
                          <small>Generated for this release</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasSmitheryNamespace ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasSmitheryNamespace ? "✓" : "○"}</span>
                        <div>
                          <strong>Smithery namespace</strong>
                          <small>{hasSmitheryNamespace ? "Provided" : "Required from customer"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasSmitheryApiKey ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasSmitheryApiKey ? "✓" : "○"}</span>
                        <div>
                          <strong>Smithery API key</strong>
                          <small>{hasSmitheryApiKey ? "Provided" : "Required for publish"}</small>
                        </div>
                      </div>
                    </div>
                  </div>

                  {!hasPublicHttpsUrl && (
                    <p className="notice warning-notice">Deployment is not ready for Smithery yet because the public MCP URL is not HTTPS. After deploying the backend, set <code>PRODUCT_TO_MCP_PUBLIC_BASE_URL=https://your-backend-domain.com</code>.</p>
                  )}

                  <div className="smithery-form">
                    <label>
                      <span className="label-row">Namespace <InfoTip id="namespace-help" text="Use the customer’s Smithery namespace or organization, for example @acme or acme." /></span>
                      <input value={smitheryForm.namespace} onChange={(event) => updateSmithery("namespace", event.target.value)} placeholder="@customer-org or customer-org" />
                    </label>
                    <label>
                      <span className="label-row">Server name <InfoTip id="server-name-help" text="This becomes the server slug under the namespace, for example demo-store-mcp." /></span>
                      <input value={smitheryForm.server_name} onChange={(event) => updateSmithery("server_name", serverSlug(event.target.value))} />
                    </label>
                    <label>
                      <span className="label-row">Smithery API key <InfoTip id="smithery-key-help" text="The customer generates this in Smithery. The prototype sends it once to publish and then clears this field." /></span>
                      <input type="password" value={smitheryForm.smithery_api_key} onChange={(event) => updateSmithery("smithery_api_key", event.target.value)} placeholder="smithery API key" />
                    </label>
                  </div>

                  <div className="publish-row">
                    <p>Qualified Smithery name: <code>{qualifiedSmitheryName}</code></p>
                    <button className="primary-action" type="button" onClick={publishToSmithery} disabled={busy || !hasPublicHttpsUrl || !hasSmitheryNamespace || !smitheryForm.server_name.trim() || !hasSmitheryApiKey}>
                      Publish to Smithery
                    </button>
                  </div>

                  {smitheryResult && (
                    <div className="smithery-result">
                      <span className="status-label">Publish accepted</span>
                      <strong>{String(smitheryResult.smithery.status || "Submitted")}</strong>
                      {smitheryResult.smithery.deploymentId && <small>Deployment ID: <code>{String(smitheryResult.smithery.deploymentId)}</code></small>}
                      {smitheryResult.smithery.mcpUrl && <code>{String(smitheryResult.smithery.mcpUrl)}</code>}
                      {smitheryResult.smithery.warnings?.length ? (
                        <ul>
                          {smitheryResult.smithery.warnings.map((warning) => <li key={warning}>{warning}</li>)}
                        </ul>
                      ) : <small>No Smithery warnings returned.</small>}
                    </div>
                  )}
                </div>

                <div className="test-section-title">
                  <div>
                    <span className="status-label">Tool tests</span>
                    <h3>Test generated MCP tools</h3>
                  </div>
                  <button className="ghost-action" type="button" onClick={clearAllToolResults} disabled={!hasToolResults}>Clear all results</button>
                </div>

                <div className="tool-grid">
                  {release.tools.map((tool) => (
                    <div className="tool-test" key={tool.name}>
                      <div className="tool-test-header">
                        <div>
                          <strong>{tool.name}</strong>
                          <small>{tool.method} {tool.path}</small>
                        </div>
                        <span className={`method-pill ${operationTone(tool.method)}`}>{tool.method}</span>
                      </div>
                      <textarea value={toolArgs[tool.name] || "{}"} onChange={(event) => setToolArgs((current) => ({ ...current, [tool.name]: event.target.value }))} />
                      <div className="tool-action-row">
                        <button className="secondary" onClick={() => testTool(tool.name)} disabled={busy}>Test tool</button>
                        <button className="ghost-action" type="button" onClick={() => clearToolResult(tool.name)} disabled={!toolResults[tool.name]}>Clear result</button>
                      </div>
                      {toolResults[tool.name] && <pre>{toolResults[tool.name]}</pre>}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <strong>Generate a release first</strong>
                <p>MCP testing unlocks after selected tools are compiled into a release.</p>
              </div>
            )}

            <div className="step-actions">
              <button className="secondary" type="button" onClick={() => setActiveStep("tools")}>Back</button>
            </div>
          </article>
        )}
      </section>

      {/* <footer>{projects.length} project{projects.length === 1 ? "" : "s"} in local prototype storage.</footer> */}
    </main>
  );
}
