# Результаты проверок Windows-адаптации

Дата: 22 ноября 2026 года (повторная проверка после исправления WinGet).

## Среда

- ОС: Linux x86_64 (контейнер разработки), не Windows.
- Python: 3.13.5.
- PowerShell 5.1/7 (`powershell.exe`/`pwsh`): не установлен.
- Сетевой checkout оригинального GitHub-репозитория из контейнера: заблокирован DNS; исходные файлы основных модулей были изучены через GitHub raw/web-доступ.

## Выполненные проверки

| Проверка | Результат |
|---|---|
| `python -m compileall -q windows tests` | PASS |
| `python -m unittest discover -s tests -v` | PASS — 15/15 |
| Проверка аргументов `winget install` в установщике | PASS — `--upgrade` удалён, указан `--source winget` |
| Проверка Windows-путей с кириллицей/пробелами | PASS — helper tests |
| Проверка клавиатурных scan codes, Enter/Esc/Ctrl+C/Ctrl+D | PASS — helper tests |
| Обнаружение браузеров по стандартным Windows-путям | PASS — helper tests |
| Включение `windowsfilenames` | PASS — helper test |
| Перенаправление команды Finder в Explorer | PASS — mocked subprocess test |
| Замена подсказок Homebrew на WinGet | PASS — helper test |
| Статическая проверка скобок и строк `.ps1` | PASS |
| Проверка UTF-8 BOM у PowerShell-скриптов и CRLF | PASS |

## Что не подтверждено

- Разбор `.ps1` настоящим PowerShell parser и запуск PowerShell 5.1/7.
- Выполнение `winget install` и установка Python/FFmpeg/Deno на Windows.
- Работа `msvcrt`, Win32 console APIs, ANSI VT и полноэкранного меню на Windows Terminal/Conhost.
- Реальные загрузки yt-dlp/gallery-dl, cookies extraction и output paths на Windows.
- Полный upstream-набор тестов: отсутствует полный checkout оригинального репозитория в среде проверки.

## Вывод

Доступные статические и Python unit-проверки пройдены. Результат не следует трактовать как подтверждённое тестирование на Windows. Перед повседневным использованием следует выполнить сценарии из раздела 5 `WINDOWS_AUDIT_RU.md` на Windows 10/11 x64.


## Исправление WinGet (22.11.2026)

В `windows/install.ps1` удалён неподдерживаемый аргумент `--upgrade` из команды `winget install`. Для WinGet установка и обновление — разные команды; прежний аргумент вызывал `0x8A150002` (`INVALID_CL_ARGUMENTS`). К установке добавлен явный источник `winget`. Добавлены два unit-теста на корректность аргументов установщика и FFmpeg package ID. Сама установка WinGet на Windows в этой среде по-прежнему не выполнялась.

## Дополнительное исправление прокси для FFmpeg

После анализа Windows-процесса `ffmpeg.exe` выявлено отсутствие `-http_proxy` при запуске через Python API. В Windows compatibility layer добавлена передача HTTP(S)-прокси в `external_downloader_args['ffmpeg_i']`.

Дополнительные проверки: выбор HTTPS-прокси с приоритетом, fallback на HTTP, игнорирование SOCKS-прокси, поведение без прокси, установка/замена аргумента `-http_proxy`.

**Итог после добавления тестов:** 21/21 unit-тестов PASS; `compileall` PASS. Проверка выполнялась на Linux. Реальный повторный запуск ESSENTIAL/FFmpeg после установки патча должен быть выполнен на целевой Windows-машине.
