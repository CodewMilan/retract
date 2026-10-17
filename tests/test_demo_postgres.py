"""Explicit opt-in real PostgreSQL tests, isolated to a UUID schema."""

import os
import unittest
from uuid import uuid4

from retract.demo import PostgresProfiles


@unittest.skipUnless(os.getenv("RUN_DEMO_POSTGRES_TESTS") == "1", "Requires .[demo] and real PostgreSQL; set RUN_DEMO_POSTGRES_TESTS=1")
class PostgresDemoTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row

        url = os.getenv("DEMO_DATABASE_URL", "postgresql://retract_demo:local_demo_only@127.0.0.1:54330/retract_demo")
        schema = "retract_test_" + uuid4().hex
        with psycopg.connect(url, connect_timeout=3) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        def cleanup():
            with psycopg.connect(url, connect_timeout=3) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        self.addCleanup(cleanup)
        self.store = PostgresProfiles(url)
        self.store.connect = lambda: psycopg.connect(url, connect_timeout=3, row_factory=dict_row, options=f"-c search_path={schema}")
        self.store.seed()

    def test_profile_edits_persist_and_repeated_seed_does_not_reset(self):
        self.store.health()
        self.store.update("alice", "Alice Updated")
        self.store.seed()
        self.assertEqual(self.store.get("alice")["display_name"], "Alice Updated")
        self.assertEqual(self.store.get("bob")["display_name"], "Bob Example")

    def test_profile_values_are_parameterized(self):
        value = "O'Connor; DROP TABLE retract_demo_profiles; --"
        self.store.update("alice", value)
        self.assertEqual(self.store.get("alice")["display_name"], value)
        self.assertEqual(self.store.get("bob")["id"], "bob")
