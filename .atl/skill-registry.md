# Skill Registry

**Delegator use only.** Any agent that launches sub-agents reads this registry to resolve compact rules, then injects them directly into sub-agent prompts. Sub-agents do NOT read this registry or individual SKILL.md files.

See `_shared/skill-resolver.md` for the full resolution protocol.

## User Skills

| Trigger | Skill | Path |
|---------|-------|------|
| libraries, frameworks, API references, code examples | context7-mcp | /home/luismolina/.claude/skills/context7-mcp/SKILL.md |
| creating a GitHub issue, reporting a bug, requesting a feature | issue-creation | /home/luismolina/.config/opencode/skills/issue-creation/SKILL.md |
| creating a pull request, opening a PR, preparing changes for review | branch-pr | /home/luismolina/.config/opencode/skills/branch-pr/SKILL.md |
| create a new skill, add agent instructions, document patterns for AI | skill-creator | /home/luismolina/.config/opencode/skills/skill-creator/SKILL.md |
| writing Go tests, using teatest, adding test coverage | go-testing | /home/luismolina/.config/opencode/skills/go-testing/SKILL.md |
| "judgment day", "review adversarial", "dual review", "juzgar", "que lo juzguen" | judgment-day | /home/luismolina/.config/opencode/skills/judgment-day/SKILL.md |
| "review my UI", "check accessibility", "audit design", "review UX", "check my site against best practices" | web-design-guidelines | /home/luismolina/.agents/skills/web-design-guidelines/SKILL.md |
| build web components, pages, artifacts, posters, applications, styling/beautifying any web UI | frontend-design | /home/luismolina/.agents/skills/frontend-design/SKILL.md |
| writing, reviewing, or refactoring React/Next.js code, data fetching, bundle optimization, performance improvements | vercel-react-best-practices | /home/luismolina/.agents/skills/vercel-react-best-practices/SKILL.md |
| "caveman mode", "talk like caveman", "use caveman", "less tokens", "be brief", /caveman | caveman | /home/luismolina/.agents/skills/caveman/SKILL.md |
| "how do I do X", "find a skill for X", "is there a skill that can..." | find-skills | /home/luismolina/.agents/skills/find-skills/SKILL.md |

## Compact Rules

Pre-digested rules per skill. Delegators copy matching blocks into sub-agent prompts as `## Project Standards (auto-resolved)`.

### context7-mcp
- Always resolve library ID with `resolve-library-id` before querying docs
- Pass user's full question as `query` to both resolve and query steps for best relevance
- Prefer official/primary packages over community forks when multiple matches exist
- Use version-specific library IDs when user mentions versions (e.g., "React 19")
- Incorporate fetched docs + code examples into responses; cite versions when relevant

### issue-creation
- Blank issues are disabled — MUST use bug report or feature request template
- Every issue gets `status:needs-review` automatically on creation
- A maintainer MUST add `status:approved` before any PR can be opened
- Questions go to Discussions, NOT issues
- Search existing issues for duplicates before creating
- Auto-labels: Bug Report → `bug`, `status:needs-review`; Feature Request → `enhancement`, `status:needs-review`

### branch-pr
- Every PR MUST link an approved issue — no exceptions
- Every PR MUST have exactly one `type:*` label
- Branch naming regex: `^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)/[a-z0-9._-]+$`
- PR body MUST contain: linked issue (`Closes/Fixes/Resolves #N`), exactly one type checkbox, summary, changes table, test plan, contributor checklist
- Commit messages MUST match conventional commits regex: `^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(...)?!?: .+`
- Automated checks must pass before merge

### skill-creator
- Create skill only for reusable patterns, not one-offs or trivial tasks
- Skill structure: `skills/{name}/SKILL.md` + optional `assets/` + optional `references/`
- Frontmatter required: name, description (with Trigger), license (Apache-2.0), metadata.author, metadata.version
- references/ points to LOCAL files only, not web URLs
- After creating, add to `AGENTS.md`
- Naming: generic `{technology}`, project-specific `{project}-{component}`, testing `{project}-test-{component}`

### go-testing
- Pure functions → table-driven tests with `tests := []struct{...}` and `t.Run(tt.name, ...)`
- Bubbletea TUI → test `Model.Update()` directly for state changes; use `teatest.NewTestModel()` for full flows
- Golden file testing → compare `m.View()` against `testdata/*.golden`; use `-update` flag to refresh
- Mock system info by injecting `&system.SystemInfo{...}` into model before testing
- File organization: pair `model.go` with `model_test.go`; keep `testdata/` adjacent
- Commands: `go test ./...`, `go test -cover ./...`, `go test -update ./...`, `go test -short ./...`

### judgment-day
- Resolve skills BEFORE launching judges — read `.atl/skill-registry.md` → match by code context + task context → inject compact rules into ALL judge/fix prompts
- Launch TWO judges via `delegate` in PARALLEL — never sequential, never review yourself
- Synthesize verdicts: Confirmed (both) → fix immediately; Suspect (one only) → triage; Contradiction → flag manually
- WARNING classification: "Can a normal user trigger this?" YES → real (fix); NO → theoretical (INFO only)
- Fix Agent is separate delegation; after fixes → re-launch both judges in parallel
- After 2 fix iterations, ASK user before continuing; never escalate automatically
- MUST NOT declare APPROVED until Round 1 clean OR Round 2 with 0 CRITICAL + 0 real WARNING
- MUST NOT git commit/push until re-judgment completes

### web-design-guidelines
- Fetch fresh guidelines before each review from `https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md`
- Read specified files, check against all fetched rules
- Output findings in terse `file:line` format
- If no files specified, ask user which files to review

### frontend-design
- Commit to a BOLD aesthetic direction before coding (minimal, maximalist, retro-futuristic, etc.)
- Typography: avoid generic fonts (Arial, Inter, Roboto); choose distinctive, characterful fonts
- Color: dominant colors with sharp accents; use CSS variables for consistency
- Motion: prioritize CSS-only animations; use one well-orchestrated page load with staggered reveals
- Spatial: unexpected layouts, asymmetry, overlap, diagonal flow, grid-breaking elements
- Backgrounds: gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows
- NEVER use generic AI aesthetics (purple gradients on white, predictable layouts, cookie-cutter components)
- Match implementation complexity to aesthetic vision

### vercel-react-best-practices
- Eliminate waterfalls: check cheap sync conditions before await, use Promise.all() for independent ops, start promises early and await late
- Bundle: avoid barrel imports, use `next/dynamic` for heavy components, defer third-party scripts after hydration
- Server: authenticate server actions, use React.cache() for dedup, avoid module-level mutable request state in RSC
- Client: use SWR for dedup, passive listeners for scroll, version localStorage schema
- Re-render: extract expensive work into memoized components, derive state during render not effects, use refs for transient values
- Rendering: animate div wrapper not SVG, use `content-visibility` for long lists, hoist static JSX outside components
- JS perf: group CSS changes via classes, build Map for repeated lookups, combine multiple filter/map into one loop

### caveman
- Drop articles, filler, pleasantries, hedging. Fragments OK. Short synonyms.
- Default intensity: **full**. Switch: `/caveman lite|full|ultra|wenyan-lite|wenyan-full|wenyan-ultra`
- Pattern: `[thing] [action] [reason]. [next step].`
- Drop caveman for: security warnings, irreversible actions, multi-step sequences where fragments risk misread
- Code/commits/PRs: write normal. "stop caveman" or "normal mode" reverts.
- Persistence: ACTIVE EVERY RESPONSE until explicit stop.

### find-skills
- Use when user asks "how do I do X", "find a skill for X", "is there a skill that can..."
- Key commands: `npx skills find [query]`, `npx skills add <package>`, `npx skills check`, `npx skills update`
- Verify quality before recommending: prefer 1K+ installs, official sources, repos with 100+ stars
- If no skill found, offer direct help + suggest `npx skills init` for custom skill

## Project Conventions

| File | Path | Notes |
|------|------|-------|

No project convention files found (no `agents.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `GEMINI.md`, or `copilot-instructions.md`).

Read the convention files listed above for project-specific patterns and rules. All referenced paths have been extracted — no need to read index files to discover more.
