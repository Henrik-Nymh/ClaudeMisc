# poe1-build-helper

**Status:** in progress · **Started:** 2026-11-22

## What

A command-line helper for analysing Path of Exile 1 builds and finding upgrades.
It reads Path of Building (PoB) export codes. It can:

- summarize a build: stats, gems, gear with mods, passive tree
- build official trade-site searches, either from an equipped item ("find
  something at least this good") or from explicit filters
- compare your build with someone else's
- link to poe.ninja builds that use the same main skill

It uses only the Python standard library (3.10+). Game data (passive trees and
trade stat ids) is downloaded from the
[Path of Building repo](https://github.com/PathOfBuildingCommunity/PathOfBuilding)
and cached in `.cache/`. Those files are parsed as data and never executed.

## Getting your character in

The best input is a **Path of Building export**:

1. In Path of Building Community, go to *Import/Export Build*, then *Import from
   website*. Enter your account (`Name#1234`) and pick the character. The
   *Characters* tab on your profile must be public, or you must log in through PoB.
2. Under *Export*, click *Generate*, then *Share* (pobb.in) to get a link, or
   copy the code.
3. Give the link or code to this tool, or to Claude.

The code holds everything: tree, items with all mods, gems, PoB config, and
the stats PoB calculated at export time.

## Run

From this folder:

```bash
python3 -m poe1 summary https://pobb.in/XXXX          # or a code, .xml file, or - for stdin
python3 -m poe1 summary build.txt --tree-stats --all-stats
python3 -m poe1 trade item build.txt --slot Helmet --league Covens --max-price 50
python3 -m poe1 trade item build.txt --slot "Ring 1" --scale 0.8 --links-min 0
python3 -m poe1 trade query --league Covens --category accessory.amulet \
    --stat "pseudo.pseudo_total_life>=60" --stat "+#% to all Elemental Resistances>=10"
python3 -m poe1 trade query --league Covens --category armour.boots \
    --weight "+# total maximum Life=1" --weight "+#% total Elemental Resistance=1" --weight-min 150
python3 -m poe1 stats suppress spell                    # look up trade stat ids
python3 -m poe1 similar build.txt --league Covens       # poe.ninja link, same skill + ascendancy
python3 -m poe1 compare mine.txt theirs.txt --mods      # diff stats, gems, gear, tree
python3 -m poe1 decode build.txt -o build.xml
python3 -m poe1 data                                    # refresh cached game data
```

Set `POE1_LEAGUE=Covens` to skip `--league`. Run the tests with
`python3 -m unittest discover -s tests`.

### Live trade results (`--live`)

Without `--live` you get a trade-site link to open in a browser. That always
works. With `--live` the tool also calls the trade API and prints the cheapest
listings. Notes on that:

- GGG blocks the trade API from datacenter IPs, Claude's cloud sessions
  included. Run `--live` on your own machine.
- PoB only calls the API when you are logged in. Unauthenticated calls may be
  refused or have low rate limits. If so, you can set `POESESSID` to your
  pathofexile.com session cookie in your own shell. **That cookie gives full
  access to your account.** Keep it only in your environment, never in a file
  in this repo, and never paste it into chat.
- The client follows GGG's `X-Rate-Limit-*` headers and does not retry 401/403
  responses, because GGG restricts clients that make many failed requests.
- Set `POE1_USER_AGENT` if you want to add contact details, as GGG asks of tools.

## Notes

- **Stats come from PoB at export time** and depend on the build's PoB config
  (boss, charges, buffs). When comparing builds, check the config section first.
- **Item to query:** life, energy shield, resistances and attributes are summed
  into pseudo stats (for example `+#% total Elemental Resistance`). Other mods
  become individual filters at `value * scale`, so 0.9 means "at least 90% of
  what I have". Small values (5 or less) are kept as they are. Crafted mods and
  enchants are skipped unless you ask for them. For weapons the base type is
  used, because the weapon category is not known.
- **poe.ninja:** its builds, profile and character endpoints are internal and
  not for third-party use, according to its API docs. So `similar` only builds
  a link to open in a browser. The filter parameter names (`class`, `skills`)
  are unverified, because the site blocks automated fetches. If the filter
  doesn't apply, take the URL from the address bar after filtering by hand,
  and fix `ninja_builds_url`.
- **Not done yet:** exact DPS/EHP deltas for a candidate item. That needs
  running PoB headless (LuaJIT + PoB source). It works technically, but is not
  set up, because it means running downloaded third-party code.
- The trade link format (gzip + base64url in the path) is the one PoB uses.
