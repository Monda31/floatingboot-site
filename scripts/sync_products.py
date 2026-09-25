#!/usr/bin/env python3
"""
Sync the hardcoded product list in index.html with the live Fourthwall catalog.

Why: the site's product grid is a static list (slug/img/price per product).
When a product is edited in Fourthwall (e.g. adding the QR code on the back,
2026-09-23) its mockup gets a new image URL, and renaming a product changes
its slug -- the 3 Milan Duomo tees were 404ing on the site for exactly that
reason. This rewrites slug/img/price in place for every product the site
already shows; it never removes products or touches existing names/tags/layout.
Since 2026-09-25 it also ADDS live products missing from the site (13 stadium
tees/caps, incl. the Como Sinigaglia tee, had never been added), inserted after
the last entry of the same tag.

Matching: by slug first; if the slug no longer exists (product renamed),
by the site's display name against the live product name.

Usage: sync_products.py [--push]   (--push commits + pushes if anything changed)
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, "/home/mnddra/.claude/skills/floatingboot-tiktok-daily/scripts")
import next_product  # noqa: E402  (reuses its Fourthwall API client + credentials)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "index.html")

ENTRY_RE = re.compile(
    r'\{name:"(?P<name>(?:\\.|[^"\\])*)", price:(?P<price>[\d.]+), (?P<mid>tag:"[^"]*", tagLabel:"[^"]*"), '
    r'slug:"(?P<slug>[^"]*)",(?P<ws>\s*)img:"(?P<img>[^"]*)"\}'
)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    push = "--push" in sys.argv
    if push:
        # The repo is pushed from both the VPS (daily cron) and the PC
        # (interactive sessions) since 2026-09-24 -- always start from the
        # latest remote state or the push fails non-fast-forward.
        subprocess.run(["git", "-C", REPO, "pull", "-q", "--rebase"], check=True)
    live = next_product.fetch_products()
    by_slug = {p["slug"]: p for p in live}
    by_name = {norm(p["name"]): p for p in live}

    html = open(INDEX, encoding="utf-8").read()
    changes, unmatched = [], []

    def fix(m):
        p = by_slug.get(m["slug"]) or by_name.get(norm(m["name"]))
        if not p:
            unmatched.append(m["slug"])
            return m.group(0)
        price = f'{float(p["price"]):.1f}' if p.get("price") is not None else m["price"]
        img = p.get("image_url") or m["img"]
        what = [k for k, a, b in (("slug", m["slug"], p["slug"]), ("img", m["img"], img),
                                  ("price", m["price"], price)) if a != b]
        if what:
            changes.append(f'{m["name"]}: {", ".join(what)}')
        return (f'{{name:"{m["name"]}", price:{price}, {m["mid"]}, slug:"{p["slug"]}",'
                f'{m["ws"]}img:"{img}"}}')

    new_html = ENTRY_RE.sub(fix, html)

    # add live products that the site doesn't list yet
    TAGS = {"stadi": "Stadi d'Italia", "cap": "Cap", "felpa": "Hoodie", "ukiyo": "Ukiyo-e Wave",
            "vintage": "Vintage Travel", "line": "Minimal Line"}
    STADIUM = ("Stadio", "Allianz", "Gewiss", "Unipol", "Dacia", "Arena")

    def tag_for(p):
        if p["name"].startswith(STADIUM):
            return "stadi"
        if "Felpa" in p["name"]:
            return "felpa"
        if p["name"].endswith("Cap"):
            return "cap"
        return {"Ukiyo-e Wave": "ukiyo", "Vintage Travel": "vintage", "Minimal Line": "line"}.get(p.get("collection_tag"))

    added = []
    on_site = {m["slug"] for m in ENTRY_RE.finditer(new_html)}
    for p in live:
        if p["slug"] in on_site or not p.get("image_url") or p.get("price") is None:
            continue
        tag = tag_for(p)
        same = [m for m in ENTRY_RE.finditer(new_html) if f'tag:"{tag}"' in m["mid"]]
        if not tag or not same:
            print("  ? no place for", p["slug"])
            continue
        name = p["name"].replace('"', '\\"')
        entry = (f'{{name:"{name}", price:{float(p["price"]):.1f}, tag:"{tag}", tagLabel:"{TAGS[tag]}", '
                 f'slug:"{p["slug"]}",\n      img:"{p["image_url"]}"}}')
        end = same[-1].end()
        new_html = new_html[:end] + ",\n    " + entry + new_html[end:]
        added.append(p["name"])
        changes.append(f'{p["name"]}: added')
    total = len(ENTRY_RE.findall(html))
    print(f"site products: {total}, changed: {len(changes)}, added: {len(added)}, unmatched: {len(unmatched)}")
    for c in changes:
        print("  ~", c)
    for u in unmatched:
        print("  ! not in live catalog:", u)
    if total == 0:
        print("ERROR: no product entries parsed -- index.html format changed?", file=sys.stderr)
        sys.exit(1)

    if new_html != html:
        open(INDEX, "w", encoding="utf-8").write(new_html)
        if push:
            subprocess.run(["git", "-C", REPO, "add", "index.html"], check=True)
            subprocess.run(["git", "-C", REPO, "commit", "-q", "-m",
                            f"Sync {len(changes)} product(s) with live Fourthwall catalog\n\n"
                            + "\n".join(changes)], check=True)
            subprocess.run(["git", "-C", REPO, "push", "-q"], check=True)
            print("pushed")


if __name__ == "__main__":
    main()
