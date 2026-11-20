"""Application-side Merkle tree over ownership records.

The root and proofs are computed from local ``ownerships`` rows only. The
root is NOT blockchain-anchored: nothing here verifies on-chain inclusion or
attests ledger finality; the API surface is read-only over application data.

Conventions:

- Leaf: ``sha256`` (hex digest) of the canonical JSON encoding of an
  ``Ownership`` record — see ``canonical_leaf``.
- Internal node: ``_combine(left_hex, right_hex)`` — ``sha256`` of the
  concatenated bytes (``bytes.fromhex``) of both child hashes.
- Tree: leaves are ``sorted_leaves(ownerships)`` — sorted by
  ``ownership_id`` (unique primary key, so the order is a total order
  independent of query order). When a level has an odd number of nodes, the
  last hash is duplicated before pairing.
- Root of an empty leaf list: ``sha256(b"")`` hex digest.
"""

import hashlib
import json
from decimal import Decimal

from app.models import Ownership


def canonical_leaf(ownership: Ownership) -> str:
    """SHA-256 hex digest of the canonical JSON encoding of one ownership.

    The canonical form is ``json.dumps`` of the object
    ``{"ownership_id", "owner_id", "parcel_id", "share", "status"}`` with
    ``sort_keys=True`` and ``separators=(",", ":")``, where ``share`` is
    ``format(Decimal(ownership.share), "f")`` and ``status`` is
    ``ownership.status.value``.
    """
    payload = json.dumps(
        {
            "ownership_id": ownership.ownership_id,
            "owner_id": ownership.owner_id,
            "parcel_id": ownership.parcel_id,
            "share": format(Decimal(ownership.share), "f"),
            "status": ownership.status.value,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sorted_leaves(ownerships) -> list[str]:
    """Canonical leaf hashes for ``ownerships``, sorted by ``ownership_id``."""
    return [
        canonical_leaf(ownership)
        for ownership in sorted(ownerships, key=lambda o: o.ownership_id)
    ]


def _combine(left_hex: str, right_hex: str) -> str:
    return hashlib.sha256(bytes.fromhex(left_hex) + bytes.fromhex(right_hex)).hexdigest()


def _pair(level: list[str]) -> list[str]:
    if len(level) % 2 == 1:
        level = level + [level[-1]]
    return [_combine(level[i], level[i + 1]) for i in range(0, len(level), 2)]


def merkle_root(leaf_hashes) -> str:
    """Merkle root of ``leaf_hashes``.

    Odd level counts duplicate the final hash before pairing. An empty tree
    yields ``sha256(b"")``.
    """
    level = list(leaf_hashes)
    if not level:
        return hashlib.sha256(b"").hexdigest()
    while len(level) > 1:
        level = _pair(level)
    return level[0]


def generate_proof(leaf_hashes, index: int) -> list[dict]:
    """Inclusion proof of leaf ``index`` as ``[{"hash", "side"}, ...]``.

    ``side`` is ``"right"`` when the leaf is the left child of its pair (the
    sibling is on the right) and ``"left"`` when the leaf is the right child
    (the sibling is on the left). Raises ``IndexError`` if ``index`` is out
    of range.
    """
    leaves = list(leaf_hashes)
    if not 0 <= index < len(leaves):
        raise IndexError("leaf index out of range")
    proof = []
    level = leaves
    idx = index
    while len(level) > 1:
        if len(level) % 2 == 1:
            level = level + [level[-1]]
        if idx % 2 == 0:
            proof.append({"hash": level[idx + 1], "side": "right"})
        else:
            proof.append({"hash": level[idx - 1], "side": "left"})
        level = [_combine(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        idx //= 2
    return proof


def verify_merkle_proof(root: str, leaf: str, proof) -> bool:
    """Verify that ``leaf`` is a member of the tree with root ``root``.

    Recomputes the root from ``leaf`` and the proof steps; returns ``True``
    when the recomputed root equals ``root``.
    """
    current = leaf
    for step in proof:
        sibling = step["hash"]
        if step["side"] == "right":
            current = _combine(current, sibling)
        else:
            current = _combine(sibling, current)
    return current == root
