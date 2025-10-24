# -*- coding: utf-8 -*-
"""Form helpers."""

from __future__ import annotations

from pathlib import Path

from core import logger
from core.project import ProjectContext


def _resolve_project_root(project: Path | ProjectContext) -> Path:
    if isinstance(project, ProjectContext):
        return project.project_root
    return Path(project)


def generate_send_email_php(project: Path | ProjectContext, recipient_email: str) -> None:
    """Создаёт send_email.php в корне проекта с учётом переданного e-mail."""

    project_root = _resolve_project_root(project)
    target = project_root / "send_email.php"

    php_code = f"""<?php
declare(strict_types=1);

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {{
    http_response_code(405);
    header('Content-Type: text/plain; charset=UTF-8');
    echo 'Method Not Allowed';
    exit;
}}

$recipient_email = "{recipient_email}";
$subject = "New request from " . ($_SERVER['HTTP_HOST'] ?? 'website');

function p(string $k, string $d=''): string {{ return isset($_POST[$k]) ? trim((string)$_POST[$k]) : $d; }}

$ignored = ['redirect','redirect2parent','g-recaptcha-response','csrf_token'];
$lines = [];
$lines[] = 'Form submission from ' . ($_SERVER['HTTP_HOST'] ?? 'website');
$lines[] = 'Date: ' . date('Y-m-d H:i:s');
$lines[] = str_repeat('-', 40);
foreach ($_POST as $k => $v) {{
    if (in_array($k, $ignored, true)) continue;
    if (is_array($v)) $v = implode(', ', $v);
    $lines[] = $k . ': ' . $v;
}}
$lines[] = str_repeat('-', 40);
$message = implode("\\n", $lines);

$email = p('Email');
$name  = strip_tags(p('Name', 'Not specified'));

$encoded_subject = '=?UTF-8?B?' . base64_encode($subject) . '?=';
$fromHost = $_SERVER['HTTP_HOST'] ?? 'localhost';
$replyTo  = (filter_var($email, FILTER_VALIDATE_EMAIL) ? $email : ('no-reply@' . $fromHost));
$headers  = "MIME-Version: 1.0\\r\\n";
$headers .= "Content-Type: text/plain; charset=UTF-8\\r\\n";
$headers .= "From: no-reply@" . $fromHost . "\\r\\n";
$headers .= "Reply-To: " . $replyTo . "\\r\\n";

$sent_ok = @mail($recipient_email, $encoded_subject, $message, $headers);

$back = (!empty($_POST['redirect'])) ? (string)$_POST['redirect']
      : (!empty($_POST['redirect2parent']) ? (string)$_POST['redirect2parent']
      : (isset($_SERVER['HTTP_REFERER']) ? (string)$_SERVER['HTTP_REFERER'] : '/'));

$parsed = parse_url($back);
$currentHost = $_SERVER['HTTP_HOST'] ?? '';
if (isset($parsed['host']) && $parsed['host'] !== '' && $parsed['host'] !== $currentHost) {{
    $back = '/';
}}

$hash = '';
if (strpos($back, '#') !== false) {{
    list($base, $frag) = explode('#', $back, 2);
    $back = $base;
    $hash = '#' . $frag;
}}

if ($hash === '' || $hash === null) {{
    $hash = '#popup:myform';
}}

$sep  = (strpos($back, '?') === false) ? '?' : '&';
$back = $back . $sep . 'sent=' . ($sent_ok ? '1' : '0') . $hash;

header('Location: ' . $back, true, 303);
exit;
?>"""

    try:
        target.write_text(php_code, encoding="utf-8")
        logger.info(f"📨 Файл send_email.php создан: {target}")
    except Exception as e:
        logger.err(f"[forms] Ошибка записи send_email.php: {e}")