# deTilda

[![Tests](https://github.com/proskurnin/deTilda/actions/workflows/tests.yml/badge.svg)](https://github.com/proskurnin/deTilda/actions/workflows/tests.yml)

Офлайн-инструмент для подготовки сайтов, экспортированных с [Tilda.cc](https://tilda.cc),
к развёртыванию на собственном хостинге.

[**English version**](#detilda-english)

---

## Описание

deTilda распаковывает ZIP-архив с экспортированным сайтом Tilda и автоматически:

- удаляет служебные файлы и скрипты Tilda (статистика, формы, аналитика)
- скачивает удалённые ресурсы (CSS, JS, изображения, шрифты Google) локально
- переименовывает файлы и обновляет все ссылки в проекте
- генерирует свой обработчик форм (`send_email.php` + `form-handler.js`)
- проверяет, что в финальной сборке не осталось ссылок на Tilda
- формирует подробный отчёт со статистикой

Работает локально, не требует подключения к Tilda. Результат — готовая к публикации
на любом хостинге папка с сайтом.

## Быстрый старт

```bash
# 1. Положите архив сайта в _workdir/
mv ~/Downloads/project12345.zip _workdir/

# 2. Запустите обработку
python main.py
# Введите имя архива: project12345.zip

# 3. Готовый сайт окажется в _workdir/project12345/
# 4. Лог и rename_map будут в logs/project12345_*.log/.json
```

Можно обработать несколько архивов за один запуск, перечислив их через запятую.

## Архитектура: 18-шаговый конвейер

`core/pipeline.py` оркестрирует следующие шаги:

| # | Модуль | Что делает |
|---|---|---|
| 1 | `archive` | Распаковка ZIP в `_workdir/<имя>/` |
| 2 | `assets` | Переименование файлов, скачивание удалённых ресурсов, удаление мусора Tilda, нормализация регистра |
| 3 | `page404` | Очистка `404.html` от ссылок Tilda и скриптов |
| 4 | `cleaners` | Очистка `robots.txt`, `readme.txt` от упоминаний Tilda |
| 5 | `forms` | Копирование `send_email.php` и `form-handler.js` из `resources/` |
| 6 | `inject` | Внедрение скриптов в HTML (form-handler перед `</body>`, GA config/loader перед `</head>`) |
| 7 | `font_substitute` | Замена TildaSans/AidaSans на нейтральный шрифт из конфигурации |
| 8 | `fonts_localizer` | Локализация Google Fonts (скачивание `.woff2`, инлайн `@import`) — GDPR-friendly |
| 9 | `refs` | Обновление всех ссылок в HTML/CSS/JS по rename_map и маршрутам `.htaccess` |
| 10 | `cdn_localizer` | Скачивание и переписывание оставшихся CDN-ссылок на локальные файлы |
| 11 | `browser_runtime_assets` | Открытие страниц в Chromium и докачка runtime CDN-ресурсов |
| 12 | `cdn_cleanup` | Удаление неразрешённых CDN-подключений после попытки локализации |
| 13 | `images` | Промоут `data-original` → `src` для lazyload изображений |
| 14 | `script_cleaner` | Удаление встроенных скриптов Tilda из HTML |
| 15 | `namespace_rewrite` | Финальный согласованный rewrite `til*` → `ai*`, `t-*` → `ai-*`, `data-til*-*` → `data-ai*-*` |
| 16 | `forms_check` | Проверка, что у каждой формы подключён `form-handler.js` |
| 17 | `html_prettify` | Форматирование HTML с правильными отступами |
| 18 | `checker` / `tilda-remnants` | Проверка внутренних ссылок и финальная очистка остаточных упоминаний Tilda |

После всех шагов `report.generate_final_report` пишет финальный отчёт.

## Структура проекта

```
deTilda/
├── main.py                    # Точка входа CLI
├── manifest.json              # Версия, описание, пути
├── config/config.yaml         # Все правила обработки
├── core/                      # Модули конвейера
│   ├── pipeline.py            # Оркестратор 18 шагов
│   ├── project.py             # Контекст проекта (paths + config + rename_map)
│   ├── archive.py             # Шаг 1: распаковка ZIP
│   ├── assets.py              # Шаг 2: ассеты + rename_map
│   ├── page404.py             # Шаг 3: очистка 404.html
│   ├── cleaners.py            # Шаг 4: robots.txt, readme.txt
│   ├── forms.py               # Шаг 5: копирование обработчиков форм
│   ├── inject.py              # Шаг 6: внедрение скриптов
│   ├── font_substitute.py     # Шаг 7: замена TildaSans/AidaSans
│   ├── fonts_localizer.py     # Шаг 8: Google Fonts → локально
│   ├── refs.py                # Шаг 9: обновление ссылок (главный для корректности)
│   ├── cdn_localizer.py       # Шаги 10, 12: CDN-ссылки → локальные ассеты
│   ├── browser_assets.py      # Шаг 11: browser-runtime докачка CDN-ассетов
│   ├── htaccess.py            # Парсинг .htaccess + стратегии для битых маршрутов
│   ├── images.py              # Шаг 13: lazyload-изображения
│   ├── script_cleaner.py      # Шаг 14: удаление скриптов Tilda
│   ├── namespace_rewriter.py  # Шаг 15: финальный Aida namespace rewrite
│   ├── checker.py             # Шаги 16, 18: проверки и tilda-remnants
│   ├── html_prettify.py       # Шаг 17: форматирование HTML
│   ├── report.py              # Промежуточный и финальный отчёты
│   ├── downloader.py          # Общий HTTP-клиент с SSL-fallback
│   ├── runtime_scripts.py     # Защита runtime-скриптов от удаления
│   ├── schemas.py             # Pydantic-модели для config.yaml
│   ├── pydantic_compat.py     # Минимальная замена pydantic (без зависимостей)
│   ├── config_loader.py       # Загрузка config.yaml в типизированные объекты
│   ├── utils.py               # Файловые хелперы (safe_read, list_files и др.)
│   ├── logger.py              # Логирование (синглтон с записью в файл)
│   └── version.py             # Чтение версии и метаданных из manifest.json
├── resources/                 # Шаблоны для копирования в проект
│   ├── send_email.php         # Универсальный обработчик форм
│   ├── js/form-handler.js     # Фронтенд для форм
│   ├── ga-config.js           # GA4 Measurement ID для готового сайта
│   ├── ga.js                  # Загрузчик Google Analytics
│   └── favicon.ico            # Дефолтная иконка
├── tools/
│   └── bump_version.py        # SemVer bump + git тег
├── tests/                     # 295 unit-тестов через pytest
└── logs/                      # Логи и rename_map для каждого проекта
```

## Конфигурация

### `manifest.json` — паспорт приложения

Хранит версию (SemVer), пути, метаданные и build-настройки:

```json
{
  "name": "deTilda",
  "version": "5.2.0",
  "release_date": "2026-05-01",
  "description": "Автоматическая подготовка Tilda-экспортов...",
  "license": "MIT",
  "python": ">=3.10",
  "features": {"reports": true},
  "paths": {"workdir": "_workdir", "logs": "logs", "config": "config"},
  "build": {"package_name": "detilda_5.2.0.zip"}
}
```

### `config/config.yaml` — правила обработки

Основные секции:
- **`patterns`** — regex для поиска ссылок, правила замен (`til→ai`), список расширений
- **`images`** — какие файлы удалять, какие ссылки заменять на 1px-плейсхолдер
- **`service_files`** — какие скрипты удалять, что копировать из `resources/`
- **`font_substitute`** — замена TildaSans/AidaSans и Google Fonts import
- **`forms`** — получатели тестовых писем и параметры обработчика форм
- **`web`** — лимиты загрузки, очереди, TTL задач и rate limiting

Все поля типизированы через Pydantic-схемы (`core/schemas.py`).

## Универсальный обработчик форм

`resources/send_email.php` работает без настройки:
- определяет получателя автоматически: `info@<домен>` (определяется по `SERVER_NAME`)
- в dev-окружении (`localhost`, `*.local`) использует тестовый адрес
- в prod ставит BCC на страховочные адреса
- автоматически переключается между TEST/PROD по env-переменной `SENDMAIL_MODE`

Достаточно один раз сгенерировать на этапе deTilda, на любом домене будет работать корректно.

## Для разработчиков

### Версионирование

Проект использует [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).
Версия живёт в `manifest.json` и читается оттуда всеми модулями.

Поднять версию:

```bash
python tools/bump_version.py patch   # 5.2.0 → 5.2.1 (баг-фикс)
python tools/bump_version.py minor   # 5.2.0 → 5.3.0 (новая фича)
python tools/bump_version.py major   # 5.2.0 → 6.0.0 (breaking change)
```

Скрипт обновляет `version`, `release_date`, `build.package_name` и создаёт git-тег.

### Тесты

```bash
python -m pytest tests/ -q
```

Покрытие — 295 unit-тестов. Каждый модуль шага конвейера имеет свой тест-файл.
Тесты используют типизированные fake-loader'ы для проверки модулей в изоляции.

### Runtime-ассеты из браузера

После статической CDN-локализации pipeline автоматически делает best-effort
browser-runtime проход: открывает HTML-страницы в Chromium, ловит запросы к
`static.tildacdn.com` / `static.aidacdn.com`, докачивает найденные файлы и
повторно запускает статическую перепись CDN-ссылок. Настройки живут в
`service_files.pipeline_stages.browser_runtime_assets`.

Если Playwright/Chromium недоступен, шаг логируется как пропущенный, а основной
offline-first pipeline продолжает работу. Для ручной диагностики того же класса
runtime-запросов можно запустить:

```bash
python tools/audit_browser_assets.py _workdir/project5641940/page27969817.html
```

В Docker-образ Chromium ставится автоматически через `python -m playwright install --with-deps chromium`.

### Зависимости

- Python 3.10+ (тестируется на 3.13)
- `PyYAML` — чтение конфига
- `pytest` — тесты
- `playwright` + Chromium — автоматическая browser-runtime докачка CDN-ассетов

Pydantic **не требуется** — `core/pydantic_compat.py` реализует нужное подмножество.
Это сделано чтобы не тянуть тяжёлую зависимость в PyInstaller-сборку.

### Структура тестов

```
tests/
├── test_audit_browser_assets.py    # Browser-аудит runtime CDN-запросов
├── test_api.py                    # Публичный API process_archive
├── test_assets_main.py            # Главный flow rename_and_cleanup_assets
├── test_assets_runtime_scripts.py # Защита runtime-скриптов
├── test_archive.py                # ZIP-распаковка
├── test_browser_assets.py         # Автоматическая browser-runtime докачка CDN-ассетов
├── test_case_normalization.py     # Нормализация регистра имён
├── test_cdn_localizer.py          # Локализация и очистка CDN-ссылок
├── test_checker_forms.py          # Проверка форм
├── test_checker_links.py          # Финальная проверка внутренних ссылок
├── test_checker_remnants.py       # Финальная проверка tilda-остатков
├── test_cleaners_compat.py        # Очистка robots.txt/readme.txt
├── test_font_substitute.py        # Замена TildaSans/AidaSans
├── test_fonts_localizer.py        # Google Fonts локализация
├── test_forms.py                  # Копирование send_email.php
├── test_htaccess.py               # Парсинг .htaccess + стратегии
├── test_html_prettify.py          # Форматирование HTML
├── test_images_fix.py             # lazyload-изображения
├── test_inject.py                 # Внедрение скриптов
├── test_logger.py                 # Изоляция логгера
├── test_namespace_rewriter.py     # Финальный Aida namespace rewrite
├── test_packer.py                 # Упаковка результата в ZIP
├── test_page404.py                # Очистка 404.html
├── test_pipeline_summary.py       # Сводка пайплайна
├── test_pipeline_e2e.py           # Smoke-тест полного pipeline
├── test_process_params.py         # Параметры обработки
├── test_project.py                # ProjectContext
├── test_pydantic_compat.py        # Наша замена pydantic
├── test_refs_anchor_links.py      # Якорные ссылки
├── test_refs_main.py              # Главный flow update_all_refs_in_project
├── test_refs_replace_rules.py     # Применение replace_rules
├── test_report.py                 # Генерация отчётов
├── test_runtime_scripts.py        # Детекция media-маркеров
├── test_script_cleaner_tilda_media.py  # Защита скриптов от удаления
├── test_smoke_test_form.py        # CLI smoke-тест формы после деплоя
├── test_utils.py                  # Файловые хелперы
├── test_web_api.py                # FastAPI endpoints
├── test_web_jobs.py               # Хранилище и восстановление web-задач
└── test_version.py                # Метаданные из manifest.json
```

---

## deTilda (English)

Offline tool for preparing [Tilda.cc](https://tilda.cc) site exports for self-hosting.

### Description

deTilda extracts a Tilda site ZIP archive and automatically:

- removes Tilda service files and scripts (analytics, forms, tracking)
- downloads remote resources (CSS, JS, images, Google Fonts) locally
- renames files and updates all links in the project
- generates a custom form handler (`send_email.php` + `form-handler.js`)
- checks that no Tilda references remain in the final build
- produces a detailed statistics report

Runs locally, no Tilda connection required. The result is a deployment-ready
site folder for any hosting.

### Quick start

```bash
# 1. Place the site archive into _workdir/
mv ~/Downloads/project12345.zip _workdir/

# 2. Run processing
python main.py
# Enter archive name: project12345.zip

# 3. Finished site appears in _workdir/project12345/
# 4. Logs and rename_map go to logs/project12345_*.log/.json
```

Multiple archives can be processed in one run by listing them comma-separated.

### Pipeline (18 steps)

`core/pipeline.py` orchestrates these steps:

| # | Module | Purpose |
|---|---|---|
| 1 | `archive` | Extract ZIP into `_workdir/<name>/` |
| 2 | `assets` | Rename files, download remote resources, remove Tilda junk, normalize case |
| 3 | `page404` | Clean Tilda links and scripts from `404.html` |
| 4 | `cleaners` | Clean Tilda mentions from `robots.txt`, `readme.txt` |
| 5 | `forms` | Copy `send_email.php` and `form-handler.js` from `resources/` |
| 6 | `inject` | Inject scripts into HTML (form-handler before `</body>`, GA config/loader before `</head>`) |
| 7 | `font_substitute` | Replace TildaSans/AidaSans with the configured neutral font |
| 8 | `fonts_localizer` | Localize Google Fonts (download `.woff2`, inline `@import`) — GDPR-friendly |
| 9 | `refs` | Update all links in HTML/CSS/JS via rename_map and `.htaccess` routes |
| 10 | `cdn_localizer` | Download remaining CDN URLs and rewrite them to local files |
| 11 | `browser_runtime_assets` | Open pages in Chromium and download runtime CDN assets |
| 12 | `cdn_cleanup` | Remove unresolved CDN references after localization attempts |
| 13 | `images` | Promote `data-original` → `src` for lazyload images |
| 14 | `script_cleaner` | Remove Tilda inline scripts from HTML |
| 15 | `namespace_rewrite` | Final consistent rewrite of `til*` → `ai*`, `t-*` → `ai-*`, `data-til*-*` → `data-ai*-*` |
| 16 | `forms_check` | Verify every form has `form-handler.js` attached |
| 17 | `html_prettify` | Format HTML with proper indentation |
| 18 | `checker` / `tilda-remnants` | Validate internal links and clean remaining Tilda references |

### For developers

- **Versioning**: [SemVer](https://semver.org/) — bump via `python tools/bump_version.py {patch,minor,major}`
- **Tests**: `python -m pytest tests/ -q` (295 unit tests)
- **Dependencies**: Python 3.10+, `PyYAML`, `pytest`, `playwright`. Pydantic **not required** — `core/pydantic_compat.py` provides a minimal replacement for PyInstaller compatibility.
