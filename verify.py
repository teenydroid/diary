#!/usr/bin/env python3
"""Check Teeny's receipts. Python 3.9+, standard library only.

    python3 verify.py                       # the chain in this checkout
    python3 verify.py --base REF            # ...and that it only grew since REF
    python3 verify.py --reveal FILE         # a revealed {"seq", "salt", "record"}

A receipt is one line of receipts/YYYY/MM/YYYY-MM-DD.jsonl:

    {"at": ..., "commit": ..., "kind": ..., "prev": ..., "ref": {...}, "seq": N}

The chain holds when every line is canonical JSON (sorted keys, no spaces,
ASCII), the seqs run 1, 2, 3... across the files in path order, each `prev` is
the sha256 of the line before it (64 zeros for the first), each `commit` is 64
hex characters, and head.json is {"hash": <sha256 of the last line>, "seq": N}.

--base REF also checks the chain at REF is an exact prefix of this one, and
that nothing outside receipts/ and head.json changed since REF. CI runs it on
every push, so a receipt cannot be edited or removed quietly.

--reveal checks that sha256(salt || canonical(record)) equals the `commit` of
receipt `seq`, which proves that receipt stands for that exact record.

Exits 0 when everything holds, 1 with the first problem otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

GENESIS = "0" * 64
HEX64 = re.compile(r"[0-9a-f]{64}")
KIND = re.compile(r"[a-z]+\.[a-z-]+")
KEYS = {"at", "commit", "kind", "prev", "ref", "seq"}
AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
PATH = re.compile(r"receipts/\d{4}/\d{2}/\d{4}-\d{2}-\d{2}\.jsonl")


class Broken(Exception):
    pass


def canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def check(files: dict[str, str], head: str | None) -> list[dict]:
    """files maps each receipts path to its text. Returns the entries in order."""
    entries, seq, prev = [], 0, GENESIS
    for path in sorted(files):
        if not PATH.fullmatch(path):
            raise Broken(f"{path}: not a receipts file name")
        text = files[path]
        if text and not text.endswith("\n"):
            raise Broken(f"{path}: no newline at the end")
        for number, line in enumerate(text.splitlines(), 1):
            where = f"{path}:{number}"
            try:
                entry = json.loads(line)
            except ValueError:
                raise Broken(f"{where}: not JSON") from None
            if not isinstance(entry, dict) or set(entry) != KEYS:
                raise Broken(f"{where}: not a receipt")
            if canonical(entry) != line:
                raise Broken(f"{where}: not canonical JSON")
            if entry["seq"] != seq + 1:
                raise Broken(f"{where}: seq {entry['seq']}, expected {seq + 1}")
            if entry["prev"] != prev:
                raise Broken(f"{where}: prev does not match the line before")
            if not (isinstance(entry["commit"], str) and HEX64.fullmatch(entry["commit"])):
                raise Broken(f"{where}: commit is not a sha256")
            if not (isinstance(entry["kind"], str) and KIND.fullmatch(entry["kind"])):
                raise Broken(f"{where}: kind is not a kind")
            if not (isinstance(entry["at"], str) and AT.fullmatch(entry["at"])):
                raise Broken(f"{where}: at is not a UTC time")
            if not isinstance(entry["ref"], dict):
                raise Broken(f"{where}: ref is not an object")
            seq, prev = entry["seq"], sha(line)
            entries.append({"line": line, **entry})
    if head is None:
        if seq:
            raise Broken("head.json is missing")
    else:
        try:
            stated = json.loads(head)
        except ValueError:
            raise Broken("head.json is not JSON") from None
        if stated != {"seq": seq, "hash": prev}:
            raise Broken(f"head.json says {stated}, the chain ends at seq {seq} hash {prev}")
    return entries


def from_disk(root: Path) -> tuple[dict[str, str], str | None]:
    files = {p.relative_to(root).as_posix(): p.read_text(encoding="ascii")
             for p in (root / "receipts").rglob("*") if p.is_file()} if (root / "receipts").is_dir() else {}
    head = root / "head.json"
    return files, head.read_text(encoding="ascii") if head.is_file() else None


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def from_git(ref: str) -> tuple[dict[str, str], str | None]:
    names = [n for n in _git("ls-tree", "-r", "--name-only", ref).splitlines()]
    files = {n: _git("show", f"{ref}:{n}") for n in names if n.startswith("receipts/")}
    head = _git("show", f"{ref}:head.json") if "head.json" in names else None
    return files, head


def check_growth(base: str, now: list[dict]) -> None:
    before = check(*from_git(base))
    if [e["line"] for e in now[: len(before)]] != [e["line"] for e in before]:
        raise Broken(f"the chain at {base} is not a prefix of this one: a receipt was edited or removed")
    changed = [n for n in _git("diff", "--name-only", base, "HEAD").splitlines() if n]
    others = [n for n in changed if n != "head.json" and not n.startswith("receipts/")]
    # The README, this script and CI are humans' to change, by pull request.
    allowed = {"README.md", "verify.py", ".gitignore"}
    others = [n for n in others if n not in allowed and not n.startswith(".github/")]
    if others:
        raise Broken(f"changed outside receipts/: {', '.join(others)}")


def check_reveal(path: Path, entries: list[dict]) -> None:
    shown = json.loads(path.read_text(encoding="utf-8"))
    seq, salt, record = shown.get("seq"), shown.get("salt"), shown.get("record")
    match = [e for e in entries if e["seq"] == seq]
    if not match:
        raise Broken(f"no receipt {seq}")
    digest = hashlib.sha256(bytes.fromhex(salt) + canonical(record).encode("ascii")).hexdigest()
    if digest != match[0]["commit"]:
        raise Broken(f"the revealed record does not match receipt {seq}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", metavar="REF", help="also check the chain only grew since REF")
    parser.add_argument("--reveal", metavar="FILE", type=Path, help="check a revealed salt and record")
    args = parser.parse_args(argv)
    try:
        entries = check(*from_disk(Path.cwd()))
        if args.base:
            check_growth(args.base, entries)
        if args.reveal:
            check_reveal(args.reveal, entries)
    except Broken as problem:
        print(f"broken: {problem}")
        return 1
    print(f"ok: {len(entries)} receipts" + (f", head {entries[-1]['line'] and _head_hash(entries)}" if entries else ""))
    return 0


def _head_hash(entries: list[dict]) -> str:
    return sha(entries[-1]["line"])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
