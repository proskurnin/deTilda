"""Helpers for generating ``send_email.php``."""
from __future__ import annotations

from pathlib import Path

from core import logger, utils

__all__ = ["generate_send_email_php"]

_TEMPLATE = """<?php
$project = '{project_name}';
$email = '{email}';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $to = $email;
    $subject = 'Запрос с сайта ' . $project;
    $body = "Имя: " . ($_POST['name'] ?? '') . "\n" .
            "Телефон: " . ($_POST['phone'] ?? '') . "\n" .
            "Email: " . ($_POST['email'] ?? '') . "\n" .
            "Сообщение: " . ($_POST['message'] ?? '');
    $headers = 'From: ' . $email;
    mail($to, $subject, $body, $headers);
}
?>
"""


def generate_send_email_php(project_root: Path, email: str) -> Path:
    project_root = Path(project_root)
    target = project_root / "send_email.php"
    content = _TEMPLATE.format(project_name=project_root.name, email=email)
    utils.safe_write(target, content)
    logger.info(f"📨 Файл send_email.php создан: {utils.relpath(target, project_root)}")
    return target
