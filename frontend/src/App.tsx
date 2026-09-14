import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, type Project, type Release, type ReleaseMode, type SmitheryPublishResponse, type ToolProfile, type Workspace } from "./api";
import { ActionStudio } from "./features/ActionStudio";

type Tool = Release["tools"][number];
type AuthType = "bearer" | "api_key" | "none";
type StepId = "setup" | "openapi" | "tools" | "release";
export type SmitheryPublishForm = {
  namespace: string;
  server_name: string;
  smithery_api_key: string;
  display_name: string;
  description: string;
  homepage: string;
  icon_url: string;
};

export type SmitheryPublishTool = Pick<Tool, "kind" | "name" | "description" | "output_schema" | "annotations">;

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

export function openapiGenerationPrompt(): string {
  return `You are working inside a backend or API project. The project may use any programming language, framework, database, or architecture.

Create one complete OpenAPI 3.1 YAML file named openapi.yaml. This must be a machine-readable API contract, not source code, a Postman collection, an API response, or general documentation. The file will be uploaded to a tool that converts API operations into MCP tools.

Requirements:
- Inspect the entire project and identify the real HTTP routes, controllers/handlers, request validators, response models, authentication middleware, and existing API documentation. Do not assume a particular framework.
- Do not invent endpoints, fields, authentication methods, or response structures. If something cannot be determined from the project, report it after creating the file.
- Include the standard OpenAPI structure: openapi, info, servers, paths, components/schemas, and components/securitySchemes when authentication exists.
- Determine the public API base URL from project configuration or documentation. If it is not available, use the relative server URL / instead of assuming localhost or inventing a domain.
- Document every public endpoint that should become an MCP tool, including its HTTP method and path.
- Give every operation a unique, descriptive operationId plus a clear summary, description, and tags.
- Describe every path, query, and header parameter. Mark required parameters correctly.
- Include requestBody descriptions, required fields, supported content types, and complete schemas.
- Include actual response status codes, content types, and useful response schemas, not only generic object responses.
- Define the API security scheme, but never put API keys, tokens, passwords, cookies, or other credential values in the file.
- Preserve enums, formats, constraints, and safe example values where the code makes them clear.
- Resolve or correctly define all $ref values and make sure the final YAML is valid OpenAPI.

Before finishing, validate openapi.yaml with an OpenAPI validator and correct all structural or reference errors. Write the file at the project root, then briefly report which routes were included and anything that could not be documented confidently.`;
}

export function smitheryPublishReadiness({
  publicMcpUrl,
  smitheryForm,
  releaseTools,
  busy,
}: {
  publicMcpUrl: string;
  smitheryForm: SmitheryPublishForm;
  releaseTools: SmitheryPublishTool[];
  busy: boolean;
}) {
  const hasPublicHttpsUrl = publicMcpUrl.startsWith("https://");
  const hasSmitheryNamespace = smitheryForm.namespace.trim().length > 0;
  const hasSmitheryApiKey = smitheryForm.smithery_api_key.trim().length > 0;
  const hasSmitheryServerName = smitheryForm.server_name.trim().length > 0;
  const hasServerDisplayName = smitheryForm.display_name.trim().length > 0;
  const hasServerDescription = smitheryForm.description.trim().length > 0;
  const hasServerHomepage = smitheryForm.homepage.trim().length > 0;
  const hasServerIcon = smitheryForm.icon_url.trim().length > 0;
  const hasServerMetadata = hasServerDisplayName && hasServerDescription && hasServerHomepage && hasServerIcon;
  const hasReleaseTools = releaseTools.length > 0;
  const hasActionTools = releaseTools.some((tool) => tool.kind === "action");
  const hasApiTools = releaseTools.some((tool) => tool.kind !== "action");
  const hasToolDescriptions = releaseTools.length > 0 && releaseTools.every((tool) => tool.description.trim().length >= 20);
  const hasOutputSchemas = releaseTools.length > 0 && releaseTools.every((tool) => Boolean(tool.output_schema));
  const hasAnnotations = releaseTools.length > 0 && releaseTools.every((tool) => Boolean(tool.annotations && Object.keys(tool.annotations).length));
  const hasGoodNaming = releaseTools.length > 0 && releaseTools.every((tool) => /^[a-z][a-z0-9_]{2,63}$/.test(tool.name));
  const canPublishToSmithery = !busy && hasPublicHttpsUrl && hasSmitheryNamespace && hasSmitheryServerName && hasSmitheryApiKey && hasServerMetadata && hasReleaseTools;
  return {
    hasPublicHttpsUrl,
    hasSmitheryNamespace,
    hasSmitheryApiKey,
    hasSmitheryServerName,
    hasServerMetadata,
    hasReleaseTools,
    hasActionTools,
    hasApiTools,
    hasToolDescriptions,
    hasOutputSchemas,
    hasAnnotations,
    hasGoodNaming,
    canPublishToSmithery,
  };
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
  const [project, setProject] = useState<Project | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedToolsetIds, setSelectedToolsetIds] = useState<string[]>([]);
  const [toolsetsNeedReview, setToolsetsNeedReview] = useState(false);
  const [release, setRelease] = useState<Release | null>(null);
  const [activeStep, setActiveStep] = useState<StepId>("setup");
  const [message, setMessage] = useState("Ready. Add the product API details to generate an MCP.");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [selectedOpenapiFile, setSelectedOpenapiFile] = useState<File | null>(null);
  const [openapiPromptCopied, setOpenapiPromptCopied] = useState(false);
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
    display_name: "Demo Store MCP",
    description: "Focused MCP actions for the Demo Store product API.",
    homepage: "",
    icon_url: "",
    repository_url: "",
    license: "",
    smithery_api_key: "",
  });

  const tabRefs = useRef<Record<StepId, HTMLButtonElement | null>>({ setup: null, openapi: null, tools: null, release: null });
  const pillRef = useRef<HTMLSpanElement | null>(null);

  const currentAuth = useMemo(() => authOptions.find((item) => item.value === form.auth_type) || authOptions[0], [form.auth_type]);
  const operations = workspace?.operations || [];
  const completedSteps = [Boolean(project), operations.length > 0, Boolean(release)].filter(Boolean).length;
  const activeHelpOption = authOptions.find((item) => item.value === activeHelp) || currentAuth;
  const localMcpUrl = release ? `${window.location.origin}/mcp/${release.deployment_slug}/mcp` : "";
  const publicMcpUrl = release?.mcp_url || localMcpUrl;
  const qualifiedSmitheryName = `${smitheryForm.namespace || "@namespace"}/${smitheryForm.server_name || "server-name"}`.replace(/\/+/g, "/");
  const hasToolResults = Object.keys(toolResults).length > 0;
  const busy = busyAction !== null;
  const openapiPrompt = openapiGenerationPrompt();
  const releaseTools = release?.tools || [];
  const {
    hasPublicHttpsUrl,
    hasSmitheryNamespace,
    hasSmitheryApiKey,
    hasServerMetadata,
    hasReleaseTools,
    hasActionTools,
    hasApiTools,
    hasToolDescriptions,
    hasOutputSchemas,
    hasAnnotations,
    hasGoodNaming,
    canPublishToSmithery,
  } = smitheryPublishReadiness({ publicMcpUrl, smitheryForm, releaseTools, busy });

  const steps: Array<{ id: StepId; label: string; detail: string; enabled: boolean; complete: boolean }> = [
    { id: "setup", label: "Product details", detail: "Base URL and auth", enabled: true, complete: Boolean(project) },
    { id: "openapi", label: "OpenAPI import", detail: "Upload API schema", enabled: Boolean(project), complete: operations.length > 0 },
    { id: "tools", label: "Action Studio", detail: "Design agent tools", enabled: operations.length > 0, complete: Boolean(release) },
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
    setBusyAction("create-project"); setMessage("Creating project...");
    try {
      const value = await api.createProject(form);
      setProject(value);
      setWorkspace(null);
      setSelectedToolsetIds([]);
      setToolsetsNeedReview(false);
      setRelease(null);
      setSelectedOpenapiFile(null);
      setToolArgs({});
      setToolResults({});
      setSmitheryResult(null);
      setSmitheryForm((current) => ({
        ...current,
        server_name: `${serverSlug(value.name)}-mcp`,
        display_name: `${value.name} MCP`,
        description: `Focused MCP actions for the ${value.name} product API.`,
      }));
      setActiveStep("openapi");
      setMessage("Project created. Upload the OpenAPI document next.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create project."); } finally { setBusyAction(null); }
  }

  async function upload() {
    if (!project || !selectedOpenapiFile) return;
    setBusyAction("upload-openapi"); setMessage("Reading OpenAPI and discovering operations...");
    try {
      const value = await api.uploadOpenapi(project.project_id, selectedOpenapiFile);
      const nextWorkspace = await api.workspace(project.project_id);
      if (workspace) {
        const available = new Set(nextWorkspace.toolsets.map((item) => item.toolset_id));
        setSelectedToolsetIds((current) => current.filter((id) => available.has(id)));
        setToolsetsNeedReview(true);
      } else {
        setSelectedToolsetIds(nextWorkspace.toolsets.map((item) => item.toolset_id));
        setToolsetsNeedReview(false);
      }
      setWorkspace(nextWorkspace);
      setRelease(null);
      setToolResults({});
      setSmitheryResult(null);
      setActiveStep("tools");
      setMessage(`${value.operations.length} operations discovered. Choose toolsets and optional actions next.`);
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not read OpenAPI."); } finally { setBusyAction(null); }
  }

  async function copyOpenapiPrompt() {
    try {
      await navigator.clipboard.writeText(openapiPrompt);
      setOpenapiPromptCopied(true);
      setMessage("OpenAPI generation prompt copied. Paste it into your coding assistant inside the API project.");
      window.setTimeout(() => setOpenapiPromptCopied(false), 2200);
    } catch {
      setMessage("Could not access the clipboard. Select the prompt text and copy it manually.");
    }
  }

  async function makeRelease(profile: ToolProfile | null, toolMode: ReleaseMode, confirmLarge: boolean, selectedToolsetIds: string[]) {
    if (profile && confirmLarge && !window.confirm(`This profile contains ${profile.action_ids.length} tools. Large tool lists can make agent selection less reliable. Generate it anyway?`)) return;
    if (!project) return; setBusyAction(profile ? `release:${profile.profile_id}` : "release:api-only"); setMessage(profile ? `Compiling the ${profile.name} publishing profile...` : "Compiling an API-only MCP release...");
    try {
      const preview = await api.previewRelease(project.project_id, profile?.profile_id || null, toolMode, selectedToolsetIds, confirmLarge);
      const value = await api.release(project.project_id, profile?.profile_id || null, toolMode, confirmLarge, selectedToolsetIds);
      const expectedApiTools = preview.tool_counts.api;
      const apiTools = value.tools.filter((tool) => tool.kind !== "action").length;
      const actionTools = value.tools.filter((tool) => tool.kind === "action").length;
      if (["api_and_actions", "api_only"].includes(toolMode) && apiTools !== expectedApiTools) {
        throw new Error(`Release verification failed: expected ${expectedApiTools} API tools but received ${apiTools}. Restart the backend and generate a new release.`);
      }
      if (toolMode === "api_and_actions" && profile && actionTools !== profile.action_ids.length) {
        throw new Error(`Release verification failed: expected ${profile.action_ids.length} actions but received ${actionTools}. Check the profile and generate a new release.`);
      }
      if (toolMode === "actions_only" && apiTools > 0) {
        throw new Error("Release verification failed: actions-only release unexpectedly contains API tools.");
      }
      if (value.tools.length !== preview.tool_counts.total || value.tools.some((tool, index) => tool.name !== preview.tool_names[index])) {
        throw new Error("Release verification failed: generated tools differ from the preview. Review the source and generate a new release.");
      }
      setRelease(value);
      setToolArgs(Object.fromEntries(value.tools.map((tool) => [tool.name, defaultArguments(tool)])));
      setSmitheryResult(null);
      setActiveStep("release");
      setMessage(`${profile?.name || "API-only"} MCP release created with ${value.tools.length} tool${value.tools.length === 1 ? "" : "s"}.`);
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not create release."); } finally { setBusyAction(null); }
  }

  async function testTool(tool: string) {
    if (!release) return; setBusyAction(`test-tool:${tool}`); setMessage(`Calling ${tool}...`);
    try {
      const args = JSON.parse(toolArgs[tool] || "{}");
      const value = await api.test(release.release_id, tool, args);
      const result = JSON.stringify(value.result, null, 2);
      setToolResults((current) => ({ ...current, [tool]: result }));
      setMessage(`${tool} finished.`);
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Tool call failed."); } finally { setBusyAction(null); }
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
    setBusyAction("publish-smithery");
    setMessage("Submitting the public MCP endpoint to Smithery...");
    try {
      const value = await api.publish(release.release_id, {
        ...smitheryForm,
        repository_url: smitheryForm.repository_url.trim() || undefined,
        license: smitheryForm.license.trim() || undefined,
        unlisted: false,
      });
      setSmitheryResult(value);
      setSmitheryForm((current) => ({ ...current, smithery_api_key: "" }));
      setMessage("Smithery publish request accepted. Review the deployment status below.");
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not publish to Smithery."); } finally { setBusyAction(null); }
  }

  return (
    <main>
      <section className="hero">
        <div>
          <div className="eyebrow">PRODUCT-TO-MCP - DEPLOYMENT PREP</div>
          <h1>Generate a customer-ready MCP from a product API.</h1>
          <p>Connect the API, organize operations, build deterministic actions, then publish a focused MCP profile.</p>
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
              <button className={`primary-action ${busyAction === "create-project" ? "loading-button" : ""}`} onClick={create} disabled={busy}>
                {busyAction === "create-project" ? "Creating project..." : "Create project and continue"}
              </button>
            </div>
          </article>
        )}

        {activeStep === "openapi" && (
          <article className="panel step-panel" id="step-panel-openapi" role="tabpanel">
            <div className="section-title">
              <span>2</span>
              <div>
                <h2>OpenAPI definition</h2>
                <p>Upload one OpenAPI file that describes the API endpoints you want available as MCP tools.</p>
              </div>
            </div>

            {project ? (
              <div className="openapi-onboarding">
                <div className="upload-box openapi-upload-box">
                  <div className="upload-heading">
                    <div>
                      <span className="status-label">Connected project</span>
                      <strong>{project.name}</strong>
                      <small>{project.base_url}</small>
                    </div>
                    <span className="file-format">OpenAPI 3.x / JSON or YAML</span>
                  </div>
                  <label className="file-picker">
                    <span>Choose your API definition</span>
                    <input
                      type="file"
                      accept=".json,.yaml,.yml,application/json,text/yaml"
                      onChange={(event) => setSelectedOpenapiFile(event.target.files?.[0] || null)}
                    />
                  </label>
                  {selectedOpenapiFile ? (
                    <p className="selected-file"><strong>Ready to import:</strong> {selectedOpenapiFile.name}</p>
                  ) : (
                    <small>Upload the full API contract, not an API response, Postman screenshot, or source-code file.</small>
                  )}
                  <p className="notice">For demo testing, choose <code>examples/demo-openapi.yaml</code>. The file is only imported after you click Next.</p>
                </div>

                <section className="openapi-guide" aria-labelledby="openapi-upload-requirements">
                  <div className="guide-heading">
                    <div>
                      <span className="status-label">What to upload</span>
                      <h3 id="openapi-upload-requirements">Your API's OpenAPI or Swagger definition</h3>
                    </div>
                    <small>Do not include API keys, tokens, passwords, or cookies.</small>
                  </div>
                  <div className="openapi-requirements">
                    <div><strong>Format</strong><span><code>.yaml</code>, <code>.yml</code>, or <code>.json</code></span></div>
                    <div><strong>Version</strong><span>OpenAPI 3.0 or 3.1</span></div>
                    <div><strong>Contents</strong><span>Paths, methods, parameters, bodies, and responses</span></div>
                  </div>
                </section>

                <details className="openapi-help" open>
                  <summary>Where can I find this file?</summary>
                  <p>Try these common documentation URLs while your API is running. Projects can configure a different path.</p>
                  <div className="openapi-source-list">
                    <div><strong>FastAPI</strong><code>/openapi.json</code></div>
                    <div><strong>Spring Boot + springdoc</strong><code>/v3/api-docs</code></div>
                    <div><strong>.NET + Swashbuckle</strong><code>/swagger/v1/swagger.json</code></div>
                    <div><strong>NestJS / Express Swagger</strong><span>Check the configured docs JSON URL, often <code>/api-json</code> or <code>/swagger.json</code>.</span></div>
                    <div><strong>Hosted API docs</strong><span>Look for Download OpenAPI, Export Swagger, or API definition.</span></div>
                  </div>
                </details>

                <details className="openapi-help prompt-help">
                  <summary>I do not have an OpenAPI file</summary>
                  <p>Open any backend project in a coding assistant and paste this generic prompt. It works across languages and frameworks and asks the assistant to inspect the real code instead of guessing.</p>
                  <textarea className="openapi-prompt" value={openapiPrompt} readOnly aria-label="Prompt for generating an OpenAPI file" />
                  <div className="prompt-actions">
                    <button className="ghost-action" type="button" onClick={() => void copyOpenapiPrompt()}>
                      {openapiPromptCopied ? "Prompt copied" : "Copy generation prompt"}
                    </button>
                    <small>Review the generated file before uploading it. Remove internal-only endpoints and all credential values.</small>
                  </div>
                </details>
              </div>
            ) : (
              <div className="empty-state">
                <strong>Create a project first</strong>
                <p>The upload step unlocks after the API base URL and authentication choice are saved.</p>
              </div>
            )}

            <div className="step-actions">
              <button className="secondary" type="button" onClick={() => setActiveStep("setup")}>Back</button>
              {project && (
                <button
                  className={`primary-action ${busyAction === "upload-openapi" ? "loading-button" : ""}`}
                  type="button"
                  onClick={() => void upload()}
                  disabled={busy || !selectedOpenapiFile}
                >
                  {busyAction === "upload-openapi" ? "Importing OpenAPI..." : "Next: discover operations"}
                </button>
              )}
            </div>
          </article>
        )}

        {activeStep === "tools" && (
          <article className="panel step-panel" id="step-panel-tools" role="tabpanel">
            <div className="review-header">
              <div className="section-title compact">
                <span>3</span>
                <div>
                  <h2>Design agent actions</h2>
                  <p>Choose the API toolsets the agent receives, and optionally add approved actions or chains.</p>
                </div>
              </div>
              {workspace && <div className="metrics"><span>{workspace.toolsets.length} toolsets</span><span>{workspace.actions.length} actions</span><span>{workspace.profiles.length} profiles</span></div>}
            </div>

            {workspace && project ? <ActionStudio projectId={project.project_id} workspace={workspace} selectedToolsetIds={selectedToolsetIds} onSelectedToolsetIds={setSelectedToolsetIds} toolsetsNeedReview={toolsetsNeedReview} onToolsetsReviewed={() => setToolsetsNeedReview(false)} onWorkspace={setWorkspace} onRelease={makeRelease} onMessage={setMessage} /> : (
              <div className="empty-state">
                <strong>Upload OpenAPI first</strong>
                <p>The Action Studio unlocks after operation discovery finishes.</p>
              </div>
            )}

            <div className="step-actions">
              <button className="secondary" type="button" onClick={() => setActiveStep("openapi")}>Back</button>
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

                <div className="release-tool-summary" aria-label="Generated release contents">
                  <strong>Generated contents</strong>
                  <span>{release.tools.filter((tool) => tool.kind !== "action").length} API tools</span>
                  <span>{release.tools.filter((tool) => tool.kind === "action").length} action tools</span>
                  <span>{release.tools.length} total</span>
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

                  <div className="requirement-panel quality-panel">
                    <div className="requirement-panel-title">
                      <span>Publish quality checklist</span>
                    </div>
                    <div className="smithery-checklist quality-checklist" aria-label="Smithery quality checklist">
                      <div className={`requirement-item ${hasReleaseTools ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasReleaseTools ? "✓" : "○"}</span>
                        <div>
                          <strong>Tool selection</strong>
                          <small>{hasReleaseTools ? `${hasApiTools ? "API tools" : ""}${hasApiTools && hasActionTools ? " + " : ""}${hasActionTools ? "actions" : ""} ready` : "Create an MCP release"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasToolDescriptions ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasToolDescriptions ? "✓" : "○"}</span>
                        <div>
                          <strong>Descriptions</strong>
                          <small>{hasToolDescriptions ? "Clear tool descriptions included" : "Actions need clear descriptions"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasOutputSchemas ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasOutputSchemas ? "✓" : "○"}</span>
                        <div>
                          <strong>Output schemas</strong>
                          <small>{hasOutputSchemas ? "Returned in tools/list" : "Release needs action outputs"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasAnnotations ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasAnnotations ? "✓" : "○"}</span>
                        <div>
                          <strong>Annotations</strong>
                          <small>{hasAnnotations ? "Read/write hints included" : "Action annotations missing"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasGoodNaming ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasGoodNaming ? "✓" : "○"}</span>
                        <div>
                          <strong>Naming</strong>
                          <small>{hasGoodNaming ? "Snake case tool names" : "Use simple snake_case names"}</small>
                        </div>
                      </div>
                      <div className={`requirement-item ${hasServerMetadata ? "ready" : "blocked"}`}>
                        <span className="requirement-icon">{hasServerMetadata ? "✓" : "○"}</span>
                        <div>
                          <strong>Server metadata</strong>
                          <small>{hasServerMetadata ? "Description, homepage, and icon ready" : "Add server description, homepage, and icon"}</small>
                        </div>
                      </div>
                      <div className="requirement-item ready">
                        <span className="requirement-icon">✓</span>
                        <div>
                          <strong>Config schema</strong>
                          <small>Empty schema sent with release</small>
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
                    <label>
                      <span className="label-row">Display name <InfoTip id="display-name-help" text="Shown on the Smithery server card." /></span>
                      <input value={smitheryForm.display_name} onChange={(event) => updateSmithery("display_name", event.target.value)} placeholder="Demo Store MCP" />
                    </label>
                    <label className="wide-field">
                      <span className="label-row">Server description <InfoTip id="server-description-help" text="A concise server card description. Make it specific to the customer API and the approved actions." /></span>
                      <textarea value={smitheryForm.description} onChange={(event) => updateSmithery("description", event.target.value)} placeholder="Focused MCP actions for the customer product API." />
                    </label>
                    <label>
                      <span className="label-row">Homepage URL <InfoTip id="homepage-help" text="Public product, docs, or project page for this MCP server." /></span>
                      <input value={smitheryForm.homepage} onChange={(event) => updateSmithery("homepage", event.target.value)} placeholder="https://example.com" />
                    </label>
                    <label>
                      <span className="label-row">Icon URL <InfoTip id="icon-url-help" text="Public HTTPS image URL for the Smithery server icon." /></span>
                      <input value={smitheryForm.icon_url} onChange={(event) => updateSmithery("icon_url", event.target.value)} placeholder="https://example.com/icon.png" />
                    </label>
                    <label>
                      <span className="label-row">Repository URL</span>
                      <input value={smitheryForm.repository_url} onChange={(event) => updateSmithery("repository_url", event.target.value)} placeholder="https://github.com/org/repo" />
                    </label>
                    <label>
                      <span className="label-row">License</span>
                      <input value={smitheryForm.license} onChange={(event) => updateSmithery("license", event.target.value)} placeholder="MIT" />
                    </label>
                  </div>

                  <div className="publish-row">
                    <p>Qualified Smithery name: <code>{qualifiedSmitheryName}</code></p>
                    <button className={`primary-action ${busyAction === "publish-smithery" ? "loading-button" : ""}`} type="button" onClick={publishToSmithery} disabled={!canPublishToSmithery}>
                      {busyAction === "publish-smithery" ? "Publishing..." : "Publish to Smithery"}
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
                          <strong>{tool.title || tool.name}</strong>
                          <small>{tool.kind === "action" ? `${tool.name} · ${tool.steps?.length || 1} API step${tool.steps?.length === 1 ? "" : "s"}` : `${tool.method} ${tool.path}`}</small>
                        </div>
                        <span className={`method-pill ${tool.kind === "action" ? "action" : operationTone(tool.method || "")}`}>{tool.kind === "action" ? "ACTION" : tool.method}</span>
                      </div>
                      <textarea value={toolArgs[tool.name] || "{}"} onChange={(event) => setToolArgs((current) => ({ ...current, [tool.name]: event.target.value }))} />
                      <div className="tool-action-row">
                        <button className={`secondary ${busyAction === `test-tool:${tool.name}` ? "loading-button" : ""}`} onClick={() => testTool(tool.name)} disabled={busy}>
                          {busyAction === `test-tool:${tool.name}` ? "Testing..." : "Test tool"}
                        </button>
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

    </main>
  );
}
