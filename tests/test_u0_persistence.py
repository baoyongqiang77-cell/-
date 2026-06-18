import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.database import build_session_factory, database_url


class DatabaseConfigurationTests(unittest.TestCase):
    def test_build_session_factory_uses_explicit_sqlite_url(self):
        factory = build_session_factory("sqlite+pysqlite:///:memory:")

        with factory() as session:
            self.assertEqual(session.bind.dialect.name, "sqlite")

    def test_database_url_defaults_to_local_sqlite_file(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                database_url(),
                "sqlite+pysqlite:///./var/u0.db",
            )


if __name__ == "__main__":
    unittest.main()
