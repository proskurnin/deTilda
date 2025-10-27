# Detilda

## Описание продукта

Detilda — офлайн-инструмент автоматизации, который приводит в порядок экспортированные проекты [Tilda.cc](https://tilda.cc) перед развёртыванием на стороннем хостинге. Программа распаковывает архив сайта, нормализует имена файлов и структуру каталогов, удаляет фирменные артефакты Tilda, чинит внутренние ссылки и формирует итоговый отчёт. Конвейер Detilda работает локально, не требует подключения к Tilda и позволяет выпускать само-хостимые сборки, готовые к публикации на любом CDN или файловом сервере.

### Архитектура и ключевые возможности

- **Основной конвейер (`main.py`, `core/pipeline.py`)** — управляет стадиями обработки: распаковка архива, нормализация ассетов, очистка сервисных файлов, генерация форм, правка ссылок, удаление скриптов и финальная проверка ссылок. Настройки стадий подаются через единый YAML-конфиг.
- **Контекст проекта (`core/project.py`, `core/config_loader.py`, `core/configuration.py`)** — описывает рабочие пути, лениво загружает конфигурацию, проверяет корректность параметров и передаёт их в остальные модули.
- **Распаковка и подготовка (`core/archive.py`, `core/logger.py`)** — извлекает входной ZIP-архив во временную директорию, ведёт журнал выполнения и аккуратно очищает рабочее окружение при ошибках.
- **Нормализация ассетов (`core/assets.py`)** — приводит имена файлов к нижнему регистру, скачивает удалённые ресурсы, копирует обязательные шаблоны из `resources/`, удаляет служебные файлы Tilda и сохраняет карту переименований для следующих стадий.
- **Очистка текстов (`core/cleaners.py`, `core/page404.py`)** — удаляет из `robots.txt`, `readme.txt`, `404.html` и других текстовых файлов рекламные и служебные блоки Tilda, заменяя их на готовые шаблоны.
- **Работа с формами (`core/forms.py`, `core/inject.py`, `resources/send_email.php`, `resources/js/form-handler.js`)** — генерирует PHP-обработчик и фронтенд-скрипт, внедряет подключение скрипта в HTML, подставляя адрес получателя, заданный пользователем.
- **Правка ссылок и маршрутов (`core/refs.py`, `core/htaccess.py`)** — обновляет ссылки в HTML/CSS/JS/JSON, учитывает переименованные файлы, собирает маршруты из `.htaccess`, проверяет совпадение регистров и сообщает о нерешённых путях.
- **Гигиена скриптов (`core/script_cleaner.py`)** — удаляет встроенные скрипты аналитики, обработки форм и другие элементы, которые не нужны в итоговой сборке.
- **Проверка ссылок и отчётность (`core/checker.py`, `core/report.py`)** — проходит по итоговому проекту, находит битые ссылки, формирует промежуточные и финальные отчёты, синхронизируемые с настройками `manifest.json`.
- **Конфигурация (`config/config.yaml`, `manifest.json`)** — задаёт правила переименования, списки запрещённых файлов, параметры вставки скриптов и флаги включённых функций. Файл `manifest.json` дополнительно хранит версию и описание сборки.
- **Инструменты и тесты (`tools/sync_manifest.py`, `core/build_sync.py`, `tests/`)** — CLI-утилиты для синхронизации манифеста и pytest-наборы, проверяющие корректность нормализации регистров и обновления манифеста.

### Типовой рабочий процесс

1. Пользователь помещает экспортированный архив Tilda в каталог `_workdir/` (создаётся автоматически при первом запуске).
2. Запускает `python main.py` и указывает имя архива и e-mail получателя для форм.
3. Detilda распаковывает архив, последовательно выполняет все стадии и пишет подробный лог в консоль и `logs/`.
4. В конце конвейера готовая сборка остаётся в `_workdir/<имя-архива>/` вместе с отчётами и картой переименований.

### Модули по каталогам

- `core/`
  - `archive.py` — отвечает за распаковку архивов и подготовку рабочей директории.
  - `assets.py` — нормализует структуру ассетов, переименовывает и скачивает ресурсы.
  - `build_sync.py` — синхронизирует сведения о сборке с `manifest.json`.
  - `checker.py` — запускает проверку ссылок и фиксирует ошибки.
  - `cleaners.py` — удаляет шаблонные артефакты Tilda из текстовых файлов.
  - `configuration.py` — предоставляет типизированные обёртки над YAML-конфигом.
  - `config_loader.py` — лениво читает `config/config.yaml` и кэширует секции.
  - `forms.py` — создаёт обработчик почтовых форм и подключаемые ресурсы.
  - `htaccess.py` — парсит `.htaccess`, извлекает маршруты и редиректы.
  - `inject.py` — вставляет ссылки на фронтенд-скрипты обработчика форм.
  - `logger.py` — настраивает формат логов, уровни и запись в файл.
  - `page404.py` — нормализует страницу 404 и удаляет лишние блоки.
  - `pipeline.py` — описывает стадии конвейера и последовательность выполнения.
  - `project.py` — хранит пути проекта и предоставляет доступ к конфигурации.
  - `refs.py` — переписывает ссылки на файлы с учётом переименований и маршрутов.
  - `report.py` — формирует текстовые отчёты и сводки по конвейеру.
  - `script_cleaner.py` — удаляет запрещённые JavaScript- и HTML-вставки.
- `config/`
  - `config.yaml` — центральный файл с правилами переименования, очистки и копирования ресурсов.
- `resources/`
  - `favicon.ico`, `send_email.php`, `js/form-handler.js` — статические шаблоны, которые копируются в итоговый проект при необходимости.
- `tests/`
  - Pytest-сценарии, проверяющие синхронизацию манифеста и корректность нормализации регистров.
- `tools/`
  - `sync_manifest.py` — CLI-утилита для обновления `manifest.json` на основе собранного архива.

### Для разработчиков

- Минимальная версия Python — 3.10 (проект проверяется на 3.11).
- Зависимости: `PyYAML` для чтения конфигурации, `pytest` для тестов.
- Запуск тестов: `pytest` из корня репозитория.
- При изменениях сборки рекомендуется запускать `python tools/sync_manifest.py` для обновления `manifest.json`.

## Product description

Detilda is an offline automation tool that tidies up exported [Tilda.cc](https://tilda.cc) projects before they are deployed on external hosting. The program extracts the site archive, normalizes filenames and folder structure, removes Tilda-specific artefacts, fixes internal links, and produces a final report. Detilda runs locally, requires no connection to Tilda, and delivers self-hosted builds ready to publish on any CDN or file server.

### Architecture and key capabilities

- **Main pipeline (`main.py`, `core/pipeline.py`)** – orchestrates the processing stages: archive extraction, asset normalization, service file cleanup, form generation, link rewriting, script removal, and final link checking. Stage settings are provided via a single YAML configuration.
- **Project context (`core/project.py`, `core/config_loader.py`, `core/configuration.py`)** – defines working paths, lazily loads configuration data, validates parameters, and passes them to the other modules.
- **Extraction and setup (`core/archive.py`, `core/logger.py`)** – unpacks the input ZIP archive into a temporary directory, logs progress, and gracefully cleans up the workspace on errors.
- **Asset normalization (`core/assets.py`)** – converts filenames to lowercase, downloads remote resources, copies mandatory templates from `resources/`, removes Tilda service files, and stores a rename map for the following stages.
- **Text cleanup (`core/cleaners.py`, `core/page404.py`)** – strips promotional and service blocks from `robots.txt`, `readme.txt`, `404.html`, and other text files, replacing them with ready-made templates.
- **Form handling (`core/forms.py`, `core/inject.py`, `resources/send_email.php`, `resources/js/form-handler.js`)** – generates a PHP handler and frontend script, injects the script reference into HTML, and inserts the user-provided recipient address.
- **Link and route repair (`core/refs.py`, `core/htaccess.py`)** – updates links across HTML/CSS/JS/JSON, respects renamed files, collects routes from `.htaccess`, enforces case matches, and reports unresolved paths.
- **Script hygiene (`core/script_cleaner.py`)** – removes embedded analytics, form scripts, and other fragments that should not ship with the final package.
- **Link checking and reporting (`core/checker.py`, `core/report.py`)** – scans the processed project for broken links, compiles interim and final reports, and aligns output with `manifest.json` settings.
- **Configuration (`config/config.yaml`, `manifest.json`)** – defines rename rules, disallowed files, script injection parameters, and feature flags. `manifest.json` additionally stores the build version and description.
- **Tooling and tests (`tools/sync_manifest.py`, `core/build_sync.py`, `tests/`)** – CLI helpers for manifest synchronization and pytest suites that verify case normalization and manifest updates.

### Typical workflow

1. Place the exported Tilda archive into the `_workdir/` directory (created automatically on the first run).
2. Run `python main.py` and supply the archive name and the recipient e-mail for forms.
3. Detilda extracts the archive, executes every stage in sequence, and writes detailed logs to the console and `logs/`.
4. The finished build remains in `_workdir/<archive-name>/` along with reports and the rename map.

### Modules by directory

- `core/`
  - `archive.py` – handles archive extraction and workspace preparation.
  - `assets.py` – normalizes asset structure, renames files, and downloads resources.
  - `build_sync.py` – synchronizes build metadata with `manifest.json`.
  - `checker.py` – runs the link checker and records issues.
  - `cleaners.py` – removes Tilda boilerplate from text files.
  - `configuration.py` – provides typed wrappers around the YAML configuration.
  - `config_loader.py` – lazily reads `config/config.yaml` and caches sections.
  - `forms.py` – creates the mail form handler and bundled assets.
  - `htaccess.py` – parses `.htaccess`, extracting routes and redirects.
  - `inject.py` – injects frontend handler script references into HTML.
  - `logger.py` – configures log format, levels, and file output.
  - `page404.py` – normalizes the 404 page and removes extra blocks.
  - `pipeline.py` – declares pipeline stages and their execution order.
  - `project.py` – stores project paths and exposes configuration accessors.
  - `refs.py` – rewrites links to account for renamed files and routes.
  - `report.py` – produces textual reports and pipeline summaries.
  - `script_cleaner.py` – removes forbidden JavaScript and HTML snippets.
- `config/`
  - `config.yaml` – central rule set for renaming, cleaning, and resource copying.
- `resources/`
  - `favicon.ico`, `send_email.php`, `js/form-handler.js` – static templates copied into the final project when required.
- `tests/`
  - Pytest scenarios that validate manifest synchronization and case normalization.
- `tools/`
  - `sync_manifest.py` – CLI utility for updating `manifest.json` from a packaged archive.

### For developers

- Minimum Python version: 3.10 (validated on 3.11).
- Dependencies: `PyYAML` for configuration parsing, `pytest` for tests.
- Run the test suite with `pytest` from the repository root.
- After build changes, run `python tools/sync_manifest.py` to refresh `manifest.json`.
