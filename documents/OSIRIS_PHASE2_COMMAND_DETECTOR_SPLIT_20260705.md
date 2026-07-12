# OSIRIS Phase 2: Command Detector Split

Date: 2026-07-05

Status: COMPLETE

Completed:
- Extracted detect_command() from assistant_router.py
- Created osiris-api/app/command_detector.py
- assistant_router.py now imports detect_command from command_detector.py
- Cleaned accidental extra helper code from command_detector.py
- Confirmed command_detector import and basic detection tests passed
- Confirmed API restart and health check passed
- Confirmed route tests passed
- Confirmed full Osiris validation passed

Validated detector commands:
- gpu status -> gpu_status
- project summary -> dev_summary
- pending patches -> patch_pending
- security status -> security_status

Validated API routes:
- project summary -> dev_summary
- pending patches -> patch_pending
- gpu status -> gpu_status
- security status -> security_status

Current extracted architecture:
- command_detector.py
- routers/command_registry.py
- routers/system_router.py
- routers/dev_router.py
- routers/document_router.py
- routers/patch_router.py
- routers/dev_review_router.py
- routers/agent_router.py
- routers/self_heal_router.py

Current state:
- assistant_router.py is now mostly orchestration:
  - normalize message
  - handle priority overrides
  - classify intent
  - save interaction memory
  - dispatch through command_registry

Security:
- Security grade remains Strong.
- Full system snapshot passed.

Next recommended Phase 2 step:
Clean assistant_router.py formatting, remove excess blank lines, and inspect remaining responsibilities before moving on to model/intent reliability improvements.
