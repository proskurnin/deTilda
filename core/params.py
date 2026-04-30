"""Runtime parameters passed by the caller (web UI, CLI, API).

Не конфиг — а то, что пользователь задаёт при каждом запросе.
Передаётся через ProjectContext во все шаги конвейера.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ProcessParams"]


@dataclass
class ProcessParams:
    """Параметры одного запуска обработки архива.

    email: адрес получателя форм сайта (подставляется в send_email.php).
           Если пустой — используются test_recipients из config.yaml.
    """
    email: str = ""
