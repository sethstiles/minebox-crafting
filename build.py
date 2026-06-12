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
    for d in n.get("drops", []):
        key = strip_prefix(d["item"])
        drop_index.setdefault(key, []).append({
            "node": n.get("name") or n.get("id"),
            "category": n.get("category", ""),
            "min_level": n.get("min_level"),
            "chance": d.get("chance", 0),
            "amount": d.get("amount", 1),
        })
for k in drop_index:
    drop_index[k].sort(key=lambda x: (x["chance"] is None, -(x["chance"] or 0)))

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
    items[idstr] = entry

data = {"items": items, "recipes": recipes, "catOrder": CAT_ORDER, "attrs": attrs}
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
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
header{padding:16px 20px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{margin:0 0 10px;font-size:18px;font-weight:600}
h1 span{color:var(--accent2)}
.search{display:flex;gap:10px;align-items:center}
#q{flex:1;max-width:520px;padding:10px 12px;border-radius:8px;border:1px solid var(--line);
   background:var(--panel);color:var(--text);font-size:14px;outline:none}
#q:focus{border-color:var(--accent)}
.count{color:var(--muted);font-size:12px}
.wrap{display:grid;grid-template-columns:320px 1fr;gap:0;min-height:calc(100vh - 84px)}
.list{border-right:1px solid var(--line);overflow:auto;max-height:calc(100vh - 84px)}
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
</style></head>
<body>
<header>
  <h1>Minebox <span>Crafting Browser</span></h1>
  <div class="search">
    <input id="q" placeholder="Search items, or browse categories on the left..." autocomplete="off">
    <span class="count" id="count"></span>
    <button class="listbtn" id="listbtn">Craft list <span id="listn">0</span></button>
  </div>
</header>
<div class="wrap">
  <div class="list" id="list"></div>
  <div class="detail" id="detail"><div class="empty">Pick a category on the left, or search, then click an item.</div></div>
</div>
<script>
const DATA = __DATA__;
const ITEMS = DATA.items, RECIPES = DATA.recipes, CAT_ORDER = DATA.catOrder, ATTR = DATA.attrs||{};
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

// ---- craft list / planner (localStorage) ----------------------------------
let BUILD = JSON.parse(localStorage.getItem('mb_build')||'{}');   // {itemId:qty}
let HAVE  = JSON.parse(localStorage.getItem('mb_have')||'{}');    // {matId:qtyHave}
let listMode='raw', viewingList=false;
function saveBuild(){localStorage.setItem('mb_build',JSON.stringify(BUILD)); updateListN();}
function saveHave(){localStorage.setItem('mb_have',JSON.stringify(HAVE));}
function updateListN(){const n=Object.keys(BUILD).length;
  document.getElementById('listn').textContent=n;}
function addToBuild(id,qty){BUILD[id]=(BUILD[id]||0)+qty; saveBuild();}
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

function imgFor(id,cls){const it=ITEMS[id];
  if(it&&it.img) return `<img class="${cls}" src="data:image/png;base64,${it.img}" alt="">`;
  return `<span class="${cls} ph">·</span>`;}
function rarPill(r){if(!r)return ''; const c=RAR_COLORS[r]||'#93a1ad';
  return `<span class="rar" style="color:${c};border:1px solid ${c}">${r[0]+r.slice(1).toLowerCase()}</span>`;}
function rdot(r){if(!r)return '<span class="rdot"></span>'; const c=RAR_COLORS[r]||'#93a1ad';
  return `<span class="rdot" style="background:${c}"></span>`;}
function pretty(k){return k.toLowerCase().replace(/_/g,' ').replace(/\b\w/g,c=>c.toUpperCase());}
function statName(k){const a=ATTR[k.toLowerCase()]; return a&&a.name?a.name:pretty(k);}
function statColor(k){const a=ATTR[k.toLowerCase()]; return a&&a.color?a.color:'#93a1ad';}
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

const arr=Object.values(ITEMS);

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
  return `<div class="row${sel===it.id?' sel':''}" data-id="${it.id}">
    ${imgFor(it.id,'ico')}
    ${rdot(it.rarity)}
    <span class="nm">${it.name}</span>
    ${tg.map(t=>`<span class="tagdot" style="background:${TAGS[t]||'#888'}"></span>`).join('')}
    <span class="lv">${it.level?'Lv'+it.level:''}</span></div>`;
}

function srcText(it){if(!it.sources||!it.sources.length)return '';
  const s=it.sources[0]; const pct=s.chance!=null?`${s.chance}%`:'';
  return `<span class="src">${s.node}${pct?` · <span class="pct">${pct}</span>`:''}${it.sources.length>1?` +${it.sources.length-1}`:''}</span>`;}

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

function showItem(id){
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
      ${BUILD[id]?`<span class="src">already on list: ${BUILD[id]}×</span>`:''}
    </div>`;
  h+=statsBlock(it);
  if(rec){
    h+=`<div class="section"><h3>Component tree</h3><div class="tree" id="tree"></div>
        <div class="legend">▾ click to expand · qty = amount to make 1 of this item</div></div>`;
    h+=`<div class="section"><h3>Total raw materials</h3><table class="roll" id="roll"></table></div>`;
  }
  if(it.sources&&it.sources.length){
    h+=`<div class="section"><h3>Where to gather</h3><table class="roll">
      <tr><th>Node</th><th>Category</th><th>Min lvl</th><th>Chance</th></tr>`+
      it.sources.map(s=>`<tr><td>${s.node}</td><td class="base">${s.category||''}</td>
        <td class="base">${s.min_level??''}</td><td class="n">${s.chance!=null?s.chance+'%':'—'}</td></tr>`).join('')+
      `</table></div>`;
  }
  detail.innerHTML=h;
  renderTagZone(id);
  let aq=1; const aqEl=document.getElementById('addq');
  document.getElementById('aqm').onclick=()=>{aq=Math.max(1,aq-1); aqEl.textContent=aq;};
  document.getElementById('aqp').onclick=()=>{aq++; aqEl.textContent=aq;};
  document.getElementById('addlist').onclick=()=>{addToBuild(id,aq);
    const b=document.getElementById('addlist'); b.textContent=`✓ Added — ${BUILD[id]}× on list`;};
  if(rec){
    document.getElementById('tree').appendChild(buildNode(id,1,new Set()));
    const acc=rollup(id,1,new Set(),{});
    const rows=Object.entries(acc).sort((a,b)=>b[1]-a[1]).map(([rid,amt])=>{
      const ri=ITEMS[rid]||{name:rid,sources:[]}; const s=ri.sources&&ri.sources[0];
      return `<tr><td class="ic">${imgFor(rid,'tico')}</td><td>${ri.name}</td>
        <td class="base">${s?s.node+(s.chance!=null?` · ${s.chance}%`:''):'—'}</td>
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
  z.querySelectorAll('[data-untag]').forEach(e=>e.onclick=()=>{unassignTag(id,e.dataset.untag); showItem(id);});
  z.querySelectorAll('[data-applytag]').forEach(e=>e.onclick=()=>{assignTag(id,e.dataset.applytag); showItem(id);});
  z.querySelectorAll('.sw').forEach(s=>s.onclick=()=>{pendColor=s.dataset.col;
    z.querySelectorAll('.sw').forEach(x=>x.classList.toggle('on',x.dataset.col===pendColor));});
  z.querySelector('#tagsave').onclick=()=>{
    const nm=z.querySelector('#tagname').value.trim(); if(!nm)return;
    TAGS[nm]=pendColor; assignTag(id,nm); showItem(id);};
}

// ---- craft list view (targets + aggregated totals + have/left) ------------
function showList(){
  viewingList=true; sel=null; renderList();
  const ids=Object.keys(BUILD);
  if(!ids.length){detail.innerHTML=`<div class="empty">Your craft list is empty.<br>
    Open any item and hit <b>+ Add to craft list</b>.</div>`; return;}
  let h=`<div class="hd"><h2>My craft list</h2></div>
    <div class="sub">Pick what you want to make; totals and "what's left" update as you check things off.</div>`;
  // targets
  h+=`<div class="section"><h3>Items to make</h3><table class="roll">`;
  for(const id of ids){const it=ITEMS[id]||{name:id};
    h+=`<tr><td class="ic">${imgFor(id,'tico')}</td><td class="mname">${it.name}</td>
      <td><span class="qstep"><button data-bq="${id}" data-d="-1">−</button>
        <b>${BUILD[id]}</b><button data-bq="${id}" data-d="1">+</button></span></td>
      <td class="n"><span class="rm" data-rm="${id}">remove</span></td></tr>`;}
  h+=`</table></div>`;
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
    const ri=ITEMS[rid]||{name:rid,sources:[]}, s=ri.sources&&ri.sources[0];
    h+=`<tr class="${doneRow?'doneRow':''}">
      <td><input type="checkbox" class="havechk" data-chk="${rid}" data-need="${need}" ${doneRow?'checked':''}></td>
      <td class="ic">${imgFor(rid,'tico')}</td>
      <td class="mname">${ri.name}</td>
      <td class="base">${s?s.node+(s.chance!=null?` · ${s.chance}%`:''):'—'}</td>
      <td class="n">${need}</td>
      <td><input class="havein" type="number" min="0" data-have="${rid}" value="${have}"></td>
      <td class="n left ${left?'':'zero'}">${left}</td></tr>`;}
  h+=`</table>
    <div class="legend" style="margin-top:12px"><button id="clearlist">Clear list</button>
      &nbsp; tick the box (or type how many you have) to cross it off · totals combine every item above</div></div>`;
  detail.innerHTML=h;
  // wiring
  detail.querySelectorAll('[data-bq]').forEach(b=>b.onclick=()=>{
    const id=b.dataset.bq; BUILD[id]=(BUILD[id]||0)+(+b.dataset.d);
    if(BUILD[id]<=0) delete BUILD[id]; saveBuild(); showList();});
  detail.querySelectorAll('[data-rm]').forEach(e=>e.onclick=()=>{delete BUILD[e.dataset.rm]; saveBuild(); showList();});
  detail.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{listMode=b.dataset.mode; showList();});
  detail.querySelectorAll('.havechk').forEach(c=>c.onchange=()=>{
    HAVE[c.dataset.chk]=c.checked?(+c.dataset.need):0; saveHave(); showList();});
  detail.querySelectorAll('.havein').forEach(inp=>inp.onchange=()=>{
    const v=Math.max(0,parseInt(inp.value)||0); HAVE[inp.dataset.have]=v; saveHave(); showList();});
  document.getElementById('clearlist').onclick=()=>{
    if(confirm('Clear the whole craft list?')){BUILD={}; saveBuild(); showList();}};
}

list.onclick=e=>{
  const r=e.target.closest('.row');
  if(r){ if(r.dataset.tagfilter){tagFilter=tagFilter===r.dataset.tagfilter?null:r.dataset.tagfilter; renderList(); return;}
         if(r.dataset.id){showItem(r.dataset.id); return;} }
  const c=e.target.closest('.cathd');
  if(c){const k=c.dataset.cat; openCats.has(k)?openCats.delete(k):openCats.add(k); renderList();}
};
document.getElementById('listbtn').onclick=showList;
q.oninput=()=>{tagFilter=null; renderList();};
updateListN();
renderList();
</script>
</body></html>"""

out = TEMPLATE.replace("__DATA__", blob)
open(OUT, "w", encoding="utf-8").write(out)
print("wrote", OUT, f"({len(out)//1024} KB)")
