"""Проверяем, что проверка выгрузки обнаруживает реальные разрывы интеграции."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('check_dump', ROOT / 'tools/check_dump.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DumpIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dump = Path(self.temp.name) / 'ДокМаршрут'
        shutil.copytree(ROOT / 'ДокМаршрут', self.dump)

    def errors(self):
        return '\n'.join(checker.check(self.dump)[0])

    def test_current_dump_is_connected(self):
        self.assertEqual('', self.errors())

    def test_missing_xml_handler_is_detected(self):
        path = self.dump / 'Documents/ДокументСЭД/Forms/ФормаДокумента/Ext/Form.xml'
        path.write_text(path.read_text().replace('>КатегорияПриИзменении<', '>НетТакогоОбработчика<'))
        self.assertIn('нет обработчика НетТакогоОбработчика', self.errors())

    def test_missing_async_callback_is_detected(self):
        path = self.dump / 'Documents/ДокументСЭД/Forms/ФормаДокумента/Ext/Form/Module.bsl'
        path.write_text(path.read_text(encoding='utf-8-sig').replace(
            'Процедура ПослеСменыВида(', 'Процедура ПереименованныйОбработчик('), encoding='utf-8-sig')
        self.assertIn('нет динамического обработчика ПослеСменыВида', self.errors())

    def test_duplicate_attribute_id_is_detected(self):
        path = self.dump / 'Documents/ДокументСЭД/Forms/ФормаДокумента/Ext/Form.xml'
        path.write_text(path.read_text().replace('<Attributes>', '<Attributes><Attribute name="Повтор" id="1"/>'))
        self.assertIn('повтор id 1', self.errors())

    def test_removed_engine_export_is_detected(self):
        path = self.dump / 'CommonModules/Согласование/Ext/Module.bsl'
        path.write_text(path.read_text(encoding='utf-8-sig').replace(
            'Функция ОтправитьНаСогласование(', 'Функция ПереименованнаяОтправка('), encoding='utf-8-sig')
        self.assertIn('нет экспортного метода Согласование.ОтправитьНаСогласование', self.errors())

    def test_missing_declared_metadata_is_detected(self):
        (self.dump / 'CommonModules/Согласование.xml').unlink()
        self.assertIn('нет CommonModule.Согласование', self.errors())

    def test_missing_wizard_descriptor_is_detected(self):
        (self.dump / 'Catalogs/ВидыДокументов/Forms/ФормаМастер.xml').unlink()
        self.assertIn('нет объявленной формы ФормаМастер', self.errors())

    def test_missing_home_form_registration_is_detected(self):
        path = self.dump / 'Configuration.xml'
        path.write_text(path.read_text().replace('<CommonForm>НачальнаяСтраница</CommonForm>', ''))
        self.assertIn('общая форма НачальнаяСтраница не подключена', self.errors())

    def test_unknown_home_attribute_is_detected(self):
        path = self.dump / 'CommonForms/НачальнаяСтраница/Ext/Form.xml'
        path.write_text(path.read_text().replace('<DataPath>Черновики</DataPath>', '<DataPath>НеизвестныйСчетчик</DataPath>'))
        self.assertIn('нет реквизита для пути НеизвестныйСчетчик', self.errors())

    def test_sync_mail_confirmation_regression_is_detected(self):
        path = self.dump / 'Documents/ДокументСЭД/Forms/ФормаДокумента/Ext/Form/Module.bsl'
        path.write_text(path.read_text(encoding='utf-8-sig') + '\n// regression fixture\nОтвет = Вопрос("Отправить?", РежимДиалогаВопрос.ДаНет);', encoding='utf-8-sig')
        self.assertIn('несовместимый с веб-клиентом вызов Вопрос', self.errors())


if __name__ == '__main__':
    unittest.main()
