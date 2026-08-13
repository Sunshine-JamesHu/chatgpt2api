# Default Upstream Model and Thinking Effort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Let administrators configure the default text upstream model and thinking effort, while allowing \`-standard\`, \`-extended\`, and \`-max\` model suffixes to override the effective thinking effort for both OpenAI-compatible text APIs.

**Architecture:** Keep the public response model unchanged, but resolve a separate upstream model and an effective thinking effort immediately after parsing each text request. Put parsing and precedence in one shared protocol helper used by both Chat Completions and Responses, then pass only resolved values to \`ConversationRequest\`. Settings remain persisted through the existing \`ConfigStore\` and generic settings endpoint; the settings page adds one model input and one constrained select.

**Tech Stack:** Python 3.12, FastAPI, unittest, Next.js/TypeScript, Zustand, shadcn/ui.

---

## Decisions and Compatibility Contract

- \`default_text_upstream_model_slug\` is a text-only fallback. It is used only when the client requests no model or \`auto\`; an explicit normal text model continues to select that upstream model. This prevents a global setting from silently discarding a caller's explicit model.
- \`default_thinking_effort\` accepts \`""\`, \`standard\`, \`extended\`, or \`max\`. \`""\` means omit \`thinking_effort\` from the upstream payload.
- For text requests, effective thinking effort precedence is: terminal model suffix (\`-standard\`, \`-extended\`, \`-max\`, case-insensitive) > explicit OpenAI-compatible request value (\`thinking_effort\`, \`reasoning_effort\`, or \`reasoning.effort\`) > configured default. An explicit \`none\` disables the configured default unless a recognized model suffix is present.
- The recognized suffix is stripped only from the upstream model. The API response and cache identity retain the caller's requested \`model\`, so a response never claims a different model name and aliases cannot reuse a response with the wrong public \`model\` field.
- Existing \`low\`, \`medium\`, \`high\`, \`xhigh\`, and \`extended\` request values remain accepted by the old compatibility normalization. New \`standard\`, \`extended\`, and \`max\` values are preserved for the direct ChatGPT upstream payload.
- Image and web-search paths are out of scope: images retain \`image_upstream_model_slug\`; local web-search does not call the ChatGPT conversation upstream.

## File Structure

- Modify: \`services/config.py\` - normalize, persist, and expose the two text defaults.
- Modify: \`services/protocol/conversation.py\` - own the shared model/suffix/effort resolver and pass resolved values through \`ConversationRequest\`.
- Modify: \`services/protocol/openai_v1_chat_complete.py\` - resolve once for \`/v1/chat/completions\` and remove its duplicate effort parser.
- Modify: \`services/protocol/openai_v1_response.py\` - resolve once for \`/v1/responses\` and remove its duplicate effort parser.
- Modify: \`services/openai_backend_api.py\` - accept the new canonical upstream effort names without changing image behavior.
- Modify: \`test/test_config.py\` - test persistence and normalization of the settings.
- Modify: \`test/test_chat_completion_cache.py\` - cover both protocol surfaces, resolver precedence, suffix stripping, and cache-safe public model behavior.
- Modify: \`web/src/lib/api.ts\` - add settings API types.
- Modify: \`web/src/app/settings/store.ts\` - normalize, save, and update the two fields.
- Modify: \`web/src/app/settings/components/config-card.tsx\` - render the input and select in the existing settings grid.
- Modify: \`config.json\` - add blank default values so fresh and existing deployments have explicit, backward-compatible defaults.
- Modify: \`README.md\` - document the settings and precedence for API users.

### Task 1: Reconcile the upstream branch before feature work

**Files:**
- Modify: Git refs only; no source files.

- [ ] **Step 1: Verify the worktree and branch relationship before any merge**

Run:

\`\`\`powershell
git status --short --branch
git fetch upstream main
git rev-list --left-right --count main...upstream/main
git rev-list --left-right --count develop...main
\`\`\`

Expected: the worktree has no uncommitted changes that overlap this work; the first count reports whether local \`main\` needs the upstream update; the second reports local develop commits that will remain after the merge.

- [ ] **Step 2: Update \`main\` from the requested source and merge it into \`develop\`**

Run:

\`\`\`powershell
git switch main
git merge --ff-only upstream/main
git branch -f main-source main
git switch develop
git merge --no-ff main -m "merge: update develop from main"
\`\`\`

Expected: \`main-source\`, \`main\`, and \`upstream/main\` point to the same upstream commit; \`develop\` contains all existing local commits plus a merge commit if it was ahead. If \`main-source\` is intentionally not a tracking alias, replace \`upstream/main\` in the fast-forward command with \`main-source\` after confirming its commit matches \`upstream/main\`.

- [ ] **Step 3: Verify the merge contains no accidental source changes**

Run:

\`\`\`powershell
git diff --check main..develop
git log --oneline --decorate -12
\`\`\`

Expected: no whitespace errors; history shows the upstream merge before the feature commits.

### Task 2: Add normalized text-default settings

**Files:**
- Modify: \`services/config.py\`
- Modify: \`config.json\`
- Test: \`test/test_config.py\`

- [ ] **Step 1: Write failing configuration tests**

Add tests that construct a temporary \`ConfigStore\` and assert the following:

\`\`\`python
store = module.ConfigStore(path)
self.assertEqual(store.default_text_upstream_model_slug, "")
self.assertEqual(store.default_thinking_effort, "")

updated = store.update({
    "default_text_upstream_model_slug": "  gpt-5.4  ",
    "default_thinking_effort": " EXTENDED ",
})
self.assertEqual(updated["default_text_upstream_model_slug"], "gpt-5.4")
self.assertEqual(updated["default_thinking_effort"], "extended")

store.update({"default_thinking_effort": "unsupported"})
self.assertEqual(store.default_thinking_effort, "")
\`\`\`

- [ ] **Step 2: Run test to verify it fails**

Run: \`uv run python -m unittest test.test_config.ConfigLoadingTests.test_text_upstream_defaults_are_normalized -v\`

Expected: FAIL because \`ConfigStore\` does not yet expose the new properties.

- [ ] **Step 3: Implement the settings normalization and public output**

In \`services/config.py\`, add a shared normalizer near the existing simple configuration helpers and use it from properties, \`get()\`, and \`update()\`:

\`\`\`python
def _normalize_default_thinking_effort(value: object) -> str:
    effort = str(value or "").strip().lower()
    return effort if effort in {"standard", "extended", "max"} else ""

@property
def default_text_upstream_model_slug(self) -> str:
    return str(self.data.get("default_text_upstream_model_slug") or "").strip()

@property
def default_thinking_effort(self) -> str:
    return _normalize_default_thinking_effort(self.data.get("default_thinking_effort"))
\`\`\`

Add both normalized values to \`ConfigStore.get()\` and normalize both before assigning \`self.data\` in \`ConfigStore.update()\`. Add these backward-compatible defaults to \`config.json\`:

\`\`\`json
"default_text_upstream_model_slug": "",
"default_thinking_effort": ""
\`\`\`

- [ ] **Step 4: Run test to verify it passes**

Run: \`uv run python -m unittest test.test_config -v\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add services/config.py config.json test/test_config.py
git commit -m "feat: add text upstream defaults"
\`\`\`

### Task 3: Centralize request model and effort resolution

**Files:**
- Modify: \`services/protocol/conversation.py\`
- Modify: \`services/openai_backend_api.py\`
- Test: \`test/test_chat_completion_cache.py\`

- [ ] **Step 1: Write failing resolver tests**

Add direct unit tests for a new shared resolver:

\`\`\`python
from services.protocol.conversation import resolve_text_request_options

self.assertEqual(
    resolve_text_request_options("auto-max", {}, "gpt-5.4", "standard"),
    ("gpt-5.4", "max"),
)
self.assertEqual(
    resolve_text_request_options("gpt-5.4-extended", {"reasoning_effort": "high"}, "", "max"),
    ("gpt-5.4", "extended"),
)
self.assertEqual(
    resolve_text_request_options("auto", {"reasoning": {"effort": "none"}}, "gpt-5.4", "max"),
    ("gpt-5.4", ""),
)
\`\`\`

- [ ] **Step 2: Run test to verify it fails**

Run: \`uv run python -m unittest test.test_chat_completion_cache.ChatCompletionCacheTests.test_text_request_options_precedence -v\`

Expected: FAIL because \`resolve_text_request_options\` does not exist.

- [ ] **Step 3: Implement one resolver in \`conversation.py\`**

Define \`resolve_text_request_options(requested_model: str, body: dict[str, Any], default_model: str, default_effort: str) -> tuple[str, str]\`. It must:

\`\`\`python
suffix_efforts = {"standard", "extended", "max"}
model = (requested_model or "auto").strip() or "auto"
base, separator, suffix = model.rpartition("-")
suffix_effort = suffix.lower() if separator and base and suffix.lower() in suffix_efforts else ""
upstream_model = base if suffix_effort else model
if upstream_model.lower() == "auto":
    upstream_model = default_model or "auto"
effective_effort = suffix_effort or explicit_effort_from_body(body) or default_effort
return upstream_model, effective_effort
\`\`\`

\`explicit_effort_from_body\` must retain the existing field precedence for Chat Completions, accept the Responses \`reasoning\` object, preserve recognized old compatibility values, and distinguish an explicit \`none\` (\`""\`) from a missing value (\`None\`). Do not duplicate this logic in individual protocol modules.

Extend \`OpenAIBackendAPI._normalize_thinking_effort\` to return canonical \`standard\`, \`extended\`, and \`max\`, while retaining old aliases (\`xhigh\` maps to \`extended\`; \`low\`, \`medium\`, and \`high\` remain valid). Do not add \`thinking_effort\` to an upstream payload when the resolver returns \`""\`.

- [ ] **Step 4: Run test to verify it passes**

Run:

\`\`\`powershell
uv run python -m unittest test.test_chat_completion_cache.ChatCompletionCacheTests.test_text_request_options_precedence test.test_chat_completion_cache.ChatCompletionCacheTests.test_chat_completion_reasoning_effort_reaches_conversation_request test.test_chat_completion_cache.ChatCompletionCacheTests.test_responses_reasoning_effort_reaches_conversation_request -v
\`\`\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add services/protocol/conversation.py services/openai_backend_api.py test/test_chat_completion_cache.py
git commit -m "feat: resolve text model thinking suffixes"
\`\`\`

### Task 4: Apply resolved options to both OpenAI-compatible text APIs

**Files:**
- Modify: \`services/protocol/openai_v1_chat_complete.py\`
- Modify: \`services/protocol/openai_v1_response.py\`
- Test: \`test/test_chat_completion_cache.py\`

- [ ] **Step 1: Write failing endpoint-level propagation tests**

Add one Chat Completions test and one Responses test that patch the outbound text function and assert the captured request is \`model == "gpt-5.4"\` and \`thinking_effort == "max"\` for input model \`"auto-max"\` with settings defaults \`"gpt-5.4"\` and \`"standard"\`. Also assert the returned response still exposes \`"auto-max"\` as its \`model\`.

- [ ] **Step 2: Run test to verify it fails**

Run:

\`\`\`powershell
uv run python -m unittest test.test_chat_completion_cache.ChatCompletionCacheTests.test_chat_completion_model_suffix_resolves_upstream_options test.test_chat_completion_cache.ChatCompletionCacheTests.test_responses_model_suffix_resolves_upstream_options -v
\`\`\`

Expected: FAIL because each endpoint currently passes the raw request model and parses effort independently.

- [ ] **Step 3: Replace duplicate parsing with the resolver**

In both protocol modules, retain \`requested_model\` for response construction and cache input, then create the outbound \`ConversationRequest\` from:

\`\`\`python
upstream_model, thinking_effort = resolve_text_request_options(
    requested_model,
    body,
    config.default_text_upstream_model_slug,
    config.default_thinking_effort,
)
request = ConversationRequest(model=upstream_model, messages=messages, thinking_effort=thinking_effort)
\`\`\`

Pass resolved values through both streaming and non-streaming paths. Remove the local \`normalize_thinking_effort\` and \`thinking_effort_from_body\` copies only after their existing behavior is covered by the shared resolver. Keep web-search and image branches unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run:

\`\`\`powershell
uv run python -m unittest test.test_chat_completion_cache test.test_v1_chat_completions test.test_v1_responses -v
\`\`\`

Expected: PASS.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add services/protocol/openai_v1_chat_complete.py services/protocol/openai_v1_response.py test/test_chat_completion_cache.py
git commit -m "feat: apply text defaults to OpenAI APIs"
\`\`\`

### Task 5: Expose the defaults in settings UI and documentation

**Files:**
- Modify: \`web/src/lib/api.ts\`
- Modify: \`web/src/app/settings/store.ts\`
- Modify: \`web/src/app/settings/components/config-card.tsx\`
- Modify: \`README.md\`

- [ ] **Step 1: Add settings API and Zustand types**

Extend \`SettingsConfig\` and \`normalizeConfig\` with:

\`\`\`ts
default_text_upstream_model_slug?: string;
default_thinking_effort?: "" | "standard" | "extended" | "max";
\`\`\`

Ensure \`saveConfig\` trims the model field and permits only \`""\`, \`"standard"\`, \`"extended"\`, and \`"max"\` for the effort. Add \`setDefaultTextUpstreamModelSlug(value: string)\` and \`setDefaultThinkingEffort(value: "" | "standard" | "extended" | "max")\` actions following the existing image-model setter pattern.

- [ ] **Step 2: Add the two existing-style controls to \`ConfigCard\`**

Add a text input labelled \`默认文本上游模型\` with placeholder \`gpt-5.4\`, then a \`Select\` labelled \`默认思考强度\` with values \`default\` (stored as \`""\`), \`standard\`, \`extended\`, and \`max\`. Place them near the existing image upstream model input and use the same \`space-y-2\` grid item styling.

- [ ] **Step 3: Document exact routing behavior**

Add a short README configuration table and examples:

\`\`\`text
model=auto                  -> configured default text upstream model + configured effort
model=auto-extended         -> configured default text upstream model + extended
model=gpt-5.4-max           -> gpt-5.4 + max
reasoning_effort=high       -> explicit request value unless the model has a recognized suffix
\`\`\`

State that the suffix is removed before calling the upstream but retained in the OpenAI-compatible response model field.

- [ ] **Step 4: Run frontend static checks**

Run:

\`\`\`powershell
Set-Location web
bun run lint
bun run build
\`\`\`

Expected: PASS with no TypeScript or lint errors.

- [ ] **Step 5: Commit**

\`\`\`powershell
git add web/src/lib/api.ts web/src/app/settings/store.ts web/src/app/settings/components/config-card.tsx README.md
git commit -m "feat: configure default text thinking"
\`\`\`

### Task 6: Run full verification and inspect the final diff

**Files:**
- Test: \`test/\`

- [ ] **Step 1: Run the full Python unit suite**

Run: \`uv run python -m unittest discover -s test -p "test_*.py" -v\`

Expected: PASS. Any scripts requiring live upstream accounts remain outside this unit-test invocation.

- [ ] **Step 2: Inspect the final changes and branch state**

Run:

\`\`\`powershell
git diff --check main..develop
git status --short --branch
git log --oneline --decorate main..develop
\`\`\`

Expected: no whitespace errors, a clean worktree, and only the planned merge plus feature commits ahead of \`main\`.

- [ ] **Step 3: Commit only source corrections found by verification**

Use the same file-specific commit pattern as Tasks 2-5; do not create a commit when verification requires no correction.
