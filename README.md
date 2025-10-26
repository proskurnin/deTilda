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
