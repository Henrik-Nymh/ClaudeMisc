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

- _(none yet)_
