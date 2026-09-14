import fs from "node:fs/promises";
import path from "node:path";
import { expect, test, type Browser, type Page } from "@playwright/test";

const frontendUrl = process.env.PRODUCT_TO_MCP_E2E_BASE_URL || "http://127.0.0.1:5175";
const backendUrl = process.env.PRODUCT_TO_MCP_E2E_BACKEND_URL || "http://127.0.0.1:8001";
const demoApiUrl = process.env.PRODUCT_TO_MCP_DEMO_API_URL || "http://127.0.0.1:9001";
const evidenceDir = path.resolve("..", ".runtime", "evidence", "action-workflow");
const demoOpenapi = path.resolve("..", "examples", "demo-openapi.yaml");
const largeOpenapi = path.resolve("..", "examples", "large-openapi-50.yaml");

type RecordedPage = {
  page: Page;
  close: () => Promise<string | null>;
};

async function recordedPage(browser: Browser, slug: string): Promise<RecordedPage> {
  await fs.mkdir(evidenceDir, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 900 },
    recordVideo: { dir: evidenceDir, size: { width: 1366, height: 900 } },
  });
  const page = await context.newPage();
  return {
    page,
    close: async () => {
      const video = page.video();
      await context.close();
      if (!video) return null;
      const target = path.join(evidenceDir, `${slug}.webm`);
      await video.saveAs(target);
      return target;
    },
  };
}

async function writeEvidence(slug: string, evidence: Record<string, unknown>) {
  await fs.mkdir(evidenceDir, { recursive: true });
  await fs.writeFile(path.join(evidenceDir, `${slug}.json`), JSON.stringify(evidence, null, 2), "utf-8");
}

async function createFreshProject(page: Page, name: string, baseUrl: string) {
  await page.goto(frontendUrl);
  await expect(page.getByRole("heading", { name: /Generate a customer-ready MCP/ })).toBeVisible();
  await expect(page.getByText("Continue existing work")).toHaveCount(0);
  await page.getByRole("button", { name: /No authentication/ }).click();
  await page.getByLabel("Project name").fill(name);
  await page.locator("label", { hasText: "API base URL" }).locator("input").fill(baseUrl);
  await page.getByRole("button", { name: "Create project and continue" }).click();
  await expect(page.getByText("Project created. Upload the OpenAPI document next.")).toBeVisible();
}

async function uploadOpenapi(page: Page, filePath: string, expectedCount: number) {
  await page.locator('input[type="file"]').setInputFiles(filePath);
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  await expect(page.getByText(`${expectedCount} operations discovered. Choose toolsets and optional actions next.`)).toBeVisible({ timeout: 20_000 });
}

async function validateAndApproveCurrentAction(page: Page) {
  await page.getByRole("button", { name: "Validate saved draft" }).click();
  await expect(page.getByText("Action is valid and ready for approval.")).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByText("Action approved for publishing profiles.")).toBeVisible({ timeout: 15_000 });
}

async function createProfileAndRelease(page: Page, name: string, description: string, actionName: RegExp | string) {
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await page.getByLabel("Profile name").fill(name);
  await page.getByLabel("Description").fill(description);
  await page.getByRole("checkbox", { name: actionName }).check();
  await page.getByRole("button", { name: "Create profile" }).click();
  await expect(page.getByText(`Publishing profile '${name}' saved.`)).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: "Generate API + actions release" }).click();
  await expect(page.getByRole("heading", { name: "MCP release ready" })).toBeVisible({ timeout: 15_000 });
}

async function testReleaseTool(page: Page, toolName: string, args: Record<string, unknown>, expectedText: string) {
  const card = page.locator(".tool-test").filter({ hasText: toolName }).first();
  await card.scrollIntoViewIfNeeded();
  await card.locator("textarea").fill(JSON.stringify(args, null, 2));
  await card.getByRole("button", { name: "Test tool" }).click();
  await expect(card.locator("pre")).toContainText('"status": "success"', { timeout: 20_000 });
  await expect(card.locator("pre")).toContainText(expectedText);
}

async function mcpPost(page: Page, endpoint: string, body: Record<string, unknown>) {
  return page.evaluate(
    async ({ endpoint, body }) => {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json, text/event-stream",
          "MCP-Protocol-Version": "2025-06-18",
        },
        body: JSON.stringify(body),
      });
      const text = await response.text();
      return { status: response.status, body: JSON.parse(text) };
    },
    { endpoint, body },
  );
}

async function showMcpProof(page: Page, proof: Record<string, unknown>) {
  await page.evaluate((proof) => {
    const panel = document.createElement("section");
    panel.setAttribute("data-testid", "mcp-protocol-proof");
    panel.style.cssText = [
      "position:fixed",
      "inset:24px",
      "z-index:9999",
      "overflow:auto",
      "padding:24px",
      "border:2px solid #3157d5",
      "border-radius:12px",
      "background:#ffffff",
      "color:#172033",
      "font:16px/1.5 Segoe UI, Arial, sans-serif",
      "box-shadow:0 24px 80px rgba(23,32,51,.24)",
    ].join(";");
    panel.innerHTML = `<h2 style="margin:0 0 12px;font-size:26px;">Raw MCP protocol proof</h2><pre style="white-space:pre-wrap;max-height:720px;">${JSON.stringify(proof, null, 2)}</pre>`;
    document.body.appendChild(panel);
  }, proof);
  await expect(page.getByTestId("mcp-protocol-proof")).toContainText("tools/call");
  await page.waitForTimeout(1200);
}

test("fresh workflow selects agent-visible toolsets without manual grouping", async ({ browser }) => {
  const slug = "01-fresh-workflow-toolsets";
  const { page, close } = await recordedPage(browser, slug);
  const evidence: Record<string, unknown> = { case: slug };
  try {
    await createFreshProject(page, `Toolset Proof ${Date.now()}`, "http://127.0.0.1:9001");
    await uploadOpenapi(page, largeOpenapi, 50);
    await expect(page.getByText("2 toolsets")).toBeVisible();

    await page.getByLabel("Search operations").fill("get_item50");
    await expect(page.getByText("get_item50", { exact: true })).toBeVisible();
    await page.getByLabel("Search operations").fill("");

    await expect(page.getByLabel("New group name")).toHaveCount(0);
    await page.getByRole("button", { name: /Release MCP/ }).click();
    await page.getByRole("checkbox", { name: /Inventory/ }).uncheck();
    await expect(page.getByText(/25 API tools selected/)).toBeVisible();
    await page.getByRole("button", { name: "Generate API-only release" }).click();
    await expect(page.getByLabel("Generated release contents")).toContainText("25 API tools", { timeout: 20_000 });
    await expect(page.locator(".tool-test")).toHaveCount(25);
    const endpoint = await page.locator(".primary-endpoint code").first().innerText();
    const listed = await mcpPost(page, endpoint, { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} });
    expect(listed.body.result.tools).toHaveLength(25);
    expect(listed.body.result.tools.some((tool: { name: string }) => tool.name === "get_item26")).toBe(false);

    evidence.assertions = [
      "Continue existing work is not present",
      "Large OpenAPI import discovered 50 operations",
      "OpenAPI automatically produced two toolsets",
      "Manual group editing is absent",
      "Selected toolset reduces the release and raw MCP tool list to 25",
    ];
  } finally {
    evidence.video = await close();
    await writeEvidence(slug, evidence);
  }
});

test("fresh workflow creates, approves, profiles, releases, and tests a single action", async ({ browser }) => {
  const slug = "02-single-action-release-test";
  const { page, close } = await recordedPage(browser, slug);
  const evidence: Record<string, unknown> = { case: slug };
  try {
    await createFreshProject(page, `Single Action Proof ${Date.now()}`, demoApiUrl);
    await uploadOpenapi(page, demoOpenapi, 6);

    await page.getByLabel("Search operations").fill("list_products");
    await page.locator(".compact-operation").filter({ hasText: "list_products" }).getByRole("button", { name: "Create action" }).click();
    await expect(page.getByText("Action draft created. Review mappings, then validate and approve it.")).toBeVisible({ timeout: 15_000 });

    await page.locator(".inline-test textarea").fill(JSON.stringify({ limit: 20 }, null, 2));
    await page.getByRole("button", { name: "Run test" }).click();
    await expect(page.locator(".inline-test pre")).toContainText("Starter plan", { timeout: 20_000 });

    await validateAndApproveCurrentAction(page);
    await createProfileAndRelease(page, "Reader Profile", "A focused read-only product catalog profile.", /List Products Action/);
    await testReleaseTool(page, "list_products_action", { limit: 20 }, "Starter plan");

    evidence.assertions = [
      "Single operation action draft was created",
      "Action-level test called the demo API",
      "Action was validated and approved",
      "Publishing profile generated an immutable MCP release",
      "Release test returned demo API data",
    ];
  } finally {
    evidence.video = await close();
    await writeEvidence(slug, evidence);
  }
});

test("fresh workflow creates a chained action and verifies the raw MCP endpoint", async ({ browser }) => {
  const slug = "03-chain-action-mcp-protocol";
  const { page, close } = await recordedPage(browser, slug);
  const evidence: Record<string, unknown> = { case: slug };
  try {
    await createFreshProject(page, `Chain MCP Proof ${Date.now()}`, demoApiUrl);
    await uploadOpenapi(page, demoOpenapi, 6);

    await page.getByLabel("Select create_product for chaining").check();
    await page.getByLabel("Select get_product for chaining").check();
    await page.getByRole("button", { name: "Create chain (2)" }).click();
    await expect(page.getByText("Action draft created. Review mappings, then validate and approve it.")).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Tool name").fill("create_then_get_product");
    await page.getByLabel("Title").fill("Create then get product");
    await page.getByLabel("Description").fill("Create a product and verify it by reading the created product.");

    const secondStep = page.locator(".chain-step").nth(1);
    const productIdBinding = secondStep.locator(".binding-row").filter({ hasText: "product_id" });
    await productIdBinding.locator("select").first().selectOption("previous_step");
    await productIdBinding.locator("select").nth(1).selectOption("create_product");
    await productIdBinding.locator("input").fill("data.id");

    const inputSchemaArea = page.locator(".schema-grid textarea").first();
    const schema = JSON.parse(await inputSchemaArea.inputValue());
    delete schema.properties.product_id;
    schema.required = schema.required.filter((item: string) => item !== "product_id");
    await inputSchemaArea.fill(JSON.stringify(schema, null, 2));

    await page.getByRole("button", { name: "Save draft" }).click();
    await expect(page.getByText("Action draft saved. Validation is required before approval.")).toBeVisible({ timeout: 15_000 });

    const inlineProductId = `p-inline-${Date.now()}`;
    await page.locator(".inline-test textarea").fill(JSON.stringify({
      body: { id: inlineProductId, name: "Inline chain plan", price: 201 },
    }, null, 2));
    await page.getByRole("button", { name: "Run test" }).click();
    await expect(page.locator(".inline-test pre")).toContainText("Inline chain plan", { timeout: 20_000 });
    await expect(page.locator(".inline-test pre")).toContainText('"trace"');

    await validateAndApproveCurrentAction(page);
    await createProfileAndRelease(page, "Chain Profile", "A focused profile containing one verified write-read chain.", /Create then get product/);

    const releaseProductId = `p-release-${Date.now()}`;
    await testReleaseTool(page, "create_then_get_product", {
      body: { id: releaseProductId, name: "Release chain plan", price: 211 },
    }, "Release chain plan");

    const endpoint = await page.locator(".primary-endpoint code").first().innerText();
    expect(endpoint).toMatch(new RegExp(`^${backendUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/mcp/.+/mcp$`));

    const initialize = await mcpPost(page, endpoint, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "product-to-mcp-e2e", version: "1.0.0" },
      },
    });
    const toolsList = await mcpPost(page, endpoint, { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    const mcpProductId = `p-mcp-${Date.now()}`;
    const toolsCall = await mcpPost(page, endpoint, {
      jsonrpc: "2.0",
      id: 3,
      method: "tools/call",
      params: {
        name: "create_then_get_product",
        arguments: { body: { id: mcpProductId, name: "Raw MCP chain plan", price: 221 } },
      },
    });

    expect(initialize.status).toBe(200);
    expect(toolsList.status).toBe(200);
    expect(toolsCall.status).toBe(200);
    expect(toolsList.body.result.tools.some((tool: { name: string }) => tool.name === "create_then_get_product")).toBe(true);
    expect(toolsCall.body.result.structuredContent.status).toBe("success");
    expect(JSON.stringify(toolsCall.body)).toContain("Raw MCP chain plan");

    const protocolProof = {
      endpoint,
      initialize: { httpStatus: initialize.status, protocolVersion: initialize.body.result.protocolVersion },
      "tools/list": { httpStatus: toolsList.status, toolNames: toolsList.body.result.tools.map((tool: { name: string }) => tool.name) },
      "tools/call": { httpStatus: toolsCall.status, status: toolsCall.body.result.structuredContent.status, productId: mcpProductId },
    };
    await showMcpProof(page, protocolProof);

    evidence.assertions = [
      "Chained action contains create_product then get_product",
      "Second step maps product_id from the previous create step output",
      "Action-level chain test includes a trace",
      "Release test executes the generated action tool",
      "Raw MCP initialize, tools/list, and tools/call all succeed",
    ];
    evidence.protocolProof = protocolProof;
  } finally {
    evidence.video = await close();
    await writeEvidence(slug, evidence);
  }
});
