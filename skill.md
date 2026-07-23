---
name: cubism-editor-control
description: >-
  Control Live2D Cubism Editor via the cubism-mcp MCP server. Use this skill
  to inspect model structures (parameters, parts, deformers), query individual
  objects, execute single and batch edits with automatic transaction management,
  or diagnose connection status. Trigger when the user asks to list model info,
  modify parameters/parts/deformers/ArtMesh/Glue, add keyframes, move objects,
  or troubleshoot the Cubism Editor connection.
---

# Cubism Editor Control

Control Live2D Cubism Editor through natural language. This skill provides
access to 9 MCP tools for model inspection, editing, and diagnostics.

## Prerequisites

- Cubism Editor 5.4 Alpha running with a model open
- External App Integration enabled (File → Settings → port 22033)
- Allow + Edit permissions granted in the dialog

## Core Workflow

### Always Start Here

Before any operation, check the connection status via `cubism_status`. If
`connected` is false, guide the user to enable external integration. If
`approved` or `edit_approved` is false, instruct them to grant permissions.

### Inspect Before Editing

Always query the model structure before making edits to discover the correct
IDs and property names. Use:

1. `cubism_get_model_uid` — get the current model UID
2. `cubism_get_parameter_structure` / `cubism_get_part_structure` / `cubism_get_deformer_structure` — discover objects
3. `cubism_get_object` — look up details of a specific item

## Available Tools

### Connection & Diagnostics

| Tool | Description |
|------|-------------|
| `cubism_status` | Check connection, registration, authorization, edit authorization |

### Model Inspection (Read-only)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_model_uid` | — | Get UID of the currently opened model |
| `cubism_get_parameter_structure` | `model_uid` | Parameter tree (groups, params with Min/Default/Max/Keys) |
| `cubism_get_part_structure` | `model_uid` | Part tree (ArtMesh, Deformer, Part, Glue, ArtPath) |
| `cubism_get_deformer_structure` | `model_uid` | Deformer hierarchy tree |
| `cubism_get_object` | `model_uid`, `id` | Detailed info for a single object by type |
| `cubism_get_selected` | `model_uid` | IDs of currently selected objects in Editor |

### Editing (Requires Edit permission)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_edit` | `action`, `params` | Single edit with auto Begin/End transaction |
| `cubism_edit_batch` | `actions[]` | Batch edit in one transaction; auto rollback on failure |

**Important**: Never include `ModelUID` in `params` — it is injected automatically.

### Supported Edit Actions

`AddParameter` `EditParameter` `DeleteParameter` `AddParameterGroup`
`EditParameterGroup` `AddPart` `EditPart` `AddWarpDeformer`
`AddRotationDeformer` `EditWarpDeformer` `EditArtMesh` `EditGlue`
`MoveParameter` `MoveParameterGroup` `AddParameterKey` `DeleteParameterKey`
`MoveParameterKey` `DeleteObject` `MoveObjectOnPartsPalette`

## Common Recipes

### Modify a Part's Label Color

```json
{ "action": "EditPart", "params": { "Id": "<part_id>", "LabelColor": "#FF0000" } }
```

### Create a New Parameter

```json
{ "action": "AddParameter", "params": {
  "GroupId": "<group_id>", "ParameterName": "MyParam",
  "ParameterId": "MyParam", "Default": 0.5, "Minimum": 0, "Maximum": 1
} }
```

### Batch-Add Keyframes

```json
{ "actions": [
  {"action": "AddParameterKey", "params": {"ParameterId": "<id>", "KeyValue": 0.3}},
  {"action": "AddParameterKey", "params": {"ParameterId": "<id>", "KeyValue": 0.7}}
] }
```

### Move a Deformer in the Palette

```json
{ "action": "MoveObjectOnPartsPalette", "params": {
  "Id": "<deformer_id>", "NewParentId": "<target_id>", "InsertPosition": 0
} }
```

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| `NotRegistered` | Editor not connected or integration off | Enable External App Integration in Editor |
| `NotApproved` | Allow not checked | Check "Allow" in the dialog |
| `EditNotApproved` | Edit not checked | Also check "Edit" in the dialog |
| Operation fails | Wrong ID or parameter name | Run inspection tools first to discover correct values |
| Connection lost | Editor restarted | Re-enable integration and re-grant permissions |

## Constraints

- Cubism Editor 5.4 Alpha is required (expires 2026-09-14).
- Every Editor restart requires re-enabling integration and re-granting permissions.
- Only one model can be operated at a time.
- All edits auto-wrap in `EditBegin`/`EditEnd`; batches auto-cancel on failure.
- Always inspect the model structure before editing — never guess IDs.
