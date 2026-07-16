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
    ga_measurement_id: GA4 Measurement ID для js/ga-config.js.
           Если пустой или невалидный — аналитика остаётся отключённой.
    """
    email: str = ""
    ga_measurement_id: str = ""
