"""Parse Path of Building build XML into plain Python objects."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

SLOT_ORDER = [
    "Weapon 1", "Weapon 2", "Helmet", "Body Armour", "Gloves", "Boots",
    "Amulet", "Ring 1", "Ring 2", "Ring 3", "Belt",
    "Flask 1", "Flask 2", "Flask 3", "Flask 4", "Flask 5",
    "Weapon 1 Swap", "Weapon 2 Swap",
]

_INFLUENCES = {
    "Shaper Item": "Shaper", "Elder Item": "Elder", "Crusader Item": "Crusader",
    "Hunter Item": "Hunter", "Redeemer Item": "Redeemer", "Warlord Item": "Warlord",
    "Searing Exarch Item": "Exarch", "Eater of Worlds Item": "Eater",
    "Synthesised Item": "Synthesised", "Fractured Item": "Fractured",
}
_TRAILING_FLAGS = {"Corrupted", "Mirrored", "Split", "Unidentified", "Sanctified"}
_PROP = re.compile(r"^([A-Za-z][A-Za-z ]*?):\s*(.*)$")
_TAG = re.compile(r"^\{([^}]*)\}")
_RANGE = re.compile(r"\((-?\d+(?:\.\d+)?)-(-?\d+(?:\.\d+)?)\)")
_MULTI_PROPS = {"Prefix", "Suffix", "Variant"}


@dataclass
class Mod:
    text: str
    tags: list[str] = field(default_factory=list)  # crafted, fractured, enchant, ...


@dataclass
class Item:
    id: str
    rarity: str
    name: str
    base: str
    implicits: list[Mod]
    explicits: list[Mod]
    influences: list[str]
    flags: list[str]
    props: dict[str, object]

    @property
    def title(self) -> str:
        if self.rarity in ("RARE", "UNIQUE", "RELIC") and self.name != self.base:
            return f"{self.name}, {self.base}"
        return self.base

    def prop_int(self, key: str) -> int | None:
        v = self.props.get(key)
        try:
            return int(str(v).split()[0]) if v is not None else None
        except ValueError:
            return None


@dataclass
class Gem:
    name: str
    level: int
    quality: int
    enabled: bool
    support: bool
    quality_id: str = "Default"


@dataclass
class SkillGroup:
    slot: str
    label: str
    enabled: bool
    gems: list[Gem]
    main_active: int = 1
    source: str = ""

    @property
    def active_gems(self) -> list[Gem]:
        return [g for g in self.gems if not g.support]


@dataclass
class TreeSpec:
    title: str
    version: str
    class_id: int
    ascend_class_id: int
    nodes: list[int]
    masteries: dict[int, int]  # mastery node id -> chosen effect id
    jewels: dict[int, str]  # socket node id -> item id
    url: str


@dataclass
class Build:
    class_name: str
    ascendancy: str
    level: int
    bandit: str
    pantheon_major: str
    pantheon_minor: str
    main_group: int
    stats: dict[str, float]
    minion_stats: dict[str, float]
    skills: list[SkillGroup]
    items: dict[str, Item]
    slots: dict[str, str]  # slot name -> item id
    trees: list[TreeSpec]
    active_tree: int
    config: dict[str, object]
    notes: str

    @property
    def tree(self) -> TreeSpec | None:
        if not self.trees:
            return None
        return self.trees[min(max(self.active_tree, 1), len(self.trees)) - 1]

    @property
    def main_skill(self) -> SkillGroup | None:
        if 1 <= self.main_group <= len(self.skills):
            return self.skills[self.main_group - 1]
        return next((g for g in self.skills if g.enabled and g.active_gems), None)

    def equipped(self) -> list[tuple[str, Item]]:
        """(slot, item) pairs in a stable, readable order, gear first then jewels."""
        def key(slot: str):
            return (SLOT_ORDER.index(slot) if slot in SLOT_ORDER else len(SLOT_ORDER), slot)

        out = [(s, self.items[i]) for s, i in sorted(self.slots.items(), key=lambda kv: key(kv[0])) if i in self.items]
        if self.tree:
            for node, item_id in sorted(self.tree.jewels.items()):
                if item_id in self.items:
                    out.append((f"Jewel @{node}", self.items[item_id]))
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["main_skill_index"] = self.main_group
        return d


def _num(v: str | None) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return int(f) if f.is_integer() else f


def _fmt_number(x: float, decimals: bool) -> str:
    if not decimals:
        return str(int(x + 0.5) if x >= 0 else -int(-x + 0.5))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def parse_mod(raw: str) -> tuple[Mod, set[int] | None]:
    """Strip PoB's {tag} prefixes and resolve (min-max) ranges. Returns (mod, variants)."""
    tags: list[str] = []
    variants: set[int] | None = None
    rng: float | None = None
    s = raw
    while m := _TAG.match(s):
        tag, s = m.group(1), s[m.end():]
        if tag.startswith("range:"):
            try:
                rng = float(tag[6:])
            except ValueError:
                pass
        elif tag.startswith("variant:"):
            variants = {int(v) for v in tag[8:].split(",") if v.strip().isdigit()}
        elif tag.startswith("tags:"):
            continue
        else:
            tags.append(tag)

    r = 0.5 if rng is None else rng

    def resolve(m: re.Match) -> str:
        lo_s, hi_s = m.group(1), m.group(2)
        lo, hi = float(lo_s), float(hi_s)
        return _fmt_number(lo + (hi - lo) * r, "." in lo_s or "." in hi_s)

    return Mod(_RANGE.sub(resolve, s).strip(), tags), variants


def parse_item(item_id: str, text: str) -> Item:
    lines = [ln.strip() for ln in (text or "").strip().splitlines() if ln.strip()]
    i = 0
    rarity = "NORMAL"
    if lines and lines[0].startswith("Rarity:"):
        rarity = lines[0].split(":", 1)[1].strip().upper()
        i = 1
    name = lines[i] if i < len(lines) else "?"
    i += 1
    base = name
    if rarity in ("RARE", "UNIQUE", "RELIC") and i < len(lines) and not _PROP.match(lines[i]):
        if lines[i] not in _INFLUENCES:
            base = lines[i]
            i += 1

    props: dict[str, object] = {}
    influences: list[str] = []
    flags: list[str] = []
    implicit_count: int | None = None
    # Everything before the "Implicits: N" line is header. Without that line,
    # the header ends at the first line that isn't a property or influence.
    header_end = next((k for k in range(i, len(lines)) if lines[k].startswith("Implicits:")), None)
    while i < len(lines):
        ln = lines[i]
        m = _PROP.match(ln)
        if m and not ln.startswith("{"):
            key, val = m.group(1), m.group(2)
            if key == "Implicits":
                implicit_count = int(val) if val.isdigit() else 0
                i += 1
                break
            if key in _MULTI_PROPS:
                props.setdefault(key, []).append(val)  # type: ignore[union-attr]
            else:
                props[key] = val
        elif ln in _INFLUENCES:
            influences.append(_INFLUENCES[ln])
        elif header_end is None:
            break
        elif ln not in (name, base):
            flags.append(ln)
        i += 1

    selected: set[int] = set()
    for key in ("Selected Variant", "Selected Alt Variant"):
        v = props.get(key)
        if isinstance(v, str) and v.isdigit():
            selected.add(int(v))

    implicits: list[Mod] = []
    explicits: list[Mod] = []
    for n, ln in enumerate(lines[i:]):
        if ln in _TRAILING_FLAGS:
            flags.append(ln)
            continue
        mod, variants = parse_mod(ln)
        if variants is not None and selected and not (variants & selected):
            continue
        is_implicit = implicit_count is not None and n < implicit_count
        (implicits if is_implicit else explicits).append(mod)

    return Item(item_id, rarity, name, base, implicits, explicits, influences, flags, props)


def _parse_skills(root: ET.Element) -> list[SkillGroup]:
    skills_el = root.find("Skills")
    if skills_el is None:
        return []
    container = skills_el
    sets = skills_el.findall("SkillSet")
    if sets:
        active = skills_el.get("activeSkillSet", "1")
        container = next((s for s in sets if s.get("id") == active), sets[0])
    groups = []
    for sk in container.findall("Skill"):
        gems = []
        for g in sk.findall("Gem"):
            gem_id = g.get("gemId", "") or ""
            skill_id = g.get("skillId", "") or ""
            gems.append(Gem(
                name=g.get("nameSpec") or skill_id or gem_id.rsplit("/", 1)[-1],
                level=int(_num(g.get("level"))),
                quality=int(_num(g.get("quality"))),
                enabled=g.get("enabled", "true") == "true",
                support="SupportGem" in gem_id or skill_id.startswith("Support"),
                quality_id=g.get("qualityId", "Default") or "Default",
            ))
        groups.append(SkillGroup(
            slot=sk.get("slot", "") or "",
            label=sk.get("label", "") or "",
            enabled=sk.get("enabled", "true") == "true",
            gems=gems,
            main_active=int(_num(sk.get("mainActiveSkill", "1")) or 1),
            source=sk.get("source", "") or "",
        ))
    return groups


def _parse_items(root: ET.Element) -> tuple[dict[str, Item], dict[str, str]]:
    items_el = root.find("Items")
    if items_el is None:
        return {}, {}
    items = {el.get("id", ""): parse_item(el.get("id", ""), el.text or "") for el in items_el.findall("Item")}
    container = items_el
    sets = items_el.findall("ItemSet")
    if sets:
        active = items_el.get("activeItemSet", "1")
        container = next((s for s in sets if s.get("id") == active), sets[0])
    slots = {}
    for sl in container.findall("Slot"):
        item_id = sl.get("itemId", "0")
        if item_id and item_id != "0":
            slots[sl.get("name", "?")] = item_id
    return items, slots


def _parse_trees(root: ET.Element) -> tuple[list[TreeSpec], int]:
    tree_el = root.find("Tree")
    if tree_el is None:
        return [], 1
    specs = []
    for sp in tree_el.findall("Spec"):
        nodes = [int(n) for n in (sp.get("nodes") or "").split(",") if n.strip().isdigit()]
        masteries = {int(a): int(b) for a, b in re.findall(r"\{(\d+),(\d+)\}", sp.get("masteryEffects") or "")}
        jewels = {}
        sockets = sp.find("Sockets")
        if sockets is not None:
            for so in sockets.findall("Socket"):
                if so.get("itemId", "0") != "0":
                    jewels[int(so.get("nodeId", "0"))] = so.get("itemId", "")
        url_el = sp.find("URL")
        specs.append(TreeSpec(
            title=sp.get("title", "") or "",
            version=sp.get("treeVersion", "") or "",
            class_id=int(_num(sp.get("classId"))),
            ascend_class_id=int(_num(sp.get("ascendClassId"))),
            nodes=nodes,
            masteries=masteries,
            jewels=jewels,
            url=(url_el.text or "").strip() if url_el is not None else "",
        ))
    return specs, int(_num(tree_el.get("activeSpec", "1")) or 1)


def _parse_config(root: ET.Element) -> dict[str, object]:
    cfg = root.find("Config")
    if cfg is None:
        return {}
    container = cfg
    sets = cfg.findall("ConfigSet")
    if sets:
        active = cfg.get("activeConfigSet", "1")
        container = next((s for s in sets if s.get("id") == active), sets[0])
    out: dict[str, object] = {}
    for inp in container.findall("Input"):
        name = inp.get("name")
        if not name:
            continue
        if inp.get("boolean") is not None:
            out[name] = inp.get("boolean") == "true"
        elif inp.get("number") is not None:
            out[name] = _num(inp.get("number"))
        else:
            out[name] = inp.get("string", "")
    return out


def parse_build(xml_text: str) -> Build:
    root = ET.fromstring(xml_text)
    b = root.find("Build")
    if b is None:
        raise ValueError("no <Build> element in XML")
    stats: dict[str, float] = {}
    for ps in b.findall("PlayerStat"):
        stats.setdefault(ps.get("stat", "?"), _num(ps.get("value")))
    minion: dict[str, float] = {}
    for ms in b.findall("MinionStat"):
        minion.setdefault(ms.get("stat", "?"), _num(ms.get("value")))
    items, slots = _parse_items(root)
    trees, active_tree = _parse_trees(root)
    notes_el = root.find("Notes")
    return Build(
        class_name=b.get("className", "") or "",
        ascendancy=b.get("ascendClassName", "") or "",
        level=int(_num(b.get("level"))),
        bandit=b.get("bandit", "None") or "None",
        pantheon_major=b.get("pantheonMajorGod", "None") or "None",
        pantheon_minor=b.get("pantheonMinorGod", "None") or "None",
        main_group=int(_num(b.get("mainSocketGroup", "1"))),
        stats=stats,
        minion_stats=minion,
        skills=_parse_skills(root),
        items=items,
        slots=slots,
        trees=trees,
        active_tree=active_tree,
        config=_parse_config(root),
        notes=(notes_el.text or "").strip() if notes_el is not None else "",
    )
