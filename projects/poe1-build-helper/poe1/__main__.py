"""CLI: python3 -m poe1 <command> ...  (run from the project folder)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from . import build as buildmod
from . import compare, gamedata, pobcalc, pobcode, summary, trade, whatif

DEFAULT_LEAGUE = os.environ.get("POE1_LEAGUE", "Standard")


def _load_build(src: str) -> buildmod.Build:
    return buildmod.parse_build(pobcode.load(src))


def _tree_for(b: buildmod.Build, override: str | None) -> dict | None:
    version = override or (b.tree.version if b.tree else None)
    if not version:
        return None
    try:
        return gamedata.load_tree(version)
    except Exception as e:  # noqa: BLE001 - tree names are a nice-to-have
        print(f"(could not load tree data {version}: {e})", file=sys.stderr)
        return None


def cmd_decode(a):
    xml = pobcode.load(a.source)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"wrote {a.output}", file=sys.stderr)
    else:
        print(xml)


def cmd_encode(a):
    print(pobcode.encode(pobcode.load(a.source)))


def cmd_summary(a):
    b = _load_build(a.source)
    if a.json:
        print(json.dumps(b.to_dict(), indent=2, ensure_ascii=False))
        return
    print(summary.render(b, _tree_for(b, a.tree_version), mods=not a.no_mods,
                         all_stats=a.all_stats, verbose_tree=a.tree_stats, notes=a.notes))


def cmd_compare(a):
    ba, bb = _load_build(a.mine), _load_build(a.other)
    print(compare.render(ba, bb, _tree_for(ba, None), _tree_for(bb, None), mods=a.mods))


def cmd_similar(a):
    b = _load_build(a.source)
    skill = a.skill or compare.main_skill_name(b)
    asc = None if a.any_class else (b.ascendancy if b.ascendancy not in ("", "None") else None)
    print(f"Main skill: {skill or '?'}" + (f" · Ascendancy: {asc}" if asc else ""))
    print(compare.ninja_builds_url(a.league, skill, asc))
    print(compare.ninja_builds_url(a.league))
    print("\nOpen the first link (the second is the unfiltered league page in case the filter\n"
          "parameters are off). Pick a character, use poe.ninja's Path of Building export,\n"
          "then: python3 -m poe1 compare <your build> <their code>")


def cmd_data(a):
    print(json.dumps(gamedata.update(a.ref, a.tree or None), indent=2))


def cmd_stats(a):
    index = trade.StatIndex(gamedata.load_trade_stats())
    for s in index.search(" ".join(a.words), a.type, a.limit):
        print(f"{s['id']:45} [{s['type']}] {s['text']}")


_SPEC = re.compile(r"^(.*?)\s*(>=|<=|=)\s*(-?\d+(?:\.\d+)?)\s*$")


def _parse_stat(index: trade.StatIndex, spec: str) -> trade.StatFilter:
    """'text or id >= 70' / '<= 10' / '= 5' / bare."""
    m = _SPEC.match(spec)
    text, op, num = (m.group(1), m.group(2), float(m.group(3))) if m else (spec, None, None)
    stat = index.resolve(text)
    f = trade.StatFilter(stat["id"], label=stat["text"])
    if op in (">=", "="):
        f.min = num
    if op in ("<=", "="):
        f.max = num
    return f


def _parse_weight(index: trade.StatIndex, spec: str) -> trade.StatFilter:
    text, _, w = spec.rpartition("=")
    if not text:
        raise SystemExit(f"--weight needs 'stat=weight', got {spec!r}")
    stat = index.resolve(text)
    return trade.StatFilter(stat["id"], weight=float(w), label=stat["text"])


def _common_query_opts(q: trade.Query, a) -> None:
    q.status = a.status
    if a.max_price is not None:
        q.max_price, q.price_currency = a.max_price, a.currency
    if a.ilvl_min is not None:
        q.ilvl_min = a.ilvl_min
    if a.links_min is not None:
        q.links_min = a.links_min
    if a.level_max is not None:
        q.level_max = a.level_max
    if a.corrupted is not None:
        q.corrupted = a.corrupted == "yes"


def _emit(q: trade.Query, index: trade.StatIndex, a, mapping=None) -> None:
    if a.json:
        print(json.dumps({"query": q.to_json(), "sort": q.sort()}, indent=2))
        return
    if mapping:
        print("Mods on current item:")
        for m in mapping:
            target = m.stat["text"] if m.stat else "-"
            note = f"  ({m.note})" if m.note else ""
            print(f"  {m.mod}  ->  {target}{note}")
        print()
    head = " ".join(p for p in (q.name, q.base, q.category, q.rarity) if p)
    print(f"Query: {head or '(any item)'}  status={q.status}")
    for line in q.describe(index):
        print(line)
    print()
    print(trade.trade_url(a.league, q, a.realm))
    if a.live:
        client = trade.TradeClient(a.league, a.realm, os.environ.get("POESESSID"))
        items, total, qid = client.search(q, a.limit)
        print(f"\n{total} listings match; showing {len(items)} (query id {qid}):")
        deltas: list[str | None] = [None] * len(items)
        calc_src, calc_slot = getattr(a, "calc_source", None), getattr(a, "slot", None)
        if calc_src and calc_slot and items:
            actions = [{"type": "item", "slot": calc_slot, "text": whatif.listing_to_item_text(e.get("item", {}))}
                       for e in items]
            res = pobcalc.run(pobcode.load(calc_src), actions=actions)
            deltas = [r.get("error") or pobcalc.delta_line(res["base"], r["stats"]) for r in res["actions"]]
        for entry, delta in zip(items, deltas):
            lines = trade.format_listing(entry)
            if delta:
                lines.insert(1, f"    => PoB: {delta}")
            print("\n".join(lines))


def cmd_trade_query(a):
    index = trade.StatIndex(gamedata.load_trade_stats())
    q = trade.Query(name=a.name, base=a.base, category=a.category, rarity=a.rarity)
    q.and_stats = [_parse_stat(index, s) for s in a.stat or []]
    q.weight_stats = [_parse_weight(index, s) for s in a.weight or []]
    q.weight_min = a.weight_min
    q.not_stats = [_parse_stat(index, s) for s in a.exclude or []]
    _common_query_opts(q, a)
    _emit(q, index, a)


def cmd_trade_item(a):
    b = _load_build(a.source)
    item_id = b.slots.get(a.slot)
    if item_id is None:
        jewel = re.match(r"^Jewel @?(\d+)$", a.slot)
        if jewel and b.tree:
            item_id = b.tree.jewels.get(int(jewel.group(1)))
    if item_id is None or item_id not in b.items:
        slots = ", ".join(s for s, _ in b.equipped())
        raise SystemExit(f"no item in slot {a.slot!r}. Equipped: {slots}")
    item = b.items[item_id]
    index = trade.StatIndex(gamedata.load_trade_stats())
    q, mapping = trade.query_from_item(item, a.slot, index, scale=a.scale, same_base=a.same_base,
                                       include_crafted=a.include_crafted, include_implicits=a.implicits)
    _common_query_opts(q, a)
    a.calc_source = a.source if a.calc else None
    print(f"Current {a.slot}: {item.title}\n")
    _emit(q, index, a, mapping)


def _read_item_text(spec: str) -> str:
    if spec == "-":
        return sys.stdin.read()
    if os.path.isfile(spec):
        with open(spec, encoding="utf-8") as f:
            return f.read()
    return spec.replace("\\n", "\n")


def cmd_calc(a):
    xml = pobcode.load(a.source)
    res = pobcalc.run(xml)
    b = buildmod.parse_build(xml)
    if res["unresolved_gems"]:
        print("Unresolved gems: " + ", ".join(res["unresolved_gems"]))
    print(f"{'stat':34}{'headless PoB':>16}{'in export':>16}")
    for k in pobcalc.DEFAULT_STATS:
        h, e = res["base"].get(k), b.stats.get(k)
        if h is None and e is None:
            continue
        flag = "" if e is None or h is None or abs(h - e) <= max(1e-6, abs(e) * 0.005) else "  <- differs"
        print(f"{k:34}{'-' if h is None else f'{h:,.2f}':>16}{'-' if e is None else f'{e:,.2f}':>16}{flag}")


def _node_ids(xml: str, spec: str) -> list[int]:
    """'Sanctuary + Safeguard' -> node ids (from the build's tree version)."""
    tree = _tree_for(buildmod.parse_build(xml), None) or {"nodes": {}}
    by_name = {n["name"].lower(): int(i) for i, n in tree["nodes"].items() if not n.get("ascendancy")}
    names = [s.strip() for s in spec.split("+") if s.strip()]
    missing = [s for s in names if s.lower() not in by_name]
    if missing:
        raise ValueError(f"unknown node(s): {', '.join(missing)}")
    return [by_name[s.lower()] for s in names]


def cmd_try(a):
    xml = pobcode.load(a.source)
    actions = [{"type": "item", "slot": a.slot, "text": _read_item_text(s)} for s in a.item or []]
    actions += [{"type": "unique", "slot": a.slot, "name": u} for u in a.unique or []]
    if a.nodes:
        ids = _node_ids(xml, a.nodes)
        for act in actions:
            act["ids"] = ids
    if a.unequip:
        actions.append({"type": "unequip", "slot": a.slot})
    if not actions:
        raise SystemExit("give --item (text, file or -), --unique NAME and/or --unequip")
    res = pobcalc.run(xml, actions=actions)
    labels = [f"item {n}" for n in range(1, len(a.item or []) + 1)] + list(a.unique or []) \
        + (["unequip"] if a.unequip else [])
    for label, r in zip(labels, res["actions"]):
        name = f" ({r['name']})" if r.get("name") else ""
        print(f"- {label}{name}: {r.get('error') or pobcalc.delta_line(res['base'], r['stats'])}")


def cmd_gems(a):
    xml = pobcode.load(a.source)
    main = buildmod.parse_build(xml).main_group
    variants, failed = [], []
    for c in a.change:
        try:
            variants.append((c, pobcalc.apply_gem_change(xml, c, main)))
        except ValueError as e:
            failed.append(f"- {c}: error: {e}")
    if a.combine and len(a.change) > 1:
        try:
            combined = xml
            for c in a.change:
                combined = pobcalc.apply_gem_change(combined, c, main)
            variants.append(("all combined", combined))
        except ValueError as e:
            failed.append(f"- all combined: error: {e}")
    if failed:
        print("\n".join(failed))
    if not variants:
        return
    res = pobcalc.run(xml, variants=variants)
    for v in res["variants"]:
        warn = f"  [unresolved gems: {', '.join(v['unresolved_gems'])}]" if v.get("unresolved_gems") else ""
        print(f"- {v['label']}: {v.get('error') or pobcalc.delta_line(res['base'], v['stats'])}{warn}")


def cmd_tree(a):
    xml = pobcode.load(a.source)
    if a.nodes:
        b = buildmod.parse_build(xml)
        tree = _tree_for(b, None) or {"nodes": {}}
        by_name = {n["name"].lower(): int(i) for i, n in tree["nodes"].items() if not n.get("ascendancy")}
        combos = []
        for combo in a.nodes:
            names = [s.strip() for s in combo.split("+") if s.strip()]
            missing = [s for s in names if s.lower() not in by_name]
            if missing:
                raise ValueError(f"unknown node(s): {', '.join(missing)}")
            combos.append({"type": "node", "ids": [by_name[s.lower()] for s in names]})
        res = pobcalc.run(xml, actions=combos)
        for r in res["actions"]:
            label = f"{r.get('name', '?')} ({r.get('points', '?')}p)"
            print(f"- {label}: {r.get('error') or pobcalc.delta_line(res['base'], r['stats'])}")
        return
    res = pobcalc.run(xml, actions=[{"type": "tree_power", "max_path": a.max_path, "include_allocated": True}])
    act = res["actions"][0]
    if "error" in act:
        raise RuntimeError(act["error"])
    print("\n".join(whatif.tree_report(res["base"], act["nodes"], a.top)))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="poe1", description="Path of Exile 1 build helper")
    sub = p.add_subparsers(dest="cmd", required=True)
    src_help = "PoB code, pobb.in/pastebin link, .xml/.txt file, or '-' for stdin"

    s = sub.add_parser("decode", help="PoB code/link -> build XML")
    s.add_argument("source", help=src_help)
    s.add_argument("-o", "--output")
    s.set_defaults(func=cmd_decode)

    s = sub.add_parser("encode", help="build XML -> PoB code")
    s.add_argument("source", help=src_help)
    s.set_defaults(func=cmd_encode)

    s = sub.add_parser("summary", help="readable overview of a build")
    s.add_argument("source", help=src_help)
    s.add_argument("--json", action="store_true", help="full parsed build as JSON")
    s.add_argument("--no-mods", action="store_true", help="hide item mods")
    s.add_argument("--all-stats", action="store_true", help="include every PoB stat")
    s.add_argument("--tree-stats", action="store_true", help="show stats of keystones/notables")
    s.add_argument("--notes", action="store_true", help="include build notes")
    s.add_argument("--tree-version", help="override tree data version (e.g. 3_30)")
    s.set_defaults(func=cmd_summary)

    s = sub.add_parser("compare", help="diff your build against another (stats, gems, gear, tree)")
    s.add_argument("mine", help=src_help)
    s.add_argument("other", help=src_help)
    s.add_argument("--mods", action="store_true", help="show the other build's mods on differing slots")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("similar", help="poe.ninja link to builds with the same main skill")
    s.add_argument("source", help=src_help)
    s.add_argument("--league", default=DEFAULT_LEAGUE)
    s.add_argument("--skill", help="override the detected main skill")
    s.add_argument("--any-class", action="store_true", help="don't filter on ascendancy")
    s.set_defaults(func=cmd_similar)

    s = sub.add_parser("data", help="refresh cached game data from Path of Building's repo")
    s.add_argument("--ref", default=gamedata.DEFAULT_REF, help="PoB git ref (default: master)")
    s.add_argument("--tree", action="append", help="tree version(s) to fetch (default: latest)")
    s.set_defaults(func=cmd_data)

    s = sub.add_parser("stats", help="find trade stat ids by text")
    s.add_argument("words", nargs="+")
    s.add_argument("--type", choices=trade.TYPE_PREFERENCE)
    s.add_argument("--limit", type=int, default=25)
    s.set_defaults(func=cmd_stats)

    def add_trade_opts(s):
        s.add_argument("--league", default=DEFAULT_LEAGUE, help=f"default: $POE1_LEAGUE or {DEFAULT_LEAGUE!r}")
        s.add_argument("--realm", default="pc")
        s.add_argument("--status", default="online", choices=trade.STATUS_OPTIONS)
        s.add_argument("--max-price", type=float)
        s.add_argument("--currency", help="price currency id (chaos, divine, ...); default chaos equivalent")
        s.add_argument("--ilvl-min", type=int)
        s.add_argument("--links-min", type=int)
        s.add_argument("--level-max", type=int, help="max required level")
        s.add_argument("--corrupted", choices=["yes", "no"])
        s.add_argument("--json", action="store_true", help="print the API request body instead")
        s.add_argument("--live", action="store_true", help="also run the search via the trade API (own machine only)")
        s.add_argument("--limit", type=int, default=10, help="listings to fetch with --live")

    tp = sub.add_parser("trade", help="build trade searches")
    tsub = tp.add_subparsers(dest="trade_cmd", required=True)

    s = tsub.add_parser("query", help="search from explicit filters")
    s.add_argument("--name", help="unique name, e.g. 'Tabula Rasa'")
    s.add_argument("--base", help="base type, e.g. 'Hubris Circlet'")
    s.add_argument("--category", help="e.g. armour.helmet, accessory.ring, weapon.bow, jewel")
    s.add_argument("--rarity", help="nonunique, unique, rare, magic, normal")
    s.add_argument("--stat", action="append", help="'+# to maximum Life >= 70' or 'pseudo.pseudo_total_life>=70'")
    s.add_argument("--weight", action="append", help="weighted sum entry 'stat=weight'")
    s.add_argument("--weight-min", type=float, help="minimum weighted sum")
    s.add_argument("--exclude", action="append", help="stat that must NOT be present")
    add_trade_opts(s)
    s.set_defaults(func=cmd_trade_query)

    s = tsub.add_parser("item", help="search for items like (or better than) one in the build")
    s.add_argument("source", help=src_help)
    s.add_argument("--slot", required=True, help="e.g. Helmet, 'Body Armour', 'Ring 1', 'Jewel @26725'")
    s.add_argument("--scale", type=float, default=0.9, help="min stat = current value * scale (default 0.9)")
    s.add_argument("--same-base", action="store_true", help="restrict to the same base type (and implicits)")
    s.add_argument("--implicits", action="store_true", help="include implicit mods")
    s.add_argument("--include-crafted", action="store_true", help="include crafted mods")
    s.add_argument("--calc", action="store_true", help="with --live: rate each listing with headless PoB")
    add_trade_opts(s)
    s.set_defaults(func=cmd_trade_item)

    s = sub.add_parser("calc", help="recalculate the build with headless PoB (checks against export)")
    s.add_argument("source", help=src_help)
    s.set_defaults(func=cmd_calc)

    s = sub.add_parser("try", help="DPS/EHP change from swapping in an item (headless PoB)")
    s.add_argument("source", help=src_help)
    s.add_argument("--slot", required=True, help="e.g. Helmet, 'Ring 1', 'Weapon 1'")
    s.add_argument("--item", action="append", help="item text (in-game Ctrl+C or PoB format), file, or -")
    s.add_argument("--unique", action="append", help="a unique from PoB's database by name, e.g. Svalinn")
    s.add_argument("--unequip", action="store_true", help="also show the effect of an empty slot")
    s.add_argument("--nodes", help="also allocate these passives: 'Sanctuary + Safeguard'")
    s.set_defaults(func=cmd_try)

    s = sub.add_parser("gems", help="DPS/EHP change from gem changes (headless PoB)")
    s.add_argument("source", help=src_help)
    s.add_argument("--change", action="append", required=True,
                   help="swap:main:Old=New@20/20 | add:3:New@20/0 | remove:main:Old (group index as in summary)")
    s.add_argument("--combine", action="store_true", help="also evaluate all changes together")
    s.set_defaults(func=cmd_gems)

    s = sub.add_parser("tree", help="value of nearby notables/keystones and of allocated ones (headless PoB)")
    s.add_argument("source", help=src_help)
    s.add_argument("--max-path", type=int, default=5, help="max points to reach a node (default 5)")
    s.add_argument("--top", type=int, default=10)
    s.add_argument("--nodes", action="append", help="evaluate allocating these together: 'Sanctuary + Safeguard'")
    s.set_defaults(func=cmd_tree)

    a = p.parse_args(argv)
    try:
        a.func(a)
    except (pobcode.PobCodeError, LookupError, RuntimeError, ValueError, pobcalc.PobUnavailable) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
