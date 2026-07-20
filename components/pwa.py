"""Installation PWA : injecte le manifest + service worker dans le document parent.

`components.html` s'exécute dans une iframe même origine ; on cible donc
`window.parent.document` pour affecter la vraie page (installable « à l'écran d'accueil »).
"""

from __future__ import annotations

import streamlit.components.v1 as components

_SNIPPET = """
<script>
(function () {
  try {
    var doc = window.parent.document;
    if (!doc.querySelector('link[rel="manifest"]')) {
      var m = doc.createElement('link');
      m.rel = 'manifest'; m.href = '/app/static/manifest.json';
      doc.head.appendChild(m);
      var t = doc.createElement('meta');
      t.name = 'theme-color'; t.content = '#e63946';
      doc.head.appendChild(t);
      var a = doc.createElement('link');
      a.rel = 'apple-touch-icon'; a.href = '/app/static/icon.svg';
      doc.head.appendChild(a);
    }
    var nav = window.parent.navigator;
    if (nav && 'serviceWorker' in nav) {
      nav.serviceWorker.register('/app/static/sw.js').catch(function () {});
    }
  } catch (e) { /* iframe cross-origin ou indisponible */ }
})();
</script>
"""


def inject() -> None:
    components.html(_SNIPPET, height=0)
