import path from "node:path";
import { expect, test } from "@playwright/test";

test.setTimeout(120_000);

test("generates API plus action, actions-only, and API-only releases", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /No authentication/ }).click();
  await page.getByLabel("Project name").fill(`Large Catalog ${Date.now()}`);
  await page.getByRole("button", { name: "Create project and continue" }).click();

  await page.locator('input[type="file"]').setInputFiles(path.resolve("..", "examples", "large-openapi-50.yaml"));
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  await expect(page.getByText("50 operations discovered. Choose toolsets and optional actions next.")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("2 toolsets")).toBeVisible();

  await page.getByLabel("Search operations").fill("get_item50");
  await expect(page.getByText("get_item50", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create action" }).click();
  await expect(page.getByText("Action draft created. Review mappings, then validate and approve it.")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Validate saved draft" }).click();
  await expect(page.getByText("Action is valid and ready for approval.")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Approve action" }).click();
  await expect(page.getByText("Action approved for publishing profiles.")).toBeVisible({ timeout: 20_000 });

  await page.getByRole("button", { name: /Release MCP/ }).click();
  await page.getByLabel("Profile name").fill("Inventory Reader");
  await page.getByLabel("Description").fill("Focused inventory lookup tools for an agent.");
  await page.getByRole("checkbox", { name: /Get Item50 Action/ }).check();
  await page.getByRole("button", { name: "Create profile" }).click();
  await expect(page.getByText("Publishing profile 'Inventory Reader' saved.")).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: "Generate API + actions release" }).click();

  await expect(page.getByRole("heading", { name: "MCP release ready" })).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("get_item50_action · 1 API step")).toBeVisible();
  await expect(page.getByText("ACTION", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Generated release contents")).toContainText("50 API tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("1 action tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("51 total");
  await expect(page.locator(".tool-test")).toHaveCount(51);

  const mcpEndpoint = await page.locator(".primary-endpoint code").first().innerText();
  const toolsListResponse = await page.request.post(mcpEndpoint, {
    headers: {
      "Content-Type": "application/json",
      "Accept": "application/json, text/event-stream",
      "MCP-Protocol-Version": "2025-06-18",
    },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
  });
  const toolsList = await toolsListResponse.json();
  expect(toolsListResponse.ok()).toBe(true);
  expect(toolsList.result.tools).toHaveLength(51);
  expect(toolsList.result.tools.some((tool: { name: string }) => tool.name === "get_item1")).toBe(true);
  expect(toolsList.result.tools.some((tool: { name: string }) => tool.name === "get_item50_action")).toBe(true);

  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await page.getByLabel("Release contents for Inventory Reader").selectOption("actions_only");
  await page.getByRole("button", { name: "Generate actions-only release" }).click();
  await expect(page.getByLabel("Generated release contents")).toContainText("0 API tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("1 action tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("1 total");

  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await page.getByRole("button", { name: "Generate API-only release" }).click();
  await expect(page.getByLabel("Generated release contents")).toContainText("50 API tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("0 action tools");
  await expect(page.getByLabel("Generated release contents")).toContainText("50 total");
});

test("toolset release picker fits a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: /No authentication/ }).click();
  await page.getByLabel("Project name").fill(`Mobile Toolsets ${Date.now()}`);
  await page.getByRole("button", { name: "Create project and continue" }).click();
  await page.locator('input[type="file"]').setInputFiles(path.resolve("..", "examples", "large-openapi-50.yaml"));
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.locator(".compact-operation").first().screenshot({ path: "test-results/custom-toolset-mobile-row.png" });
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await expect(page.getByText("API toolsets to expose")).toBeVisible();
  await expect(page.getByText(/50 API tools selected/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.locator(".toolset-picker").screenshot({ path: "test-results/toolset-mobile.png" });
});

test("custom toolset exposes its chosen API tools and survives workspace refresh", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /No authentication/ }).click();
  await page.getByLabel("Project name").fill(`Custom Toolset ${Date.now()}`);
  await page.getByRole("button", { name: "Create project and continue" }).click();
  await page.locator('input[type="file"]').setInputFiles(path.resolve("..", "examples", "large-openapi-50.yaml"));
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  await expect(page.getByText("50 operations discovered. Choose toolsets and optional actions next.")).toBeVisible();
  await page.getByLabel("Search operations").fill("get_item1");
  await page.getByLabel("Custom toolset name").fill("Support essentials");
  await page.getByLabel("Add get_item1 to custom toolset").check();
  await page.getByRole("button", { name: "Save toolset (1)" }).click();
  await expect(page.getByText("Custom toolset 'Support essentials' saved. Select it in Release MCP to expose its API tools.")).toBeVisible();
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await expect(page.getByRole("checkbox", { name: /Support essentials/ })).not.toBeChecked();
  await page.getByRole("button", { name: "Clear" }).click();
  await page.getByRole("checkbox", { name: /Support essentials/ }).check();
  await expect(page.getByText(/1 API tools selected/)).toBeVisible();
  await page.getByRole("button", { name: "Generate API-only release" }).click();
  await expect(page.getByLabel("Generated release contents")).toContainText("1 API tools");
  await expect(page.locator(".tool-test")).toHaveCount(1);
  const mcpEndpoint = await page.locator(".primary-endpoint code").first().innerText();
  const listed = await page.request.post(mcpEndpoint, {
    headers: { "Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18" },
    data: { jsonrpc: "2.0", id: 1, method: "tools/list", params: {} },
  });
  expect(listed.ok()).toBe(true);
  expect((await listed.json()).result.tools.map((tool: { name: string }) => tool.name)).toEqual(["get_item1"]);
});

test("reimport preserves a narrow toolset selection and requires review", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /No authentication/ }).click();
  await page.getByLabel("Project name").fill(`Reimport Toolsets ${Date.now()}`);
  await page.getByRole("button", { name: "Create project and continue" }).click();
  await page.locator('input[type="file"]').setInputFiles(path.resolve("..", "examples", "large-openapi-50.yaml"));
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await page.getByRole("checkbox", { name: /Inventory/ }).uncheck();
  await expect(page.getByText(/25 API tools selected/)).toBeVisible();

  await page.getByRole("button", { name: "Back" }).click();
  await page.locator('input[type="file"]').setInputFiles(path.resolve("..", "examples", "large-openapi-50.yaml"));
  await page.getByRole("button", { name: "Next: discover operations" }).click();
  await page.getByRole("button", { name: /Release MCP/ }).click();
  await expect(page.getByText(/25 API tools selected/)).toBeVisible();
  await expect(page.getByText(/OpenAPI toolsets changed/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate API-only release" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /Catalog/ }).uncheck();
  await page.getByRole("checkbox", { name: /Catalog/ }).check();
  await expect(page.getByRole("button", { name: "Generate API-only release" })).toBeEnabled();
});
