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
that nothing else published changed since REF in a way it may not: the
days/ and memory/ chains only grow, a page in days/ or accounts/ is written
once and never changed, and only the numbers (stats/, world/, wallet.json),
the chain heads and memory/MEMORY.md are rewritten. CI runs it on every
push, so a receipt or a published page cannot be edited or removed quietly.

days/ (a diary page per finished day) and memory/ (Teeny's memory page, one
commit per dream) are the two folders of free text, each with a hash chain
of its own (chain.jsonl, head.json): {"seq", "prev", "sha256", ...}, where
sha256 is of the page's bytes. A days/ line names its page by "date"; a
memory/ line names its snapshot, and the newest one must be memory/MEMORY.md
(an older one is the page as its own commit left it).

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


#: Published files that are rewritten as they move: the numbers, the heads of
#: the text chains, and the memory page (its chain keeps every version's hash).
REWRITTEN = {"wallet.json", "days/head.json", "memory/head.json", "memory/MEMORY.md"}
REWRITTEN_DIRS = ("stats/", "world/")
#: Written once and never changed: a finished day's page, a closed week.
WRITTEN_ONCE_DIRS = ("days/", "accounts/")
#: Append-only: each version must start with the one before.
CHAINS = ("days/chain.jsonl", "memory/chain.jsonl")
#: The README, this script and CI are humans' to change, by pull request.
HUMANS = {"README.md", "verify.py", ".gitignore"}


def check_text_chain(root: Path, folder: str) -> int:
    """days/ or memory/: the chain holds, the head matches, and the pages
    match their hashes (every day; the newest memory snapshot). Returns its
    length."""
    chain, head = root / folder / "chain.jsonl", root / folder / "head.json"
    seq, prev, last = 0, GENESIS, None
    lines = chain.read_text(encoding="ascii").splitlines() if chain.is_file() else []
    for number, line in enumerate(lines, 1):
        where = f"{folder}/chain.jsonl:{number}"
        try:
            entry = json.loads(line)
        except ValueError:
            raise Broken(f"{where}: not JSON") from None
        if not isinstance(entry, dict) or canonical(entry) != line:
            raise Broken(f"{where}: not canonical JSON")
        if entry.get("seq") != seq + 1 or entry.get("prev") != prev:
            raise Broken(f"{where}: does not follow the line before")
        if not (isinstance(entry.get("sha256"), str) and HEX64.fullmatch(entry["sha256"])):
            raise Broken(f"{where}: sha256 is not a sha256")
        if folder == "days":
            page = root / "days" / f"{entry.get('date')}.md"
            if not page.is_file() or hashlib.sha256(page.read_bytes()).hexdigest() != entry["sha256"]:
                raise Broken(f"{where}: the page for {entry.get('date')} does not match")
        seq, prev, last = entry["seq"], sha(line), entry
    if folder == "memory" and last is not None:
        page = root / "memory" / "MEMORY.md"
        if not page.is_file() or hashlib.sha256(page.read_bytes()).hexdigest() != last["sha256"]:
            raise Broken("memory/MEMORY.md is not the newest snapshot in memory/chain.jsonl")
    if seq or head.is_file():
        try:
            stated = json.loads(head.read_text(encoding="ascii"))
        except (OSError, ValueError):
            raise Broken(f"{folder}/head.json is missing or not JSON") from None
        if stated != {"seq": seq, "hash": prev}:
            raise Broken(f"{folder}/head.json says {stated}, the chain ends at seq {seq} hash {prev}")
    return seq


def check_growth(base: str, now: list[dict]) -> None:
    before = check(*from_git(base))
    if [e["line"] for e in now[: len(before)]] != [e["line"] for e in before]:
        raise Broken(f"the chain at {base} is not a prefix of this one: a receipt was edited or removed")
    changes = [line.split("\t") for line in _git("diff", "--name-status", "--no-renames", base, "HEAD").splitlines() if line]
    wrong = []
    for status, name in ((c[0], c[-1]) for c in changes):
        if name == "head.json" or name.startswith("receipts/") or name in HUMANS or name.startswith(".github/"):
            continue
        if name in CHAINS:
            old = _git("show", f"{base}:{name}") if status != "A" else ""
            if status == "D" or not (root_text(name)).startswith(old):
                wrong.append(f"{name} (a chain may only grow)")
            continue
        if name in REWRITTEN or name.startswith(REWRITTEN_DIRS):
            continue
        if name.startswith(WRITTEN_ONCE_DIRS):
            if status != "A":
                wrong.append(f"{name} (written once, never changed)")
            continue
        wrong.append(name)
    if wrong:
        raise Broken(f"changed where it may not: {', '.join(wrong)}")


def root_text(name: str) -> str:
    path = Path.cwd() / name
    return path.read_text(encoding="ascii") if path.is_file() else ""


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
        for folder in ("days", "memory"):
            check_text_chain(Path.cwd(), folder)
        if args.base:
            check_growth(args.base, entries)
        if args.reveal:
            check_reveal(args.reveal, entries)
    except Broken as problem:
        print(f"broken: {problem}")
        return 1
    print(f"ok: {len(entries)} receipts" + (f", head {sha(entries[-1]['line'])}" if entries else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
