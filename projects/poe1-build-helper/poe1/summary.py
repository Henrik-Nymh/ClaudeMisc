"""Render a Build as compact, readable text (made for both humans and Claude)."""

from __future__ import annotations

from .build import Build, Item

# (label, stat keys) rows; a row is printed when any of its stats exist.
_STAT_ROWS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Damage", [
        ("CombinedDPS", "Combined DPS"), ("FullDPS", "Full DPS"), ("TotalDPS", "Hit DPS"),
        ("TotalDotDPS", "DoT DPS"), ("AverageHit", "Avg hit"), ("Speed", "Speed /s"),
        ("CritChance", "Crit %"), ("CritMultiplier", "Crit multi"), ("HitChance", "Hit %"),
    ]),
    ("Pools", [
        ("Life", "Life"), ("LifeUnreserved", "Unreserved"), ("EnergyShield", "ES"),
        ("Ward", "Ward"), ("Mana", "Mana"), ("ManaUnreserved", "Mana unreserved"),
        ("TotalEHP", "EHP"),
    ]),
    ("Resists", [
        ("FireResist", "Fire"), ("ColdResist", "Cold"), ("LightningResist", "Light"),
        ("ChaosResist", "Chaos"), ("FireResistOverCap", "Fire over"),
        ("ColdResistOverCap", "Cold over"), ("LightningResistOverCap", "Light over"),
    ]),
    ("Defence", [
        ("Armour", "Armour"), ("PhysicalDamageReduction", "Phys DR %"), ("Evasion", "Evasion"),
        ("MeleeEvadeChance", "Evade %"), ("EffectiveBlockChance", "Block %"),
        ("EffectiveSpellBlockChance", "Spell block %"),
        ("EffectiveSpellSuppressionChance", "Suppress %"),
    ]),
    ("Max hit", [
        ("PhysicalMaximumHitTaken", "Phys"), ("FireMaximumHitTaken", "Fire"),
        ("ColdMaximumHitTaken", "Cold"), ("LightningMaximumHitTaken", "Light"),
        ("ChaosMaximumHitTaken", "Chaos"),
    ]),
    ("Recovery", [
        ("NetLifeRegen", "Net life regen"), ("LifeLeechGainRate", "Life leech /s"),
        ("EnergyShieldRegenRecovery", "ES regen"), ("NetManaRegen", "Net mana regen"),
    ]),
    ("Attributes", [
        ("Str", "Str"), ("ReqStr", "req"), ("Dex", "Dex"), ("ReqDex", "req"),
        ("Int", "Int"), ("ReqInt", "req"),
    ]),
    ("Misc", [("EffectiveMovementSpeedMod", "Move speed x"), ("ManaCost", "Mana cost")]),
]


def _fmt(v: float) -> str:
    if isinstance(v, float) and not v.is_integer():
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:.2f}".rstrip("0").rstrip(".")
    v = int(v)
    if abs(v) >= 10_000_000:
        return f"{v / 1_000_000:.1f}M"
    return f"{v:,}"


def _stat_lines(stats: dict[str, float], all_stats: bool) -> list[str]:
    out, shown = [], set()
    for label, keys in _STAT_ROWS:
        parts = [f"{name} {_fmt(stats[k])}" for k, name in keys if k in stats and stats[k] not in (0, None)]
        shown.update(k for k, _ in keys)
        if parts:
            out.append(f"- {label}: " + " · ".join(parts))
    if all_stats:
        rest = [f"{k}={_fmt(v)}" for k, v in sorted(stats.items()) if k not in shown and v]
        if rest:
            out.append("- Other: " + ", ".join(rest))
    return out


def _item_lines(slot: str, item: Item, show_mods: bool) -> list[str]:
    bits = [item.rarity.title()]
    ilvl, q = item.prop_int("Item Level"), item.prop_int("Quality")
    if ilvl:
        bits.append(f"ilvl {ilvl}")
    if q:
        bits.append(f"Q{q}")
    if item.props.get("Sockets"):
        bits.append(str(item.props["Sockets"]))
    bits += item.influences + item.flags
    lines = [f"- **{slot}**: {item.title} ({', '.join(bits)})"]
    if show_mods:
        for m in item.implicits:
            lines.append(f"    - impl: {m.text}" + (f" [{', '.join(m.tags)}]" if m.tags else ""))
        for m in item.explicits:
            lines.append(f"    - {m.text}" + (f" [{', '.join(m.tags)}]" if m.tags else ""))
    return lines


def tree_breakdown(spec, tree_data: dict, verbose: bool = False) -> dict:
    """Classify allocated nodes: keystones, notables, ascendancy notables, masteries, counts."""
    nodes = tree_data["nodes"]
    groups: dict = {k: [] for k in ("keystone", "notable", "asc", "mastery", "jewel")}
    counts = {"passive": 0, "asc": 0, "cluster": 0, "unknown": 0}
    for nid in spec.nodes:
        n = nodes.get(str(nid))
        if n is None:
            counts["cluster" if nid > 65535 else "unknown"] += 1
            continue
        kind = n["kind"]
        if kind in ("class-start", "ascendancy-start"):
            continue
        if n.get("ascendancy"):
            counts["asc"] += 1
            if kind == "notable":
                groups["asc"].append(n["name"])
            continue
        counts["passive"] += 1
        if kind in ("keystone", "notable"):
            groups[kind].append(n["name"] + (f" ({'; '.join(n['stats'])})" if verbose else ""))
        elif kind == "mastery":
            effect = spec.masteries.get(nid)
            stats = n.get("effects", {}).get(str(effect), []) if effect is not None else []
            groups["mastery"].append(f"{n['name']}: {'; '.join(stats) or '?'}")
        elif kind == "jewel":
            groups["jewel"].append(str(nid))
    return {"groups": groups, "counts": counts}


def _tree_lines(build: Build, tree_data: dict | None, verbose: bool) -> list[str]:
    spec = build.tree
    if not spec:
        return ["- (no passive tree)"]
    head = f"- Version {spec.version or '?'}" + (f", spec \"{spec.title}\"" if spec.title else "")
    head += f" ({len(build.trees)} specs in build)" if len(build.trees) > 1 else ""
    lines = [head]
    if not tree_data:
        lines.append(f"- {len(spec.nodes)} allocated node ids (tree data not loaded)")
        return lines
    tb = tree_breakdown(spec, tree_data, verbose)
    groups, c = tb["groups"], tb["counts"]
    lines.append(f"- Points: {c['passive']} passive + {c['asc']} ascendancy"
                 + (f" + {c['cluster']} cluster-jewel nodes" if c["cluster"] else ""))
    if c["unknown"]:
        lines.append(f"- {c['unknown']} node ids not found in tree {tree_data['version']} (version mismatch?)")
    if groups["asc"]:
        lines.append("- Ascendancy: " + ", ".join(groups["asc"]))
    if groups["keystone"]:
        lines.append("- Keystones: " + ", ".join(groups["keystone"]))
    if groups["notable"]:
        lines.append(f"- Notables ({len(groups['notable'])}): " + ", ".join(sorted(groups["notable"])))
    if groups["mastery"]:
        lines.append("- Masteries:")
        lines += [f"    - {m}" for m in groups["mastery"]]
    if groups["jewel"]:
        lines.append(f"- Jewel sockets allocated: {len(groups['jewel'])}")
    return lines


def render(build: Build, tree_data: dict | None = None, *, mods: bool = True,
           all_stats: bool = False, verbose_tree: bool = False, notes: bool = False) -> str:
    asc = build.ascendancy if build.ascendancy not in ("", "None") else build.class_name
    out = [f"# {asc} ({build.class_name}), level {build.level}"]
    main = build.main_skill
    if main and main.active_gems:
        idx = min(max(main.main_active, 1), len(main.active_gems)) - 1
        out.append(f"Main skill: **{main.active_gems[idx].name}** ({main.slot or main.label or 'no slot'})")
    pantheon = " / ".join(p for p in (build.pantheon_major, build.pantheon_minor) if p and p != "None")
    out.append(f"Bandit: {build.bandit} · Pantheon: {pantheon or 'none'}")

    out += ["", "## Stats (as computed by PoB at export)"]
    out += _stat_lines(build.stats, all_stats) or ["- (no stats in export)"]
    if build.minion_stats:
        out += ["", "## Minion stats"]
        out += _stat_lines(build.minion_stats, all_stats) or ["- (none)"]

    out += ["", "## Skills"]
    for n, g in enumerate(build.skills, start=1):
        if not g.gems:
            continue
        gems = ", ".join(
            f"{x.name} {x.level}/{x.quality}" + ("" if x.enabled else " (off)")
            + (f" [{x.quality_id}]" if x.quality_id not in ("Default", "") else "")
            for x in g.gems
        )
        where = g.slot or g.label or "-"
        marks = (" **main**" if n == build.main_group else "") + ("" if g.enabled else " (disabled)")
        if g.source:
            marks += f" (from {g.source})"
        out.append(f"- [{where}]{marks}: {gems}")

    out += ["", "## Equipment"]
    eq = build.equipped()
    for slot, item in eq:
        out += _item_lines(slot, item, mods)
    if not eq:
        out.append("- (nothing equipped)")

    out += ["", "## Passive tree"]
    out += _tree_lines(build, tree_data, verbose_tree)
    if build.tree and build.tree.url:
        out.append(f"- Tree link: {build.tree.url}")

    if build.config:
        out += ["", "## Config (non-default PoB inputs)"]
        out.append("- " + ", ".join(f"{k}={v}" for k, v in sorted(build.config.items())))
    if notes and build.notes:
        out += ["", "## Notes", build.notes]
    return "\n".join(out)
