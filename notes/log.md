# Session log

Newest first. One entry per session where something non-trivial happened:
date, what was done, what's left.

## 2026-11-22: poe1-build-helper

- Built `projects/poe1-build-helper`: PoB code decode/summary, trade queries and
  links (from an equipped item or explicit filters, optional `--live` search),
  `compare` for two builds, `similar` for poe.ninja links. 19 offline tests.
- Game data comes from PoB's repo (Lua tables parsed as data, cached in `.cache/`).
- Current league: Covens (tree 3_30).
- Left: the owner's actual build (waiting for a pobb.in link); verify the
  poe.ninja filter URL params; `--live` is untested (needs the owner's machine);
  headless PoB for exact DPS deltas needs the owner's OK to run downloaded PoB code.

## 2026-11-22: Repo set up

- Created the initial structure: `projects/`, `tools/`, `notes/`, `CLAUDE.md`,
  `README.md`, plus `.gitignore`, `.gitattributes` and `.editorconfig`.
- Added `tools/new-project.sh` for scaffolding project folders.
- Next: no projects yet. Pick something to build.
