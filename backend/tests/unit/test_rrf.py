"""
tests/unit/test_rrf.py
───────────────────────
Unit tests for Reciprocal Rank Fusion (RRF) algorithm.
Pure unit tests — no database, no network calls.
"""
from __future__ import annotations

import pytest
from app.services.retrieval_service import compute_rrf


def test_rrf_empty_lists():
    assert compute_rrf([]) == []
    assert compute_rrf([[]]) == []
    assert compute_rrf([[], []]) == []


def test_rrf_single_list():
    items = ["doc_a", "doc_b", "doc_c"]
    k = 60
    results = compute_rrf([items], k=k)

    assert len(results) == 3
    # Check ordering
    assert [item for item, _ in results] == ["doc_a", "doc_b", "doc_c"]

    # Check exact mathematical formula
    expected_score_a = 1.0 / (k + 1)
    expected_score_b = 1.0 / (k + 2)
    expected_score_c = 1.0 / (k + 3)

    assert pytest.approx(results[0][1], rel=1e-5) == expected_score_a
    assert pytest.approx(results[1][1], rel=1e-5) == expected_score_b
    assert pytest.approx(results[2][1], rel=1e-5) == expected_score_c


def test_rrf_two_lists_fusion():
    """Items appearing in both lists should get boosted above single-list items."""
    list1 = ["doc_a", "doc_b", "doc_c"]
    list2 = ["doc_b", "doc_d", "doc_e"]
    k = 60

    results = compute_rrf([list1, list2], k=k)
    result_dict = dict(results)

    # doc_b is rank 2 in list1 (1/62) and rank 1 in list2 (1/61)
    expected_b = (1.0 / 62) + (1.0 / 61)
    assert pytest.approx(result_dict["doc_b"], rel=1e-5) == expected_b

    # doc_a is rank 1 in list1 only
    expected_a = 1.0 / 61
    assert pytest.approx(result_dict["doc_a"], rel=1e-5) == expected_a

    # doc_b must rank #1 overall because it appeared high in both
    assert results[0][0] == "doc_b"


def test_rrf_custom_k():
    items = ["chunk_1", "chunk_2"]
    results_k10 = compute_rrf([items], k=10)
    assert pytest.approx(results_k10[0][1], rel=1e-5) == 1.0 / 11.0
    assert pytest.approx(results_k10[1][1], rel=1e-5) == 1.0 / 12.0


def test_rrf_disjoint_lists():
    list1 = ["doc_x"]
    list2 = ["doc_y"]
    results = compute_rrf([list1, list2], k=60)
    result_dict = dict(results)

    # Both are rank 1 in their respective lists
    assert pytest.approx(result_dict["doc_x"], rel=1e-5) == 1.0 / 61
    assert pytest.approx(result_dict["doc_y"], rel=1e-5) == 1.0 / 61
    assert len(results) == 2


def test_rrf_multiple_rankers():
    """Test fusion across 3 rankers."""
    list1 = ["a", "b"]
    list2 = ["b", "c"]
    list3 = ["b", "a"]
    k = 60

    results = compute_rrf([list1, list2, list3], k=k)
    # 'b' appears in all three: rank 2 + rank 1 + rank 1
    expected_b = (1.0 / 62) + (1.0 / 61) + (1.0 / 61)
    assert results[0][0] == "b"
    assert pytest.approx(dict(results)["b"], rel=1e-5) == expected_b
