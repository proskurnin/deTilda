"""Helpers for generating form related assets."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from core import logger, utils

__all__ = ["generate_send_email_php", "generate_form_handler_js"]

_SEND_EMAIL_TEMPLATE = """<?php
$project = '{project_name}';
$email = '{email}';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {{
    $to = $email;
    $subject = 'Запрос с сайта ' . $project;
    $body = "Имя: " . ($_POST['name'] ?? '') . "\n" .
            "Телефон: " . ($_POST['phone'] ?? '') . "\n" .
            "Email: " . ($_POST['email'] ?? '') . "\n" .
            "Сообщение: " . ($_POST['message'] ?? '');
    $headers = 'From: ' . $email;
    mail($to, $subject, $body, $headers);
}}
?>
"""

_FORM_HANDLER_TEMPLATE = """/* form-handler.js */
(function(){
  function qs(s, root){ return (root||document).querySelector(s); }
  function qsa(s, root){ return Array.prototype.slice.call((root||document).querySelectorAll(s)); }
  function popup(text, ok){
    var id = 'aida-form-popup';
    var el = document.getElementById(id);
    if(!el){
      el = document.createElement('div');
      el.id = id;
      el.style.position='fixed';
      el.style.left='50%';
      el.style.top='20px';
      el.style.transform='translateX(-50%)';
      el.style.padding='12px 16px';
      el.style.borderRadius='8px';
      el.style.background= ok ? '#1f7a1f' : '#7a1f1f';
      el.style.color='#fff';
      el.style.zIndex='99999';
      el.style.fontFamily='system-ui, -apple-system, Segoe UI, Roboto';
      document.body.appendChild(el);
    }
    el.textContent = text;
    el.style.display='block';
    setTimeout(function(){ el.style.display='none'; }, 3500);
  }

  function onSubmit(e){
    var f = e.target;
    if(!f || f.tagName !== 'FORM') return;

    e.preventDefault();

    // Простая валидация [required] (добавлено из v3.19+)
    var required = qsa('[required]', f);
    for(var i=0; i<required.length; i++){
        if(!required[i].value){
            // e.preventDefault(); // Уже вызван выше
            popup('Заполните обязательные поля', false);
            try { required[i].focus(); } catch(e){}
            return;
        }
    }

    var fd = new FormData(f);
    var action = f.getAttribute('action') || 'send_email.php';
    fetch(action, { method:'POST', body: fd, credentials: 'same-origin' })
      .then(function(resp){
        var ok = resp.status >=200 && resp.status < 400; // 303 редирект это < 400

        if (resp.redirected) {
             window.location.href = resp.url;
             return;
        }

        var loc = resp.headers.get('Location');
        if (loc) {
            window.location.href = loc;
            return;
        }

        // Fallback popup
        popup(ok ? 'Заявка отправлена' : 'Ошибка отправки', ok);
        if(ok) f.reset();
      })
      .catch(function(){
        popup('Ошибка сети', false);
      });
  }

  // Подключение
  document.addEventListener('submit', onSubmit, true);

  // Если есть ?sent= в url — показать popup и очистить query
  try {
    var u = new URL(window.location.href);
    var sent = u.searchParams.get('sent');
    if(sent === '1' || sent === '0'){
      popup(sent === '1' ? 'Заявка отправлена' : 'Ошибка отправки', sent==='1');
      u.searchParams.delete('sent');
      history.replaceState(null, '', u.pathname + u.search + u.hash); // (Сохраняем search)
    }
  } catch(e){}
})();
"""


def _resolve_project_root(project_root: Path | Any) -> Path:
    """Return the actual project root path from different inputs."""

    if hasattr(project_root, "project_root"):
        return Path(getattr(project_root, "project_root"))
    return Path(project_root)


def _extract_project_name(project_root: Path) -> str:
    """Derive project name using robots.txt Host if available."""

    robots_path = project_root / "robots.txt"
    if robots_path.exists():
        try:
            robots_content = robots_path.read_text(encoding="utf-8")
        except OSError:
            robots_content = ""

        for raw_line in robots_content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("host:"):
                host_value = line.split(":", 1)[1].strip()
                parsed = urlparse(host_value)
                host = parsed.netloc or parsed.path
                host = host.rstrip("/")
                if host:
                    return host

    return project_root.name


def generate_send_email_php(project_root: Path | Any, email: str) -> Path:
    project_root = _resolve_project_root(project_root)
    target = project_root / "send_email.php"
    project_name = _extract_project_name(project_root)
    content = _SEND_EMAIL_TEMPLATE.format(project_name=project_name, email=email)
    utils.safe_write(target, content)
    logger.info(f"📨 Файл send_email.php создан: {utils.relpath(target, project_root)}")
    generate_form_handler_js(project_root)
    return target


def generate_form_handler_js(project_root: Path | Any) -> Path:
    project_root = _resolve_project_root(project_root)
    target = project_root / "js" / "form-handler.js"
    utils.safe_write(target, _FORM_HANDLER_TEMPLATE)
    logger.info(
        f"📨 Файл form-handler.js создан: {utils.relpath(target, project_root)}"
    )
    return target
