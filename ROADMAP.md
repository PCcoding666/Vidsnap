VidSnap — turn a long video into a publishable illustrated article, with every figure traceable to the frame it came from.

## Now

M0, consolidation (2026-11): one truthful main branch. PR #24 (first live harness-vs-native comparison, frame labels by default, allow-listed model and endpoint, `analyze` flags, `recipe article`) is merged; the reviewed article workflow v2 is rebased and open as PR #27, opt-in, not yet merged; stale worktrees and pull requests are cleared; this roadmap and `PROJECT_STATE.md` describe the present.

## Next

M1, proof: run article v1, v2 and the native URL baseline on five real videos (an English screen tutorial, an English talk with audio, a Chinese explainer, a Chinese vertical short, one with music over speech) and rate them blind against the hand-edited 2026-11-04 articles. Hard gates: figure fidelity at least 95% and zero wrong numbers or names; soft gates: key-step coverage and readability not below the hand-edited articles; at most 5 CNY and 15 minutes per article. v2 becomes the default only if it passes; the native upload path joins the evaluation as its own system so this comparison runs under the same graders.

M2, usable by a stranger: PyPI release, `pipx install vidsnap-harness`, one command from a local file to an article folder, a creator-facing README whose first screen is a real article and its trace, a second provider (DeepSeek or another OpenAI-compatible endpoint) through `ProviderProtocol`, a licensed example video under `docs/examples/`.

## Later

M3, distribution and credibility: a write-up of the measured comparison (what lost, what won, what was fixed), releases with results pages, good-first issues, and the first merged pull request from outside. Then the earlier runtime goals in their new role as the engine: diffable traces across runs, a versioned compatibility contract for plugins and providers, more source-preserving recipes.

## Non-goals

- SaaS accounts
- Hosted video library
- Arbitrary shell agent
- Unrestricted browser agent
- Plugin marketplace
- Social publishing platform
