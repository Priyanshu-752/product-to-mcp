export type Project = {
  project_id: string; name: string; base_url: string; auth_type: string;
};

export type Operation = {
  operation_id: string; tool_name: string; method: string; path: string;
  description: string; input_schema: Record<string, unknown>;
  supported: boolean; reason?: string | null;
};

export type Release = {
  release_id: string; deployment_slug: string; project_id: string;
  manifest_hash: string; tools: Array<{ name: string; description: string; method: string; path: string; input_schema: Record<string, unknown> }>;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body instanceof FormData ? { ...(init?.headers || {}) } : { "Content-Type": "application/json", ...(init?.headers || {}) };
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw new Error(await response.text() || `Request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  projects: () => call<{ projects: Project[] }>("/v1/projects"),
  createProject: (body: Record<string, unknown>) => call<Project>("/v1/projects", { method: "POST", body: JSON.stringify(body) }),
  uploadOpenapi: async (projectId: string, file: File) => {
    const form = new FormData(); form.append("file", file);
    return call<{ operations: Operation[] }>(`/v1/projects/${projectId}/openapi`, { method: "POST", body: form, headers: {} });
  },
  operations: (projectId: string) => call<{ operations: Operation[]; selected: string[] }>(`/v1/projects/${projectId}/operations`),
  select: (projectId: string, operation_ids: string[]) => call<{ selected: string[] }>(`/v1/projects/${projectId}/operations`, { method: "PUT", body: JSON.stringify({ operation_ids }) }),
  release: (projectId: string) => call<Release>(`/v1/projects/${projectId}/releases`, { method: "POST" }),
  test: (releaseId: string, tool_name: string, arguments_: Record<string, unknown>) => call<{ result: unknown }>(`/v1/releases/${releaseId}/test`, { method: "POST", body: JSON.stringify({ tool_name, arguments: arguments_ }) }),
  publish: (releaseId: string, body: Record<string, string>) => call<{ mcp_url: string; smithery: unknown }>(`/v1/releases/${releaseId}/smithery/publish`, { method: "POST", body: JSON.stringify(body) }),
};
