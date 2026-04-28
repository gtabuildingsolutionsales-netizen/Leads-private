# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository status

This repository is currently **empty** — it has no source files, no commits on any branch, and no default branch on the remote (`gtabuildingsolutionsales-netizen/Leads-private`). There is no README, no build system, no language toolchain, and no test framework yet.

When code is added, this file should be updated to document:

- Build, lint, test, and run commands (including how to run a single test)
- The high-level architecture that spans multiple files
- Project-specific conventions that aren't obvious from reading individual files
- Any important content from a future README, `.cursor/rules/`, `.cursorrules`, or `.github/copilot-instructions.md`

Until then, treat any architectural claim as unverified — there is nothing to read.

## Branch convention

Per the task harness configuration for this repo, development work should happen on a dedicated `claude/...` branch (e.g. `claude/add-claude-documentation-3bdR0`) and be pushed with `git push -u origin <branch-name>`. Do not push to a different branch without explicit permission, and do not open a pull request unless the user asks for one.
