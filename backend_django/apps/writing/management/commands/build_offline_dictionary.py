"""Rebuild the bundled offline EN-CN dictionary from an ECDICT CSV.

Usage:
    python manage.py build_offline_dictionary path/to/ecdict.csv

Source: https://github.com/skywind3000/ECDICT (ecdict.csv). We keep only single
English tokens that have a Chinese translation and look like real / exam
vocabulary (Collins, Oxford 3000, BNC or COCA frequency, or zk/gk/cet/ky/ielts/
toefl/gre tags), storing just word/phonetic/translation/definition. This shrinks
~770k raw rows to ~58k common entries (~10MB) suitable for bundling in the repo.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

EXAM_TAGS = ("zk", "gk", "cet4", "cet6", "ky", "ielts", "toefl", "gre")
OUTPUT_PATH = Path(settings.BASE_DIR).parent / "data" / "dictionary" / "offline_dict.sqlite3"


class Command(BaseCommand):
    help = "Build the bundled offline dictionary SQLite from an ECDICT CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to ecdict.csv")
        parser.add_argument(
            "--output", default=str(OUTPUT_PATH), help="Output SQLite path"
        )

    def handle(self, *args, **options):
        src = Path(options["csv_path"])
        if not src.exists():
            raise CommandError(f"CSV not found: {src}")
        out = Path(options["output"])
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()

        csv.field_size_limit(10_000_000)
        con = sqlite3.connect(str(out))
        con.execute(
            "CREATE TABLE entries (word TEXT PRIMARY KEY, phonetic TEXT, "
            "translation TEXT, definition TEXT)"
        )
        kept = 0
        rows: list[tuple] = []
        with open(src, encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # header
            for row in reader:
                if len(row) < 10:
                    continue
                word, phonetic, definition, translation = row[0], row[1], row[2], row[3]
                collins, oxford, tag, bnc, frq = row[5], row[6], row[7], row[8], row[9]
                w = word.strip().lower()
                if not w or " " in w:
                    continue
                if not translation.strip():
                    continue
                useful = (
                    collins.strip() not in ("", "0")
                    or oxford.strip() not in ("", "0")
                    or bnc.strip() not in ("", "0")
                    or frq.strip() not in ("", "0")
                    or any(t in tag for t in EXAM_TAGS)
                )
                if not useful:
                    continue
                rows.append((w, phonetic.strip(), translation.strip(), definition.strip()))
                kept += 1
                if len(rows) >= 5000:
                    con.executemany(
                        "INSERT OR REPLACE INTO entries(word,phonetic,translation,definition) "
                        "VALUES (?,?,?,?)",
                        rows,
                    )
                    rows.clear()
        if rows:
            con.executemany(
                "INSERT OR REPLACE INTO entries(word,phonetic,translation,definition) "
                "VALUES (?,?,?,?)",
                rows,
            )
        con.commit()
        con.execute("VACUUM")
        con.close()
        size_mb = round(out.stat().st_size / 1048576, 2)
        self.stdout.write(
            self.style.SUCCESS(f"Built {kept} entries -> {out} ({size_mb} MB)")
        )
