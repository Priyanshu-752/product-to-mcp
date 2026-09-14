import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ActionDefinition, Operation, ToolProfile, Workspace } from "../api";
import { ActionStudio } from "./ActionStudio";

const mockApi = vi.hoisted(() => ({
  workspace: vi.fn(), saveGroups: vi.fn(), createCustomToolset: vi.fn(), updateCustomToolset: vi.fn(), deleteCustomToolset: vi.fn(), createAction: vi.fn(), updateAction: vi.fn(),
  deleteAction: vi.fn(), validateAction: vi.fn(), approveAction: vi.fn(), testAction: vi.fn(),
  createProfile: vi.fn(), updateProfile: vi.fn(), deleteProfile: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return { ...original, api: mockApi };
});

const stamp = "2026-01-01T00:00:00Z";

function operation(index: number, method = "GET"): Operation {
  return {
    operation_id: `getItem${index}`, tool_name: `getitem${index}`, method, path: `/items/${index}`,
    description: `Get item ${index}`, input_schema: { type: "object", properties: {} },
    output_schema: { type: "object", properties: { id: { type: "string" } } },
    tags: [index < 25 ? "Catalog" : "Inventory"], default_group: index < 25 ? "Catalog" : "Inventory",
    operation_fingerprint: String(index).padStart(64, "0"), supported: true,
  };
}

function action(status: ActionDefinition["status"] = "draft", steps = [0]): ActionDefinition {
  return {
    action_id: "action-1", project_id: "project-1", name: "inspect_catalog", title: "Inspect catalog",
    description: "Inspect catalog items for an agent.", group_id: "group-1",
    input_schema: { type: "object", properties: {}, additionalProperties: false },
    output_schema: { type: "object", properties: { id: { type: "string" } } },
    steps: steps.map((index) => ({ step_id: `step_${index}`, operation_id: `getItem${index}`, argument_bindings: [], condition: null })),
    output_bindings: [], annotations: {}, status, created_at: stamp, updated_at: stamp,
  };
}

function workspace(overrides: Partial<Workspace> = {}): Workspace {
  const operations = Array.from({ length: 50 }, (_, index) => operation(index));
  return {
    project: { project_id: "project-1", name: "Catalog", base_url: "https://api.example.com", auth_type: "none" },
    operations,
    groups: [
      { group_id: "group-1", project_id: "project-1", name: "Catalog", sort_order: 0, hidden: false, operation_ids: operations.slice(0, 25).map((item) => item.operation_id), created_at: stamp, updated_at: stamp },
      { group_id: "group-2", project_id: "project-1", name: "Inventory", sort_order: 1, hidden: false, operation_ids: operations.slice(25).map((item) => item.operation_id), created_at: stamp, updated_at: stamp },
    ],
    toolsets: [
      { toolset_id: "ts_catalog", name: "Catalog", operation_ids: operations.slice(0, 25).map((item) => item.operation_id), read_count: 25, write_count: 0 },
      { toolset_id: "ts_inventory", name: "Inventory", operation_ids: operations.slice(25).map((item) => item.operation_id), read_count: 25, write_count: 0 },
    ],
    actions: [], profiles: [],
    limits: { max_chain_steps: 10, warn_chain_steps: 5, warn_profile_tools: 20, confirm_profile_tools: 30 },
    ...overrides,
  };
}

function renderStudio(value: Workspace, onRelease = vi.fn()) {
  function Harness() {
    const [currentWorkspace, setCurrentWorkspace] = useState(value);
    const [selectedToolsetIds, setSelectedToolsetIds] = useState(value.toolsets.map((item) => item.toolset_id));
    return <ActionStudio projectId="project-1" workspace={currentWorkspace} selectedToolsetIds={selectedToolsetIds} onSelectedToolsetIds={setSelectedToolsetIds} toolsetsNeedReview={false} onToolsetsReviewed={vi.fn()} onWorkspace={setCurrentWorkspace} onRelease={onRelease} onMessage={vi.fn()} />;
  }
  return render(<Harness />);
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("Action Studio", () => {
  it("searches auto-derived toolsets without manual group editing", async () => {
    const user = userEvent.setup();
    const value = workspace();
    renderStudio(value);

    await user.type(screen.getByLabelText("Search operations"), "getitem49");
    expect(screen.getByText("getitem49")).toBeInTheDocument();
    expect(screen.queryByText("getitem1")).not.toBeInTheDocument();

    expect(screen.queryByLabelText("New group name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Move getitem0 to group")).not.toBeInTheDocument();
    expect(mockApi.saveGroups).not.toHaveBeenCalled();
  });

  it("selects derived toolsets for the generated API tool list", async () => {
    const user = userEvent.setup();
    const value = workspace();
    const release = vi.fn().mockResolvedValue(undefined);
    renderStudio(value, release);

    await user.click(screen.getByRole("button", { name: /Release MCP/ }));
    await user.click(screen.getByRole("checkbox", { name: /Inventory/ }));
    expect(screen.getByText(/25 API tools selected/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate API-only release" }));
    expect(release).toHaveBeenCalledWith(null, "api_only", false, ["ts_catalog"]);
  });

  it("creates a custom toolset and includes only its selected API tools", async () => {
    const user = userEvent.setup();
    const value = workspace();
    const custom = { toolset_id: "custom_1", name: "Essentials", operation_ids: ["getItem0"], read_count: 1, write_count: 0, custom: true };
    mockApi.createCustomToolset.mockResolvedValue(custom);
    mockApi.workspace.mockResolvedValue({ ...value, toolsets: [...value.toolsets, custom] });
    const release = vi.fn().mockResolvedValue(undefined);
    renderStudio(value, release);

    await user.type(screen.getByLabelText("Custom toolset name"), "Essentials");
    await user.click(screen.getByLabelText("Add getitem0 to custom toolset"));
    await user.click(screen.getByRole("button", { name: "Save toolset (1)" }));
    await waitFor(() => expect(mockApi.createCustomToolset).toHaveBeenCalledWith("project-1", { name: "Essentials", operation_ids: ["getItem0"] }));
    await user.click(screen.getByRole("button", { name: /Release MCP/ }));
    await user.click(screen.getByRole("button", { name: "Clear" }));
    await user.click(screen.getByRole("checkbox", { name: /Essentials/ }));
    expect(screen.getByText(/1 API tools selected/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate API-only release" }));
    expect(release).toHaveBeenCalledWith(null, "api_only", false, ["custom_1"]);
  });

  it("shows server validation errors and persists manual step ordering", async () => {
    const user = userEvent.setup();
    const draft = action("draft", [0, 1]);
    const value = workspace({ actions: [draft] });
    mockApi.workspace.mockResolvedValue(value);
    mockApi.validateAction.mockResolvedValue({
      valid: false,
      errors: [{ path: "steps.1.argument_bindings", code: "required_mapping", message: "Required API argument is not mapped." }],
      action: draft,
    });
    mockApi.updateAction.mockImplementation(async (_projectId: string, updated: ActionDefinition) => ({ ...updated, status: "draft" }));
    renderStudio(value);

    await user.click(screen.getByRole("button", { name: /Optional actions 1/ }));
    await user.click(screen.getByRole("button", { name: /Inspect catalog/ }));
    await user.click(screen.getByRole("button", { name: "Validate saved draft" }));
    expect(await screen.findByText("Required API argument is not mapped.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Operation to add to this action"), "getItem2");
    await user.click(screen.getByRole("button", { name: "Add step" }));
    await user.click(screen.getByRole("button", { name: "Move step_0 down" }));
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() => expect(mockApi.updateAction).toHaveBeenCalled());
    expect(mockApi.updateAction.mock.calls[0][1].steps.map((step: ActionDefinition["steps"][number]) => step.step_id)).toEqual(["step_1", "step_0", "getitem2"]);
  });

  it("flags large profiles and requires explicit release confirmation", async () => {
    const user = userEvent.setup();
    const approvedActions = Array.from({ length: 31 }, (_, index) => ({
      ...action("approved"), action_id: `action-${index + 1}`, name: `inspect_catalog_${index + 1}`, title: `Inspect catalog ${index + 1}`,
    }));
    const profile: ToolProfile = {
      profile_id: "profile-1", project_id: "project-1", name: "Large catalog", description: "All catalog tools.",
      action_ids: approvedActions.map((item) => item.action_id),
      created_at: stamp, updated_at: stamp,
    };
    const release = vi.fn().mockResolvedValue(undefined);
    renderStudio(workspace({ actions: approvedActions, profiles: [profile] }), release);

    await user.click(screen.getByRole("button", { name: /Release MCP 1/ }));
    expect(screen.getByText("Large profile: consider splitting it by agent role.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate API + actions release" }));
    expect(release).toHaveBeenCalledWith(profile, "api_and_actions", true, ["ts_catalog", "ts_inventory"]);
  });

  it("lets users generate API-only or actions-only releases", async () => {
    const user = userEvent.setup();
    const approved = action("approved");
    const profile: ToolProfile = {
      profile_id: "profile-1", project_id: "project-1", name: "Reader", description: "Catalog reader.",
      action_ids: [approved.action_id], created_at: stamp, updated_at: stamp,
    };
    const release = vi.fn().mockResolvedValue(undefined);
    renderStudio(workspace({ actions: [approved], profiles: [profile] }), release);

    await user.click(screen.getByRole("button", { name: /Release MCP 1/ }));
    await user.click(screen.getByRole("button", { name: "Generate API-only release" }));
    expect(release).toHaveBeenCalledWith(null, "api_only", false, ["ts_catalog", "ts_inventory"]);

    await user.selectOptions(screen.getByLabelText("Release contents for Reader"), "actions_only");
    await user.click(screen.getByRole("button", { name: "Generate actions-only release" }));
    expect(release).toHaveBeenLastCalledWith(profile, "actions_only", false, ["ts_catalog", "ts_inventory"]);

    await user.selectOptions(screen.getByLabelText("Release contents for Reader"), "api_only");
    const readerCard = screen.getByRole("heading", { name: "Reader" }).closest("article");
    expect(readerCard).not.toBeNull();
    await user.click(within(readerCard!).getByRole("button", { name: "Generate API-only release" }));
    expect(release).toHaveBeenLastCalledWith(profile, "api_only", false, ["ts_catalog", "ts_inventory"]);
  });

  it("blocks profiles containing an invalidated action but lets the user remove it", async () => {
    const user = userEvent.setup();
    const draft = action("draft");
    const profile: ToolProfile = {
      profile_id: "profile-1", project_id: "project-1", name: "Reader", description: "Catalog reader.",
      action_ids: [draft.action_id], created_at: stamp, updated_at: stamp,
    };
    renderStudio(workspace({ actions: [draft], profiles: [profile] }));

    await user.click(screen.getByRole("button", { name: /Release MCP 1/ }));
    expect(screen.getByText("Blocked: 1 action needs validation and approval again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate API + actions release" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const selectedDraft = screen.getByRole("checkbox", { name: /Inspect catalog/ });
    expect(selectedDraft).toBeEnabled();
    await user.click(selectedDraft);
    expect(selectedDraft).not.toBeChecked();
  });
});
