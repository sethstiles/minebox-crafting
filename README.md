# Minebox Crafting Browser

A single-page, offline-capable crafting reference for the [Minebox](https://minebox.co)
Minecraft server. Search any item, see its full recursive component tree, a rolled-up
raw-material shopping list, drop rates for gathered materials, and tag items with your
own custom labels.

**Live:** https://sethstiles.github.io/minebox-crafting/

## Features

- Browse by category (Weapons, Armor, Accessories, Tools, Consumables, Materials, …)
- Item icons, rarity, and level on every entry
- Click an item → expandable component tree (item → ingredients → sub-ingredients → raw)
- "Total raw materials" shopping list for any craft
- "Where to gather" table with node, min level, and drop %
- Custom tags (name + color) saved in your browser (localStorage), filterable

Everything is a single static `index.html` with all data embedded — no server, no
tracking. Custom tags never leave your browser.

## Data

All data comes from the public Minebox API (`api.minebox.co`): `/recipes`,
`/harvestables`, `/collections`, `/items`. This is an unofficial fan tool and is not
affiliated with Minebox; item names and art belong to Minebox.

## Rebuild

```sh
python fetch_data.py   # pulls fresh API data into ./data
python build.py        # regenerates index.html from ./data
```

`./data` is git-ignored (regenerable). Re-run both when Minebox adds items.
