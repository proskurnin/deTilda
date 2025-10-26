# Detilda

Offline automation tool that cleans up, normalizes, and repackages exported [Tilda.cc](https://tilda.cc) projects. Detilda standardizes asset names, removes vendor remnants, patches internal links, and prepares self-hosted archives ready for deployment without the original Tilda infrastructure.

## Key capabilities

- **Archive-aware pipeline** – unpacks the provided project archive, runs every stage, and records a detailed summary for each processed site. 【F:main.py†L36-L118】
- **Asset normalization** – renames resources, enforces lowercase filenames, downloads remote assets, and updates references across HTML, CSS, JS, and JSON. 【F:core/assets.py†L1-L156】【F:core/assets.py†L314-L651】
- **Text cleanup** – strips Tilda-specific snippets (robots.txt, README, generic leftovers) from service files. 【F:core/cleaners.py†L1-L108】
- **Form handling** – generates `send_email.php`, injects handler scripts, and protects required assets referenced in forms. 【F:core/forms.py†L1-L82】【F:core/inject.py†L1-L58】
- **Reference repair** – rewrites links and routes, including `.htaccess` aliases, fixing case mismatches and reporting unresolved entries. 【F:core/refs.py†L1-L200】【F:core/htaccess.py†L1-L120】
- **Script hygiene** – removes bundled analytics/forms scripts that should not ship with the final package. 【F:core/script_cleaner.py†L1-L160】
- **Link checker & reporting** – scans the cleaned project for broken links and emits a final summary with statistics in the log output. 【F:core/checker.py†L1-L138】【F:core/report.py†L44-L107】

## Project layout

```
core/        Core pipeline modules
config/      Shared YAML configuration for the cleanup stages
resources/   Static templates (e.g., for generated PHP form handler)
tests/       Pytest suites covering assets, manifest sync, and normalization logic
```

The pipeline is orchestrated from `main.py`, which wires the stages together and handles logging and CLI prompts. 【F:main.py†L10-L155】

## Requirements

- Python 3.10 or newer (the project is tested on Python 3.11). 【F:manifest.json†L2-L27】【7c8896†L1-L9】
- [PyYAML](https://pyyaml.org/) for parsing `config/config.yaml`. 【F:core/config_loader.py†L1-L47】

Optional tools:

- `pytest` for running the automated test suite. 【F:tests/test_case_normalization.py†L1-L58】

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt  # or pip install pyyaml pytest
```

If you maintain your own dependency management, ensure `pyyaml` (and `pytest` for development) are available in the environment.

## Usage

1. Export your site from Tilda and copy the resulting `.zip` archive into the `_workdir/` directory (created automatically on the first run). 【F:main.py†L124-L152】
2. Run the CLI entrypoint:
   ```bash
   python main.py
   ```
3. Enter one or more archive names when prompted (comma-separated) and provide the recipient e-mail for generated forms (defaults to `r@prororo.com`). 【F:main.py†L132-L152】
4. Monitor the console or `logs/` folder for progress. The tool reports renamed assets, cleaned files, fixed links, warnings, and total runtime at the end of each archive. 【F:main.py†L108-L118】

The processed project is left inside `_workdir/<archive-name>/` ready for publishing on any static hosting provider.

## Configuration

Detilda is driven by the unified YAML file at `config/config.yaml`. Key sections include:

- `patterns`: regexes and replacement rules applied to links, README/robots cleanup, and `.htaccess` parsing. 【F:config/config.yaml†L1-L64】
- `images`: guidance for removing or replacing vendor images/icons left in exports. 【F:config/config.yaml†L65-L93】
- `service_files`: advanced pipeline settings, including remote asset downloads, scripts to delete, protected files, form injection, link checker options, and optional case-normalization stage. 【F:config/config.yaml†L94-L160】

Adjust these sections to reflect your project-specific conventions or additional cleanup rules.

## Подробное описание файлов

### Корневой уровень

- `README.md`
  - **Назначение:** основная документация и руководство по запуску Detilda. 【F:README.md†L1-L116】
  - **Зависимости и конфиг:** не использует конфигурацию, но описывает ключевые секции `config/config.yaml`.
  - **Отключение через config:** не применимо.
- `main.py`
  - **Назначение:** CLI-входная точка, поочередно запускающая распаковку архива, обработку ассетов, очистку, генерацию форм, обновление ссылок, удаление скриптов, проверку ссылок и финальные отчёты. 【F:main.py†L10-L156】
  - **Зависимости и конфиг:** загружает `manifest.json` для версии/рабочей папки и инициализирует `ConfigLoader`, передавая его в модули, которые читают `config/config.yaml`. 【F:main.py†L24-L126】
  - **Отключение через config:** порядок шагов задаётся кодом; отдельные стадии можно отключить лишь удалив вызов в `main.py` либо настроив соответствующие секции конфига, если модуль поддерживает флаги (см. ниже).
- `manifest.json`
  - **Назначение:** метаданные релиза, список включаемых возможностей и путей по умолчанию. 【F:manifest.json†L1-L40】
  - **Зависимости и конфиг:** используется `main.py` (путь `paths.workdir`) и модуль отчётов (флаг `features.reports`). 【F:main.py†L123-L152】【F:core/report.py†L9-L55】
  - **Отключение через config:** отдельные фичи отключаются значениями `features.*`; например, `reports: false` выключает генерацию отчётов без правки кода.
- `config/config.yaml`
  - **Назначение:** единый YAML, управляющий правилами переименования ассетов, очистки текстов, обработкой изображений, загрузкой удалённых ресурсов и пр. 【F:config/config.yaml†L1-L160】
  - **Зависимости и конфиг:** читается `ConfigLoader`/`ProjectContext`; большинство модулей (`assets`, `cleaners`, `inject`, `refs`, `script_cleaner`, `checker`) забирают свои параметры отсюда. 【F:core/config_loader.py†L10-L66】【F:core/project.py†L10-L47】
  - **Отключение через config:** секция `service_files.pipeline_stages.normalize_case.enabled` отключает нормализацию регистра; очистка и удаление скриптов прекращаются при очистке соответствующих списков.

### Конфигурация и утилиты

- `core/config_loader.py`
  - **Назначение:** лениво загружает `config.yaml` и предоставляет методы `patterns()`, `images()`, `service_files()`. 【F:core/config_loader.py†L10-L58】
  - **Зависимости и конфиг:** зависит от `yaml` и `core.logger` для сообщений об ошибках; путь к конфигу вычисляется относительно репозитория. 【F:core/config_loader.py†L1-L34】
  - **Отключение через config:** не отключается; чтобы выключить чтение конфигурации, требуется менять код.
- `core/configuration.py`
  - **Назначение:** альтернативные dataclass-обёртки (`DetildaConfig`, `ConfigSection`) для типизированного доступа к конфигу. 【F:core/configuration.py†L19-L121】
  - **Зависимости и конфиг:** также читает `config/config.yaml` с помощью `yaml`; выводит предупреждения через `core.logger`. 【F:core/configuration.py†L7-L69】
  - **Отключение через config:** не используется по умолчанию; отключение не требуется.
- `core/utils.py`
  - **Назначение:** общие вспомогательные функции (чтение/запись файлов, копирование ресурсов, обход директорий, загрузка `manifest.json`, форматирование времени). 【F:core/utils.py†L1-L118】
  - **Зависимости и конфиг:** опирается на `core.logger` для логирования; параметры не читаются из конфигурации.
  - **Отключение через config:** не управляется конфигом.
- `core/logger.py`
  - **Назначение:** единая система логирования с файлами журнала и контекстными менеджерами для этапов пайплайна. 【F:core/logger.py†L1-L102】
  - **Зависимости и конфиг:** автоматически создаёт каталог `logs` рядом с проектом; настройки формата задаются самим модулем.
  - **Отключение через config:** нет; чтобы отключить логирование, придётся модифицировать код.
- `core/project.py`
  - **Назначение:** `ProjectContext` хранит путь проекта, ссылку на репозиторий и экземпляр `ConfigLoader`, а также карту переименований. 【F:core/project.py†L1-L47】
  - **Зависимости и конфиг:** определяет корень репозитория и подготавливает конфиг для остальных модулей. 【F:core/project.py†L10-L43】
  - **Отключение через config:** не отключается; контекст нужен пайплайну `core/pipeline.py`.

### Оркестрация пайплайна

- `core/pipeline.py`
  - **Назначение:** объектно-ориентированный вариант пайплайна (`DetildaPipeline`), который использует `ProjectContext` и по модульным блокам выполняет те же стадии, что и CLI. 【F:core/pipeline.py†L1-L107】
  - **Зависимости и конфиг:** каждый блок читает настройки через `ProjectContext.config_loader`, то есть через `config.yaml`. 【F:core/pipeline.py†L32-L71】
  - **Отключение через config:** отдельные стадии управляются теми же флагами, что и в `main.py` (см. описания модулей); глобального переключателя в конфиге нет.
- `core/archive.py`
  - **Назначение:** распаковывает входной ZIP-архив и возвращает корневую директорию проекта. 【F:core/archive.py†L1-L52】
  - **Зависимости и конфиг:** не использует конфиг; опирается на `zipfile`, `shutil` и `core.logger` для сообщений об ошибках. 【F:core/archive.py†L13-L51】
  - **Отключение через config:** нельзя; распаковка обязательна для дальнейших шагов.

### Обработка контента

- `core/assets.py`
  - **Назначение:** переименовывает ассеты, скачивает удалённые ресурсы, удаляет фирменные файлы Tilda, копирует нужные шаблоны и нормализует регистр путей. 【F:core/assets.py†L1-L332】【F:core/assets.py†L332-L653】
  - **Зависимости и конфиг:** использует секции `patterns`, `images`, `service_files` из `config.yaml` (правила ссылок, списки исключений, скачивание, копирование ресурсов, сохранение rename-map). 【F:core/assets.py†L139-L260】【F:core/assets.py†L562-L653】
  - **Отключение через config:** нормализацию регистра можно отключить через `service_files.pipeline_stages.normalize_case.enabled`; скачивание и удаления прекращаются при очистке списков правил. Полное отключение этапа требует изменений в коде/пайплайне.
- `core/cleaners.py`
  - **Назначение:** чистит `robots.txt`, `readme.txt` и другие текстовые файлы от остатков Tilda. 【F:core/cleaners.py†L1-L79】
  - **Зависимости и конфиг:** использует паттерны из `patterns` и список файлов из `service_files.cleaner_options.files_to_clean_tilda_refs`. 【F:core/cleaners.py†L60-L79】
  - **Отключение через config:** достаточно очистить `files_to_clean_tilda_refs` или сами паттерны, тогда модуль ничего не изменит.
- `core/forms.py`
  - **Назначение:** генерирует `send_email.php` и `js/form-handler.js` с обработчиком форм. 【F:core/forms.py†L1-L195】
  - **Зависимости и конфиг:** напрямую конфиг не читает; использует e-mail из CLI и путь проекта. 【F:core/forms.py†L136-L195】
  - **Отключение через config:** нет прямого флага; чтобы не создавать файлы, нужно исключить вызов модуля из пайплайна.
- `core/inject.py`
  - **Назначение:** добавляет в HTML ссылку на скрипт обработчика форм перед заданным маркером. 【F:core/inject.py†L1-L51】
  - **Зависимости и конфиг:** читает `service_files.html_inject_options` (имя скрипта и маркер вставки) из `config.yaml`. 【F:core/inject.py†L11-L22】
  - **Отключение через config:** спецфлага нет, но можно очистить маркер/скрипт в конфиге или убрать стадию из пайплайна.
- `core/refs.py`
  - **Назначение:** обновляет ссылки в HTML/CSS/JS на основе карты переименований, правил замены и маршрутов `.htaccess`. 【F:core/refs.py†L1-L198】【F:core/refs.py†L198-L274】
  - **Зависимости и конфиг:** использует `patterns` (`links`, `ignore_prefixes`, `replace_rules`), `images` (паттерны для favicon) и `htaccess_patterns`; маршруты берёт через `core.htaccess`. 【F:core/refs.py†L18-L130】【F:core/refs.py†L198-L236】
  - **Отключение через config:** удалить все правила возможно, но стадия всё равно пройдёт по файлам; полное выключение требует изменения пайплайна.
- `core/htaccess.py`
  - **Назначение:** парсит `.htaccess` и собирает карту маршрутов/редиректов для обновления ссылок и проверки. 【F:core/htaccess.py†L1-L86】
  - **Зависимости и конфиг:** читает регэкспы из `patterns.htaccess_patterns`. 【F:core/htaccess.py†L12-L40】
  - **Отключение через config:** можно очистить паттерны, тогда маршруты не будут найдены; полностью отключить парсинг можно только убрав вызов `collect_routes`.
- `core/page404.py`
  - **Назначение:** нормализует страницу `404.html`, заменяя заголовок, сообщение и удаляя сторонние скрипты. 【F:core/page404.py†L1-L68】
  - **Зависимости и конфиг:** работает без конфига; ищет файл в корне проекта. 【F:core/page404.py†L20-L68】
  - **Отключение через config:** отсутствует; для пропуска нужно исключить вызов из пайплайна.
- `core/script_cleaner.py`
  - **Назначение:** удаляет из HTML/JS запретные скрипты Tilda и связанные комментарии. 【F:core/script_cleaner.py†L1-L220】
  - **Зависимости и конфиг:** использует `service_files.scripts_to_remove_from_project` для списка имён и паттернов, а также `patterns.text_extensions` для перечня расширений. 【F:core/script_cleaner.py†L8-L91】【F:core/script_cleaner.py†L137-L220】
  - **Отключение через config:** очистите списки `filenames`/`patterns`, тогда модуль завершится без изменений.
- `core/checker.py`
  - **Назначение:** проверяет ссылки в HTML, учитывая маршруты из `.htaccess`, и фиксирует битые ссылки. 【F:core/checker.py†L1-L108】
  - **Зависимости и конфиг:** использует паттерны ссылок и игнорируемые префиксы из `patterns`, а также `core.htaccess`. 【F:core/checker.py†L13-L92】
  - **Отключение через config:** конфиг не содержит флага; отключить можно только исключив вызов из пайплайна.
- `core/report.py`
  - **Назначение:** формирует промежуточные и финальные текстовые отчёты. 【F:core/report.py†L1-L86】
  - **Зависимости и конфиг:** опирается на `manifest.json` (`features.reports`) и переменную окружения `DETILDA_DISABLE_REPORTS`. 【F:core/report.py†L9-L55】
  - **Отключение через config:** установите `features.reports: false` в манифесте или задайте `DETILDA_DISABLE_REPORTS=1`.

### Тесты и инструменты

- `core/build_sync.py`
  - **Назначение:** синхронизирует `manifest.json` с собранным архивом (имя файла, версия). 【F:core/build_sync.py†L1-L63】
  - **Зависимости и конфиг:** работает с путями и JSON; конфиг не участвует.
  - **Отключение через config:** не требуется; модуль используется вручную или из CLI.
- `tools/sync_manifest.py`
  - **Назначение:** CLI-обёртка вокруг `synchronize_manifest_with_build`, принимает путь к архиву и опциональную версию. 【F:tools/sync_manifest.py†L1-L33】
  - **Зависимости и конфиг:** не читает конфиг; зависит от `argparse` и `core.build_sync`.
  - **Отключение через config:** не применимо.
- `tests/test_manifest_sync.py`
  - **Назначение:** проверяет, что синхронизация манифеста обновляет версию и имя архива. 【F:tests/test_manifest_sync.py†L1-L55】
  - **Зависимости и конфиг:** напрямую с конфигом не работает; подставляет временный `manifest.json`.
  - **Отключение через config:** тест отключается только через pytest-маркеры/исключение из набора тестов.
- `tests/test_case_normalization.py`
  - **Назначение:** покрывает нормализацию регистра в `core.assets` и обновление ссылок. 【F:tests/test_case_normalization.py†L1-L77】
  - **Зависимости и конфиг:** использует минимальные словари, имитируя секции `patterns` и `service_files` для проверки флага `normalize_case`. 【F:tests/test_case_normalization.py†L16-L56】
  - **Отключение через config:** тест демонстрирует, что выключение достигается установкой `enabled: False`; отключить сам тест можно только на уровне pytest.
- `resources/favicon.ico`
  - **Назначение:** дефолтная иконка, копируемая на этапах ассетов по правилам `service_files.resource_copy`. 【F:core/assets.py†L468-L543】【F:config/config.yaml†L150-L160】
  - **Зависимости и конфиг:** используется модулем `core.assets`; правило копирования настраивается в конфиге.
  - **Отключение через config:** удалите или измените правило `resource_copy.files`, чтобы не копировать иконку.
- `core/__init__.py`
  - **Назначение:** помечает директорию `core` как пакет Python.
  - **Зависимости и конфиг:** не содержит логики.
  - **Отключение через config:** не требуется.

## Logging & reports

Logs are written to the `logs/` folder inside the project root. Intermediate and final summaries track renamed assets, cleaned files, fixed/remaining broken links, and overall duration. 【F:core/logger.py†L28-L136】【F:core/report.py†L44-L107】

## Development & testing

Run the existing tests with:

```bash
pytest
```

The suite covers manifest synchronization and asset case normalization behavior. 【F:tests/test_manifest_sync.py†L1-L62】【F:tests/test_case_normalization.py†L1-L114】

For pull requests, keep the manifest (`manifest.json`) aligned with the build rules by running `python tools/sync_manifest.py` when packaging changes. 【F:tools/sync_manifest.py†L1-L41】【F:manifest.json†L32-L48】

## License

Detilda is distributed under the MIT License; see `manifest.json` for attribution details. 【F:manifest.json†L2-L21】
