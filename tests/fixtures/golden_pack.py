"""Test-only registry and integrity loader for the default Golden Pack."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES_ROOT = REPOSITORY_ROOT / "tests" / "live" / "fixtures"
DEFAULT_SELECTOR = "default"
MATERIALIZATION_COMMAND = "python scripts/materialize_higgsfield_multimodal_pack.py"
REQUIRED_MEDIA_TYPES = frozenset({"IMAGE", "VIDEO", "AUDIO"})
REQUIRED_VIDEO_ROLES = frozenset(
    {
        "video_playblast",
        "video_control",
        "video_camera",
        "video_motion",
        "video_timing",
        "video_environment",
    }
)
REQUIRED_AUDIO_ROLES = frozenset({"audio_reference", "audio_timing", "audio_ambience"})
UPSTREAM_ROLES = {
    "IMAGE": "image_reference",
    "VIDEO": "video_reference",
    "AUDIO": "audio_reference",
}


class GoldenPackError(ValueError):
    """The selector or manifest violates the test-only Golden Pack schema."""


class GoldenPackIntegrityError(GoldenPackError):
    """A materialized file differs from its manifest identity."""


@dataclass(frozen=True, slots=True)
class AssetVerification:
    state: str
    checked_asset_ids: tuple[str, ...]
    missing_asset_ids: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state == "READY"


@dataclass(frozen=True, slots=True)
class GoldenPack:
    fixtures_root: Path
    selector_path: Path
    manifest_path: Path
    manifest: dict[str, Any]

    @property
    def pack_root(self) -> Path:
        return self.manifest_path.parent

    @property
    def pack_id(self) -> str:
        return str(self.manifest["id"])

    @property
    def assets_by_id(self) -> dict[str, dict[str, Any]]:
        return {asset["asset_id"]: asset for asset in self.manifest["assets"]}

    @property
    def canonical_references(self) -> tuple[dict[str, Any], ...]:
        """Resolve ordered occurrences from manifest data; never duplicate order in code."""
        assets = self.assets_by_id
        return tuple(
            {**assets[item["asset_id"]], "position": item["position"]}
            for item in self.manifest["canonical_mmr2v_order"]
        )

    @property
    def semantic_roles(self) -> dict[str, tuple[str, ...]]:
        return {asset["asset_id"]: tuple(asset["roles"]) for asset in self.manifest["assets"]}

    @property
    def transport_mapping(self) -> dict[str, dict[str, str]]:
        return {asset["asset_id"]: dict(asset["transport"]) for asset in self.manifest["assets"]}

    def verify_local_assets(self) -> AssetVerification:
        checked: list[str] = []
        missing: list[str] = []
        for asset in self.manifest["assets"]:
            path = _contained_path(self.pack_root, asset["path"])
            if not path.is_file():
                missing.append(asset["asset_id"])
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.stat().st_size != asset["bytes"] or digest != asset["sha256"]:
                raise GoldenPackIntegrityError(
                    f"Asset integrity mismatch for {asset['asset_id']}: {path}"
                )
            checked.append(asset["asset_id"])
        return AssetVerification(
            state="MATERIALIZATION_REQUIRED" if missing else "READY",
            checked_asset_ids=tuple(checked),
            missing_asset_ids=tuple(missing),
        )


def load_default_pack(
    *, fixtures_root: Path | None = None, selector: str = DEFAULT_SELECTOR
) -> GoldenPack:
    """Load and schema-check the selected test fixture without network access."""
    if selector != DEFAULT_SELECTOR:
        raise GoldenPackError(f"Unsupported Golden Pack selector: {selector}")
    root = (fixtures_root or DEFAULT_FIXTURES_ROOT).resolve()
    selector_path = _contained_path(root, "default_golden_pack.json")
    selector_data = _load_json(selector_path)
    if selector_data.get("schema_version") != 1:
        raise GoldenPackError("Unsupported default Golden Pack selector schema_version")
    manifest_path = _contained_path(root, selector_data.get("manifest", ""))
    if not manifest_path.is_file():
        raise GoldenPackError(f"Default Golden Pack manifest is missing: {manifest_path}")
    manifest = _load_json(manifest_path)
    validate_manifest(manifest, pack_root=manifest_path.parent)
    if manifest["id"] != selector_data.get("default_pack_id"):
        raise GoldenPackError("Default selector id does not match the selected manifest")
    return GoldenPack(root, selector_path, manifest_path, manifest)


def load_manifest(*, fixtures_root: Path | None = None) -> dict[str, Any]:
    """Load the default selected pack manifest through the test-only registry."""
    return load_default_pack(fixtures_root=fixtures_root).manifest


def validate_manifest(manifest: dict[str, Any], *, pack_root: Path | None = None) -> None:
    """Validate schema and core multimodal ordering/role/transport invariants."""
    if manifest.get("schema_version") != 1:
        raise GoldenPackError("Unsupported Golden Pack manifest schema_version")
    if not isinstance(manifest.get("id"), str) or not manifest["id"]:
        raise GoldenPackError("Golden Pack manifest id is required")
    if manifest.get("generation_target_seconds") != 5:
        raise GoldenPackError("Golden Pack output target must remain five seconds")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise GoldenPackError("Golden Pack manifest assets must be a nonempty list")

    asset_ids: set[str] = set()
    canonical_assets: dict[str, dict[str, Any]] = {}
    for asset in assets:
        asset_id = asset.get("asset_id")
        media_type = asset.get("type")
        if not isinstance(asset_id, str) or asset_id in asset_ids:
            raise GoldenPackError("Golden Pack asset ids must be unique strings")
        asset_ids.add(asset_id)
        if media_type not in REQUIRED_MEDIA_TYPES:
            raise GoldenPackError(f"Unsupported Golden Pack media type: {media_type}")
        if not isinstance(asset.get("path"), str) or not asset["path"]:
            raise GoldenPackError(f"Asset path is required: {asset_id}")
        if not isinstance(asset.get("upstream_filename"), str):
            raise GoldenPackError(f"Upstream filename is required: {asset_id}")
        if not isinstance(asset.get("source_url"), str) or not asset["source_url"].startswith(
            "https://"
        ):
            raise GoldenPackError(f"HTTPS source URL is required: {asset_id}")
        if not isinstance(asset.get("bytes"), int) or asset["bytes"] < 1:
            raise GoldenPackError(f"Positive byte count is required: {asset_id}")
        digest = asset.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise GoldenPackError(f"SHA-256 is required: {asset_id}")
        if not isinstance(asset.get("media_metadata"), dict):
            raise GoldenPackError(f"Media metadata is required: {asset_id}")
        if asset.get("modified") is not False:
            raise GoldenPackError(f"Golden Pack originals must remain unmodified: {asset_id}")
        if not isinstance(asset.get("roles"), list) or not asset["roles"]:
            raise GoldenPackError(f"Semantic roles are required: {asset_id}")
        transport = asset.get("transport")
        if not isinstance(transport, dict) or set(transport) != {"upstream_role", "wire_type"}:
            raise GoldenPackError(f"Transport mapping is required: {asset_id}")
        if transport.get("upstream_role") != UPSTREAM_ROLES[media_type]:
            raise GoldenPackError(f"Transport role does not match media type: {asset_id}")
        if transport.get("wire_type") != f"{media_type.casefold()}_url":
            raise GoldenPackError(f"Transport wire type does not match {asset_id}")
        canonical_assets[asset_id] = asset

    ordered = manifest.get("canonical_mmr2v_order")
    if not isinstance(ordered, list) or not ordered:
        raise GoldenPackError("Canonical MMR2V order is required")
    if [item.get("position") for item in ordered] != list(range(1, len(ordered) + 1)):
        raise GoldenPackError("Canonical MMR2V order positions must be contiguous and one-based")
    ordered_ids = [item.get("asset_id") for item in ordered]
    if len(ordered_ids) != len(set(ordered_ids)):
        raise GoldenPackError("Canonical MMR2V order cannot contain duplicate occurrences")
    try:
        ordered_types = [canonical_assets[item["asset_id"]]["type"] for item in ordered]
    except KeyError as error:
        raise GoldenPackError(f"Canonical order references an unknown asset: {error}") from error
    if not set(ordered_types) >= REQUIRED_MEDIA_TYPES:
        raise GoldenPackError("Canonical MMR2V order must include IMAGE, VIDEO, and AUDIO")
    type_rank = {"IMAGE": 0, "VIDEO": 1, "AUDIO": 2}
    if [type_rank[media_type] for media_type in ordered_types] != sorted(
        type_rank[media_type] for media_type in ordered_types
    ):
        raise GoldenPackError("Canonical MMR2V order must preserve IMAGE → VIDEO → AUDIO")
    if manifest.get("paid_generation") != {"status": "not_run", "post_count": 0}:
        raise GoldenPackError("Golden Pack validation must keep paid generation at zero")

    video_assets = [asset for asset in assets if asset["type"] == "VIDEO"]
    audio_assets = [asset for asset in assets if asset["type"] == "AUDIO"]
    if not any(set(asset["roles"]) >= REQUIRED_VIDEO_ROLES for asset in video_assets):
        raise GoldenPackError("A VIDEO must carry all required playblast/control roles")
    if not any(set(asset["roles"]) >= REQUIRED_AUDIO_ROLES for asset in audio_assets):
        raise GoldenPackError("An AUDIO must carry all required reference/timing roles")
    _validate_duplicate_fixture(manifest, asset_ids, pack_root)


def _validate_duplicate_fixture(
    manifest: dict[str, Any], asset_ids: set[str], pack_root: Path | None
) -> None:
    relative = manifest.get("duplicate_reference_regression_fixture")
    if relative is None:
        return
    if pack_root is None:
        raise GoldenPackError("pack_root is required to validate duplicate reference fixture")
    duplicate_path = _contained_path(pack_root, relative)
    duplicate_data = _load_json(duplicate_path)
    occurrences = duplicate_data.get("ordered_occurrences")
    physical_ids = duplicate_data.get("physical_asset_ids")
    if not isinstance(occurrences, list) or not isinstance(physical_ids, list):
        raise GoldenPackError("Duplicate occurrence regression fixture is malformed")
    if not set(occurrences) <= asset_ids or not set(physical_ids) <= asset_ids:
        raise GoldenPackError("Duplicate regression refers to unknown physical assets")
    if len(physical_ids) != len(set(physical_ids)):
        raise GoldenPackError("Duplicate regression must not duplicate physical asset files")
    if set(physical_ids) != asset_ids:
        raise GoldenPackError("Duplicate regression physical ids must list each pack asset once")
    if len(occurrences) <= len(set(occurrences)):
        raise GoldenPackError(
            "Duplicate regression must contain an intentional repeated occurrence"
        )
    if duplicate_data.get("paid_post_count") != 0:
        raise GoldenPackError("Duplicate regression fixture must record zero paid POSTs")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GoldenPackError(f"Cannot load Golden Pack JSON: {path}") from error
    if not isinstance(value, dict):
        raise GoldenPackError(f"Golden Pack JSON root must be an object: {path}")
    return value


def _contained_path(root: Path, relative: str) -> Path:
    if not relative:
        raise GoldenPackError("Golden Pack path cannot be empty")
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()):
        raise GoldenPackError(f"Golden Pack path escapes its fixture root: {relative}")
    return result
