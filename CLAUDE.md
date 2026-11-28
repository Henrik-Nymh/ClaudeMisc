# CLAUDE.md

This repo is Claude's own workspace: a place for small projects, experiments,
utilities and notes that should outlive a single session. Cloud sessions run in
ephemeral containers, so **anything not committed and pushed is lost**.

The repo is **public**. Never commit secrets, tokens, or personal details about
the owner or anyone else.

## Layout

```
projects/<name>/   self-contained projects, one folder each (kebab-case)
tools/             reusable helper scripts for working in this repo
notes/log.md       session log, newest entry first
CLAUDE.md          this file: conventions + durable lessons (auto-loaded)
scratch/           local throwaway space, gitignored
```

## Working here

- **Starting a session:** if the task continues earlier work, skim the top of
  `notes/log.md` first. Otherwise just get going.
- **New project:** `tools/new-project.sh <kebab-name>` creates
  `projects/<name>/README.md` from a template. Fill in What / Run / Status.
- **Self-contained projects:** no imports across project folders. Each project
  owns its dependency file (`requirements.txt`, `package.json`, ...) with
  pinned versions. Prefer the standard library when it does the job.
- **Status line:** keep the `**Status:**` line in each project README honest
  (`in progress`, `done`, `abandoned`, ...) so the repo stays scannable.
- **Ending a session** where something non-trivial happened: add a short entry
  at the top of `notes/log.md` (date, what was done, what's left), then commit
  and push.

## Language

- Talk to the owner in Norwegian (bokmål).
- `README.md` (the owner's front page) is in Norwegian.
- Code, comments, commit messages and project docs are in English.

## Git

- Small, focused commits with imperative subject lines ("Add X", "Fix Y").
- Push before the session ends; the container will not wait.

## Lessons learned

Durable facts worth knowing in every future session go here (environment
quirks, gotchas, decisions and why). Keep each one to a line or two.

- Cloud sessions use the personal "ClaudeMisc" environment, which allows
  www.pathofexile.com, poe.ninja, pobb.in and a few other hosts (check get_environment).
  GitHub (incl. raw) is always reachable.
- pathofexile.com APIs (trade, character-window) return 403 from cloud IPs.
  Don't probe repeatedly: GGG restricts clients with many 4xx responses. Live
  trade has to run on the owner's machine.
- poe.ninja: the public API lives under `/poe1/api/...` (the old `/api/data/...`
  paths return 404). HTML pages sit behind a Cloudflare JS challenge. Builds,
  profile and character endpoints are internal per its docs, so don't call them.
- Auto mode refuses spoofing a browser User-Agent, and refuses running
  downloaded third-party code (e.g. PoB's Lua) without the owner's OK. Ask, don't work around it.
- Path of Building's repo is the best machine-readable PoE1 data source (tree,
  trade stats, mods, gems as Lua tables). `poe1/luadata.py` parses them safely.
- Headless PoB works (the owner approved running it): `projects/poe1-build-helper/setup-pob.sh`,
  then `python3 -m poe1 calc|try|gems|tree`. Stock LuaJIT needs our driver's fixes
  (compound `+=` rewrite, FFI zlib Inflate). Construct objects as `new("Item"):Item(text)`.
- PoB numbers depend heavily on each build's Config tab. Before comparing builds
  or judging gem swaps, check the config (e.g. `usePowerCharges`). Swap one build's
  `<Config>` into the other for a fair comparison.
- poe.ninja's Divine `chaosEquivalent` can lag the in-game Currency Exchange
  (148 vs 174 on 2026-11-24). Ask the owner for the current rate before converting
  their currency. For item prices, use poe.ninja's own `divineValue`.
- The owner's Outlook can be reachable through the Microsoft 365 connector. `read_resource` on a
  PDF attachment returns extracted text only, not the original file.
- Headless Playwright handles JavaScript-only public sites. Its `page.request` ignores the egress
  proxy (DNS fails), so download files with an in-page `fetch` instead.
