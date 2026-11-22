# Session log

Newest first. One entry per session where something non-trivial happened:
date, what was done, what's left.

## 2026-11-22 (later): headless PoB

- Added headless Path of Building (`setup-pob.sh`, `poe1/pob_driver.lua`,
  `pobcalc.py`, `whatif.py`) and the `calc`, `try`, `gems`, `tree` commands, plus
  `trade item --live --calc`. Verified against the owner's build: 41/41 stats match.
- The owner plays Hierophant mana-stacking Shock Nova of Procession (Covens) and
  is following a poe.ninja character (PoB code received, kept in scratch only).
- Key finding: the owner's PoB config is nearly empty (no power charges, shock, etc.),
  so DPS reads 5.5M vs 30M with the reference's config. Always compare with the
  same config. Biggest gaps: Svalinn + block nodes (EHP), Ravenous Passion and
  Greater Spell Echo (DPS).
- Next: add a `compare --calc` that recalculates both builds with one config.

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
