import { describe, expect, it } from "vitest";
import { openapiGenerationPrompt, smitheryPublishReadiness, type SmitheryPublishForm, type SmitheryPublishTool } from "./App";

const form: SmitheryPublishForm = {
  namespace: "@acme",
  server_name: "catalog-mcp",
  smithery_api_key: "smithery-key",
  display_name: "Catalog MCP",
  description: "Focused product catalog actions for support agents.",
  homepage: "https://example.com",
  icon_url: "https://example.com/icon.png",
};

const actionTool: SmitheryPublishTool = {
  kind: "action",
  name: "list_products",
  description: "Run GET /products: list product catalog entries.",
  output_schema: { type: "object", properties: { items: { type: "array", items: { type: "object" } } } },
  annotations: { readOnlyHint: true, destructiveHint: false },
};

describe("smitheryPublishReadiness", () => {
  it("requires all Smithery metadata before publishing", () => {
    const ready = smitheryPublishReadiness({
      publicMcpUrl: "https://mcp.example.com/mcp/release/mcp",
      smitheryForm: form,
      releaseTools: [actionTool],
      busy: false,
    });

    expect(ready.canPublishToSmithery).toBe(true);
    expect(ready.hasServerMetadata).toBe(true);
    expect(ready.hasOutputSchemas).toBe(true);
    expect(ready.hasAnnotations).toBe(true);
    expect(ready.hasGoodNaming).toBe(true);
  });

  it("blocks publish when homepage and icon metadata are missing", () => {
    const blocked = smitheryPublishReadiness({
      publicMcpUrl: "https://mcp.example.com/mcp/release/mcp",
      smitheryForm: { ...form, homepage: "", icon_url: "" },
      releaseTools: [actionTool],
      busy: false,
    });

    expect(blocked.canPublishToSmithery).toBe(false);
    expect(blocked.hasServerMetadata).toBe(false);
  });

  it("allows API-only releases when metadata and schemas are complete", () => {
    const ready = smitheryPublishReadiness({
      publicMcpUrl: "https://mcp.example.com/mcp/release/mcp",
      smitheryForm: form,
      releaseTools: [{ ...actionTool, kind: "legacy" }],
      busy: false,
    });

    expect(ready.canPublishToSmithery).toBe(true);
    expect(ready.hasReleaseTools).toBe(true);
    expect(ready.hasApiTools).toBe(true);
    expect(ready.hasActionTools).toBe(false);
  });
});

describe("openapiGenerationPrompt", () => {
  it("is generic across projects while requiring a complete importable schema", () => {
    const prompt = openapiGenerationPrompt();

    expect(prompt).toContain("any programming language, framework");
    expect(prompt).toContain("machine-readable API contract");
    expect(prompt).toContain("OpenAPI 3.1");
    expect(prompt).toContain("components/securitySchemes");
    expect(prompt).toContain("relative server URL /");
    expect(prompt).toContain("operationId");
    expect(prompt).toContain("requestBody descriptions");
    expect(prompt).toContain("response schemas");
    expect(prompt).toContain("Do not invent endpoints");
    expect(prompt).toContain("never put API keys, tokens, passwords, cookies");
    expect(prompt).toContain("validate openapi.yaml");
    expect(prompt).not.toContain("Demo Store");
    expect(prompt).not.toContain("127.0.0.1");
  });
});
