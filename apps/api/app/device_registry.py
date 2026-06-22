from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from drone_inspection.errors import DomainError

from .models import DeviceModel, DockModel


class DeviceRegistryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list_devices(self, tenant_id: str) -> list[DeviceModel]:
        statement = (
            select(DeviceModel)
            .where(DeviceModel.tenant_id == tenant_id)
            .order_by(DeviceModel.id)
        )
        return list(self.session.scalars(statement))

    def device(self, tenant_id: str, device_id: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.tenant_id == tenant_id,
                DeviceModel.id == device_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def device_by_serial(self, serial_number: str) -> DeviceModel:
        item = self.session.scalar(
            select(DeviceModel).where(
                DeviceModel.serial_number == serial_number
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "设备不存在或不可访问")
        return item

    def list_docks(self, tenant_id: str) -> list[DockModel]:
        statement = (
            select(DockModel)
            .where(DockModel.tenant_id == tenant_id)
            .order_by(DockModel.id)
        )
        return list(self.session.scalars(statement))

    def dock(self, tenant_id: str, dock_id: str) -> DockModel:
        item = self.session.scalar(
            select(DockModel).where(
                DockModel.tenant_id == tenant_id,
                DockModel.id == dock_id,
            )
        )
        if item is None:
            raise DomainError("TENANT_404", "机巢不存在或不可访问")
        return item
