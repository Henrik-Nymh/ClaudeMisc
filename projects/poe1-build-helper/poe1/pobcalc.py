"""Run Path of Building headless (via LuaJIT) to recalculate builds and item swaps.

Setup: ./setup-pob.sh (installs LuaJIT + luautf8, fetches PoB into .cache/pob).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DRIVER = Path(__file__).resolve().parent / "pob_driver.lua"

DEFAULT_STATS = [
    "CombinedDPS", "FullDPS", "TotalDPS", "TotalDotDPS", "AverageHit", "Speed", "CritChance",
    "CritMultiplier", "HitChance", "Life", "EnergyShield", "Mana", "ManaUnreserved", "Ward",
    "TotalEHP", "Armour", "Evasion", "PhysicalDamageReduction", "EffectiveBlockChance",
    "EffectiveSpellBlockChance", "EffectiveSpellSuppressionChance", "FireResist", "ColdResist",
    "LightningResist", "ChaosResist", "FireResistOverCap", "ColdResistOverCap",
    "LightningResistOverCap", "PhysicalMaximumHitTaken", "FireMaximumHitTaken",
    "ColdMaximumHitTaken", "LightningMaximumHitTaken", "ChaosMaximumHitTaken",
    "NetLifeRegen", "NetManaRegen", "EffectiveMovementSpeedMod", "Str", "Dex", "Int",
    "ReqStr", "ReqDex", "ReqInt", "ManaCost",
]

# Stats shown in delta tables, (key, label, higher_is_better)
DELTA_STATS = [
    ("FullDPS", "Full DPS", True), ("CombinedDPS", "DPS", True), ("TotalEHP", "EHP", True),
    ("Life", "Life", True), ("EnergyShield", "ES", True), ("Mana", "Mana", True),
    ("FireResist", "Fire", True), ("ColdResist", "Cold", True), ("LightningResist", "Light", True),
    ("ChaosResist", "Chaos", True), ("PhysicalMaximumHitTaken", "Max phys hit", True),
    ("EffectiveSpellSuppressionChance", "Suppress", True), ("EffectiveBlockChance", "Block", True),
    ("EffectiveSpellBlockChance", "Spell block", True), ("Armour", "Armour", True),
    ("Evasion", "Evasion", True), ("EffectiveMovementSpeedMod", "Move", True),
]


class PobUnavailable(RuntimeError):
    pass


def pob_dir() -> Path:
    return Path(os.environ.get("POE1_POB_DIR", PROJECT / ".cache" / "pob"))


def check() -> None:
    if not shutil.which("luajit"):
        raise PobUnavailable("luajit not found; run ./setup-pob.sh")
    if not (pob_dir() / "src" / "HeadlessWrapper.lua").exists():
        raise PobUnavailable(f"Path of Building not found in {pob_dir()}; run ./setup-pob.sh")


def run(xml: str, actions: list[dict] | None = None, stats: list[str] | None = None,
        variants: list[tuple[str, str]] | None = None, timeout: float = 600) -> dict:
    """Load `xml` in PoB, apply `actions` (each evaluated separately against the
    base build), then evaluate whole-build `variants` [(label, xml)]. Returns stats."""
    check()
    src = pob_dir() / "src"
    with tempfile.TemporaryDirectory(prefix="poe1-pob-") as td:
        td_path = Path(td)
        (td_path / "build.xml").write_text(xml, encoding="utf-8")
        vlist = []
        for n, (label, vxml) in enumerate(variants or []):
            p = td_path / f"variant{n}.xml"
            p.write_text(vxml, encoding="utf-8")
            vlist.append({"label": label, "xml_path": str(p)})
        req = {"xml_path": str(td_path / "build.xml"), "stats": stats or DEFAULT_STATS,
               "actions": actions or [], "variants": vlist}
        (td_path / "request.json").write_text(json.dumps(req), encoding="utf-8")
        out = td_path / "result.json"
        env = dict(os.environ)
        env["LUA_PATH"] = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;" + env.get("LUA_PATH", ";;")
        proc = subprocess.run(
            ["luajit", str(DRIVER), str(td_path / "request.json"), str(out)],
            cwd=src, env=env, capture_output=True, text=True, timeout=timeout,
        )
        if not out.exists():
            tail = "\n".join((proc.stderr or proc.stdout or "").strip().splitlines()[-15:])
            raise RuntimeError(f"headless PoB failed (exit {proc.returncode}):\n{tail}")
        return json.loads(out.read_text(encoding="utf-8"))


_GEM_SPEC = re.compile(r"^(swap|add|remove):([^:]+):(.+)$")


def apply_gem_change(xml: str, spec: str, main_group: int) -> str:
    """Return a modified build XML. Specs (group = 'main' or 1-based index as in `summary`):
    swap:<group>:<Old>=<New>[@level/quality]   add:<group>:<New>[@level/quality]   remove:<group>:<Old>
    """
    m = _GEM_SPEC.match(spec.strip())
    if not m:
        raise ValueError(f"bad gem change {spec!r}")
    op, group_s, rest = m.groups()
    root = ET.fromstring(xml)
    skills = root.find("Skills")
    sets = skills.findall("SkillSet") if skills is not None else []
    container = skills
    if sets:
        active = skills.get("activeSkillSet", "1")
        container = next((s for s in sets if s.get("id") == active), sets[0])
    groups = container.findall("Skill") if container is not None else []
    idx = main_group if group_s.strip().lower() == "main" else int(group_s)
    if not 1 <= idx <= len(groups):
        raise ValueError(f"no skill group {group_s} (build has {len(groups)})")
    group = groups[idx - 1]

    def parse_new(text: str) -> tuple[str, str | None, str | None]:
        name, _, lq = text.partition("@")
        level, _, quality = lq.partition("/")
        return name.strip(), level.strip() or None, quality.strip() or None

    def find(name: str) -> ET.Element:
        for g in group.findall("Gem"):
            if (g.get("nameSpec") or "").lower() == name.strip().lower():
                return g
        names = ", ".join(g.get("nameSpec", "?") for g in group.findall("Gem"))
        raise ValueError(f"gem {name!r} not in group {idx} ({names})")

    def set_gem(el: ET.Element, name: str, level: str | None, quality: str | None) -> None:
        for attr in ("gemId", "skillId", "variantId"):
            el.attrib.pop(attr, None)
        el.set("nameSpec", name)
        el.set("level", level or el.get("level") or "20")
        el.set("quality", quality or el.get("quality") or "0")
        el.set("enabled", "true")

    if op == "remove":
        group.remove(find(rest))
    elif op == "swap":
        old, _, new = rest.partition("=")
        set_gem(find(old), *parse_new(new))
    else:
        el = ET.SubElement(group, "Gem")
        set_gem(el, *parse_new(rest))
        el.set("qualityId", "Default")
    return ET.tostring(root, encoding="unicode")


def _fmt(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 10_000:
        return f"{v / 1000:.1f}k"
    return f"{v:.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:.2f}"


def delta_line(base: dict, new: dict) -> str:
    parts = []
    for key, label, _ in DELTA_STATS:
        a, b = base.get(key), new.get(key)
        if a is None or b is None or abs(b - a) < 1e-9:
            continue
        diff = b - a
        pct = f" ({diff / abs(a) * 100:+.1f}%)" if a else ""
        parts.append(f"{label} {'+' if diff > 0 else ''}{_fmt(diff)}{pct}")
    return " · ".join(parts) or "no change in key stats"
