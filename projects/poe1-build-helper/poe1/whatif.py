"""What-if analysis on top of headless PoB: items, gems, passive nodes."""

from __future__ import annotations

import math
import re

from . import pobcalc

RARITY = {0: "NORMAL", 1: "MAGIC", 2: "RARE", 3: "UNIQUE", 9: "RELIC"}
INFLUENCE_LINES = {
    "shaper": "Shaper Item", "elder": "Elder Item", "crusader": "Crusader Item",
    "redeemer": "Redeemer Item", "hunter": "Hunter Item", "warlord": "Warlord Item",
}


def listing_to_item_text(item: dict) -> str:
    """Trade/character API item JSON -> item text Path of Building can parse."""
    lines = [f"Rarity: {RARITY.get(item.get('frameType'), 'RARE')}"]
    if item.get("name"):
        lines.append(item["name"])
    lines.append(item.get("typeLine") or item.get("baseType") or "?")
    if item.get("ilvl"):
        lines.append(f"Item Level: {item['ilvl']}")
    for prop in item.get("properties") or []:
        if prop.get("name") == "Quality" and prop.get("values"):
            lines.append("Quality: " + prop["values"][0][0].strip("+%"))
    sockets = item.get("sockets") or []
    if sockets:
        out, last_group = "", None
        for s in sockets:
            if out:
                out += "-" if s.get("group") == last_group else " "
            out += s.get("sColour", "W")
            last_group = s.get("group")
        lines.append(f"Sockets: {out}")
    for key, on in (item.get("influences") or {}).items():
        if on and key in INFLUENCE_LINES:
            lines.append(INFLUENCE_LINES[key])
    if item.get("searing"):
        lines.append("Searing Exarch Item")
    if item.get("tangled"):
        lines.append("Eater of Worlds Item")
    implicits = [f"{{enchant}}{m}" for m in item.get("enchantMods") or []] + list(item.get("implicitMods") or [])
    lines.append(f"Implicits: {len(implicits)}")
    lines += implicits
    lines += [f"{{fractured}}{m}" for m in item.get("fracturedMods") or []]
    lines += list(item.get("explicitMods") or [])
    lines += [f"{{crafted}}{m}" for m in item.get("craftedMods") or []]
    if item.get("corrupted"):
        lines.append("Corrupted")
    return "\n".join(lines)


def _pct(base: dict, new: dict, key: str) -> float:
    a, b = base.get(key) or 0, new.get(key) or 0
    return (b - a) / abs(a) * 100 if a else 0.0


def tree_report(base: dict, nodes: list[dict], top: int = 10) -> list[str]:
    def per_point(n, key):
        return _pct(base, n["stats"], key) / max(abs(n["points"]), 1)

    free = [n for n in nodes if not n["allocated"]]
    taken = [n for n in nodes if n["allocated"]]
    out = []
    for title, key in (("Best unallocated for DPS (per point)", "CombinedDPS"),
                       ("Best unallocated for EHP (per point)", "TotalEHP")):
        out.append(f"## {title}")
        for n in sorted(free, key=lambda n: -per_point(n, key))[:top]:
            if per_point(n, key) <= 0:
                break
            out.append(f"- {n['name']} ({n['points']}p): {pobcalc.delta_line(base, n['stats'])}")
        out.append("")
    if taken:
        out.append("## Weakest allocated notables/keystones (least lost when removed with dependents)")
        for n in sorted(taken, key=lambda n: -(per_point(n, "CombinedDPS") + per_point(n, "TotalEHP")))[:top]:
            out.append(f"- {n['name']} ({n['points']}p): {pobcalc.delta_line(base, n['stats'])}")
    return out


# ---------------------------------------------------------------- PoB-weighted searches

# QueryMods category per slot (PoB's trade generator names)
SLOT_MODS_CATEGORY = {
    "Helmet": "Helmet", "Body Armour": "Chest", "Gloves": "Gloves", "Boots": "Boots",
    "Amulet": "Amulet", "Ring 1": "Ring", "Ring 2": "Ring", "Belt": "Belt",
}
_SKIP_MODS = re.compile(
    r"Minion|Warcry|Attack|Totem|Melee|Vaal Soul|Cannot|cannot|Can have|Prefix Modifiers|"
    r"Suffix Modifiers|to Quality|Onslaught|Soul Gain|Socketed Strength|Socketed Dexterity"
)


def mod_candidates(category: str) -> list[dict]:
    """Explicit mods that can roll on `category`, with a mid roll (PoB's default 0.5)."""
    from . import luadata
    path = pobcalc.pob_dir() / "src" / "Data" / "QueryMods.lua"
    explicit = luadata.loads(path.read_text(encoding="utf-8"))["Explicit"]
    best: dict[str, dict] = {}
    for m in explicit.values():
        if not isinstance(m, dict) or category not in m or _SKIP_MODS.search(m["tradeMod"]["text"]):
            continue
        t, r = m["tradeMod"], m[category]
        if t["id"] not in best or r["max"] > best[t["id"]]["max"]:
            best[t["id"]] = {"id": t["id"], "text": t["text"], "min": r["min"], "max": r["max"]}
    out = []
    for m in best.values():
        m["value"] = math.ceil((m["max"] - m["min"]) * 0.5 + m["min"]) if m["max"] > 1 else m["max"]
        text = m["text"].replace(" (Local)", "")
        if text.count("#") == 2:
            text = text.replace("#", str(max(1, round(m["value"] * 0.7))), 1).replace("#", str(round(m["value"] * 1.3)), 1)
        m["line"] = text.replace("#", f"{m['value']:g}")
        out.append(m)
    return out


def blank_rare(base: str, mod_line: str | None = None, sockets: str = "B-B-B") -> str:
    text = f"Rarity: RARE\nCandidate\n{base}\nItem Level: 86\nQuality: 20\nSockets: {sockets}\nImplicits: 0"
    return text + (f"\n{mod_line}" if mod_line else "")


def mod_values(xml: str, slot: str, base: str, category: str, node_ids: list[int] | None = None,
               objective: str = "balanced") -> tuple[dict, dict, list[dict]]:
    """Value of every mod that can roll on `category`, on a blank rare `base` in `slot`.
    Returns (build stats, blank-rare stats, rows sorted by score)."""
    cands = mod_candidates(category)
    acts = [{"type": "item", "slot": slot, "text": blank_rare(base), "ids": node_ids}]
    acts += [{"type": "item", "slot": slot, "text": blank_rare(base, m["line"]), "ids": node_ids} for m in cands]
    res = pobcalc.run(xml, actions=acts)
    if "error" in res["actions"][0]:
        raise RuntimeError(res["actions"][0]["error"])
    blank = res["actions"][0]["stats"]
    rows = []
    for m, r in zip(cands, res["actions"][1:]):
        if "error" in r:
            continue
        dps, ehp = _pct(blank, r["stats"], "CombinedDPS"), _pct(blank, r["stats"], "TotalEHP")
        score = {"dps": dps, "ehp": ehp}.get(objective, dps + ehp)
        if abs(dps) + abs(ehp) >= 0.3:
            rows.append({**m, "dps": dps, "ehp": ehp, "score": score})
    rows.sort(key=lambda r: -r["score"])
    return res["base"], blank, rows
