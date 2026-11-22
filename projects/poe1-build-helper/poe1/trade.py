"""Official trade site helpers: stat lookup, query building, links, live search.

Links work for anyone (open them in a browser). The live search calls the trade
API directly; GGG blocks it from datacenter IPs, so run it from your own machine.
"""

from __future__ import annotations

import base64
import gzip
import json
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field

from . import net
from .build import Item

TRADE_HOST = "https://www.pathofexile.com"
TYPE_PREFERENCE = ["pseudo", "explicit", "implicit", "fractured", "crafted", "enchant",
                   "scourge", "crucible", "veiled", "delve", "imbued"]
STATUS_OPTIONS = ["securable", "available", "onlineleague", "online", "any"]

_NUM = re.compile(r"\d+(?:\.\d+)?")


def normalize(text: str) -> str:
    """'+99 to maximum Life' -> '+# to maximum life' (matches trade stat text)."""
    return re.sub(r"\s+", " ", _NUM.sub("#", text.strip().lower()))


def mod_value(text: str) -> float | None:
    nums = [float(n) for n in _NUM.findall(text)]
    if not nums:
        return None
    if len(nums) == 2 and text.lower().startswith("adds "):
        return (nums[0] + nums[1]) / 2
    sign = -1 if re.search(r"(^|\s)-\d", text) else 1
    return sign * nums[0]


# ---------------------------------------------------------------- stat index


class StatIndex:
    def __init__(self, stats: list[dict]):
        self.by_id = {s["id"]: s for s in stats}
        self.by_template: dict[str, list[dict]] = defaultdict(list)
        for s in stats:
            self.by_template[normalize(s["text"])].append(s)

    def search(self, query: str, type_: str | None = None, limit: int = 20) -> list[dict]:
        words = query.lower().split()
        hits = [
            s for s in self.by_id.values()
            if all(w in s["text"].lower() for w in words) and (type_ is None or s["type"] == type_)
        ]
        hits.sort(key=lambda s: (_type_rank(s["type"]), len(s["text"])))
        return hits[:limit]

    def closest(self, text: str, types: list[str] | None = None, limit: int = 8) -> list[dict]:
        """Stats sharing the most words with `text` (for 'did you mean' hints)."""
        words = {w for w in re.findall(r"[a-z]{3,}", text.lower())}
        if not words:
            return []
        scored = []
        for s in self.by_id.values():
            if types and s["type"] not in types:
                continue
            hits = len(words & set(re.findall(r"[a-z]{3,}", s["text"].lower())))
            if hits:
                scored.append((-hits, _type_rank(s["type"]), len(s["text"]), s["id"], s))
        return [x[-1] for x in sorted(scored)[:limit]]

    def by_text(self, text: str, types: list[str] | None = None) -> list[dict]:
        norm = normalize(text)
        cands = self.by_template.get(norm, [])
        if not cands:  # "-9% to X" is listed as "+#% to X" on the trade site (and vice versa)
            flipped = re.sub(r"(^|\s)([+-])#", lambda m: m.group(1) + ("-" if m.group(2) == "+" else "+") + "#", norm)
            cands = self.by_template.get(flipped, [])
        if types:
            cands = [c for c in cands if c["type"] in types]
        return sorted(cands, key=lambda s: _type_rank(s["type"]))

    def resolve(self, spec: str) -> dict:
        """Stat id ('explicit.stat_123'), or '[type:]text' with numbers as '#' or literal."""
        spec = spec.strip()
        if spec in self.by_id:
            return self.by_id[spec]
        types = None
        m = re.match(r"^([a-z]+):(.*)$", spec)
        if m and m.group(1) in TYPE_PREFERENCE:
            types, spec = [m.group(1)], m.group(2)
        exact = self.by_text(spec, types)
        if exact:
            return exact[0]
        hint = "\n".join(f"  {s['id']}  [{s['type']}] {s['text']}" for s in self.closest(spec, types))
        raise LookupError(f"no trade stat matches {spec!r}" + (f"; close matches:\n{hint}" if hint else ""))


def _type_rank(t: str) -> int:
    return TYPE_PREFERENCE.index(t) if t in TYPE_PREFERENCE else len(TYPE_PREFERENCE)


# ---------------------------------------------------------------- queries


@dataclass
class StatFilter:
    id: str
    min: float | None = None
    max: float | None = None
    weight: float | None = None
    label: str = ""

    def to_json(self) -> dict:
        value: dict = {}
        if self.min is not None:
            value["min"] = _clean(self.min)
        if self.max is not None:
            value["max"] = _clean(self.max)
        if self.weight is not None:
            value["weight"] = _clean(self.weight)
        f: dict = {"id": self.id}
        if value:
            f["value"] = value
        return f


def _clean(x: float):
    return int(x) if float(x).is_integer() else round(x, 2)


@dataclass
class Query:
    status: str = "online"
    name: str | None = None
    base: str | None = None
    category: str | None = None
    rarity: str | None = None  # "nonunique", "unique", "rare", ...
    and_stats: list[StatFilter] = field(default_factory=list)
    weight_stats: list[StatFilter] = field(default_factory=list)
    weight_min: float | None = None
    not_stats: list[StatFilter] = field(default_factory=list)
    max_price: float | None = None
    price_currency: str | None = None  # None = chaos equivalent
    ilvl_min: int | None = None
    links_min: int | None = None
    level_max: int | None = None
    corrupted: bool | None = None

    def to_json(self) -> dict:
        q: dict = {"status": {"option": self.status}, "stats": []}
        if self.name:
            q["name"] = self.name
        if self.base:
            q["type"] = self.base
        q["stats"].append({"type": "and", "filters": [f.to_json() for f in self.and_stats]})
        if self.weight_stats:
            group = {"type": "weight", "filters": [f.to_json() for f in self.weight_stats]}
            if self.weight_min is not None:
                group["value"] = {"min": _clean(self.weight_min)}
            q["stats"].append(group)
        if self.not_stats:
            q["stats"].append({"type": "not", "filters": [f.to_json() for f in self.not_stats]})
        filters: dict = {}
        type_f = {}
        if self.category:
            type_f["category"] = {"option": self.category}
        if self.rarity:
            type_f["rarity"] = {"option": self.rarity}
        if type_f:
            filters["type_filters"] = {"filters": type_f}
        if self.max_price is not None:
            price: dict = {"max": _clean(self.max_price)}
            if self.price_currency:
                price["option"] = self.price_currency
            filters["trade_filters"] = {"filters": {"price": price}}
        misc = {}
        if self.ilvl_min is not None:
            misc["ilvl"] = {"min": self.ilvl_min}
        if self.corrupted is not None:
            misc["corrupted"] = {"option": "true" if self.corrupted else "false"}
        if misc:
            filters["misc_filters"] = {"filters": misc}
        if self.links_min is not None:
            filters["socket_filters"] = {"filters": {"links": {"min": self.links_min}}}
        if self.level_max is not None:
            filters["req_filters"] = {"filters": {"lvl": {"max": self.level_max}}}
        if filters:
            q["filters"] = filters
        return q

    def sort(self) -> dict:
        return {"statgroup.1": "desc"} if self.weight_stats else {"price": "asc"}

    def describe(self, index: StatIndex | None = None) -> list[str]:
        lines = []
        for title, group in (("and", self.and_stats), ("weight", self.weight_stats), ("not", self.not_stats)):
            for f in group:
                text = f.label or (index.by_id[f.id]["text"] if index and f.id in index.by_id else f.id)
                rng = " ".join(p for p in (
                    f"min {_clean(f.min)}" if f.min is not None else "",
                    f"max {_clean(f.max)}" if f.max is not None else "",
                    f"weight {_clean(f.weight)}" if f.weight is not None else "") if p)
                lines.append(f"  [{title}] {text}  ({f.id}{', ' + rng if rng else ''})")
        return lines


def trade_url(league: str, query: Query | dict, realm: str = "pc") -> str:
    """Shareable trade site link (same format Path of Building generates)."""
    q = query.to_json() if isinstance(query, Query) else query
    payload = gzip.compress(json.dumps(q, separators=(",", ":")).encode("utf-8"))
    code = base64.b64encode(payload).decode("ascii").replace("+", "-").replace("/", "_")
    realm_part = f"{realm}/" if realm and realm != "pc" else ""
    return f"{TRADE_HOST}/trade/search/{realm_part}{urllib.parse.quote(league, safe='-._~')}/{code}"


# ---------------------------------------------------------------- item -> query

ELE, FIRE, COLD, LIGHT, CHAOS = (
    "pseudo.pseudo_total_elemental_resistance", "pseudo.pseudo_total_fire_resistance",
    "pseudo.pseudo_total_cold_resistance", "pseudo.pseudo_total_lightning_resistance",
    "pseudo.pseudo_total_chaos_resistance",
)
STR, DEX, INT = "pseudo.pseudo_total_strength", "pseudo.pseudo_total_dexterity", "pseudo.pseudo_total_intelligence"
_RES = {"fire": FIRE, "cold": COLD, "lightning": LIGHT}
_ATTR = {"strength": STR, "dexterity": DEX, "intelligence": INT}

# normalized mod template -> pseudo stat contributions (multiplier of the mod value)
PSEUDO_RULES: dict[str, dict[str, float]] = {
    "+# to maximum life": {"pseudo.pseudo_total_life": 1},
    "+# to maximum energy shield": {"pseudo.pseudo_total_energy_shield": 1},
    "+# to maximum mana": {"pseudo.pseudo_total_mana": 1},
    "#% increased movement speed": {"pseudo.pseudo_increased_movement_speed": 1},
    "+#% to all elemental resistances": {ELE: 3, FIRE: 1, COLD: 1, LIGHT: 1},
    "+#% to chaos resistance": {CHAOS: 1},
    "+# to all attributes": {STR: 1, DEX: 1, INT: 1},
}
for _e, _id in _RES.items():
    PSEUDO_RULES[f"+#% to {_e} resistance"] = {ELE: 1, _id: 1}
    PSEUDO_RULES[f"+#% to {_e} and chaos resistances"] = {ELE: 1, _id: 1, CHAOS: 1}
for _a, _b in (("fire", "cold"), ("fire", "lightning"), ("cold", "lightning")):
    PSEUDO_RULES[f"+#% to {_a} and {_b} resistances"] = {ELE: 2, _RES[_a]: 1, _RES[_b]: 1}
for _a, _id in _ATTR.items():
    PSEUDO_RULES[f"+# to {_a}"] = {_id: 1}
for _a, _b in (("strength", "dexterity"), ("strength", "intelligence"), ("dexterity", "intelligence")):
    PSEUDO_RULES[f"+# to {_a} and {_b}"] = {_ATTR[_a]: 1, _ATTR[_b]: 1}

SLOT_CATEGORY = {
    "Helmet": "armour.helmet", "Body Armour": "armour.chest", "Gloves": "armour.gloves",
    "Boots": "armour.boots", "Amulet": "accessory.amulet", "Ring 1": "accessory.ring",
    "Ring 2": "accessory.ring", "Ring 3": "accessory.ring", "Belt": "accessory.belt",
}
_LOCAL_SLOTS = {"Weapon 1", "Weapon 2", "Weapon 1 Swap", "Weapon 2 Swap", "Helmet", "Body Armour", "Gloves", "Boots"}


def slot_category(slot: str, item: Item) -> str | None:
    if slot in SLOT_CATEGORY:
        return SLOT_CATEGORY[slot]
    base = item.base.lower()
    if slot.startswith("Weapon"):
        if "quiver" in base:
            return "armour.quiver"
        if any(w in base for w in ("shield", "buckler", "kite", "tower")):
            return "armour.shield"
        return None  # weapon subtype unknown without base data; use base type instead
    if slot.startswith("Flask"):
        return "flask"
    if slot.startswith("Jewel"):
        return "jewel.abyss" if any(w in base for w in ("eye jewel", "searching", "hypnotic", "murderous", "ghastly")) else "jewel"
    return None


@dataclass
class ModMapping:
    mod: str
    stat: dict | None
    value: float | None
    note: str = ""


def query_from_item(item: Item, slot: str, index: StatIndex, *, scale: float = 0.9,
                    same_base: bool = False, include_crafted: bool = False,
                    include_implicits: bool = False) -> tuple[Query, list[ModMapping]]:
    """Build a query for items at least ~`scale` as good as `item` in its main stats."""
    q = Query()
    mapping: list[ModMapping] = []
    if item.rarity in ("UNIQUE", "RELIC"):
        q.name, q.base = item.name, item.base
        return q, mapping

    q.category = slot_category(slot, item)
    q.rarity = "nonunique"
    if same_base or not q.category:
        q.base = item.base
    prefer_local = slot in _LOCAL_SLOTS

    pseudo_totals: dict[str, float] = defaultdict(float)
    mods = [(m, "explicit") for m in item.explicits]
    if include_implicits or same_base:
        mods = [(m, "implicit") for m in item.implicits] + mods
    for mod, section in mods:
        if "crafted" in mod.tags and not include_crafted:
            mapping.append(ModMapping(mod.text, None, None, "crafted (skipped)"))
            continue
        if "enchant" in mod.tags:
            mapping.append(ModMapping(mod.text, None, None, "enchant (skipped)"))
            continue
        template = re.sub(r"^-#", "+#", normalize(mod.text))
        value = mod_value(mod.text)
        rule = PSEUDO_RULES.get(template)
        if rule and value is not None:
            for pid, mult in rule.items():
                pseudo_totals[pid] += value * mult
            mapping.append(ModMapping(mod.text, {"id": "pseudo", "text": "counted in pseudo totals"}, value))
            continue
        stat = _match_mod(index, mod.text, section, mod.tags, prefer_local)
        if stat is None:
            mapping.append(ModMapping(mod.text, None, value, "no trade stat found"))
            continue
        stat_def, val = stat
        if val is not None and val < 0:
            mapping.append(ModMapping(mod.text, stat_def, val, "negative (skipped)"))
            continue
        mapping.append(ModMapping(mod.text, stat_def, val))
        q.and_stats.append(StatFilter(stat_def["id"], min=_scaled(val, scale), label=stat_def["text"]))

    for pid in (ELE, CHAOS, "pseudo.pseudo_total_life", "pseudo.pseudo_total_energy_shield",
                "pseudo.pseudo_total_mana", "pseudo.pseudo_increased_movement_speed", STR, DEX, INT):
        total = pseudo_totals.get(pid, 0)
        if total > 0 and pid in index.by_id:
            q.and_stats.insert(0, StatFilter(pid, min=_scaled(total, scale), label=index.by_id[pid]["text"]))
    return q, mapping


def _scaled(value: float | None, scale: float) -> float | None:
    """Scale a minimum down, but keep small values (+1 gem level, 5% chance) as they are."""
    if not value:
        return None
    if value <= 5:
        return value
    return float(int(value * scale))


def _match_mod(index: StatIndex, text: str, section: str, tags: list[str], prefer_local: bool):
    value = mod_value(text)
    type_order = ["fractured"] if "fractured" in tags else []
    type_order += ["crafted"] if "crafted" in tags else []
    type_order += [section] + ([t for t in ("explicit", "implicit") if t != section])
    variants = [(text, value)]
    low = text.lower()
    for a, b in (("reduced", "increased"), ("less", "more")):
        if f" {a} " in f" {low} ":
            variants.append((re.sub(rf"\b{a}\b", b, text, flags=re.I), -value if value is not None else None))
    for t in type_order:
        for txt, val in variants:
            cands = index.by_text(txt, [t])
            local = index.by_text(txt + " (Local)", [t])
            ordered = (local + cands) if prefer_local else (cands + local)
            if ordered:
                return ordered[0], val
    return None


# ---------------------------------------------------------------- live search


class RateLimiter:
    """Respects GGG's X-Rate-Limit-* headers conservatively."""

    def __init__(self):
        self.wait_until = 0.0

    def before(self):
        delay = self.wait_until - time.time()
        if delay > 0:
            print(f"(rate limit: waiting {delay:.0f}s)", file=sys.stderr)
            time.sleep(delay)

    def after(self, headers: dict[str, str]):
        rules = [r.strip().lower() for r in headers.get("x-rate-limit-rules", "").split(",") if r.strip()]
        for rule in rules:
            limits = headers.get(f"x-rate-limit-{rule}", "")
            states = headers.get(f"x-rate-limit-{rule}-state", "")
            for lim, st in zip(limits.split(","), states.split(",")):
                try:
                    max_hits, period, _ = (int(x) for x in lim.split(":"))
                    hits, _, penalty = (int(x) for x in st.split(":"))
                except ValueError:
                    continue
                if penalty > 0:
                    self.wait_until = max(self.wait_until, time.time() + penalty)
                elif hits >= max_hits - 1:
                    self.wait_until = max(self.wait_until, time.time() + period)


class TradeClient:
    def __init__(self, league: str, realm: str = "pc", poesessid: str | None = None):
        self.league, self.realm = league, realm
        self.cookie = {"Cookie": f"POESESSID={poesessid}"} if poesessid else {}
        self.limiter = RateLimiter()

    def _url(self, kind: str, tail: str = "") -> str:
        realm_part = f"/{self.realm}" if self.realm and self.realm != "pc" else ""
        return f"{TRADE_HOST}/api/trade/{kind}{realm_part}{tail}"

    def _call(self, url: str, data: dict | None = None) -> dict:
        for attempt in range(2):
            self.limiter.before()
            try:
                body, headers = net.request(url, data=data, headers=self.cookie)
                self.limiter.after(headers)
                return json.loads(body)
            except net.HttpError as e:
                self.limiter.after(e.headers)
                if e.status == 429 and attempt == 0:
                    wait = int(e.headers.get("retry-after", "10") or 10)
                    print(f"(429 rate limited: waiting {wait}s)", file=sys.stderr)
                    time.sleep(wait)
                    continue
                if e.status in (401, 403):
                    raise RuntimeError(
                        f"trade API refused the request (HTTP {e.status}). GGG blocks datacenter IPs "
                        "and may require login: run this on your own machine, optionally with "
                        "POESESSID set (see README). Do not retry in a loop: GGG restricts clients "
                        "that make many failed requests."
                    ) from None
                raise
        raise RuntimeError("rate limited twice; try again later")

    def search(self, query: Query, limit: int = 10) -> tuple[list[dict], int, str]:
        body = {"query": query.to_json(), "sort": query.sort(), "engine": "new"}
        league = urllib.parse.quote(self.league, safe="-._~")
        res = self._call(self._url("search", f"/{league}"), body)
        ids, qid, total = res.get("result", []), res.get("id", ""), res.get("total", 0)
        items: list[dict] = []
        for i in range(0, min(limit, len(ids)), 10):
            chunk = ",".join(ids[i : min(i + 10, limit)])
            items += self._call(f"{TRADE_HOST}/api/trade/fetch/{chunk}?query={qid}").get("result", [])
        return items, total, qid


def format_listing(entry: dict) -> list[str]:
    listing, item = entry.get("listing", {}), entry.get("item", {})
    price = listing.get("price") or {}
    price_s = f"{price.get('amount', '?')} {price.get('currency', '')}".strip() if price else "no price"
    name = " ".join(p for p in (item.get("name"), item.get("typeLine")) if p)
    bits = [f"ilvl {item['ilvl']}"] if item.get("ilvl") else []
    sockets = item.get("sockets") or []
    if sockets:
        groups: dict[int, int] = defaultdict(int)
        for s in sockets:
            groups[s.get("group", 0)] += 1
        bits.append(f"{len(sockets)}S{max(groups.values())}L")
    if item.get("corrupted"):
        bits.append("corrupted")
    lines = [f"- {price_s}: {name} ({', '.join(bits)})" if bits else f"- {price_s}: {name}"]
    for key, tag in (("enchantMods", "ench"), ("implicitMods", "impl"), ("fracturedMods", "frac"),
                     ("explicitMods", ""), ("craftedMods", "craft")):
        for m in item.get(key) or []:
            lines.append(f"    - {tag + ': ' if tag else ''}{m}")
    return lines
