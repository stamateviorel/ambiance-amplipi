"""Groups store: CRUD, validation, and groups.conf persistence roundtrip."""
import os
import tempfile
import unittest

from ambiance.config import _load_groups
from ambiance.groups import Groups


class TestGroups(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".conf")
        with os.fdopen(fd, "w") as f:
            f.write("# seed\nBoven|0,1\nBeneden|2,3,4\n")
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))
        self.addCleanup(lambda: os.path.exists(self.path + ".bak") and os.remove(self.path + ".bak"))
        self.g = Groups(self.path, lambda: 6)

    def test_load(self):
        self.assertEqual([g["name"] for g in self.g.entries], ["Boven", "Beneden"])
        self.assertEqual(self.g.get("Boven")["zones"], [0, 1])

    def test_create_persists(self):
        ok, err = self.g.create("Alles", [0, 1, 2, 3, 4, 5])
        self.assertTrue(ok, err)
        reloaded = _load_groups(self.path)                  # survives a restart
        self.assertEqual(reloaded[-1], {"name": "Alles", "zones": [0, 1, 2, 3, 4, 5]})

    def test_create_validation(self):
        self.assertEqual(self.g.create("", [0]), (False, "naam vereist"))
        self.assertEqual(self.g.create("Boven", [0]), (False, "naam bestaat al"))
        self.assertEqual(self.g.create("Leeg", [9, -1, "x"]), (False, "geen geldige zones"))

    def test_invalid_ids_filtered_dupes_dropped(self):
        ok, _ = self.g.create("Mix", [5, 5, 9, -1, 0])
        self.assertTrue(ok)
        self.assertEqual(self.g.get("Mix")["zones"], [5, 0])   # order kept, junk gone

    def test_update_rename_and_members(self):
        ok, err = self.g.update("Boven", name="Verdieping", zones=[1, 2])
        self.assertTrue(ok, err)
        self.assertIsNone(self.g.get("Boven"))
        self.assertEqual(self.g.get("Verdieping")["zones"], [1, 2])
        self.assertEqual(_load_groups(self.path)[0]["name"], "Verdieping")

    def test_update_validation(self):
        self.assertEqual(self.g.update("Nope", name="x"), (False, "groep niet gevonden"))
        self.assertEqual(self.g.update("Boven", name="Beneden"), (False, "naam bestaat al"))
        self.assertEqual(self.g.update("Boven", zones=[42]), (False, "geen geldige zones"))
        self.assertEqual(self.g.get("Boven")["zones"], [0, 1])  # unchanged after refusals

    def test_delete_persists(self):
        ok, _ = self.g.delete("Boven")
        self.assertTrue(ok)
        self.assertEqual(self.g.delete("Boven"), (False, "groep niet gevonden"))
        self.assertEqual([g["name"] for g in _load_groups(self.path)], ["Beneden"])

    def test_name_cleaned(self):
        ok, _ = self.g.create("  Bar|zaal\n ", [0])
        self.assertTrue(ok)
        self.assertIsNotNone(self.g.get("Bar zaal"))            # pipe/newline stripped


if __name__ == "__main__":
    unittest.main()
