from __future__ import annotations

from hashlib import sha256
from json import dumps
from re import fullmatch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import (
    BridgeAssetModel,
    RoadAssetModel,
    RouteModel,
    RouteVersionModel,
    SlopeAssetModel,
    utc_now,
)
from .repositories import RequestMeta, U0Repository


ROUTE_FORMATS = {"DJI_WPML", "KML", "GEOJSON", "PENDING_CONFIRMATION"}
ASSET_TYPES = {"road", "bridge", "slope"}


class RouteRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_routes(self, tenant_id: str) -> list[RouteModel]:
        statement = (
            select(RouteModel)
            .where(RouteModel.tenant_id == tenant_id)
            .order_by(RouteModel.id)
        )
        return list(self.session.scalars(statement))

    def route(self, tenant_id: str, route_id: str) -> RouteModel:
        item = self.session.scalar(
            select(RouteModel).where(
                RouteModel.tenant_id == tenant_id,
                RouteModel.id == route_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "Route does not exist or is not accessible")
        return item

    def list_versions(self, tenant_id: str, route_id: str) -> list[RouteVersionModel]:
        self.route(tenant_id, route_id)
        statement = (
            select(RouteVersionModel)
            .where(
                RouteVersionModel.tenant_id == tenant_id,
                RouteVersionModel.route_id == route_id,
            )
            .order_by(RouteVersionModel.version, RouteVersionModel.id)
        )
        return list(self.session.scalars(statement))

    def version(
        self,
        tenant_id: str,
        route_id: str,
        version_id: str,
    ) -> RouteVersionModel:
        self.route(tenant_id, route_id)
        item = self.session.scalar(
            select(RouteVersionModel).where(
                RouteVersionModel.tenant_id == tenant_id,
                RouteVersionModel.route_id == route_id,
                RouteVersionModel.id == version_id,
            )
        )
        if item is None:
            raise DomainError(
                "TENANT_404",
                "Route version does not exist or is not accessible",
            )
        return item


def route_payload(item: RouteModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "route_code": item.route_code,
        "name": item.name,
        "description": item.description,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def route_version_payload(item: RouteVersionModel) -> dict:
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "route_id": item.route_id,
        "version": item.version,
        "route_file_uri": item.route_file_uri,
        "route_format": item.route_format,
        "checksum": item.checksum,
        "path_geom_json": item.path_geom_json,
        "asset_bindings": item.asset_bindings,
        "validation_report": item.validation_report,
        "dji_route_id": item.dji_route_id,
        "uploaded_at": _iso(item.uploaded_at),
        "created_at": _iso(item.created_at),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


class RouteManagementService:
    ROUTE_UPDATE_FIELDS = {"route_code", "name", "description"}

    def __init__(self, session: Session):
        self.session = session
        self.routes = RouteRepository(session)
        self.u0 = U0Repository(session)

    def create_route(
        self,
        actor_id: str,
        tenant_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        self.u0.tenant_context(tenant_id)
        normalized = self._normalize_route(values)
        fingerprint = self._fingerprint(
            {"action": "create_route", "tenant_id": tenant_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_route(tenant_id, normalized["route_code"])
            item = RouteModel(
                id=f"route_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(tenant_id, actor_id, "route_created", "route", item.id, request_meta)
            return route_payload(item)

        return self.u0.run_idempotent(
            tenant_id, "POST", "route-create", idempotency_key, fingerprint, operation
        )

    def update_route(
        self,
        actor_id: str,
        tenant_id: str,
        route_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        item = self.routes.route(tenant_id, route_id)
        normalized = self._normalize_route(
            {**route_payload(item), **self._allowed(values, self.ROUTE_UPDATE_FIELDS)}
        )
        fingerprint = self._fingerprint(
            {"action": "update_route", "tenant_id": tenant_id, "id": route_id, **normalized}
        )

        def operation() -> dict:
            self._reject_duplicate_route(
                tenant_id, normalized["route_code"], exclude_id=route_id
            )
            self._apply(item, normalized)
            self._audit(tenant_id, actor_id, "route_updated", "route", item.id, request_meta)
            return route_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "PATCH",
            f"route-update:{route_id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def create_route_version(
        self,
        actor_id: str,
        tenant_id: str,
        route_id: str,
        values: dict,
        idempotency_key: str | None,
        request_meta: RequestMeta,
    ) -> dict:
        route = self.routes.route(tenant_id, route_id)
        normalized = self._normalize_version(tenant_id, values)
        fingerprint = self._fingerprint(
            {
                "action": "create_route_version",
                "tenant_id": tenant_id,
                "route_id": route.id,
                **normalized,
            }
        )

        def operation() -> dict:
            self._reject_duplicate_version(tenant_id, route.id, normalized["version"])
            item = RouteVersionModel(
                id=f"rv_{uuid4().hex[:12]}",
                tenant_id=tenant_id,
                route_id=route.id,
                **normalized,
            )
            self.session.add(item)
            self.session.flush()
            self._audit(
                tenant_id,
                actor_id,
                "route_version_created",
                "route_version",
                item.id,
                request_meta,
            )
            return route_version_payload(item)

        return self.u0.run_idempotent(
            tenant_id,
            "POST",
            f"route-version-create:{route.id}",
            idempotency_key,
            fingerprint,
            operation,
        )

    def _normalize_route(self, values: dict) -> dict:
        normalized = {
            "route_code": values.get("route_code"),
            "name": values.get("name"),
            "description": values.get("description"),
        }
        _require_non_empty(normalized, ("route_code", "name"))
        return normalized

    def _normalize_version(self, tenant_id: str, values: dict) -> dict:
        normalized = {
            "version": values.get("version"),
            "route_file_uri": values.get("route_file_uri"),
            "route_format": values.get("route_format"),
            "checksum": values.get("checksum"),
            "path_geom_json": values.get("path_geom_json"),
            "asset_bindings": values.get("asset_bindings") or [],
            "validation_report": values.get("validation_report") or {},
            "dji_route_id": values.get("dji_route_id"),
            "uploaded_at": values.get("uploaded_at"),
        }
        _require_non_empty(
            normalized,
            ("version", "route_file_uri", "route_format", "checksum"),
        )
        if normalized["route_format"] not in ROUTE_FORMATS:
            raise DomainError(
                "MISSION_422",
                "Route format is not supported or confirmed",
                {"field": "route_format", "allowed": sorted(ROUTE_FORMATS)},
            )
        if not fullmatch(r"sha256:[0-9a-fA-F]{64}", normalized["checksum"]):
            raise DomainError("MISSION_422", "Route checksum is invalid", {"field": "checksum"})
        if (
            not isinstance(normalized["path_geom_json"], dict)
            or normalized["path_geom_json"].get("type") != "LineString"
        ):
            raise DomainError("GIS_422", "Route path geometry is invalid", {"field": "path_geom_json"})
        if not isinstance(normalized["validation_report"], dict):
            raise DomainError(
                "MISSION_422",
                "Route validation report must be an object",
                {"field": "validation_report"},
            )
        normalized["asset_bindings"] = self._normalize_asset_bindings(
            tenant_id, normalized["asset_bindings"]
        )
        return normalized

    def _normalize_asset_bindings(self, tenant_id: str, bindings: list) -> list[dict]:
        if not isinstance(bindings, list):
            raise DomainError(
                "GIS_422",
                "Route asset bindings must be a list",
                {"field": "asset_bindings"},
            )
        normalized = []
        for index, binding in enumerate(bindings):
            if not isinstance(binding, dict):
                raise DomainError(
                    "GIS_422",
                    "Route asset binding is invalid",
                    {"field": f"asset_bindings[{index}]"},
                )
            asset_type = binding.get("asset_type")
            asset_id = binding.get("asset_id")
            if asset_type not in ASSET_TYPES or not str(asset_id or "").strip():
                raise DomainError(
                    "GIS_422",
                    "Route asset binding is invalid",
                    {"field": f"asset_bindings[{index}]"},
                )
            self._require_asset(tenant_id, asset_type, asset_id)
            normalized.append({"asset_type": asset_type, "asset_id": asset_id})
        return normalized

    def _require_asset(self, tenant_id: str, asset_type: str, asset_id: str) -> None:
        model = {
            "road": RoadAssetModel,
            "bridge": BridgeAssetModel,
            "slope": SlopeAssetModel,
        }[asset_type]
        found = self.session.scalar(
            select(model.id).where(model.tenant_id == tenant_id, model.id == asset_id)
        )
        if found is None:
            raise DomainError(
                "TENANT_404",
                "Route asset binding does not exist or is not accessible",
            )

    def _reject_duplicate_route(
        self,
        tenant_id: str,
        route_code: str,
        exclude_id: str | None = None,
    ) -> None:
        statement = select(RouteModel.id).where(
            RouteModel.tenant_id == tenant_id,
            RouteModel.route_code == route_code,
        )
        self._reject_duplicate(statement, exclude_id, "route code already exists")

    def _reject_duplicate_version(
        self,
        tenant_id: str,
        route_id: str,
        version: str,
    ) -> None:
        existing = self.session.scalar(
            select(RouteVersionModel.id).where(
                RouteVersionModel.tenant_id == tenant_id,
                RouteVersionModel.route_id == route_id,
                RouteVersionModel.version == version,
            )
        )
        if existing is not None:
            raise DomainError("MISSION_422", "route version already exists")

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
                "Required route field is empty",
                {"field": field},
            )
