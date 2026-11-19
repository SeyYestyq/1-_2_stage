"""Регрессия: генерация метаданных не должна стирать разработанные формы."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CommonFormPreservationTest(unittest.TestCase):
    def test_existing_form_survives_generation_and_out_export(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            shutil.copytree(source, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            relative = Path("CommonForms/МоиСогласования/Ext/Form.xml")
            form = checkout / relative
            authored = form.read_text().replace("</Form>", "<!-- authored form sentinel --></Form>")
            form.write_text(authored)
            for args, destination in [([], checkout), (["--out", str(Path(directory) / "export")], Path(directory) / "export")]:
                subprocess.run([sys.executable, str(checkout / "tools/gen_config.py"), *args],
                               check=True, capture_output=True, text=True)
                self.assertEqual(authored, (destination / relative).read_text())

    def test_missing_form_gets_initial_shell(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            shutil.copytree(source, checkout, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            form = checkout / "CommonForms/МоиСогласования/Ext/Form.xml"
            form.unlink()
            subprocess.run([sys.executable, str(checkout / "tools/gen_config.py")],
                           check=True, capture_output=True, text=True)
            self.assertIn("ПриСозданииНаСервере", form.read_text())


if __name__ == "__main__":
    unittest.main()
