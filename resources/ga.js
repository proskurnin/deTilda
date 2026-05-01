/* Google Analytics 4 loader.
   Set window.DETILDA_GA_ID in js/ga-config.js. */
(function () {
  'use strict';

  var id = window.DETILDA_GA_ID;

  if (!id || !/^G-[A-Z0-9]+$/i.test(id)) {
    return;
  }

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () {
    window.dataLayer.push(arguments);
  };

  window.gtag('js', new Date());
  window.gtag('config', id);

  var script = document.createElement('script');
  script.async = true;
  script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(id);
  document.head.appendChild(script);
})();
