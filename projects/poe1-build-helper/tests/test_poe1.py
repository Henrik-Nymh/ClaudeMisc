"""Offline tests: python3 -m unittest discover -s tests (from the project folder)."""

from __future__ import annotations

import base64
import gzip
import json
import unittest
import urllib.parse

from poe1 import build, compare, luadata, pobcode, summary, trade

ITEM_RARE = """
Rarity: RARE
Doom Visor
Hubris Circlet
Hunter Item
Unique ID: abc
Item Level: 86
Quality: 20
Sockets: B-B-R-G
LevelReq: 69
Implicits: 1
{crafted}{range:1}+(20-25) to Strength
+120 to maximum Energy Shield
{range:0.5}+(40-50) to maximum Life
-9% to Chaos Resistance
+30% to Fire Resistance
+16% to all Elemental Resistances
{crafted}+20% to Cold Resistance
Corrupted
"""

ITEM_UNIQUE = """
Rarity: UNIQUE
Ondar's Clasp
Wrapped Mitts
Variant: Pre 1.1.0
Variant: Current
Selected Variant: 2
Wrapped Mitts
Quality: 20
LevelReq: 5
Implicits: 0
{variant:1}20% increased Attack Speed when on Full Life
{variant:2}30% increased Attack Speed when on Full Life
Adds 1 to 13 Lightning Damage to Attacks
"""

BUILD_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<PathOfBuilding>
  <Build level="92" className="Witch" ascendClassName="Necromancer" mainSocketGroup="1"
         bandit="None" pantheonMajorGod="Lunaris" pantheonMinorGod="None">
    <PlayerStat stat="Life" value="4500"/>
    <PlayerStat stat="CombinedDPS" value="1234567.8"/>
    <PlayerStat stat="FireResist" value="76"/>
  </Build>
  <Skills activeSkillSet="1">
    <SkillSet id="1">
      <Skill slot="Body Armour" enabled="true" mainActiveSkill="1">
        <Gem nameSpec="Raise Spectre" gemId="Metadata/Items/Gems/RaiseSpectre" skillId="RaiseSpectre" level="21" quality="20" enabled="true"/>
        <Gem nameSpec="Minion Damage" gemId="Metadata/Items/Gems/SupportGemMinionDamage" skillId="SupportMinionDamage" level="20" quality="20" enabled="true"/>
      </Skill>
      <Skill slot="Helmet" enabled="true">
        <Gem nameSpec="Hatred" gemId="Metadata/Items/Gems/Hatred" skillId="Hatred" level="20" quality="0" enabled="true"/>
      </Skill>
    </SkillSet>
  </Skills>
  <Tree activeSpec="1">
    <Spec treeVersion="3_30" classId="3" ascendClassId="2" nodes="1,2,3,70000" masteryEffects="{{3,99}}">
      <URL>https://www.pathofexile.com/passive-skill-tree/AAAA</URL>
      <Sockets><Socket nodeId="2" itemId="0"/></Sockets>
    </Spec>
  </Tree>
  <Items activeItemSet="1">
    <Item id="1">{ITEM_RARE}</Item>
    <Item id="2">{ITEM_UNIQUE}</Item>
    <ItemSet id="1">
      <Slot name="Helmet" itemId="1"/>
      <Slot name="Gloves" itemId="2"/>
      <Slot name="Boots" itemId="0"/>
    </ItemSet>
  </Items>
  <Config><Input name="enemyIsBoss" string="Pinnacle"/><Input name="useFrenzyCharges" boolean="true"/></Config>
</PathOfBuilding>"""

TREE = {
    "version": "3_30",
    "nodes": {
        "1": {"name": "Elemental Overload", "kind": "keystone", "stats": ["..."]},
        "2": {"name": "Heart of Ice", "kind": "notable", "stats": ["..."]},
        "3": {"name": "Life Mastery", "kind": "mastery", "stats": [], "effects": {"99": ["+50 to maximum Life"]}},
    },
}

STATS = [
    {"id": "pseudo.pseudo_total_life", "text": "+# total maximum Life", "type": "pseudo"},
    {"id": "pseudo.pseudo_total_energy_shield", "text": "+# total maximum Energy Shield", "type": "pseudo"},
    {"id": trade.ELE, "text": "+#% total Elemental Resistance", "type": "pseudo"},
    {"id": trade.STR, "text": "+# total to Strength", "type": "pseudo"},
    {"id": trade.CHAOS, "text": "+#% total to Chaos Resistance", "type": "pseudo"},
    {"id": "explicit.stat_3299347043", "text": "+# to maximum Life", "type": "explicit"},
    {"id": "explicit.stat_1", "text": "#% increased Attack Speed", "type": "explicit"},
    {"id": "explicit.stat_2", "text": "#% increased Attack Speed (Local)", "type": "explicit"},
    {"id": "explicit.stat_3", "text": "#% increased Mana Cost of Skills", "type": "explicit"},
]


class LuaDataTest(unittest.TestCase):
    def test_literals(self):
        v = luadata.loads('-- c\nreturn { a = 1, ["b"] = "x\\"y\\226\\128\\147", [3] = -2.5e1, 10, { true, nil } }')
        self.assertEqual(v["a"], 1)
        self.assertEqual(v["b"], 'x"y–')
        self.assertEqual(v[3], -25.0)
        self.assertEqual(v[1], 10)
        self.assertEqual(v[2], [True, None])

    def test_array_and_long_string(self):
        self.assertEqual(luadata.loads("{ 'a', [[line\nbreak]] }"), ["a", "line\nbreak"])

    def test_rejects_code(self):
        with self.assertRaises(luadata.LuaDataError):
            luadata.loads("return { os.exit() }")


class PobCodeTest(unittest.TestCase):
    def test_roundtrip(self):
        code = pobcode.encode(BUILD_XML)
        self.assertEqual(pobcode.decode(code), BUILD_XML)
        self.assertEqual(pobcode.load(code), BUILD_XML)

    def test_share_urls(self):
        self.assertEqual(pobcode.share_raw_url("https://pobb.in/AbC_12"), "https://pobb.in/AbC_12/raw")
        self.assertEqual(pobcode.share_raw_url("https://pastebin.com/xYz1"), "https://pastebin.com/raw/xYz1")

    def test_bad_code(self):
        with self.assertRaises(pobcode.PobCodeError):
            pobcode.decode("not a code")


class ItemTest(unittest.TestCase):
    def test_rare(self):
        it = build.parse_item("1", ITEM_RARE)
        self.assertEqual((it.rarity, it.name, it.base), ("RARE", "Doom Visor", "Hubris Circlet"))
        self.assertEqual(it.influences, ["Hunter"])
        self.assertEqual(it.flags, ["Corrupted"])
        self.assertEqual(it.prop_int("Item Level"), 86)
        self.assertEqual(it.implicits[0].text, "+25 to Strength")
        self.assertEqual(it.implicits[0].tags, ["crafted"])
        self.assertIn("+45 to maximum Life", [m.text for m in it.explicits])

    def test_unique_variants_and_repeated_base(self):
        it = build.parse_item("2", ITEM_UNIQUE)
        texts = [m.text for m in it.explicits]
        self.assertEqual(texts, ["30% increased Attack Speed when on Full Life", "Adds 1 to 13 Lightning Damage to Attacks"])
        self.assertEqual(it.props["Variant"], ["Pre 1.1.0", "Current"])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.b = build.parse_build(BUILD_XML)

    def test_basics(self):
        b = self.b
        self.assertEqual((b.class_name, b.ascendancy, b.level), ("Witch", "Necromancer", 92))
        self.assertEqual(b.stats["Life"], 4500)
        self.assertEqual(compare.main_skill_name(b), "Raise Spectre")
        self.assertTrue(b.skills[0].gems[1].support)
        self.assertEqual(b.slots, {"Helmet": "1", "Gloves": "2"})
        self.assertEqual(b.tree.masteries, {3: 99})
        self.assertEqual(b.config["enemyIsBoss"], "Pinnacle")

    def test_summary(self):
        text = summary.render(self.b, TREE)
        self.assertIn("Main skill: **Raise Spectre**", text)
        self.assertIn("Keystones: Elemental Overload", text)
        self.assertIn("Life Mastery: +50 to maximum Life", text)
        self.assertIn("1 cluster-jewel nodes", text)
        self.assertIn("Doom Visor, Hubris Circlet", text)

    def test_compare_self(self):
        text = compare.render(self.b, self.b, TREE, TREE)
        self.assertIn("(same)", text)
        self.assertNotIn("Only A", text)


class TradeTest(unittest.TestCase):
    def setUp(self):
        self.index = trade.StatIndex(STATS)
        self.b = build.parse_build(BUILD_XML)

    def test_resolve(self):
        self.assertEqual(self.index.resolve("+70 to maximum Life")["id"], "explicit.stat_3299347043")
        self.assertEqual(self.index.resolve("pseudo.pseudo_total_life")["type"], "pseudo")
        with self.assertRaises(LookupError):
            self.index.resolve("totally unknown stat")

    def test_query_from_rare(self):
        q, mapping = trade.query_from_item(self.b.items["1"], "Helmet", self.index, scale=1.0)
        got = {f.id: f.min for f in q.and_stats}
        self.assertEqual(q.category, "armour.helmet")
        self.assertEqual(got["pseudo.pseudo_total_life"], 45)
        self.assertEqual(got["pseudo.pseudo_total_energy_shield"], 120)
        self.assertEqual(got[trade.ELE], 30 + 48)  # crafted cold res skipped
        self.assertNotIn(trade.CHAOS, got)  # negative total is not a filter
        self.assertNotIn(trade.STR, got)  # crafted implicit skipped
        self.assertTrue(any(m.note == "crafted (skipped)" for m in mapping))

    def test_query_from_unique(self):
        q, _ = trade.query_from_item(self.b.items["2"], "Gloves", self.index)
        self.assertEqual((q.name, q.base), ("Ondar's Clasp", "Wrapped Mitts"))

    def test_local_preference(self):
        stat, _ = trade._match_mod(self.index, "12% increased Attack Speed", "explicit", [], True)
        self.assertEqual(stat["id"], "explicit.stat_2")
        stat, _ = trade._match_mod(self.index, "12% increased Attack Speed", "explicit", [], False)
        self.assertEqual(stat["id"], "explicit.stat_1")

    def test_reduced_maps_to_negative_increased(self):
        stat, val = trade._match_mod(self.index, "10% reduced Mana Cost of Skills", "explicit", [], False)
        self.assertEqual((stat["id"], val), ("explicit.stat_3", -10))

    def test_url_payload(self):
        q = trade.Query(category="accessory.ring", and_stats=[trade.StatFilter("pseudo.pseudo_total_life", min=60)])
        url = trade.trade_url("Hardcore Covens", q)
        prefix = "https://www.pathofexile.com/trade/search/Hardcore%20Covens/"
        self.assertTrue(url.startswith(prefix))
        payload = url[len(prefix):].replace("-", "+").replace("_", "/")
        self.assertEqual(json.loads(gzip.decompress(base64.b64decode(payload))), q.to_json())

    def test_rate_limiter(self):
        rl = trade.RateLimiter()
        rl.after({"x-rate-limit-rules": "Ip", "x-rate-limit-ip": "5:10:60", "x-rate-limit-ip-state": "4:10:0"})
        self.assertGreater(rl.wait_until, 0)


class NinjaTest(unittest.TestCase):
    def test_slugs_and_url(self):
        self.assertEqual(compare.ninja_league_slug("Hardcore Covens"), "covenshc")
        self.assertEqual(compare.ninja_league_slug("Standard"), "standard")
        url = compare.ninja_builds_url("Covens", "Toxic Rain", "Deadeye")
        self.assertEqual(urllib.parse.urlparse(url).path, "/poe1/builds/covens")
        self.assertIn("skills=Toxic+Rain", url)


if __name__ == "__main__":
    unittest.main()
