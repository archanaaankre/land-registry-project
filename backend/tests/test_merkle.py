"""Unit tests for the ownership Merkle tree module (backend/app/registry/merkle.py)."""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models import Ownership, OwnershipStatus
from app.registry.merkle import (
    canonical_leaf,
    generate_proof,
    merkle_root,
    sorted_leaves,
    verify_merkle_proof,
)

_CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _ownership(
    ownership_id,
    owner_id="user-asha",
    share="60.000000",
    status=OwnershipStatus.ACTIVE,
    parcel_id="parcel-1",
):
    return Ownership(
        ownership_id=ownership_id,
        parcel_id=parcel_id,
        owner_id=owner_id,
        share=Decimal(share),
        status=status,
        created_at=_CREATED,
        updated_at=_CREATED,
    )


def _combine(left_hex, right_hex):
    return hashlib.sha256(bytes.fromhex(left_hex) + bytes.fromhex(right_hex)).hexdigest()


def _leaves(*ids):
    return [canonical_leaf(_ownership(ownership_id=i)) for i in ids]


def test_canonical_leaf_matches_canonical_encoding():
    ownership = _ownership("ownership-1", share="60.000000")
    expected = hashlib.sha256(
        json.dumps(
            {
                "ownership_id": "ownership-1",
                "owner_id": "user-asha",
                "parcel_id": "parcel-1",
                "share": "60.000000",
                "status": "ACTIVE",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert canonical_leaf(ownership) == expected


def test_canonical_leaf_is_deterministic():
    ownership = _ownership("ownership-1")
    assert canonical_leaf(ownership) == canonical_leaf(_ownership("ownership-1"))


def test_canonical_leaf_differs_by_identity_fields():
    base = canonical_leaf(_ownership("ownership-1"))
    assert canonical_leaf(_ownership("ownership-2")) != base
    assert canonical_leaf(_ownership("ownership-1", owner_id="user-other")) != base
    assert canonical_leaf(_ownership("ownership-1", share="40.000000")) != base
    assert canonical_leaf(_ownership("ownership-1", status=OwnershipStatus.INACTIVE)) != base
    assert canonical_leaf(_ownership("ownership-1", parcel_id="parcel-2")) != base


def test_sorted_leaves_sorts_by_ownership_id():
    records = [
        _ownership("ownership-3"),
        _ownership("ownership-1"),
        _ownership("ownership-2"),
    ]
    assert sorted_leaves(records) == _leaves("ownership-1", "ownership-2", "ownership-3")


def test_merkle_root_empty():
    assert merkle_root([]) == hashlib.sha256(b"").hexdigest()


def test_merkle_root_single_leaf_is_the_leaf():
    leaves = _leaves("ownership-1")
    assert merkle_root(leaves) == leaves[0]


def test_merkle_root_two_leaves_known_vector():
    leaves = _leaves("ownership-1", "ownership-2")
    assert merkle_root(leaves) == _combine(leaves[0], leaves[1])


def test_merkle_root_three_leaves_duplicates_last_on_odd_level():
    leaves = _leaves("ownership-1", "ownership-2", "ownership-3")
    assert merkle_root(leaves) == _combine(
        _combine(leaves[0], leaves[1]), _combine(leaves[2], leaves[2])
    )


def test_merkle_root_changes_when_a_leaf_changes():
    assert merkle_root(_leaves("ownership-1")) != merkle_root(_leaves("ownership-2"))


def _expected_depth(n):
    depth = 0
    while n > 1:
        n = (n + n % 2) // 2
        depth += 1
    return depth


def test_proof_length_matches_expected_depth_for_all_indices():
    leaves = _leaves(*[f"ownership-{i:02d}" for i in range(1, 6)])
    root = merkle_root(leaves)
    for i in range(len(leaves)):
        proof = generate_proof(leaves, i)
        assert len(proof) == _expected_depth(len(leaves))
        assert verify_merkle_proof(root, leaves[i], proof)


def test_generate_proof_rejects_out_of_range_index():
    leaves = _leaves("ownership-1", "ownership-2")
    with pytest.raises(IndexError):
        generate_proof(leaves, 2)
    with pytest.raises(IndexError):
        generate_proof(leaves, -1)


def test_tampered_leaf_is_rejected():
    leaves = _leaves("ownership-1", "ownership-2", "ownership-3", "ownership-4")
    root = merkle_root(leaves)
    proof = generate_proof(leaves, 0)
    assert not verify_merkle_proof(root, "f" * 64, proof)


def test_tampered_proof_sibling_is_rejected():
    leaves = _leaves("ownership-1", "ownership-2", "ownership-3", "ownership-4")
    root = merkle_root(leaves)
    proof = generate_proof(leaves, 1)
    tampered = [{**proof[0], "hash": "f" * 64}]
    assert not verify_merkle_proof(root, leaves[1], tampered)


def test_truncated_proof_is_rejected():
    leaves = _leaves("ownership-1", "ownership-2", "ownership-3", "ownership-4")
    root = merkle_root(leaves)
    proof = generate_proof(leaves, 1)
    assert proof
    assert not verify_merkle_proof(root, leaves[1], proof[:-1])


def test_wrong_root_is_rejected():
    leaves = _leaves("ownership-1", "ownership-2")
    root = merkle_root(leaves)
    proof = generate_proof(leaves, 0)
    other_root = merkle_root(leaves[::-1])
    assert other_root != root
    assert not verify_merkle_proof(other_root, leaves[0], proof)
