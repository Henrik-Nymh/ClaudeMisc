# Session log

Newest first. One entry per session where something non-trivial happened:
date, what was done, what's left.

## 2026-11-25 (later): Ravenous Passion in

- The owner bought Ravenous Passion with +1 PC (+47 Str, 10 Rage) and respecced Might to
  Faith and Steel. With the reference config: DPS 27.4M -> 35.6M, EHP 112k -> 107k, res capped,
  chaos 55. Since the start: DPS 30.0M -> 35.6M, EHP 33.6k -> 106.9k.
- The owner must set Rage = 30 in the PoB config, or PoB shows no gain from RP.
- Next: tree points (Annihilation +11%, Arcane Guarding +16% EHP, Heart of Thunder,
  Heart and Soul). The reference's belt and gloves are now downgrades (resistances).

## 2026-11-25: helmet options, config

- Unique helmet scan with an added "+1 to Maximum Power Charges" implicit (new driver
  option). Corrupted PC helmets available to the owner: Memory Vault 0.1 div (+9% DPS,
  +4% EHP); Ravenous Passion ~14 div (+30% DPS, or +38% if its Str lets Might go).
- The owner respecced Faith and Steel to the mana node (+6.3% DPS) and started filling
  in the PoB config. Biggest missing toggles: intensifyIntensity 4 (+64% DPS),
  Focused (+12%), Enemy Unnerved (+10%), Enemy Shocked (+5%).

## 2026-11-24 (later): Red Nightmare in

- The owner added a Foulborn The Red Nightmare in socket 26196 (+26% EHP; it beats the
  regular version thanks to its chaos-res mutation) and took Might for Str (needed:
  93 Str without it vs 108 required). With the reference config: EHP 112k, block 75/71, chaos 75.
- The owner dropped "Mana and Arcane Surge Effect" for Might, costing -6% DPS. Suggested
  respecing Faith and Steel (-0.9% EHP) to take it back. Attack block is capped, so the
  focus is now DPS: Ravenous Passion with +1 power charge (+30%).

## 2026-11-24: shield bought, next steps

- Owner bought the rare shield (Armageddon Bastion) and took Sanctuary, Safeguard
  and the block masteries: EHP 32k -> 79k, block 61/68 (with the reference config).
- Next by PoB value: Ravenous Passion with +1 max power charge (+30% DPS); The Red
  Nightmare in the empty socket 26196 (+20% EHP, 0 points); Arcane Guarding (3p, +17% EHP).
  Svalinn is now only +11% EHP, so it's no longer worth it.
- The owner's PoB config is still empty; they should fill it in.

## 2026-11-23: shield shopping (6 div budget)

- Added `trade best` (PoB-weighted search per slot), `try --unique/--nodes`,
  `tree --nodes`. Prices come from poe.ninja's public economy API.
- Shield findings (ref config, with Sanctuary + Safeguard): Chalice of Horrors 1c
  +49% EHP; Dawnbreaker 3c +71% EHP, but it needs 159 Str (the Might node fixes
  that); Svalinn 30 div +130%; a good rare Titanium Spirit Shield is about +58% EHP
  with no DPS loss. All the unique options cost ~15% DPS (Ordered Fate).
- Left: live trade still needs the owner's machine (no Remote Control folder yet).

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
