# Исправление прокси для FFmpeg в Windows

## Что выявлено

Процесс `ffmpeg.exe`, запускаемый через `yt_essential.engine.Session.download`, не получал `-http_proxy`, хотя yt-dlp использовал HTTP(S)-прокси из системного окружения. В CLI-тесте с `--downloader-args "ffmpeg_i:-http_proxy <proxy>"` обрезка успешно завершилась, а в процессе ESSENTIAL аргумент отсутствовал.

## Что меняется

Windows compatibility layer оборачивает `Session.base_opts()` и определяет HTTP(S)-прокси через `urllib.request.getproxies()`. Если найден HTTP(S)-прокси, он добавляется в параметр yt-dlp:

```python
'external_downloader_args': {
    'ffmpeg_i': ['-http_proxy', proxy_url],
}
```

Передаются только аргументы для входного FFmpeg downloader (`ffmpeg_i`). Логика выбора форматов, именования файлов, плейлистов и диапазонов не меняется. SOCKS-прокси намеренно не преобразуется в `-http_proxy`, поскольку это другой протокол.

## Установка исправления без полной переустановки

1. В первом окне PowerShell, где выполняется зависший API-тест, нажмите `Ctrl+C` один раз и дождитесь приглашения `PS>`.
2. Распакуйте архив исправления.
3. Откройте PowerShell в распакованной папке `yt-dlp-essential-windows`.
4. Выполните:

```powershell
Set-ExecutionPolicy -Scope Process Bypass -Force
.\windows\apply-proxy-fix.ps1
```

5. Закройте старые окна ESSENTIAL/PowerShell и откройте новое.
6. Запустите ESSENTIAL и повторите скачивание того же фрагмента `0:00–3:00`.

## Проверка передачи прокси

Во время загрузки из второго окна PowerShell можно безопасно проверить только наличие аргумента (не печатая URL прокси или URL потока):

```powershell
$ff = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -ieq 'ffmpeg.exe' } |
    Sort-Object CreationDate -Descending |
    Select-Object -First 1

if ($ff) {
    [pscustomobject]@{
        PID = $ff.ProcessId
        HasHttpProxy = ([string]$ff.CommandLine -match '(?i)-http_proxy')
        Has180SecondLimit = ([string]$ff.CommandLine -match '(?i)-t\s+180')
    }
} else {
    'ffmpeg.exe пока не запущен'
}
```

Ожидается `HasHttpProxy = True` для HTTP(S)-прокси в системе и `Has180SecondLimit = True` для теста на 3 минуты.

> Важно: архив содержит исправление Windows compatibility layer. Проверку нужно завершить на реальной Windows. Если в системе прокси отсутствует или используется SOCKS, этот патч не добавляет поддержку такого типа прокси.
