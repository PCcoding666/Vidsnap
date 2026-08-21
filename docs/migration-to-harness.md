# Migration to VidSnap Harness

This release is intentionally breaking. The React frontend, authentication, OAuth/JWT, subscriptions, email, PostgreSQL/SQLAlchemy, Redis/Celery, WebSockets, cloud-persistent jobs, Docker Compose infrastructure, and product deployment scripts have been removed.

Use vidsnap analyze or VideoHarness.run(...) for a single bounded run. CLI/SDK runs can retain a user-selected RunBundle; HTTP requests use a temporary RunBundle and remove it at completion.

The only approved model configuration is the fixed qwen3.8-max compatible endpoint. Set a rotated local VIDSNAP_QWEN_API_KEY (or QWEN_API_KEY) only when running a live benchmark. Never pass credentials in an HTTP request.

## Current guarantees

- Plugin trust boundary: only allow-listed, dependency-checked plugins run, and runs can never mutate them.
- The Agentic policy is a true iterative loop: the model chooses only allowed tools and receives tool results; budgets and verifier gates still bound every run.
- Fixed remains the default policy and keeps transcribe_audio before sample_evidence (ASR before visual evidence).
- `vidsnap trace export <run-dir> -o out.html` renders one run offline; legacy result directories are summary-only and are never reconstructed.
- Infrastructure validation is not evidence that Harness beats Direct; that question requires actual benchmark evidence.
- These pages make no live result claims.
