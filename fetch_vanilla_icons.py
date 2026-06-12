"""
Fetch Minecraft textures for items the Minebox API has no art for (vanilla
logs, ores, crops, etc.) and write them to ./data/vanilla_icons.json as
{itemId: base64png}. build.py merges these as fallback icons.

Source: InventivetalentDev/minecraft-assets (vanilla 16x16 item/block textures).
"""
import json, glob, os, base64, urllib.request

DATA = os.path.join(os.path.dirname(__file__), "data")
VER = "1.21.4"
CDN = f"https://raw.githubusercontent.com/InventivetalentDev/minecraft-assets/{VER}/assets/minecraft/textures"
UA = "Mozilla/5.0 (minebox-crafting-browser)"

# ---- figure out which universe items are missing an icon -------------------
items = {}
for f in glob.glob(os.path.join(DATA, "items_p*.json")):
    for it in json.load(open(f)).get("items", []):
        items[it["id"]] = it
recipes = {}
for f in glob.glob(os.path.join(DATA, "recipes_*.json")):
    for r in (json.load(open(f)).get("recipes") or []):
        recipes[r["id"]] = r
uni = set(recipes)
for r in recipes.values():
    for i in r["ingredients"]:
        uni.add(i["id"])
missing = [i for i in uni if not (i in items and items[i].get("image"))]

def candidates(idstr):
    """Texture-name guesses for a Minebox id, best first."""
    out = []
    def add(s):
        if s and s not in out:
            out.append(s)
    add(idstr)
    if "-" in idstr:                       # bag_material-bamboo -> bamboo
        add(idstr.split("-")[-1])
    if "_" in idstr:                        # log_olive_tree style fallbacks
        add(idstr.split("_", 1)[1])
        add(idstr.rsplit("_", 1)[-1])
    return out

def fetch(path):
    try:
        req = urllib.request.Request(f"{CDN}/{path}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
            if data[:4] == b"\x89PNG":
                return base64.b64encode(data).decode()
    except Exception:
        pass
    return None

icons = {}
tried = 0
for idstr in missing:
    for cand in candidates(idstr):
        b64 = fetch(f"item/{cand}.png") or fetch(f"block/{cand}.png")
        tried += 1
        if b64:
            icons[idstr] = b64
            break
    if len(icons) % 25 == 0 and icons:
        print(f"  ...{len(icons)} found")

json.dump(icons, open(os.path.join(DATA, "vanilla_icons.json"), "w"))
print(f"DONE: matched {len(icons)}/{len(missing)} missing items -> data/vanilla_icons.json")
