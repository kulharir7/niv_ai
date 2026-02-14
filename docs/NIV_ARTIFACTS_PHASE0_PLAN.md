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

## Next (Phase 1)
- API endpoints for create/get/list artifact
- Basic right-pane preview in chat UI (feature flag)
- Version write on regenerate

## Test Gate Before Server
- `bench --site <site> migrate` clean
- Existing chat send/receive works
- Existing settings panel works
- No console JS errors
- No MCP regression
