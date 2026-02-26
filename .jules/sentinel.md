## 2025-05-22 - [Missing Authentication on New Routers]
**Vulnerability:** New API routers (like `analyze.py`) were added without the `Depends(auth.get_current_user)` dependency, leaving sensitive/costly OCR and LLM endpoints open to the public.
**Learning:** Forgetting to apply authentication to newly added routes is a common oversight when the protection is not applied globally.
**Prevention:** Always verify that every new router and its endpoints are protected by appropriate dependencies, and consider global or router-level authentication if appropriate.

## 2025-05-22 - [Public Data Leak in Search Endpoint]
**Vulnerability:** The `/api/guides/public` endpoint returns all guides in the database regardless of ownership because the `Guide` model lacks a visibility flag (`is_public`).
**Learning:** This leaks sensitive user screenshots and descriptions to any unauthenticated requester.
**Prevention:** Data should be private by default. Add a visibility field to the model and filter search results accordingly.
