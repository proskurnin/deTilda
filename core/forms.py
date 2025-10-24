# -*- coding: utf-8 -*-
"""
forms.py — генерация PHP-формы и внедрение JS-скриптов (Detilda v4.4 LTS)
"""

from pathlib import Path
from core import logger
import re


def generate_send_email_php(project_root: Path, recipient_email: str) -> None:
    """
    Создаёт send_email.php в корне проекта с учётом переданного e-mail.
    """
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


def inject_form_scripts(project_root: Path) -> int:
    """
    Внедряет form-handler.js и AIDA forms во все HTML-файлы.
    Возвращает количество изменённых файлов.
    """
    injected = 0
    html_files = list(project_root.rglob("*.html"))

    for file_path in html_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")

            # Удаляем старые тильдовские скрипты
            content = re.sub(r'<script[^>]+tilda[^>]*></script>', '', content, flags=re.I)

            # Проверяем, добавлен ли уже form-handler.js
            if "form-handler.js" not in content:
                script_block = '\n<script src="js/form-handler.js"></script>\n'
                if "</body>" in content:
                    content = content.replace("</body>", script_block + "</body>")
                else:
                    content += script_block
                injected += 1
                logger.info(f"🧩 Добавлен скрипт form-handler.js в {file_path.name}")

            # Проверяем наличие AIDA forms
            if "aida-forms" not in content.lower():
                aida_block = '\n<script src="js/aida-forms-1.0.min.js"></script>\n'
                if "</body>" in content:
                    content = content.replace("</body>", aida_block + "</body>")
                else:
                    content += aida_block
                injected += 1
                logger.info(f"🧩 Добавлен AIDA forms в {file_path.name}")

            file_path.write_text(content, encoding="utf-8")

        except Exception as e:
            logger.err(f"[inject] Ошибка обработки {file_path}: {e}")

    return injected