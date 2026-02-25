## 2025-02-25 - Hardcoded Database Credentials in Fallback Configuration
**Vulnerability:** A hardcoded PostgreSQL connection string containing a plaintext password (`Andy%2022`) was used as a fallback for the `DATABASE_URL` environment variable in `app/database.py`.
**Learning:** Fallback values in `os.getenv()` or `os.environ.get()` are a common source of accidental credential leakage. While they may seem convenient for local development, they often end up in version control.
**Prevention:** Never use sensitive data as default values in code. Instead, use a "fail-fast" approach by raising an exception if required environment variables are missing, or use a separate, non-committed configuration file (like `.env`) for local development.
