import json
import sqlite3

cfg = json.load(open("config.json"))
db = sqlite3.connect(cfg["library_path"] + "/metadata.db")
rows = db.execute(
    "SELECT t.name, COUNT(btl.book) cnt "
    "FROM tags t JOIN books_tags_link btl ON btl.tag=t.id "
    "GROUP BY t.id ORDER BY cnt DESC, t.name"
).fetchall()
with open("tags_export.txt", "w", encoding="utf-8") as f:
    for name, cnt in rows:
        f.write(f"{cnt:5}  {name}\n")
print(f"{len(rows)} tags written to tags_export.txt")
