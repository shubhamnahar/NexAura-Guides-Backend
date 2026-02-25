## 2025-05-22 - [Unprotected Sensitive Endpoints]
**Vulnerability:** The `/api/analyze/analyze` and `/api/analyze/analyze_live` endpoints were public and lacked authentication.
**Learning:** In a fast-growing codebase, new endpoints might be added without inheriting the security middleware or decorators used elsewhere.
**Prevention:** Always use a consistent authentication dependency for all routes that interact with external services or sensitive data.
