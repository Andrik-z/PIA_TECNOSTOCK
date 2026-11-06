import os
import unittest
from unittest import mock

from src.config import Settings


class TestConfig(unittest.TestCase):
    def test_env(self):
        with mock.patch.dict(os.environ, {"LIMITE_ARTICULOS": "7", "SEED_DATA": "false", "DATABASE_URL": "sqlite:///x.db"}):
            s = Settings.desde_entorno()
        self.assertEqual((s.limite_articulos, s.seed_data, s.database_url), (7, False, "sqlite:///x.db"))
