VidSnap — Build auditable video agents with bounded tools, plugins, and replayable traces.

## Now

Every run produces an auditable trace that can be replayed offline, with a portable viewer for inspecting steps. Plugins and model providers operate behind typed ports under fixed bounds: Qwen (qwen3.8-max) is the locked default reference provider with concurrency capped at two, and keys come only from environment variables. The application may inject a conforming ProviderProtocol before a run, while the agent cannot switch provider, model, or base_url during a run. Recipes are source-preserving, keeping original media references intact from input to output. Benchmarks ship as documentation-only profiles with offline conformance checks, reported as measured results rather than superiority claims.

## Next

Harden trace replay so traces stay diffable and portable as the harness evolves. Formalize a versioned compatibility contract so external plugins and providers declare their capabilities and bounds explicitly. Extend source-preserving recipes to more video workflows, and deepen benchmark trust by publishing variance, failure modes, and reproducible setups.

## Later

Support cross-run trace comparison to surface behavioral drift over time. Grow the plugin developer kit toward a stable release with offline conformance checks. Enable community-contributed recipes with provenance and source verification.

## Non-goals

- SaaS accounts
- Hosted video library
- Arbitrary shell agent
- Unrestricted browser agent
- Plugin marketplace
- Social publishing platform
