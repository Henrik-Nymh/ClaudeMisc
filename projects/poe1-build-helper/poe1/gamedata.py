"""Game data (passive tree, trade stat ids) taken from Path of Building's repo.

PoB keeps up-to-date snapshots of GGG's data as Lua tables. We download only the
files we need from raw.githubusercontent.com, parse them as data (never run
them) and cache compact JSON under `.cache/` in the project folder.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from . import luadata, net

POB_REPO = "PathOfBuildingCommunity/PathOfBuilding"
DEFAULT_REF = os.environ.get("POE1_POB_REF", "master")


def cache_dir() -> Path:
    default = Path(__file__).resolve().parent.parent / ".cache"
    d = Path(os.environ.get("POE1_CACHE_DIR", default))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _raw_url(path: str, ref: str) -> str:
    return f"https://raw.githubusercontent.com/{POB_REPO}/{ref}/{path}"


def _cached_json(name: str, build, refresh: bool = False) -> Any:
    path = cache_dir() / name
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = build()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
    return data


def tree_versions(ref: str = DEFAULT_REF, refresh: bool = False) -> list[str]:
    def build():
        text = net.get_text(_raw_url("src/GameVersions.lua", ref))
        m = re.search(r"treeVersionList\s*=\s*(\{.*?\})", text, re.S)
        if not m:
            raise RuntimeError("could not find treeVersionList in GameVersions.lua")
        return {"ref": ref, "fetched": int(time.time()), "versions": luadata.loads(m.group(1))}

    return _cached_json("tree-versions.json", build, refresh)["versions"]


def latest_tree_version(ref: str = DEFAULT_REF) -> str:
    return [v for v in tree_versions(ref) if "ruthless" not in v and "alternate" not in v][-1]


def _node_kind(node: dict) -> str:
    for flag, kind in (
        ("isKeystone", "keystone"),
        ("isMastery", "mastery"),
        ("isJewelSocket", "jewel"),
        ("isAscendancyStart", "ascendancy-start"),
        ("isNotable", "notable"),
    ):
        if node.get(flag):
            return kind
    if node.get("classStartIndex") is not None:
        return "class-start"
    return "small"


def load_tree(version: str, ref: str = DEFAULT_REF, refresh: bool = False) -> dict:
    """Return {"version", "nodes": {id: {...}}, "classes": [...]} for a tree version."""
    if not re.fullmatch(r"[0-9a-z_]+", version):
        raise ValueError(f"bad tree version {version!r}")

    def build():
        raw = luadata.loads(net.get_text(_raw_url(f"src/TreeData/{version}/tree.lua", ref)))
        nodes = {}
        for nid, node in raw["nodes"].items():
            if not isinstance(node, dict) or "name" not in node:
                continue
            entry = {"name": node["name"], "kind": _node_kind(node), "stats": node.get("stats") or []}
            if node.get("ascendancyName"):
                entry["ascendancy"] = node["ascendancyName"]
            if node.get("masteryEffects"):
                entry["effects"] = {str(e["effect"]): e.get("stats") or [] for e in node["masteryEffects"]}
            nodes[str(nid)] = entry
        classes = [
            {"name": c["name"], "ascendancies": [a["name"] for a in c.get("ascendancies", [])]}
            for c in raw.get("classes", [])
        ]
        return {"version": version, "ref": ref, "fetched": int(time.time()), "nodes": nodes, "classes": classes}

    return _cached_json(f"tree-{version}.json", build, refresh)


def load_trade_stats(ref: str = DEFAULT_REF, refresh: bool = False) -> list[dict]:
    """Flat list of trade site stats: [{"id", "text", "type"}, ...]."""

    def build():
        raw = luadata.loads(net.get_text(_raw_url("src/Data/TradeSiteStats.lua", ref)))
        out = []
        for group in raw:
            for e in group.get("entries", []):
                out.append({"id": e["id"], "text": e["text"], "type": e.get("type", "")})
        return {"ref": ref, "fetched": int(time.time()), "stats": out}

    return _cached_json("trade-stats.json", build, refresh)["stats"]


def update(ref: str = DEFAULT_REF, versions: list[str] | None = None) -> dict:
    """Refresh all cached data. Returns a short report."""
    tv = tree_versions(ref, refresh=True)
    stats = load_trade_stats(ref, refresh=True)
    report = {"ref": ref, "tree_versions": len(tv), "trade_stats": len(stats), "trees": {}}
    for v in versions or [latest_tree_version(ref)]:
        report["trees"][v] = len(load_tree(v, ref, refresh=True)["nodes"])
    return report
