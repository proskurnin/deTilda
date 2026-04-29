import pytest
import yaml

# Захватываем настоящий safe_load здесь — conftest импортируется pytest
# раньше любого тест-файла, поэтому yaml ещё не подменён.
_REAL_YAML_SAFE_LOAD = yaml.safe_load


@pytest.fixture(autouse=True)
def _restore_yaml_safe_load():
    """Восстанавливает yaml.safe_load до и после каждого теста.

    Несколько тест-файлов делают `yaml_stub.safe_load = _fake_safe_load`
    на module-level при коллекции. Это побочный эффект: в порядке
    импорта test_refs_anchor_links.py (который патчит yaml) идёт
    перед test_refs_replace_rules.py, поэтому `_real_yaml_safe_load`
    там захватывает уже fake-функцию, а не настоящую.

    Фикстура снимает эту зависимость: каждый тест начинается и
    заканчивается с настоящим yaml.safe_load.
    """
    yaml.safe_load = _REAL_YAML_SAFE_LOAD
    yield
    yaml.safe_load = _REAL_YAML_SAFE_LOAD
