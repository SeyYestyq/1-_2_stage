#!/usr/bin/env python3
"""Проверка структуры выгрузки и связей обработчиков, без запуска платформы 1С."""
import argparse
from collections import Counter
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

FORM = 'http://v8.1c.ru/8.3/xcf/logform'
MD = 'http://v8.1c.ru/8.3/MDClasses'
TYPE_DIR = {'Catalog': 'Catalogs', 'Document': 'Documents', 'CommonModule': 'CommonModules',
            'Enum': 'Enums', 'InformationRegister': 'InformationRegisters', 'StyleItem': 'StyleItems',
            'Role': 'Roles', 'Language': 'Languages', 'Subsystem': 'Subsystems',
            'Constant': 'Constants', 'DataProcessor': 'DataProcessors', 'CommonForm': 'CommonForms'}
NS = {'f': FORM, 'm': MD}


def check(root):
    errors = []
    roots = {}
    uuids = {}
    for path in sorted(root.rglob('*.xml')):
        try:
            tree = ET.parse(path).getroot()
        except ET.ParseError as error:
            errors.append(f'{path}: {error}')
            continue
        roots[path] = tree
        for node in tree.iter():
            uid = node.get('uuid')
            if uid:
                if uid in uuids:
                    errors.append(f'{path}: повтор uuid {uid} из {uuids[uid]}')
                uuids[uid] = path
        if tree.tag != f'{{{FORM}}}Form':
            continue
        ids = [n.get('id') for n in tree.iter() if n.get('id') is not None]
        for uid, count in Counter(ids).items():
            if count > 1:
                errors.append(f'{path}: повтор id {uid}')
        attributes = {n.get('name') for n in tree.findall('f:Attributes/f:Attribute', NS)}
        for data_path in tree.findall('.//f:DataPath', NS):
            if data_path.text and data_path.text.split('.')[0] not in attributes:
                errors.append(f'{path}: нет реквизита для пути {data_path.text}')
        module = path.parent / 'Form/Module.bsl'
        source = module.read_text(encoding='utf-8-sig') if module.exists() else ''
        methods = set(re.findall(r'(?:Процедура|Функция)\s+(\w+)\s*\(', source, re.I))
        for node in tree.iter():
            if node.tag in {f'{{{FORM}}}Event', f'{{{FORM}}}Action'} and node.text:
                if node.text not in methods:
                    errors.append(f'{path}: нет обработчика {node.text}')
        # Оповещения и динамические события не объявляются в XML.
        callbacks = re.findall(r'(?:Новый\s+ОписаниеОповещения\(|УстановитьДействие\("[^"]+",)\s*"([^"]+)"', source)
        for callback in callbacks:
            if callback not in methods:
                errors.append(f'{module}: нет динамического обработчика {callback}')
    config_path = root / 'Configuration.xml'
    config = roots.get(config_path)
    if config is None:
        errors.append(f'{config_path}: нет корректного корня конфигурации')
    else:
        for obj in config.findall('m:Configuration/m:ChildObjects/*', NS):
            kind = obj.tag.split('}')[-1]
            if kind in TYPE_DIR and not (root / TYPE_DIR[kind] / f'{obj.text}.xml').is_file():
                errors.append(f'Configuration.xml: нет {kind}.{obj.text}')
    # Дескриптор формы недостаточен: он должен быть объявлен внутри объекта.
    for directory in ('Catalogs', 'Documents', 'DataProcessors'):
        for metadata_path in (root / directory).glob('*.xml'):
            metadata = roots.get(metadata_path)
            if metadata is None:
                continue
            for name in metadata.findall('.//m:ChildObjects/m:Form', NS):
                descriptor = metadata_path.with_suffix('') / 'Forms' / f'{name.text}.xml'
                body = metadata_path.with_suffix('') / 'Forms' / name.text / 'Ext/Form.xml'
                if not descriptor.exists() or not body.exists():
                    errors.append(f'{metadata_path}: нет объявленной формы {name.text}')
    declared_common_forms = set()
    if config is not None:
        declared_common_forms = {n.text for n in config.findall('m:Configuration/m:ChildObjects/m:CommonForm', NS)}
    modules = {p.parent.parent.name: p.read_text(encoding='utf-8-sig')
               for p in (root / 'CommonModules').glob('*/Ext/Module.bsl')}
    for path in root.rglob('*.bsl'):
        source = path.read_text(encoding='utf-8-sig')
        for form in re.findall(r'ОткрытьФорму\("ОбщаяФорма\.(\w+)"', source):
            if form not in declared_common_forms or not (root / 'CommonForms' / form / 'Ext/Form.xml').exists():
                errors.append(f'{path}: общая форма {form} не подключена')
        for name, text in modules.items():
            exported = set(re.findall(r'(?:Функция|Процедура)\s+(\w+)\([^\n]*\)\s+Экспорт', text))
            for method in re.findall(r'\b' + re.escape(name) + r'\.(\w+)\s*\(', source):
                if method not in exported:
                    errors.append(f'{path}: нет экспортного метода {name}.{method}')
    return errors, len(roots), len(uuids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', type=Path, default=Path(__file__).resolve().parents[1] / 'ДокМаршрут')
    args = parser.parse_args()
    errors, count, uuids = check(args.root)
    for error in errors:
        print(error, file=sys.stderr)
    print(f'XML: {count}; UUID: {uuids}; ошибок структуры: {len(errors)}')
    print('Загрузка в 1С, типы и исполнение BSL этой проверкой не подтверждаются.')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
