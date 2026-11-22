# План публикации Windows-поддержки в icloud-storage/yt-dlp-essential

## Что уже подтверждено на Windows 11 пользователя

- Установка Windows bootstrap и создание venv.
- Обнаружение Python x64, FFmpeg/ffprobe и Deno.
- Обычная загрузка видео с аудио.
- Обработка трёхминутного фрагмента через yt-dlp CLI.
- Передача HTTP(S)-proxy дочернему FFmpeg после установки ProxyFix.
- Успешная загрузка временного фрагмента через ESSENTIAL после применения ProxyFix.
- Выявлено ограничение извлечения cookies Chrome через DPAPI; Firefox extractor прочитал cookies DB, но тестовый профиль не был авторизован в Instagram, поэтому 401 не является подтверждением ошибки Firefox.

Это пользовательские smoke-тесты на одной Windows 11 машине, а не полная матрица Windows 10/11.

## Перед публикацией

1. Создать ветку `feature/windows-support` от свежего `main`.
2. Слить содержимое `windows/` из адаптации в корень репозитория.
3. Добавить `tests/test_windows_compat.py` в существующую папку `tests/`, не перезаписывая оригинальные тесты.
4. Обновить `README.md` (подготовленный файл из этого пакета) и сохранить macOS-инструкции.
5. Обновить `pyproject.toml`: description/keywords/classifiers должны указывать macOS + Windows. Не менять минимальную версию Python без проверки совместимости зависимостей.
6. Заменить `.github/workflows/tests.yml` предложенным workflow из этого пакета: оставить macOS/Ubuntu, добавить Windows runner, FFmpeg setup и реальный PowerShell parser для всех `.ps1`.
7. Убедиться, что в коммит не попали `.venv/`, `__pycache__/`, `.pyc`, cookies, config, пользовательские логи и скачанные медиа.
8. Запустить полный unittest suite на macOS, Ubuntu и Windows CI.
9. На реальных Windows 10 и 11 выполнить ручной smoke-test (см. ниже).
10. Только после зелёного CI обновить `__version__` и `pyproject.toml` одной и той же версией (например, `1.2.0`, если это следующий minor-релиз), слить PR и создать тег `v1.2.0`/GitHub Release.

## Обязательные Windows smoke-тесты

- Windows 10 x64 (минимальная версия, заявленная инсталлятором) и Windows 11 x64.
- Windows PowerShell 5.1 и PowerShell 7.
- Чистая установка через `windows/install.ps1`; затем `doctor.ps1`.
- Запуск `essn`, клавиатура, меню и прогресс.
- Видео+аудио, audio-only, H.264/MP4, MKV/WebM, временной диапазон, плейлист.
- Загрузка без прокси и с HTTP(S) proxy; проверить `-http_proxy` в командной строке дочернего FFmpeg (не печатая URL media/cookies).
- Ctrl+C: дочерние процессы корректно завершаются и временные файлы обрабатываются ожидаемо.
- Путь с кириллицей, пробелами, `&`, скобками и длинным именем файла.
- `gallery-dl` на публичном контенте; authenticated tests только с собственной авторизованной сессией.
- Cookies: Chrome/Edge/Firefox; проверить случай незашифровываемых Chrome cookies и показать правильное диагностическое сообщение, не заявлять автоматическую поддержку App-Bound Encryption без подтверждения.
- Повторный запуск installer, update, сохранение config/downloads и uninstall.

## Рекомендуемая последовательность Git

```powershell
git clone https://github.com/icloud-storage/yt-dlp-essential.git
cd yt-dlp-essential
git switch -c feature/windows-support
```

Скопировать файлы из integration patch в соответствующие пути. Затем:

```powershell
git status --short
git diff --check
git diff -- README.md pyproject.toml .github/workflows/tests.yml
python -m unittest discover -s tests -t . -v
```

Проверить PowerShell syntax локально:

```powershell
$files = Get-ChildItem .\windows -Filter *.ps1 -File
foreach ($file in $files) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $file.FullName, [ref]$tokens, [ref]$errors
    ) | Out-Null
    if ($errors) { $errors | Format-List; throw "Syntax error: $($file.Name)" }
}
```

Затем commit и push ветки:

```powershell
git add README.md pyproject.toml .github/workflows/tests.yml windows tests/test_windows_compat.py WINDOWS_AUDIT_RU.md TEST_RESULTS_RU.md PROXY_FIX_RU.md
git commit -m "Add Windows 10/11 support"
git push -u origin feature/windows-support
```

На GitHub открыть Pull Request `feature/windows-support` → `main`. Не делать прямой push в `main`, пока CI и ручной smoke-test не пройдены.

## После merge

- Обновить `yt_essential/__init__.py` и `pyproject.toml` одной версией.
- Создать annotated tag и GitHub Release.
- Прикрепить zip исходного репозитория (или release archive) как удобный Windows-дистрибутив; source ZIP из GitHub уже должен включать `windows/`.
- Обновить GitHub About description и topics: `yt-dlp`, `gallery-dl`, `downloader`, `cli`, `python`, `macos`, `windows`.
- Проверить, что README и Release notes не обещают поддержку Chrome cookies/Windows 10, пока эти тесты не подтверждены.

## Важная архитектурная заметка

Текущий installer берёт upstream source из локального checkout (если запущен в корне репозитория с `pyproject.toml`) либо скачивает `main.zip`, затем устанавливает Python package и копирует `windows/yt_essential_windows.py` в установленный пакет как `yt_essential/windows_compat.py`. Поэтому для работы опубликованного bootstrap папка `windows/` должна быть в репозитории и содержать актуальные скрипты. Обновление `windows/update.ps1` использует сохранённую копию `windows/install.ps1`, поэтому обновления Windows-слоя также должны попадать в `main`.
