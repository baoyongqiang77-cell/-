import sys
import unittest
from pathlib import Path

from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "src"))

from app.database import build_session_factory
from app.models import Base


class U2MediaIngestPersistenceTests(unittest.TestCase):
    def test_media_file_model_contains_u2_ingest_columns(self):
        table = Base.metadata.tables["media_files"]
        for column in (
            "source_type",
            "original_filename",
            "mime_type",
            "size_bytes",
            "captured_at",
            "failure_reason",
        ):
            self.assertIn(column, table.c)

    def test_media_chunks_model_registers_required_constraints(self):
        table = Base.metadata.tables["media_chunks"]
        constraints = {constraint.name for constraint in table.constraints}
        self.assertIn("fk_media_chunks_tenant_media_file", constraints)
        self.assertIn("uq_media_chunks_tenant_media_file_index", constraints)
        self.assertIn("ck_media_chunks_status", constraints)
        self.assertIn("ck_media_chunks_index_range", constraints)

    def test_metadata_create_all_creates_media_chunks(self):
        session_factory = build_session_factory("sqlite+pysqlite:///:memory:")
        engine = session_factory.kw["bind"]
        try:
            Base.metadata.create_all(engine)
            self.assertIn("media_chunks", set(inspect(engine).get_table_names()))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
