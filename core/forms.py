"""Helpers for generating form related assets."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from core import logger, utils
from core.module_versions import register_module_version

register_module_version(
    __name__,
    "v4.7 Stable",
    "Добавлена регистрация версий модулей для отслеживания эволюции форм.",
)

__all__ = ["generate_send_email_php", "generate_form_handler_js"]

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
    var attr = f.getAttribute('action');
    var fallbackAction = 'send_email.php';
    var action = attr ? attr.trim() : '';
    var remoteHosts = [
      'forms.tildacdn.com',
      'forms.tildacdn.pro',
      'forms.tilda.ws',
      'forms.tilda.cc',
      'forms.tilda.network',
      'forms.tilda.ru',
      'forms.aladeco.com'
    ];
    var remotePrefixes = [
      'forms.tilda.',
      'forms.tildacdn.',
      'forms.aladeco.'
    ];

    if(!action){
      action = fallbackAction;
    } else {
      try {
        var parsed = new URL(action, window.location.href);
        var host = (parsed.host || '').toLowerCase();
        var isRemote = false;

        for(var i=0; i<remoteHosts.length; i++){
          if(host === remoteHosts[i]){
            isRemote = true;
            break;
          }
        }

        if(!isRemote){
          for(var j=0; j<remotePrefixes.length; j++){
            if(host.indexOf(remotePrefixes[j]) === 0){
              isRemote = true;
              break;
            }
          }
        }

        action = isRemote ? fallbackAction : parsed.href;
      } catch(parseError){
        action = fallbackAction;
      }
    }

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


def generate_send_email_php(project_root: Path | Any) -> Path:
    project_root = _resolve_project_root(project_root)
    target = project_root / "send_email.php"
    template_path = Path(__file__).resolve().parent.parent / "resources" / "send_email.php"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(template_path.read_bytes())
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
