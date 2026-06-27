from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import (
    BridgeAssetModel,
    CoordinateTransformModel,
    RoadAssetModel,
    SlopeAssetModel,
)


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
