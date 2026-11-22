"""Compare two builds (e.g. yours vs. a ladder character using the same skill)."""

from __future__ import annotations

import urllib.parse

from .build import Build
from .summary import _fmt, tree_breakdown

COMPARE_STATS = [
    ("CombinedDPS", "Combined DPS"), ("FullDPS", "Full DPS"), ("TotalDotDPS", "DoT DPS"),
    ("TotalEHP", "EHP"), ("Life", "Life"), ("EnergyShield", "ES"), ("Mana", "Mana"),
    ("Ward", "Ward"), ("Armour", "Armour"), ("Evasion", "Evasion"),
    ("EffectiveBlockChance", "Block %"), ("EffectiveSpellBlockChance", "Spell block %"),
    ("EffectiveSpellSuppressionChance", "Suppress %"),
    ("FireResist", "Fire res"), ("ColdResist", "Cold res"), ("LightningResist", "Light res"),
    ("ChaosResist", "Chaos res"), ("PhysicalMaximumHitTaken", "Max phys hit"),
    ("FireMaximumHitTaken", "Max fire hit"), ("ColdMaximumHitTaken", "Max cold hit"),
    ("LightningMaximumHitTaken", "Max light hit"), ("ChaosMaximumHitTaken", "Max chaos hit"),
    ("EffectiveMovementSpeedMod", "Move speed x"),
]


def main_skill_name(b: Build) -> str | None:
    g = b.main_skill
    if not g or not g.active_gems:
        return None
    return g.active_gems[min(max(g.main_active, 1), len(g.active_gems)) - 1].name


def _label(b: Build) -> str:
    asc = b.ascendancy if b.ascendancy not in ("", "None") else b.class_name
    return f"{asc} {b.level}, {main_skill_name(b) or '?'}"


def _diff(a: set[str], b: set[str], label_a: str, label_b: str) -> list[str]:
    out = []
    if b - a:
        out.append(f"- Only {label_b}: " + ", ".join(sorted(b - a)))
    if a - b:
        out.append(f"- Only {label_a}: " + ", ".join(sorted(a - b)))
    if not out:
        out.append("- Same")
    return out


def _gem_names(b: Build, main_only: bool) -> set[str]:
    groups = [b.main_skill] if main_only else b.skills
    return {g.name for grp in groups if grp and grp.enabled for g in grp.gems if g.enabled}


def _uniques(b: Build) -> set[str]:
    return {item.name for _, item in b.equipped() if item.rarity in ("UNIQUE", "RELIC")}


def render(a: Build, b: Build, tree_a: dict | None, tree_b: dict | None, *, mods: bool = False) -> str:
    la, lb = "A", "B"
    out = [f"# Compare  A: {_label(a)}  vs  B: {_label(b)}", ""]
    out.append("## Stats (A -> B; PoB values, depend on each build's config)")
    for key, name in COMPARE_STATS:
        va, vb = a.stats.get(key, 0) or 0, b.stats.get(key, 0) or 0
        if not va and not vb:
            continue
        pct = f" ({(vb - va) / abs(va) * 100:+.0f}%)" if va else ""
        out.append(f"- {name}: {_fmt(va)} -> {_fmt(vb)}{pct}")

    out += ["", "## Main skill links"]
    for lab, bb in ((la, a), (lb, b)):
        g = bb.main_skill
        gems = ", ".join(f"{x.name} {x.level}/{x.quality}" for x in g.gems if x.enabled) if g else "-"
        out.append(f"- {lab} [{g.slot if g else '-'}]: {gems}")
    out += _diff(_gem_names(a, True), _gem_names(b, True), la, lb)

    out += ["", "## All other gems (auras, utility, other links)"]
    out += _diff(_gem_names(a, False) - _gem_names(a, True), _gem_names(b, False) - _gem_names(b, True), la, lb)

    out += ["", "## Gear by slot"]
    ea, eb = dict(a.equipped()), dict(b.equipped())
    for slot in [s for s, _ in b.equipped() if not s.startswith("Jewel")] + \
                [s for s, _ in a.equipped() if not s.startswith("Jewel") and s not in eb]:
        ia, ib = ea.get(slot), eb.get(slot)
        ta, tb = (ia.title if ia else "-"), (ib.title if ib else "-")
        same = ia and ib and ia.rarity == ib.rarity and (ia.base == ib.base if ia.rarity == "RARE" else ia.name == ib.name)
        out.append(f"- **{slot}**: {ta}  |  {tb}" + ("  (same)" if same else ""))
        if mods and ib and not same:
            out += [f"    - {lb}: {m.text}" for m in ib.implicits + ib.explicits]
    out.append("")
    out.append("Uniques anywhere (incl. jewels/flasks):")
    out += _diff(_uniques(a), _uniques(b), la, lb)

    out += ["", "## Passive tree"]
    if a.tree and b.tree and tree_a and tree_b:
        ba, bb_ = tree_breakdown(a.tree, tree_a), tree_breakdown(b.tree, tree_b)
        ca, cb = ba["counts"], bb_["counts"]
        out.append(f"- Points: {ca['passive']}+{ca['asc']} asc -> {cb['passive']}+{cb['asc']} asc")
        for key, title in (("asc", "Ascendancy"), ("keystone", "Keystones"), ("notable", "Notables"), ("mastery", "Masteries")):
            out.append(f"{title}:")
            out += ["  " + line for line in _diff(set(ba["groups"][key]), set(bb_["groups"][key]), la, lb)]
    else:
        out.append("- (tree data missing for one of the builds)")
    return "\n".join(out)


def ninja_league_slug(league: str) -> str:
    low = league.strip().lower()
    if low in ("standard", "hardcore"):
        return low
    if low.startswith("hardcore "):
        return low[len("hardcore "):].replace(" ", "") + "hc"
    return low.replace(" ", "")


def ninja_builds_url(league: str, skill: str | None = None, ascendancy: str | None = None) -> str:
    """Link to poe.ninja's builds page for a league, filtered by skill/class.

    The filter parameter names are a best guess (the site can't be fetched
    automatically to verify); the league page itself is reliable.
    """
    params = {}
    if ascendancy:
        params["class"] = ascendancy
    if skill:
        params["skills"] = skill
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    return f"https://poe.ninja/poe1/builds/{ninja_league_slug(league)}{qs}"
