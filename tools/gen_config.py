#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор XML-выгрузки конфигурации «ДокМаршрут» (формат выгрузки 1С 8.3, версия 2.17).

Источник истины — spec/metadata.json. Шаблоны структуры файлов повторяют реальный
эталонный дамп Конфигуратора (см. .refs/ex), порядок элементов — как в выгрузке 1С.

Запуск: python3 tools/gen_config.py [--out .]
Скрипт пишет только метаданные (*.xml). Модули *.bsl не трогает: если файл уже есть,
он остаётся как есть.
"""
import json
import os
import re
import sys
import uuid

NS = uuid.UUID("6f1ed0f4-2e2a-4a45-9b6d-3f5f0e2f6a10")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_PATH = os.path.join(ROOT, "spec", "metadata.json")

HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses"'
    ' xmlns:app="http://v8.1c.ru/8.2/managed-application/core"'
    ' xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"'
    ' xmlns:cmi="http://v8.1c.ru/8.2/managed-application/cmi"'
    ' xmlns:ent="http://v8.1c.ru/8.1/data/enterprise"'
    ' xmlns:lf="http://v8.1c.ru/8.2/managed-application/logform"'
    ' xmlns:style="http://v8.1c.ru/8.1/data/ui/style"'
    ' xmlns:sys="http://v8.1c.ru/8.1/data/ui/fonts/system"'
    ' xmlns:v8="http://v8.1c.ru/8.1/data/core"'
    ' xmlns:v8ui="http://v8.1c.ru/8.1/data/ui"'
    ' xmlns:web="http://v8.1c.ru/8.1/data/ui/colors/web"'
    ' xmlns:win="http://v8.1c.ru/8.1/data/ui/colors/windows"'
    ' xmlns:xen="http://v8.1c.ru/8.3/xcf/enums"'
    ' xmlns:xpr="http://v8.1c.ru/8.3/xcf/predef"'
    ' xmlns:xr="http://v8.1c.ru/8.3/xcf/readable"'
    ' xmlns:xs="http://www.w3.org/2001/XMLSchema"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' version="2.17">\n'
)
FOOTER = "</MetaDataObject>\n"

SHELL_STUB = """#Область ОбработчикиСобытий

// Оболочка общего модуля создана в каркасе (зона Ангелины, каркас 18.11 20:00).
// Наполняет владелец модуля в своей ветке; править этот файл может только он.

#КонецОбласти
"""



def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def syn(text, indent=3):
    """Мультиязычный синоним."""
    t = "\t" * indent
    return (f"{t}<Synonym>\n{t}\t<v8:item>\n{t}\t\t<v8:lang>ru</v8:lang>\n"
            f"{t}\t\t<v8:content>{esc(text)}</v8:content>\n{t}\t</v8:item>\n{t}</Synonym>\n")


def generated_types(kind, name, cats, indent=2):
    """Блок InternalInfo с GeneratedType. cats — список (суффикс, категория)."""
    t = "\t" * indent
    out = [f"{t}<InternalInfo>\n"]
    for suffix, category in cats:
        out.append(f'{t}\t<xr:GeneratedType name="{kind}{suffix}.{esc(name)}" category="{category}">\n')
        out.append(f"{t}\t\t<xr:TypeId>{uid(name, kind + suffix, 'type')}</xr:TypeId>\n")
        out.append(f"{t}\t\t<xr:ValueId>{uid(name, kind + suffix, 'value')}</xr:ValueId>\n")
        out.append(f"{t}\t</xr:GeneratedType>\n")
    out.append(f"{t}</InternalInfo>\n")
    return "".join(out)


CATALOG_CATS = [("Object", "Object"), ("Ref", "Ref"), ("Selection", "Selection"),
                ("List", "List"), ("Manager", "Manager")]
DOCUMENT_CATS = [("Object", "Object"), ("Ref", "Ref"), ("Selection", "Selection"),
                 ("List", "List"), ("Manager", "Manager")]
ENUM_CATS = [("Ref", "Ref"), ("Manager", "Manager"), ("List", "List")]
IR_CATS = [("Record", "Record"), ("Manager", "Manager"), ("Selection", "Selection"),
           ("List", "List"), ("RecordSet", "RecordSet"), ("RecordKey", "RecordKey"),
           ("RecordManager", "RecordManager")]
CONSTANT_CATS = [("Manager", "Manager"), ("ValueManager", "ValueManager"),
                 ("ValueKey", "ValueKey")]
PVH_CATS = [("Object", "Object"), ("Ref", "Ref"), ("Selection", "Selection"),
            ("List", "List"), ("Characteristic", "Characteristic"), ("Manager", "Manager")]


# ---------------------------------------------------------------- типы значений
def type_xml(spec, indent):
    """Собирает <Type> по упрощённой записи: String(100), Number(15,2), Bool, Date,
    CatalogRef.X, EnumRef.X, DocumentRef.X, ChartOfCharacteristicTypesRef.X,
    Multi:String(500),Number(15,2),..."""
    t = "\t" * indent
    if spec.startswith("Multi:"):
        sep = "|" if "|" in spec else ","
        parts = spec[6:].split(sep)
        items = []
        quals = ""
        for p in parts:
            one, q = type_one(p.strip(), indent + 1)
            items.append(one)
            if q and q not in quals:
                quals += q
        body = "".join(items) + quals
        return f"{t}<Type>\n{body}{t}</Type>\n", None

    one, quals = type_one(spec, indent + 1)
    return f"{t}<Type>\n{one}{quals}{t}</Type>\n", None


def type_one(spec, indent):
    t = "\t" * indent
    spec = spec.strip()
    m = re.match(r"^String\((\d+)\)$", spec)
    if m:
        return (f"{t}<v8:Type>xs:string</v8:Type>\n", 
                f"{t}<v8:StringQualifiers>\n{t}\t<v8:Length>{m.group(1)}</v8:Length>\n"
                f"{t}\t<v8:AllowedLength>Variable</v8:AllowedLength>\n{t}</v8:StringQualifiers>\n")
    m = re.match(r"^Number\((\d+),(\d+)\)$", spec)
    if m:
        return (f"{t}<v8:Type>xs:decimal</v8:Type>\n",
                f"{t}<v8:NumberQualifiers>\n{t}\t<v8:Digits>{m.group(1)}</v8:Digits>\n"
                f"{t}\t<v8:FractionDigits>{m.group(2)}</v8:FractionDigits>\n"
                f"{t}\t<v8:AllowedSign>Any</v8:AllowedSign>\n{t}</v8:NumberQualifiers>\n")
    if spec == "Bool":
        return f"{t}<v8:Type>xs:boolean</v8:Type>\n", ""
    if spec == "Date":
        return (f"{t}<v8:Type>xs:dateTime</v8:Type>\n",
                f"{t}<v8:DateQualifiers>\n{t}\t<v8:DateFractions>Date</v8:DateFractions>\n"
                f"{t}</v8:DateQualifiers>\n")
    if spec.startswith(("CatalogRef.", "EnumRef.", "DocumentRef.",
                        "ChartOfCharacteristicTypesRef.")):
        return f"{t}<v8:Type>cfg:{spec}</v8:Type>\n", ""
    raise ValueError("неизвестный тип: " + spec)


# ---------------------------------------------------------------- реквизит
def attribute(obj_kind, obj_name, attr, indent=3, is_ts=False, extra="", comment=None):
    """Реквизит / колонка табличной части. obj_kind: Catalog|Document|ChartOfCharacteristicTypes."""
    t = "\t" * indent
    a = attr
    typ, _ = type_xml(a["type"], indent + 1)
    num_dec = 0
    m = re.match(r"^Number\(\d+,(\d+)\)$", a["type"])
    if m:
        num_dec = int(m.group(1))
    fill_value = ('<FillValue xsi:type="xs:decimal">0</FillValue>' if num_dec
                  else '<FillValue xsi:nil="true"/>')
    if a["type"].startswith("String("):
        fill_value = '<FillValue xsi:type="xs:string"/>'
    if a["type"] == "Bool":
        fill_value = '<FillValue xsi:type="xs:boolean">false</FillValue>'

    out = [f'{t}<Attribute uuid="{uid(obj_kind + "." + obj_name, "attr", a["name"])}">\n']
    out.append(f"{t}\t<Properties>\n")
    out.append(f"{t}\t\t<Name>{esc(a['name'])}</Name>\n")
    out.append(syn(a.get("synonym", a["name"]), indent + 2))
    out.append(f"{t}\t\t<Comment>{esc(a.get('comment', ''))}</Comment>\n")
    out.append(typ.replace("\t" * (indent + 1), "\t" * (indent + 2)))
    out.append(f"{t}\t\t<PasswordMode>{'true' if a.get('passwordMode') else 'false'}</PasswordMode>\n")
    out.append(f"{t}\t\t<Format/>\n")
    out.append(f"{t}\t\t<EditFormat/>\n")
    out.append(f"{t}\t\t<ToolTip/>\n")
    out.append(f"{t}\t\t<MarkNegatives>false</MarkNegatives>\n")
    out.append(f"{t}\t\t<Mask/>\n")
    out.append(f"{t}\t\t<MultiLine>false</MultiLine>\n")
    out.append(f"{t}\t\t<ExtendedEdit>false</ExtendedEdit>\n")
    out.append(f"{t}\t\t<MinValue xsi:nil=\"true\"/>\n")
    out.append(f"{t}\t\t<MaxValue xsi:nil=\"true\"/>\n")
    if not is_ts:
        out.append(f"{t}\t\t<FillFromFillingValue>false</FillFromFillingValue>\n")
        out.append(f"{t}\t\t<FillValue xsi:nil=\"true\"/>\n")
    out.append(f"{t}\t\t<FillChecking>DontCheck</FillChecking>\n")
    out.append(f"{t}\t\t<ChoiceFoldersAndItems>Items</ChoiceFoldersAndItems>\n")
    out.append(f"{t}\t\t<ChoiceParameterLinks/>\n")
    out.append(f"{t}\t\t<ChoiceParameters/>\n")
    out.append(f"{t}\t\t<QuickChoice>Auto</QuickChoice>\n")
    out.append(f"{t}\t\t<CreateOnInput>Auto</CreateOnInput>\n")
    out.append(f"{t}\t\t<ChoiceForm/>\n")
    out.append(f"{t}\t\t<LinkByType/>\n")
    out.append(f"{t}\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append(extra)
    out.append(f"{t}\t\t<Indexing>{'Index' if a.get('index') else 'DontIndex'}</Indexing>\n")
    out.append(f"{t}\t\t<FullTextSearch>Use</FullTextSearch>\n")
    out.append(f"{t}\t\t<DataHistory>Use</DataHistory>\n")
    out.append(f"{t}\t</Properties>\n")
    out.append(f"{t}</Attribute>\n")
    return "".join(out)


STD_ATTR_BODY = """{t}<xr:LinkByType/>
{t}<xr:FillChecking>DontCheck</xr:FillChecking>
{t}<xr:MultiLine>false</xr:MultiLine>
{t}<xr:FillFromFillingValue>false</xr:FillFromFillingValue>
{t}<xr:CreateOnInput>Auto</xr:CreateOnInput>
{t}<xr:MaxValue xsi:nil="true"/>
{t}<xr:ToolTip/>
{t}<xr:ExtendedEdit>false</xr:ExtendedEdit>
{t}<xr:Format/>
{t}<xr:ChoiceForm/>
{t}<xr:QuickChoice>Auto</xr:QuickChoice>
{t}<xr:ChoiceHistoryOnInput>Auto</xr:ChoiceHistoryOnInput>
{t}<xr:EditFormat/>
{t}<xr:PasswordMode>false</xr:PasswordMode>
{t}<xr:DataHistory>Use</xr:DataHistory>
{t}<xr:MarkNegatives>false</xr:MarkNegatives>
{t}<xr:MinValue xsi:nil="true"/>
{t}<xr:Synonym/>
{t}<xr:Comment/>
{t}<xr:FullTextSearch>Use</xr:FullTextSearch>
{t}<xr:ChoiceParameterLinks/>
{t}<xr:FillValue xsi:nil="true"/>
{t}<xr:Mask/>
{t}<xr:ChoiceParameters/>
"""


def std_attrs(names, indent):
    t = "\t" * indent
    out = [f"{t}<StandardAttributes>\n"]
    for n in names:
        out.append(f'{t}\t<xr:StandardAttribute name="{n}">\n')
        out.append(STD_ATTR_BODY.format(t=t + "\t\t"))
        out.append(f"{t}\t</xr:StandardAttribute>\n")
    out.append(f"{t}</StandardAttributes>\n")
    return "".join(out)


# ---------------------------------------------------------------- перечисления
def gen_enum(e):
    name = e["name"]
    out = [HEADER, f'\t<Enum uuid="{uid("Enum", name)}">\n',
           generated_types("Enum", name, ENUM_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(e.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(e.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<UseStandardCommands>false</UseStandardCommands>\n")
    out.append(std_attrs(["Order", "Ref"], 3))
    out.append("\t\t\t<Characteristics/>\n")
    out.append("\t\t\t<QuickChoice>true</QuickChoice>\n")
    out.append("\t\t\t<ChoiceMode>BothWays</ChoiceMode>\n")
    out.append("\t\t\t<DefaultListForm/>\n")
    out.append("\t\t\t<DefaultChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryListForm/>\n")
    out.append("\t\t\t<AuxiliaryChoiceForm/>\n")
    out.append("\t\t\t<ListPresentation/>\n")
    out.append("\t\t\t<ExtendedListPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t\t<ChildObjects>\n")
    for v in e["values"]:
        out.append(f'\t\t\t<EnumValue uuid="{uid("Enum." + name, "value", v["name"])}">\n')
        out.append("\t\t\t\t<Properties>\n")
        out.append(f"\t\t\t\t\t<Name>{esc(v['name'])}</Name>\n")
        out.append(syn(v.get("synonym", v["name"]), 5))
        out.append(f"\t\t\t\t\t<Comment>{esc(v.get('comment', ''))}</Comment>\n")
        out.append("\t\t\t\t</Properties>\n")
        out.append("\t\t\t</EnumValue>\n")
    out.append("\t\t</ChildObjects>\n")
    out.append("\t</Enum>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- справочник
def gen_tabular_section(owner_kind, owner_name, ts, indent=2):
    t = "\t" * indent
    name = ts["name"]
    ts_kind = owner_kind + "TabularSection"
    ts_row_kind = owner_kind + "TabularSectionRow"
    out = [f'{t}<TabularSection uuid="{uid(owner_kind + "." + owner_name, "ts", name)}">\n']
    # оба GeneratedType — в одной InternalInfo, как в выгрузке Конфигуратора
    ti = "\t" * (indent + 1)
    out.append(f"{ti}<InternalInfo>\n")
    for kind, category in ((ts_kind, "TabularSection"), (ts_row_kind, "TabularSectionRow")):
        out.append(f'{ti}\t<xr:GeneratedType name="{kind}.{esc(owner_name)}.{esc(name)}" category="{category}">\n')
        out.append(f"{ti}\t\t<xr:TypeId>{uid(owner_name + '.' + name, kind, 'type')}</xr:TypeId>\n")
        out.append(f"{ti}\t\t<xr:ValueId>{uid(owner_name + '.' + name, kind, 'value')}</xr:ValueId>\n")
        out.append(f"{ti}\t</xr:GeneratedType>\n")
    out.append(f"{ti}</InternalInfo>\n")
    out.append(f"{t}\t<Properties>\n")
    out.append(f"{t}\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(ts.get("synonym", name), indent + 2))
    out.append(f"{t}\t\t<Comment>{esc(ts.get('comment', ''))}</Comment>\n")
    out.append(f"{t}\t\t<ToolTip/>\n")
    out.append(f"{t}\t\t<FillChecking>DontCheck</FillChecking>\n")
    out.append(std_attrs(["LineNumber"], indent + 2))
    out.append(f"{t}\t</Properties>\n")
    out.append(f"{t}\t<ChildObjects>\n")
    for a in ts["attributes"]:
        out.append(attribute(owner_kind, owner_name + "." + name, a, indent + 2, is_ts=True))
    out.append(f"{t}\t</ChildObjects>\n")
    out.append(f"{t}</TabularSection>\n")
    return "".join(out)


def gen_catalog(c, forms):
    name = c["name"]
    out = [HEADER, f'\t<Catalog uuid="{uid("Catalog", name)}">\n',
           generated_types("Catalog", name, CATALOG_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(c.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(c.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<Hierarchical>false</Hierarchical>\n")
    out.append("\t\t\t<HierarchyType>HierarchyFoldersAndItems</HierarchyType>\n")
    out.append("\t\t\t<LimitLevelCount>false</LimitLevelCount>\n")
    out.append("\t\t\t<LevelCount>2</LevelCount>\n")
    out.append("\t\t\t<FoldersOnTop>true</FoldersOnTop>\n")
    out.append("\t\t\t<UseStandardCommands>true</UseStandardCommands>\n")
    if c.get("owners"):
        out.append("\t\t\t<Owners>\n")
        for o in c["owners"]:
            out.append('\t\t\t\t<xr:Item xsi:type="xr:MDObjectRef">%s</xr:Item>\n' % esc(o))
        out.append("\t\t\t</Owners>\n")
    else:
        out.append("\t\t\t<Owners/>\n")
    out.append("\t\t\t<SubordinationUse>ToItems</SubordinationUse>\n")
    out.append(f"\t\t\t<CodeLength>{c.get('codeLength', 9)}</CodeLength>\n")
    out.append(f"\t\t\t<DescriptionLength>{c.get('descriptionLength', 150)}</DescriptionLength>\n")
    out.append("\t\t\t<CodeType>String</CodeType>\n")
    out.append("\t\t\t<CodeAllowedLength>Variable</CodeAllowedLength>\n")
    out.append("\t\t\t<CodeSeries>WholeCatalog</CodeSeries>\n")
    out.append("\t\t\t<CheckUnique>true</CheckUnique>\n")
    out.append("\t\t\t<Autonumbering>true</Autonumbering>\n")
    out.append("\t\t\t<DefaultPresentation>AsDescription</DefaultPresentation>\n")
    out.append("\t\t\t<Characteristics/>\n")
    out.append("\t\t\t<PredefinedDataUpdate>Auto</PredefinedDataUpdate>\n")
    out.append("\t\t\t<EditType>InDialog</EditType>\n")
    out.append("\t\t\t<QuickChoice>false</QuickChoice>\n")
    out.append("\t\t\t<ChoiceMode>BothWays</ChoiceMode>\n")
    out.append("\t\t\t<InputByString>\n")
    out.append(f"\t\t\t\t<xr:Field>Catalog.{esc(name)}.StandardAttribute.Description</xr:Field>\n")
    out.append(f"\t\t\t\t<xr:Field>Catalog.{esc(name)}.StandardAttribute.Code</xr:Field>\n")
    out.append("\t\t\t</InputByString>\n")
    out.append("\t\t\t<SearchStringModeOnInputByString>Begin</SearchStringModeOnInputByString>\n")
    out.append("\t\t\t<FullTextSearchOnInputByString>DontUse</FullTextSearchOnInputByString>\n")
    out.append("\t\t\t<ChoiceDataGetModeOnInputByString>Directly</ChoiceDataGetModeOnInputByString>\n")
    out.append(f"\t\t\t<DefaultObjectForm>{forms.get('object', '')}</DefaultObjectForm>\n")
    out.append("\t\t\t<DefaultFolderForm/>\n")
    out.append(f"\t\t\t<DefaultListForm>{forms.get('list', '')}</DefaultListForm>\n")
    out.append(f"\t\t\t<DefaultChoiceForm>{forms.get('choice', '')}</DefaultChoiceForm>\n")
    out.append("\t\t\t<DefaultFolderChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryObjectForm/>\n")
    out.append("\t\t\t<AuxiliaryFolderForm/>\n")
    out.append("\t\t\t<AuxiliaryListForm/>\n")
    out.append("\t\t\t<AuxiliaryChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryFolderChoiceForm/>\n")
    out.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    out.append("\t\t\t<BasedOn/>\n")
    out.append("\t\t\t<DataLockFields/>\n")
    out.append("\t\t\t<DataLockControlMode>Managed</DataLockControlMode>\n")
    out.append("\t\t\t<FullTextSearch>Use</FullTextSearch>\n")
    out.append("\t\t\t<ObjectPresentation/>\n")
    out.append("\t\t\t<ExtendedObjectPresentation/>\n")
    out.append("\t\t\t<ListPresentation/>\n")
    out.append("\t\t\t<ExtendedListPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<CreateOnInput>Use</CreateOnInput>\n")
    out.append("\t\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append("\t\t\t<DataHistory>DontUse</DataHistory>\n")
    out.append("\t\t\t<UpdateDataHistoryImmediatelyAfterWrite>false</UpdateDataHistoryImmediatelyAfterWrite>\n")
    out.append("\t\t\t<ExecuteAfterWriteDataHistoryVersionProcessing>false</ExecuteAfterWriteDataHistoryVersionProcessing>\n")
    out.append("\t\t</Properties>\n")
    children = []
    for a in c.get("attributes", []):
        children.append(attribute("Catalog", name, a, 3))
    for ts in c.get("tabularSections", []):
        children.append(gen_tabular_section("Catalog", name, ts, 3))
    for f in forms.get("names", []):
        children.append(f"\t\t\t<Form>{esc(f)}</Form>\n")
    if children:
        out.append("\t\t<ChildObjects>\n")
        out.extend(children)
        out.append("\t\t</ChildObjects>\n")
    else:
        out.append("\t\t<ChildObjects/>\n")
    out.append("\t</Catalog>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- ПВХ
def gen_pvh(p, forms):
    name = p["name"]
    out = [HEADER, f'\t<ChartOfCharacteristicTypes uuid="{uid("ChartOfCharacteristicTypes", name)}">\n',
           generated_types("ChartOfCharacteristicTypes", name, PVH_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(p.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(p.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<UseStandardCommands>true</UseStandardCommands>\n")
    out.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    out.append("\t\t\t<CharacteristicExtValues/>\n")
    typ, _ = type_xml("Multi:" + "|".join(p["valueTypes"]), 3)
    out.append(typ)
    out.append("\t\t\t<Hierarchical>false</Hierarchical>\n")
    out.append("\t\t\t<FoldersOnTop>true</FoldersOnTop>\n")
    out.append("\t\t\t<CodeLength>9</CodeLength>\n")
    out.append("\t\t\t<CodeAllowedLength>Variable</CodeAllowedLength>\n")
    out.append(f"\t\t\t<DescriptionLength>{p.get('descriptionLength', 150)}</DescriptionLength>\n")
    out.append("\t\t\t<CodeSeries>WholeCharacteristicKind</CodeSeries>\n")
    out.append("\t\t\t<CheckUnique>true</CheckUnique>\n")
    out.append("\t\t\t<Autonumbering>true</Autonumbering>\n")
    out.append("\t\t\t<DefaultPresentation>AsDescription</DefaultPresentation>\n")
    out.append("\t\t\t<Characteristics/>\n")
    out.append("\t\t\t<PredefinedDataUpdate>Auto</PredefinedDataUpdate>\n")
    out.append("\t\t\t<EditType>InDialog</EditType>\n")
    out.append("\t\t\t<QuickChoice>false</QuickChoice>\n")
    out.append("\t\t\t<ChoiceMode>BothWays</ChoiceMode>\n")
    out.append("\t\t\t<InputByString>\n")
    out.append(f"\t\t\t\t<xr:Field>ChartOfCharacteristicTypes.{esc(name)}.StandardAttribute.Description</xr:Field>\n")
    out.append(f"\t\t\t\t<xr:Field>ChartOfCharacteristicTypes.{esc(name)}.StandardAttribute.Code</xr:Field>\n")
    out.append("\t\t\t</InputByString>\n")
    out.append("\t\t\t<CreateOnInput>DontUse</CreateOnInput>\n")
    out.append("\t\t\t<SearchStringModeOnInputByString>Begin</SearchStringModeOnInputByString>\n")
    out.append("\t\t\t<ChoiceDataGetModeOnInputByString>Directly</ChoiceDataGetModeOnInputByString>\n")
    out.append("\t\t\t<FullTextSearchOnInputByString>DontUse</FullTextSearchOnInputByString>\n")
    out.append("\t\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append("\t\t\t<DefaultObjectForm/>\n")
    out.append("\t\t\t<DefaultFolderForm/>\n")
    out.append("\t\t\t<DefaultListForm/>\n")
    out.append("\t\t\t<DefaultChoiceForm/>\n")
    out.append("\t\t\t<DefaultFolderChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryObjectForm/>\n")
    out.append("\t\t\t<AuxiliaryFolderForm/>\n")
    out.append("\t\t\t<AuxiliaryListForm/>\n")
    out.append("\t\t\t<AuxiliaryChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryFolderChoiceForm/>\n")
    out.append("\t\t\t<BasedOn/>\n")
    out.append("\t\t\t<DataLockFields/>\n")
    out.append("\t\t\t<DataLockControlMode>Managed</DataLockControlMode>\n")
    out.append("\t\t\t<FullTextSearch>Use</FullTextSearch>\n")
    out.append("\t\t\t<ObjectPresentation/>\n")
    out.append("\t\t\t<ExtendedObjectPresentation/>\n")
    out.append("\t\t\t<ListPresentation/>\n")
    out.append("\t\t\t<ExtendedListPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<DataHistory>DontUse</DataHistory>\n")
    out.append("\t\t\t<UpdateDataHistoryImmediatelyAfterWrite>false</UpdateDataHistoryImmediatelyAfterWrite>\n")
    out.append("\t\t\t<ExecuteAfterWriteDataHistoryVersionProcessing>false</ExecuteAfterWriteDataHistoryVersionProcessing>\n")
    out.append("\t\t</Properties>\n")
    children = [attribute("ChartOfCharacteristicTypes", name, a, 3) for a in p.get("attributes", [])]
    if children:
        out.append("\t\t<ChildObjects>\n")
        out.extend(children)
        out.append("\t\t</ChildObjects>\n")
    else:
        out.append("\t\t<ChildObjects/>\n")
    out.append("\t</ChartOfCharacteristicTypes>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- документ
def gen_document(d, forms):
    name = d["name"]
    out = [HEADER, f'\t<Document uuid="{uid("Document", name)}">\n',
           generated_types("Document", name, DOCUMENT_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(d.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(d.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<UseStandardCommands>true</UseStandardCommands>\n")
    out.append("\t\t\t<Numerator/>\n")
    out.append(f"\t\t\t<NumberType>{d.get('numberType', 'String')}</NumberType>\n")
    out.append(f"\t\t\t<NumberLength>{d.get('numberLength', 15)}</NumberLength>\n")
    out.append("\t\t\t<NumberAllowedLength>Variable</NumberAllowedLength>\n")
    out.append(f"\t\t\t<NumberPeriodicity>{d.get('numberPeriodicity', 'Year')}</NumberPeriodicity>\n")
    out.append("\t\t\t<CheckUnique>true</CheckUnique>\n")
    out.append("\t\t\t<Autonumbering>true</Autonumbering>\n")
    out.append("\t\t\t<Characteristics/>\n")
    out.append("\t\t\t<BasedOn/>\n")
    out.append("\t\t\t<InputByString>\n")
    out.append(f"\t\t\t\t<xr:Field>Document.{esc(name)}.StandardAttribute.Number</xr:Field>\n")
    out.append("\t\t\t</InputByString>\n")
    out.append("\t\t\t<CreateOnInput>Use</CreateOnInput>\n")
    out.append("\t\t\t<SearchStringModeOnInputByString>Begin</SearchStringModeOnInputByString>\n")
    out.append("\t\t\t<FullTextSearchOnInputByString>DontUse</FullTextSearchOnInputByString>\n")
    out.append("\t\t\t<ChoiceDataGetModeOnInputByString>Directly</ChoiceDataGetModeOnInputByString>\n")
    out.append(f"\t\t\t<DefaultObjectForm>{forms.get('object', '')}</DefaultObjectForm>\n")
    out.append(f"\t\t\t<DefaultListForm>{forms.get('list', '')}</DefaultListForm>\n")
    out.append("\t\t\t<DefaultChoiceForm/>\n")
    out.append("\t\t\t<AuxiliaryObjectForm/>\n")
    out.append("\t\t\t<AuxiliaryListForm/>\n")
    out.append("\t\t\t<AuxiliaryChoiceForm/>\n")
    out.append("\t\t\t<Posting>Deny</Posting>\n")
    out.append("\t\t\t<RealTimePosting>Deny</RealTimePosting>\n")
    out.append("\t\t\t<RegisterRecordsDeletion>AutoDelete</RegisterRecordsDeletion>\n")
    out.append("\t\t\t<RegisterRecordsWritingOnPost>WriteSelected</RegisterRecordsWritingOnPost>\n")
    out.append("\t\t\t<SequenceFilling>AutoFill</SequenceFilling>\n")
    out.append("\t\t\t<RegisterRecords/>\n")
    out.append("\t\t\t<PostInPrivilegedMode>true</PostInPrivilegedMode>\n")
    out.append("\t\t\t<UnpostInPrivilegedMode>true</UnpostInPrivilegedMode>\n")
    out.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    out.append("\t\t\t<DataLockFields/>\n")
    out.append("\t\t\t<DataLockControlMode>Managed</DataLockControlMode>\n")
    out.append("\t\t\t<FullTextSearch>Use</FullTextSearch>\n")
    out.append("\t\t\t<ObjectPresentation/>\n")
    out.append("\t\t\t<ExtendedObjectPresentation/>\n")
    out.append("\t\t\t<ListPresentation/>\n")
    out.append("\t\t\t<ExtendedListPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append("\t\t\t<DataHistory>DontUse</DataHistory>\n")
    out.append("\t\t\t<UpdateDataHistoryImmediatelyAfterWrite>false</UpdateDataHistoryImmediatelyAfterWrite>\n")
    out.append("\t\t\t<ExecuteAfterWriteDataHistoryVersionProcessing>false</ExecuteAfterWriteDataHistoryVersionProcessing>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t\t<ChildObjects>\n")
    for a in d.get("attributes", []):
        out.append(attribute("Document", name, a, 3))
    for ts in d.get("tabularSections", []):
        out.append(gen_tabular_section("Document", name, ts, 3))
    for f in forms.get("names", []):
        out.append(f"\t\t\t<Form>{esc(f)}</Form>\n")
    out.append("\t\t</ChildObjects>\n")
    out.append("\t</Document>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- регистр сведений
def gen_information_register(r):
    name = r["name"]
    out = [HEADER, f'\t<InformationRegister uuid="{uid("InformationRegister", name)}">\n',
           generated_types("InformationRegister", name, IR_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(r.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(r.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<UseStandardCommands>true</UseStandardCommands>\n")
    out.append("\t\t\t<EditType>InDialog</EditType>\n")
    out.append("\t\t\t<DefaultRecordForm/>\n")
    out.append("\t\t\t<DefaultListForm/>\n")
    out.append("\t\t\t<AuxiliaryRecordForm/>\n")
    out.append("\t\t\t<AuxiliaryListForm/>\n")
    out.append(std_attrs(["Active", "LineNumber"], 3))
    out.append(f"\t\t\t<InformationRegisterPeriodicity>{r.get('periodicity', 'Nonperiodical')}</InformationRegisterPeriodicity>\n")
    out.append(f"\t\t\t<WriteMode>{r.get('writeMode', 'Independent')}</WriteMode>\n")
    out.append("\t\t\t<MainFilterOnPeriod>false</MainFilterOnPeriod>\n")
    out.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    out.append("\t\t\t<DataLockControlMode>Managed</DataLockControlMode>\n")
    out.append("\t\t\t<FullTextSearch>Use</FullTextSearch>\n")
    out.append("\t\t\t<EnableTotalsSliceFirst>false</EnableTotalsSliceFirst>\n")
    out.append("\t\t\t<EnableTotalsSliceLast>false</EnableTotalsSliceLast>\n")
    out.append("\t\t\t<RecordPresentation/>\n")
    out.append("\t\t\t<ExtendedRecordPresentation/>\n")
    out.append("\t\t\t<ListPresentation/>\n")
    out.append("\t\t\t<ExtendedListPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<DataHistory>DontUse</DataHistory>\n")
    out.append("\t\t\t<UpdateDataHistoryImmediatelyAfterWrite>false</UpdateDataHistoryImmediatelyAfterWrite>\n")
    out.append("\t\t\t<ExecuteAfterWriteDataHistoryVersionProcessing>false</ExecuteAfterWriteDataHistoryVersionProcessing>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t\t<ChildObjects>\n")
    for res in r.get("resources", []):
        body = attribute("InformationRegister", name, res, 3)
        body = body.replace("<Attribute uuid", "<Resource uuid").replace("</Attribute>", "</Resource>")
        out.append(body)
    for dim in r.get("dimensions", []):
        extra = ("\t\t\t\t<Master>{}</Master>\n\t\t\t\t<MainFilter>true</MainFilter>\n"
                 "\t\t\t\t<DenyIncompleteValues>false</DenyIncompleteValues>\n").format(
                     "true" if dim.get("master") else "false")
        body = attribute("InformationRegister", name, dim, 3, extra=extra)
        body = body.replace("<Attribute uuid", "<Dimension uuid").replace("</Attribute>", "</Dimension>")
        out.append(body)
    out.append("\t\t</ChildObjects>\n")
    out.append("\t</InformationRegister>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- константа
def gen_constant(c):
    name = c["name"]
    out = [HEADER, f'\t<Constant uuid="{uid("Constant", name)}">\n',
           generated_types("Constant", name, CONSTANT_CATS)]
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(c.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(c.get('comment', ''))}</Comment>\n")
    typ, _ = type_xml(c["type"], 3)
    out.append(typ)
    out.append("\t\t\t<UseStandardCommands>false</UseStandardCommands>\n")
    out.append("\t\t\t<DefaultForm/>\n")
    out.append("\t\t\t<ExtendedPresentation/>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append(f"\t\t\t<PasswordMode>{'true' if c.get('passwordMode') else 'false'}</PasswordMode>\n")
    out.append("\t\t\t<Format/>\n")
    out.append("\t\t\t<EditFormat/>\n")
    out.append("\t\t\t<ToolTip/>\n")
    out.append("\t\t\t<MarkNegatives>false</MarkNegatives>\n")
    out.append("\t\t\t<Mask/>\n")
    out.append("\t\t\t<MultiLine>false</MultiLine>\n")
    out.append("\t\t\t<ExtendedEdit>false</ExtendedEdit>\n")
    out.append("\t\t\t<MinValue xsi:nil=\"true\"/>\n")
    out.append("\t\t\t<MaxValue xsi:nil=\"true\"/>\n")
    out.append("\t\t\t<FillChecking>DontCheck</FillChecking>\n")
    out.append("\t\t\t<ChoiceFoldersAndItems>Items</ChoiceFoldersAndItems>\n")
    out.append("\t\t\t<ChoiceParameterLinks/>\n")
    out.append("\t\t\t<ChoiceParameters/>\n")
    out.append("\t\t\t<QuickChoice>Auto</QuickChoice>\n")
    out.append("\t\t\t<ChoiceForm/>\n")
    out.append("\t\t\t<LinkByType/>\n")
    out.append("\t\t\t<ChoiceHistoryOnInput>Auto</ChoiceHistoryOnInput>\n")
    out.append("\t\t\t<DataHistory>DontUse</DataHistory>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t</Constant>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- общий модуль
def gen_common_module(m):
    name = m["name"]
    out = [HEADER, f'\t<CommonModule uuid="{uid("CommonModule", name)}">\n']
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(m.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(m.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<Global>false</Global>\n")
    out.append("\t\t\t<ClientManagedApplication>false</ClientManagedApplication>\n")
    out.append(f"\t\t\t<Server>{'true' if m.get('server') else 'false'}</Server>\n")
    out.append("\t\t\t<ExternalConnection>false</ExternalConnection>\n")
    out.append("\t\t\t<ClientOrdinaryApplication>false</ClientOrdinaryApplication>\n")
    out.append(f"\t\t\t<ServerCall>{'true' if m.get('serverCall') else 'false'}</ServerCall>\n")
    out.append(f"\t\t\t<Privileged>{'true' if m.get('privileged') else 'false'}</Privileged>\n")
    out.append("\t\t\t<ReturnValuesReuse>DontUse</ReturnValuesReuse>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t</CommonModule>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- роль
def gen_role(role, rights):
    name = role["name"]
    out = [HEADER, f'\t<Role uuid="{uid("Role", name)}">\n']
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(role.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(role.get('comment', ''))}</Comment>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t</Role>\n")
    out.append(FOOTER)

    r = ['<?xml version="1.0" encoding="UTF-8"?>\n'
         '<Rights xmlns="http://v8.1c.ru/8.2/roles" xmlns:xs="http://www.w3.org/2001/XMLSchema"'
         ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Rights" version="2.17">\n',
         "\t<setForNewObjects>false</setForNewObjects>\n",
         "\t<setForAttributesByDefault>true</setForAttributesByDefault>\n",
         "\t<independentRightsOfChildObjects>false</independentRightsOfChildObjects>\n"]
    for obj, right in rights:
        r.append(f"\t<object>\n\t\t<name>{esc(obj)}</name>\n")
        for rn in right:
            r.append(f"\t\t<right>\n\t\t\t<name>{rn}</name>\n\t\t\t<value>true</value>\n\t\t</right>\n")
        r.append("\t</object>\n")
    r.append("</Rights>\n")
    return "".join(out), "".join(r)


# ---------------------------------------------------------------- подсистема
def gen_subsystem(s):
    name = s["name"]
    out = [HEADER, f'\t<Subsystem uuid="{uid("Subsystem", name)}">\n']
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(s.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(s.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<IncludeHelpInContents>true</IncludeHelpInContents>\n")
    out.append("\t\t\t<IncludeInCommandInterface>true</IncludeInCommandInterface>\n")
    out.append("\t\t\t<UseOneCommand>false</UseOneCommand>\n")
    out.append("\t\t\t<Explanation/>\n")
    out.append("\t\t\t<Picture/>\n")
    out.append("\t\t\t<Content>\n")
    for item in s.get("content", []):
        out.append(f'\t\t\t\t<xr:Item xsi:type="xr:MDObjectRef">{esc(item)}</xr:Item>\n')
    out.append("\t\t\t</Content>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t\t<ChildObjects/>\n")
    out.append("\t</Subsystem>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- элемент стиля
def gen_style_item(s):
    name = s["name"]
    out = [HEADER, f'\t<StyleItem uuid="{uid("StyleItem", name)}">\n']
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    out.append(syn(s.get("synonym", name), 3))
    out.append(f"\t\t\t<Comment>{esc(s.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<Type>Color</Type>\n")
    out.append(f'\t\t\t<Value xsi:type="v8ui:Color">{esc(s["color"])}</Value>\n')
    out.append("\t\t</Properties>\n")
    out.append("\t</StyleItem>\n")
    out.append(FOOTER)
    return "".join(out)


# ---------------------------------------------------------------- язык
def gen_language():
    out = [HEADER, f'\t<Language uuid="{uid("Language", "Русский")}">\n']
    out.append("\t\t<Properties>\n")
    out.append("\t\t\t<Name>Русский</Name>\n")
    out.append(syn("Русский", 3))
    out.append("\t\t\t<Comment/>\n")
    out.append("\t\t\t<LanguageCode>ru</LanguageCode>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t</Language>\n")
    out.append(FOOTER)
    return "".join(out)



def gen_common_form(f):
    name = f["name"]
    meta = [HEADER, f'\t<CommonForm uuid="{uid("CommonForm", name)}">\n']
    meta.append("\t\t<Properties>\n")
    meta.append(f"\t\t\t<Name>{esc(name)}</Name>\n")
    meta.append(syn(f.get("synonym", name), 3))
    meta.append(f"\t\t\t<Comment>{esc(f.get('comment', ''))}</Comment>\n")
    meta.append("\t\t\t<FormType>Managed</FormType>\n")
    meta.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    meta.append("\t\t\t<UsePurposes>\n")
    meta.append('\t\t\t\t<v8:Value xsi:type="app:ApplicationUsePurpose">PlatformApplication</v8:Value>\n')
    meta.append("\t\t\t</UsePurposes>\n")
    meta.append("\t\t</Properties>\n")
    meta.append("\t</CommonForm>\n")
    meta.append(FOOTER)

    form_ns = ('xmlns="http://v8.1c.ru/8.3/xcf/logform" xmlns:app="http://v8.1c.ru/8.2/managed-application/core"'
               ' xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config"'
               ' xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"'
               ' xmlns:dcssch="http://v8.1c.ru/8.1/data-composition-system/schema"'
               ' xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"'
               ' xmlns:ent="http://v8.1c.ru/8.1/data/enterprise"'
               ' xmlns:lf="http://v8.1c.ru/8.2/managed-application/logform"'
               ' xmlns:style="http://v8.1c.ru/8.1/data/ui/style"'
               ' xmlns:sys="http://v8.1c.ru/8.1/data/ui/fonts/system"'
               ' xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:v8ui="http://v8.1c.ru/8.1/data/ui"'
               ' xmlns:web="http://v8.1c.ru/8.1/data/ui/colors/web"'
               ' xmlns:win="http://v8.1c.ru/8.1/data/ui/colors/windows"'
               ' xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" xmlns:xs="http://www.w3.org/2001/XMLSchema"'
               ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" version="2.17"')
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n<Form ' + form_ns + '>\n'
            '\t<Title>\n\t\t<v8:item>\n\t\t\t<v8:lang>ru</v8:lang>\n'
            '\t\t\t<v8:content>' + esc(f.get("synonym", name)) + '</v8:content>\n'
            '\t\t</v8:item>\n\t</Title>\n'
            '\t<AutoTitle>false</AutoTitle>\n'
            '\t<AutoCommandBar name="ФормаКоманднаяПанель" id="-1"/>\n'
            '\t<Events>\n\t\t<Event name="OnCreateAtServer">ПриСозданииНаСервере</Event>\n\t</Events>\n'
            '\t<ChildItems/>\n</Form>\n')
    return "".join(meta), body


# ---------------------------------------------------------------- корень
def gen_configuration(cfg, child_groups):
    out = [HEADER, f'\t<Configuration uuid="{uid("Configuration", cfg["name"])}">\n']
    out.append("\t\t<Properties>\n")
    out.append(f"\t\t\t<Name>{esc(cfg['name'])}</Name>\n")
    out.append(syn(cfg.get("synonym", cfg["name"]), 3))
    out.append(f"\t\t\t<Comment>{esc(cfg.get('comment', ''))}</Comment>\n")
    out.append("\t\t\t<NamePrefix/>\n")
    out.append("\t\t\t<ConfigurationExtensionCompatibilityMode>Version8_3_24</ConfigurationExtensionCompatibilityMode>\n")
    out.append("\t\t\t<DefaultRunMode>ManagedApplication</DefaultRunMode>\n")
    out.append("\t\t\t<UsePurposes>\n")
    out.append('\t\t\t\t<v8:Value xsi:type="app:ApplicationUsePurpose">PlatformApplication</v8:Value>\n')
    out.append("\t\t\t</UsePurposes>\n")
    out.append("\t\t\t<ScriptVariant>Russian</ScriptVariant>\n")
    out.append("\t\t\t<DefaultRoles/>\n")
    out.append(f"\t\t\t<Vendor>{esc(cfg.get('vendor', ''))}</Vendor>\n")
    out.append(f"\t\t\t<Version>{esc(cfg.get('version', '0.1.0'))}</Version>\n")
    out.append("\t\t\t<UpdateCatalogAddress/>\n")
    out.append("\t\t\t<IncludeHelpInContents>false</IncludeHelpInContents>\n")
    out.append("\t\t\t<UseManagedFormInOrdinaryApplication>false</UseManagedFormInOrdinaryApplication>\n")
    out.append("\t\t\t<UseOrdinaryFormInManagedApplication>false</UseOrdinaryFormInManagedApplication>\n")
    out.append("\t\t\t<AdditionalFullTextSearchDictionaries/>\n")
    out.append("\t\t\t<CommonSettingsStorage/>\n")
    out.append("\t\t\t<ReportsUserSettingsStorage/>\n")
    out.append("\t\t\t<ReportsVariantsStorage/>\n")
    out.append("\t\t\t<FormDataSettingsStorage/>\n")
    out.append("\t\t\t<DynamicListsUserSettingsStorage/>\n")
    out.append("\t\t\t<URLExternalDataStorage/>\n")
    out.append("\t\t\t<Content/>\n")
    out.append("\t\t\t<DefaultReportForm/>\n")
    out.append("\t\t\t<DefaultReportVariantForm/>\n")
    out.append("\t\t\t<DefaultReportSettingsForm/>\n")
    out.append("\t\t\t<DefaultReportAppearanceTemplate/>\n")
    out.append("\t\t\t<DefaultDynamicListSettingsForm/>\n")
    out.append("\t\t\t<DefaultSearchForm/>\n")
    out.append("\t\t\t<DefaultDataHistoryChangeHistoryForm/>\n")
    out.append("\t\t\t<DefaultDataHistoryVersionDataForm/>\n")
    out.append("\t\t\t<DefaultDataHistoryVersionDifferencesForm/>\n")
    out.append("\t\t\t<DefaultCollaborationSystemUsersChoiceForm/>\n")
    out.append("\t\t\t<RequiredMobileApplicationPermissions/>\n")
    out.append("\t\t\t<UsedMobileApplicationFunctionalities/>\n")
    out.append("\t\t\t<StandaloneConfigurationRestrictionRoles/>\n")
    out.append("\t\t\t<MobileApplicationURLs/>\n")
    out.append("\t\t\t<AllowedIncomingShareRequestTypes/>\n")
    out.append("\t\t\t<MainClientApplicationWindowMode>Normal</MainClientApplicationWindowMode>\n")
    out.append("\t\t\t<DefaultInterface/>\n")
    out.append("\t\t\t<DefaultStyle/>\n")
    out.append("\t\t\t<DefaultLanguage>Language.Русский</DefaultLanguage>\n")
    out.append("\t\t\t<BriefInformation/>\n")
    out.append("\t\t\t<DetailedInformation/>\n")
    out.append("\t\t\t<Copyright/>\n")
    out.append("\t\t\t<VendorInformationAddress/>\n")
    out.append("\t\t\t<ConfigurationInformationAddress/>\n")
    out.append("\t\t\t<DataLockControlMode>Managed</DataLockControlMode>\n")
    out.append("\t\t\t<ObjectAutonumerationMode>NotAutoFree</ObjectAutonumerationMode>\n")
    out.append("\t\t\t<ModalityUseMode>DontUse</ModalityUseMode>\n")
    out.append("\t\t\t<SynchronousPlatformExtensionAndAddInCallUseMode>DontUse</SynchronousPlatformExtensionAndAddInCallUseMode>\n")
    out.append("\t\t\t<InterfaceCompatibilityMode>TaxiEnableVersion8_2</InterfaceCompatibilityMode>\n")
    out.append("\t\t\t<DatabaseTablespacesUseMode>DontUse</DatabaseTablespacesUseMode>\n")
    out.append("\t\t\t<CompatibilityMode>Version8_3_24</CompatibilityMode>\n")
    out.append("\t\t\t<DefaultConstantsForm/>\n")
    out.append("\t\t</Properties>\n")
    out.append("\t\t<ChildObjects>\n")
    # строгий порядок типов в ChildObjects конфигурации
    order = ["Language", "Subsystem", "StyleItem", "Style", "CommonPicture", "SessionParameter",
             "Role", "CommonTemplate", "FilterCriterion", "CommonModule", "CommonAttribute",
             "ExchangePlan", "XDTOPackage", "WebService", "HTTPService", "WSReference",
             "EventSubscription", "ScheduledJob", "SettingsStorage", "FunctionalOption",
             "FunctionalOptionsParameter", "DefinedType", "Bot", "PaletteColor",
             "CommonCommand", "CommandGroup", "Constant", "CommonForm", "Catalog",
             "Document", "DocumentNumerator", "Sequence", "DocumentJournal", "Enum",
             "Report", "DataProcessor", "InformationRegister", "AccumulationRegister",
             "ChartOfCharacteristicTypes", "ChartOfAccounts", "AccountingRegister",
             "ChartOfCalculationTypes", "CalculationRegister", "BusinessProcess", "Task"]
    for kind in order:
        names = sorted(child_groups.get(kind, []))
        for n in names:
            out.append(f"\t\t\t<{kind}>{esc(n)}</{kind}>\n")
    out.append("\t\t</ChildObjects>\n")
    out.append("\t</Configuration>\n")
    out.append(FOOTER)
    return "".join(out)


def write(rel, text, root):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def main():
    root = ROOT
    if "--out" in sys.argv:
        root = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec = json.load(f)

    groups = {}
    written = []

    # формы, которые уже лежат на диске (их пишут отдельные задачи)
    def forms_of(kind, name, prefix=""):
        if not prefix:
            prefix = {"Catalogs": "Catalog", "Documents": "Document",
                      "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes"}.get(kind, kind)
        base = os.path.join(ROOT, kind, name, "Forms")
        names = sorted(os.listdir(base)) if os.path.isdir(base) else []
        names = [n[:-4] for n in names if n.endswith(".xml")]
        res = {"names": names}
        for n in names:
            low = n.lower()
            if low.startswith("формавида"):
                res["object"] = f"Catalog.{name}.Form.{n}"
            elif low.startswith("формавыбора"):
                res["choice"] = f"Catalog.{name}.Form.{n}"
            elif low.startswith("формасписка"):
                res["list"] = f"{prefix}.{name}.Form.{n}"
            elif low.startswith("формадокумента"):
                res["object"] = f"{prefix}.{name}.Form.{n}"
        return res

    # перечисления
    for e in spec.get("enums", []):
        write(f"Enums/{e['name']}.xml", gen_enum(e), root)
        groups.setdefault("Enum", []).append(e["name"]); written.append("Enums/" + e["name"])

    # справочники
    for c in spec.get("catalogs", []):
        write(f"Catalogs/{c['name']}.xml", gen_catalog(c, forms_of("Catalogs", c["name"])), root)
        groups.setdefault("Catalog", []).append(c["name"]); written.append("Catalogs/" + c["name"])

    # план видов характеристик
    for p in spec.get("chartOfCharacteristicTypes", []):
        write(f"ChartsOfCharacteristicTypes/{p['name']}.xml",
              gen_pvh(p, forms_of("ChartsOfCharacteristicTypes", p["name"])), root)
        groups.setdefault("ChartOfCharacteristicTypes", []).append(p["name"])
        written.append("ChartsOfCharacteristicTypes/" + p["name"])

    # документы
    for d in spec.get("documents", []):
        write(f"Documents/{d['name']}.xml", gen_document(d, forms_of("Documents", d["name"])), root)
        groups.setdefault("Document", []).append(d["name"]); written.append("Documents/" + d["name"])

    # регистры сведений
    for r in spec.get("informationRegisters", []):
        write(f"InformationRegisters/{r['name']}.xml", gen_information_register(r), root)
        groups.setdefault("InformationRegister", []).append(r["name"])
        written.append("InformationRegisters/" + r["name"])

    # константы
    for c in spec.get("constants", []):
        write(f"Constants/{c['name']}.xml", gen_constant(c), root)
        groups.setdefault("Constant", []).append(c["name"]); written.append("Constants/" + c["name"])

    # общие модули
    for m in spec.get("commonModules", []):
        write(f"CommonModules/{m['name']}.xml", gen_common_module(m), root)
        groups.setdefault("CommonModule", []).append(m["name"]); written.append("CommonModules/" + m["name"])

    # заглушки модулей оболочек (не перезаписываем написанный код)
    for m in spec.get("commonModules", []):
        module_path = os.path.join(root, "CommonModules", m["name"], "Ext", "Module.bsl")
        if not os.path.exists(module_path):
            os.makedirs(os.path.dirname(module_path), exist_ok=True)
            with open(module_path, "wb") as f:
                f.write(b"\xef\xbb\xbf" + SHELL_STUB.encode("utf-8"))
            written.append("CommonModules/" + m["name"] + "/Ext/Module.bsl (заглушка)")

    # общие формы
    for cf in spec.get("commonForms", []):
        meta, body = gen_common_form(cf)
        write(f"CommonForms/{cf['name']}.xml", meta, root)
        write(f"CommonForms/{cf['name']}/Ext/Form.xml", body, root)
        groups.setdefault("CommonForm", []).append(cf["name"])
        written.append("CommonForms/" + cf["name"])

    # роли + права
    rights_map = build_rights(spec)
    for role in spec.get("roles", []):
        meta, rights = gen_role(role, rights_map.get(role["name"], []))
        write(f"Roles/{role['name']}.xml", meta, root)
        write(f"Roles/{role['name']}/Ext/Rights.xml", rights, root)
        groups.setdefault("Role", []).append(role["name"]); written.append("Roles/" + role["name"])

    # подсистемы
    for s in spec.get("subsystems", []):
        write(f"Subsystems/{s['name']}.xml", gen_subsystem(s), root)
        groups.setdefault("Subsystem", []).append(s["name"]); written.append("Subsystems/" + s["name"])

    # элементы стиля
    for s in spec.get("styleItems", []):
        write(f"StyleItems/{s['name']}.xml", gen_style_item(s), root)
        groups.setdefault("StyleItem", []).append(s["name"]); written.append("StyleItems/" + s["name"])

    # язык и корень
    write("Languages/Русский.xml", gen_language(), root)
    groups.setdefault("Language", []).append("Русский")
    write("Configuration.xml", gen_configuration(spec["configuration"], groups), root)
    written.append("Configuration.xml")

    print("записано файлов: %d" % (len(written) + 1))
    for w in written:
        print("  ", w)


# ---------------------------------------------------------------- матрица прав
def build_rights(spec):
    """Права ролей. Набор прав зависит от типа объекта: у перечисления есть только View,
    у подсистемы — только View, у константы — Read/Update/View/Edit. Несуществующее право
    в Rights.xml не даст загрузить конфигурацию, поэтому наборы фиксированы по типу.

    Ключевые договорённости (модель данных команды):
    - пользовательские роли не получают права изменения истории согласования (только чтение);
    - прямой правки согласованного документа нет ни у одной роли — это проверяет модуль объекта;
    - пароль SMTP читают и меняют только «Администратор видов» и «ПолныеПрава».
    """
    OBJECT_RIGHTS = {
        "Catalog": ["Read", "Insert", "Update", "Delete", "View", "Edit",
                    "InteractiveInsert", "InteractiveSetDeletionMark",
                    "InteractiveClearDeletionMark", "InteractiveDelete",
                    "InteractiveDeleteMarked", "InputByString"],
        "ChartOfCharacteristicTypes": ["Read", "Insert", "Update", "Delete", "View", "Edit",
                                       "InteractiveInsert", "InteractiveSetDeletionMark",
                                       "InteractiveClearDeletionMark", "InteractiveDelete",
                                       "InteractiveDeleteMarked", "InputByString"],
        "Document": ["Read", "Insert", "Update", "Delete", "View", "Edit",
                     "InteractiveInsert", "InteractiveSetDeletionMark",
                     "InteractiveClearDeletionMark", "InteractiveDelete",
                     "InteractiveDeleteMarked", "InputByString"],
        "InformationRegister": ["Read", "Update", "View", "Edit"],
        "Constant": ["Read", "Update", "View", "Edit"],
        "Enum": ["View"],
        "Subsystem": ["View"],
    }
    READ_COMPLEX = {
        "Catalog": ["Read", "View", "InputByString"],
        "ChartOfCharacteristicTypes": ["Read", "View", "InputByString"],
        "Document": ["Read", "View", "InputByString"],
        "InformationRegister": ["Read", "View"],
        "Constant": [],
        "Enum": ["View"],
        "Subsystem": ["View"],
    }

    objects = []
    for kind, key in (("Enum", "enums"), ("Catalog", "catalogs"),
                      ("ChartOfCharacteristicTypes", "chartOfCharacteristicTypes"),
                      ("Document", "documents"), ("InformationRegister", "informationRegisters"),
                      ("Constant", "constants"), ("Subsystem", "subsystems")):
        for item in spec.get(key, []):
            objects.append((kind, item["name"]))

    def rights(kind, name, mode):
        key = kind
        if mode == "full":
            return OBJECT_RIGHTS[key]
        if mode == "read":
            return READ_COMPLEX[key]
        return [r for r in READ_COMPLEX[key] if r in ("Read", "View")]

    roles = {r["name"]: [] for r in spec.get("roles", [])}

    for kind, name in objects:
        obj = f"{kind}.{name}"
        roles["ПолныеПрава"].append((obj, rights(kind, name, "full")))

        if (kind, name) in (("Catalog", "ВидыДокументов"), ("Catalog", "Сотрудники"),
                            ("Catalog", "ЗначенияПолей"),
                            ("ChartOfCharacteristicTypes", "ПоляДокументов")):
            roles["АдминистраторВидов"].append((obj, rights(kind, name, "full")))
        elif kind == "Constant":
            roles["АдминистраторВидов"].append((obj, rights(kind, name, "full")))
        else:
            roles["АдминистраторВидов"].append((obj, rights(kind, name, "read")))

        # Сотрудник: создаёт и правит свои документы в статусах «Черновик»/«На доработке»
        if (kind, name) == ("Document", "ДокументСЭД"):
            roles["Сотрудник"].append((obj, ["Read", "Insert", "Update", "View", "Edit",
                                             "InteractiveInsert", "InputByString"]))
        else:
            roles["Сотрудник"].append((obj, rights(kind, name, "plain")))

        # Согласующий: видит документы и историю, статус меняет движок согласования
        if (kind, name) == ("InformationRegister", "ИсторияСогласования"):
            roles["Согласующий"].append((obj, ["Read", "View"]))
        else:
            roles["Согласующий"].append((obj, rights(kind, name, "plain")))

    roles["ПолныеПрава"].append(("Configuration", ["Administration", "DataAdministration",
                                                  "UpdateDataHistory", "OpenExtDataSources"]))
    return roles


if __name__ == "__main__":
    main()
