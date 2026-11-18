#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверки выгрузки конфигурации без платформы 1С (то, что можно проверить руками на Mac).

Что проверяется:
1. каждый *.xml — well-formed (через xmllint);
2. все uuid в выгрузке уникальны;
3. все перекрёстные ссылки по именам разрешаются: cfg:CatalogRef.X, EnumRef.X, DocumentRef.X,
   ChartOfCharacteristicTypesRef.X, а также <Form>X</Form> у объекта -> существует файл формы;
4. состав корня Configuration.xml совпадает с набором объектов на диске (объект на диске, но
   не в корне — ошибка; в корне, но без файла — ошибка);
5. у каждого объекта заполнены Name/Synonym, у каждой ТЧ есть InternalInfo с GeneratedType.

Что НЕ проверяется: загрузится ли выгрузка в платформу. Платформы 1С на машине нет.
Запуск: python3 tools/check_config.py
"""
import glob
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = {"md": "http://v8.1c.ru/8.3/MDClasses"}

KIND_DIRS = {
    "Enum": "Enums",
    "Catalog": "Catalogs",
    "Document": "Documents",
    "InformationRegister": "InformationRegisters",
    "ChartOfCharacteristicTypes": "ChartsOfCharacteristicTypes",
    "Constant": "Constants",
    "CommonModule": "CommonModules",
    "Role": "Roles",
    "Subsystem": "Subsystems",
    "StyleItem": "StyleItems",
    "Language": "Languages",
}

errors = []
warnings = []
checked = 0


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def all_xml():
    out = []
    for base, _, files in os.walk(ROOT):
        if "/.git" in base or "/.refs" in base:
            continue
        for f in files:
            if f.endswith(".xml"):
                out.append(os.path.join(base, f))
    return sorted(out)


def rel(p):
    return os.path.relpath(p, ROOT)


def check_wellformed(files):
    global checked
    for f in files:
        r = subprocess.run(["xmllint", "--noout", f], capture_output=True, text=True)
        checked += 1
        if r.returncode != 0:
            err("%s: не well-formed: %s" % (rel(f), r.stderr.strip().splitlines()[-1]))


def load_tree(f):
    with open(f, "rb") as fh:
        return ET.parse(fh).getroot()


def collect_objects():
    """Собирает имена объектов по типам из файлов на диске."""
    found = {k: set() for k in KIND_DIRS}
    for kind, d in KIND_DIRS.items():
        for f in glob.glob(os.path.join(ROOT, d, "*.xml")):
            found[kind].add(os.path.splitext(os.path.basename(f))[0])
    return found


def check_root(found):
    cfg_path = os.path.join(ROOT, "Configuration.xml")
    if not os.path.exists(cfg_path):
        err("нет Configuration.xml")
        return None
    root = load_tree(cfg_path)
    conf = root.find("md:Configuration", NS)
    if conf is None:
        err("Configuration.xml: нет элемента Configuration")
        return None
    props = conf.find("md:Properties", NS)
    name = props.findtext("md:Name", default="", namespaces=NS)
    if not name:
        err("Configuration.xml: пустое имя конфигурации")
    in_root = {}
    child = conf.find("md:ChildObjects", NS)
    if child is None:
        err("Configuration.xml: нет ChildObjects")
        return conf
    for el in list(child):
        tag = el.tag.split("}")[-1]
        in_root.setdefault(tag, set()).add((el.text or "").strip())

    for kind, d in KIND_DIRS.items():
        disk = found[kind]
        declared = in_root.get(kind, set())
        for n in sorted(disk - declared):
            err("объект %s.%s лежит на диске, но не объявлен в Configuration.xml" % (kind, n))
        for n in sorted(declared - disk):
            err("Configuration.xml объявляет %s.%s, но файла нет" % (kind, n))
        for n in sorted(declared & disk):
            pass

    # порядок типов в корне
    order = ["Language", "Subsystem", "StyleItem", "Style", "CommonPicture", "SessionParameter",
             "Role", "CommonTemplate", "FilterCriterion", "CommonModule", "CommonAttribute",
             "ExchangePlan", "XDTOPackage", "WebService", "HTTPService", "WSReference",
             "EventSubscription", "ScheduledJob", "SettingsStorage", "FunctionalOption",
             "FunctionalOptionsParameter", "DefinedType", "Bot", "PaletteColor",
             "CommonCommand", "CommandGroup", "Constant", "CommonForm", "Catalog", "Document",
             "DocumentNumerator", "Sequence", "DocumentJournal", "Enum", "Report",
             "DataProcessor", "InformationRegister", "AccumulationRegister",
             "ChartOfCharacteristicTypes", "ChartOfAccounts", "AccountingRegister",
             "ChartOfCalculationTypes", "CalculationRegister", "BusinessProcess", "Task"]
    seen = [el.tag.split("}")[-1] for el in list(child)]
    idx = [order.index(t) for t in seen if t in order]
    if idx != sorted(idx):
        err("Configuration.xml: нарушен порядок типов в ChildObjects: %s" % ", ".join(seen))
    return conf


def iter_object_files(found):
    for kind, d in KIND_DIRS.items():
        for n in sorted(found[kind]):
            yield kind, n, os.path.join(ROOT, d, n + ".xml")


def check_uuids(files):
    seen = {}
    for f in files:
        try:
            root = load_tree(f)
        except ET.ParseError:
            continue
        for el in root.iter():
            u = el.get("uuid")
            if u:
                if u in seen:
                    err("uuid %s повторяется: %s и %s" % (u, seen[u], rel(f)))
                seen[u] = rel(f)
    return len(seen)


def check_links(found):
    names = {k: found[k] for k in found}
    known = {
        "CatalogRef": "Catalog", "CatalogObject": "Catalog",
        "EnumRef": "Enum", "DocumentRef": "Document", "DocumentObject": "Document",
        "ChartOfCharacteristicTypesRef": "ChartOfCharacteristicTypes",
        "InformationRegisterRecordSet": "InformationRegister",
    }
    ref_re = re.compile(r"cfg:([A-Za-z]+)\.([^\s<\"]+)")
    for f in all_xml():
        if "/Forms/" in f:
            pass
        text = open(f, encoding="utf-8").read()
        for kind, obj in ref_re.findall(text):
            target = known.get(kind)
            if not target:
                continue
            obj = obj.split(".")[0]
            if obj not in names.get(target, set()):
                err("%s: ссылка на несуществующий %s.%s" % (rel(f), kind, obj))

    # формы: <Form>Имя</Form> у объекта -> Catalogs/X/Forms/Имя.xml
    for kind, name, path in iter_object_files(found):
        d = KIND_DIRS[kind]
        try:
            root = load_tree(path)
        except ET.ParseError:
            continue
        el = root[0] if len(root) else None
        if el is None:
            continue
        for form_el in el.iter("{%s}Form" % NS["md"]):
            form = (form_el.text or "").strip()
            if not form:
                continue
            fp = os.path.join(ROOT, d, name, "Forms", form + ".xml")
            if not os.path.exists(fp):
                err("%s: объявлена форма %s, но файла %s нет" % (rel(path), form, rel(fp)))


def check_props(found):
    for kind, name, path in iter_object_files(found):
        try:
            root = load_tree(path)
        except ET.ParseError:
            continue
        el = root[0] if len(root) else None
        if el is None:
            err("%s: пустой MetaDataObject" % rel(path))
            continue
        props = el.find("md:Properties", NS)
        if props is None:
            err("%s: нет Properties" % rel(path))
            continue
        n = props.findtext("md:Name", default="", namespaces=NS)
        if n != name:
            err("%s: Name=%r не совпадает с именем файла %r" % (rel(path), n, name))
        syn = props.find("md:Synonym", NS)
        if syn is None or not (syn.text or "").strip():
            # синоним есть как вложенный v8:item
            item = syn.find("v8:item/v8:content", {"v8": "http://v8.1c.ru/8.1/data/core"}) if syn is not None else None
            if item is None or not (item.text or "").strip():
                err("%s: не заполнен синоним (стандарт № 474)" % rel(path))
        # табличные части: GeneratedType должен быть
        for ts in el.iter("{%s}TabularSection" % NS["md"]):
            if ts.find("md:InternalInfo", NS) is None:
                err("%s: у табличной части нет InternalInfo" % rel(path))


def check_modules(found):
    need = [
        ("CommonModules/КонструкторВидов/Ext/Module.bsl", "общий модуль КонструкторВидов"),
        ("Documents/ДокументСЭД/Ext/ObjectModule.bsl", "модуль объекта ДокументСЭД"),
        ("Documents/ДокументСЭД/Ext/ManagerModule.bsl", "модуль менеджера ДокументСЭД"),
        ("Catalogs/ВидыДокументов/Ext/ObjectModule.bsl", "модуль объекта ВидыДокументов"),
    ]
    for relpath, what in need:
        if not os.path.exists(os.path.join(ROOT, relpath)):
            warn("нет файла %s (%s) — модуль ещё не написан" % (relpath, what))
    for f in glob.glob(os.path.join(ROOT, "**", "*.bsl"), recursive=True):
        raw = open(f, "rb").read()
        if not raw.startswith(b"\xef\xbb\xbf"):
            warn("%s: нет BOM в начале файла (1С ждёт UTF-8 с BOM)" % rel(f))


def main():
    files = all_xml()
    if not files:
        print("нет XML — сначала запусти tools/gen_config.py")
        return 2
    check_wellformed(files)
    found = collect_objects()
    check_root(found)
    uuids = check_uuids(files)
    check_links(found)
    check_props(found)
    check_modules(found)

    print("файлов XML: %d, уникальных uuid: %d" % (len(files), uuids))
    print("объектов: " + ", ".join("%s=%d" % (k, len(v)) for k, v in sorted(found.items()) if v))
    if warnings:
        print("\nпредупреждения (не ломают загрузку):")
        for w in warnings:
            print("  -", w)
    if errors:
        print("\nошибки:")
        for e in errors:
            print("  -", e)
        print("\nИТОГ: проверки НЕ пройдены (%d)" % len(errors))
        return 1
    print("\nИТОГ: все проверки пройдены. Загрузка в платформу не выполнялась — платформы нет.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
