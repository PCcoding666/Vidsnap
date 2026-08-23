# Migration to VidSnap Harness

This release is intentionally breaking. The React frontend, authentication, OAuth/JWT, subscriptions, email, PostgreSQL/SQLAlchemy, Redis/Celery, WebSockets, cloud-persistent jobs, Docker Compose infrastructure, and product deployment scripts have been removed.

Use vidsnap analyze or VideoHarness.run(...) for a single bounded run. CLI/SDK runs can retain a user-selected RunBundle; HTTP requests use a temporary RunBundle and remove it at completion.

The only approved model configuration is the fixed qwen3.8-max compatible endpoint. Set a rotated local VIDSNAP_QWEN_API_KEY (or QWEN_API_KEY) only when running a live benchmark. Never pass credentials in an HTTP request.
