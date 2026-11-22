"""What-if analysis on top of headless PoB: items, gems, passive nodes."""

from __future__ import annotations

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
