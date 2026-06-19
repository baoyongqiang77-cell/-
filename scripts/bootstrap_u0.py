from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.bootstrap import bootstrap_u0
from app.database import build_session_factory, database_url
from app.models import RoleModel, TenantModel, UserModel


def main() -> int:
    factory = build_session_factory(database_url())
    with factory() as session:
        bootstrap_u0(session)
        counts = {
            "tenants": session.scalar(select(func.count(TenantModel.id))),
            "users": session.scalar(select(func.count(UserModel.id))),
            "roles": session.scalar(select(func.count(RoleModel.code))),
        }
    print(counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
