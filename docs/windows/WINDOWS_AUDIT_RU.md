# Технический аудит и план переноса yt-dlp-essential на Windows

## 1. Архитектура оригинального проекта

По доступному исходному дереву и README оригинал — Python 3.10+ CLI-приложение (версия upstream на момент проверки — 1.1.0), которое использует официальные библиотеки `yt-dlp` и `gallery-dl`, не встраивая их код.

| Модуль | Ответственность | Задействование ОС |
|---|---|---|
| `yt_essential/cli.py` | Entry point и диалог загрузки, выбор режима, качества, фрагментов, папки и cookies | `Path`, вызов Finder только на macOS |
| `menu.py` | Главное меню, settings, update/version | Полноэкранное меню через функции `ui` |
| `ui.py` | ANSI-интерфейс, клавиши, ввод, spinner/progress | `termios`, `tty`, `select`, `os.read` POSIX |
| `engine.py` | `Plan`, формирование yt-dlp opts, probe/download, browser list | Браузеры искались по macOS `.app`; `shutil.which` для ffmpeg/deno/node |
| `gallery.py` | Запуск `python -m gallery_dl`, подсчёт элементов и загрузка | `subprocess` с argv list, `Path` |
| `formats.py` | Преобразование форматов yt-dlp в меню качества | Независим от ОС |
| `parsing.py` | Парсинг диапазонов, диапазонов playlist items, форматирование | Независим от ОС |
| `updates.py` | Проверка PyPI/GitHub и `pip install --upgrade` текущего окружения | `sys.executable -m pip`, urllib |
| `config.py` | JSON config и папка загрузок | Unix-путь `~/.config`/XDG по умолчанию |
| `install.sh` | Bootstrap, venv, pip, system packages, команда PATH, uninstall | Bash, Homebrew, POSIX paths и chmod/rm/mkdir |
| `pyproject.toml` | Python package metadata, `essn` entry point | Python packaging, кроссплатформенно |
| `tests/` | Unit tests parsing/engine; test workflow | CI в upstream: macOS + Ubuntu, не Windows |

Исходный README указывает на поддержку видео/аудио, playlists/channels/sections, time ranges, cookies-from-browser, gallery-dl (Instagram/Pinterest), сохранённой папки, Ask folder и package update. Это функциональные требования при переносе.

## 2. Найденные несовместимости

1. **Терминал:** в `ui.py` `interactive()` возвращает false, если нет `termios`. В Windows модуль отсутствует. Следовательно, оригинал отходит к текстовому меню и теряет полноэкранную клавиатурную навигацию. Простое удаление import-error не исправляет read-key/line-editor, так как исходные функции используют `termios.tcgetattr`, `tty.setcbreak`, `select.select` на stdin и `os.read`.
2. **Браузеры:** `engine.installed_browsers()` проверяет `/Applications/*.app` и `~/Applications/*.app`; на Windows найденные браузеры не определятся. В исходном `BROWSERS` Safari ошибочно является первым выбором, хотя он не является актуальным Windows-браузером.
3. **Конфигурация:** `config_dir()` по умолчанию направляет настройки в `~/.config/yt-essential`, а на Windows ожидается `%APPDATA%\yt-essential`. Сама JSON-запись UTF-8 и атомарная замена файла через `os.replace` кроссплатформенны.
4. **Установка:** `install.sh` зависит от Bash, Homebrew, `rm`, `mkdir`, `$VENV/bin/python` и POSIX bin dir. `brew install ffmpeg` и автоматическая установка Python/JS runtime неприменимы на Windows.
5. **JS runtime:** `engine.py` автоматически указывает `js_runtimes={'node': {}}`, если нет Deno, но не устанавливает runtime. Для современной поддержки YouTube нужен совместимый runtime; рекомендован Deno (минимум 2.3.0 по текущей EJS-инструкции yt-dlp). `yt-dlp[default]` устанавливает `yt-dlp-ejs`.
6. **FFmpeg:** оригинал корректно проверяет наличие FFmpeg через `shutil.which`, но его macOS-инструкция для установки неприменима. Отсутствие ffmpeg препятствует merge, audio postprocessing и фрагментам, где нужен перекод.
7. **Кодировки:** исходные JSON config и внутренние файлы используют UTF-8; внешние PowerShell 5.1 и Python subprocess нуждаются в явном UTF-8 режиме для устойчивого вывода кириллицы.
8. **Пути и аргументы:** `pathlib` и вызовы `subprocess` с массивами аргументов в `gallery.py` являются хорошей кроссплатформенной основой; строки не нужно вручную склеивать или экранировать через shell.
9. **CI:** upstream `.github/workflows/tests.yml` запускает тесты только на macOS и Ubuntu; Windows матрицы и проверки PowerShell installer нет.

## 3. Реализация Windows-слоя

- `windows/yt_essential_windows.py` — небольшая compatibility layer. Перенаправляет config/download locations, реализует Windows console input через `msvcrt`, включает VT ANSI mode, выявляет Windows браузеры по стандартным путям, принудительно задаёт UTF-8, пишет runtime log, задаёт `windowsfilenames=True` для защиты от зарезервированных символов Windows и переводит открытие Finder-папки в Explorer. Затем вызывает исходный `yt_essential.cli.main()` без замены логики загрузки.
- `windows/install.ps1` — Windows 10 1709+/11 x64 installer; находит Python x64 3.10+, при наличии WinGet ставит Python 3.14, FFmpeg Shared и Deno (команда `winget install` без неподдерживаемого `--upgrade`, с явным `--source winget`), создаёт `venv`, скачивает upstream source zip (или принимает `-SourcePath`), добавляет compatibility module и ставит оригинальный пакет через pip.
- `windows/run.ps1`, `run.bat`, `bin/essn.cmd` — запуск из PowerShell/CMD, UTF-8 environment и безопасное quoting аргументов.
- `windows/update.ps1` — повторная установка актуального upstream source и upgrade Python package.
- `windows/uninstall.ps1` — удаление app/venv и очистка добавленной PATH-записи, сохраняя конфигурацию и downloads.
- `windows/doctor.ps1` — диагностика Python, FFmpeg, ffprobe, Deno, WinGet и установленных модулей.
- `tests/test_windows_compat.py` — проверки Windows-specific path logic, кириллицы, пробелов, key mappings, браузерного обнаружения, Windows-safe filenames и Finder → Explorer.

## 4. Проверки и ограничения результата

Установщик по умолчанию получает текущий `main` zip-архивом без фиксации commit SHA. Это позволяет получать обновления проекта без Git, но не обеспечивает воспроизводимость версий и не является проверкой подлинности исходного архива. Для проверяемой/фиксированной версии следует передавать `-SourcePath` на локальный checkout с нужным commit.

Локальная рабочая среда — Linux x86_64, Python 3.13.5; `pwsh`/Windows PowerShell не обнаружены. Прямое `git clone` и загрузка файлов из GitHub в контейнере не сработали из-за DNS-сетевой блокировки. При этом исходные страницы/файлы основных модулей, README, pyproject, upstream tests и workflow были просмотрены через доступ к GitHub raw pages.

Провести в этой среде реально возможно:

- `compileall` для Python compatibility module и тестов;
- 15 unit-тестов: пути/кодировки, пробелы/кириллица, key mappings, Ctrl+D, браузеры, safe filenames, Finder → Explorer и WinGet-подсказки;
- проверка комплектности scripts и связей между установкой/запуском/обновлением/удалением;
- статическая проверка PowerShell-блоков: сбалансированность скобок, закрытие строк и UTF-8 BOM; это не PowerShell parser/runtime test.

Нельзя честно заявить, что уже выполнены:

- запуск `.ps1` в Windows PowerShell 5.1/PowerShell 7;
- фактическая установка WinGet пакетов;
- поиск Windows Python launcher/`PATH` на реальной Windows машине;
- реальная работа `msvcrt` и ANSI VT console navigation;
- browser cookies extraction из Chrome/Edge/Firefox/Brave;
- сквозная загрузка видео/плейлиста/фрагмента на Windows;
- запись файлов в кириллический путь и путь с пробелами из yt-dlp/gallery-dl;
- полное выполнение upstream test suite, так как checkout исходного репозитория недоступен в этой сессии.

## 5. Ручная проверка на Windows 10/11

1. Запустить `windows\install.ps1` без административного PowerShell; проверить лог в `%APPDATA%\yt-essential\logs`.
2. В новом Windows Terminal выполнить `essn`, проверить `↑/↓`, Enter, Escape, Q, U, V.
3. Создать каталог `C:\Users\<user>\Видео тест\Папка с пробелами`; выбрать его как папку загрузки.
4. Выполнить `essn https://www.youtube.com/watch?v=<public-test-video>`; проверить video+audio, audio formats, MP4/MKV/WebM, quality presets, fragment and playlist selection.
5. Проверить `ffmpeg -version`, `ffprobe -version`, `deno --version` (Deno 2.3+); выполнить `doctor.ps1`.
6. Проверить cookies extraction с Edge/Chrome/Firefox/Brave для тестового контента с законным доступом.
7. Выполнить загрузку публичной картинки/поддерживаемого Instagram/Pinterest URL через gallery-dl.
8. Выполнить menu Update и `windows\update.ps1`; после обновления проверить, что `windows_compat.py` остался на месте.
9. Проверить `windows\uninstall.ps1`; удостовериться, что конфиг и загруженные файлы сохранены.

## 6. Ссылки на первичные источники

- Original repository: https://github.com/icloud-storage/yt-dlp-essential
- Upstream README: https://github.com/icloud-storage/yt-dlp-essential#readme
- Upstream workflow: https://github.com/icloud-storage/yt-dlp-essential/blob/main/.github/workflows/tests.yml
- yt-dlp EJS runtime setup: https://github.com/yt-dlp/yt-dlp/wiki/ejs
- Deno installation / WinGet: https://docs.deno.com/runtime/getting_started/installation/
- FFmpeg Windows packages (Gyan): https://www.gyan.dev/ffmpeg/builds/
- WinGet docs: https://learn.microsoft.com/windows/package-manager/winget/


### Дополнительное исправление WinGet от 22.11.2026

Первоначальный `Invoke-WinGetInstall` передавал `--upgrade` команде `winget install`, что не входит в набор поддерживаемых аргументов `install` и соответствует `APPINSTALLER_CLI_ERROR_INVALID_CL_ARGUMENTS` (`0x8A150002`). Исправлено: параметр удалён, для устранения неоднозначности задан `--source winget`. Добавлены unit-тесты на аргументы и идентификатор `Gyan.FFmpeg.Shared`. Проверка фактической установки остаётся Windows-only.

## Дополнение: прокси для внешнего FFmpeg downloader

Реальная Windows-диагностика показала, что при вызове через `Session.download` дочерний `ffmpeg.exe` не получал `-http_proxy`, тогда как явная передача через CLI `--downloader-args "ffmpeg_i:-http_proxy <proxy>"` позволяла обработать трёхминутный диапазон. Windows compatibility layer теперь находит HTTP(S)-proxy через `urllib.request.getproxies()` и добавляет его как `external_downloader_args = {"ffmpeg_i": ["-http_proxy", proxy]}` в `Session.base_opts()`. SOCKS proxy не преобразуется в HTTP proxy. На Windows требуется подтвердить повторную работу исходного ESSENTIAL UI с этим исправлением.
