/* form-handler.js */
(function () {
  'use strict';

  var INVALID_CLASS = '_dt-invalid';
  var STYLE_ID = 'dt-invalid-style';
  var PHONE_RE = /^[0-9+()\-\s]+$/;

  var FIELD_ALIASES = {
    Name: ['name', 'fullname', 'your-name'],
    Company: ['company', 'company_name'],
    Country: ['country', 'location_country'],
    Email: ['email', 'mail', 'your-email'],
    Phone: ['phone', 'tel', 'telephone'],
    Message: ['message', 'comment', 'text']
  };

  function ensureInvalidStyle() {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    var style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent =
      '.' + INVALID_CLASS + '{border-color:#d33 !important;outline:1px solid rgba(211,51,51,.35) !important;box-shadow:0 0 0 2px rgba(211,51,51,.12) !important;}';
    document.head.appendChild(style);
  }

  function normalizeToken(value) {
    return String(value || '')
      .toLowerCase()
      .replace(/[_\s]+/g, '-')
      .replace(/[^a-z0-9\-]/g, '')
      .trim();
  }

  function fieldCandidates(input) {
    var attrs = [
      input.name,
      input.id,
      input.getAttribute('placeholder'),
      input.getAttribute('aria-label'),
      input.getAttribute('data-name'),
      input.getAttribute('data-field'),
      input.getAttribute('data-title'),
      input.getAttribute('data-input-name')
    ];

    var out = [];
    for (var i = 0; i < attrs.length; i += 1) {
      var token = normalizeToken(attrs[i]);
      if (token) {
        out.push(token);
      }
    }
    return out;
  }

  function resolveStandardField(input) {
    var candidates = fieldCandidates(input);
    for (var i = 0; i < candidates.length; i += 1) {
      var token = candidates[i];
      for (var canonical in FIELD_ALIASES) {
        if (!Object.prototype.hasOwnProperty.call(FIELD_ALIASES, canonical)) {
          continue;
        }
        var aliases = FIELD_ALIASES[canonical];
        for (var j = 0; j < aliases.length; j += 1) {
          if (token === normalizeToken(aliases[j])) {
            return canonical;
          }
        }
      }
    }

    return null;
  }

  function collectStandardFields(form) {
    var fields = {
      Name: null,
      Company: null,
      Country: null,
      Email: null,
      Phone: null,
      Message: null
    };

    var controls = form.querySelectorAll('input, textarea, select');
    for (var i = 0; i < controls.length; i += 1) {
      var input = controls[i];
      if (input.disabled) {
        continue;
      }

      var canonical = resolveStandardField(input);
      if (canonical && !fields[canonical]) {
        fields[canonical] = input;
      }
    }

    return fields;
  }

  function clearInvalid(input) {
    if (!input || !input.classList) {
      return;
    }
    input.classList.remove(INVALID_CLASS);
  }

  function markInvalid(input) {
    if (!input || !input.classList) {
      return;
    }
    if ((input.type || '').toLowerCase() === 'hidden') {
      return;
    }
    input.classList.add(INVALID_CLASS);
  }

  function normalizedValue(input) {
    return String(input && input.value ? input.value : '').trim();
  }

  function isValidEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  function isValidPhone(value) {
    return value === '' || PHONE_RE.test(value);
  }

  function attachRealtimeCleanup(form) {
    var controls = form.querySelectorAll('input, textarea, select');
    for (var i = 0; i < controls.length; i += 1) {
      controls[i].addEventListener('input', function (event) {
        clearInvalid(event.target);
      });
      controls[i].addEventListener('change', function (event) {
        clearInvalid(event.target);
      });
    }
  }

  function validateForm(form) {
    var fields = collectStandardFields(form);
    var errors = [];

    if (fields.Name) {
      if (!normalizedValue(fields.Name)) {
        errors.push(fields.Name);
      }
    }

    if (fields.Email) {
      var emailValue = normalizedValue(fields.Email);
      if (!emailValue || !isValidEmail(emailValue)) {
        errors.push(fields.Email);
      }
    }

    if (fields.Phone) {
      var phoneValue = normalizedValue(fields.Phone);
      if (!isValidPhone(phoneValue)) {
        errors.push(fields.Phone);
      }
    }

    for (var i = 0; i < errors.length; i += 1) {
      markInvalid(errors[i]);
    }

    if (errors.length > 0 && errors[0] && typeof errors[0].focus === 'function') {
      try {
        errors[0].focus();
      } catch (ignore) {
        // no-op
      }
    }

    return errors.length === 0;
  }

  function resolveAction(form) {
    var fallbackAction = 'send_email.php';
    var attr = (form.getAttribute('action') || '').trim();
    if (!attr) {
      return fallbackAction;
    }

    var remoteHosts = [
      'forms.tildacdn.com',
      'forms.tildacdn.pro',
      'forms.aidacdn.com',
      'forms.aidacdn.pro',
      'forms.tilda.ws',
      'forms.tilda.cc',
      'forms.tilda.network',
      'forms.tilda.ru',
      'forms.aladeco.com'
    ];

    var remotePrefixes = ['forms.tilda.', 'forms.tildacdn.', 'forms.aidacdn.', 'forms.aladeco.'];

    try {
      var parsed = new URL(attr, window.location.href);
      var host = (parsed.host || '').toLowerCase();

      for (var i = 0; i < remoteHosts.length; i += 1) {
        if (host === remoteHosts[i]) {
          return fallbackAction;
        }
      }
      for (var j = 0; j < remotePrefixes.length; j += 1) {
        if (host.indexOf(remotePrefixes[j]) === 0) {
          return fallbackAction;
        }
      }

      return parsed.href;
    } catch (e) {
      return fallbackAction;
    }
  }

  function showPopup(text, ok) {
    var id = 'aida-form-popup';
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.style.position = 'fixed';
      el.style.left = '50%';
      el.style.top = '20px';
      el.style.transform = 'translateX(-50%)';
      el.style.padding = '12px 16px';
      el.style.borderRadius = '8px';
      el.style.color = '#fff';
      el.style.zIndex = '99999';
      el.style.fontFamily = 'system-ui, -apple-system, Segoe UI, Roboto';
      document.body.appendChild(el);
    }
    el.style.background = ok ? '#1f7a1f' : '#7a1f1f';
    el.textContent = text;
    el.style.display = 'block';
    setTimeout(function () {
      el.style.display = 'none';
    }, 3500);
  }

  // ── Popup support (replaces tilda-events-1.0.min.js) ──────

  function _findPopupRoot(el) {
    if (el && el.closest) {
      return el.closest('.t-popup');
    }
    var node = el;
    while (node && node.nodeType === 1) {
      if (node.classList && node.classList.contains('t-popup')) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  function openPopup(popup) {
    if (!popup || !popup.classList) {
      return;
    }
    popup.style.display = 'block';
    popup.style.opacity = '';
    popup.classList.add('t-popup_show', 't-popup_opened');

    var bg = popup.querySelector('.t-popup__bg');
    if (bg) {
      bg.style.display = 'block';
    }

    if (document.body) {
      document.body.classList.add('t-body_popupshowed', 't-body_popupfixed', 't-lock');
      document.body.style.overflow = 'hidden';
    }
    if (document.documentElement) {
      document.documentElement.classList.add('t-lock');
    }
  }

  function closePopup(popup) {
    if (!popup || !popup.classList) {
      return;
    }
    popup.classList.remove('t-popup_show', 't-popup_opened');
    popup.style.display = 'none';
    popup.style.opacity = '0';

    var bg = popup.querySelector('.t-popup__bg');
    if (bg) {
      bg.style.display = 'none';
    }

    if (document.body) {
      document.body.classList.remove('t-body_popupshowed', 't-body_popupfixed', 't-lock');
      document.body.style.overflow = '';
      document.body.style.position = '';
    }
    if (document.documentElement) {
      document.documentElement.classList.remove('t-lock');
    }
  }

  function handlePopupClick(event) {
    var node = event.target;
    while (node && node.nodeType === 1) {
      // Close button
      if (node.classList && (
        node.classList.contains('js-popup-close') ||
        node.classList.contains('t-popup__close')
      )) {
        var popup = _findPopupRoot(node);
        if (popup) {
          event.preventDefault();
          closePopup(popup);
        }
        return;
      }

      // Background overlay
      if (node.classList && node.classList.contains('t-popup__bg')) {
        closePopup(_findPopupRoot(node));
        return;
      }

      // data-popup-id trigger
      var popupId = node.getAttribute && node.getAttribute('data-popup-id');
      if (popupId) {
        var target = document.getElementById(popupId);
        if (target && target.classList && target.classList.contains('t-popup')) {
          event.preventDefault();
          openPopup(target);
          return;
        }
      }

      // href="#popupXXX" trigger
      if (node.tagName === 'A') {
        var href = (node.getAttribute('href') || '').trim();
        if (href.charAt(0) === '#' && href.length > 1) {
          var target = document.getElementById(href.slice(1));
          if (target && target.classList && target.classList.contains('t-popup')) {
            event.preventDefault();
            openPopup(target);
            return;
          }
        }
      }

      node = node.parentNode;
    }
  }

  function handleEscKey(event) {
    if (event.key === 'Escape' || event.keyCode === 27) {
      var openPopups = document.querySelectorAll('.t-popup.t-popup_show');
      for (var i = 0; i < openPopups.length; i += 1) {
        closePopup(openPopups[i]);
      }
    }
  }

  function hideFormPopup(form) {
    closePopup(_findPopupRoot(form));
  }

  function handleSubmit(event) {
    var form = event.target;
    if (!form || form.tagName !== 'FORM') {
      return;
    }

    if (!validateForm(form)) {
      event.preventDefault();
      showPopup('Проверьте корректность полей формы', false);
      return;
    }

    event.preventDefault();

    fetch(resolveAction(form), {
      method: 'POST',
      body: new FormData(form),
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(function (response) {
        if (response.redirected) {
          window.location.href = response.url;
          return null;
        }

        var locationHeader = response.headers.get('Location');
        if (locationHeader) {
          window.location.href = locationHeader;
          return null;
        }

        return response.text().then(function (text) {
          var ok = response.ok;
          var message = ok ? 'Заявка отправлена' : 'Ошибка отправки';

          if (text) {
            try {
              var payload = JSON.parse(text);
              if (typeof payload.ok === 'boolean') {
                ok = payload.ok;
              }
              if (payload.message) {
                message = payload.message;
              } else if (payload.error && !ok) {
                message = payload.error;
              }
            } catch (ignore) {
              // Not JSON; keep fallback message.
            }
          }

          showPopup(message, ok);
          if (ok) {
            hideFormPopup(form);
            if (typeof form.reset === 'function') {
              form.reset();
            }
          }
        });
      })
      .catch(function () {
        showPopup('Ошибка сети', false);
      });
  }

  ensureInvalidStyle();
  document.addEventListener('submit', handleSubmit, true);
  document.addEventListener('click', handlePopupClick, false);
  document.addEventListener('keydown', handleEscKey, false);

  var forms = document.querySelectorAll('form');
  for (var i = 0; i < forms.length; i += 1) {
    attachRealtimeCleanup(forms[i]);
  }
})();
