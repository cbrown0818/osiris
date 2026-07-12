# OSIRIS Phase 2: Document Router Split

Date: 2026-07-05

Status: COMPLETE

Completed:
- Extracted document query handling out of assistant_router.py
- Created osiris-api/app/routers/document_router.py
- assistant_router.py reduced from 1355 lines to 1183 lines
- document_router.py contains document query logic
- summarize the document routes to doc_query
- according to the document routes to doc_query
- Document memory search works through Qdrant
- Ollama document answer generation works

Known intentional legacy names:
- Qdrant collection remains lilith_documents
- Parent path remains /srv/lilith

Next recommended Phase 2 step:
Extract patch handling into routers/patch_router.py
