"""
Fetch all Minebox API data needed to build the crafting browser into ./data.

Pulls (api.minebox.co, all public, no auth):
  /recipes?job=X  for the 13 crafting jobs
  /harvestables   drop nodes + per-item drop %
  /collections    static checkpoint ladders
  /items          name / rarity / level / type / inline image (paginated)

Notes:
  - The API blocks the default Python-urllib User-Agent, so a browser UA is set.
  - /items pageSize is capped at ~50 (>=100 returns an empty body), so ~42 pages.
  - Rate limit is 10 requests / 10s; we fetch in bursts of 8 with a short pause.
"""
import json, os, time, urllib.request

BASE = "https://api.minebox.co"
UA = "Mozilla/5.0 (minebox-crafting-browser)"
DATA = os.path.join(os.path.dirname(__file__), "data")
JOBS = ["farmer", "fisherman", "runeforger", "shoemaker", "hunter", "jeweler",
        "lumberjack", "miner", "tailor", "tinkerer", "alchemist", "blacksmith", "cook"]

os.makedirs(DATA, exist_ok=True)

def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode().strip()
    return json.loads(body) if body else None

def save(name, obj):
    if obj is None:
        print("  (skip", name, "- empty response)"); return
    json.dump(obj, open(os.path.join(DATA, name), "w"))

def try_save(name, path):
    try:
        save(name, get(path))
    except Exception as e:
        print("  (skip", name, "-", e, ")")

def main():
    for j in JOBS:
        save(f"recipes_{j}.json", get(f"/recipes?job={j}"))
        print("recipes", j)
        time.sleep(1.2)
    try_save("harvestables.json", "/harvestables"); print("harvestables")
    try_save("collections.json", "/collections"); print("collections")
    try_save("sets.json", "/sets"); print("sets")

    page, n = 1, 0
    while True:
        d = get(f"/items?page={page}&pageSize=50")
        items = d.get("items", [])
        if not items:
            break
        save(f"items_p{page}.json", d)
        n += len(items)
        total = d.get("total", 0)
        print(f"items page {page}  ({n}/{total})")
        if n >= total:
            break
        page += 1
        if page % 8 == 0:
            time.sleep(11)
    print(f"done: {page} item pages, {n} items -> {DATA}")

if __name__ == "__main__":
    main()
