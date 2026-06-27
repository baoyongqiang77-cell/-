from __future__ import annotations

from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import (
    BridgeAssetModel,
    CoordinateTransformModel,
    RoadAssetModel,
    SlopeAssetModel,
    utc_now,
)
from .repositories import RequestMeta, U0Repository


ASSET_CRS_VALUES = {"WGS84", "GCJ02", "CGCS2000", "PENDING_CONFIRMATION"}
GEOMETRY_TYPES = {"Point", "LineString", "Polygon", "MultiLineString", "MultiPolygon"}
ROAD_DIRECTIONS = {"UP", "DOWN", "BIDIRECTIONAL", "RAMP", "UNKNOWN"}
SLOPE_SIDES = {"LEFT", "RIGHT", "BOTH", "UNKNOWN"}
TRANSFORM_METHODS = {"CONFIG_ONLY", "AFFINE", "HELMERT", "MANUAL_REVIEW"}
TRANSFORM_STATUSES = {"ACTIVE", "DEPRECATED", "PENDING_CONFIRMATION"}


class GisAssetRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_road_assets(self, tenant_id: str) -> list[RoadAssetModel]:
        statement = (
            select(RoadAssetModel)
            .where(RoadAssetModel.tenant_id == tenant_id)
            .order_by(RoadAssetModel.id)
        )
        return list(self.session.scalars(statement))

    def road_asset(self, tenant_id: str, asset_id: str) -> RoadAssetModel:
        item = self.session.scalar(
            select(RoadAssetModel).where(
                RoadAssetModel.tenant_id == tenant_id,
                RoadAssetModel.id == asset_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Road asset does not exist or is not accessible",
            )
        return item

    def list_bridge_assets(self, tenant_id: str) -> list[BridgeAssetModel]:
        statement = (
            select(BridgeAssetModel)
            .where(BridgeAssetModel.tenant_id == tenant_id)
            .order_by(BridgeAssetModel.id)
        )
        return list(self.session.scalars(statement))

    def bridge_asset(self, tenant_id: str, asset_id: str) -> BridgeAssetModel:
        item = self.session.scalar(
            select(BridgeAssetModel).where(
                BridgeAssetModel.tenant_id == tenant_id,
                BridgeAssetModel.id == asset_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Bridge asset does not exist or is not accessible",
            )
        return item

    def list_slope_assets(self, tenant_id: str) -> list[SlopeAssetModel]:
        statement = (
            select(SlopeAssetModel)
            .where(SlopeAssetModel.tenant_id == tenant_id)
            .order_by(SlopeAssetModel.id)
        )
        return list(self.session.scalars(statement))

    def slope_asset(self, tenant_id: str, asset_id: str) -> SlopeAssetModel:
        item = self.session.scalar(
            select(SlopeAssetModel).where(
                SlopeAssetModel.tenant_id == tenant_id,
                SlopeAssetModel.id == asset_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Slope asset does not exist or is not accessible",
            )
        return item

    def list_coordinate_transforms(
        self,
        tenant_id: str,
    ) -> list[CoordinateTransformModel]:
        statement = (
            select(CoordinateTransformModel)
            .where(CoordinateTransformModel.tenant_id == tenant_id)
            .order_by(CoordinateTransformModel.id)
        )
        return list(self.session.scalars(statement))

    def coordinate_transform(
        self,
        tenant_id: str,
        transform_id: str,
    ) -> CoordinateTransformModel:
        item = self.session.scalar(
            select(CoordinateTransformModel).where(
                CoordinateTransformModel.tenant_id == tenant_id,
                CoordinateTransformModel.id == transform_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Coordinate transform does not exist or is not accessible",
            )
        return item


def road_asset_payload(item: RoadAssetModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "route_code": item.route_code,
        "road_name": item.road_name,
        "direction": item.direction,
        "start_stake": item.start_stake,
        "end_stake": item.end_stake,
        "geom_json": item.geom_json,
        "source": item.source,
        "crs": item.crs,
        "data_version": item.data_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def bridge_asset_payload(item: BridgeAssetModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "bridge_code": item.bridge_code,
        "bridge_name": item.bridge_name,
        "route_code": item.route_code,
        "stake_no": item.stake_no,
        "geom_json": item.geom_json,
        "structure_parts": item.structure_parts,
        "source": item.source,
        "crs": item.crs,
        "data_version": item.data_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def slope_asset_payload(item: SlopeAssetModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "slope_code": item.slope_code,
        "route_code": item.route_code,
        "start_stake": item.start_stake,
        "end_stake": item.end_stake,
        "side": item.side,
        "geom_json": item.geom_json,
        "source": item.source,
        "crs": item.crs,
        "data_version": item.data_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def coordinate_transform_payload(item: CoordinateTransformModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "source_crs": item.source_crs,
        "target_crs": item.target_crs,
        "method": item.method,
        "params_json": item.params_json,
        "version": item.version,
        "status": item.status,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class GisAssetService:
    ROAD_UPDATE_FIELDS = {
        "route_code",
        "road_name",
        "direction",
        "start_stake",
        "end_stake",
        "geom_json",
        "source",
        "crs",
        "data_version",
    }
    BRIDGE_UPDATE_FIELDS = {
        "bridge_code",
        "bridge_name",
        "route_code",
        "stake_no",
        "geom_json",
        "structure_parts",
        "source",
        "crs",
        "data_version",
    }
    SLOPE_UPDATE_FIELDS = {
        "slope_code",
        "route_code",
        "start_stake",
        "end_stake",
        "side",
        "geom_json",
        "source",
        "crs",
        "data_version",
    }
    TRANSFORM_UPDATE_FIELDS = {
        "source_crs",
        "target_crs",
        "method",
        "params_json",
        "version",
        "status",
    }

    def __init__(self, session: Session):
        self.session = session
        self.assets = GisAssetRepository(session)
        self.u0 = U0Repository(session)

    def create_road_asset(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_road(values)
        fingerprint = self._fingerprint(
            {"action": "create_road_asset", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_road(tenant_id, normalized)
            item = RoadAssetModel(
                id=f"road_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(
                tenant_id, actor_id, "road_asset_created", "road_asset", item.id, request_meta
            )
            return road_asset_payload(item)

        self.u0.tenant_context(tenant_id)
        return self.u0.run_idempotent(
            tenant_id, "POST", "gis-road-create", idempotency_key, fingerprint, operation
        )

    def update_road_asset(
        self,
        actor_id: str,
        tenant_id: str,
        asset_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.assets.road_asset(tenant_id, asset_id)
        normalized = self._normalize_road(
            {**road_asset_payload(item), **self._allowed(values, self.ROAD_UPDATE_FIELDS)}
        )
        fingerprint = self._fingerprint(
            {"action": "update_road_asset", "tenant_id": tenant_id, "id": asset_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_road(tenant_id, normalized, exclude_id=asset_id)
            self._apply(item, normalized)
            self._audit(
                tenant_id, actor_id, "road_asset_updated", "road_asset", item.id, request_meta
            )
            return road_asset_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"gis-road-update:{asset_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def create_bridge_asset(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_bridge(values)
        fingerprint = self._fingerprint(
            {"action": "create_bridge_asset", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_bridge(tenant_id, normalized["bridge_code"])
            item = BridgeAssetModel(
                id=f"bridge_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(
                tenant_id,
                actor_id,
                "bridge_asset_created",
                "bridge_asset",
                item.id,
                request_meta,
            )
            return bridge_asset_payload(item)

        self.u0.tenant_context(tenant_id)
        return self.u0.run_idempotent(
            tenant_id, "POST", "gis-bridge-create", idempotency_key, fingerprint, operation
        )

    def update_bridge_asset(
        self,
        actor_id: str,
        tenant_id: str,
        asset_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.assets.bridge_asset(tenant_id, asset_id)
        normalized = self._normalize_bridge(
            {**bridge_asset_payload(item), **self._allowed(values, self.BRIDGE_UPDATE_FIELDS)}
        )
        fingerprint = self._fingerprint(
            {
                "action": "update_bridge_asset",
                "tenant_id": tenant_id,
                "id": asset_id,
                **normalized,
            }
        )

        def operation() -> dict:
            self._reject_duplicate_bridge(
                tenant_id, normalized["bridge_code"], exclude_id=asset_id
            )
            self._apply(item, normalized)
            self._audit(
                tenant_id,
                actor_id,
                "bridge_asset_updated",
                "bridge_asset",
                item.id,
                request_meta,
            )
            return bridge_asset_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"gis-bridge-update:{asset_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def create_slope_asset(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_slope(values)
        fingerprint = self._fingerprint(
            {"action": "create_slope_asset", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_slope(tenant_id, normalized["slope_code"])
            item = SlopeAssetModel(
                id=f"slope_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(
                tenant_id,
                actor_id,
                "slope_asset_created",
                "slope_asset",
                item.id,
                request_meta,
            )
            return slope_asset_payload(item)

        self.u0.tenant_context(tenant_id)
        return self.u0.run_idempotent(
            tenant_id, "POST", "gis-slope-create", idempotency_key, fingerprint, operation
        )

    def update_slope_asset(
        self,
        actor_id: str,
        tenant_id: str,
        asset_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.assets.slope_asset(tenant_id, asset_id)
        normalized = self._normalize_slope(
            {**slope_asset_payload(item), **self._allowed(values, self.SLOPE_UPDATE_FIELDS)}
        )
        fingerprint = self._fingerprint(
            {"action": "update_slope_asset", "tenant_id": tenant_id, "id": asset_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_slope(
                tenant_id, normalized["slope_code"], exclude_id=asset_id
            )
            self._apply(item, normalized)
            self._audit(
                tenant_id, actor_id, "slope_asset_updated", "slope_asset", item.id, request_meta
            )
            return slope_asset_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"gis-slope-update:{asset_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def create_coordinate_transform(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        normalized = self._normalize_transform(values)
        fingerprint = self._fingerprint(
            {"action": "create_coordinate_transform", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_transform(tenant_id, normalized)
            item = CoordinateTransformModel(
                id=f"ctr_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(
                tenant_id,
                actor_id,
                "coordinate_transform_created",
                "coordinate_transform",
                item.id,
                request_meta,
            )
            return coordinate_transform_payload(item)

        self.u0.tenant_context(tenant_id)
        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            "gis-coordinate-transform-create",
            idempotency_key,
            fingerprint,
            operation,
        )

    def update_coordinate_transform(
        self,
        actor_id: str,
        tenant_id: str,
        transform_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.assets.coordinate_transform(tenant_id, transform_id)
        normalized = self._normalize_transform(
            {
                **coordinate_transform_payload(item),
                **self._allowed(values, self.TRANSFORM_UPDATE_FIELDS),
            }
        )
        fingerprint = self._fingerprint(
            {
                "action": "update_coordinate_transform",
                "tenant_id": tenant_id,
                "id": transform_id,
                **normalized,
            }
        )

        def operation() -> dict:
            self._reject_duplicate_transform(tenant_id, normalized, exclude_id=transform_id)
            self._apply(item, normalized)
            self._audit(
                tenant_id,
                actor_id,
                "coordinate_transform_updated",
                "coordinate_transform",
                item.id,
                request_meta,
            )
            return coordinate_transform_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"gis-coordinate-transform-update:{transform_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _normalize_road(self, values: dict) -> dict:
        normalized = {
            "route_code": values.get("route_code"),
            "road_name": values.get("road_name"),
            "direction": values.get("direction"),
            "start_stake": values.get("start_stake"),
            "end_stake": values.get("end_stake"),
            "geom_json": values.get("geom_json"),
            "source": values.get("source") or "MANUAL_IMPORT",
            "crs": values.get("crs") or "PENDING_CONFIRMATION",
            "data_version": values.get("data_version"),
        }
        _require_non_empty(normalized, ("route_code", "road_name", "source"))
        _require_choice(normalized["direction"], ROAD_DIRECTIONS, "direction")
        _validate_stake_range(normalized["start_stake"], normalized["end_stake"])
        _validate_geom(normalized["geom_json"])
        _validate_crs(normalized["crs"])
        return normalized

    def _normalize_bridge(self, values: dict) -> dict:
        normalized = {
            "bridge_code": values.get("bridge_code"),
            "bridge_name": values.get("bridge_name"),
            "route_code": values.get("route_code"),
            "stake_no": values.get("stake_no"),
            "geom_json": values.get("geom_json"),
            "structure_parts": values.get("structure_parts") or [],
            "source": values.get("source") or "MANUAL_IMPORT",
            "crs": values.get("crs") or "PENDING_CONFIRMATION",
            "data_version": values.get("data_version"),
        }
        _require_non_empty(
            normalized,
            ("bridge_code", "bridge_name", "route_code", "source"),
        )
        if not isinstance(normalized["stake_no"], int) or normalized["stake_no"] < 0:
            raise DomainError("GIS_422", "GIS stake value is invalid", {"field": "stake_no"})
        _validate_geom(normalized["geom_json"])
        _validate_crs(normalized["crs"])
        if not isinstance(normalized["structure_parts"], list):
            raise DomainError(
                "MISSION_422",
                "Bridge structure parts must be a list",
                {"field": "structure_parts"},
            )
        return normalized

    def _normalize_slope(self, values: dict) -> dict:
        normalized = {
            "slope_code": values.get("slope_code"),
            "route_code": values.get("route_code"),
            "start_stake": values.get("start_stake"),
            "end_stake": values.get("end_stake"),
            "side": values.get("side"),
            "geom_json": values.get("geom_json"),
            "source": values.get("source") or "MANUAL_IMPORT",
            "crs": values.get("crs") or "PENDING_CONFIRMATION",
            "data_version": values.get("data_version"),
        }
        _require_non_empty(normalized, ("slope_code", "route_code", "source"))
        _require_choice(normalized["side"], SLOPE_SIDES, "side")
        _validate_stake_range(normalized["start_stake"], normalized["end_stake"])
        _validate_geom(normalized["geom_json"])
        _validate_crs(normalized["crs"])
        return normalized

    def _normalize_transform(self, values: dict) -> dict:
        normalized = {
            "source_crs": values.get("source_crs"),
            "target_crs": values.get("target_crs"),
            "method": values.get("method"),
            "params_json": values.get("params_json") or {},
            "version": values.get("version"),
            "status": values.get("status"),
        }
        _require_non_empty(normalized, ("source_crs", "target_crs", "version"))
        _validate_crs(normalized["source_crs"], "source_crs")
        _validate_crs(normalized["target_crs"], "target_crs")
        if normalized["source_crs"] == normalized["target_crs"]:
            raise DomainError(
                "GIS_422",
                "Coordinate transform CRS pair is invalid",
                {"field": "target_crs"},
            )
        _require_choice(normalized["method"], TRANSFORM_METHODS, "method")
        _require_choice(normalized["status"], TRANSFORM_STATUSES, "status")
        if not isinstance(normalized["params_json"], dict):
            raise DomainError(
                "MISSION_422",
                "Coordinate transform params must be an object",
                {"field": "params_json"},
            )
        return normalized

    def _reject_duplicate_road(
        self,
        tenant_id: str,
        values: dict,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(RoadAssetModel.id).where(
            RoadAssetModel.tenant_id == tenant_id,
            RoadAssetModel.route_code == values["route_code"],
            RoadAssetModel.direction == values["direction"],
            RoadAssetModel.start_stake == values["start_stake"],
            RoadAssetModel.end_stake == values["end_stake"],
        )
        self._reject_duplicate(statement, exclude_id, "road asset range already exists")

    def _reject_duplicate_bridge(
        self,
        tenant_id: str,
        bridge_code: str,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(BridgeAssetModel.id).where(
            BridgeAssetModel.tenant_id == tenant_id,
            BridgeAssetModel.bridge_code == bridge_code,
        )
        self._reject_duplicate(statement, exclude_id, "bridge asset code already exists")

    def _reject_duplicate_slope(
        self,
        tenant_id: str,
        slope_code: str,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(SlopeAssetModel.id).where(
            SlopeAssetModel.tenant_id == tenant_id,
            SlopeAssetModel.slope_code == slope_code,
        )
        self._reject_duplicate(statement, exclude_id, "slope asset code already exists")

    def _reject_duplicate_transform(
        self,
        tenant_id: str,
        values: dict,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(CoordinateTransformModel.id).where(
            CoordinateTransformModel.tenant_id == tenant_id,
            CoordinateTransformModel.source_crs == values["source_crs"],
            CoordinateTransformModel.target_crs == values["target_crs"],
            CoordinateTransformModel.version == values["version"],
        )
        self._reject_duplicate(
            statement,
            exclude_id,
            "coordinate transform version already exists",
        )

    def _reject_duplicate(self, statement, exclude_id: str | None, message: str) -> None:
        existing = self.session.scalar(statement)
        if existing is not None and existing != exclude_id:
            raise DomainError("MISSION_422", message)

    def _audit(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        request_meta: RequestMeta,
    ) -> None:
        self.u0.audit(
            tenant_id=tenant_id,
            actor=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_meta=request_meta,
        )

    @staticmethod
    def _allowed(values: dict, fields: set[str]) -> dict:
        return {key: value for key, value in values.items() if key in fields}

    @staticmethod
    def _apply(item, values: dict) -> None:
        for key, value in values.items():
            setattr(item, key, value)
        item.updated_at = utc_now()

    @staticmethod
    def _fingerprint(payload: dict) -> str:
        encoded = dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return sha256(encoded).hexdigest()


def _require_non_empty(values: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if not str(values.get(field, "")).strip():
            raise DomainError(
                "MISSION_422",
                "Required GIS asset field is empty",
                {"field": field},
            )


def _require_choice(value: str, allowed: set[str], field: str) -> None:
    if value not in allowed:
        raise DomainError(
            "MISSION_422",
            "GIS asset field value is not supported",
            {"field": field, "allowed": sorted(allowed)},
        )


def _validate_stake_range(start_stake: int, end_stake: int) -> None:
    if (
        not isinstance(start_stake, int)
        or not isinstance(end_stake, int)
        or end_stake < start_stake
    ):
        raise DomainError(
            "GIS_422",
            "GIS stake range is invalid",
            {"field": "start_stake/end_stake"},
        )


def _validate_geom(value: dict) -> None:
    if not isinstance(value, dict) or value.get("type") not in GEOMETRY_TYPES:
        raise DomainError("GIS_422", "GIS geometry is invalid", {"field": "geom_json"})


def _validate_crs(value: str, field: str = "crs") -> None:
    if value not in ASSET_CRS_VALUES:
        raise DomainError(
            "GIS_422",
            "CRS is not supported or confirmed",
            {"field": field},
        )
