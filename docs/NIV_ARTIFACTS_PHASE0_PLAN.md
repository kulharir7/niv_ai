# Niv Artifacts — Phase 0 Plan (Safe Start)

## Goal
Create the base data model for Artifacts without touching existing chat/tool behavior.

## Safety Rules
- No overwrite of existing core files.
- No changes to streaming/chat execution paths in Phase 0.
- Keep migrations reversible and isolated.

## Added in Phase 0
1. **DocType: Niv Artifact**
   - title, type, status, owner
   - source prompt
   - generated content JSON
   - preview HTML
   - version metadata

2. **DocType: Niv Artifact Version**
   - link to artifact
   - version number
   - change summary
   - snapshot

## Phase 1 (in progress)
- [x] API endpoints scaffolded in `niv_core/api/artifacts.py`
  - `create_artifact`
  - `list_artifacts`
  - `get_artifact`
  - `update_artifact_content`
  - `set_artifact_publish_state`
  - `get_artifact_version`
- [ ] Basic right-pane preview in chat UI (feature flag)
- [x] Version write on every content update (auto version row)

## Test Gate Before Server
- `bench --site <site> migrate` clean
- Existing chat send/receive works
- Existing settings panel works
- No console JS errors
- No MCP regression
