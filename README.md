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

## Архитектура: 14-шаговый конвейер

`core/pipeline.py` оркестрирует следующие шаги:

| # | Модуль | Что делает |
|---|---|---|
| 1 | `archive` | Распаковка ZIP в `_workdir/<имя>/` |
| 2 | `assets` | Переименование файлов, скачивание удалённых ресурсов, удаление мусора Tilda, нормализация регистра |
| 3 | `page404` | Очистка `404.html` от ссылок Tilda и скриптов |
| 4 | `cleaners` | Очистка `robots.txt`, `readme.txt` от упоминаний Tilda |
| 5 | `forms` | Копирование `send_email.php` и `form-handler.js` из `resources/` |
| 6 | `inject` | Внедрение скриптов в HTML (form-handler перед `</body>`, GA config/loader перед `</head>`) |
| 7 | `fonts_localizer` | Локализация Google Fonts (скачивание `.woff2`, инлайн `@import`) — GDPR-friendly |
| 8 | `refs` | Обновление всех ссылок в HTML/CSS/JS по rename_map и маршрутам `.htaccess` |
| 9 | `images` | Промоут `data-original` → `src` для lazyload изображений |
| 10 | `script_cleaner` | Удаление встроенных скриптов Tilda из HTML |
| 11 | `forms_check` | Проверка, что у каждой формы подключён `form-handler.js` |
| 12 | `html_prettify` | Форматирование HTML с правильными отступами |
| 13 | `checker` | Проверка всех внутренних ссылок, отчёт о битых |
| 14 | `tilda-remnants` | Финальная проверка: ищет и исправляет остаточные упоминания Tilda |

После всех шагов `report.generate_final_report` пишет финальный отчёт.

## Структура проекта

```
deTilda/
├── main.py                    # Точка входа CLI
├── manifest.json              # Версия, описание, пути
├── config/config.yaml         # Все правила обработки
├── core/                      # Модули конвейера
│   ├── pipeline.py            # Оркестратор 14 шагов
│   ├── project.py             # Контекст проекта (paths + config + rename_map)
│   ├── archive.py             # Шаг 1: распаковка ZIP
│   ├── assets.py              # Шаг 2: ассеты + rename_map
│   ├── page404.py             # Шаг 3: очистка 404.html
│   ├── cleaners.py            # Шаг 4: robots.txt, readme.txt
│   ├── forms.py               # Шаг 5: копирование обработчиков форм
│   ├── inject.py              # Шаг 6: внедрение скриптов
│   ├── fonts_localizer.py     # Шаг 7: Google Fonts → локально
│   ├── refs.py                # Шаг 8: обновление ссылок (главный для корректности)
│   ├── htaccess.py            # Парсинг .htaccess + стратегии для битых маршрутов
│   ├── images.py              # Шаг 9: lazyload-изображения
│   ├── script_cleaner.py      # Шаг 10: удаление скриптов Tilda
│   ├── checker.py             # Шаги 11, 13, 14: проверки и tilda-remnants
│   ├── html_prettify.py       # Шаг 12: форматирование HTML
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
├── tests/                     # 160 unit-тестов через pytest
└── logs/                      # Логи и rename_map для каждого проекта
```

## Конфигурация

### `manifest.json` — паспорт приложения

Хранит версию (SemVer), пути, метаданные и build-настройки:

```json
{
  "name": "deTilda",
  "version": "4.8.1",
  "release_date": "2026-04-25",
  "description": "Автоматическая подготовка Tilda-экспортов...",
  "license": "MIT",
  "python": ">=3.10",
  "features": {"reports": true},
  "paths": {"workdir": "_workdir", "logs": "logs", "config": "config"},
  "build": {"package_name": "detilda_4.8.1.zip"}
}
```

### `config/config.yaml` — правила обработки

Три секции:
- **`patterns`** — regex для поиска ссылок, правила замен (`til→ai`), список расширений
- **`images`** — какие файлы удалять, какие ссылки заменять на 1px-плейсхолдер
- **`service_files`** — какие скрипты удалять, что копировать из `resources/`

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
python tools/bump_version.py patch   # 4.8.1 → 4.8.2 (баг-фикс)
python tools/bump_version.py minor   # 4.8.1 → 4.9.0 (новая фича)
python tools/bump_version.py major   # 4.8.1 → 5.0.0 (breaking change)
```

Скрипт обновляет `version`, `release_date`, `build.package_name` и создаёт git-тег.

### Тесты

```bash
python -m pytest tests/ -q
```

Покрытие — 160 unit-тестов. Каждый модуль шага конвейера имеет свой тест-файл.
Тесты используют типизированные fake-loader'ы для проверки модулей в изоляции.

### Зависимости

- Python 3.10+ (тестируется на 3.13)
- `PyYAML` — чтение конфига
- `pytest` — тесты

Pydantic **не требуется** — `core/pydantic_compat.py` реализует нужное подмножество.
Это сделано чтобы не тянуть тяжёлую зависимость в PyInstaller-сборку.

### Структура тестов

```
tests/
├── test_assets_main.py            # Главный flow rename_and_cleanup_assets
├── test_assets_runtime_scripts.py # Защита runtime-скриптов
├── test_archive.py                # ZIP-распаковка
├── test_case_normalization.py     # Нормализация регистра имён
├── test_checker_forms.py          # Проверка форм
├── test_checker_remnants.py       # Финальная проверка tilda-остатков
├── test_cleaners_compat.py        # Очистка robots.txt/readme.txt
├── test_fonts_localizer.py        # Google Fonts локализация
├── test_forms.py                  # Копирование send_email.php
├── test_htaccess.py               # Парсинг .htaccess + стратегии
├── test_html_prettify.py          # Форматирование HTML
├── test_images_fix.py             # lazyload-изображения
├── test_inject.py                 # Внедрение скриптов
├── test_page404.py                # Очистка 404.html
├── test_pipeline_summary.py       # Сводка пайплайна
├── test_project.py                # ProjectContext
├── test_pydantic_compat.py        # Наша замена pydantic
├── test_refs_anchor_links.py      # Якорные ссылки
├── test_refs_main.py              # Главный flow update_all_refs_in_project
├── test_refs_replace_rules.py     # Применение replace_rules
├── test_report.py                 # Генерация отчётов
├── test_runtime_scripts.py        # Детекция media-маркеров
├── test_script_cleaner_tilda_media.py  # Защита скриптов от удаления
├── test_utils.py                  # Файловые хелперы
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

### Pipeline (14 steps)

`core/pipeline.py` orchestrates these steps:

| # | Module | Purpose |
|---|---|---|
| 1 | `archive` | Extract ZIP into `_workdir/<name>/` |
| 2 | `assets` | Rename files, download remote resources, remove Tilda junk, normalize case |
| 3 | `page404` | Clean Tilda links and scripts from `404.html` |
| 4 | `cleaners` | Clean Tilda mentions from `robots.txt`, `readme.txt` |
| 5 | `forms` | Copy `send_email.php` and `form-handler.js` from `resources/` |
| 6 | `inject` | Inject scripts into HTML (form-handler before `</body>`, GA config/loader before `</head>`) |
| 7 | `fonts_localizer` | Localize Google Fonts (download `.woff2`, inline `@import`) — GDPR-friendly |
| 8 | `refs` | Update all links in HTML/CSS/JS via rename_map and `.htaccess` routes |
| 9 | `images` | Promote `data-original` → `src` for lazyload images |
| 10 | `script_cleaner` | Remove Tilda inline scripts from HTML |
| 11 | `forms_check` | Verify every form has `form-handler.js` attached |
| 12 | `html_prettify` | Format HTML with proper indentation |
| 13 | `checker` | Validate all internal links, report broken ones |
| 14 | `tilda-remnants` | Final check: find and fix remaining Tilda references |

### For developers

- **Versioning**: [SemVer](https://semver.org/) — bump via `python tools/bump_version.py {patch,minor,major}`
- **Tests**: `python -m pytest tests/ -q` (160 unit tests)
- **Dependencies**: Python 3.10+, `PyYAML`, `pytest`. Pydantic **not required** — `core/pydantic_compat.py` provides a minimal replacement for PyInstaller compatibility.
