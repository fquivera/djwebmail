# SnappyMail → Django — Fase 3: sistema de diseño, plantillas y contratos HTMX

**Documento:** detalle de Fase 3 sobre el plan de `docs/migracion-django-fase0-2.md`.
**Decisiones de entrada:** las ocho de §3.10 del documento anterior, ya confirmadas.
**Estado:** especificación. **No se genera código de proyecto**; los fragmentos son contratos verificables, no archivos creados.

---

## 0. Resumen y refinamientos sobre la Fase 2

La Fase 3 fija cuatro cosas: cómo se compila y aplica el CSS, cómo se estructura el HTML, qué atributos HTMX exactos usa cada interacción, y qué estado local queda en el navegador.

**Refinamientos explícitos respecto a §3.3 del documento anterior:**

| Tema | Fase 2 decía | Fase 3 fija | Motivo |
|---|---|---|---|
| Login | `hx-post` con `hx-swap="outerHTML"` | **Formulario POST clásico**, sin HTMX | El login debe funcionar sin JS y sin depender de `HX-Redirect`; el fallo de credenciales no debe ser un swap parcial. |
| Logout | `hx-post` + `HX-Redirect` | **Formulario POST clásico** + `303` | Cierra sesión incluso si HTMX no cargó; evita carrera con la cookie. |
| Toasts | No definido | **Módulo JS vanilla**, no Alpine | Un `role="status"` con `textContent` es más simple y auditable que una expresión Alpine. |
| Selección de mensajes | No definido | **Store vanilla** con re-sincronización en `htmx:afterSwap` | La selección cruza lista, toolbar y teclado; no es estado de un solo componente. |
| Paginación / navegación | Parciales HTMX | Parciales **con `href` real** | HTMX es mejora progresiva: sin JS se navega con recarga completa. |
| Autocompletado | JSON (Fase 2) | **Parcial HTML** | Evita plantilla duplicada en JS y mantiene una sola ruta de escape/sanitización. JSON queda solo para subida de adjuntos y healthcheck. |
| `hx-confirm` | Implícito | **Prohibido** | `window.confirm` no es accesible ni tematizable; se usa `<dialog>` de daisyUI. |
| Carga inicial | `hx-trigger="load"` en carpetas y lista | **Render en servidor**, sin petición `load` | Sin JS la página debe mostrar contenido real, no skeletons; y se evita una petición redundante. |
| `hx-on` / `hx-vals` con `js:` | No definido | **Prohibido** | Requieren `eval`; incompatible con CSP estricta. |
| Alpine | “Solo estado local” | **Solo menús, modales y panel de redacción** | Todo lo demás es servidor o vanilla JS. |

**Regla rectora:** el servidor renderiza HTML; HTMX lo intercambia; Alpine solo abre y cierra cosas; el JS vanilla cubre lo que necesita APIs del navegador (portapapeles, XHR con progreso, teclado, foco).

### 0.1 Contraste con la demo oficial 2.38.3c

La demo se capturó con REA `capture_browser_scenario` (ver §1.11 del documento Fase 0–2). Estos son los puntos que **cambian o confirman** la Fase 3:

| Comportamiento observado en SnappyMail | Efecto en esta especificación |
|---|---|
| Login por `POST ?/Json/&q[]=/0/` con body JSON y `X-SM-Token` | Se mantiene formulario POST clásico + `303`; el token CSRF va en el formulario, no en un header que dependa de JS. |
| `Login` devuelve `System.token` y toda la configuración | Django separa autenticación de preferencias; el shell se renderiza con datos de sesión, no con un “dump” de settings. |
| `MessageList` usa `{folder, offset, limit, uidNext, sort, search, useThreads, threadAlgorithm, threadUid}` | El endpoint HTMX de lista usa exactamente esa semántica, pero devuelve HTML parcial; los parámetros se validan con un `Form`. |
| La lista ya trae `preview`, `headers` y adjuntos | El parcial `_message_list.html` pinta esos datos sin una segunda petición por fila. |
| Abrir compositor vacío no genera red | `GET /compose/` renderiza desde sesión; solo reply/forward/draft leen IMAP. |
| `SettingsUpdate` automático al mover resizers | Persistencia por `POST` pequeño y `debounce`; no hay botón “Guardar preferencias”. |
| `smctoken` no HttpOnly; `smtoken`, `smsession`, `smaccount` HttpOnly/Secure/Strict | Django usa sesión HttpOnly + CSRF token; no copia el token de cliente. |
| CSP con `'unsafe-eval'`, `'unsafe-inline'`, `frame-ancestors 'self'` | Se mantiene CSP estricta: Alpine CSP, HTMX `allowEval=false`, `frame-ancestors 'none'`. |
| `AccountsAndIdentities` devuelve `smimeKey` | PGP/S/MIME fuera del MVP; ninguna vista devuelve claves privadas. |
| Plugin JS por usuario en `PluginsLink` | Sin plugins JS por usuario; no se ejecuta código de usuario en el origen de la app. |

**Límite:** `Message`, `Raw` y `Upload` no se observaron en vivo. Sus contratos en §6.4/§6.6 son source-derived y están marcados como tales.

---

## 1. Stack y versiones ancladas

| Pieza | Versión | Motivo del anclaje |
|---|---|---|
| Python | 3.12+ | `imapclient`, tipado moderno, soporte de Django 5.2. |
| Django | 5.2 LTS | Requisito de `django-tailwind` 4.x y LTS con soporte hasta 2028. |
| `django-tailwind` | 4.6.x | Soporta Tailwind v4, modo standalone sin Node y daisyUI opcional. |
| Tailwind CSS | 4.3.x | Configuración CSS-first; sin `tailwind.config.js` obligatorio. |
| daisyUI | 5.7.x | Temas por variables CSS y componentes accesibles. |
| HTMX | 2.0.11 | `responseHandling`, `allowEval=false`, `hx-preserve`. |
| Alpine CSP | 3.17.5 (`@alpinejs/csp`) | Build sin `new Function`, obligatorio para CSP estricta. |
| `django-csp` | 4.0 | Formato `CONTENT_SECURITY_POLICY = {"DIRECTIVES": ...}`. |
| `whitenoise` | 6.x | Estáticos con hash y caché larga sin CDN. |

**Sin CDN.** Todo vendorizado en `static/vendor/` y servido con `ManifestStaticFilesStorage`. Un webmail con CSP estricta no debe depender de un tercero para arrancar.

**daisyUI no se usa como framework de layout.** Se usan sus componentes (`btn`, `menu`, `modal`, `badge`, `input`, `textarea`) y sus tokens de tema; la estructura la pone Tailwind. Esto evita pelearse con estilos de componente cuando la densidad cambia.

---

## 2. Tailwind + daisyUI con `django-tailwind`

### 2.1 Instalación (modo standalone, sin Node)

```bash
pip install 'django-tailwind[cookiecutter,honcho,reload]'
python manage.py tailwind init --no-input --app-name theme --tailwind-version 4s --include-daisy-ui
python manage.py tailwind install
```

- `4s` = binario standalone de Tailwind v4. No requiere Node en producción ni en CI.
- `--include-daisy-ui` descarga `daisyui.mjs` y `daisyui-theme.mjs` en `theme/static_src/src/`. **Se versionan**: sin ellos el build no es reproducible.
- El modo `npm` solo se justifica si hiciera falta un plugin PostCSS propio; no es el caso.

### 2.2 Settings

```python
# config/settings/base.py
INSTALLED_APPS += ["tailwind", "theme"]
TAILWIND_APP_NAME = "theme"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MIDDLEWARE += [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
]
```

`theme` va **después** de `tailwind`. `SecurityMiddleware` antes de WhiteNoise. `CSPMiddleware` lo más arriba posible para cubrir también respuestas de error.

En desarrollo, `django_browser_reload` solo si `DEBUG`; nunca en `base.py` sin condición.

### 2.3 `theme/static_src/src/styles.css`

```css
@import "tailwindcss";

/* Escanea plantillas y código Python/JS del proyecto. */
@source "../../../**/*.{html,py,js}";

/* Los nombres exactos los genera `tailwind init --include-daisy-ui`. */
@plugin "./daisyui.mjs";

@plugin "./daisyui-theme.mjs" {
  name: "mail-light";
  default: true;
  color-scheme: light;

  --color-base-100: oklch(100% 0 0);
  --color-base-200: oklch(97.4% 0.003 250);
  --color-base-300: oklch(92.8% 0.006 250);
  --color-base-content: oklch(24% 0.012 255);

  --color-primary: oklch(52% 0.16 255);
  --color-primary-content: oklch(98% 0.01 255);
  --color-secondary: oklch(58% 0.07 250);
  --color-secondary-content: oklch(98% 0.005 250);
  --color-accent: oklch(62% 0.12 195);
  --color-accent-content: oklch(98% 0.01 195);
  --color-neutral: oklch(32% 0.012 255);
  --color-neutral-content: oklch(97% 0.004 255);

  --color-info: oklch(60% 0.11 240);
  --color-success: oklch(56% 0.12 155);
  --color-warning: oklch(76% 0.14 80);
  --color-error: oklch(56% 0.19 27);

  --radius-selector: 0.375rem;
  --radius-field: 0.375rem;
  --radius-box: 0.5rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 0;
  --noise: 0;
}

@plugin "./daisyui-theme.mjs" {
  name: "mail-dark";
  prefersdark: true;
  color-scheme: dark;

  --color-base-100: oklch(21% 0.012 255);
  --color-base-200: oklch(25% 0.012 255);
  --color-base-300: oklch(30% 0.014 255);
  --color-base-content: oklch(93% 0.006 255);

  --color-primary: oklch(72% 0.13 250);
  --color-primary-content: oklch(18% 0.02 255);
  --color-secondary: oklch(66% 0.06 250);
  --color-secondary-content: oklch(18% 0.02 255);
  --color-accent: oklch(72% 0.10 195);
  --color-accent-content: oklch(18% 0.02 195);
  --color-neutral: oklch(32% 0.01 255);
  --color-neutral-content: oklch(93% 0.006 255);

  --color-info: oklch(70% 0.10 240);
  --color-success: oklch(70% 0.11 155);
  --color-warning: oklch(80% 0.13 80);
  --color-error: oklch(66% 0.17 27);

  --radius-selector: 0.375rem;
  --radius-field: 0.375rem;
  --radius-box: 0.5rem;
  --size-selector: 0.25rem;
  --size-field: 0.25rem;
  --border: 1px;
  --depth: 0;
  --noise: 0;
}

/* Densidad: variante propia, sin tocar la escala global de Tailwind. */
@custom-variant density-compact (&:where([data-density="compact"] *));

@layer base {
  [x-cloak] { display: none !important; }

  html { color-scheme: light dark; }

  :focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
  }

  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
      scroll-behavior: auto !important;
    }
  }
}

/* HTMX: con includeIndicatorStyles = false estas clases son obligatorias. */
@layer components {
  .htmx-indicator {
    opacity: 0;
    transition: opacity 150ms ease-in;
  }
  .htmx-request .htmx-indicator,
  .htmx-request.htmx-indicator {
    opacity: 1;
  }
}
```

Notas:

- `default: true` en claro + `prefersdark: true` en oscuro: la primera visita sigue al sistema operativo sin JS y sin parpadeo.
- Cuando el usuario elige tema, el servidor renderiza `data-theme="mail-dark"` o `mail-light` en `<html>` desde su preferencia. **No hay script de tema antes del paint**, luego no hay FOUC.
- `@custom-variant density-compact` permite `class="h-9 density-compact:h-7"` sin redefinir el espaciado global.
- Los valores OKLCH son punto de partida; el contraste AA se verifica en §9.

### 2.4 Build y CI

```bash
python manage.py tailwind build      # una vez, en CI, antes de collectstatic
python manage.py collectstatic --noinput
```

`tailwind build` es determinista con los `.mjs` versionados. En CI se ejecuta `tailwind build` y se falla si `theme/static/css/dist/styles.css` cambia respecto a lo commiteado (evita CSS desincronizado del HTML).

---

## 3. CSP y carga de assets

### 3.1 Cabeceras

```python
# config/settings/base.py
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "media-src": ["'self'"],
    },
}
```

Consecuencias directas:

- **Sin `unsafe-eval`.** HTMX arranca con `allowEval = false`; Alpine es el build CSP.
- **Sin `unsafe-inline` en estilos.** Nada de `style="..."` en plantillas. Toda variación visual va por clase o por variable CSS puesta con `style` desde JS (CSSOM, permitido) o, preferible, por `data-*` + variantes.
- **`/admin/`** es la excepción: Django admin inyecta estilos y scripts inline. Se sirve con una CSP propia más laxa, aplicada por middleware según `request.path.startswith("/admin/")`. Nunca se relaja la del webmail.
- **Imágenes remotas** no se cargan directo: `img-src` no incluye `https:`. El visor usa `/mail/image-proxy/?u=...` con lista blanca de esquemas, límite de tamaño y timeout; eso convierte una decisión de CSP en una defensa anti-SSRF.
- `connect-src 'self'` permite el `fetch` de autocompletado y el XHR de subida; nada de terceros.
- **Diferencia deliberada con la demo:** SnappyMail 2.38.3c emite `frame-ancestors 'self'` y `X-Frame-Options: SAMEORIGIN`; además necesita `script-src 'unsafe-eval'` y `style-src 'unsafe-inline'`. Django mantiene `frame-ancestors 'none'`, `X-Frame-Options: DENY` y CSP sin `unsafe-*`. No se “copia” la CSP observada.
- `X-Frame-Options: DENY` se emite además de `frame-ancestors 'none'` para navegadores antiguos; `django-csp` no lo pone por sí solo.

### 3.2 Configuración de HTMX (módulo externo, sin inline)

```js
// static/js/core/htmx-config.js
export function configureHtmx(htmx) {
  htmx.config.allowEval = false;
  htmx.config.allowScriptTags = false;
  htmx.config.historyCacheSize = 10;
  htmx.config.refreshOnHistoryMiss = true;
  htmx.config.defaultSwapStyle = "innerHTML";
  htmx.config.includeIndicatorStyles = false; // los estilos viven en styles.css

  htmx.config.responseHandling = [
    { code: "204", swap: false },
    { code: "[23]..", swap: true },
    { code: "422", swap: true, error: false }, // errores de validación de formularios
    { code: "401", swap: false, error: true }, // sesión caducada -> HX-Redirect
    { code: "[45]..", swap: false, error: true },
  ];

  htmx.on("htmx:beforeRequest", (event) => {
    const elt = event.detail.elt;
    if (elt instanceof HTMLElement) elt.setAttribute("aria-busy", "true");
  });

  htmx.on("htmx:afterRequest", (event) => {
    const elt = event.detail.elt;
    if (elt instanceof HTMLElement) elt.removeAttribute("aria-busy");
  });

  htmx.on("htmx:responseError", (event) => {
    const status = event.detail.xhr.status;
    if (status === 401) return; // el servidor ya mandó HX-Redirect
    if (status === 413) {
      document.dispatchEvent(new CustomEvent("mail:toast", {
        detail: { level: "error", text: "El adjunto supera el tamaño máximo permitido." },
      }));
      return;
    }
    document.dispatchEvent(new CustomEvent("mail:toast", {
      detail: { level: "error", text: "No se pudo completar la operación. Inténtalo de nuevo." },
    }));
  });

  htmx.on("htmx:sendError", () => {
    document.dispatchEvent(new CustomEvent("mail:toast", {
      detail: { level: "error", text: "Sin conexión con el servidor." },
    }));
  });
}
```

**Lo que se pierde con `allowEval = false` y cómo se sustituye:**

| Función de HTMX | Sin eval | Sustituto |
|---|---|---|
| `hx-on:*` | No funciona | Listeners en módulos JS (`htmx.on(...)`, `addEventListener`). |
| Filtros de trigger `[condición]` | No funcionan | Eventos explícitos: `hx-trigger="poll"` + `htmx.trigger(el, "poll")` desde JS con la condición. |
| `hx-vals="js:..."` | No funciona | Valores JSON renderizados por el servidor o campos ocultos. |
| `hx-confirm` | Funciona, pero es `window.confirm` | `<dialog>` de daisyUI + evento `mail:confirm`; al aceptar, `confirm.js` ejecuta el `hx-post`. |

### 3.3 Alpine CSP: límites que condicionan las plantillas

El build CSP **no evalúa expresiones arbitrarias**. Soporta más de lo que su nombre sugiere, pero tiene límites que condicionan las plantillas:

- **Sí soporta:** literales de objeto/array, operadores, comparaciones, ternarios, asignaciones simples y `++`, llamadas a métodos, y las magics `$event`, `$refs`, `$el`.
- **No soporta:** asignación a propiedades (`user.name = "x"`), funciones arrow, destructuring, template literals, spread, ni globals (`document`, `window`, `console`, `Math`, `JSON`, `new`).
- `x-html` no funciona (inyección de HTML bloqueada); el HTML siempre viene del servidor.
- `x-data` puede ser un objeto literal, pero se usa `Alpine.data(...)` por mantenibilidad y para poder testear los métodos.
- Se prefieren getters y métodos con nombre a `$watch` para estado derivado; menos magia, más fácil de razonar.

Por eso los componentes de §7 son deliberadamente pequeños y con métodos con nombre.

### 3.4 Orden de scripts en `<head>`/final del `<body>`

```html
<script defer src="{% static 'vendor/htmx.min.js' %}"></script>
<script defer src="{% static 'vendor/alpine-csp.min.js' %}"></script>
<script type="module" src="{% static 'js/app.js' %}"></script>
```

- `defer` conserva el orden: HTMX → Alpine → `app.js`.
- `app.js` registra componentes en `alpine:init` y configura HTMX en `DOMContentLoaded`. Si `app.js` es `type="module"`, se ejecuta tras el parseo pero **antes** de `DOMContentLoaded`; el registro de Alpine debe escuchar `alpine:init`, que Alpine dispara después de su propio `defer`.
- `alpine-focus` no se incluye: `<dialog>` nativo ya atrapa el foco y lo devuelve. Añadirlo solo si aparece un panel no modal que lo necesite, verificando que `x-trap` funciona con el build CSP.

---

## 4. Esqueleto de plantillas

### 4.1 `templates/base.html`

```html
<!doctype html>
<html lang="{{ LANGUAGE_CODE }}" data-theme="{{ ui.theme }}" data-density="{{ ui.density }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="csrf-token" content="{{ csrf_token }}">
  <meta name="color-scheme" content="light dark">
  <title>{% block title %}{{ ui.product_name }}{% endblock %}</title>
  {% load tailwind_tags %}
  {% tailwind_css %}
  {% block head_extra %}{% endblock %}
</head>
<body
  class="min-h-dvh bg-base-200 text-base-content antialiased"
  data-session-expires-at="{{ session_expires_at|date:'c' }}"
  hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>

  <a href="#message-list" class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:p-2 focus:bg-base-100">
    Saltar a la lista de mensajes
  </a>

  {% include "partials/_app_header.html" %}

  <div id="app-shell" hx-history-elt class="grid h-[calc(100dvh-var(--header-h))] grid-cols-1 lg:grid-cols-[16rem_minmax(0,1fr)] xl:grid-cols-[16rem_minmax(0,26rem)_minmax(0,1fr)]">
    <aside id="folder-pane" class="hidden lg:block border-e border-base-300 bg-base-100 overflow-y-auto">
      <nav id="folder-tree" aria-label="Carpetas"
           hx-get="{% url 'mail:folders' %}"
           hx-trigger="mail:folders-changed from:body"
           hx-swap="innerHTML">
        {% include "partials/_folder_tree.html" %}
      </nav>
    </aside>

    <main id="list-pane" class="min-w-0 border-e border-base-300 bg-base-100">
      <section id="message-list" aria-label="Mensajes"
               hx-get="{{ list_url }}"
               hx-trigger="mail:list-changed from:body"
               hx-swap="innerHTML">
        {% include "partials/_message_list.html" %}
      </section>
    </main>

    <section id="viewer-pane" class="min-w-0 bg-base-100">
      <div id="message-viewer" aria-live="polite">
        {% include "partials/_empty_state.html" with title="Ningún mensaje seleccionado" %}
      </div>
    </section>
  </div>

  <div id="compose-host"></div>
  <div id="modal-host"></div>
  <div id="toast-region" role="status" aria-live="polite" aria-atomic="false"
       class="fixed bottom-4 end-4 z-50 flex w-80 flex-col gap-2"></div>

  <script defer src="{% static 'vendor/htmx.min.js' %}"></script>
  <script defer src="{% static 'vendor/alpine-csp.min.js' %}"></script>
  <script type="module" src="{% static 'js/app.js' %}"></script>
</body>
</html>
```

Detalles que importan:

- `hx-headers` es JSON estático: HTMX lo parsea con `JSON.parse`, **no** con `eval`.
- `hx-history-elt` es un atributo bandera sobre el elemento que se snapshot; no lleva selector.
- **La shell se renderiza completa en servidor** (árbol de carpetas y lista incluidos). Por eso no hay `hx-trigger="load"` en `#folder-tree` ni en `#message-list`: sería una segunda petición redundante y dejaría un skeleton inservible sin JS. El `hx-get` de esos contenedores existe solo para refrescos por evento.
- `#message-list` tampoco lleva `hx-push-url`: la URL del shell ya es canónica al cargar; empujarla duplicaría la entrada de historial. Los enlaces de carpeta, los de mensaje y la paginación sí lo llevan.
- Los skeletons se reservan para contenido diferido real: el cuerpo del mensaje y el panel de composición.
- `aria-live="polite"` en `#message-viewer` es deliberadamente **bajo**: el foco se mueve al `<h1>` del mensaje, y el anuncio extenso lo hace el título, no todo el cuerpo.

### 4.2 Inventario de partials

| Partial | Devuelve | Contenedor que lo recibe |
|---|---|---|
| `partials/_app_header.html` | Barra superior: logo, buscador, botón redactar, menú de cuenta | Shell completo |
| `partials/_folder_tree.html` | `<ul role="tree">` con contadores | `#folder-tree` (`innerHTML`) |
| `partials/_folder_node.html` | Nodo recursivo con `aria-expanded` | Incluido por `_folder_tree` |
| `partials/_message_list.html` | Toolbar de selección + `<ul>` de filas + paginación | `#message-list` (`innerHTML`) |
| `partials/_message_row.html` | Fila `<li>` con checkbox, remitente, asunto, fecha, flags | `_message_list` u OOB |
| `partials/_pagination.html` | Enlaces `?page=` con `hx-get` | `_message_list` |
| `partials/_message_view.html` | Cabecera, acciones, banner de imágenes remotas, `#message-body` | `#message-viewer` (`innerHTML`) |
| `partials/_message_body.html` | Cuerpo sanitizado + lista de adjuntos | `#message-body` (`innerHTML`) |
| `partials/_attachment_list.html` | Enlaces de descarga y tamaños | `_message_body` |
| `partials/_compose.html` | `<dialog>`/panel de redacción completo | `#compose-host` |
| `partials/_compose_form.html` | Formulario con TO/CC/BCC, asunto, cuerpo, adjuntos | `_compose.html` |
| `partials/_recipient_field.html` | Campo de destinatario + chips | `_compose_form` |
| `partials/_recipient_suggestions.html` | Sugerencias de autocompletado (HTML, no JSON) | `#recipient-suggestions` |
| `partials/_settings_form.html` | Preferencias de UI | Página de ajustes |
| `partials/_modal_confirm.html` | `<dialog>` de confirmación | `#modal-host` |
| `partials/_toast.html` | Toast individual (lo clona el JS) | `#toast-region` |
| `partials/_empty_state.html` | Estado vacío con icono y texto | Lista/visor |
| `partials/_inline_error.html` | Error de validación de campo | Formulario afectado |
| `partials/_skeletons.html` | Skeleton del cuerpo y del compositor | `#message-body`, `#compose-host` |

**Convención:** cada partial declara su raíz con `data-partial="nombre"` y, si aplica, `data-page-title="..."`. Eso permite tests de contrato y actualización de título sin adivinar el DOM.

### 4.3 Vistas: shell o parcial

```python
# apps/core/http.py
def render_shell_or_partial(request, *, partial: str, full: str, context: dict, status: int = 200):
    is_htmx = request.headers.get("HX-Request") == "true"
    response = render(request, partial if is_htmx else full, context, status=status)
    response["Vary"] = "HX-Request"
    return response
```

- Misma URL, dos plantillas. Sin rutas `/partial/` paralelas: eso duplica el mapa de URLs y rompe el deep link.
- `Vary: HX-Request` es obligatorio si hay caché por delante (Redis de página o CDN), o el parcial se sirve a una navegación completa.
- Los tests comprueban ambas ramas (§11).

### 4.4 Responsive

- `lg`: carpetas + lista + visor.
- `< lg`: una sola columna. El servidor decide qué panel mostrar con `?view=list|message`; los enlaces llevan ese parámetro para que el deep link funcione sin JS.
- El árbol de carpetas en móvil se abre en un `<dialog>` (mismo partial `_folder_tree`, cargado bajo demanda). No se duplica el markup.
- Sin `hx-boost`: el control explícito de targets evita swaps inesperados en formularios.

---

## 5. Contratos HTMX globales

### 5.1 Cabeceras de respuesta

| Cabecera | Cuándo | Valor |
|---|---|---|
| `HX-Trigger` | Tras `settle` | JSON con eventos de negocio: `mail:list-changed`, `mail:flags-changed`, `mail:folders-changed`, `mail:sent`, `mail:draft-saved`, `mail:toast` |
| `HX-Trigger-After-Swap` | Cuando el listener necesita el DOM nuevo | Igual que arriba, para eventos que dependen de nodos recién insertados |
| `HX-Redirect` | Sesión caducada (401) o logout desde HTMX | `/login/?next=...` |
| `HX-Retarget` | Validación que debe pintarse en otro contenedor | Selector CSS concreto (`#compose-errors`) |
| `HX-Reswap` | Cuando el destino cambia de estrategia | `innerHTML` / `none` |
| `HX-Push-Url` | Navegación que debe entrar en historial | URL canónica |
| `Vary` | Siempre en respuestas duales | `HX-Request` |
| `Cache-Control` | Parciales con datos de correo | `private, no-store` |

**Nunca** se usa `HX-Trigger` para lanzar lógica de negocio en el cliente; solo para notificar. La fuente de verdad sigue siendo el servidor.

### 5.2 Catálogo de eventos

| Evento | Emisor | Consumidor | Payload |
|---|---|---|---|
| `mail:folders-changed` | Servidor (`HX-Trigger`) | `#folder-tree` | `{}` |
| `mail:list-changed` | Servidor | `#message-list` | `{"folder": "INBOX", "reason": "move"}` |
| `mail:flags-changed` | Servidor | Filas OOB / contadores | `{"uids": [1,2], "add": ["\\Seen"]}` |
| `mail:sent` | Servidor | Compositor (cierra), lista (refresh) | `{"folder": "Sent"}` |
| `mail:draft-saved` | Servidor | Compositor (indicador “Guardado”) | `{"at": "2026-10-22T10:00:00Z"}` |
| `mail:toast` | Servidor o JS | `toasts.js` | `{"level": "info|success|warning|error", "text": "..."}` |
| `mail:preference-changed` | Servidor | `theme.js` | `{"theme": "mail-dark", "density": "compact"}` |
| `mail:compose-close` | Componente `composer` | `compose/composer.js` | `{}` |
| `mail:compose-open` | Botón “Redactar” | `compose/composer.js` | `{"mode": "new|reply|forward", "uid": null}` |
| `mail:confirm` | `composer.js`, acciones destructivas | Componente `modal` | `{"message": "...", "action": "compose:discard"}` |
| `mail:confirm-accepted` | Componente `modal` | `confirm.js` | `{"action": "compose:discard"}` |
| `ui:view-changed` | Servidor (HTML) | `shortcuts.js` | `{"view": "list|message"}` |
| `session:expiring` | `session.js` | `toasts.js` | `{"minutes": 5}` |

### 5.3 Reglas de swap

1. **`innerHTML` por defecto.** `outerHTML` solo cuando el servidor devuelve el contenedor completo con su id (p. ej. el panel de composición).
2. **Un target por petición.** Nada de actualizar tres regiones con tres `hx-get` disparados por el mismo clic.
3. **Actualizaciones múltiples → OOB.** El servidor devuelve el fragmento principal y añade `<tr id="msg-123" hx-swap-oob="outerHTML">` para las filas afectadas.
4. **`hx-swap="none"`** para acciones sin representación visual inmediata (marcar leído, polling) que solo emiten eventos.
5. **`hx-sync`** en buscador y paginación: `hx-sync="#search-form:replace"` para abortar la petición anterior.
6. **`hx-indicator`** siempre apunta a un elemento con `aria-hidden="true"`; el estado accesible se anuncia por el toast o por `aria-busy`.
7. **`hx-disabled-elt="this"`** en botones de envío para evitar doble submit.
8. **Sin `hx-on`.** Cualquier efecto posterior va en `htmx.on(...)`.

### 5.4 Navegación y deep links

Los enlaces críticos llevan `href` real **y** atributos HTMX:

```html
<a href="{{ folder.url }}"
   hx-get="{{ folder.url }}"
   hx-target="#message-list"
   hx-swap="innerHTML"
   hx-push-url="true">{{ folder.name }}</a>
```

- Clic normal con JS: swap parcial y URL actualizada.
- Clic con modificador, o sin JS: navegación completa; el servidor devuelve la shell.
- Atrás/adelante: HTMX restaura el snapshot de `#app-shell`; el visor se re-pide si el snapshot no lo contiene (`refreshOnHistoryMiss`).
- Título: el partial raíz lleva `data-page-title`; `history-title.js` lo aplica en `htmx:afterSettle`. En navegación completa lo pone `<title>`.

### 5.5 Errores y sesión

| Situación | Respuesta | Efecto |
|---|---|---|
| Validación de formulario | `422` + partial con errores | Swap (configurado en `responseHandling`), foco al primer campo inválido |
| Conflicto de estado (UID ya no existe) | `409` + toast | El servidor emite `mail:list-changed`; la fila desaparece |
| IMAP caído | `503` + toast | No se rompe la shell; el error técnico va al log con `request_id` |
| Sesión caducada | `401` + `HX-Redirect` | Redirección completa a login con `next` validado |
| Adjunto demasiado grande | `413` (JSON en subida, HTML en formulario) | Toast específico, sin perder el resto del formulario |
| Error inesperado | `500` + partial de error | Toast genérico; nunca se filtra el mensaje IMAP |

El detalle técnico se registra con `logger.exception` y un `request_id` en el contexto; el usuario ve un identificador corto para soporte.

---

## 6. Contratos por interacción

### 6.1 Login y logout (sin HTMX)

```html
<form method="post" action="{% url 'accounts:login' %}" class="space-y-4" novalidate>
  {% csrf_token %}
  <input type="hidden" name="next" value="{{ next }}">
  <label class="label" for="id_email">Correo</label>
  <input class="input input-bordered w-full" id="id_email" name="email" type="email"
         autocomplete="username" required autofocus>
  <label class="label" for="id_password">Contraseña</label>
  <input class="input input-bordered w-full" id="id_password" name="password" type="password"
         autocomplete="current-password" required>
  {% if form.non_field_errors %}
    <p role="alert" class="text-error text-sm">{{ form.non_field_errors.0 }}</p>
  {% endif %}
  <button class="btn btn-primary w-full" type="submit">Entrar</button>
</form>
```

- `POST` → `303` a `/mail/` (o `next` validado con `url_has_allowed_host_and_scheme`).
- Credenciales incorrectas → `200` con el formulario y un mensaje genérico; **nunca** distinguir “usuario no existe” de “contraseña incorrecta”.
- Rate limit por IP + email con `django-ratelimit` sobre Redis: 5 intentos/minuto, bloqueo progresivo.
- `request.session.cycle_key()` tras autenticar; `SESSION_COOKIE_AGE = 8 * 3600`; `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`.
- Logout: `POST` con CSRF, `request.session.flush()`, `303` a `/login/`.

### 6.2 Shell y carpetas

| Elemento | Atributos exactos | Disparador | Destino / swap | Respuesta |
|---|---|---|---|---|
| `#folder-tree` | `hx-get="/mail/folders/" hx-trigger="mail:folders-changed from:body" hx-swap="innerHTML"` | Solo evento (la carga inicial viene renderizada) | `#folder-tree` / `innerHTML` | `_folder_tree.html` |
| Enlace de carpeta | `hx-get="/mail/folder/INBOX/" hx-target="#message-list" hx-swap="innerHTML" hx-push-url="true" hx-indicator="#list-spinner"` | `click` | `#message-list` | `_message_list.html` |
| Nodo expandible | `hx-get="/mail/folders/?parent=..." hx-trigger="click once" hx-target="#children-<id>" hx-swap="innerHTML"` | `click` | Hijos del nodo | `_folder_node.html` |

Las carpetas se cargan una vez y se refrescan por evento; no se hace polling del árbol.

### 6.3 Lista, paginación y búsqueda

| Elemento | Atributos exactos | Destino / swap | Notas |
|---|---|---|---|
| `#message-list` | `hx-get="{{ list_url }}" hx-trigger="mail:list-changed from:body" hx-swap="innerHTML"` | `#message-list` | Recarga del panel por evento; la carga inicial es render de servidor |
| Formulario de búsqueda | `hx-get="/mail/search/" hx-trigger="input changed delay:400ms, search" hx-target="#message-list" hx-swap="innerHTML" hx-push-url="true" hx-sync="this:replace" hx-include="#search-filters"` | `#message-list` | `changed` evita peticiones con la misma query; `replace` aborta la anterior |
| Paginación siguiente | `hx-get="{{ next_url }}" hx-target="#message-list" hx-swap="innerHTML" hx-push-url="true" hx-indicator="#list-spinner"` | `#message-list` | El enlace tiene `href` real |
| Fila de mensaje | `hx-get="/mail/message/{{ uid }}/" hx-target="#message-viewer" hx-swap="innerHTML" hx-push-url="true"` | `#message-viewer` | También `href` real |
| Checkbox de selección | `data-uid="{{ uid }}"` (sin HTMX) | — | `selection.js` |
| Barra de selección | `hx-post="/mail/messages/flags/" hx-swap="none" hx-include="#selection-fields"` | — | Campos ocultos con UIDs serializados por JS |

**Búsqueda:** el servidor recibe `q`, `folder`, `from`, `to`, `subject`, `has_attachment`, `date_from`, `date_to`, `unread`. El servicio traduce a `UID SEARCH` y devuelve el mismo partial; si el servidor IMAP no soporta `CHARSET UTF-8`, se degrada a búsqueda ASCII y se muestra un aviso discreto.

**Paginación:** `?page=N` con tamaño 50. El servidor no guarda la posición; el historial del navegador es la fuente.

### 6.4 Visor de mensaje

| Elemento | Atributos exactos | Destino / swap | Respuesta |
|---|---|---|---|
| `#message-viewer` | contenedor del partial | — | `_message_view.html` |
| Cuerpo lazy | `hx-get="/mail/message/{{ uid }}/body/" hx-trigger="load" hx-target="#message-body" hx-swap="innerHTML" hx-indicator="#body-spinner"` | `#message-body` | `_message_body.html` |
| Cargar imágenes remotas | `hx-post="/mail/message/{{ uid }}/remote-images/" hx-target="#message-body" hx-swap="innerHTML"` | `#message-body` | Cuerpo con URLs de proxy + banner eliminado |
| Adjunto | `<a href="/mail/message/{{ uid }}/attachment/{{ part }}/" download>` | — | `StreamingHttpResponse` |
| Responder / reenviar | `data-compose="reply" data-uid="{{ uid }}"` | — | `composer.js` abre el panel y pide el partial |

- El cuerpo se carga en una segunda petición para que la cabecera aparezca rápido en mensajes con adjuntos grandes.
- `BODY.PEEK[]` en el servicio: abrir no marca `\Seen`. El marcado ocurre por `POST /mail/messages/flags/` tras 2 s visibles o al interactuar, decisión del servidor.
- El HTML del cuerpo se sanitiza en servidor (`nh3`) y se inserta con `|safe` **solo** tras sanitizar. Nunca se sanitiza en cliente.
- `cid:` se reescribe a `/mail/message/<uid>/inline/<part>/`; `img-src 'self' data:` permite ambos.
- Los enlaces externos llevan `rel="noopener noreferrer"` y `target="_blank"`; el servidor puede reescribirlos a `/mail/link?u=...` si se quiere aviso de salida.

### 6.5 Flags, movimiento y borrado

| Acción | Elemento y atributos | Respuesta | Efecto en UI |
|---|---|---|---|
| Marcar leído | `hx-post="/mail/messages/flags/" hx-vals='{"add": ["\\Seen"]}' hx-swap="none" hx-disabled-elt="this"` | `200` + fila OOB + `HX-Trigger: {"mail:flags-changed": {...}}` | Fila se repinta; contador se actualiza por OOB |
| Marcar destacado | Igual con `{"add": ["\\Flagged"]}` o `{"remove": ["\\Flagged"]}` | Igual | Igual |
| Marcar no leído | `{"remove": ["\\Seen"]}` | Igual | Igual |
| Borrar | Botón emite `mail:confirm` (`action: "message:delete"`); al aceptar, `confirm.js` hace `hx-post="/mail/messages/delete/"` con `hx-vals='{"uids": [...]}'` | `204` + `HX-Trigger: {"mail:list-changed": {...}}` | Lista se recarga; toast “Movido a Papelera” |
| Mover | `hx-post="/mail/messages/move/"` con `hx-vals='{"dest": "Archive"}'` | `204` + `HX-Trigger` | Igual |
| Copiar | Igual, endpoint `copy` | `204` + toast | Sin recarga de lista |

**Por qué `hx-vals` estático y no `js:`:** los UIDs se renderizan en el atributo desde el servidor para acciones de una fila. Para selección múltiple, `selection.js` escribe campos ocultos y se usa `hx-include="#selection-fields"`; así no hay evaluación dinámica.

**OOB en flags:** la respuesta incluye la fila afectada y el contador:

```html
<tr id="msg-{{ uid }}" hx-swap-oob="outerHTML" class="...">...</tr>
<span id="unread-count" hx-swap-oob="true">{{ unread }}</span>
```

### 6.6 Redacción, adjuntos y envío

| Elemento | Atributos exactos | Destino / swap | Respuesta |
|---|---|---|---|
| Botón “Redactar” | `data-compose="new"` | — | `composer.js` hace `hx-get="/compose/new/"` a `#compose-host` |
| `#compose-host` | `hx-target="#compose-host" hx-swap="outerHTML"` en el enlace que lo llena | — | `_compose.html` |
| Formulario | `hx-post="/compose/send/" hx-target="#compose-host" hx-swap="outerHTML" hx-disabled-elt="find button[type=submit]"` | `#compose-host` | `204` + `HX-Trigger: mail:sent` o `422` con errores |
| Autoguardado | `hx-post="/compose/draft/" hx-trigger="draft-save" hx-swap="none" hx-include="closest form"` | — | `204` + `HX-Trigger: mail:draft-saved` |
| Adjuntar | `<input type="file" multiple>` (sin HTMX) | — | `uploader.js` XHR a `/compose/attachments/` |
| Autocompletar destinatario | `hx-get="/compose/recipients/?q=..." hx-trigger="input changed delay:250ms" hx-target="#recipient-suggestions" hx-swap="innerHTML"` | Lista de sugerencias | `_recipient_suggestions.html` |

**Subida de adjuntos (excepción JSON documentada):**

```http
POST /compose/attachments/
Content-Type: multipart/form-data
X-CSRFToken: <token>
```

```json
// 201 Created
{ "id": "att_7f3c", "name": "informe.pdf", "size": 482133, "content_type": "application/pdf" }
```

- `uploader.js` usa `XMLHttpRequest` porque `fetch` no expone progreso de subida.
- El servidor guarda el adjunto en la sesión (o en Redis con TTL 1 h) y devuelve un id opaco; el formulario solo envía `attachment_ids`.
- Límite doble: `DATA_UPLOAD_MAX_MEMORY_SIZE` y `MAIL_MAX_ATTACHMENT_BYTES`; al superarlo, `413` JSON y toast.
- El autoguardado se dispara con debounce de 5 s desde `composer.js` (`input` → `htmx.trigger(form, "draft-save")`); no usa `every` para no escribir borradores vacíos.
- `#compose-host` vive **fuera** de `#app-shell`: ningún swaps de lista, visor o carpetas puede destruir un borrador abierto. Por eso no hace falta `hx-preserve`.

**Cerrar el compositor:** `mail:sent` o `Escape`; si hay cambios sin guardar, `<dialog>` con dos opciones: descartar o seguir editando. El borrador ya se autoguarda cada 5 s, así que “guardar y cerrar” no es una tercera vía: se guarda solo.

### 6.7 Preferencias y tema

| Elemento | Atributos exactos | Destino / swap | Respuesta |
|---|---|---|---|
| Toggle de tema | `hx-post="/settings/theme/" hx-vals='{"theme": "mail-dark"}' hx-swap="none"` | — | `204`; el servidor guarda y el cliente aplica `document.documentElement.dataset.theme` desde `HX-Trigger` o recarga |
| Densidad | `hx-post="/settings/density/" hx-vals='{"density": "compact"}' hx-swap="none"` | — | `204`; `data-density` se actualiza en cliente |
| Formulario de preferencias | `hx-post="/settings/" hx-target="#settings-form" hx-swap="outerHTML"` | `#settings-form` | `_settings_form.html` con estado guardado |

El tema se aplica en servidor al siguiente render; para el cambio inmediato, `theme.js` escucha `mail:preference-changed` y actualiza `data-theme`/`data-density` en `<html>`. Sin `localStorage` como fuente de verdad: la preferencia vive en PostgreSQL y la cookie solo recuerda el último valor para el primer render anónimo.

### 6.8 Polling y sesión

```html
<div id="mail-poller"
     hx-get="/mail/unread/"
     hx-trigger="poll"
     hx-swap="none"
     aria-hidden="true"></div>
```

```js
// polling.js
export function startPolling(el, intervalMs = 60_000) {
  const tick = () => {
    if (document.hidden) return;
    el.dispatchEvent(new CustomEvent("poll", { bubbles: true }));
  };
  const id = setInterval(tick, intervalMs);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) tick();
  });
  return () => clearInterval(id);
}
```

- El endpoint devuelve `204` sin cambios, o `200` con `HX-Trigger: {"mail:folders-changed": {}, "mail:list-changed": {}}` si el conteo de no leídos cambió.
- No se usa `hx-trigger="every 60s [!document.hidden]"` porque los filtros requieren evaluación.
- Aviso de expiración: `session.js` compara `data-session-expires-at` con `Date.now()` y emite `session:expiring` a los 5 minutos; el usuario puede renovar con `POST /session/extend/`.

---

## 7. Alpine: componentes permitidos

Solo cuatro componentes. Todos registrados con `Alpine.data` y usados como `x-data="nombre"`; la lógica vive en métodos, no en atributos.

### 7.1 `dropdown`

```js
// static/js/ui/dropdown.js
export function registerDropdown(Alpine) {
  Alpine.data("dropdown", () => ({
    open: false,
    toggle() { this.open = !this.open; },
    close() { this.open = false; },
    onKeydown(event) {
      if (event.key === "Escape") this.close();
    },
  }));
}
```

```html
<div x-data="dropdown" @keydown.escape.window="close()">
  <button type="button" class="btn btn-ghost" @click="toggle()"
          :aria-expanded="open" aria-haspopup="menu">Cuenta</button>
  <ul x-show="open" x-cloak @click.outside="close()" role="menu" class="menu ...">
    <li role="none"><a role="menuitem" href="{% url 'preferences:index' %}">Ajustes</a></li>
    <li role="none">
      <form method="post" action="{% url 'accounts:logout' %}">
        {% csrf_token %}
        <button role="menuitem" class="w-full text-start" type="submit">Cerrar sesión</button>
      </form>
    </li>
  </ul>
</div>
```

`x-show` alterna `display` vía CSSOM; no inyecta `<style>` ni atributos `style` en el HTML parseado, por lo que `style-src 'self'` no lo bloquea.

### 7.2 `modal`

```js
// static/js/ui/modal.js
export function registerModal(Alpine) {
  Alpine.data("modal", () => ({
    action: "",
    show(event) {
      const detail = event?.detail ?? {};
      this.action = detail.action ?? "";
      this.$refs.message.textContent = detail.message ?? "";
      this.$refs.dialog.showModal();
    },
    hide() { this.$refs.dialog?.close(); },
    accept() {
      this.hide();
      document.dispatchEvent(new CustomEvent("mail:confirm-accepted", {
        detail: { action: this.action },
      }));
    },
  }));
}
```

```html
<div x-data="modal" @mail:confirm.window="show($event)">
  <dialog x-ref="dialog" class="modal" aria-labelledby="confirm-title">
    <div class="modal-box">
      <h2 id="confirm-title" class="text-lg font-semibold">Confirmar</h2>
      <p class="py-4" x-ref="message"></p>
      <div class="modal-action">
        <button class="btn btn-ghost" type="button" @click="hide()">Cancelar</button>
        <button class="btn btn-error" type="button" @click="accept()">Continuar</button>
      </div>
    </div>
  </dialog>
</div>
```

`<dialog>` da foco atrapado y `Escape` gratis. `show($event)` recibe el detalle del evento, escribe el mensaje con `textContent` (nunca `innerHTML`) y abre el diálogo. `confirm.js` escucha `mail:confirm-accepted` y ejecuta la acción asociada (`action: "compose:discard"`, `"message:delete"`, etc.). **No** se usa `x-html`.

### 7.3 `composer`

```js
// static/js/ui/composer.js
export function registerComposer(Alpine) {
  Alpine.data("composer", () => ({
    dirty: false,
    sending: false,
    markDirty() { this.dirty = true; },
    clearDirty() { this.dirty = false; },
    requestClose() {
      if (!this.dirty) {
        document.dispatchEvent(new CustomEvent("mail:compose-close"));
        return;
      }
      document.dispatchEvent(new CustomEvent("mail:confirm", {
        detail: {
          message: "Hay cambios sin enviar. ¿Descartar el borrador?",
          action: "compose:discard",
        },
      }));
    },
  }));
}
```

El panel usa `x-data="composer"` y `@input="markDirty()"`; el autoguardado exitoso limpia el flag mediante un listener de `mail:draft-saved` registrado en `app.js`.

### 7.4 `shortcutsDialog`

Solo abre/cierra el diálogo de atajos. La lógica de teclas está en `shortcuts.js` (§8.4).

**Prohibido en plantillas:** `x-html`, arrow functions, template literals, destructuring, spread, asignación a propiedades y cualquier global (`document`, `window`, `console`, `Math`, `JSON`, `new`). Esas operaciones van en métodos del componente.

---

## 8. Módulos JS vanilla

### 8.1 `app.js`

```js
// static/js/app.js
import { configureHtmx } from "./core/htmx-config.js";
import { initToasts } from "./core/toasts.js";
import { initSelection } from "./core/selection.js";
import { initShortcuts } from "./core/shortcuts.js";
import { initPolling } from "./core/polling.js";
import { initHistoryTitle } from "./core/history-title.js";
import { initConfirm } from "./core/confirm.js";
import { initTree } from "./core/tree.js";
import { initSession } from "./core/session.js";
import { initTheme } from "./core/theme.js";
import { initComposerPanel } from "./compose/composer.js";
import { initUploader } from "./compose/uploader.js";
import { registerDropdown } from "./ui/dropdown.js";
import { registerModal } from "./ui/modal.js";
import { registerComposer } from "./ui/composer.js";
import { registerShortcutsDialog } from "./ui/shortcuts-dialog.js";

document.addEventListener("DOMContentLoaded", () => {
  if (window.htmx) configureHtmx(window.htmx);
  initToasts();
  initSelection();
  initShortcuts();
  initPolling();
  initHistoryTitle();
  initConfirm();
  initTree();
  initSession();
  initTheme();
  initComposerPanel();
  initUploader();
});

document.addEventListener("alpine:init", () => {
  registerDropdown(window.Alpine);
  registerModal(window.Alpine);
  registerComposer(window.Alpine);
  registerShortcutsDialog(window.Alpine);
});
```

Sin `window.htmx` la configuración se omite y el resto de módulos degrada a enlaces reales; si Alpine no carga, `alpine:init` nunca se dispara y los componentes simplemente no existen. Ningún módulo asume que el otro esté presente.

### 8.2 `toasts.js`

- Escucha `mail:toast` en `document`.
- Crea `<div role="status">` (o `role="alert"` si `level === "error"`), inserta `textContent`, no HTML.
- Auto-cierre a los 6 s (errores: 10 s, con botón de cierre).
- Máximo 3 visibles; los demás se descartan.
- `prefers-reduced-motion` desactiva la animación de entrada.

### 8.3 `selection.js`

- `Set<number>` de UIDs; se limpia al cambiar de carpeta (`htmx:afterSwap` sobre `#message-list`).
- `change` delegado en `#message-list` para checkboxes con `data-uid`.
- Re-sincroniza checkboxes tras `htmx:afterSwap` (las filas nuevas nacen sin marcar).
- Escribe los UIDs en `#selection-fields` (`<input type="hidden" name="uids" value="1,2,3">`).
- Actualiza el contador de la toolbar y su `aria-live` (“3 mensajes seleccionados”).
- `Shift+clic` selecciona rango usando el orden DOM.

### 8.4 `shortcuts.js`

| Tecla | Acción | Condición |
|---|---|---|
| `c` | Redactar | Fuera de input/textarea/contenteditable |
| `/` | Foco al buscador | Igual |
| `j` / `k` | Siguiente / anterior mensaje | Lista visible |
| `Enter` | Abrir mensaje enfocado | Fila con foco |
| `r` | Responder | Visor abierto |
| `u` | Volver a la lista | Vista móvil |
| `?` | Diálogo de atajos | Siempre |
| `Escape` | Cerrar modal/panel | Siempre |

Implementación: `keydown` en `document`, guardas de contexto, `event.preventDefault()` solo cuando se actúa, y respeto de `event.ctrlKey/metaKey/altKey`. Nunca se dispara con el foco en un campo de texto.

### 8.5 `uploader.js`

- `input[type=file]` → `FormData` → `XMLHttpRequest`.
- Cabecera `X-CSRFToken` desde el meta.
- Barra de progreso con `role="progressbar"` y `aria-valuenow`.
- Cancelación con `xhr.abort()`; el servidor borra el temporal por TTL.
- Al completar, añade un chip con nombre, tamaño y botón de quitar; el chip guarda `data-attachment-id`.
- Reintento manual en error de red; no automático.

### 8.6 `history-title.js` y `composer.js`

- `history-title.js`: en `htmx:afterSettle`, lee `data-page-title` del partial raíz y actualiza `document.title`.
- `composer.js` (panel): abre el panel con `htmx.ajax("GET", url, { target: "#compose-host", swap: "outerHTML" })`; escucha `mail:sent` y `mail:compose-close`; gestiona el foco inicial (campo TO) y la restauración del foco al botón que abrió el panel.

### 8.7 Resto de módulos

| Módulo | Responsabilidad | Detalle |
|---|---|---|
| `core/confirm.js` | Ejecutar la acción confirmada | Escucha `mail:confirm-accepted`; mapa `action → función`. Para `message:delete` usa `htmx.ajax("POST", url, { values: {uids}, swap: "none" })`; para `compose:discard` cierra el panel y limpia el borrador. |
| `core/tree.js` | Navegación del árbol | Roving tabindex, flechas arriba/abajo/izquierda/derecha, `aria-expanded`, carga de hijos bajo demanda. |
| `core/session.js` | Aviso de expiración | Lee `data-session-expires-at` de `<body>`; emite `session:expiring` a los 5 minutos; `POST /session/extend/` renueva sin perder el borrador. |
| `core/theme.js` | Cambio inmediato de tema/densidad | Escucha `mail:preference-changed`; actualiza `document.documentElement.dataset.theme` y `.dataset.density`. La persistencia la hace el servidor. |

---

## 9. Accesibilidad

### 9.1 Estructura y foco

| Requisito | Implementación |
|---|---|
| Landmarks | `<header>`, `<nav aria-label="Carpetas">`, `<main>`, `<section aria-label="Mensajes">` |
| Skip link | Primer elemento del `<body>`, visible con foco |
| Título de página | `<h1>` en cada vista; el visor tiene el asunto como `<h1>` |
| Foco tras swap de mensaje | `viewer.js` enfoca `#message-viewer h1` (`tabindex="-1"`) solo si la acción vino por teclado |
| Foco tras swap de lista | Se conserva el foco en la carpeta o en el buscador; nunca se roba al usuario |
| Modales | `<dialog>` nativo; foco atrapado; retorno al elemento que abrió |
| Compositor | `<dialog>` o panel con `role="dialog" aria-modal="true"`; foco en TO al abrir |

### 9.2 Semántica

- Árbol de carpetas: `role="tree"` + `role="treeitem"` + `aria-expanded` + `aria-level`; navegación con flechas en `tree.js` (roving tabindex).
- Lista de mensajes: `<ul>` con un `<li>` por mensaje; el enlace principal es el asunto; el remitente y la fecha son texto, no enlaces.
- No leído: texto oculto (`<span class="sr-only">No leído</span>`) además del indicador visual; nunca solo color.
- Flags: `aria-pressed` en botones de destacado; `aria-label` explícito (“Marcar como destacado”).
- Adjuntos: `<a download>` con nombre y tamaño legibles; icono `aria-hidden="true"`.
- Progreso: `role="progressbar"` con `aria-valuemin/max/now` y `aria-label`.
- Toasts: `role="status"` para informativos, `role="alert"` para errores; sin `aria-live` duplicado en el contenedor y en el hijo.

### 9.3 Teclado y contraste

- Todo accionable es alcanzable con `Tab`; no hay `tabindex > 0`.
- `:focus-visible` con anillo de 2 px y offset 2 px; contraste mínimo 3:1 contra el fondo.
- Texto normal ≥ 4.5:1; texto grande ≥ 3:1. Los pares OKLCH de §2.3 se validan con `axe` y con un script de contraste en CI.
- `prefers-reduced-motion` desactiva transiciones y scroll suave.
- Zoom al 200 % sin pérdida de contenido; la lista usa `min-w-0` y `truncate` con `title` en asunto/remitente.

### 9.4 Pruebas manuales obligatorias

1. Recorrido completo solo con teclado: login → carpeta → mensaje → responder → enviar.
2. Lector de pantalla (NVDA o VoiceOver): anuncio de “3 mensajes seleccionados”, de toast de error y de mensaje abierto.
3. Zoom 200 % y 400 % en el visor.
4. Tema oscuro con contraste comprobado.

---

## 10. Rendimiento

| Medida | Objetivo | Cómo |
|---|---|---|
| CSS compilado | < 60 KB gzip | daisyUI con temas acotados, sin `@import` de componentes no usados; verificar `styles.css` final |
| JS propio | < 25 KB sin comprimir | Módulos pequeños, sin frameworks |
| Primer render de lista | < 500 ms con IMAP local | Skeletons + una sola petición de lista |
| Swap de carpeta | < 300 ms | Parcial sin layout, `fetch` de 50 UIDs |
| Peticiones por interacción | 1 | Sin `hx-trigger` múltiples ni polling del árbol |
| Imágenes | lazy | `loading="lazy"` + `decoding="async"`; proxy con caché `private, max-age=300` |
| Fuentes | 0 peticiones | Stack del sistema (`ui-sans-serif`, `system-ui`) |

- `whitenoise` con `CompressedManifestStaticFilesStorage`: nombres con hash, `Cache-Control: max-age=31536000, immutable`.
- HTML de parciales con `Cache-Control: private, no-store` (correo).
- No se sirve el CSS de daisyUI completo si no se usan todos los componentes: el `@source` acota el escaneo, pero los componentes de daisyUI se incluyen por uso de clase; revisar el tamaño en CI y fallar si supera el presupuesto.

---

## 11. Testing

### 11.1 Unitarios y de integración (pytest-django)

| Test | Qué comprueba |
|---|---|
| `test_partial_vs_full` | `HX-Request: true` → template partial; sin cabecera → shell; `Vary` presente |
| `test_htmx_csrf_required` | POST sin `X-CSRFToken` → 403; con token → 204 |
| `test_flags_oob` | Respuesta contiene `hx-swap-oob` de la fila y del contador, y `HX-Trigger` válido |
| `test_search_debounce_contract` | El partial de búsqueda no incluye `<html>` ni `<body>` |
| `test_session_expiry` | Sesión caducada → 401 + `HX-Redirect` en petición HTMX; 302 en navegación normal |
| `test_attachment_limit` | Fichero sobre límite → 413 y mensaje en JSON/HTML según endpoint |
| `test_csp_headers` | `script-src` sin `unsafe-eval`; `style-src` sin `unsafe-inline`; `frame-ancestors 'none'` |
| `test_no_inline_style` | Recorre plantillas y falla si aparece `style="` (excepto el admin) |
| `test_admin_csp_separada` | `/admin/` tiene su propia política y el webmail no se relaja |
| `test_html_sanitization` | `<script>`, `onerror`, `javascript:` eliminados del cuerpo renderizado |
| `test_theme_server_side` | `data-theme` y `data-density` salen del servidor, no de `localStorage` |

### 11.2 Contrato de plantillas

- Test que renderiza cada partial con un contexto mínimo y valida que la raíz tiene `data-partial` y los ids esperados (`#message-list`, `#message-viewer`, etc.).
- Test de “sin JS”: con `Client` sin cabecera `HX-Request`, cada URL de carpeta/mensaje devuelve 200 con `<html>` y enlaces reales.

### 11.3 E2E (Playwright)

| Escenario | Assertions clave |
|---|---|
| Login correcto | Redirección a `/mail/`, árbol de carpetas visible, foco en la lista |
| Login incorrecto | Mensaje genérico, sin distinguir usuario/contraseña, campo contraseña vacío |
| Navegación de carpetas | Swap sin recarga (`performance.navigation` intacto), URL actualizada |
| Atrás/adelante | Lista y visor coherentes; sin estados duplicados |
| Abrir mensaje | Cabecera inmediata, cuerpo lazy, foco en `<h1>`, `\Seen` aplicado |
| Flags | Fila y contador actualizados sin recargar; `aria-pressed` correcto |
| Mover a carpeta | Fila desaparece, toast, contador de destino actualizado |
| Búsqueda | Debounce real (≤ 2 peticiones al escribir rápido), resultados correctos |
| Redactar y enviar | Adjunto con progreso, envío, cierre del panel, mensaje en Enviados |
| Borrador | Autoguardado a los 5 s, indicador “Guardado”, recuperación tras recarga |
| Sesión caducada | Petición HTMX → redirección a login con `next` |
| Sin JS | Login, carpetas, lista y mensaje funcionan con recarga completa |

### 11.4 Accesibilidad automatizada

- `@axe-core/playwright` en login, shell, visor, compositor y ajustes; **0 violaciones críticas**.
- Test de teclado: `Tab` no queda atrapado; `Escape` cierra modales; `?` abre atajos.
- Test de contraste de tokens con `wcag-contrast` sobre los pares de §2.3.
- Test de `prefers-reduced-motion` con `page.emulateMedia({ reducedMotion: "reduce" })`.

### 11.5 Regresión visual (opcional)

Playwright con snapshots de lista, visor y compositor en claro/oscuro y densidad compacta/cómoda. Se marca como opcional porque el coste de mantenimiento es alto; si se activa, solo en CI nocturna.

---

## 12. Estructura de archivos

```text
config/
  settings/
    base.py
    dev.py
    prod.py
  urls.py
apps/
  core/
    http.py                 # render_shell_or_partial, request_id
    templatetags/
      ui.py                 # iconos, formato de fecha, clases condicionales
  accounts/
  mail/
  compose/
  preferences/
theme/                      # generado por django-tailwind
  static_src/
    src/
      styles.css
      daisyui.mjs
      daisyui-theme.mjs
  templates/
    base.html
templates/
  partials/
    _app_header.html
    _folder_tree.html
    _folder_node.html
    _message_list.html
    _message_row.html
    _pagination.html
    _message_view.html
    _message_body.html
    _attachment_list.html
    _compose.html
    _compose_form.html
    _recipient_field.html
    _recipient_suggestions.html
    _settings_form.html
    _modal_confirm.html
    _toast.html
    _empty_state.html
    _inline_error.html
    _skeletons.html
static/
  vendor/
    htmx.min.js
    alpine-csp.min.js
  js/
    app.js
    core/
      htmx-config.js
      toasts.js
      selection.js
      shortcuts.js
      polling.js
      history-title.js
      tree.js
      confirm.js
      session.js
      theme.js
    ui/
      dropdown.js
      modal.js
      composer.js
      shortcuts-dialog.js
    compose/
      uploader.js
      composer.js
  css/
    # solo overrides pequeños; el grueso lo genera Tailwind
```

**Regla:** `theme/templates/base.html` se reemplaza por `templates/base.html`; la app `theme` solo aporta CSS. Los partials viven en `templates/partials/` para que las cuatro apps los compartan sin depender de `core` como app instalada.

---

## 13. Riesgos y no-objetivos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Alpine CSP no soporta una expresión necesaria | Componente no funciona | Componentes con métodos; si falta, se pasa a vanilla JS. Nunca relajar CSP. |
| `allowEval=false` rompe un patrón HTMX copiado de un tutorial | Interacción muerta | Prohibir `hx-on`, filtros y `js:` en revisión; tests E2E cubren cada contrato |
| daisyUI crece de más | CSS lento | Presupuesto en CI; solo componentes usados |
| `<dialog>` y foco en navegadores antiguos | Accesibilidad degradada | Navegadores objetivo: últimas 2 versiones; polyfill no previsto |
| Historial de HTMX con estado obsoleto | Mensajes ya movidos reaparecen | `refreshOnHistoryMiss`, snapshots acotados a `#app-shell`, `no-store` |
| Proxy de imágenes como SSRF | Acceso a red interna | Lista blanca de esquemas, resolución DNS verificada, bloqueo de IP privadas, timeout y tamaño máximo |
| Tema en cookie y CSP | Parpadeo o bloqueo | Tema resuelto en servidor; sin script inline |
| Adjuntos en sesión Redis | Memoria | TTL 1 h, límite por usuario, limpieza al enviar/descartar |

**No-objetivos de Fase 3:** PGP/S/MIME, CardDAV, Sieve, notificaciones push, modo offline, aplicación móvil nativa, temas de usuario arbitrarios (solo claro/oscuro), editor WYSIWYG completo (se usa `contenteditable` con sanitización en servidor o textarea + Markdown, decisión de Fase 4).

---

## 14. Criterios de aceptación de la Fase 3

1. `python manage.py tailwind build` produce CSS determinista y `collectstatic` no falla con `ManifestStaticFilesStorage`.
2. La CSP del webmail no contiene `unsafe-eval` ni `unsafe-inline`; un test lo verifica.
3. Ninguna plantilla del webmail contiene `style="`, `hx-on`, filtros `[...]` ni `hx-vals="js:`; un test lo verifica.
4. Login funciona sin JS; navegación de carpetas, lista y mensaje funciona sin JS con recarga completa.
5. Con JS, abrir carpeta y mensaje no recarga la página; la URL y el título se actualizan.
6. Flags, movimiento y borrado actualizan fila y contador sin recargar y emiten los eventos documentados.
7. Compositor: adjunto con progreso, autoguardado, envío, cierre y confirmación de descarte.
8. Tema y densidad se aplican desde el servidor y cambian en caliente tras guardar.
9. `axe` sin violaciones críticas en las cinco vistas principales; recorrido completo solo con teclado.
10. Tests E2E de §11.3 en verde, incluido el escenario sin JS.

---

## 15. Siguiente paso

Con este documento, la Fase 3 queda especificada y las Fases 0–2 actualizadas con las decisiones confirmadas. El siguiente paso es **implementación**, en el orden del roadmap de §3.9:

1. Esqueleto Django + `django-tailwind` + CSP + login (iteración 1).
2. `mail`: carpetas, lista, visor, sanitización, adjuntos (iteración 2).
3. Flags, movimiento, caché Redis (iteración 3).
4. `compose` (iteración 4).
5. `preferences` y pulido visual/accesibilidad (iteración 5).

No se ha creado ningún archivo de proyecto: solo documentación.
