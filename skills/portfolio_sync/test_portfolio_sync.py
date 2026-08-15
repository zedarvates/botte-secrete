"""Tests for deterministic, read-only portfolio synchronization."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skills.portfolio_sync.cli import main
from skills.portfolio_sync.core import (
    PortfolioError,
    compare_github_inventory,
    load_observed_inventory,
    load_registry,
    summarize_registry,
    validate_registry,
)


def _registry() -> dict:
    return {
        "schema_version": 1,
        "owner": "zedarvates",
        "status_values": [
            "active",
            "maintenance",
            "incubation",
            "publication",
            "needs-review",
            "archived",
        ],
        "priority_values": [
            "critical",
            "high",
            "medium",
            "low",
            "unclassified",
        ],
        "policies": {
            "secrets": "never-store",
            "absolute_local_paths": "never-store",
        },
        "programs": {
            "ai-forge": [
                {
                    "id": "botte-secrete",
                    "source": "github:zedarvates/botte-secrete",
                    "visibility": "private",
                    "status": "active",
                    "priority": "critical",
                    "confidentiality": "restricted",
                }
            ],
            "research": [
                {
                    "id": "shardjepa-publications",
                    "source": "github:zedarvates/shardjepa-publications",
                    "visibility": "public",
                    "status": "publication",
                    "priority": "high",
                    "confidentiality": "public",
                },
                {
                    "id": "local-research",
                    "source": "local-private",
                    "visibility": "restricted",
                    "status": "incubation",
                    "priority": "medium",
                    "confidentiality": "confidential",
                },
            ],
        },
    }


def test_validate_and_summarize_registry() -> None:
    registry = _registry()
    report = validate_registry(registry)
    assert report["projects"] == 3
    assert report["github_projects"] == 2

    summary = summarize_registry(registry)
    assert summary["by_status"] == {
        "active": 1,
        "incubation": 1,
        "publication": 1,
    }
    assert summary["by_source_type"] == {"github": 2, "local-private": 1}


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value["programs"]["research"][0].update(
                {"id": "botte-secrete"}
            ),
            "duplicate project id",
        ),
        (
            lambda value: value["programs"]["research"][0].update(
                {"status": "imaginary"}
            ),
            "status is not declared",
        ),
        (
            lambda value: value["programs"]["research"][0].update(
                {"source": "github:missing-slash"}
            ),
            "invalid GitHub form",
        ),
        (
            lambda value: value.update({"api_key": "live-secret"}),
            "sensitive value is forbidden",
        ),
        (
            lambda value: value["programs"]["research"][0].update(
                {"notes": r"F:\\private\\project"}
            ),
            "absolute local path is forbidden",
        ),
        (
            lambda value: value["programs"]["research"][0].update(
                {"notes": "file:///home/user/private/project"}
            ),
            "absolute local path is forbidden",
        ),
        (
            lambda value: value["programs"]["research"][0].update(
                {"notes": "file:///C:/Users/user/private/project"}
            ),
            "absolute local path is forbidden",
        ),
    ],
)
def test_registry_rejects_unsafe_or_ambiguous_data(mutator, message: str) -> None:
    registry = copy.deepcopy(_registry())
    mutator(registry)
    with pytest.raises(PortfolioError, match=message):
        validate_registry(registry)


@pytest.mark.parametrize(
    "key",
    [
        "secret",
        "secrets",
        "secret_key",
        "auth_token",
        "refresh_token",
        "bearer_token",
        "github_token",
        "credentials",
        "secret_access_key",
    ],
)
def test_registry_rejects_common_sensitive_key_variants(key: str) -> None:
    registry = copy.deepcopy(_registry())
    registry[key] = "live-secret-value"
    with pytest.raises(PortfolioError, match="sensitive value is forbidden"):
        validate_registry(registry)


def test_registry_rejects_sensitive_container_value() -> None:
    registry = copy.deepcopy(_registry())
    registry["secrets"] = {"service": "example", "value": "live-secret-value"}
    with pytest.raises(PortfolioError, match="sensitive value is forbidden"):
        validate_registry(registry)


@pytest.mark.parametrize("sentinel", ["never-store", "redacted", "env-only"])
def test_registry_allows_safe_sensitive_sentinels(sentinel: str) -> None:
    registry = copy.deepcopy(_registry())
    registry["secrets"] = sentinel
    assert validate_registry(registry)["valid"] is True


@pytest.mark.parametrize(
    "source",
    [
        "github:/repo",
        "github:owner/",
        "github:-bad/repo",
        "github:bad-/repo",
        "github:owner/..",
        "github:owner/repo name",
    ],
)
def test_registry_rejects_invalid_github_segments(source: str) -> None:
    registry = copy.deepcopy(_registry())
    registry["programs"]["research"][0]["source"] = source
    with pytest.raises(PortfolioError, match="invalid GitHub form"):
        validate_registry(registry)


@pytest.mark.parametrize("full_name", ["/repo", "owner/", "bad-/repo"])
def test_observed_inventory_rejects_invalid_github_segments(
    tmp_path: Path,
    full_name: str,
) -> None:
    observed_path = tmp_path / "repos.json"
    observed_path.write_text(
        json.dumps({"repositories": [{"full_name": full_name}]}),
        encoding="utf-8",
    )
    with pytest.raises(PortfolioError, match="valid full_name"):
        load_observed_inventory(observed_path)


def test_compare_inventory_reports_drift_without_writing() -> None:
    registry = _registry()
    observed = [
        {
            "full_name": "zedarvates/botte-secrete",
            "private": False,
            "archived": False,
        },
        {
            "full_name": "zedarvates/new-repository",
            "private": True,
            "archived": False,
        },
    ]

    report = compare_github_inventory(registry, observed)
    assert report["read_only"] is True
    assert report["matched"] == 1
    assert report["missing_in_registry"] == ["zedarvates/new-repository"]
    assert report["registered_not_observed"] == [
        "zedarvates/shardjepa-publications"
    ]
    assert report["visibility_mismatches"][0]["project_id"] == "botte-secrete"
    assert report["drift_count"] == 3
    assert report["clean"] is False


def test_loaders_and_cli_use_utf8_json(tmp_path: Path, capsys) -> None:
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(
        json.dumps(_registry(), ensure_ascii=False),
        encoding="utf-8",
    )
    observed_path = tmp_path / "repos.json"
    observed_path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "name": "botte-secrete",
                        "private": True,
                        "archived": False,
                    },
                    {
                        "name": "shardjepa-publications",
                        "private": False,
                        "archived": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded = load_registry(registry_path)
    inventory = load_observed_inventory(observed_path, owner="zedarvates")
    assert loaded["owner"] == "zedarvates"
    assert len(inventory) == 2

    code = main(
        [
            "diff",
            "--registry",
            str(registry_path),
            "--json",
            "--observed",
            str(observed_path),
            "--owner",
            "zedarvates",
            "--fail-on-drift",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["clean"] is True
