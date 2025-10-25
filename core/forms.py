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

header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {{
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed'], JSON_UNESCAPED_UNICODE);
    exit;
}}

$to = $email;
$subject = 'Запрос с сайта ' . $project;

$safe_post = [];
foreach ($_POST as $key => $value) {{
    if (is_array($value)) {{
        $value = implode(', ', $value);
    }}
    $safe_post[$key] = trim((string) $value);
}}

$name = $safe_post['name']
    ?? $safe_post['Name']
    ?? $safe_post['fullname']
    ?? $safe_post['FullName']
    ?? '';
$phone = $safe_post['phone']
    ?? $safe_post['Phone']
    ?? $safe_post['tel']
    ?? $safe_post['Телефон']
    ?? '';
$email_from = $safe_post['email']
    ?? $safe_post['Email']
    ?? $safe_post['mail']
    ?? '';
$message = $safe_post['message']
    ?? $safe_post['Message']
    ?? $safe_post['comment']
    ?? $safe_post['Комментарий']
    ?? '';

$body_lines = [];
if ($name !== '') {{
    $body_lines[] = 'Имя: ' . $name;
}}
if ($phone !== '') {{
    $body_lines[] = 'Телефон: ' . $phone;
}}
if ($email_from !== '') {{
    $body_lines[] = 'Email: ' . $email_from;
}}
if ($message !== '') {{
    $body_lines[] = 'Сообщение: ' . $message;
}}

foreach ($safe_post as $key => $value) {{
    if (in_array($key, ['name', 'Name', 'fullname', 'FullName', 'phone', 'Phone', 'tel', 'Телефон', 'email', 'Email', 'mail', 'message', 'Message', 'comment', 'Комментарий'], true)) {{
        continue;
    }}
    $body_lines[] = $key . ': ' . $value;
}}

if (!$body_lines) {{
    $body_lines[] = 'Форма отправлена, но данные отсутствуют.';
}}

$body_lines[] = '';
$body_lines[] = '---';
$body_lines[] = 'Отправлено: ' . date('Y-m-d H:i:s');

$body = implode("\n", $body_lines);

$headers = [];
$headers[] = 'From: ' . $email;
if ($email_from !== '') {{
    $headers[] = 'Reply-To: ' . $email_from;
}}
$headers[] = 'Content-Type: text/plain; charset=utf-8';
$headers[] = 'X-Mailer: PHP/' . phpversion();

$sent = mail($to, $subject, $body, implode("\r\n", $headers));

if ($sent) {{
    http_response_code(200);
    echo json_encode(['ok' => true, 'message' => 'Сообщение успешно отправлено'], JSON_UNESCAPED_UNICODE);
    exit;
}}

http_response_code(500);
echo json_encode(['ok' => false, 'error' => 'Не удалось отправить письмо'], JSON_UNESCAPED_UNICODE);
exit;
?>
"""

_FORM_HANDLER_TEMPLATE = """/* form-handler.js */
(function(){
  function qs(s, root){ return (root||document).querySelector(s); }
  function qsa(s, root){ return Array.prototype.slice.call((root||document).querySelectorAll(s)); }
  function matches(el, selector){
    if(!el || !selector) return false;
    var proto = Element.prototype;
    var fn = proto.matches || proto.matchesSelector || proto.webkitMatchesSelector || proto.mozMatchesSelector || proto.msMatchesSelector;
    if(!fn) return false;
    return fn.call(el, selector);
  }
  function closest(el, selector){
    while(el && el !== document){
      if(matches(el, selector)) return el;
      el = el.parentElement || el.parentNode;
    }
    return null;
  }
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

  function unlockPage(){
    var body = document.body;
    if(body && body.classList){
      body.classList.remove('t-body_popupshowed', 't-body_popupfixed', 't-lock');
      body.style.overflow = '';
      body.style.position = '';
    }
    if(document.documentElement && document.documentElement.classList){
      document.documentElement.classList.remove('t-lock');
    }
  }

  function hideFormPopup(form){
    var popupEl = closest(form, '.t-popup');
    if(popupEl && popupEl.classList){
      popupEl.classList.remove('t-popup_show', 't-popup_opened');
      if(popupEl.style){
        popupEl.style.display = 'none';
        popupEl.style.opacity = '0';
      }
      var bg = qs('.t-popup__bg', popupEl);
      if(bg && bg.style){
        bg.style.display = 'none';
      }
    }
    unlockPage();
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
    fetch(action, { method:'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
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

        var message = ok ? 'Заявка отправлена' : 'Ошибка отправки';

        return resp.text().then(function(bodyText){
          if(bodyText){
            try {
              var payload = JSON.parse(bodyText);
              if(typeof payload.ok === 'boolean'){
                ok = !!payload.ok;
              }
              if(payload.message){
                message = payload.message;
              } else if(payload.error && !ok){
                message = payload.error;
              }
            } catch(parseErr){
              // ignore invalid json
            }
          }

          popup(message, ok);
          if(ok){
            hideFormPopup(f);
            if(typeof f.reset === 'function'){
              f.reset();
            }
          }

          try {
            var successEvent;
            if (typeof window.CustomEvent === 'function') {
              successEvent = new CustomEvent('detilda:form-sent', { detail: { form: f, ok: ok } });
            } else {
              successEvent = document.createEvent('CustomEvent');
              successEvent.initCustomEvent('detilda:form-sent', true, true, { form: f, ok: ok });
            }
            document.dispatchEvent(successEvent);
          } catch(eventErr) {
            // старые браузеры без CustomEvent
          }
        });

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
