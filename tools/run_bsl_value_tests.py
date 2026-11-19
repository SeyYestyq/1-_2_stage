#!/usr/bin/env python3
"""Исполнение чистых функций из исходников через OneScript; это не тест платформы 1С."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'ДокМаршрут'
SOURCES = {
    'CommonModules/ДинамическиеФормы/Ext/Module.bsl':
        ['СтрокаЗначенияРедактора', 'ДатаИзСтрокиПоля', 'ЗначениеЭтоЧисло', 'ЗначениеЭтоДата'],
    'Documents/ДокументСЭД/Forms/ФормаДокумента/Ext/Form/Module.bsl': ['ИмяФайлаДляСкачивания'],
}
TESTS = r'''
Процедура Равно(Факт, Ожидание, Название)
    Если Факт <> Ожидание Тогда
        ВызватьИсключение Название + ": ожидалось [" + Строка(Ожидание) + "] получено [" + Строка(Факт) + "]";
    КонецЕсли;
    Сообщить("PASS: " + Название);
КонецПроцедуры

Равно(СтрокаЗначенияРедактора(0), "0", "нулевая сумма сохраняется");
Равно(СтрокаЗначенияРедактора(1234.56789), "1234.56789", "дробная часть сохраняется");
Равно(СтрокаЗначенияРедактора(-125.75), "-125.75", "отрицательное число сохраняется");
Равно(СтрокаЗначенияРедактора("  значение  "), "  значение  ", "строка не обрезается");
Равно(СтрокаЗначенияРедактора(Дата(2026, 11, 19)), "19.11.2026", "дата форматируется");
Равно(СтрокаЗначенияРедактора(Дата(1, 1, 1)), "", "пустая дата остаётся пустой");
Равно(ДатаИзСтрокиПоля("29.02.2024"), Дата(2024, 2, 29), "високосная дата читается");
Равно(ЗначениеЭтоДата("31.02.2026"), Ложь, "несуществующая дата отклоняется");
Равно(ЗначениеЭтоДата("ошибка"), Ложь, "текст вместо даты отклоняется");
Равно(ЗначениеЭтоЧисло("1 234.50"), Истина, "число с группировкой принимается");
Равно(ЗначениеЭтоЧисло("12x"), Ложь, "текст вместо числа отклоняется");
Равно(ИмяФайлаДляСкачивания("  Д-1/Договор: ""Тест"".html  "), "Д-1_Договор_ _Тест_.html", "имя HTML файла очищается");
Равно(ИмяФайлаДляСкачивания("C:\tmp\out.pdf"), "C__tmp_out.pdf", "разделители Windows очищаются");
Равно(ИмяФайлаДляСкачивания(""), "Печатная_форма.pdf", "пустое имя заменяется");
Равно(ИмяФайлаДляСкачивания("a" + Символы.ВК + Символы.ПС + "b.pdf"), "a__b.pdf", "переводы строк удаляются из имени");
Сообщить("15 проверок функций BSL пройдены. OneScript не заменяет тесты управляемых форм 1С.");
'''


def source_functions():
    functions = []
    for relative, names in SOURCES.items():
        text = (ROOT / relative).read_text(encoding='utf-8-sig')
        for name in names:
            found = re.search(r'Функция\s+' + re.escape(name) + r'\([^\n]*\).*?КонецФункции', text, re.S)
            if found is None:
                raise ValueError(f'Нет функции {name} в {relative}')
            functions.append(found.group(0))
    return '\n\n'.join(functions)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--oscript', default='oscript', help='oscript либо путь к oscript.dll для запуска через dotnet')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='docroute-values-') as directory:
        script = Path(directory) / 'values.os'
        script.write_text(source_functions() + '\n' + TESTS, encoding='utf-8-sig')
        command = ['dotnet', args.oscript] if args.oscript.endswith('.dll') else [args.oscript]
        return subprocess.run([*command, str(script)], check=False).returncode


if __name__ == '__main__':
    raise SystemExit(main())
