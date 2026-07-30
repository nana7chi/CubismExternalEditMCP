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
access to **42 MCP tools** for model inspection, editing, and diagnostics.

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
IDs and property names:

1. `cubism_get_model_uid` — get the current model UID
2. `cubism_get_parameter_structure` / `cubism_get_part_structure` / `cubism_get_deformer_structure` — discover objects
3. `cubism_get_object` — look up details of a specific item

## Available Tools

### Connection & Diagnostics (1 tool)

| Tool | Description |
|------|-------------|
| `cubism_status` | Check connection, registration, authorization, edit authorization |

### Model & Document Info (4 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_model_uid` | — | Get UID of the currently opened model |
| `cubism_get_current_edit_mode` | — | Get current edit mode (Physics/Modeling/Animation/ModelingMeshEdit/FormAnimation) |
| `cubism_get_documents` | — | List all open documents (PhysicsDocuments/ModelingDocuments/AnimationDocuments) |
| `cubism_get_document` | `document_uid` | Get single document details by UID |

### Parameter Values (3 tools, read/write without edit transaction)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_parameter_values` | `model_uid`, `ids?` | Get current parameter values (all if `ids` omitted) |
| `cubism_set_parameter_values` | `model_uid`, `parameters` | Set parameter values (`[{Id, Value}]`) |
| `cubism_clear_parameter_values` | `model_uid` | Clear temporary parameter value cache |

### Structure Query (5 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_parameters` | `model_uid?`, `document_uid?` | Parameter metadata (Name, Min/Max/Default, GroupUID, Type, Keyform). Type: 0=normal, 1=blend shape |
| `cubism_get_parameter_groups` | `model_uid?`, `document_uid?` | Parameter group list (GroupUID, GroupName) |
| `cubism_get_parameter_structure` | `model_uid` | Full parameter tree (groups + params with KeyValues) |
| `cubism_get_part_structure` | `model_uid` | Part tree (ArtMesh/WarpDeformer/RotationDeformer/Part/ArtPath/Glue) |
| `cubism_get_deformer_structure` | `model_uid` | Deformer hierarchy tree |

### Object Query (3 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_object` | `model_uid`, `id`, `parameters?` | Detailed info per object type; pass `parameters` to query at specific keyframe |
| `cubism_get_parameter_keys` | `model_uid`, `object_id` | Parameter keyframes linked to an object |
| `cubism_get_objects_by_parameter_keys` | `model_uid`, `parameter_id`, `key_value` | Find objects linked to a parameter at a given key value |

### Selection (3 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_get_selected` | `model_uid` | IDs of currently selected objects |
| `cubism_add_selected_objects` | `model_uid`, `ids?` | Add objects to selection (Edit permission required) |
| `cubism_clear_selected_objects` | `model_uid` | Clear all selection (Edit permission required) |

### Generic Edit (2 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `cubism_edit` | `action`, `params` | Single edit with auto Begin/End transaction. Prefer dedicated tools below when available. |
| `cubism_edit_batch` | `actions` | Batch edit in one transaction; auto Cancel on failure |

**Important**: Never include `ModelUID` in `params` for `cubism_edit` — it is injected automatically.

### Dedicated Edit Tools (21 tools)

Each tool auto-wraps `EditBegin`/`EditEnd`. **Always prefer these over `cubism_edit`** — they have full type signatures for better AI accuracy.

#### Parameter Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_add_parameter` | `model_uid`, `name?`, `id?`, `group_id?`, `min?`, `default?`, `max?`, `is_blend_shape?` | Add a parameter |
| `cubism_edit_parameter` | `model_uid`, `id`, `new_id?`, `name?`, `min?`, `default?`, `max?`, `is_repeat?` | Edit parameter properties |
| `cubism_delete_parameter` | `model_uid`, `id` | Delete a parameter |

#### Parameter Group Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_add_parameter_group` | `model_uid`, `name?`, `id?` | Add a parameter group |
| `cubism_edit_parameter_group` | `model_uid`, `id`, `new_id?`, `name?`, `label_color_type?`, `label_custom_color?` | Edit group properties |
| `cubism_delete_parameter_group` | `model_uid`, `id` | Delete a parameter group |
| `cubism_move_parameter` | `model_uid`, `id`, `group_id`, `insert_index?` | Move parameter to a group |
| `cubism_move_parameter_group` | `model_uid`, `id`, `insert_index` | Reorder parameter groups |

#### Parameter Key Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_add_parameter_key` | `model_uid`, `object_id`, `parameter_id`, `key_value` | Add keyframe to a parameter |
| `cubism_delete_parameter_key` | `model_uid`, `object_id?`, `parameter_id?`, `key_value?`, `strict?` | Delete parameter keyframes |
| `cubism_move_parameter_key` | `model_uid`, `from_value`, `to_value`, `object_id?`, `parameter_id?`, `strict?`, `force_overwrite?` | Move keyframe position |

#### Part Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_add_part` | `model_uid`, `name?`, `id?`, `draw_order?`, `ids?`, `is_nested?` | Add a part |
| `cubism_edit_part` | `model_uid`, `id`, plus 17 optional fields (new_id, name, parent_id, opacity, draw_order, multiply_color, screen_color, color_blend, alpha_blend, clipping_ids, is_reverse_mask, is_grouped, is_guid_image, is_offscreen, label_color_type, label_custom_color, parameters, is_exact_match) | Edit part properties |

#### ArtMesh Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_edit_artmesh` | `model_uid`, `id`, plus 15 optional fields (new_id, name, parent_id, parent_deformer_id, opacity, draw_order, multiply_color, screen_color, color_blend, alpha_blend, clipping_ids, is_reverse_mask, is_culling, label_color_type, label_custom_color, parameters, is_exact_match) | Edit ArtMesh properties |

#### Glue Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_edit_glue` | `model_uid`, `id`, plus 7 optional fields (new_id, name, parent_id, intensity, label_color_type, label_custom_color, parameters, is_exact_match) | Edit Glue properties |

#### Deformer Editing

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_add_warp_deformer` | `model_uid`, `name?`, `id?`, `parent_id?`, `target_object_ids?`, `mode?`, `warp_div_h?`, `warp_div_v?`, `bezier_div_h?`, `bezier_div_v?`, `consider_child_keyforms?`, `snap_center?` | Add a warp deformer |
| `cubism_add_rotation_deformer` | `model_uid`, `name?`, `id?`, `parent_id?`, `target_object_ids?`, `mode?` | Add a rotation deformer |
| `cubism_edit_warp_deformer` | `model_uid`, `id`, plus 10 optional fields (new_id, name, parent_id, parent_deformer_id, opacity, multiply_color, screen_color, label_color_type, label_custom_color, parameters, is_exact_match) | Edit warp deformer |
| `cubism_edit_rotation_deformer` | `model_uid`, `id`, plus 12 optional fields (new_id, name, parent_id, parent_deformer_id, angle, base_angle, scale, opacity, multiply_color, screen_color, label_color_type, label_custom_color, parameters, is_exact_match) | Edit rotation deformer |

#### Object Operations

| Tool | Key Parameters | Description |
|------|---------------|-------------|
| `cubism_delete_object` | `model_uid`, `id` | Delete any object (ArtMesh/Deformer/Part/Glue) |
| `cubism_move_object_on_parts_palette` | `model_uid`, `id`, `parent_id?`, `insert_id?`, `insert_index?` | Move object in the Parts palette |

### Enum Values

These enum values are verified through Editor API testing:

**LabelColorType**: `undefined`, `custom`, `red`, `orange`, `yellow`, `green`, `blue`, `purple`, `gray`

**ColorBlendMode**: `normal`, `add`, `addglow`, `darken`, `multiply`, `colorburn`, `linearburn`, `lighten`, `screen`, `colordodge`, `overlay`, `softlight`, `hardlight`, `linearlight`, `hue`, `color`, `add_5.2`, `multiply_5.2`

**AlphaBlendMode**: `over`, `atop`, `out`, `conjoint`, `disjoint`

**DeformerParentMode**: `AsParent`, `AsChild`

## Common Recipes

### Inspect Model Structure

```
cubism_status                            → check connection
cubism_get_model_uid                     → get UID
cubism_get_parameter_structure(model_uid) → explore parameters
cubism_get_part_structure(model_uid)      → explore parts/deformers
cubism_get_object(model_uid, "ArtMesh0")  → inspect a specific object
```

### Modify a Part's Label Color

```
cubism_edit_part(model_uid, part_id, label_color_type="custom", label_custom_color="#FF0000")
```

### Create a New Parameter (in group "G1", range 0–1, default 0.5)

```
cubism_add_parameter(model_uid, name="MyParam", id="MyParam", group_id="G1", min=0, default=0.5, max=1)
```

### Batch-Add Keyframes

```
cubism_add_parameter_key(model_uid, object_id="ArtMesh0", parameter_id="ParamAngleX", key_value=0.3)
cubism_add_parameter_key(model_uid, object_id="ArtMesh0", parameter_id="ParamAngleX", key_value=0.7)
```

Or via batch transaction:
```
cubism_edit_batch([
  {"action": "AddParameterKey", "params": {"ObjectId": "ArtMesh0", "ParameterId": "ParamAngleX", "KeyValue": 0.3}},
  {"action": "AddParameterKey", "params": {"ObjectId": "ArtMesh0", "ParameterId": "ParamAngleX", "KeyValue": 0.7}}
])
```

### Move a Deformer in the Palette

```
cubism_move_object_on_parts_palette(model_uid, "Warp1", parent_id="Part5", insert_index=0)
```

### Set Parameter Values (no edit transaction needed)

```
cubism_set_parameter_values(model_uid, [{"Id": "ParamAngleX", "Value": 0.5}, {"Id": "ParamAngleY", "Value": -0.3}])
```

## Error Handling

| Error | Cause | Action |
|-------|-------|--------|
| `NotRegistered` | Editor not connected or integration off | Enable External App Integration in Editor |
| `NotApproved` | Allow not checked | Check "Allow" in the dialog |
| `EditNotApproved` | Edit not checked | Also check "Edit" in the dialog |
| `NoModel` | No model UID obtained | Open a model in Editor |
| `ModelUIDMismatch` | Specified UID != Editor current model | Use `cubism_get_model_uid` to get actual UID |
| `InvalidParameter` | Wrong parameter ID | Run `cubism_get_parameters` to discover correct IDs |
| `InvalidData` | Bad field name or value | Verify field names match the tool signatures exactly; Editor is case-sensitive |
| Operation fails | Wrong object ID | Run inspection tools first to discover correct values |
| Connection lost | Editor restarted | Re-enable integration and re-grant permissions |

## Constraints

- Cubism Editor 5.4 Alpha is required (expires 2026-09-14).
- Every Editor restart requires re-enabling integration and re-granting permissions.
- Only one model can be operated at a time.
- All edit tools auto-wrap in `EditBegin`/`EditEnd`; batches auto-cancel on failure.
- Always inspect the model structure before editing — never guess IDs.
