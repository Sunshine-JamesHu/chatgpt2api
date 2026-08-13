# OAuth Import Dialog Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the OAuth account import dialog while preserving its authorization and proxy behavior.

**Architecture:** Modify the existing React import dialog only. Rename the OAuth start action, hide the instructional and one-time-code warning panels, and place the return action above the account proxy selector.

**Tech Stack:** Next.js, React, TypeScript, existing account import dialog components.

---

### Task 1: Update OAuth import dialog presentation

**Files:**
- Modify: `web/src/app/accounts/components/account-import-dialog.tsx`

- [ ] Rename the OAuth start button from opening the authorization page to generating an authorization link.
- [ ] Remove the visible operation-step guide and the callback/code warning text.
- [ ] Render the return-to-import-method action before the account proxy selector.
- [ ] Keep all existing callbacks, session state, proxy selection, and finish flow unchanged.

### Task 2: Verify the UI build and focused behavior

**Files:**
- Test: `web/src/app/accounts/components/account-import-dialog.tsx`

- [ ] Run the frontend build from `web` with `npm run build`.
- [ ] Inspect the dialog source to confirm the requested labels and ordering, with no remaining visible instruction/warning copy.
