export type Project = {
  project_id: string; name: string; base_url: string; auth_type: string;
};

export type Operation = {
  operation_id: string; tool_name: string; method: string; path: string;
  description: string; input_schema: JsonSchema; output_schema: JsonSchema;
  tags: string[]; default_group: string; operation_fingerprint: string;
  supported: boolean; reason?: string | null;
};

export type JsonSchema = {
  type?: string | string[]; properties?: Record<string, JsonSchema>; required?: string[];
  description?: string; enum?: unknown[]; items?: JsonSchema; additionalProperties?: boolean;
  [key: string]: unknown;
};

export type OperationGroup = {
  group_id: string; project_id: string; name: string; sort_order: number;
  hidden: boolean; operation_ids: string[]; created_at: string; updated_at: string;
};

export type Toolset = {
  toolset_id: string; name: string; operation_ids: string[]; read_count: number; write_count: number;
  custom?: boolean; needs_review?: boolean;
};

export type ValueReference = {
  source: "action_input" | "previous_step" | "constant";
  source_path?: string | null; source_step_id?: string | null; constant_value?: unknown;
};

export type ArgumentBinding = { target_path: string; value: ValueReference };

export type StepCondition = {
  left: ValueReference; operator: string; right?: ValueReference | null;
  on_false: "skip" | "fail"; failure_message: string;
};

export type ActionStep = {
  step_id: string; operation_id: string; argument_bindings: ArgumentBinding[];
  condition?: StepCondition | null;
};

export type ActionDefinition = {
  action_id: string; project_id: string; name: string; title: string; description: string;
  group_id?: string | null; input_schema: JsonSchema; output_schema: JsonSchema;
  steps: ActionStep[]; output_bindings: ArgumentBinding[];
  annotations: Record<string, unknown>; status: "draft" | "valid" | "approved";
  created_at: string; updated_at: string;
};

export type ToolProfile = {
  profile_id: string; project_id: string; name: string; description: string;
  action_ids: string[]; created_at: string; updated_at: string;
};

export type ReleaseMode = "api_and_actions" | "actions_only" | "api_only";

export type Workspace = {
  project: Project; operations: Operation[]; groups: OperationGroup[]; toolsets: Toolset[];
  actions: ActionDefinition[]; profiles: ToolProfile[];
  limits: { max_chain_steps: number; warn_chain_steps: number; warn_profile_tools: number; confirm_profile_tools: number };
};

export type ReleaseTool = {
  kind?: "legacy" | "action"; name: string; title?: string; description: string;
  method?: string; path?: string; input_schema: JsonSchema; output_schema?: JsonSchema;
  annotations?: Record<string, unknown>; steps?: ActionStep[];
};

export type Release = {
  release_id: string; deployment_slug: string; project_id: string; profile_id?: string | null;
  mcp_url?: string; manifest_hash: string; tools: ReleaseTool[]; tool_mode?: ReleaseMode;
  tool_counts?: { api: number; actions: number; total: number };
};

export type SmitheryPublishResponse = {
  mcp_url: string;
  smithery: { deploymentId?: string; status?: string; mcpUrl?: string; warnings?: string[]; [key: string]: unknown };
};

export type SmitheryPublishRequest = {
  namespace: string;
  server_name: string;
  smithery_api_key: string;
  display_name: string;
  description: string;
  homepage: string;
  icon_url: string;
  repository_url?: string;
  license?: string;
  unlisted?: boolean;
};

const apiBaseUrl = (import.meta.env.VITE_PRODUCT_TO_MCP_API_BASE_URL || "").replace(/\/+$/, "");

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body instanceof FormData ? { ...(init?.headers || {}) } : { "Content-Type": "application/json", ...(init?.headers || {}) };
  const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    const raw = await response.text();
    try {
      const parsed = JSON.parse(raw);
      const detail = parsed.detail;
      const message = typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => `${Array.isArray(item.loc) ? item.loc.filter((part: unknown) => part !== "body").join(".") : "Request"}: ${item.msg || "Invalid value"}`).join(" ")
          : detail?.message || raw;
      throw new Error(message);
    } catch (error) {
      if (error instanceof Error && error.message !== raw) throw error;
      throw new Error(raw || `Request failed: ${response.status}`);
    }
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const api = {
  projects: () => call<{ projects: Project[] }>("/v1/projects"),
  createProject: (body: Record<string, unknown>) => call<Project>("/v1/projects", { method: "POST", body: JSON.stringify(body) }),
  uploadOpenapi: async (projectId: string, file: File) => {
    const form = new FormData(); form.append("file", file);
    return call<{ operations: Operation[]; groups: OperationGroup[]; invalidated_action_ids: string[] }>(`/v1/projects/${projectId}/openapi`, { method: "POST", body: form, headers: {} });
  },
  workspace: async (projectId: string) => {
    const value = await call<Workspace>(`/v1/projects/${projectId}/workspace`);
    if (!Array.isArray(value.toolsets)) throw new Error("The backend is out of date. Restart the API server with the current code, then retry Next.");
    return value;
  },
  createCustomToolset: (projectId: string, body: { name: string; operation_ids: string[] }) => call<Toolset>(`/v1/projects/${projectId}/custom-toolsets`, { method: "POST", body: JSON.stringify(body) }),
  updateCustomToolset: (projectId: string, toolsetId: string, body: { name: string; operation_ids: string[] }) => call<Toolset>(`/v1/projects/${projectId}/custom-toolsets/${toolsetId}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteCustomToolset: (projectId: string, toolsetId: string) => call<void>(`/v1/projects/${projectId}/custom-toolsets/${toolsetId}`, { method: "DELETE" }),
  saveGroups: (projectId: string, groups: OperationGroup[]) => call<{ groups: OperationGroup[] }>(`/v1/projects/${projectId}/groups`, { method: "PUT", body: JSON.stringify({ groups }) }),
  createAction: (projectId: string, operation_ids: string[], group_id?: string | null) => call<ActionDefinition>(`/v1/projects/${projectId}/actions`, { method: "POST", body: JSON.stringify({ operation_ids, group_id }) }),
  updateAction: (projectId: string, action: ActionDefinition) => call<ActionDefinition>(`/v1/projects/${projectId}/actions/${action.action_id}`, { method: "PUT", body: JSON.stringify(action) }),
  deleteAction: (projectId: string, actionId: string) => call<void>(`/v1/projects/${projectId}/actions/${actionId}`, { method: "DELETE" }),
  validateAction: (projectId: string, actionId: string) => call<{ valid: boolean; errors: Array<{ path: string; code: string; message: string }>; action: ActionDefinition }>(`/v1/projects/${projectId}/actions/${actionId}/validate`, { method: "POST" }),
  approveAction: (projectId: string, actionId: string) => call<ActionDefinition>(`/v1/projects/${projectId}/actions/${actionId}/approve`, { method: "POST" }),
  testAction: (projectId: string, actionId: string, arguments_: Record<string, unknown>) => call<Record<string, unknown>>(`/v1/projects/${projectId}/actions/${actionId}/test`, { method: "POST", body: JSON.stringify({ arguments: arguments_ }) }),
  createProfile: (projectId: string, body: { name: string; description: string; action_ids: string[] }) => call<ToolProfile>(`/v1/projects/${projectId}/profiles`, { method: "POST", body: JSON.stringify(body) }),
  updateProfile: (projectId: string, profile: ToolProfile) => call<ToolProfile>(`/v1/projects/${projectId}/profiles/${profile.profile_id}`, { method: "PUT", body: JSON.stringify(profile) }),
  deleteProfile: (projectId: string, profileId: string) => call<void>(`/v1/projects/${projectId}/profiles/${profileId}`, { method: "DELETE" }),
  previewRelease: (projectId: string, profile_id: string | null, tool_mode: ReleaseMode, selected_toolset_ids: string[], confirm_large_profile = false) => call<{ tool_names: string[]; tool_counts: { api: number; actions: number; total: number } }>(`/v1/projects/${projectId}/releases/preview`, {
    method: "POST",
    body: JSON.stringify({ ...(profile_id ? { profile_id } : {}), tool_mode, selected_toolset_ids: tool_mode === "actions_only" ? [] : selected_toolset_ids, confirm_large_profile }),
  }),
  release: (projectId: string, profile_id: string | null, tool_mode: ReleaseMode = "api_and_actions", confirm_large_profile = false, selected_toolset_ids?: string[]) => call<Release>(`/v1/projects/${projectId}/releases`, {
    method: "POST",
    body: JSON.stringify({ ...(profile_id ? { profile_id } : {}), tool_mode, confirm_large_profile, ...(selected_toolset_ids ? { selected_toolset_ids: tool_mode === "actions_only" ? [] : selected_toolset_ids } : {}) }),
  }),
  test: (releaseId: string, tool_name: string, arguments_: Record<string, unknown>) => call<{ result: unknown }>(`/v1/releases/${releaseId}/test`, { method: "POST", body: JSON.stringify({ tool_name, arguments: arguments_ }) }),
  publish: (releaseId: string, body: SmitheryPublishRequest) => call<SmitheryPublishResponse>(`/v1/releases/${releaseId}/smithery/publish`, { method: "POST", body: JSON.stringify(body) }),
};
