#!/usr/bin/env python3
"""Создать отдельную тестовую ИБ, загрузить выгрузку и проверить её в установленной 1С."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def result_of_step(exit_code, result_file):
    if exit_code != 0:
        return False, None, f'Процесс завершился с кодом {exit_code}'
    if not result_file.exists():
        return False, None, '1С не создала файл /DumpResult; успех не подтверждён'
    try:
        result = int(result_file.read_text(encoding='utf-8-sig').strip())
    except (ValueError, UnicodeError):
        return False, None, 'Некорректный файл /DumpResult; успех не подтверждён'
    return result == 0, result, 'Операция завершена' if result == 0 else f'1С вернула код {result}'


def commands(platform, source, workspace):
    base = workspace / 'base'
    operations = [
        ('create', ['CREATEINFOBASE', f'File="{base}";']),
        ('load', ['DESIGNER', '/F', str(base), '/LoadConfigFromFiles', str(source)]),
        ('update', ['DESIGNER', '/F', str(base), '/UpdateDBCfg']),
        ('check', ['DESIGNER', '/F', str(base), '/CheckConfig', '-ThinClient', '-WebClient', '-Server']),
    ]
    return [(name, [platform, *operation, '/Out', str(workspace / f'{name}.log'),
                    '/DumpResult', str(workspace / f'{name}.result'), '/DisableStartupDialogs'])
            for name, operation in operations]


def prepare_workspace(requested):
    if requested is None:
        return Path(tempfile.mkdtemp(prefix='docroute-platform-'))
    workspace = requested.resolve()
    if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
        raise ValueError('Каталог проверки должен быть новым или пустым. Рабочая ИБ не используется.')
    if '"' in str(workspace):
        raise ValueError('В пути каталога проверки не допускается двойная кавычка')
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def execute(command, stdout_file, timeout):
    with stdout_file.open('wb') as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=os.name == 'posix')
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Останавливается только созданный этой проверкой процесс и его группа.
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', help='Путь к 1cv8t/1cv8/1cv8.exe')
    parser.add_argument('--source', type=Path, default=ROOT / 'ДокМаршрут')
    parser.add_argument('--workspace', type=Path, help='Новый или пустой каталог; существующая ИБ не принимается')
    parser.add_argument('--timeout', type=int, default=300, help='Таймаут одного этапа в секундах')
    parser.add_argument('--prepare-only', action='store_true', help='Записать план команд без запуска платформы')
    args = parser.parse_args(argv)
    if not (args.source / 'Configuration.xml').is_file():
        parser.error('В --source отсутствует Configuration.xml')
    if args.timeout <= 0:
        parser.error('--timeout должен быть положительным')
    platform = args.platform or shutil.which('1cv8t') or shutil.which('1cv8')
    if not platform and not args.prepare_only:
        parser.error('Платформа не найдена. Укажите --platform или используйте --prepare-only')
    if args.platform and not args.prepare_only:
        platform = shutil.which(args.platform)
        if not platform:
            parser.error('Указанный исполняемый файл платформы не найден')
    try:
        workspace = prepare_workspace(args.workspace)
    except ValueError as error:
        parser.error(str(error))
    report_file = workspace / 'report.json'
    plan = commands(platform or '<path-to-1cv8t>', args.source.resolve(), workspace)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'source': str(args.source.resolve()),
              'workspace': str(workspace), 'status': 'prepared_not_run', 'steps':
              [{'name': name, 'command': command, 'status': 'not_run'} for name, command in plan]}

    def save_report():
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    save_report()
    print(f'Отчёт: {report_file}', flush=True)
    if args.prepare_only:
        print('Команды подготовлены. Платформа не запускалась; проверка 1С не выполнена.')
        return 0
    report['status'] = 'running'
    try:
        for step, (name, command) in zip(report['steps'], plan):
            print(f'1С: {name}', flush=True)
            step['status'] = 'running'
            save_report()
            try:
                exit_code = execute(command, workspace / f'{name}.stdout.log', args.timeout)
            except (subprocess.TimeoutExpired, OSError) as error:
                step.update(status='failed', message=str(error))
                report['status'] = 'failed'
                return 1
            success, native_code, message = result_of_step(exit_code, workspace / f'{name}.result')
            step.update(status='passed' if success else 'failed', exit_code=exit_code,
                        native_code=native_code, message=message)
            save_report()
            if not success:
                print(message, flush=True)
                report['status'] = 'failed'
                return 1
        report['status'] = 'platform_checks_passed'
        print('Загрузка и проверка конфигурации пройдены. Ручные сценарии интерфейса ещё не проверены.')
        return 0
    finally:
        save_report()


if __name__ == '__main__':
    raise SystemExit(main())
