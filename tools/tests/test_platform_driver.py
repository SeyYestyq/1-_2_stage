"""Проверка драйвера: чужая ИБ не используется, отсутствие результата не считается успехом."""
import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('check_in_1c', Path(__file__).resolve().parents[1] / 'check_in_1c.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


class PlatformDriverTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.result = self.path / 'check.result'

    def test_bom_zero_is_success(self):
        self.result.write_text('0\n', encoding='utf-8-sig')
        self.assertTrue(driver.result_of_step(0, self.result)[0])

    def test_native_error_with_zero_process_exit_is_failure(self):
        self.result.write_text('101', encoding='utf-8-sig')
        self.assertFalse(driver.result_of_step(0, self.result)[0])

    def test_missing_result_is_failure(self):
        self.assertFalse(driver.result_of_step(0, self.result)[0])

    def test_process_failure_is_not_overridden_by_dump_result(self):
        self.result.write_text('0')
        self.assertFalse(driver.result_of_step(1, self.result)[0])

    def test_existing_base_directory_is_rejected(self):
        sentinel = self.path / '1Cv8.1CD'
        sentinel.write_bytes(b'untouched')
        with self.assertRaises(ValueError):
            driver.prepare_workspace(self.path)
        self.assertEqual(b'untouched', sentinel.read_bytes())

    def test_prepare_only_does_not_launch_platform(self):
        workspace = self.path / 'prepared'
        with patch.object(driver, 'execute', side_effect=AssertionError('must not launch')):
            self.assertEqual(0, driver.main(['--prepare-only', '--workspace', str(workspace)]))
        report = json.loads((workspace / 'report.json').read_text())
        self.assertEqual('prepared_not_run', report['status'])
        self.assertTrue(all(s['status'] == 'not_run' for s in report['steps']))
        self.assertFalse((workspace / 'base').exists())

    def test_native_load_error_stops_following_steps_and_records_report(self):
        workspace = self.path / 'run'
        called = []

        def native_results(command, stdout_file, timeout):
            name = stdout_file.name.split('.')[0]
            called.append(name)
            result = Path(command[command.index('/DumpResult') + 1])
            result.write_text('101' if name == 'load' else '0', encoding='utf-8-sig')
            return 0

        with patch.object(driver, 'execute', side_effect=native_results):
            code = driver.main(['--platform', sys.executable, '--workspace', str(workspace)])
        self.assertEqual(1, code)
        self.assertEqual(['create', 'load'], called)
        report = json.loads((workspace / 'report.json').read_text())
        self.assertEqual('failed', report['status'])
        self.assertEqual(101, report['steps'][1]['native_code'])
        self.assertEqual('not_run', report['steps'][2]['status'])


if __name__ == '__main__':
    unittest.main()
