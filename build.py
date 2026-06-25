"""
Build a self-contained Minebox crafting browser (single HTML file).

Reads the cached API dumps in ./data (recipes_*.json, harvestables.json,
items_p*.json) and emits index.html with all data embedded.

Run `python fetch_data.py` first to populate ./data, then `python build.py`.

Data sources (api.minebox.co):
  /recipes?job=X  -> craftable items + ingredient trees (13 jobs)
  /harvestables   -> drop nodes with per-item drop % (chance)
  /items          -> name / rarity / level / type / inline base64 image
"""
import json, glob, os

SRC = os.path.join(os.path.dirname(__file__), "data")
OUT = os.path.join(os.path.dirname(__file__), "index.html")

# ---- load recipes -----------------------------------------------------------
recipes = {}
for f in glob.glob(os.path.join(SRC, "recipes_*.json")):
    for r in (json.load(open(f)).get("recipes") or []):
        recipes[r["id"]] = {
            "name": r.get("name") or r["id"],
            "job": r.get("job", ""),
            "amount": r.get("amount", 1) or 1,
            "ingredients": [
                {"id": i["id"], "amount": i.get("amount", 1), "type": i.get("type", "custom")}
                for i in r.get("ingredients", [])
            ],
        }

# ---- load harvestables -> drop index ---------------------------------------
CAT_PREFIXES = ("mbi", "material", "mbc", "block")
def strip_prefix(s):
    if "-" in s:
        pre, rest = s.split("-", 1)
        if pre in CAT_PREFIXES:
            return rest
    return s

harv_raw = json.load(open(os.path.join(SRC, "harvestables.json")))
nodes = harv_raw if isinstance(harv_raw, list) else list(harv_raw.values())[0]
drop_index = {}
for n in nodes:
    drops = n.get("drops", [])
    nid = n.get("id", "")
    for d in drops:
        key = strip_prefix(d["item"])
        # primary = this node IS the source for this item: the only drop, or the
        # node's eponymous yield (ore_cobalt node -> ore_cobalt). Its `chance`
        # is a weight (often 1), NOT a meaningful percent, so don't show it.
        primary = len(drops) == 1 or key == nid or nid.endswith(key) or key.endswith(nid)
        drop_index.setdefault(key, []).append({
            "node": n.get("name") or nid,
            "category": n.get("category", ""),
            "min_level": n.get("min_level"),
            "chance": d.get("chance", 0),
            "amount": d.get("amount", 1),
            "primary": primary,
        })
# best source first: primary nodes, then highest real drop %
for k in drop_index:
    drop_index[k].sort(key=lambda x: (not x["primary"], -(x["chance"] or 0)))

# ---- load full item metadata (name/rarity/level/type/image) ----------------
items_full = {}
for f in glob.glob(os.path.join(SRC, "items_p*.json")):
    for it in json.load(open(f)).get("items", []):
        items_full[it["id"]] = it

# ---- stat metadata (/attributes) + vanilla icon fallbacks ------------------
attrs = {}   # lower-id -> {name, color}
ap = os.path.join(SRC, "attributes.json")
if os.path.exists(ap):
    araw = json.load(open(ap, encoding="utf-8", errors="replace"))
    alist = araw if isinstance(araw, list) else list(araw.values())[0]
    for a in alist:
        attrs[a["id"].lower()] = {"name": a.get("name"), "color": a.get("color")}

vanilla_icons = {}
vp = os.path.join(SRC, "vanilla_icons.json")
if os.path.exists(vp):
    vanilla_icons = json.load(open(vp))

relic_stats = {}   # relicId -> {stat: value}
rp = os.path.join(SRC, "relics.json")
if os.path.exists(rp):
    rraw = json.load(open(rp))
    rlist = rraw if isinstance(rraw, list) else list(rraw.values())[0]
    for r in rlist:
        relic_stats[r["id"]] = r.get("stats") or {}

# ---- set bonuses (/sets) ---------------------------------------------------
# item.set is a display name (e.g. "Astral set"); match it to the set def's
# `name`. bonuses are keyed by piece-count threshold and are the CUMULATIVE
# total at that threshold (wear N pieces -> take the highest threshold <= N).
sets_by_name = {}   # set display-name -> {id, name, bonuses}
sp = os.path.join(SRC, "sets.json")
if os.path.exists(sp):
    sraw = json.load(open(sp, encoding="utf-8", errors="replace"))
    slist = sraw.get("sets") if isinstance(sraw, dict) else sraw
    for s in (slist or []):
        nm = s.get("name")
        if nm:
            sets_by_name[nm] = {"id": s.get("id"), "name": nm, "bonuses": s.get("bonuses") or {}}

# ---- type -> friendly category ---------------------------------------------
CATS = [
    ("Weapons",       {"LONG_SWORD","SWORD","DAGGER","BOW","GUN","STAFF","HAMMER"}),
    ("Armor",         {"HELMET","CHESTPLATE","LEGGINGS","BOOTS","BACK"}),
    ("Accessories",   {"RING","NECKLACE","BELT","GLOVES"}),
    ("Tools",         {"HARVESTER","FISHING_ROD","WATERING_CAN","BUCKET","VANILLA_TOOL",
                        "COMPACTOR","BLOCK_STICK","SPONGE","BLOWER","GHOST_VACUUM"}),
    ("Consumables",   {"EDIBLE","CONSUMABLE","CANDY","JELLY","DIVORCE_POTION","SCROLL",
                        "EXPERIENCE_TOME","SKILL_EXPERIENCE_TOME","BASKET_SEEDS"}),
    ("Pets & Mounts", {"PET","MOUNT","SOUL","EGG_INCUBATOR","KIBBLE","SPAWNER"}),
    ("Runes & Magic", {"RUNE","RELIC","SCROLL"}),
    ("Storage",       {"INFINITE_BAG","INFINITE_CHEST","INFINITE_BAG_MODULE","BAG"}),
    ("Furniture",     {"FURNITURE","JUKEBOX","TELEPORTER","JUMP_PAD","WORKSHOP","VILLAGE","MUSIC_DISC"}),
    ("Ships",         {"SHIP","SHIP_COMPONENT"}),
]
TYPE2CAT = {t: name for name, types in CATS for t in types}
CAT_ORDER = [name for name, _ in CATS] + ["Materials", "Other"]

def category_of(idstr, itype, craftable):
    if itype in TYPE2CAT:
        return TYPE2CAT[itype]
    if itype in ("INGREDIENT", "VEIN") or itype is None:
        return "Materials"
    return "Other"

def prettify(idstr):
    return " ".join(w.capitalize() for w in idstr.replace("-", " ").replace("_", " ").split())

# ---- assemble searchable universe ------------------------------------------
all_ids = set(recipes.keys())
for r in recipes.values():
    for i in r["ingredients"]:
        all_ids.add(i["id"])
for k in drop_index:
    all_ids.add(k)

items = {}
for idstr in all_ids:
    m = items_full.get(idstr) or items_full.get(strip_prefix(idstr)) or {}
    craftable = idstr in recipes
    name = m.get("name") or (recipes[idstr]["name"] if craftable else prettify(idstr))
    itype = m.get("type")
    entry = {
        "id": idstr,
        "name": name,
        "rarity": m.get("rarity"),
        "level": m.get("level"),
        "type": itype,
        "cat": category_of(idstr, itype, craftable),
        "craftable": craftable,
        "sources": drop_index.get(idstr) or drop_index.get(strip_prefix(idstr)) or [],
    }
    img = m.get("image") or vanilla_icons.get(idstr)
    if img:
        entry["img"] = img   # raw base64 png, data: prefix added in JS
    if m.get("stats"):
        entry["stats"] = m["stats"]       # {STAT: [min,max]}
    if m.get("damages"):
        entry["damages"] = m["damages"]   # {ELEMENT: [min,max]}
    if m.get("set"):
        entry["set"] = m["set"]           # set display-name (links to DATA.sets)
    items[idstr] = entry

data = {"items": items, "recipes": recipes, "catOrder": CAT_ORDER,
        "attrs": attrs, "relics": relic_stats, "sets": sets_by_name}
blob = json.dumps(data, separators=(",", ":"))

ncat = {}
for it in items.values():
    ncat[it["cat"]] = ncat.get(it["cat"], 0) + 1
print("items:", len(items), "recipes:", len(recipes),
      "with-img:", sum(1 for i in items.values() if i.get("img")),
      "size:", f"{len(blob)//1024} KB")
print("by category:", {c: ncat.get(c, 0) for c in CAT_ORDER})

# ---- HTML -------------------------------------------------------------------
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minebox Crafting Browser</title>
<style>
:root{
  --bg:#14181c; --panel:#1b2127; --panel2:#222a31; --line:#2c353d;
  --text:#e6edf3; --muted:#93a1ad; --accent:#1D9E75; --accent2:#5DCAA5;
}
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:#33414c transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#2c353d;border-radius:8px;border:2px solid var(--bg);background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:#3f4c57;background-clip:padding-box}
::-webkit-scrollbar-corner{background:transparent}
body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{padding:16px 20px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{margin:0 0 10px;font-size:18px;font-weight:600}
h1 span{color:var(--accent2)}
.search{display:flex;gap:10px;align-items:center}
#q{flex:1;max-width:520px;padding:10px 12px;border-radius:8px;border:1px solid var(--line);
   background:var(--panel);color:var(--text);font-size:14px;outline:none}
#q:focus{border-color:var(--accent)}
.count{color:var(--muted);font-size:12px}
.wrap{display:grid;grid-template-columns:268px 430px minmax(0,1fr);gap:0;min-height:calc(100vh - 84px)}
.list{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 84px)}
.charcol{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 84px);padding:14px 14px 24px}
.charhdr{font-size:15px;font-weight:600;margin-bottom:12px}
.charhdr2{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 8px}
.charstats{margin-top:16px;border-top:1px solid var(--line);padding-top:14px}
.charbtn-narrow{display:none}
@media(max-width:1180px){
  .wrap{grid-template-columns:268px minmax(0,1fr)}
  .charcol{display:none}
  .charbtn-narrow{display:inline-block}
}
.cathd{display:flex;align-items:center;gap:8px;padding:9px 14px;cursor:pointer;
   background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;font-weight:500}
.cathd:hover{background:var(--panel2)}
.cathd .tw{width:14px;color:var(--muted)}
.cathd .cc{margin-left:auto;color:var(--muted);font-size:11px;font-weight:400}
.cathd .dot{width:8px;height:8px;border-radius:2px;background:var(--accent)}
.row{padding:7px 14px 7px 28px;cursor:pointer;border-bottom:1px solid var(--line);
   display:flex;gap:9px;align-items:center}
.row:hover{background:var(--panel)}
.row.sel{background:var(--panel2)}
.ico{width:26px;height:26px;flex:none;image-rendering:pixelated;object-fit:contain;
   background:#0d1014;border-radius:5px;border:1px solid var(--line)}
.ico.ph{display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px}
.row .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .lv{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.rdot{width:7px;height:7px;border-radius:50%;flex:none}
.tagdot{width:7px;height:7px;border-radius:2px;flex:none}
.detail{padding:20px 24px;overflow:auto;max-height:calc(100vh - 84px)}
.empty{color:var(--muted);margin-top:40px;text-align:center}
.hd{display:flex;align-items:center;gap:14px;margin-bottom:4px}
.hd .bigico{width:48px;height:48px;image-rendering:pixelated;object-fit:contain;
   background:#0d1014;border-radius:8px;border:1px solid var(--line)}
.hd h2{margin:0;font-size:20px}
.hd .meta{display:flex;gap:8px;align-items:center;margin-top:3px}
.sub{color:var(--muted);font-size:12px;margin-bottom:14px}
.rar{font-size:11px;padding:1px 8px;border-radius:10px}
.lvtag{font-size:11px;padding:1px 8px;border-radius:10px;color:var(--muted);border:1px solid var(--line)}
.section{margin-top:24px}
.section h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 8px}
.tree{margin-top:6px}
.node{margin:1px 0}
.node .bar{display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:6px}
.node .bar:hover{background:var(--panel)}
.tw{display:inline-flex;width:14px;justify-content:center;color:var(--muted);cursor:pointer;user-select:none}
.tico{width:20px;height:20px;image-rendering:pixelated;object-fit:contain;border-radius:4px;background:#0d1014;flex:none}
.qty{color:var(--accent2);font-variant-numeric:tabular-nums;min-width:30px}
.nname{font-weight:500}
.job{font-size:10px;color:var(--muted);border:1px solid var(--line);border-radius:10px;padding:0 6px}
.src{font-size:11px;color:var(--muted)}
.children{margin-left:16px;border-left:1px solid var(--line);padding-left:6px}
.collapsed>.children{display:none}
table.roll{border-collapse:collapse;width:100%;max-width:680px}
.roll td,.roll th{text-align:left;padding:5px 10px;border-bottom:1px solid var(--line);font-size:13px}
.roll th{color:var(--muted);font-weight:500;font-size:11px;text-transform:uppercase}
.roll td.n{text-align:right;color:var(--accent2);font-variant-numeric:tabular-nums}
.roll td.ic{width:30px;padding-right:0}
.pct{color:var(--accent2)}
.base{color:var(--muted)}
.legend{font-size:11px;color:var(--muted);margin-top:6px}
.tags{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:10px}
.chip{font-size:11px;padding:2px 9px;border-radius:11px;display:inline-flex;align-items:center;gap:6px}
.chip .x{cursor:pointer;opacity:.6}.chip .x:hover{opacity:1}
.addbtn{font-size:11px;padding:2px 9px;border-radius:11px;border:1px dashed var(--line);
   color:var(--muted);cursor:pointer;background:none}
.addbtn:hover{border-color:var(--accent);color:var(--accent2)}
.tageditor{margin-top:8px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel);
   display:none;gap:8px;flex-wrap:wrap;align-items:center;max-width:560px}
.tageditor.on{display:flex}
.tageditor input[type=text]{padding:6px 9px;border-radius:6px;border:1px solid var(--line);
   background:var(--bg);color:var(--text);font-size:13px;flex:1;min-width:120px}
.swatches{display:flex;gap:5px}
.sw{width:18px;height:18px;border-radius:5px;cursor:pointer;border:2px solid transparent}
.sw.on{border-color:#fff}
.tageditor button{padding:6px 12px;border-radius:6px;border:none;background:var(--accent);color:#04221a;
   font-weight:600;cursor:pointer;font-size:13px}
.exist{display:flex;gap:5px;flex-wrap:wrap;flex-basis:100%}
.exist .chip{cursor:pointer;opacity:.75}.exist .chip:hover{opacity:1}
.listbtn{margin-left:auto;padding:9px 14px;border-radius:8px;border:1px solid var(--line);
   background:var(--panel);color:var(--text);cursor:pointer;font-size:13px;white-space:nowrap}
.listbtn:hover{border-color:var(--accent)}
.listbtn span{color:#04221a;background:var(--accent2);border-radius:9px;padding:0 7px;margin-left:4px;font-weight:600}
.addrow{display:flex;gap:12px;align-items:center;margin:12px 0 2px}
.addlist{padding:8px 15px;border-radius:7px;border:none;background:var(--accent);color:#04221a;
   font-weight:600;cursor:pointer;font-size:13px}
.addlist:hover{filter:brightness(1.08)}
.qstep{display:inline-flex;gap:8px;align-items:center;color:var(--muted);font-size:13px}
.qstep button{width:24px;height:24px;border-radius:6px;border:1px solid var(--line);
   background:var(--panel);color:var(--text);cursor:pointer;font-size:15px;line-height:1;padding:0}
.qstep button:hover{border-color:var(--accent)}
.qstep b{min-width:22px;text-align:center;color:var(--text)}
.modetoggle{display:inline-flex;gap:6px;margin-left:12px;vertical-align:middle}
.modetoggle button{font-size:11px;padding:2px 10px;border-radius:8px;border:1px solid var(--line);
   background:none;color:var(--muted);cursor:pointer;text-transform:none;letter-spacing:0}
.modetoggle button.on{background:var(--accent);color:#04221a;border-color:var(--accent);font-weight:600}
.havein{width:58px;padding:4px 6px;border-radius:6px;border:1px solid var(--line);
   background:var(--bg);color:var(--text);font-size:13px;text-align:right}
.havechk{width:16px;height:16px;cursor:pointer;accent-color:var(--accent)}
tr.doneRow{opacity:.5}
tr.doneRow .mname{text-decoration:line-through}
.left{color:var(--accent2);font-weight:500}
.left.zero{color:var(--muted);font-weight:400}
.rm{cursor:pointer;color:#E24B4A;font-size:12px}.rm:hover{text-decoration:underline}
#clearlist{background:none;border:1px solid var(--line);color:var(--muted);border-radius:6px;
   padding:3px 12px;cursor:pointer;font-size:12px}
#clearlist:hover{border-color:#E24B4A;color:#E24B4A}
.progress{height:6px;border-radius:3px;background:var(--line);overflow:hidden;max-width:680px;margin:2px 0 14px}
.progress>span{display:block;height:100%;background:var(--accent)}
.statgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:4px 18px;max-width:680px}
.stat{display:flex;align-items:center;justify-content:space-between;padding:4px 0;
   border-bottom:1px solid var(--line);font-size:13px}
.statn{display:flex;align-items:center;gap:7px;color:var(--text)}
.statdot{width:8px;height:8px;border-radius:2px;flex:none}
.statv{font-variant-numeric:tabular-nums;font-weight:500}
.charwrap{display:flex;gap:32px;flex-wrap:wrap;align-items:flex-start;margin-top:6px}
.charleft{flex:0 0 auto}
.skinwrap{display:flex;flex-direction:column;align-items:center;margin-bottom:14px}
#skinview{width:200px;height:300px;border:1px solid var(--line);border-radius:10px;background:#0d1014;cursor:grab}
.charcol .userrow{margin-bottom:14px}
.charcol .slotgrid{margin-bottom:8px}
.isummary{max-width:560px}
.charright{flex:1;min-width:260px;max-width:460px}
.charright h3{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 10px}
.userrow{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.userrow input{padding:8px 10px;border-radius:7px;border:1px solid var(--line);
   background:var(--panel);color:var(--text);font-size:13px;width:230px}
.userrow button{padding:8px 14px;border-radius:7px;border:none;background:var(--accent);
   color:#04221a;font-weight:600;cursor:pointer;font-size:13px}
.slotgrid{display:grid;grid-template-columns:repeat(3,118px);gap:10px}
.slot{position:relative;height:118px;border:1px solid var(--line);border-radius:10px;background:var(--panel);
   display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;transition:border-color .1s}
.slot.filled{background:var(--panel2);cursor:pointer}
.slot.drop{border-color:var(--accent);background:#10261f}
.slot.bad{border-color:#E24B4A;animation:shake .3s}
@keyframes shake{25%{transform:translateX(-3px)}75%{transform:translateX(3px)}}
.slotico{width:50px;height:50px;image-rendering:pixelated;object-fit:contain}
.slotph{width:42px;height:42px;border-radius:8px;border:1px dashed var(--line)}
.slotlabel{font-size:11px;color:var(--muted);text-align:center;padding:0 5px;max-width:110px;
   overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slot.filled .slotlabel{color:var(--text)}
.slotx{position:absolute;top:5px;right:7px;color:#E24B4A;font-size:12px;cursor:pointer;opacity:.55}
.slotx:hover{opacity:1}
.handrow{width:374px;margin-top:10px}
.handrow .slot{height:66px;flex-direction:row;justify-content:flex-start;gap:14px;padding:0 16px}
.handrow .slotico{width:42px;height:42px}
.handrow .slotph{width:36px;height:36px}
.handrow .slotlabel{max-width:none;font-size:13px;text-align:left}
.tip{position:fixed;z-index:50;display:none;background:#0d1014;border:1px solid var(--line);
   border-radius:8px;padding:9px 11px;font-size:12px;max-width:240px;pointer-events:none}
.tip b{font-size:13px;margin-right:6px}.tiprows{margin-top:6px;display:flex;flex-direction:column;gap:2px}
.tipsrc{display:flex;justify-content:space-between;gap:16px}
.tipsrc span:last-child{color:var(--accent2);font-variant-numeric:tabular-nums}
.statrow{cursor:default}
.row[draggable=true]{cursor:grab}
.listtabs{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-bottom:16px}
.ltab{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:9px;border:1px solid var(--line);
   background:var(--panel);color:var(--muted);cursor:pointer;font-size:13px;user-select:none}
.ltab:hover{border-color:var(--accent)}
.ltab.on{background:var(--panel2);color:var(--text);border-color:var(--accent);font-weight:500}
.ltab .cnt{font-size:11px;color:#04221a;background:var(--accent2);border-radius:8px;padding:0 6px;font-weight:600}
.ltab.on .cnt{color:#04221a}
.ltab .lx{opacity:.45;font-size:11px}.ltab .lx:hover{opacity:1;color:#E24B4A}
.ltab.add{border-style:dashed}
.rmall{float:right;font-size:11px;padding:2px 11px;border-radius:8px;border:1px solid var(--line);
   background:none;color:var(--muted);cursor:pointer;text-transform:none;letter-spacing:0;font-weight:500}
.rmall:hover{border-color:#E24B4A;color:#E24B4A}
.rmall.equipall:hover{border-color:var(--accent);color:var(--accent2)}
.setbonus{display:flex;flex-direction:column;gap:4px;margin-bottom:12px;font-size:13px;max-width:560px}
.setrow b{display:inline-block;min-width:42px;color:var(--accent2);margin-right:10px;font-variant-numeric:tabular-nums}
.setpieces{display:flex;flex-wrap:wrap;gap:7px;max-width:600px}
.setpiece{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:4px 9px;border-radius:8px;
   border:1px solid var(--line);background:var(--panel);cursor:pointer;color:var(--muted)}
.setpiece:hover{border-color:var(--accent);color:var(--text)}
.setpiece.cur{border-color:var(--accent);color:var(--text);background:var(--panel2)}
.setpiece .tico{width:18px;height:18px}
.optchips{display:flex;flex-wrap:wrap;gap:8px;max-width:780px}
.optchip{font-size:13px;padding:5px 13px;border-radius:18px;border:1px solid var(--line);
   background:var(--panel);color:var(--muted);cursor:pointer;user-select:none}
.optchip:hover{border-color:var(--accent)}
.optchip.on{font-weight:600}
.lvlslider{width:100%;max-width:520px;accent-color:var(--accent);cursor:pointer;margin:2px 0}
.optbuild{border:1px solid var(--line);border-radius:12px;padding:15px 18px;margin-bottom:18px;background:var(--panel)}
.optbuildhd{display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.optbuildhd .rmall{float:none}
.optrank{font-size:18px;font-weight:700;color:var(--accent2)}
.optscore{font-size:13px;color:var(--text);background:var(--panel2);border:1px solid var(--line);
   border-radius:8px;padding:2px 10px;font-variant-numeric:tabular-nums}
.optequip{margin-left:auto}
</style></head>
<body>
<header>
  <h1>Minebox <span>Crafting Browser</span></h1>
  <div class="search">
    <input id="q" placeholder="Search items, or browse categories on the left..." autocomplete="off">
    <span class="count" id="count"></span>
    <button class="listbtn" id="optbtn">Optimizer</button>
    <button class="listbtn charbtn-narrow" id="charbtn">Character</button>
    <button class="listbtn" id="listbtn">Craft list <span id="listn">0</span></button>
  </div>
</header>
<div class="wrap">
  <div class="list" id="list"></div>
  <div class="charcol" id="charcol"></div>
  <div class="detail" id="detail"><div class="empty">Pick a category on the left, or search, then click an item.</div></div>
</div>
<script>
const DATA = __DATA__;
const ITEMS = DATA.items, RECIPES = DATA.recipes, CAT_ORDER = DATA.catOrder, ATTR = DATA.attrs||{}, RELICS = DATA.relics||{}, SETS = DATA.sets||{};
const RAR_COLORS = {COMMON:'#93a1ad',UNCOMMON:'#63a022',RARE:'#378ADD',EPIC:'#7F77DD',LEGENDARY:'#EF9F27',MYTHIC:'#D4537E'};
const TAG_PALETTE = ['#E24B4A','#EF9F27','#63a022','#1D9E75','#378ADD','#7F77DD','#D4537E','#93a1ad'];
const list=document.getElementById('list'), detail=document.getElementById('detail'),
      q=document.getElementById('q'), countEl=document.getElementById('count');
let sel=null, tagFilter=null;
const openCats=new Set();

// ---- custom tags (localStorage) -------------------------------------------
let TAGS = JSON.parse(localStorage.getItem('mb_tags')||'{}');          // {name:color}
let ITEMTAGS = JSON.parse(localStorage.getItem('mb_itemtags')||'{}');   // {itemId:[name,...]}
function saveTags(){localStorage.setItem('mb_tags',JSON.stringify(TAGS));
  localStorage.setItem('mb_itemtags',JSON.stringify(ITEMTAGS));}
function itemTags(id){return ITEMTAGS[id]||[];}
function assignTag(id,name){const t=ITEMTAGS[id]||[]; if(!t.includes(name))t.push(name);
  ITEMTAGS[id]=t; saveTags();}
function unassignTag(id,name){ITEMTAGS[id]=(ITEMTAGS[id]||[]).filter(x=>x!==name);
  if(!ITEMTAGS[id].length)delete ITEMTAGS[id]; saveTags();}
function tagCount(name){return Object.values(ITEMTAGS).filter(a=>a.includes(name)).length;}

// ---- craft lists / planner (localStorage, up to 5 named lists) ------------
// BUILD/HAVE always point at the ACTIVE list's items/have objects.
const MAXLISTS=5;
let LISTS = JSON.parse(localStorage.getItem('mb_lists')||'null');  // {id:{name,items,have}}
let ACTIVE = localStorage.getItem('mb_active')||'';
if(!LISTS){   // migrate the old single mb_build/mb_have into list 1
  LISTS={l1:{name:'My craft list',
    items:JSON.parse(localStorage.getItem('mb_build')||'{}'),
    have :JSON.parse(localStorage.getItem('mb_have')||'{}')}};
  ACTIVE='l1';
}
if(!LISTS[ACTIVE]) ACTIVE=Object.keys(LISTS)[0];
let BUILD=LISTS[ACTIVE].items, HAVE=LISTS[ACTIVE].have;
let listMode='raw', viewingList=false;
function saveLists(){localStorage.setItem('mb_lists',JSON.stringify(LISTS));
  localStorage.setItem('mb_active',ACTIVE);}
function saveBuild(){saveLists(); updateListN();}
function saveHave(){saveLists();}
function updateListN(){document.getElementById('listn').textContent=Object.keys(BUILD).length;}
function addToBuild(id,qty){BUILD[id]=(BUILD[id]||0)+qty; saveBuild();}
function clearActiveList(){LISTS[ACTIVE].items={}; LISTS[ACTIVE].have={};
  BUILD=LISTS[ACTIVE].items; HAVE=LISTS[ACTIVE].have; saveLists(); updateListN();}
function setActiveList(id){if(!LISTS[id])return; ACTIVE=id; BUILD=LISTS[id].items; HAVE=LISTS[id].have;
  saveLists(); updateListN(); showList();}
function newList(){const ids=Object.keys(LISTS); if(ids.length>=MAXLISTS)return;
  let i=1; while(LISTS['l'+i])i++; const id='l'+i;
  LISTS[id]={name:'List '+(ids.length+1),items:{},have:{}}; setActiveList(id);}
function renameList(id){const cur=LISTS[id]; if(!cur)return;
  const nm=prompt('Rename list:',cur.name); if(nm&&nm.trim()){cur.name=nm.trim().slice(0,28); saveLists(); showList();}}
function deleteList(id){
  if(Object.keys(LISTS).length<=1){LISTS[id].items={}; LISTS[id].have={}; setActiveList(id); return;}
  if(!confirm('Delete list "'+LISTS[id].name+'"?'))return;
  delete LISTS[id]; if(ACTIVE===id)ACTIVE=Object.keys(LISTS)[0];
  BUILD=LISTS[ACTIVE].items; HAVE=LISTS[ACTIVE].have; saveLists(); updateListN(); showList();}
saveLists();   // persist the migrated/normalized shape on first load
// aggregate raw materials (leaves) across the whole craft list
function rawAgg(){const acc={}; for(const [id,q] of Object.entries(BUILD)) rollup(id,q,new Set(),acc); return acc;}
// aggregate EVERY component (intermediates + raws) once each, excluding the target items
function walkBom(id,mult,stack,acc,isTop){
  if(!isTop) acc[id]=(acc[id]||0)+mult;
  const rec=RECIPES[id];
  if(!rec||stack.has(id)) return;
  const ns=new Set(stack); ns.add(id); const per=rec.amount||1;
  for(const ing of rec.ingredients) walkBom(ing.id,mult*ing.amount/per,ns,acc,false);}
function bomAgg(){const acc={}; for(const [id,q] of Object.entries(BUILD)) walkBom(id,q,new Set(),acc,true); return acc;}

// ---- character / equipment loadout ----------------------------------------
let EQUIP = JSON.parse(localStorage.getItem('mb_equip')||'{}');   // {slotKey:itemId}
let BASESTATS = JSON.parse(localStorage.getItem('mb_basestats')||'null'); // {base:{},scrolls:{}}
let BASENAME = localStorage.getItem('mb_basename')||'';
function saveEquip(){localStorage.setItem('mb_equip',JSON.stringify(EQUIP));}
// slot key -> {label, type(s) accepted, row, col}
const SLOTS=[
  {k:'necklace',label:'Necklace',types:['NECKLACE']},
  {k:'helmet',  label:'Helmet',  types:['HELMET']},
  {k:'ring1',   label:'Ring',    types:['RING']},
  {k:'back',    label:'Back',    types:['BACK']},
  {k:'chest',   label:'Chest',   types:['CHESTPLATE']},
  {k:'ring2',   label:'Ring',    types:['RING']},
  {k:'belt',    label:'Belt',    types:['BELT']},
  {k:'legs',    label:'Legs',    types:['LEGGINGS']},
  {k:'gloves',  label:'Gloves',  types:['GLOVES']},
  {k:'mount',   label:'Mount',   types:['MOUNT']},
  {k:'boots',   label:'Boots',   types:['BOOTS']},
  {k:'pet',     label:'Pet',     types:['PET']},
];
// hand = held weapon or tool (rendered separately, below the armor grid)
const HAND={k:'hand',label:'Hand (weapon / tool)',types:['LONG_SWORD','SWORD','DAGGER','BOW','GUN','STAFF','HAMMER',
  'HARVESTER','FISHING_ROD','WATERING_CAN','BUCKET','VANILLA_TOOL','COMPACTOR','BLOCK_STICK','SPONGE','BLOWER','GHOST_VACUUM']};
const ALLSLOTS=SLOTS.concat([HAND]);
const SLOTBYKEY=Object.fromEntries(ALLSLOTS.map(s=>[s.k,s]));
function slotForType(t){return ALLSLOTS.filter(s=>s.types.includes(t));}
function canEquip(it){return it&&it.type&&slotForType(it.type).length>0;}
function slotHTML(s,eq,readonly){eq=eq||EQUIP; const id=eq[s.k], it=id?ITEMS[id]:null;
  return `<div class="slot${it?' filled':''}" data-slot="${s.k}" data-types="${s.types.join(',')}"${it?` data-itemid="${id}"`:''}>
    ${it?imgFor(id,'slotico'):'<span class="slotph"></span>'}
    <span class="slotlabel">${it?it.name:s.label}</span>
    ${(it&&!readonly)?`<span class="slotx" data-unequip="${s.k}">✕</span>`:''}</div>`;}
// aggregate base + scrolls + relics + equipped gear into per-stat totals,
// keeping a per-source breakdown for the hover tooltip
function equipStats(){
  const tot={};
  function ent(k){k=k.toLowerCase(); return tot[k]||(tot[k]={min:0,max:0,gearMin:0,gearMax:0,sources:[]});}
  function add(name,stat,mn,mx,isGear){const e=ent(stat); e.min+=mn; e.max+=mx;
    if(isGear){e.gearMin+=mn; e.gearMax+=mx;} e.sources.push({name,min:mn,max:mx});}
  if(BASESTATS){
    const lbl={base:'Base',scrolls:'Scrolls',relics:'Relics'};
    for(const src of ['base','scrolls','relics'])
      for(const [k,v] of Object.entries(BASESTATS[src]||{})) if(v) add(lbl[src],k,v,v,false);
  }
  for(const id of Object.values(EQUIP)){const it=ITEMS[id]; if(!it)continue;
    if(it.stats) for(const [k,r] of Object.entries(it.stats)) add(it.name,k,r[0],r[1],true);
    if(it.damages) for(const [k,r] of Object.entries(it.damages)) add(it.name,'dmg:'+k,r[0],r[1],true);}
  for(const sb of setBonusSources(Object.values(EQUIP)))
    for(const [k,v] of Object.entries(sb.stats)) add(sb.name,k,v,v,true);
  return tot;
}
// set bonuses: count equipped pieces per set, take the highest threshold <= count
function setBonusSources(ids){
  const cnt={};
  for(const id of ids){const it=ITEMS[id]; const s=it&&it.set; if(s)cnt[s]=(cnt[s]||0)+1;}
  const out=[];
  for(const [name,n] of Object.entries(cnt)){
    const def=SETS[name]; if(!def||!def.bonuses)continue;
    const ths=Object.keys(def.bonuses).map(Number).filter(t=>t<=n).sort((a,b)=>a-b);
    if(!ths.length)continue;
    out.push({name:name+' ('+n+' pc)', stats:def.bonuses[String(ths[ths.length-1])]});
  }
  return out;
}
// gear-only stat aggregation for an arbitrary item-id list (craft-list set)
function statsFromItems(ids){
  const tot={};
  function ent(k){k=k.toLowerCase(); return tot[k]||(tot[k]={min:0,max:0,gearMin:0,gearMax:0,sources:[]});}
  function add(name,stat,mn,mx){const e=ent(stat); e.min+=mn; e.max+=mx; e.gearMin+=mn; e.gearMax+=mx; e.sources.push({name,min:mn,max:mx});}
  for(const id of ids){const it=ITEMS[id]; if(!it)continue;
    if(it.stats) for(const [k,r] of Object.entries(it.stats)) add(it.name,k,r[0],r[1]);
    if(it.damages) for(const [k,r] of Object.entries(it.damages)) add(it.name,'dmg:'+k,r[0],r[1]);}
  for(const sb of setBonusSources(ids))
    for(const [k,v] of Object.entries(sb.stats)) add(sb.name,k,v,v);
  return tot;
}
// auto-place the equippable items in the craft list into a slot map (preview loadout)
function buildLoadout(){const map={};
  for(const id of Object.keys(BUILD)){const it=ITEMS[id]; if(!canEquip(it))continue;
    const slots=slotForType(it.type); const t=slots.find(s=>!map[s.k])||slots[0]; if(t)map[t.k]=id;}
  return map;}

function imgFor(id,cls){const it=ITEMS[id];
  if(it&&it.img) return `<img class="${cls}" src="data:image/png;base64,${it.img}" alt="">`;
  return `<span class="${cls} ph">·</span>`;}
function rarPill(r){if(!r)return ''; const c=RAR_COLORS[r]||'#93a1ad';
  return `<span class="rar" style="color:${c};border:1px solid ${c}">${r[0]+r.slice(1).toLowerCase()}</span>`;}
function rdot(r){if(!r)return '<span class="rdot"></span>'; const c=RAR_COLORS[r]||'#93a1ad';
  return `<span class="rdot" style="background:${c}"></span>`;}
function pretty(k){return k.toLowerCase().replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());}
function statName(k){if(k.startsWith('dmg:'))return pretty(k.slice(4))+' dmg';
  const a=ATTR[k.toLowerCase()]; return a&&a.name?a.name:pretty(k);}
function statColor(k){if(k.startsWith('dmg:'))return '#E24B4A';
  const a=ATTR[k.toLowerCase()]; return a&&a.color?a.color:'#93a1ad';}
function statRow(k,rng,suffix){const c=statColor(k);
  const v=rng[0]===rng[1]?rng[0]:`${rng[0]}–${rng[1]}`;
  return `<div class="stat"><span class="statn"><span class="statdot" style="background:${c}"></span>${statName(k)}${suffix||''}</span><span class="statv" style="color:${c}">+${v}</span></div>`;}
function statsBlock(it){
  const s=it.stats, d=it.damages; if(!s&&!d) return '';
  let rows='';
  if(d) for(const [k,r] of Object.entries(d)) rows+=statRow(k,r,' dmg');
  if(s) for(const [k,r] of Object.entries(s)) rows+=statRow(k,r,'');
  return `<div class="section"><h3>Stats</h3><div class="statgrid">${rows}</div>
    <div class="legend">ranges = the possible roll on this item</div></div>`;}
// set membership + per-threshold bonuses for an item that belongs to a set
function setBlock(it){
  const name=it.set; if(!name) return '';
  const def=SETS[name];
  const pieces=arr.filter(x=>x.set===name);
  let h=`<div class="section"><h3>Set — ${name}</h3>`;
  if(def&&def.bonuses&&Object.keys(def.bonuses).length){
    h+=`<div class="setbonus">`+Object.keys(def.bonuses).map(Number).sort((a,b)=>a-b).map(t=>{
      const st=def.bonuses[String(t)];
      const stats=Object.entries(st).map(([k,v])=>
        `<span style="color:${statColor(k)}">+${v} ${statName(k)}</span>`).join('  ');
      return `<div class="setrow"><b>${t} pc</b>${stats}</div>`;}).join('')+`</div>`;
  } else { h+=`<div class="src" style="margin-bottom:10px">no bonus data for this set</div>`; }
  if(pieces.length) h+=`<div class="setpieces">`+pieces.map(p=>
    `<span class="setpiece${p.id===it.id?' cur':''}" data-setid="${p.id}">${imgFor(p.id,'tico')}${p.name}</span>`).join('')+`</div>`;
  return h+`</div>`;
}
function wireSetPieces(){detail.querySelectorAll('[data-setid]').forEach(e=>
  e.onclick=()=>showItemSummary(e.dataset.setid));}

const arr=Object.values(ITEMS);
// every attribute stat that appears on equippable gear or in a set bonus,
// ordered to match the /attributes ordering (used by the optimizer chips)
const GEAR_STATS=(()=>{const s=new Set();
  for(const it of arr){ if(it.type&&it.stats) for(const k in it.stats) s.add(k.toLowerCase()); }
  for(const def of Object.values(SETS)) for(const th of Object.values(def.bonuses||{})) for(const k in th) s.add(k.toLowerCase());
  const ord=Object.keys(ATTR);
  return [...s].sort((a,b)=>((ord.indexOf(a)<0?99:ord.indexOf(a))-(ord.indexOf(b)<0?99:ord.indexOf(b)))||a.localeCompare(b));})();

// ---- left panel: categories or search results -----------------------------
function renderList(){
  const term=q.value.trim().toLowerCase();
  let pool=arr;
  if(tagFilter) pool=pool.filter(it=>itemTags(it.id).includes(tagFilter));
  if(term) pool=pool.filter(it=>it.name.toLowerCase().includes(term)||it.id.toLowerCase().includes(term));

  // tag filter banner + my-tags group
  let html='';
  const tagNames=Object.keys(TAGS);
  if(tagNames.length){
    html+=`<div class="cathd" data-cat="__tags"><span class="tw">${openCats.has('__tags')?'▾':'▸'}</span>
      <span class="dot" style="background:#7F77DD"></span>My Tags<span class="cc">${tagNames.length}</span></div>`;
    if(openCats.has('__tags')){
      for(const tn of tagNames){
        const on=tagFilter===tn;
        html+=`<div class="row" data-tagfilter="${tn}" style="padding-left:28px">
          <span class="tagdot" style="background:${TAGS[tn]}"></span>
          <span class="nm" style="color:${on?'#fff':''}">${tn}</span>
          <span class="lv">${tagCount(tn)}</span></div>`;
      }
    }
  }

  if(term||tagFilter){
    const matches=pool.slice(0,500).sort((a,b)=>(b.craftable-a.craftable)||a.name.localeCompare(b.name));
    countEl.textContent=`${matches.length}${pool.length>500?'+':''} match`;
    html+=matches.map(rowHtml).join('') || `<div class="empty" style="margin-top:24px">No matches</div>`;
    list.innerHTML=html; return;
  }

  // category accordion
  countEl.textContent=`${arr.length} items`;
  const byCat={}; for(const it of pool){(byCat[it.cat]=byCat[it.cat]||[]).push(it);}
  for(const cat of CAT_ORDER){
    const its=byCat[cat]; if(!its||!its.length)continue;
    const open=openCats.has(cat);
    html+=`<div class="cathd" data-cat="${cat}"><span class="tw">${open?'▾':'▸'}</span>
      <span class="dot"></span>${cat}<span class="cc">${its.length}</span></div>`;
    if(open){
      its.sort((a,b)=>(b.craftable-a.craftable)||(a.level||0)-(b.level||0)||a.name.localeCompare(b.name));
      html+=its.map(rowHtml).join('');
    }
  }
  list.innerHTML=html;
}
function rowHtml(it){
  const tg=itemTags(it.id);
  return `<div class="row${sel===it.id?' sel':''}" data-id="${it.id}" draggable="true">
    ${imgFor(it.id,'ico')}
    ${rdot(it.rarity)}
    <span class="nm">${it.name}</span>
    ${tg.map(t=>`<span class="tagdot" style="background:${TAGS[t]||'#888'}"></span>`).join('')}
    <span class="lv">${it.level?'Lv'+it.level:''}</span></div>`;
}

// primary nodes (single-drop / eponymous, e.g. ore veins) show level, not a
// misleading weight-as-percent; real drop-table sources show the %.
function srcTail(s){return s.primary ? (s.min_level?` · Lv${s.min_level}`:' · gather')
  : (s.chance!=null?` · ${s.chance}%`:'');}
function srcLabel(it){if(!it.sources||!it.sources.length)return '—';
  const s=it.sources[0]; return s.node+srcTail(s);}
function srcText(it){if(!it.sources||!it.sources.length)return '';
  const s=it.sources[0];
  return `<span class="src">${s.node}${srcTail(s)}${it.sources.length>1?` +${it.sources.length-1}`:''}</span>`;}

function buildNode(id,mult,stack){
  const it=ITEMS[id]||{id,name:id,craftable:!!RECIPES[id],sources:[]};
  const rec=RECIPES[id];
  const wrap=document.createElement('div'); wrap.className='node';
  const bar=document.createElement('div'); bar.className='bar';
  const hasKids=rec&&rec.ingredients.length&&!stack.has(id);
  bar.innerHTML=`<span class="tw">${hasKids?'▾':'·'}</span>`+
    `<span class="qty">${fmt(mult)}×</span>`+imgFor(id,'tico')+
    `<span class="nname">${it.name}</span>`+
    (rec?`<span class="job">${rec.job.toLowerCase()}</span>`:'')+rarPill(it.rarity)+
    (!rec?srcText(it):'');
  wrap.appendChild(bar);
  if(hasKids){
    const kids=document.createElement('div'); kids.className='children';
    const ns=new Set(stack); ns.add(id); const per=rec.amount||1;
    for(const ing of rec.ingredients) kids.appendChild(buildNode(ing.id,mult*ing.amount/per,ns));
    wrap.appendChild(kids);
    const tw=bar.querySelector('.tw');
    tw.onclick=()=>{wrap.classList.toggle('collapsed');
      tw.textContent=wrap.classList.contains('collapsed')?'▸':'▾';};
  }
  return wrap;
}
function rollup(id,mult,stack,acc){
  const rec=RECIPES[id];
  if(!rec||stack.has(id)){acc[id]=(acc[id]||0)+mult; return acc;}
  const ns=new Set(stack); ns.add(id); const per=rec.amount||1;
  for(const ing of rec.ingredients) rollup(ing.id,mult*ing.amount/per,ns,acc);
  return acc;
}
function fmt(n){return Number.isInteger(n)?n:(Math.round(n*100)/100);}

// compact summary card (default on click) — no crafting tree; button opens it
function showItemSummary(id){
  sel=id; viewingList=false; renderList();
  const it=ITEMS[id], rec=RECIPES[id];
  let h=`<div class="isummary"><div class="hd">${imgFor(id,'bigico')}<div>
      <h2>${it.name}</h2>
      <div class="meta">${rarPill(it.rarity)}${it.level?`<span class="lvtag">Lvl ${it.level}</span>`:''}
        ${it.type?`<span class="lvtag">${it.type.toLowerCase().replace(/_/g,' ')}</span>`:''}</div>
    </div></div>`;
  h+=statsBlock(it);
  h+=setBlock(it);
  if(!it.stats&&!it.damages) h+=`<div class="sub">${rec?`Crafted by <b>${rec.job.toLowerCase()}</b>`:'Base material'}</div>`;
  if(it.sources&&it.sources.length) h+=`<div class="sub">Gather: ${srcLabel(it)}</div>`;
  h+=`<div class="addrow">
      ${canEquip(it)?`<button class="addlist" id="equipbtn">Equip</button>`:''}
      ${BUILD[id]?
        `<span class="qstep" style="border:1px solid var(--line);border-radius:7px;padding:5px 10px">on list
           <button data-bd="-1">−</button><b>${BUILD[id]}</b><button data-bd="1">+</button>
           <span class="rm" id="rmlist" style="margin-left:6px">remove</span></span>`
        :`<button class="addlist" id="addlist" style="background:var(--panel2);color:var(--text);border:1px solid var(--line)">+ Craft list</button>`}
      ${rec?`<button class="addlist" id="recipebtn" style="background:var(--panel2);color:var(--text);border:1px solid var(--line)">View crafting recipe →</button>`:''}
    </div></div>`;
  detail.innerHTML=h;
  wireSetPieces();
  const eb=document.getElementById('equipbtn'); if(eb)eb.onclick=()=>{if(equipItem(id)){eb.textContent='✓ Equipped'; refreshChar();}};
  const addb=document.getElementById('addlist'); if(addb)addb.onclick=()=>{addToBuild(id,1); showItemSummary(id);};
  detail.querySelectorAll('[data-bd]').forEach(b=>b.onclick=()=>{BUILD[id]=(BUILD[id]||0)+(+b.dataset.bd);
    if(BUILD[id]<=0) delete BUILD[id]; saveBuild(); showItemSummary(id);});
  const rml=document.getElementById('rmlist'); if(rml)rml.onclick=()=>{delete BUILD[id]; saveBuild(); showItemSummary(id);};
  const rb=document.getElementById('recipebtn'); if(rb)rb.onclick=()=>showItemFull(id);
}
function showItemFull(id){
  sel=id; viewingList=false; renderList();
  const it=ITEMS[id], rec=RECIPES[id];
  let h=`<div class="hd">${imgFor(id,'bigico')}<div>
      <h2>${it.name}</h2>
      <div class="meta">${rarPill(it.rarity)}${it.level?`<span class="lvtag">Lvl ${it.level}</span>`:''}
        ${it.type?`<span class="lvtag">${it.type.toLowerCase().replace(/_/g,' ')}</span>`:''}</div>
    </div></div>`;
  h+=`<div class="sub">${rec?`Crafted by <b>${rec.job.toLowerCase()}</b> · makes ${rec.amount} per craft`
      :'Base material'+(it.sources.length?'':' (vendor / farm / vanilla)')}</div>`;
  h+=`<div id="tagzone"></div>`;
  h+=`<div class="addrow">
      <button class="addlist" id="addlist">+ Add to craft list</button>
      <span class="qstep">qty <button id="aqm">−</button><b id="addq">1</b><button id="aqp">+</button></span>
      ${canEquip(it)?`<button class="addlist" id="equipbtn" style="background:var(--panel2);color:var(--text);border:1px solid var(--line)">Equip</button>`:''}
      ${BUILD[id]?`<span class="src">already on list: ${BUILD[id]}×</span>`:''}
    </div>`;
  h+=statsBlock(it);
  h+=setBlock(it);
  if(rec){
    h+=`<div class="section"><h3>Component tree</h3><div class="tree" id="tree"></div>
        <div class="legend">▾ click to expand · qty = amount to make 1 of this item</div></div>`;
    h+=`<div class="section"><h3>Total raw materials</h3><table class="roll" id="roll"></table></div>`;
  }
  if(it.sources&&it.sources.length){
    h+=`<div class="section"><h3>Where to gather</h3><table class="roll">
      <tr><th>Node</th><th>Category</th><th>Min lvl</th><th>Drop</th></tr>`+
      it.sources.map(s=>`<tr><td>${s.node}</td><td class="base">${s.category||''}</td>
        <td class="base">${s.min_level??''}</td>
        <td class="n">${s.primary?'<span class="base">primary</span>':(s.chance!=null?s.chance+'%':'—')}</td></tr>`).join('')+
      `</table></div>`;
  }
  detail.innerHTML=h;
  renderTagZone(id);
  wireSetPieces();
  let aq=1; const aqEl=document.getElementById('addq');
  document.getElementById('aqm').onclick=()=>{aq=Math.max(1,aq-1); aqEl.textContent=aq;};
  document.getElementById('aqp').onclick=()=>{aq++; aqEl.textContent=aq;};
  document.getElementById('addlist').onclick=()=>{addToBuild(id,aq);
    const b=document.getElementById('addlist'); b.textContent=`✓ Added — ${BUILD[id]}× on list`;};
  const eb=document.getElementById('equipbtn');
  if(eb) eb.onclick=()=>{if(equipItem(id)){eb.textContent='✓ Equipped'; refreshChar();}};
  if(rec){
    document.getElementById('tree').appendChild(buildNode(id,1,new Set()));
    const acc=rollup(id,1,new Set(),{});
    const rows=Object.entries(acc).sort((a,b)=>b[1]-a[1]).map(([rid,amt])=>{
      const ri=ITEMS[rid]||{name:rid,sources:[]};
      return `<tr><td class="ic">${imgFor(rid,'tico')}</td><td>${ri.name}</td>
        <td class="base">${srcLabel(ri)}</td>
        <td class="n">${fmt(Math.ceil(amt*100)/100)}</td></tr>`;});
    document.getElementById('roll').innerHTML=
      `<tr><th></th><th>Raw material</th><th>Best source</th><th>Qty</th></tr>`+rows.join('');
  }
}

// ---- tag zone (assign / create custom tags) -------------------------------
let pendColor=TAG_PALETTE[3];
function renderTagZone(id){
  const z=document.getElementById('tagzone');
  const tg=itemTags(id);
  let h=`<div class="tags">`+
    tg.map(t=>`<span class="chip" style="background:${TAGS[t]||'#888'}33;color:${TAGS[t]||'#ccc'};border:1px solid ${TAGS[t]||'#888'}">
        ${t}<span class="x" data-untag="${t}">✕</span></span>`).join('')+
    `<span class="addbtn" id="addtag">+ Tag</span></div>`;
  const exist=Object.keys(TAGS).filter(t=>!tg.includes(t));
  h+=`<div class="tageditor" id="tageditor">
      <input type="text" id="tagname" placeholder="Tag name (e.g. Need to craft, BIS)" maxlength="24">
      <span class="swatches" id="swatches">${TAG_PALETTE.map(c=>
        `<span class="sw${c===pendColor?' on':''}" data-col="${c}" style="background:${c}"></span>`).join('')}</span>
      <button id="tagsave">Add</button>
      ${exist.length?`<div class="exist">${exist.map(t=>
        `<span class="chip" data-applytag="${t}" style="background:${TAGS[t]}33;color:${TAGS[t]};border:1px solid ${TAGS[t]}">${t}</span>`).join('')}</div>`:''}
    </div>`;
  z.innerHTML=h;
  z.querySelector('#addtag').onclick=()=>z.querySelector('#tageditor').classList.toggle('on');
  z.querySelectorAll('[data-untag]').forEach(e=>e.onclick=()=>{unassignTag(id,e.dataset.untag); showItemFull(id);});
  z.querySelectorAll('[data-applytag]').forEach(e=>e.onclick=()=>{assignTag(id,e.dataset.applytag); showItemFull(id);});
  z.querySelectorAll('.sw').forEach(s=>s.onclick=()=>{pendColor=s.dataset.col;
    z.querySelectorAll('.sw').forEach(x=>x.classList.toggle('on',x.dataset.col===pendColor));});
  z.querySelector('#tagsave').onclick=()=>{
    const nm=z.querySelector('#tagname').value.trim(); if(!nm)return;
    TAGS[nm]=pendColor; assignTag(id,nm); showItemFull(id);};
}

// ---- craft list view (targets + aggregated totals + have/left) ------------
// up-to-5 named lists shown as switchable tabs above the list
function listTabsHTML(){
  const ids=Object.keys(LISTS);
  let h=`<div class="listtabs">`;
  for(const id of ids){const L=LISTS[id], n=Object.keys(L.items).length;
    h+=`<span class="ltab${id===ACTIVE?' on':''}" data-list="${id}" title="click to switch · double-click to rename">
      ${L.name}<span class="cnt">${n}</span>${id===ACTIVE?`<span class="lx" data-del="${id}" title="delete this list">✕</span>`:''}</span>`;}
  if(ids.length<MAXLISTS) h+=`<span class="ltab add" data-newlist="1" title="new craft list">+ New list</span>`;
  return h+`</div>`;
}
function wireListTabs(){
  detail.querySelectorAll('[data-list]').forEach(e=>{
    e.onclick=ev=>{if(ev.target.dataset.del)return; setActiveList(e.dataset.list);};
    e.ondblclick=()=>renameList(e.dataset.list);});
  detail.querySelectorAll('[data-del]').forEach(e=>e.onclick=ev=>{ev.stopPropagation(); deleteList(e.dataset.del);});
  const nl=detail.querySelector('[data-newlist]'); if(nl)nl.onclick=newList;
}
function showList(){
  viewingList=true; sel=null; renderList();
  const ids=Object.keys(BUILD);
  const tabs=listTabsHTML();
  if(!ids.length){detail.innerHTML=tabs+`<div class="empty">"${LISTS[ACTIVE].name}" is empty.<br>
    Open any item and hit <b>+ Add to craft list</b>.</div>`; wireListTabs(); return;}
  let h=tabs+`<div class="hd"><h2>${LISTS[ACTIVE].name}</h2></div>
    <div class="sub">Pick what you want to make; totals and "what's left" update as you check things off.</div>`;
  // targets
  h+=`<div class="section"><h3>Items to make
      <button class="rmall" id="rmall">Remove all</button></h3><table class="roll">`;
  for(const id of ids){const it=ITEMS[id]||{name:id};
    h+=`<tr><td class="ic">${imgFor(id,'tico')}</td><td class="mname">${it.name}</td>
      <td><span class="qstep"><button data-bq="${id}" data-d="-1">−</button>
        <b>${BUILD[id]}</b><button data-bq="${id}" data-d="1">+</button></span></td>
      <td class="n"><span class="rm" data-rm="${id}">remove</span></td></tr>`;}
  h+=`</table></div>`;
  // gear-set preview: equippable items in the list, shown in their slots + combined stats
  const loadout=buildLoadout(); const setIds=Object.values(loadout);
  if(setIds.length){
    h+=`<div class="section"><h3>Gear set preview
        <button class="rmall equipall" id="equipall">Equip all to character ⮕</button></h3>
      <div class="charwrap"><div class="charleft">
        <div class="slotgrid">${SLOTS.map(s=>slotHTML(s,loadout,true)).join('')}</div>
        <div class="handrow">${slotHTML(HAND,loadout,true)}</div>
        <div class="legend">equippable items in your craft list, in their slots · hover for stats</div>
      </div><div class="charright"><h3>Combined gear stats</h3><div id="setstats"></div></div></div></div>`;
  }
  // totals
  const acc = listMode==='raw' ? rawAgg() : bomAgg();
  const rows=Object.entries(acc).map(([rid,amt])=>[rid,Math.ceil(Math.round(amt*100)/100)])
    .sort((a,b)=>b[1]-a[1]);
  const done=rows.filter(([rid,need])=>(HAVE[rid]||0)>=need).length;
  const pct=rows.length?Math.round(done/rows.length*100):0;
  h+=`<div class="section"><h3>Totals — ${done}/${rows.length} complete
      <span class="modetoggle">
        <button data-mode="raw" class="${listMode==='raw'?'on':''}">Raw materials</button>
        <button data-mode="all" class="${listMode==='all'?'on':''}">All components</button></span></h3>
    <div class="progress"><span style="width:${pct}%"></span></div>
    <table class="roll"><tr><th></th><th></th><th>Material</th><th>Best source</th>
      <th>Need</th><th>Have</th><th>Left</th></tr>`;
  for(const [rid,need] of rows){
    const have=HAVE[rid]||0, left=Math.max(0,need-have), doneRow=have>=need;
    const ri=ITEMS[rid]||{name:rid,sources:[]};
    h+=`<tr class="${doneRow?'doneRow':''}">
      <td><input type="checkbox" class="havechk" data-chk="${rid}" data-need="${need}" ${doneRow?'checked':''}></td>
      <td class="ic">${imgFor(rid,'tico')}</td>
      <td class="mname">${ri.name}</td>
      <td class="base">${srcLabel(ri)}</td>
      <td class="n">${need}</td>
      <td><input class="havein" type="number" min="0" data-have="${rid}" value="${have}"></td>
      <td class="n left ${left?'':'zero'}">${left}</td></tr>`;}
  h+=`</table>
    <div class="legend" style="margin-top:12px"><button id="clearlist">Clear list</button>
      &nbsp; tick the box (or type how many you have) to cross it off · totals combine every item above</div></div>`;
  detail.innerHTML=h;
  // wiring
  wireListTabs();
  detail.querySelectorAll('[data-bq]').forEach(b=>b.onclick=()=>{
    const id=b.dataset.bq; BUILD[id]=(BUILD[id]||0)+(+b.dataset.d);
    if(BUILD[id]<=0) delete BUILD[id]; saveBuild(); showList();});
  detail.querySelectorAll('[data-rm]').forEach(e=>e.onclick=()=>{delete BUILD[e.dataset.rm]; saveBuild(); showList();});
  detail.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{listMode=b.dataset.mode; showList();});
  detail.querySelectorAll('.havechk').forEach(c=>c.onchange=()=>{
    HAVE[c.dataset.chk]=c.checked?(+c.dataset.need):0; saveHave(); showList();});
  detail.querySelectorAll('.havein').forEach(inp=>inp.onchange=()=>{
    const v=Math.max(0,parseInt(inp.value)||0); HAVE[inp.dataset.have]=v; saveHave(); showList();});
  const rmall=document.getElementById('rmall'); if(rmall)rmall.onclick=()=>{
    if(confirm('Remove all items from "'+LISTS[ACTIVE].name+'"?')){clearActiveList(); showList();}};
  document.getElementById('clearlist').onclick=()=>{
    if(confirm('Clear the whole craft list?')){clearActiveList(); showList();}};
  if(setIds.length){
    const ea=document.getElementById('equipall'); if(ea)ea.onclick=()=>{
      for(const [k,id] of Object.entries(loadout)) EQUIP[k]=id;
      saveEquip(); refreshChar(); ea.textContent='✓ Equipped to character';};
    const setTot=statsFromItems(setIds); const box=document.getElementById('setstats');
    box.innerHTML=Object.keys(setTot).length?renderStatRows(setTot):'<div class="src">these items have no stats</div>';
    wireStatHover(box,setTot);
    detail.querySelectorAll('.slot.filled').forEach(el=>{el.onmouseenter=()=>showSlotTip(el.dataset.itemid);
      el.onmousemove=moveTip; el.onmouseleave=hideTip;});
  }
}

// ---- character view -------------------------------------------------------
function equipItem(id){const it=ITEMS[id]; if(!canEquip(it))return false;
  const slots=slotForType(it.type); const t=slots.find(s=>!EQUIP[s.k])||slots[0];
  EQUIP[t.k]=id; saveEquip(); return true;}
// the character panel lives persistently in #charcol (or in #detail as a
// narrow-screen fallback). renderCharPanel fills whichever box it's given.
let charHost=null;
function renderCharPanel(box){
  charHost=box; hideTip();
  let h=`<div class="charhdr">Character</div>
    <div class="userrow">
      <input id="charuser" type="text" placeholder="Minecraft username" value="${BASENAME||''}">
      <button id="loaduser">Load stats</button>
    </div>
    ${BASESTATS?`<div class="src" style="margin:-8px 0 10px">base+scrolls loaded${BASENAME?': '+BASENAME:''}</div>`:''}
    ${BASENAME?`<div class="skinwrap"><canvas id="skinview"></canvas><div class="legend" style="text-align:center;margin-top:4px">drag to rotate</div></div>`:''}
    <div class="slotgrid" id="slotgrid">${SLOTS.map(s=>slotHTML(s)).join('')}</div>
    <div class="handrow">${slotHTML(HAND)}</div>
    <div class="legend">drag an item onto a slot · ✕ to remove</div>
    <div class="charstats"><div class="charhdr2">Total stats</div><div id="stattotals"></div></div>`;
  box.innerHTML=h;
  renderStatTotals();
  box.querySelectorAll('.slot').forEach(el=>{
    el.ondragover=e=>{e.preventDefault(); el.classList.add('drop');};
    el.ondragleave=()=>el.classList.remove('drop');
    el.ondrop=e=>{e.preventDefault(); el.classList.remove('drop');
      const id=e.dataTransfer.getData('text/plain'); const it=ITEMS[id]; if(!it)return;
      if(el.dataset.types.split(',').includes(it.type)){EQUIP[el.dataset.slot]=id; saveEquip(); renderCharPanel(box);}
      else if(equipItem(id)){renderCharPanel(box);}        // wrong slot -> snap to the right one
      else{el.classList.add('bad'); setTimeout(()=>el.classList.remove('bad'),350);}};});
  box.querySelectorAll('[data-unequip]').forEach(x=>x.onclick=e=>{e.stopPropagation();
    delete EQUIP[x.dataset.unequip]; saveEquip(); renderCharPanel(box);});
  box.querySelectorAll('.slot.filled').forEach(el=>{
    el.onmouseenter=()=>showSlotTip(el.dataset.itemid);
    el.onmousemove=moveTip; el.onmouseleave=hideTip;});
  box.querySelector('#loaduser').onclick=loadUserStats;
  if(BASENAME) renderSkin(BASENAME);
}
function charVisible(){const c=document.getElementById('charcol'); return c&&getComputedStyle(c).display!=='none';}
function refreshChar(){if(charHost&&charHost.isConnected&&(charHost.id!=='charcol'||charVisible())) renderCharPanel(charHost);}
function showChar(){sel=null; viewingList=false; renderList(); renderCharPanel(detail);}  // narrow fallback
// 3D walking character render (skinview3d, lazy-loaded)
let SV_LOADING, skinViewer;
function ensureSkinview(){
  if(window.skinview3d) return Promise.resolve();
  if(SV_LOADING) return SV_LOADING;
  SV_LOADING=new Promise((res,rej)=>{const s=document.createElement('script');
    s.src='https://cdn.jsdelivr.net/npm/skinview3d@3.0.1/bundles/skinview3d.bundle.js';
    s.onload=res; s.onerror=rej; document.head.appendChild(s);});
  return SV_LOADING;
}
function renderSkin(name){
  const canvas=document.getElementById('skinview'); if(!canvas)return;
  ensureSkinview().then(()=>{
    if(!document.getElementById('skinview'))return;   // view changed while loading
    try{
      if(skinViewer&&skinViewer.dispose) skinViewer.dispose();
      skinViewer=new skinview3d.SkinViewer({canvas,width:200,height:300,
        skin:'https://mc-heads.net/skin/'+encodeURIComponent(name)});
      skinViewer.animation=new skinview3d.WalkingAnimation();
      skinViewer.animation.speed=0.55; skinViewer.zoom=0.9;
      // v3 SkinViewer auto-creates orbit controls (rotate on by default)
      skinViewer.controls.enableZoom=false; skinViewer.controls.enablePan=false;
    }catch(e){console.warn('skin render failed',e);}
  }).catch(()=>{});
}
function renderStatRows(tot){
  const order=Object.keys(ATTR);
  const keys=Object.keys(tot).sort((a,b)=>(order.indexOf(a)<0?99:order.indexOf(a))-(order.indexOf(b)<0?99:order.indexOf(b)));
  return '<div class="statgrid" style="grid-template-columns:1fr">'+keys.map(k=>{
    const t=tot[k], c=statColor(k); const v=t.min===t.max?`${t.min}`:`${t.min}–${t.max}`;
    const g=(t.gearMin||t.gearMax)?` <span class="src">(gear +${t.gearMin===t.gearMax?t.gearMin:t.gearMin+'–'+t.gearMax})</span>`:'';
    return `<div class="stat statrow" data-stat="${k}"><span class="statn"><span class="statdot" style="background:${c}"></span>${statName(k)}</span>
      <span class="statv" style="color:${c}">${v}${g}</span></div>`;}).join('')+'</div>';
}
function wireStatHover(container,tot){container.querySelectorAll('.statrow').forEach(row=>{
  row.onmouseenter=()=>showStatTip(tot,row.dataset.stat); row.onmousemove=moveTip; row.onmouseleave=hideTip;});}
function showStatTip(tot,k){const t=tot[k]; if(!t)return;
  if(!tipEl){tipEl=document.createElement('div'); tipEl.className='tip'; document.body.appendChild(tipEl);}
  const srcs=[...t.sources].sort((a,b)=>b.max-a.max);
  const rows=srcs.map(s=>`<div class="tipsrc"><span>${s.name}</span><span>+${s.min===s.max?s.min:s.min+'–'+s.max}</span></div>`).join('');
  const tv=t.min===t.max?t.min:t.min+'–'+t.max;
  tipEl.innerHTML=`<b style="color:${statColor(k)}">${statName(k)} ${tv}</b><div class="tiprows">${rows}</div>`;
  tipEl.style.display='block';}
function renderStatTotals(){
  const tot=equipStats();
  const box=document.getElementById('stattotals');
  if(!Object.keys(tot).length){box.innerHTML=`<div class="src">Equip gear (and optionally load your username) to see totals.</div>`; return;}
  box.innerHTML=renderStatRows(tot)+
    `<div class="legend" style="margin-top:10px">hover a stat for its sources · totals = base + scrolls + relics + equipped gear
      (the API can't expose your default base HP, museum, pets, or what gear you're actually wearing)</div>`;
  wireStatHover(box,tot);
}
let tipEl;
function showSlotTip(id){const it=ITEMS[id]; if(!it)return;
  if(!tipEl){tipEl=document.createElement('div'); tipEl.className='tip'; document.body.appendChild(tipEl);}
  let rows='';
  if(it.damages) for(const [k,r] of Object.entries(it.damages))
    rows+=`<div><span style="color:#E24B4A">${pretty(k)} dmg</span> +${r[0]===r[1]?r[0]:r[0]+'–'+r[1]}</div>`;
  if(it.stats) for(const [k,r] of Object.entries(it.stats))
    rows+=`<div><span style="color:${statColor(k)}">${statName(k)}</span> +${r[0]===r[1]?r[0]:r[0]+'–'+r[1]}</div>`;
  const setln=it.set?`<div class="src" style="margin-top:5px">⛓ ${it.set}</div>`:'';
  const lvln=it.level?` <span class="src">Lv${it.level}</span>`:'';
  tipEl.innerHTML=`<b>${it.name}</b>${rarPill(it.rarity)}${lvln}<div class="tiprows">${rows||'<span class="src">no stats</span>'}</div>${setln}`;
  tipEl.style.display='block';}
function moveTip(e){if(tipEl){tipEl.style.left=Math.min(e.clientX+14,innerWidth-260)+'px'; tipEl.style.top=(e.clientY+14)+'px';}}
function hideTip(){if(tipEl)tipEl.style.display='none';}
function loadUserStats(){
  const u=document.getElementById('charuser').value.trim(); if(!u)return;
  const btn=document.getElementById('loaduser'); btn.textContent='Loading…';
  fetch('https://api.minebox.co/data/'+encodeURIComponent(u))
    .then(r=>r.ok?r.json():Promise.reject(r.status))
    .then(d=>{const a=d.data&&d.data.ATTRIBUTED_STATS;
      if(!a){btn.textContent='No stats found'; return;}
      const relics={}; const unlocked=Object.keys((d.data.OBJECTIVES&&d.data.OBJECTIVES.relics)||{});
      for(const rid of unlocked){const st=RELICS[rid]||{};
        for(const [k,v] of Object.entries(st)) relics[k]=(relics[k]||0)+v;}
      BASESTATS={base:a.base||{},scrolls:a.scrolls||{},relics}; BASENAME=d.username||u;
      localStorage.setItem('mb_basestats',JSON.stringify(BASESTATS));
      localStorage.setItem('mb_basename',BASENAME); renderCharPanel(charHost||detail);})
    .catch(err=>{btn.textContent='Not found ('+err+')';});
}

// ---- gear optimizer -------------------------------------------------------
// pick stats to maximize + a level cap; search items AND set bonuses for the
// best loadouts. Candidates: pure best-in-slot greedy, every relevant set
// anchored at each piece-threshold, and dual (2pc+2pc) set combos; remaining
// slots filled greedily, then deduped and ranked by weighted score.
let OPT=JSON.parse(localStorage.getItem('mb_opt')||'null')||{stats:[],level:100,basis:'max'};
function saveOpt(){localStorage.setItem('mb_opt',JSON.stringify(OPT));}
function optStatScore(it,weights,useMax){
  if(!it.stats)return 0; let s=0;
  for(const [k,r] of Object.entries(it.stats)){const w=weights[k.toLowerCase()]; if(w)s+=(useMax?r[1]:(r[0]+r[1])/2)*w;}
  return s;
}
function optimize(selStats,levelCap,useMax){
  const weights={}; selStats.forEach(k=>weights[k]=1);
  const elig=it=>it.type&&(!it.level||it.level<=levelCap);
  const score=it=>optStatScore(it,weights,useMax);
  // per-slot eligible items, best score first
  const bySlot={}; ALLSLOTS.forEach(s=>bySlot[s.k]=[]);
  for(const it of arr){ if(!elig(it))continue; for(const s of slotForType(it.type)) bySlot[s.k].push(it); }
  for(const k in bySlot) bySlot[k].sort((a,b)=>score(b)-score(a));
  function greedyFill(prefer){
    const eq=Object.assign({},prefer); const used=new Set(Object.values(eq));
    for(const s of ALLSLOTS){ if(eq[s.k])continue;
      const c=bySlot[s.k].find(it=>!used.has(it.id)&&score(it)>0);
      if(c){eq[s.k]=c.id; used.add(c.id);} }
    return eq;
  }
  function loadoutScore(eq){
    const ids=Object.values(eq); let s=0;
    for(const id of ids){const it=ITEMS[id]; if(it)s+=score(it);}
    for(const sb of setBonusSources(ids))for(const [k,v] of Object.entries(sb.stats)){const w=weights[k.toLowerCase()]; if(w)s+=v*w;}
    return s;
  }
  // sets whose bonus touches a selected stat, with their eligible pieces cached
  const relSets=Object.keys(SETS).filter(nm=>{const b=SETS[nm].bonuses||{};
    return Object.values(b).some(th=>Object.keys(th).some(k=>weights[k.toLowerCase()]));});
  const setPieces={};
  for(const nm of relSets) setPieces[nm]=arr.filter(x=>x.set===nm&&elig(x)&&canEquip(x)).sort((a,b)=>score(b)-score(a));
  // place up to maxN of a set's top pieces into distinct slots, optionally on top of a base map
  function placeSet(nm,maxN,base){
    const prefer=Object.assign({},base||{}); const used=new Set(Object.values(prefer)); let placed=0;
    for(const p of setPieces[nm]){ if(placed>=maxN)break; if(used.has(p.id))continue;
      for(const s of slotForType(p.type)){ if(!prefer[s.k]){prefer[s.k]=p.id; used.add(p.id); placed++; break;} } }
    return {prefer,placed};
  }
  const cands=[greedyFill({})];
  for(const nm of relSets){
    const ths=Object.keys(SETS[nm].bonuses).map(Number).sort((a,b)=>a-b);
    for(const n of ths){ const r=placeSet(nm,n); if(r.placed>=2)cands.push(greedyFill(r.prefer)); }
    const full=placeSet(nm,99); if(full.placed>=2)cands.push(greedyFill(full.prefer));
  }
  for(let i=0;i<relSets.length;i++)for(let j=i+1;j<relSets.length;j++){
    const a=placeSet(relSets[i],2); if(a.placed<2)continue;
    const ab=placeSet(relSets[j],2,a.prefer); if(ab.placed>=2)cands.push(greedyFill(ab.prefer));
  }
  const seen=new Set(); const scored=[];
  for(const eq of cands){ const key=ALLSLOTS.map(s=>eq[s.k]||'').join('|');
    if(seen.has(key))continue; seen.add(key); scored.push({eq,score:loadoutScore(eq)}); }
  scored.sort((a,b)=>b.score-a.score);
  return scored.slice(0,5);
}
function showOptimizer(){
  sel=null; viewingList=false; renderList();
  let h=`<div class="hd"><h2>Gear optimizer</h2></div>
    <div class="sub">Pick the stats to maximize and your level — it searches every item <i>and</i> set bonus for the best
      combinations. Try combos like Luck + Fishing Fortune, or Strength + Agility.</div>`;
  h+=`<div class="section"><h3>Stats to maximize</h3><div class="optchips">`+
    GEAR_STATS.map(k=>{const on=OPT.stats.includes(k); const c=statColor(k);
      return `<span class="optchip${on?' on':''}" data-stat="${k}" style="${on?`background:${c}22;border-color:${c};color:${c}`:''}">${statName(k)}</span>`;}).join('')+
    `</div><div class="legend">click to toggle · combine as many as you like</div></div>`;
  h+=`<div class="section"><h3>Level cap — <b id="lvlval" style="color:var(--accent2)">${OPT.level}</b></h3>
      <input type="range" id="lvlslider" min="1" max="100" value="${OPT.level}" class="lvlslider">
      <div class="legend">only gear that requires this level or lower
        <span class="modetoggle" style="margin-left:10px">
          <button data-basis="max" class="${OPT.basis==='max'?'on':''}">Best roll</button>
          <button data-basis="avg" class="${OPT.basis==='avg'?'on':''}">Average roll</button></span></div></div>`;
  h+=`<div id="optresults"></div>`;
  detail.innerHTML=h;
  detail.querySelectorAll('[data-stat]').forEach(e=>e.onclick=()=>{
    const k=e.dataset.stat, i=OPT.stats.indexOf(k);
    if(i<0)OPT.stats.push(k); else OPT.stats.splice(i,1); saveOpt(); showOptimizer();});
  const sl=document.getElementById('lvlslider');
  sl.oninput=()=>{document.getElementById('lvlval').textContent=sl.value;};
  sl.onchange=()=>{OPT.level=+sl.value; saveOpt(); renderOptResults();};
  detail.querySelectorAll('[data-basis]').forEach(b=>b.onclick=()=>{OPT.basis=b.dataset.basis; saveOpt(); showOptimizer();});
  renderOptResults();
}
function renderOptResults(){
  const box=document.getElementById('optresults'); if(!box)return;
  if(!OPT.stats.length){box.innerHTML=`<div class="empty" style="margin-top:30px">Pick one or more stats above to see the best gear combinations.</div>`; return;}
  const results=optimize(OPT.stats,OPT.level,OPT.basis==='max');
  if(!results.length||results[0].score<=0){box.innerHTML=`<div class="empty" style="margin-top:30px">No gear with those stats at level ${OPT.level} or lower.</div>`; return;}
  let h='';
  results.forEach((r,idx)=>{
    const sb=setBonusSources(Object.values(r.eq));
    const setLbl=sb.length?sb.map(s=>s.name).join('  ·  '):'no set bonus';
    h+=`<div class="optbuild"><div class="optbuildhd">
        <span class="optrank">#${idx+1}</span>
        <span class="optscore">${fmt(Math.round(r.score*10)/10)} pts</span>
        <span class="src">${setLbl}</span>
        <button class="rmall equipall optequip" data-eq="${idx}">Equip all ⮕</button>
        <button class="rmall optcraft" data-eq="${idx}">+ Craft list</button></div>
      <div class="charwrap"><div class="charleft">
        <div class="slotgrid">${SLOTS.map(s=>slotHTML(s,r.eq,true)).join('')}</div>
        <div class="handrow">${slotHTML(HAND,r.eq,true)}</div>
      </div><div class="charright"><h3>Combined stats</h3><div id="optstats${idx}"></div></div></div></div>`;
  });
  box.innerHTML=h;
  results.forEach((r,idx)=>{
    const tot=statsFromItems(Object.values(r.eq)); const sbox=document.getElementById('optstats'+idx);
    sbox.innerHTML=renderStatRows(tot); wireStatHover(sbox,tot);});
  box.querySelectorAll('.slot.filled').forEach(el=>{el.onmouseenter=()=>showSlotTip(el.dataset.itemid);
    el.onmousemove=moveTip; el.onmouseleave=hideTip;});
  box.querySelectorAll('.optequip').forEach(b=>b.onclick=()=>{const r=results[+b.dataset.eq];
    for(const [k,id] of Object.entries(r.eq)) EQUIP[k]=id; saveEquip(); refreshChar(); b.textContent='✓ Equipped';});
  box.querySelectorAll('.optcraft').forEach(b=>b.onclick=()=>{const r=results[+b.dataset.eq];
    for(const id of Object.values(r.eq)) addToBuild(id,1); b.textContent='✓ Added to list';});
}

list.addEventListener('dragstart',e=>{const r=e.target.closest('.row');
  if(r&&r.dataset.id) e.dataTransfer.setData('text/plain',r.dataset.id);});
list.addEventListener('dblclick',e=>{const r=e.target.closest('.row');
  if(r&&r.dataset.id&&equipItem(r.dataset.id)){hideTip(); refreshChar();
    const eb=document.getElementById('equipbtn'); if(eb&&sel===r.dataset.id) eb.textContent='✓ Equipped';}});
// hover a row -> live stats tooltip (no click needed); double-click still equips
list.addEventListener('mouseover',e=>{const r=e.target.closest('.row');
  if(r&&r.dataset.id){const it=ITEMS[r.dataset.id];
    if(it&&(it.stats||it.damages)){showSlotTip(r.dataset.id); moveTip(e);} else hideTip();}});
list.addEventListener('mousemove',e=>{if(tipEl&&tipEl.style.display==='block'&&e.target.closest('.row'))moveTip(e);});
list.addEventListener('mouseout',e=>{const from=e.target.closest('.row');
  const to=e.relatedTarget&&e.relatedTarget.closest?e.relatedTarget.closest('.row'):null;
  if(from&&from!==to)hideTip();});
list.onclick=e=>{
  const r=e.target.closest('.row');
  if(r){ if(r.dataset.tagfilter){tagFilter=tagFilter===r.dataset.tagfilter?null:r.dataset.tagfilter; renderList(); return;}
         if(r.dataset.id){showItemSummary(r.dataset.id); return;} }   // click = quick summary, not full crafting
  const c=e.target.closest('.cathd');
  if(c){const k=c.dataset.cat; openCats.has(k)?openCats.delete(k):openCats.add(k); renderList();}
};
document.getElementById('optbtn').onclick=showOptimizer;
document.getElementById('charbtn').onclick=showChar;
document.getElementById('listbtn').onclick=showList;
q.oninput=()=>{tagFilter=null; renderList();};
updateListN();
renderList();
if(charVisible()) renderCharPanel(document.getElementById('charcol'));
addEventListener('resize',()=>{const c=document.getElementById('charcol');
  if(charVisible()&&c&&!c.querySelector('#slotgrid')) renderCharPanel(c);});
</script>
</body></html>"""

out = TEMPLATE.replace("__DATA__", blob)
open(OUT, "w", encoding="utf-8").write(out)
print("wrote", OUT, f"({len(out)//1024} KB)")
