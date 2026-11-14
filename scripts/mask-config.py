#!/usr/bin/env python3
"""Produce a fully masked copy of a sing-box config for safe publication.

Unlike a partial mask that keeps the first and last few characters plus the
length, every secret here is replaced entirely. Partial masking still leaks
entropy: a 43-char base64url key with 6 known characters leaves the rest
brute-forceable for a motivated attacker.
"""
import json
import sys
from pathlib import Path

MASKED = "<REDACTED>"

# Every field that must never survive masking. "*" matches every list element
# or every dict value at that level.
SECRET_PATHS = [
    ("inbounds", "*", "users", "*", "uuid"),
    ("inbounds", "*", "users", "*", "password"),
    ("inbounds", "*", "password"),
    ("inbounds", "*", "tls", "reality", "private_key"),
    ("inbounds", "*", "tls", "reality", "short_id"),
    ("endpoints", "*", "auth_key"),
    ("endpoints", "*", "private_key"),
    ("experimental", "clash_api", "secret"),
    ("services", "*", "secret"),
]


def _walk(node, path):
    """Recursively apply a path pattern; "*" fans out over lists and dicts."""
    if node is None:
        return
    if not path:
        return

    head, rest = path[0], path[1:]

    if head == "*":
        if isinstance(node, list):
            for item in node:
                _walk(item, rest)
        elif isinstance(node, dict):
            for key in list(node.keys()):
                _walk(node[key], rest)
        return

    if isinstance(node, list):
        for item in node:
            _walk(item, path)
        return

    if not isinstance(node, dict) or head not in node:
        return

    if not rest:
        value = node[head]
        if isinstance(value, list):
            # e.g. reality short_id: replace the whole list with one placeholder
            node[head] = [MASKED]
        elif value:
            node[head] = MASKED
        return

    _walk(node[head], rest)


def mask(cfg):
    for path in SECRET_PATHS:
        _walk(cfg, list(path))
    return cfg


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mask-config.py <input.json> <output.json>", file=sys.stderr)
        return 2
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = mask(json.loads(src.read_text(encoding="utf-8")))

    if "_meta" in cfg:
        cfg["_meta"].pop("reality_public_key", None)
        if not cfg["_meta"]:
            cfg.pop("_meta")

    cfg["_note"] = "masked copy: all credentials replaced, structure only"

    dst.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("wrote " + str(dst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

