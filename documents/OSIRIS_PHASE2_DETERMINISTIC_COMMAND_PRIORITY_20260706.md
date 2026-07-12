# OSIRIS Phase 2: Deterministic Command Priority

Date: 2026-07-06

Status: COMPLETE

Completed:
- Added deterministic priority command detection
- Updated command_detector.py so obvious commands are resolved before AI classification
- Replaced assistant_router.py with a cleaner dispatcher
- assistant_router.py now:
  - cleans empty input
  - detects deterministic commands
  - dispatches known commands directly
  - only uses AI classification for unknown/chat-like input
  - saves interaction memory
  - dispatches through command_registry
- Confirmed API restart and health check passed
- Confirmed major route tests passed

Validated routes:
- project summary -> dev_summary
- summarize osiris project -> dev_summary
- gpu status -> gpu_status
- security status -> security_status
- pending patches -> patch_pending
- show patch backups -> patch_backups
- summarize the document -> doc_query
- cognition optimize my codebase -> cognition
- agent loop inspect current osiris project health -> agent_loop
- review file osiris-api/app/assistant_router.py -> dev_review_file
- explain file osiris-api/app/assistant_router.py -> dev_explain_file

Important note:
- The self-heal route test created a pending patch by design.
- The generated self-heal patch was not applied and was denied.
- Future self-heal tests should use caution because they create real pending patches.

Current state:
- Deterministic commands now bypass AI classifier.
- AI classifier is reserved for unknown or chat-like messages.
- assistant_router.py is now a compact orchestrator.

Next recommended Phase 2 step:
Improve self-heal safety so route tests can check self_heal without generating an actual pending patch.
