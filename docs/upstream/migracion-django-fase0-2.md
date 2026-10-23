# SnappyMail → Django: reconocimiento, arquitectura y plan (Fases 0–2)

**Repositorio analizado:** `/home/fquivera/Proyectos/snappymail-master`
**Versión del árbol:** `package.json` 2.38.2; árbol de desarrollo `snappymail/v/0.0.0`
**Versión observada en vivo:** demo oficial **2.38.3c** (`https://snappymail.eu/demo/`)
**Fecha del análisis:** 2026-10-22
**Alcance de este documento:** Fase 0 (reconocimiento), Fase 1 (informe de arquitectura) y Fase 2 (plan Django). La Fase 3 se entrega en `docs/migracion-django-fase3.md`, con los contratos HTMX y el sistema de diseño derivados de estas decisiones.

---

## 0. Resumen ejecutivo

1. SnappyMail **no es una aplicación Electron**. Es un cliente web PHP clásico con un frontend SPA escrito en JavaScript ES modules, empaquetado con Rollup y servido por el mismo `index.php`. REA no encontró ningún `asar`, `BrowserWindow`, `preload`, IPC ni bridge de contexto: todos los contadores de Electron salieron a cero.
2. El frontend habla con el backend mediante **un único endpoint JSON** (`?/Json/...`) con un sobre común `{Action, Result, code, message, messageAdditional, epoch}`, más endpoints auxiliares (`AppData`, `Raw`, `Upload`, `Css`, `Lang`, `Plugins`, `ProxyExternal`).
3. No hay base de datos para el correo. **Todo el estado del buzón vive en IMAP**; la UI y las identidades viven en archivos JSON dentro de `data/_data_/`; las sesiones IMAP se materializan en archivos con TTL; la caché es de ficheros (con plugins APCu/Redis/Memcache).
4. El backend tiene una arquitectura **Service → Actions → ServiceActions** con traits (`User`, `Admin`, `UserAuth`, `Messages`, `Folders`, etc.). `ServiceActions::ServiceJson()` es el punto exacto de serialización JSON y de validación CSRF.
5. REA permitió observar estáticamente **11 candidatos de endpoint** en los 11 módulos priorizados, el uso de `localStorage`/cookie `smctoken`, y confirmar la ausencia de Electron. El resto del mapa de endpoints se obtuvo por **lectura de código**, y así se marca en cada tabla.
6. La demo oficial 2.38.3c confirmó en runtime el login, `AppData`, `Folders`, `MessageList`, cookies, CSP y persistencia automática de preferencias. **No** se observaron `Message`, `Raw`, `Upload` ni envío; esos contratos siguen marcados como source-derived (§1.11).
7. Recomendación Django: **no replicar la ausencia de BD**. Usar PostgreSQL solo para preferencias de UI e identidades; el buzón queda en IMAP, la sesión y la caché en Redis, y la configuración de dominio en variables de entorno. La autenticación de usuarios finales **no debe pasar por `django.contrib.auth`**: sesión propia contra IMAP, y `contrib.auth` solo para el admin interno.

---

## 1. Fase 0 — Reconocimiento del terreno

### 1.1 Método y separación de evidencias

| Fuente | Qué se puede afirmar | Herramienta |
|---|---|---|
| REA `analyze_javascript_application` | Inventario y grafo estático de los módulos JS analizados, imports, endpoints candidatos, almacenamiento, ausencia de Electron | REA |
| REA `inspect_analysis_view` | Proyecciones de hechos del grafo: endpoints, storage, módulos | REA |
| REA `capture_browser_scenario` | Contrato observado en runtime: peticiones/respuestas, cabeceras, cookies, storage, orden de acciones | REA (navegador real) |
| Lectura de `dev/**/*.js` | Nombres de acciones, payloads concretos, URL builders, flujo de UI | Lectura de código |
| Lectura de `snappymail/v/0.0.0/app/**/*.php` | Dispatch, acciones, settings, sesiones IMAP, CSRF, CSP, JSON | Lectura de código |
| HAR/SAZ/PCAP | **No disponibles** en el repositorio | Búsqueda de archivos |
| Demo oficial `https://snappymail.eu/demo/` | Contrato real de la versión **2.38.3c** con cuenta `demo@snappymail.eu` | REA `capture_browser_scenario` |

> Regla aplicada en este documento: cuando una conclusión viene de REA estática se cita `evidence_id`; cuando viene de lectura de código se cita `archivo:línea`; cuando viene de la demo en vivo se cita `evidence_id` de `capture_browser_scenario`. Las tres categorías no se mezclan.

**Sobre Ghidra:** no aplica a este objetivo. SnappyMail es una aplicación PHP + JavaScript; no hay binario nativo, `.so`, `.dll`, Mach-O ni firmware que decompilar. El límite real es HTTP y el runtime del navegador, así que la herramienta correcta es captura de navegador/CDP y análisis de bundles, no desensamblado. Usar Ghidra aquí solo produciría conclusiones vacías o inventadas.

### 1.2 Evidencia REA: aplicación JavaScript

**Herramienta:** `tools.rea.analyze_javascript_application`
**Entrada:** `/home/fquivera/Proyectos/snappymail-master/dev`, `format="directory"`, `detail="summary"`, con 11 rutas priorizadas:

```
boot.js
Remote/AbstractFetch.js
Remote/User/Fetch.js
Remote/Admin/Fetch.js
Common/Links.js
App/User.js
App/Admin.js
Screen/User/MailBox.js
Screen/User/Login.js
Stores/User/App.js
Model/Message.js
```

**Evidencia devuelta:**

| Dato | Valor |
|---|---|
| `evidence_id` padre | `ev_541369e25f9169030a6b92ff9dd9367bbc687226928634bcf2f5ee447c12f236` |
| `evidence_id` vista summary | `ev_210113e92d8221513944f36513c3f00f7a91f706f80860fbf52f5a08bd5eaa20` |
| SHA-256 del árbol `dev/` | `8a932c05f1a4103ea191a422be6f1796e01957c72d5a82c754d840cb9614bfc3` |
| Archivos JS relevantes en inventario | **165** |
| Archivos JS parseados (selección) | **11** |
| Archivos no seleccionados | **154** |
| Nodos AST visitados | **6.908** |
| Hallazgos | **275** |
| Contenedores ASAR anidados | **0** |
| `parse_failures` | **0** |
| Cobertura del grafo | `partial` (explícita, con 154 archivos fuera de alcance y 3.616 incógnitas semánticas) |

**Contadores Electron devueltos por REA (todos cero):**

```
browser_windows: 0
explicit_web_preferences: 0
preload_entrypoints: 0
context_bridge_apis: 0
exposed_api_members: 0
ipc.operations: 0
ipc.literal_channels: 0
ipc.renderer_transmissions: 0
ipc.renderer_listeners: 0
ipc.main_handlers: 0
native_addon_bindings: 0
```

**Conclusión (REA):** no hay límite Electron que migrar. El frontend es una aplicación web pura; el único “boundary” relevante es HTTP mismo.

**Limitaciones declaradas por REA (importante para no sobreafirmar):**

- “Static imports, entrypoints, workers, endpoints, and storage relationships do not prove runtime execution.”
- “JavaScript and HTML were parsed as inert text; bundle bootstrap code was never executed.”
- “Caller-selected source analysis leaves 154 inventoried files outside analysis scope.”
- “Graph coverage is incomplete; unavailable facts remain explicit and must not be read as absence.”
- “The semantic graph contains static syntax observations and conservative relationship candidates.”

### 1.3 Evidencia REA: endpoints candidatos observados

**Herramienta:** `tools.rea.inspect_analysis_view`, vista `javascript-facts` con `where: {kinds: ["endpoint"]}`.
**Evidencia:** `ev_0849489c0d70387c57fe14040bf492bfac8a5894cecb2a7fdf518040f1a480a1` (11 filas, `exhausted=true`; corroborada por `ev_025241f07dea205adcd7778bf4c333dcbbc32b4236202b19a9c975ab4db089de`).

| # | Archivo:línea | Valor | Mecanismo | Autoridad / estado |
|---|---|---|---|---|
| 1 | `Model/Message.js:729` | `SMimeVerifyMessage` | `Remote.post` | static-relationship-inference / inferred, low |
| 2 | `Remote/User/Fetch.js:54` | `SettingsUpdate` | `request` | static-relationship-inference / inferred, low |
| 3 | `Model/Message.js:94` | `MessageSetKeyword` | `Remote.request` | static-relationship-inference / inferred, low |
| 4 | `boot.js:103` | `resource` (expresión no literal) | `fetch` | **ast-static-analysis / observed, exact** (destino parcial) |
| 5 | `App/User.js:205` | `AppDelayStart` | `Remote.request` | static-relationship-inference / inferred, low |
| 6 | `Remote/User/Fetch.js:28` | `Message` | `request` | static-relationship-inference / inferred, low |
| 7 | `Remote/Admin/Fetch.js:11` | `AdminSettingsUpdate` | `request` | static-relationship-inference / inferred, low |
| 8 | `App/User.js:280` | `ResealCryptKey` | `Remote.post` | static-relationship-inference / inferred, low |
| 9 | `App/User.js:152` | `Logout` | `Remote.request` | static-relationship-inference / inferred, low |
| 10 | `App/User.js:75` | `Version` | `Remote.request` | static-relationship-inference / inferred, low |
| 11 | `Model/Message.js:701` | `SMimeDecryptMessage` | `Remote.post` | static-relationship-inference / inferred, low |

**Lectura correcta:** REA confirma que en esos 11 módulos se construyen llamadas a esos nombres de acción. No confirma que sean todos los endpoints de la aplicación ni que se ejecuten siempre. El inventario completo de acciones del frontend se obtuvo por búsqueda de código: **101 nombres de acción distintos** en `dev/**/*.js` (ver §1.5).

### 1.4 Evidencia REA: almacenamiento en el navegador

**Herramienta:** `tools.rea.inspect_analysis_view`, vista `javascript-facts` con `where: {paths: ["boot.js"], kinds: ["storage"]}`.
**Evidencia:** `ev_5af302032d5b98a95208293bf4b4007cf356f36b2aa5ea533f1d60bc76d224d1` (19 filas de hechos para `boot.js` + `Remote/AbstractFetch.js`).

| Archivo:línea | Nombre | Tipo | Mecanismo |
|---|---|---|---|
| `boot.js:30` | `smctoken` | `local-storage` | `localStorage.getItem` |
| `boot.js:36` | `smctoken` | `local-storage` | `localStorage.setItem` |

Esto coincide con la lectura de `dev/boot.js:29-37`: el token se lee de cookie o `localStorage`, se genera con `crypto.getRandomValues(16)` y se escribe tanto en `localStorage` como en cookie `smctoken; path=/; samesite=strict`. Es un identificador de cliente, **no** la sal del CSRF: el CSRF de PHP se deriva de `smtoken` (anónimo) o del hash de la cuenta (`1-…`, `2-…`) (§1.9).

### 1.5 Mapa real de endpoints (REA + lectura de código)

El transporte tiene dos capas:

1. **Rutas de servicio PHP** (`Service*`), seleccionadas por el primer segmento de la query:
   - `Service::RunResult()` toma `QUERY_STRING`, lo parte por `&`, añade los segmentos `q[]` y hace `explode('/')` → `snappymail/v/0.0.0/app/libraries/RainLoop/Service.php:73-113`.
   - `Service<primerSegmento>` se invoca si existe (`Service.php:126-131`).
   - Ejemplos: `?/Json/...`, `?/AppData/...`, `?/Raw/...`, `?/Upload`, `?/Css/...`, `?/Lang/...`, `?/Plugins/...`, `?/ProxyExternal/...`, `?/CspReport`, `?/Ping`.
   - El panel admin se selecciona por host o por la clave `admin` en la URL (`Service.php:87-92`), y usa `ActionsAdmin` (`Service.php:100`).

2. **Acción JSON** dentro de `?/Json/`:
   - `ServiceJson()` lee `Action` del body JSON o de `aPaths[2]` en GET (`ServiceActions.php:73-90`).
   - Valida CSRF salvo para `Logout` (`ServiceActions.php:96-113`).
   - Resuelve `Do<Action>` por reflexión (`ServiceActions.php:120-138`).
   - Serializa con `Utils::jsonEncode` y añade `Action` y `epoch` (`ServiceActions.php:151-182`).

#### 1.5.1 Endpoints de arranque y transporte

| Método | Ruta observada | Entrada | Salida | Evidencia |
|---|---|---|---|---|
| GET | `./?/AppData/0/<random>/` | — | JSON de bootstrap: `Auth`, `title`, `System.version`, `System.token`, `System.webPath`, `System.webVersionPath`, idiomas, settings de cuenta, `accountHash`, etc. | `dev/boot.js:144`; `Actions.php:555-650`; `ServiceActions.php:500-503,627-638` |
| POST | `./?/Json/&q[]=/0/` | JSON `{Action, ...params}` o `FormData` con `Action` | Sobre JSON `{Action, Result, code?, message?, messageAdditional?, epoch}` | `dev/Remote/AbstractFetch.js:8,42-62`; `ServiceActions.php:73-182` |
| GET | `./?/Json/&q[]=/0/<Action>/&q[]=/<RawKey>` | `RawKey` = Base64 URL-safe de JSON | Igual sobre JSON | `dev/Common/Links.js:56`; `dev/Stores/User/Messagelist.js:334`; `Actions.php:931-944` |
| GET | `./?/Raw/&q[]=/0/Download/&q[]=/<RawKey>` | `RawKey` con referencia a adjunto | Binario (`Content-Disposition`) | `dev/Common/Links.js:32-44`; `ServiceActions.php:327-386` |
| GET | `./?/ProxyExternal/<base64url>` | URL externa codificada | Imagen proxy (solo `image/*`, 200) | `dev/Common/Links.js:46-50`; `ServiceActions.php:279-320` |
| POST | `./?/Upload` | `multipart/form-data` campo `uploader` | JSON de subida | `ServiceActions.php:203-267` |
| POST | `./?/UploadContacts` | `multipart/form-data` campo `uploader` (límite 5 MB) | JSON | `ServiceActions.php:269-272` |
| POST | `./?/UploadBackground` | `multipart/form-data` campo `uploader` (límite 1 MB) | JSON | `ServiceActions.php:274-277` |
| GET | `./?/Css/0/User/-/<theme>/<ts>/Hash/-/Json/` | Tema | CSS (o JSON si el último segmento es `Json`) | `dev/Common/Links.js:59`; `ServiceActions.php:451-499` |
| GET | `./?/Lang/0/App/<lang>/<version>/` | Idioma | JS con traducciones | `dev/Common/Links.js:66-70`; `ServiceActions.php:387-418` |
| GET | `./?/Plugins/...` | Plugin JS compilado | `application/javascript` | `ServiceActions.php:419-450` |
| POST | `./?/CspReport` | Reporte CSP | 204 | `ServiceActions.php:322-325` |
| GET | `./?/Ping` | — | `Pong` | `ServiceActions.php:528-536` |

#### 1.5.2 Acciones de usuario (las que consume el webmail)

La lista siguiente está verificada por lectura de las llamadas del frontend (101 acciones) y por los `Do*` del backend. Las filas marcadas **REA** tienen además evidencia estática de REA.

| Acción | Payload de entrada (claves relevantes) | Salida (`Result`) | Evidencia |
|---|---|---|---|
| `Login` | `Email`, `Password`, `language`, `signMe` | `AppData` de la cuenta (incluye `Auth: true`) | **REA** (`Login` en `View/User/Login.js` no estaba en la selección; la acción sí está en `Actions/User.php:36`); `UserAuth.php:142`; `Login.js:88-104` |
| `Logout` | — | `true` | **REA** `App/User.js:152`; `Actions/User.php:67` |
| `Version` | `{version}` | `true`/error de versión | **REA** `App/User.js:75` |
| `AppDelayStart` | — | `true` (GC de caché/sesiones) | **REA** `App/User.js:205`; `Actions/User.php:71-127` |
| `Folders` | — | Colección de `Object/Folder` | Lectura: `Actions/Folders.php:47-112`; `Model/FolderCollection.js:98-104`; `Imap/Folder.php:149-185` |
| `MessageList` | `folder`, `offset`, `limit`, `uidNext`, `sort`, `search`, `useThreads`, `threadUid`, `threadAlgorithm`; variante GET con `hash` y `RawKey` | `Collection/Message` con `totalEmails`, `totalThreads`, `offset`, `limit`, `search`, `sort`, `limited`, `folder` + mensajes | Lectura: `Actions/Messages.php:19-155`; `Stores/User/Messagelist.js:206-232`; `Mail/MessageCollection.php:60-75` |
| `Message` | `folder`, `uid`; variante GET `RawKey=[folder,uid,useThreads,accountHash]` | `Object/Message` completo: cabeceras, `html`, `plain`, adjuntos, flags, firmas PGP/S/MIME | **REA** `Remote/User/Fetch.js:28`; `Actions/Messages.php:465-587`; `Mail/Message.php:490-580` |
| `MessageSetSeen` | `folder`, `uids` (CSV), `setAction` (1=seen, 0=unseen) | `true` | Lectura: `Actions/Messages.php:419-422`; `Stores/User/Messagelist.js:400-410` |
| `MessageSetFlagged` | `folder`, `uids`, `setAction` | `true` | Lectura: `Stores/User/Messagelist.js:410-418` |
| `MessageSetDeleted` | `folder`, `uids`, `setAction` | `true` | Lectura: `Stores/User/Messagelist.js:418-427` |
| `MessageSetKeyword` | `folder`, `uids`, `keyword`, `setAction` | `true` | **REA** `Model/Message.js:94`; lectura `Model/Message.js:88-105` |
| `MessageSetSeenToAll` | `folder`, `threadUids`, `setAction` | `true` | Lectura: `Actions/Messages.php:424-450`; `View/User/MailBox/MessageList.js` |
| `MessageMove` | `fromFolder`, `toFolder`, `uids`, `markAsRead`, `learning` (`SPAM`/`HAM`) | `true` | Lectura: `Actions/Messages.php:612-680`; `Stores/User/Messagelist.js:530-555` |
| `MessageCopy` | `fromFolder`, `toFolder`, `uids` | `true` | Lectura: `Stores/User/Messagelist.js:533-538` |
| `MessageDelete` | `folder`, `uids` | `true` | Lectura: `Actions/Messages.php:588-610`; `Stores/User/Messagelist.js:552-558` |
| `SendMessage` | `identityID`, `from`, `to`, `cc`, `bcc`, `replyTo`, `subject`, `html`/`plain`, `draftInfo`, `inReplyTo`, `references`, `attachments` (mapa tempName→{name,inline,cId,location,type}), `saveFolder`, `dsn`, `requireTLS`, `readReceiptRequest`, `markAsImportant`, `autocrypt`, `linkedData`, `signed`, `encrypted` | `true` o error (`CantSendMessage`, `CantSaveMessage`) | Lectura: `Actions/Messages.php:157-260,974-1094`; `View/Popup/Compose.js:1485-1540` |
| `SaveMessage` | Igual que envío + `saveFolder`, `messageFolder`, `messageUid` | `{folder, uid}` | Lectura: `Actions/Messages.php:113-155`; `Compose.js:586-608` |
| `MessageUploadAttachments` | `attachments[]` con `RawKey` de mensaje/MIME index | `[{tempName, mimeType}]` | Lectura: `Actions/Messages.php:693-757`; `Compose.js` |
| `SettingsUpdate` | pares clave/valor de preferencias (ver §3.3) | `true` | **REA** `Remote/User/Fetch.js:54`; `Actions/User.php:129-241` |
| `AccountsAndIdentities` | — | Cuentas e identidades | Lectura: `Actions/Accounts.php:338`; `Common/UtilsUser.js` |
| `AccountSwitch` | `Email` | Datos de la cuenta | Lectura: `Actions/Accounts.php:253-261`; `View/User/SystemDropDown.js` |
| `AccountSetup` | datos de cuenta adicional | `true` | Lectura: `View/Popup/Account.js`; `Actions/Accounts.php` |
| `Suggestions` | `Query` | Sugerencias de contactos | Lectura: `Actions/User.php:243-258` |
| `Contacts`, `ContactSave`, `ContactsDelete` | según contacto | Contactos | Lectura: `Actions/Contacts.php` |
| `Filters`, `FiltersScriptSave`, `FiltersScriptDelete`, `FiltersScriptActivate` | script Sieve | Estado de filtros | Lectura: `Actions/Filters.php`; `dev/sieve.js` |
| `Pgp*`, `Gnupg*`, `SMime*` | claves, passphrase, partes MIME | Resultado criptográfico | **REA** varios (`PgpVerifyMessage`, `SMimeDecryptMessage`, `SMimeVerifyMessage`); lectura `Actions/Pgp.php`, `Actions/SMime.php` |
| `FolderCreate`, `FolderRename`, `FolderDelete`, `FolderClear`, `FolderSubscribe`, `FolderSettings`, `FolderSetMetadata`, `FolderACL`, `FolderSetACL`, `FolderDeleteACL` | `folder`, `parent`, `subscribe`, etc. | `true`/folder | Lectura: `Actions/Folders.php:114+` |

**Panel de administración** (misma capa, `ActionsAdmin`): `AdminLogin`, `AdminLogout`, `AdminAppData`, `AdminDomainList/Load/Save/Delete/Disable/Match/Test/Autoconfig/AliasSave`, `AdminSettingsGet/Set/Update`, `AdminPackagesList/Install/Delete`, `AdminPluginLoad/Disable/SettingsUpdate`, `AdminPasswordUpdate`, `AdminQRCode`, `AdminClearCache`, `AdminInfo`, `AdminUpgradeCore`, `AdminContactsTest`. Evidencia de lectura: `ActionsAdmin.php`, `Actions/Admin*.php`, `Remote/Admin/Fetch.js`; REA observó `AdminSettingsUpdate` en `Remote/Admin/Fetch.js:11`.

#### 1.5.3 Sobre JSON

`DefaultResponse` construye:

```json
{
  "Action": "MessageList",
  "Result": { "...": "..." },
  "code": 0,
  "message": "",
  "messageAdditional": "",
  "epoch": 1761120000
}
```

- Éxito: `Result` es el objeto/colección; `code` solo aparece en errores.
- Error de cliente: `Result=false`, `code` (p. ej. `101` token inválido, `102` auth, `104` conexión, `301` no se pudo guardar, `302` no se pudo enviar, `901` error IMAP, `903` argumento inválido, `999` desconocido).
- `ExceptionResponse` añade `ExceptionCode` (`Actions/Response.php:31-56`).
- `ServiceActions::ServiceJson` añade `Action` y `epoch` después de la acción (`ServiceActions.php:151-182`).
- El frontend **rechaza** la respuesta si `action !== data.Action` (`Remote/AbstractFetch.js:176-183`), lo que conviene preservar como comprobación de contrato.

### 1.6 Capturas de red e instancia

- **No hay** `.har`, `.saz`, `.pcap` ni capturas equivalentes en el repositorio. Búsqueda realizada con `find` sobre todo el árbol: el único `.min.js` encontrado es un plugin de ejemplo (`plugins/wysiwyg-example/static/example.min.js`).
- **No hay instancia local corriendo**: `ss -ltn` no muestra 8888 ni 80. El `docker-compose.yml` define `http://localhost:8888` (admin en `/?admin`), pero no se levantó.
- **Sí hay instancia oficial en vivo.** Se usó REA `capture_browser_scenario` en modo `launch` con `/usr/bin/google-chrome` (Chromium 156), perfil temporal aislado, viewport 1440×900, locale `es-ES`, y la cuenta pública `demo@snappymail.eu` / contraseña `demo`. La demo declara la versión **2.38.3c**.
- La captura es de **solo lectura**: login, carga de buzón, listado, apertura de compositor y cierre de diálogos. **No** se envió correo, **no** se borró nada, **no** se cambiaron preferencias, identidad ni contraseña.
- La captura de REA retiene peticiones y respuestas, pero **no** genera un HAR exportable; los `evidence_id` de la tabla §1.11 son la referencia reproducible. `inspect_analysis_view` no admite evidencia de `capture_browser_scenario` (error `unsupported_target`), así que el detalle se extrajo del resultado normalizado de cada captura.
- El login se confirmó con `Auth:true`; el buzón cargó y `MessageList` devolvió 3 mensajes. La demo abre automáticamente un `#V-PopupsIdentity` que bloquea clics; para el compositor hubo que cerrarlo y confirmar `#V-PopupsAsk`.

### 1.7 Backend PHP: arquitectura real

#### Capas

```
index.php
  └─ snappymail/v/0.0.0/include.php
      └─ Service::Handle()
          ├─ headers/CSP
          ├─ parsea query → aPaths
          ├─ elige Actions (usuario) o ActionsAdmin (admin)
          └─ ServiceActions→Service<segmento>()
              ├─ ServiceJson()  → Do<Action>()  → respuesta array → json_encode
              ├─ ServiceRaw()   → Raw<Action>() → stream/binario
              ├─ ServiceUpload()→ Upload()      → JSON
              └─ ServiceAppData()/Css()/Lang()/Plugins()/...
```

- `Service.php:73-113`: parseo de `QUERY_STRING` y `q[]`.
- `Service.php:87-92`: detección de admin por host o por clave `admin`.
- `Service.php:126-131`: dispatch a `Service<segmento>`.
- `ServiceActions.php:73-182`: `ServiceJson`.
- `Actions.php:8-16`: `Actions` compone los traits `Admin`, `User`, `UserAuth`, `Raw`, `Response`, `Localization`, `Themes`.
- `Actions/User.php:11-20`: el trait `User` compone a su vez `Accounts`, `Contacts`, `Filters`, `Folders`, `Messages`, `Attachments`, `Pgp`, `SMime`.
- `ActionsAdmin.php:8`: `class ActionsAdmin extends Actions` (hereda y añade el trait `Admin`).

**Punto exacto de serialización JSON:** `ServiceActions.php:151-182`. Antes, `Actions/Response.php:9-29` normaliza cualquier `JsonSerializable` (mensajes, carpetas, cuentas) y envuelve todo en `DefaultResponse`. Ahí es donde se decide el contrato `{Action, Result, ...}`.

#### Traits User/Admin

- `Actions\User` (trait) agrupa acciones de usuario y a su vez usa los traits de dominio (`Messages`, `Folders`, etc.).
- `Actions\Admin` (trait) agrupa las acciones de administración; `ActionsAdmin` extiende `Actions`.
- `Actions\UserAuth` concentra login, tokens, cookies y conexión IMAP.
- `Actions\Response` centraliza el sobre de respuesta y la conversión de objetos a JSON.
- `Actions\Raw` implementa descarga/visualización de adjuntos.

Esto es relevante para la migración: **cada “vista” PHP es en realidad una acción de un servicio de aplicación**, no un controlador REST. En Django conviene mantener esa separación como capa de servicios, no como vistas gordas.

### 1.8 Modelo de estado de SnappyMail

| Estado | Dónde vive | Evidencia |
|---|---|---|
| Configuración global | `data/_data_/_default_/application.ini` | `include.php:71`; `Config/Application.php:14` |
| Dominios | `data/_data_/_default_/domains/*.json`, `*.ini`, `*.alias` | `Providers/Domain/DefaultDomain.php:71-120` |
| Preferencias de cuenta | `<data>/<dominio>/<local>/settings` (JSON) | `Providers/Settings/DefaultSettings.php:12-48`; `Settings.php` |
| Preferencias “locales” (tema, layout, etc.) | `<data>/<dominio>/<local>/settings_local` | `DefaultSettings.php:12-48` |
| Sesión IMAP | `<data>/<dominio>/<local>/.sessions/<token>` (marcador `true`; TTL 3 h, `touch` en cada lectura) | `Actions/UserAuth.php:174-178`; `Providers/Storage/FileStorage.php:47-50,160-167` |
| “Recordarme” | `.sign_me/<uuid>` (30 días) + cookie `smremember` | `UserAuth.php:363-430`; `FileStorage.php:160-167` |
| Identidades | `<data>/<dominio>/<local>/identities` (JSON) | `Providers/Identities/FileIdentities.php:17-52` |
| PGP | `.pgp/` | `FileStorage.php:160-167` |
| Caché | `_data_/_default_/cache` (driver fichero por defecto; APCu/Redis/Memcache vía plugins) | `Actions.php:473-501` |
| Contactos | Opcional SQLite (`AddressBook.sqlite`) o CardDAV | `Api.php:122`; `Providers/AddressBook/*` |
| **Buzón** | **Solo IMAP**: carpetas, UIDs, flags, cuerpos, adjuntos, hilos, cuota, ACL, metadatos | `MailClient.php`, `ImapClient.php`; no hay tablas de correo |
| Envío | SMTP; no se persiste cola | `Actions/Messages.php:157+` |

**Conclusión:** SnappyMail no tiene BD para el correo. Es una decisión deliberada: el servidor IMAP es la fuente de verdad y el filesystem hace de almacén de sesión/preferencias. Django puede conservar esa premisa para el correo, pero **debe** añadir BD para preferencias/identidades/tokens, porque el filesystem no es fiable en un despliegue con contenedores efímeros o múltiples workers.

### 1.9 Flujo de autenticación IMAP

1. `DoLogin()` (`Actions/User.php:36-65`) llama a `LoginProcess()` (`UserAuth.php:142`).
2. `resolveLoginCredentials()` aplica plugins de mapeo (LDAP, custom-login-mapping, etc.) y devuelve `email`, `domain`, `imapUser`, `smtpUser`, `pass`.
3. `DomainProvider()->getByEmailAddress()` resuelve el dominio y su configuración IMAP/SMTP (`Domain.php:192-207`).
4. `MainAccount` guarda credenciales y `imapConnect()` (`UserAuth.php:445-470`) llama a `Account::ImapConnectAndLogin()` (`Model/Account.php:196-219`).
5. `ImapClient->Connect()` usa `Settings` (`MailSo/Imap/Settings.php`) y `SSLContext` (`MailSo/Net/SSLContext.php:24-48`): por defecto `verify_peer=true`, `verify_peer_name=true`, `allow_self_signed=false`, `security_level=1`.
6. Si el login IMAP funciona:
   - se escribe un marcador de sesión en `.sessions/<token>` (`UserAuth.php:174-178`);
   - se cifra la cuenta en la cookie `smaccount` (`SetAuthToken`, `UserAuth.php:328-332`);
   - opcionalmente se crea `.sign_me/<uuid>` y la cookie `smremember` (30 días) (`UserAuth.php:363-397`).
7. En cada petición, `getMainAccountFromToken()` (`UserAuth.php:250-320`) descifra `smaccount`, comprueba que el marcador de sesión existe en disco y, si no, invalida la cookie y lanza `InvalidToken`. La conexión IMAP se abre de forma perezosa en `initMailClientConnection()` (`Actions.php:918-935`), es decir, **se reabre por petición** (no hay pooling entre requests).
8. `Logout` borra `smaccount`/`smadditional`; el `signMe` se limpia con `ClearSignMeData()` (`UserAuth.php:421-428`).

**Cookies:**

- `smctoken`: la genera el JS (`boot.js:29-37`), **no HttpOnly**, `SameSite=Strict`, 16 bytes aleatorios. No es la sal del CSRF; es un token de cliente para el transporte.
- `smtoken`: la genera el servidor (`Utils::GetConnectionToken()`), **HttpOnly, Secure, Strict**, 30 días. Es la sal del CSRF cuando no hay cuenta autenticada.
- `smsession`: marcador de sesión server-side; se contrasta con el valor guardado en `StorageType::SESSION` (`UserAuth.php:264-295`). Sin esta cookie, `smaccount` no basta y la sesión se invalida.
- `smaccount`, `smadditional`: cifradas (`Crypt::EncryptToJSON`), HttpOnly por `Cookies::setSecure`.
- `smremember`: cifrada, 30 días (fuera del alcance confirmado).
- `Cookies::set` parte valores > 4 KB en cookies `nombre~1`, `nombre~2` (`snappymail/cookies.php:104-140`).
- `SameSite` por defecto `Strict`, configurable; `Secure` si HTTPS o `SameSite=None` (`cookies.php:12-26`).

**CSRF (corregido con código + demo):**

- `Utils::GetCsrfToken()` delega en `GetConnectionToken()` (`Utils.php:69-91`).
- Sin cuenta: `'0-' . sha1('Connection'.APP_SALT.$smtoken.'Token'.APP_SALT)`.
- Con cuenta principal: `'1-' . sha1(APP_SALT.$oAccount->Hash())`.
- Con cuenta adicional: `'2-' . sha1(APP_SALT.$oAccount->Hash())`.
- Se envía como `X-SM-Token` en JSON o `XToken` en POST de formulario (`ServiceActions.php:96-113`). `Logout` está exento.
- `AppData` incluye `System.token` (`Actions.php:567`), que es el token que usa `rl.fetch` (`boot.js:101`). En la demo, el token pasa de `0-...` antes del login a `1-...` después.
- Consecuencia para Django: el token CSRF **no** debe derivarse solo de un valor de cliente; debe rotar al autenticar y validarse contra la sesión server-side.

**Cabeceras de seguridad (observadas en vivo, 2.38.3c):**

```
cache-control: no-store
server: SnappyMail
strict-transport-security: max-age=31536000
x-content-type-options: nosniff
x-frame-options: SAMEORIGIN
referrer-policy: no-referrer
x-xss-protection: 1; mode=block
content-security-policy:
  base-uri 'self'; default-src 'self' data:;
  script-src 'self' 'unsafe-eval';
  img-src 'self' data:; media-src 'self' data:;
  style-src 'self' 'unsafe-inline';
  connect-src 'self' data: keys.openpgp.org;
  frame-ancestors 'self'
```

- La demo difiere del valor por defecto del repositorio: usa `frame-ancestors 'self'` y `X-Frame-Options: SAMEORIGIN`, no `DENY`. En el repositorio, `X-Frame-Options: DENY` se emite si no hay `frame-ancestors` (`snappymail/http/csp.php:82-90`).
- `frame-ancestors 'self'` tiene precedencia sobre `X-Frame-Options` en navegadores modernos, así que la demo **sí permite framing same-origin**. Para Django se mantiene `frame-ancestors 'none'` + `X-Frame-Options: DENY`.
- En la página índice se inyecta un nonce en `nonce=""` (`Service.php:233-235`), pero la CSP observada sigue necesitando `'unsafe-eval'` y `'unsafe-inline'`. Django no debe copiar eso.
- En `Raw` se fuerza `Content-Security-Policy: script-src 'none'; child-src 'none'` (`ServiceActions.php:342`).
- La demo responde `500` en un recurso no identificado al abrir el buzón (consola del navegador); no afecta al contrato JSON y no se reprodujo en el login.

### 1.10 Limitaciones del reconocimiento

1. **La captura en vivo cubre login, bootstrap, carpetas, identidades, listado y compositor**, pero **no** cubre `Message`, `Raw`, `Upload`, envío SMTP ni adjuntos. Esos contratos siguen siendo lectura de código (§1.5, Anexo B).
2. **REA solo analizó 11 archivos priorizados**; el resto de módulos (154) queda fuera del grafo. El inventario de acciones (101) es de lectura de código, no de REA.
3. **La demo abre automáticamente `#V-PopupsIdentity`**, un diálogo que intercepta clics y explica los timeouts iniciales. Se cerró con confirmación `#V-PopupsAsk` para poder abrir el compositor. No se modificó la identidad.
4. **No se analizaron** PGP/S/MIME, Sieve, CardDAV, plugins de terceros ni el panel admin en profundidad; se documentan como alcance futuro.
5. **No hay Electron ni binario nativo**; Ghidra no aplica.

### 1.11 Evidencia en vivo — demo oficial 2.38.3c

**Herramienta:** `tools.rea.capture_browser_scenario` en modo `launch` (`/usr/bin/google-chrome`, Chromium 156, perfil temporal, headless). Todas las acciones fueron de solo lectura. La demo declara `System.version = 2.38.3c` y `webPath = /demo/`.

#### 1.11.1 Secuencia real de arranque autenticado

Tras el login, el frontend ejecuta, en este orden:

```
Login → AppData → Folders → SystemFoldersUpdate → AccountsAndIdentities
→ SMimeGetCertificates → MessageList → GnupgGetKeys → GetPGPKeys
→ SettingsUpdate (Resizer5Width) → SettingsUpdate (Resizer4Width)
```

- Todas las acciones JSON van a `POST /demo/?/Json/&q[]=/0/`.
- `AppData` va a `GET /demo/?/AppData/0/<random>/`.
- El orden no es casual: primero se resuelve la sesión y las carpetas, luego identidades/claves, luego la lista, y por último la UI persiste los anchos de los paneles.

#### 1.11.2 Login observado (exacto)

```http
POST /demo/?/Json/&q[]=/0/
Content-Type: application/json

{"Email":"demo@snappymail.eu","Password":"demo","language":"","signMe":"0","Action":"Login"}
```

Respuesta (recortada, claves relevantes):

```json
{
  "Action": "Login",
  "Result": {
    "Auth": true,
    "System": {
      "version": "2.38.3c",
      "token": "1-…",
      "webPath": "/demo/",
      "webVersionPath": "/demo/snappymail/v/2.38.3c/",
      "themes": ["Default", "A", "BlackWood", "…", "SquaresDark"],
      "allowAppendMessage": true
    },
    "Email": "demo@snappymail.eu",
    "accountHash": "d019581d…",
    "mainEmail": "demo@snappymail.eu",
    "MessagesPerPage": 20,
    "messageReadAuto": 1,
    "MessageReadDelay": 5,
    "MsgDefaultAction": 1,
    "Layout": 1,
    "useThreads": true,
    "ViewHTML": true,
    "ViewImages": "ask",
    "proxyExternalImages": true,
    "allowSpellcheck": false,
    "attachmentLimit": 2097152,
    "PluginsLink": "Plugins/0/User/59db9c24e50b3d50f96fa007a4a41756/"
  }
}
```

**Hallazgo de contrato:** el login devuelve **toda** la configuración efectiva de la cuenta, no solo un `Auth`. Django no necesita replicar ese acoplamiento: el login debe devolver identidad + token, y las preferencias deben venir de un endpoint/plantilla separada.

#### 1.11.3 Cookies y almacenamiento observados

| Cookie | Flags observados | Origen |
|---|---|---|
| `smctoken` | `path=/; SameSite=Strict`; **no HttpOnly**; escrita por JS | Cliente (`boot.js:29-37`) |
| `smtoken` | `expires=+30d; path=/; Secure; HttpOnly; SameSite=Strict` | Servidor (`GetConnectionToken`) |
| `smsession` | sesión server-side | Servidor (`GetSessionToken`) |
| `smaccount` | `path=/; Secure; HttpOnly; SameSite=Strict` | Servidor (`SetAuthToken`) |

`localStorage` observado: `smctoken`, `rlcsc`, `openpgp-private-keys`, `openpgp-public-keys`.

**Riesgo:** `smctoken` no es HttpOnly y se usa como identificador de cliente; cualquier XSS puede leerlo. En Django no hay equivalente: el CSRF token va en cookie/token server-side y la sesión es HttpOnly.

#### 1.11.4 `MessageList` observado (exacto)

Payload:

```json
{
  "folder": "INBOX",
  "offset": 0,
  "limit": 20,
  "uidNext": 0,
  "sort": "",
  "search": "",
  "useThreads": 1,
  "threadAlgorithm": "",
  "threadUid": 0,
  "Action": "MessageList"
}
```

Respuesta:

```json
{
  "Action": "MessageList",
  "Result": {
    "@Object": "Collection/MessageCollection",
    "@Collection": [
      {
        "@Object": "Object/Message",
        "folder": "INBOX",
        "uid": 29,
        "hash": "f9e1ec8160b2bb6d6a020952b74f71df",
        "subject": "foreignObject",
        "encrypted": false,
        "messageId": "<…@snappymail.eu>",
        "dateTimestamp": 1792684711,
        "from": [{"@Object": "Object/Email", "name": "test", "email": "demo@snappymail.eu"}],
        "to": [{"@Object": "Object/Email", "name": "", "email": "demo@snappymail.eu"}],
        "attachments": {
          "@Object": "Collection/AttachmentCollection",
          "@Collection": [{
            "@Object": "Object/Attachment",
            "folder": "INBOX", "uid": 29, "mimeIndex": "2",
            "mimeType": "image/svg+xml", "fileName": "foreignObject.svg",
            "estimatedSize": 27126, "cId": "", "isInline": false
          }]
        },
        "flags": ["\\seen"],
        "size": 38436,
        "preview": "foreignObject",
        "headers": {"@Object": "Collection/MimeHeaderCollection", "@Collection": []}
      }
    ],
    "totalEmails": 3,
    "totalThreads": 3,
    "offset": 0,
    "limit": 20,
    "folder": "INBOX"
  }
}
```

> Ejemplo recortado: la respuesta real incluye las 3 filas de `INBOX`, la colección completa de `headers` MIME y los adjuntos de cada mensaje. No se reproducen cabeceras con datos personales de la demo.

**Notas de diseño para Django:**

- `attachments` es una **colección serializada**, no un array plano. En Django será una lista de dataclasses/`dict`, no un `QuerySet`.
- `mimeIndex` identifica la parte MIME; es la clave para `fetch_part` y para descargar sin volver a parsear el mensaje completo.
- `hash` es el identificador de mensaje que usa el frontend para operaciones; no confundir con `uid`.
- La lista ya trae `preview` y `headers`; eso evita un `Message` extra para la vista de lista. Django puede hacer lo mismo con `BODY.PEEK[HEADER]` + `BODY.PEEK[TEXT]<0.N>` en una sola transacción.

#### 1.11.5 Compositor: acción de red ausente

Abrir el compositor vacío **no genera ninguna petición**. El compositor se construye en cliente con la identidad y la configuración que ya vinieron en `Login`.

Implicación: el `Compose`/`DoCompose` de SnappyMail no es “abrir formulario”, sino “cargar datos de un mensaje citado/reenviado/borrador”. En Django, `GET /compose/` puede renderizar el formulario desde la sesión sin tocar IMAP; solo `reply/forward/draft` necesita una lectura IMAP.

#### 1.11.6 Persistencia automática y material sensible

- Al cargar la lista, el frontend envía **dos** `SettingsUpdate` automáticos:
  - `{"Resizer5Width":504,"Action":"SettingsUpdate"}`
  - `{"Resizer4Width":220,"Action":"SettingsUpdate"}`
  Esto confirma que la UI persiste preferencias sin acción explícita del usuario. Django debe hacerlo con `PATCH`/`POST` pequeño y `debounce`, no con un “Guardar” global.
- `AccountsAndIdentities` devuelve la identidad con `smimeKey` (clave privada cifrada, `-----BEGIN ENCRYPTED PRIVATE KEY-----`). `IdentityUpdate` la reenvía en el body al guardar.
- **No reproducir ese diseño.** Una identidad no debe transportar clave privada al navegador en cada carga. En Django, PGP/S/MIME queda fuera del MVP (§3.10); si se añade, la clave debe quedarse en servidor/KMS y el cliente solo debe recibir metadatos y capacidades.

#### 1.11.7 Plugin por usuario

La demo carga `Plugins/0/User/59db9c24e50b3d50f96fa007a4a41756/` como script y lo usa para autocompletar el destinatario del compositor y la passphrase `demo`.

**No copiar:** ejecutar JavaScript por usuario bajo el mismo origen y con la CSP de la aplicación anula la separación de privilegios. En Django no habrá “plugins JS por usuario” en el MVP; si se necesita extensibilidad, será server-side y con permisos explícitos.

#### 1.11.8 Límites de esta captura

- `Message`, `Raw`, `Upload` y envío **no se observaron en vivo**. Se documentan desde código (§1.5) y se marcan como source-derived.
- El clic en una fila de mensaje completó la acción de Playwright pero no disparó `Message`; el diálogo de identidad y la semántica de selección de la demo lo impidieron. No se usa como evidencia de ausencia de endpoint.
- Un replay HTTP directo con `fetch` obtuvo `InvalidToken`/`CantGetMessage` por no disponer de `smsession`; se descartó y no se presenta como contrato.
- No se cambió ninguna preferencia, identidad, contraseña ni estado del buzón.

---

## 2. Fase 1 — Informe de arquitectura

### 2.1 Mapa de módulos JavaScript y responsabilidades

Inventario por lectura de `dev/` (165 archivos JS) y contraste con el grafo REA (393 registros de módulo en la vista, 560 totales de la vista; `exhausted=true`; evidencia `ev_2304180f3587d0adaf06c5ddecced8ea32debe1774d9d514bf45b9bd61c7a14b`).

| Grupo | Módulos representativos | Responsabilidad |
|---|---|---|
| Bootstrap | `boot.js`, `app.js`, `admin.js`, `bootstrap.js` | Generar `smctoken`, pedir `AppData`, cargar `libs.*` y `app.*`, arrancar la app. `boot.js` es el único punto que habla con el servidor antes de cargar el bundle. |
| Núcleo de app | `App/Abstract.js`, `App/User.js`, `App/Admin.js` | Ciclo de vida, pantallas, comandos globales, logout, version check, `AppDelayStart`, atajos. |
| Micro-framework | `Knoin/Knoin.js`, `Knoin/AbstractScreen.js`, `Knoin/AbstractViews.js`, `Knoin/AbstractModel.js` | Pantallas, popups, routing por hash, bindings tipo Knockout, composición de vistas. |
| Pantallas | `Screen/User/Login.js`, `Screen/User/MailBox.js`, `Screen/User/Settings.js`, `Screen/Admin/*` | Composición de la pantalla y carga de stores. |
| Vistas de usuario | `View/User/Login.js`, `View/User/MailBox/FolderList.js`, `MessageList.js`, `MessageView.js`, `View/User/Settings/*` | Render y eventos de la UI. |
| Composición | `View/Popup/Compose.js`, `View/Popup/Account.js`, `View/Popup/Contacts.js`, `View/Popup/Folder*.js`, `View/Popup/Identity.js` | Modales de redacción, cuentas, contactos, carpetas, identidades. |
| Modelos | `Model/Message.js`, `MessageCollection.js`, `FolderCollection.js`, `Account.js`, `Attachment.js`, `Email.js`, `Identity.js` | Espejo cliente de los `jsonSerialize()` del servidor; `reviveFromJson` reconstruye objetos. |
| Stores | `Stores/User/{Folder,Messagelist,Message,Settings,Account,Contact,Pgp,SMime,Sieve}.js`, `Stores/Theme.js`, `Stores/Language.js` | Estado observable de la UI; no es estado de servidor. |
| Transporte | `Remote/AbstractFetch.js`, `Remote/User/Fetch.js`, `Remote/Admin/Fetch.js` | `fetch` same-origin, cabecera `X-SM-Token`, `AbortController`, timeouts, reintento en error `111`, envoltura de errores. |
| URLs | `Common/Links.js` | Construcción de `?/Json`, `?/Raw`, `?/ProxyExternal`, `?/Css`, `?/Lang`, rutas hash `#/mailbox/...`. |
| Utilidades | `Common/Utils.js`, `Globals.js`, `Cache.js`, `Folders.js`, `Translator.js`, `Enums*.js`, `Consts.js` | Helpers, settings globales, caché de carpetas, i18n, enums. |
| MIME | `Mime/Parser.js`, `Mime/*` | Parseo/construcción de MIME en cliente (para PGP/S/MIME y previsualización). |
| Sieve | `Sieve/{Grammar,Parser,Commands,RegEx,Utils}.js`, `sieve.js` | Editor y parser de filtros Sieve. |
| Almacenamiento cliente | `Storage/Client.js`, `Storage/Passphrases.js` | Persistencia local de passphrases y preferencias. |
| Terceros | `External/ko.js`, `External/SquireUI.js`, `External/User/ko` | Knockout, editor Squire y bindings. |
| Service worker | `serviceworker.js` | Notificaciones de escritorio (click/close). |
| Estilos | `Styles/*`, `gulpfile.js`, `rollup.config.js` | Less/CSS y bundling; no es lógica de negocio. |

**Conclusión de responsabilidades:** la migración no necesita portar Knoin/Knockout. Sí necesita portar **contratos**: modelos (`Message`, `Folder`, `Attachment`), acciones (`Remote`), y la semántica de navegación (`#/mailbox/<folder>/p<page>/<search>`), no el framework.

### 2.2 Modelo de estado (persistido vs. solo IMAP)

| Estado | SnappyMail | Django propuesto |
|---|---|---|
| Mensajes, cuerpos, adjuntos | IMAP | **IMAP** (no se copian a BD) |
| Carpetas, UIDs, flags, \Seen, \Flagged, \Deleted, keywords | IMAP | **IMAP** |
| Hilos | IMAP `THREAD` o agrupación en servidor | **IMAP** (con fallback a agrupación por `References`/`Message-ID` en servicio) |
| Cuota, ACL, metadatos de carpeta | IMAP | **IMAP** |
| Preferencias de UI | `settings`/`settings_local` (JSON) | **PostgreSQL** (`MailPreference`) |
| Identidades | `identities` (JSON) | **PostgreSQL** (`MailIdentity`) |
| Dominios y configuración IMAP/SMTP | `domains/*.json` | **Entorno** (un dominio por despliegue); `MailDomain` en BD solo si se añade multi-dominio |
| Credenciales IMAP | Cookie cifrada + `.sessions` en disco | **Sesión Django cifrada en servidor** (Redis), sin persistencia de larga duración |
| “Recordarme” | `.sign_me/<uuid>` + cookie | **Descartado**: solo sesión, sin credenciales persistentes |
| Caché de listas/carpetas | Ficheros / APCu / Redis | **Redis** (`django-redis`) |
| Contactos | SQLite/CardDAV | Fase posterior (CardDAV o `Contact`) |
| Filtros Sieve | ManageSieve | **ManageSieve** (fase posterior) |
| Cola de envío | No existe | **No en MVP**; envío síncrono con error claro. Opcional `OutboxMessage` después |

**Regla de diseño:** la BD de Django **nunca** es la fuente de verdad del buzón. Si se cae Redis o PostgreSQL, el correo sigue siendo visible mientras IMAP esté disponible (salvo preferencias). Esto evita el error clásico de “sincronizar el correo a una BD” y conserva la principal virtud de SnappyMail.

### 2.3 Flujo de autenticación y requisitos de seguridad para Django

#### Lo que hay que replicar (contrato)

1. Login contra IMAP, no contra una tabla de usuarios.
2. Resolución de dominio por email según configuración de entorno (un dominio por despliegue).
3. Sesión con expiración absoluta y rotación de clave al autenticar.
4. Token CSRF ligado a una cookie de sesión, enviado en cabecera para XHR/HTMX.
5. CSP estricta, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`.
6. Cookies `HttpOnly` para credenciales, `SameSite`, `Secure` en HTTPS.
7. Redacción de secretos en logs.
8. Rate limiting de login y bloqueo progresivo.

#### Lo que hay que mejorar

| Riesgo en SnappyMail | Mejora Django |
|---|---|
| La cuenta IMAP completa viaja cifrada en una cookie de cliente (`smaccount`), aunque sea HttpOnly | **No enviar credenciales al cliente**. Guardar en la sesión de servidor (Redis/DB), cifradas con `FERNET_KEY`; el navegador solo lleva un `sessionid` opaco. |
| SnappyMail acepta un token de cliente (`smctoken`, no HttpOnly) y deriva el CSRF de `smtoken`/hash de cuenta; el token estático no rota por sí solo | Usar el CSRF de Django (cookie + `X-CSRFToken`) y `Origin`/`Referer`; rotar el token al login (`cycle_key`); `CSRF_COOKIE_HTTPONLY=False` para que HTMX lo lea, o incrustar `{{ csrf_token }}` en `hx-headers`. |
| `script-src 'unsafe-eval'` por Knockout | Alpine **CSP build** + HTMX con `allowEval=false`; CSP con nonce y `strict-dynamic`, sin `unsafe-eval`. |
| `style-src 'unsafe-inline'` | Mantener solo si daisyUI/Tailwind lo exige; idealmente nonce/hash para estilos críticos. |
| HTML de correo insertado en el DOM | Sanitizar con `nh3` (Rust, rápido) o `bleach`; política de imágenes remotas `ask/always/never`; proxy de imágenes con allowlist y bloqueo de IP privadas. |
| `ProxyExternal` acepta cualquier URL y hace `GET` | Validar esquema `http/https`, resolver DNS y bloquear rangos privados/loopback/link-local, limitar redirecciones (2), tamaño y content-type `image/*`; considerar descargar en worker. |
| Contraseña en logs si una clave no contiene “pass” | Filtro de redacción por lista de claves y por patrón; logs JSON estructurados; nunca `print`/`var_dump`. |
| Sesión sin regeneración explícita | `request.session.cycle_key()` en login; `SESSION_COOKIE_AGE`, `SESSION_EXPIRE_AT_BROWSER_CLOSE`, timeout absoluto. |
| `X-XSS-Protection` (obsoleto) | Eliminar; usar CSP y sanitización. |
| Sin rate limit nativo | `django-axes` o throttle por caché + `fail2ban` con formato de log; backoff exponencial y captcha opcional. |
| Sin 2FA para usuarios | Opcional TOTP (`django-otp`) o delegar en el proveedor IMAP/OAuth2. |
| Sin OAuth2 | Fase posterior: `imaplib`/`imapclient` con `AUTH=XOAUTH2` y refresh token cifrado. |

#### Contrato CSRF/HTMX propuesto

- `POST` siempre con `X-CSRFToken`.
- En la plantilla base:
  ```html
  <body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
  ```
- Para formularios no-HTMX, `{% csrf_token %}`.
- Validar `request.headers.get("HX-Request") == "true"` en vistas parciales para evitar que un GET directo devuelva un fragmento sin layout (o devolver el layout completo si no es HTMX).
- `LoginRequired` propio: `MailLoginRequiredMixin` que redirige a `/login/?next=...` y conserva `next` solo si es local.

### 2.4 Requisitos de seguridad adicionales para el visor de correo

1. **Sanitización HTML**: allowlist de tags/atributos; eliminar `script`, `iframe`, `object`, `embed`, `form`, `meta`, `link`, `style` peligroso, `on*`, `javascript:`, `data:` en `href`.
2. **Imágenes remotas**: por defecto `ask`; si `always`, proxy; si `never`, bloquear. Añadir `referrerpolicy="no-referrer"` y `loading="lazy"`.
3. **Adjuntos**: `Content-Disposition: attachment` salvo inline seguro (imágenes); `X-Content-Type-Options: nosniff`; nombres saneados; límite de tamaño; streaming por partes.
4. **Enlaces**: `rel="noopener noreferrer nofollow"`, `target="_blank"`, interceptar `mailto:` para abrir composición.
5. **iframe**: si se opta por aislar el HTML en iframe, `sandbox="allow-same-origin"` sin `allow-scripts`, y CSP propia; no mezclar con el DOM principal.
6. **Cabeceras**: `Content-Security-Policy`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` mínima.
7. **Adjuntos peligrosos**: aviso para `.exe`, `.js`, `.html`, `.svg`; no ejecutar; descarga forzada.

---

## 3. Fase 2 — Plan de proyecto Django

### 3.1 Apps Django y justificación

| App | Responsabilidad | Por qué separada |
|---|---|---|
| `accounts` | Login/logout IMAP, resolución de dominio desde entorno, sesión, `ImapService` (conexión), middleware/mixin de auth | Es el único punto que conoce credenciales y conexión. Aislarlo facilita auditoría, rate limiting y futura OAuth2. |
| `mail` | Carpetas, listado, búsqueda, visor, flags, movimiento, borrado, adjuntos, cuota | Dominio de lectura/estado del buzón. No debe depender de `compose`. |
| `compose` | Redacción, borradores, envío SMTP, identidades, subida de adjuntos, firmas | Ciclo de vida y riesgo distintos (MIME, SMTP, adjuntos). Permite probar envío sin montar el visor. |
| `preferences` | Preferencias de UI, tema, densidad, layout, tamaño de página, carpetas especiales, firma | Evita el nombre `settings` (colisiona con `django.conf.settings` y `settings.py`). Es configuración de presentación, no de correo. |
| `core` (opcional) | Plantilla base, partials compartidos, templatetags, middleware de request-id, healthcheck, filtros de logging | Evita duplicar layout/HTMX helpers entre apps. |

**Sobre el nombre `settings`:** Django permite una app llamada `settings`, pero es una mala idea: `from settings import ...` se confunde con `django.conf.settings`, y los principiantes rompen imports. Recomiendo el paquete `preferences` con `verbose_name = "Settings"` y URLs `/settings/`.

**Sobre `django.contrib.auth`:**

- **No** usarlo para usuarios finales. El usuario no existe como fila; existe en IMAP.
- **Sí** usarlo para `/admin/` interno (superusuario/staff) y para permisos de administración de dominios.
- Implementar `MailSessionMiddleware` + `MailLoginRequiredMixin`. Si más adelante se necesita `request.user`, se puede añadir un `ImapBackend` que cree/actualice un `User` “sombra”, pero **no es necesario en el MVP** y añade acoplamiento.

### 3.2 Capa de servicio

#### 3.2.1 Elección: `imapclient` + `email` estándar

**Recomendación: `imapclient` 3.x** para el protocolo, `email` (stdlib) para MIME, `nh3` para sanitización HTML, `charset-normalizer` para charsets rotos.

| Criterio | `imaplib` | `imapclient` |
|---|---|---|
| UID nativo | Manual (`UID FETCH`, `UID SEARCH`) | `use_uid=True` desde el constructor |
| Parseo de `FETCH` | Manual de literales y paréntesis | Devuelve dicts con `ENVELOPE`, `FLAGS`, `INTERNALDATE`, `RFC822.SIZE`, `BODY[]` |
| BODYSTRUCTURE / partes | Manual | `fetch` con `BODY.PEEK[...]`, helpers |
| IDLE | Hay que implementar hilos | `idle()`/`idle_check()` |
| Namespace, capability, ACL | Manual | Helpers |
| UTF-7 de carpetas | Manual | `folder_encode`/`folder_decode` |
| Dependencia | Stdlib | Tercero pequeño y mantenido |
| Riesgo | Más código propio y más bugs de protocolo | API más alta, pero menos control fino |

`imaplib` solo se justifica si hay una restricción de dependencias (“stdlib only”). Para un webmail real, el coste de reimplementar UID/FETCH/BODYSTRUCTURE no compensa. `imap-tools` es cómodo para scripts, pero **oculta** el acceso a partes MIME y a `BODYSTRUCTURE`, que el visor necesita; no lo usaría como capa principal.

**Diseño:**

```python
# apps/accounts/services/imap.py
@dataclass(frozen=True)
class MailAccount:
    email: str
    imap_host: str
    imap_port: int
    imap_security: Literal["ssl", "starttls", "none"]
    smtp_host: str
    smtp_port: int
    smtp_security: Literal["ssl", "starttls", "none"]
    verify_tls: bool = True
    timeout: int = 30

class ImapService:
    """Conexión IMAP por request. No guarda estado entre requests."""
    def __init__(self, account: MailAccount, username: str, password: str): ...
    def __enter__(self) -> "ImapService": ...
    def __exit__(self, *exc) -> None: ...
    def list_folders(self) -> list[Folder]: ...
    def select(self, folder: str) -> FolderStatus: ...
    def search(self, criteria: list[str], *, charset: str = "UTF-8") -> list[int]: ...
    def fetch_summaries(self, uids: Sequence[int]) -> list[MessageSummary]: ...
    def fetch_message(self, uid: int, *, peek: bool = True) -> FetchedMessage: ...
    def fetch_part(self, uid: int, part: str) -> Iterator[bytes]: ...
    def store_flags(self, uids, *, add=(), remove=()) -> None: ...
    def move(self, uids, dest: str) -> None: ...
    def copy(self, uids, dest: str) -> None: ...
    def delete(self, uids, *, expunge: bool = False) -> None: ...
    def append(self, folder: str, raw: bytes, flags=(), when=None) -> int: ...
    def quota(self) -> Quota: ...
```

**Reglas:**

- Una conexión por request (o por tarea). `imapclient` **no es thread-safe**; no compartir en `global`/`lru_cache`.
- `ssl.create_default_context()`; `verify_mode=CERT_REQUIRED`; `check_hostname=True`; nunca `verify=False`.
- Timeouts de socket y de operación; reintento solo en errores transitorios (`ABORT`, `NO` de servidor caído), nunca en `AUTHENTICATIONFAILED`.
- Errores de dominio: `ImapAuthError`, `ImapConnectionError`, `FolderNotFound`, `MessageNotFound`, `ImapProtocolError`; el mensaje al usuario es genérico, el detalle va al log.
- `BODY.PEEK[]` para no marcar `\Seen` al abrir; el marcado de leído es una acción explícita (o tras `MessageReadDelay`, como SnappyMail).
- Para listados grandes: `fetch` por lotes de UIDs (p. ej. 200), no `1:*` completo.
- Codificación de carpetas con `imapclient.folder_encode`; nombres IMAP en UTF-7 modificado.
- `IDLE` no en el MVP: para notificaciones, polling HTMX cada 60 s; luego worker ASGI/`IDLE` dedicado.

**`SmtpService`** separado en `compose/services/smtp.py`, con `smtplib.SMTP_SSL`/`starttls`, `verify` por `ssl_context`, timeout, y `send_message`. No reutilizar la conexión IMAP para SMTP.

**Servicios de dominio:**

- `mail/services/mailbox.py`: `MailboxService` usa `ImapService` y devuelve DTOs (`FolderDTO`, `MessageSummaryDTO`, `MessageDTO`), aplica paginación, orden, hilos, búsqueda y sanitización.
- `mail/services/rendering.py`: MIME → HTML seguro, `cid:` → `/mail/attachment/...`, quoted-printable/base64, charset fallback.
- `compose/services/compose.py`: construye `EmailMessage`/`MIMEMultipart`, adjuntos, firma, `In-Reply-To`/`References`, guarda en Sent/Drafts vía IMAP `APPEND`.
- `accounts/services/session.py`: cifra el payload de sesión, rota la clave al autenticar y aplica expiración absoluta.

### 3.3 Vistas y HTMX

> **Nota:** la Fase 3 (`docs/migracion-django-fase3.md` §0 y §6) refina esta sección: el login y el logout pasan a formularios POST clásicos, la carga inicial se renderiza en servidor y la paginación conserva `href` reales. La matriz siguiente sigue siendo válida para el resto de interacciones.

#### Principios

- **HTML parcial para todo lo navegable** (carpetas, lista, visor, paginación, búsqueda, ajustes).
- **JSON solo** para: subida de adjuntos con progreso (XHR), healthcheck y una futura API móvil. El autocompletado devuelve un parcial HTML (ver Fase 3 §0). No usar JSON+JS para pintar la UI principal.
- **CBV** para páginas completas y formularios (`TemplateView`, `FormView`, `ListView`, `UpdateView`); **FBV** cortas para parciales HTMX.
- **`LoginRequiredMixin`** solo en el admin interno; para el webmail, `MailLoginRequiredMixin`.

#### Matriz de vistas

| URL | Método | Tipo | Qué devuelve | HTMX |
|---|---|---|---|---|
| `/login/` | GET | HTML completa | `LoginView` (FormView) | — |
| `/login/` | POST | HTML/redirect | Valida IMAP, crea sesión, `HX-Redirect` o 302 | `hx-post`, `hx-target="this"`, `hx-swap="outerHTML"`; en éxito `HX-Redirect: /mail/` |
| `/logout/` | POST | 204/redirect | Cierra sesión | `hx-post`, `hx-swap="none"` + `HX-Redirect` |
| `/mail/` | GET | HTML completa | Shell: sidebar + toolbar + `#message-list` + `#message-viewer` | — |
| `/mail/folders/` | GET | Parcial | Árbol de carpetas + contadores | `hx-get`, `hx-trigger="load, mail:folders-changed from:body"`, `hx-target="#folder-tree"`, `hx-swap="innerHTML"` |
| `/mail/folder/<path>/` | GET | Parcial | Lista paginada + toolbar + paginación | `hx-get`, `hx-target="#message-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"`, `hx-indicator="#list-spinner"` |
| `/mail/folder/<path>/page/<n>/` | GET | Parcial | Ídem página n | `hx-get`, `hx-target="#message-list"`, `hx-swap="innerHTML"`, `hx-push-url="true"` |
| `/mail/search/` | GET | Parcial | Resultados de búsqueda | `hx-get`, `hx-trigger="input changed delay:400ms from:#search-input, search"`, `hx-target="#message-list"`, `hx-push-url="true"` |
| `/mail/message/<uid>/` | GET | Parcial | Visor del mensaje (cabecera, cuerpo, adjuntos) | `hx-get`, `hx-target="#message-viewer"`, `hx-swap="innerHTML"`; `hx-push-url="true"` opcional |
| `/mail/message/<uid>/body/` | GET | Parcial | Cuerpo lazy (si el visor carga primero cabecera) | `hx-get`, `hx-trigger="load"`, `hx-target="#message-body"`, `hx-swap="innerHTML"` |
| `/mail/message/<uid>/attachment/<part>/` | GET | Binario | Adjunto con `Content-Disposition` | — (enlace normal) |
| `/mail/messages/flags/` | POST | 204 + eventos | Aplica `\Seen`/`\Flagged`/`\Deleted`/keyword | `hx-post`, `hx-swap="none"`, `hx-vals`; respuesta `HX-Trigger: {"mail:flags-changed": {...}}` |
| `/mail/messages/move/` | POST | 204 + eventos | Mueve/copia | `hx-post`, `hx-swap="none"`; `HX-Trigger: mail:list-changed` |
| `/mail/messages/delete/` | POST | 204 + eventos | Borra | Ídem |
| `/mail/counts/` | GET | Parcial | Contadores de carpetas | `hx-get`, `hx-trigger="every 60s, mail:flags-changed from:body"`, `hx-target="#folder-counts"`, `hx-swap="outerHTML"` |
| `/compose/new/` | GET | Parcial (modal) | Formulario de composición | `hx-get`, `hx-target="#modal-root"`, `hx-swap="innerHTML"` |
| `/compose/reply/<uid>/` | GET | Parcial | Formulario citando | Ídem |
| `/compose/send/` | POST | Parcial/204 | Envía; errores de validación en el formulario | `hx-post`, `hx-target="#compose-form"`, `hx-swap="outerHTML"`; éxito `HX-Redirect` o `HX-Trigger: mail:sent` |
| `/compose/draft/` | POST | Parcial | Autosave de borrador | `hx-post`, `hx-trigger="every 20s, change from:#compose-form"`, `hx-swap="none"` |
| `/compose/upload/` | POST | JSON | Subida de adjunto (tempName) | XHR/fetch con `FormData` (no HTMX) |
| `/settings/` | GET | HTML completa | Página de ajustes | — |
| `/settings/<section>/` | GET | Parcial | Panel de sección | `hx-get`, `hx-target="#settings-panel"`, `hx-swap="innerHTML"` |
| `/settings/<section>/` | POST | Parcial | Guarda y devuelve panel + toast | `hx-post`, `hx-target="#settings-panel"`, `hx-swap="innerHTML"`; `HX-Trigger: settings:saved` |
| `/healthz` | GET | JSON | `{"status":"ok"}` | — |

**Contrato de errores HTMX:**

- Validación de formulario → `200` con el parcial y errores inline (no `400`, para que HTMX pueda swap).
- Error de sesión/IMAP → `401`/`502` con parcial de error y `HX-Retarget`/`HX-Reswap` si hace falta; el cliente muestra toast.
- Errores de servidor → `500` con partial genérico; log con `request_id`.

**`hx-*` clave:**

- `hx-boost="false"` en enlaces de descarga.
- `hx-indicator` en cada operación lenta (listado, envío, apertura).
- `hx-disabled-elt="this"` en botones de envío para evitar doble submit.
- `hx-confirm` solo para acciones destructivas (borrar carpeta, vaciar papelera); para el resto, modal Alpine.
- `hx-push-url="true"` en navegación de carpetas/búsqueda para conservar historial.
- `HX-Trigger` como bus de eventos entre parciales (evita orquestar con Alpine).

### 3.4 Modelos mínimos

Solo lo imprescindible. **No** modelar mensajes, carpetas ni flags.

```python
# apps/accounts/models.py
# Sin modelos. El dominio se resuelve desde configuración de entorno.
# (Decisión confirmada: un dominio por despliegue.)
```

> SnappyMail guarda los dominios en `domains/*.json` para permitir multi-dominio en un mismo despliegue. Aquí no se replica: `DJANGO_MAIL_DOMAIN`, `DJANGO_IMAP_HOST`, `DJANGO_SMTP_HOST` fijan el servidor en `config/settings/base.py`. Si en el futuro hace falta multi-dominio, se añade `MailDomain` junto con resolución por sufijo del email; el resto del diseño no cambia porque `MailAccount` ya es un DTO.

```python
# apps/preferences/models.py
class MailPreference(models.Model):
    account_key = models.CharField(max_length=64, unique=True, db_index=True)
    email = models.EmailField()
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.SYSTEM)
    density = models.CharField(max_length=8, choices=Density.choices, default=Density.COMPACT)
    page_size = models.PositiveSmallIntegerField(default=50)
    layout = models.CharField(max_length=8, choices=Layout.choices, default=Layout.SIDE)
    use_threads = models.BooleanField(default=False)
    html_allowed = models.BooleanField(default=True)
    remote_images = models.CharField(max_length=8, choices=RemoteImages.choices, default=RemoteImages.ASK)
    signature_html = models.TextField(blank=True)
    special_folders = models.JSONField(default=dict)  # sent/drafts/trash/archive/junk
    updated_at = models.DateTimeField(auto_now=True)
```

`account_key` se calcula de forma estable:

```python
def account_key(email: str, domain: str) -> str:
    return hashlib.sha256(f"{email.strip().lower()}|{domain.strip().lower()}".encode()).hexdigest()
```

> No se usa FK a `User` porque no hay usuario Django. Si mañana se añade `ImapBackend`, se puede añadir una FK opcional sin romper.

```python
# apps/compose/models.py
class MailIdentity(models.Model):
    account_key = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=255)
    email = models.EmailField()
    reply_to = models.EmailField(blank=True)
    signature_html = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account_key", "email"], name="uniq_identity_per_account")
        ]
```

> SnappyMail guarda identidades en `identities` (JSON) vía `FileIdentities`; en Django es un dato de usuario que merece BD y transacciones.

```python
# apps/accounts/models.py
# Sin modelo RememberMeToken.
# Decisión confirmada: solo sesión; cerrar el navegador exige login de nuevo.
```

> **Descartado explícitamente:** no se guardan credenciales ni tokens de larga duración. La contraseña IMAP vive únicamente cifrada en la sesión server-side (`SESSION_ENGINE` en Redis) y muere con ella. Esto elimina el `.sign_me` de SnappyMail y su superficie de robo de credenciales.

**Lo que deliberadamente no se modela:**

- `Message`, `Folder`, `Attachment`, `Flag`: viven en IMAP.
- `CachedMessage`: solo si se implementa caché persistente; en el MVP, Redis con TTL.
- `Outbox`: el envío es síncrono; una cola de reintentos es fase 2.
- `Contact`: CardDAV o tabla propia en fase posterior.

### 3.5 Configuración por entorno, logging y convenciones

#### `django-environ`

```
config/settings/base.py
config/settings/dev.py
config/settings/prod.py
```

Variables mínimas:

```
DJANGO_SECRET_KEY
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=mail.example.com
DATABASE_URL=postgres://...
REDIS_URL=redis://...
DJANGO_MAIL_DOMAIN=example.com
DJANGO_MAIL_IMAP_HOST=imap.example.com
DJANGO_MAIL_IMAP_PORT=993
DJANGO_MAIL_IMAP_SECURITY=ssl
DJANGO_MAIL_SMTP_HOST=smtp.example.com
DJANGO_MAIL_SMTP_PORT=465
DJANGO_MAIL_SMTP_SECURITY=ssl
DJANGO_MAIL_VERIFY_TLS=True
FERNET_KEY=...
DJANGO_LOG_LEVEL=INFO
```

`DEBUG` **nunca** hardcodeado; `ALLOWED_HOSTS` obligatorio en prod; `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS` en prod.

#### Logging estructurado

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
        },
    },
    "filters": {
        "request_id": {"()": "core.logging.RequestIdFilter"},
        "redact": {"()": "core.logging.RedactSecretsFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["request_id", "redact"],
        },
    },
    "loggers": {
        "apps.accounts": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps.mail": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps.compose": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "imapclient": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
```

- `RedactSecretsFilter`: redacta claves que contengan `pass`, `password`, `passphrase`, `token`, `authorization`, `cookie`, `secret`.
- `RequestIdFilter`: `X-Request-ID` o UUID; se devuelve en la respuesta.
- Prohibido `print`, `var_dump`, `console.log` de datos de usuario; `DEBUG` solo por env.
- Eventos de auditoría: `auth.login.success`, `auth.login.failure`, `mail.send.success`, `mail.send.failure`, `imap.error`, con `email_hash` (no email en claro si es política), IP, duración.

#### Convenciones Django

- CBV para páginas; FBV para parciales.
- `get_queryset`/`get_context_data` sin lógica de IMAP; la lógica va al servicio.
- `select_related`/`prefetch_related` solo en modelos propios (pocos).
- `transaction.atomic` en preferencias/identidades; **nunca** envolver una operación IMAP en una transacción de BD.
- `LoginRequiredMixin` para admin; `MailLoginRequiredMixin` para webmail.
- `django-environ` + `django-structlog` opcional; `django-htmx` para `HX-Request` y `HX-Redirect`.
- Tests con `pytest-django`; `factory_boy` para modelos; `responses`/`vcrpy` para HTTP; `GreenMail`/Dovecot en Docker para integración.

### 3.6 Estructura de proyecto propuesta

```
config/
  __init__.py
  settings/
    base.py
    dev.py
    prod.py
  urls.py
  asgi.py
  wsgi.py
apps/
  core/
    middleware.py
    logging.py
    templatetags/
  accounts/
    models.py
    services/
      imap.py
      session.py
    views.py
    urls.py
  mail/
    services/
      mailbox.py
      rendering.py
      attachments.py
    views/
      folders.py
      messages.py
      attachments.py
    urls.py
  compose/
    models.py
    services/
      compose.py
      smtp.py
      uploads.py
    views.py
    urls.py
  preferences/
    models.py
    forms.py
    views.py
    urls.py
templates/
  base.html
  login.html
  mail/
    shell.html
    _folder_tree.html
    _message_list.html
    _message_row.html
    _message_view.html
    _pagination.html
    _search.html
    _empty_state.html
  compose/
    _form.html
    _modal.html
  preferences/
    _panel.html
  partials/
    _toast.html
    _spinner.html
static/
  src/
    app.css
    app.js
```

### 3.7 Estrategia de caché y rendimiento

- **Redis** (`django-redis`), confirmado en el entorno objetivo, para caché y para `SESSION_ENGINE` (sesión server-side):
  - `mail:{account_key}:folders` TTL 60 s;
  - `mail:{account_key}:list:{folder}:{uidvalidity}:{query_hash}:{page}` TTL 30 s;
  - `mail:{account_key}:unread` TTL 30 s;
  - `mail:{account_key}:quota` TTL 300 s.
- Invalidar por evento: `mail:flags-changed`, `mail:list-changed`, `mail:sent`, `mail:folders-changed`.
- **No cachear cuerpos** en el MVP: tamaño, privacidad y complejidad de invalidación. Si se cachean, cifrados y con TTL corto.
- Listados: `fetch` por lotes, `BODY.PEEK[HEADER.FIELDS (...)]` para resúmenes, `BODYSTRUCTURE` solo al abrir.
- Búsqueda: `UID SEARCH` con `CHARSET UTF-8`; si el servidor no soporta, fallback a filtrado local sobre la página actual (documentar la limitación).
- Hilos: `THREAD REFERENCES`/`THREAD ORDEREDSUBJECT` si está disponible; si no, agrupar por `References` en el servicio.
- Paginación: `offset`/`limit` como SnappyMail; no cargar `1:*`.
- Adjuntos: streaming por `fetch_part`, no cargar el mensaje completo en memoria. Sin almacenamiento temporal propio en el MVP; tope configurable (`MAIL_MAX_ATTACHMENT_BYTES` y `DATA_UPLOAD_MAX_MEMORY_SIZE`) y respuesta `413` clara.

### 3.8 Testing y criterios de aceptación

**Unitarios:**

- `ImapService` con un fake/protocolo; errores de auth, timeout, `NO`, `BAD`.
- Parseo MIME: multipart/alternative, adjuntos, `cid:`, charsets raros, mensajes vacíos.
- Sanitización: `<script>`, `onerror`, `javascript:`, `data:`, SVG, `iframe`.
- Construcción de MIME: TO/CC/BCC, `In-Reply-To`, `References`, firma, adjuntos.
- Preferencias: claves válidas, rangos, defaults.

**Integración:**

- Dovecot/GreenMail en Docker: login, carpetas, listado, flags, movimiento, APPEND, búsqueda.
- HTMX: cada parcial devuelve el fragmento esperado y no el layout; `HX-Trigger` correcto.
- Seguridad: CSRF obligatorio, login requerido, redirección `next` segura, headers CSP, cookies.

**E2E (Playwright):**

- Login → carpeta → mensaje → responder → enviar (SMTP fake) → aparece en Sent.
- Búsqueda, paginación, cambio de tema, densidad.
- Error de IMAP muestra toast y no rompe la shell.

**Criterios de aceptación de la Fase 2:**

1. Un usuario puede autenticarse contra IMAP y ver sus carpetas.
2. Puede listar, paginar, buscar y abrir mensajes sin recarga completa.
3. Puede marcar leído/flag/borrar/mover y ver el estado reflejado.
4. Puede componer, adjuntar, guardar borrador y enviar.
5. Las preferencias persisten y se aplican.
6. CSP sin `unsafe-eval`, CSRF en todos los POST, HTML sanitizado, logs sin secretos.
7. Tests de integración IMAP y E2E en verde.

### 3.9 Roadmap por iteraciones

| Iteración | Entregable | Riesgo principal |
|---|---|---|
| 1 | Esqueleto Django, `accounts`, login IMAP, sesión, `ImapService.list_folders`, shell HTMX | Config TLS/STARTTLS y timeouts |
| 2 | `mail`: listado paginado, búsqueda, visor, sanitización, adjuntos | MIME/charset y HTML malformado |
| 3 | Flags, movimiento, borrado, contadores, caché Redis | Consistencia UID/EXPUNGE entre servidores |
| 4 | `compose`: formulario, adjuntos, borradores, envío SMTP, identidades | MIME, SMTP auth, límites |
| 5 | `preferences`, tema/densidad, atajos, accesibilidad | Tailwind/daisyUI y CSP |
| 6 | Endurecimiento: rate limit, auditoría, métricas, OAuth2, Sieve/CardDAV | Alcance y compatibilidad |

### 3.10 Decisiones confirmadas

Confirmadas antes de la Fase 3. Condicionan el alcance, así que no quedan abiertas:

| # | Decisión | Confirmado | Efecto en el diseño |
|---|---|---|---|
| 1 | Autenticación | **Solo password IMAP** | Sin OAuth2, sin scopes, sin refresh tokens. `MailAccount` queda preparado para añadir un `authenticator` futuro sin cambiar vistas. |
| 2 | Dominios | **Un dominio por despliegue** | Sin `MailDomain`; host/puerto/seguridad vienen de entorno. `MailAccount` se construye en `accounts/services/account.py`. |
| 3 | “Recordarme” | **Solo sesión, sin recordarme** | Sin `RememberMeToken`, sin `.sign_me`, sin credenciales de larga duración. Sesión en Redis con expiración absoluta. |
| 4 | Caché | **Redis disponible** | `django-redis` para caché y `SESSION_ENGINE`; rate limiting con `django-ratelimit` sobre Redis. |
| 5 | Adjuntos | **Streaming desde IMAP con límite** | Sin S3 ni disco temporal; `StreamingHttpResponse` + `fetch_part`; tope de tamaño y `413`. |
| 6 | PGP / S/MIME | **Fuera del MVP** | No se modela `PgpKey` ni `SmimeCert`; el visor muestra aviso “firma no verificada” en lugar de fingir verificación. |
| 7 | Contactos | **Tabla propia, fase posterior** | Sin CardDAV en el MVP; autocompletado desde historial de destinatarios y `MailIdentity`. |
| 8 | Stack de Fase 3 | **Tailwind + daisyUI + Alpine CSP + HTMX** | `django-tailwind`, Alpine build CSP-safe, HTMX sin `allowEval`; CSP sin `unsafe-eval`. |

**Consecuencias de seguridad asumidas:** al no haber “recordarme”, el usuario reintroduce la contraseña tras cerrar sesión; a cambio, no existe ningún almacén de credenciales de 30 días que robar. La sesión sigue siendo server-side y la contraseña IMAP nunca llega al navegador.

### 3.11 Ajustes derivados de la demo en vivo

La demo 2.38.3c confirma el modelo, pero también expone decisions que **no** conviene heredar:

| Observación en SnappyMail | Decisión en Django |
|---|---|
| `Login` devuelve toda la configuración de cuenta y `System.token` | `Login` devuelve solo identidad, token y `next`; preferencias en endpoint/plantilla aparte |
| `AccountsAndIdentities` devuelve `smimeKey` y `IdentityUpdate` la reenvía | PGP/S/MIME fuera del MVP; nunca enviar clave privada al navegador |
| `PluginsLink` ejecuta JS por usuario en el mismo origen | Sin plugins JS por usuario; extensibilidad server-side con permisos |
| `smctoken` no es HttpOnly y el cliente lo escribe | Sesión y CSRF en cookies HttpOnly + token server-side rotado al login |
| `frame-ancestors 'self'` y `X-Frame-Options: SAMEORIGIN` en la demo | `frame-ancestors 'none'` + `X-Frame-Options: DENY` |
| `script-src 'unsafe-eval'`, `style-src 'unsafe-inline'` | Alpine CSP build + HTMX `allowEval=false`; sin `unsafe-eval` |
| `SettingsUpdate` automático al mover resizers | Persistencia de preferencias con `POST` pequeño y `debounce`, sin “Guardar” global |
| `MessageList` ya trae `preview`, `headers` y adjuntos | Una sola lectura IMAP por página: headers + preview + estructura MIME |
| Abrir compositor vacío no hace red | `GET /compose/` renderiza desde sesión; solo reply/forward/draft leen IMAP |
| `smsession` es imprescindible; `smaccount` solo no autentica | Sesión server-side en Redis con ID HttpOnly; no confiar solo en cookie de cuenta cifrada |

---

## 4. Anexo A — Índice de evidencia REA

| `evidence_id` | Operación | Uso en este informe |
|---|---|---|
| `ev_541369e25f9169030a6b92ff9dd9367bbc687226928634bcf2f5ee447c12f236` | `analyze_javascript_application` (parent) | Grafo estático de `dev/`, cobertura, Electron, estadísticas |
| `ev_210113e92d8221513944f36513c3f00f7a91f706f80860fbf52f5a08bd5eaa20` | `inspect_analysis_view` summary | Resumen: 165 archivos, 11 parseados, Electron=0, cobertura parcial |
| `ev_2304180f3587d0adaf06c5ddecced8ea32debe1774d9d514bf45b9bd61c7a14b` | `inspect_analysis_view` javascript/modules | 393 registros de módulo (560 totales de la vista), rutas e imports |
| `ev_0849489c0d70387c57fe14040bf492bfac8a5894cecb2a7fdf518040f1a480a1` | `inspect_analysis_view` javascript-facts/endpoint | 11 endpoints candidatos con archivo:línea |
| `ev_025241f07dea205adcd7778bf4c333dcbbc32b4236202b19a9c975ab4db089de` | `inspect_analysis_view` javascript-facts/endpoint | Corroboración de los 11 endpoints |
| `ev_5af302032d5b98a95208293bf4b4007cf356f36b2aa5ea533f1d60bc76d224d1` | `inspect_analysis_view` javascript-facts (boot.js, AbstractFetch.js) | `smctoken` en `localStorage` (boot.js:30,36) y hechos de `fetch` |
| `ev_6d51713e1932ef86e7b22078e59c74aea5525e6a6f89c09efe029b8d91400ed5` | `capture_browser_scenario` (login demo) | Login real, `Auth:true`, carga de buzón |
| `ev_e2cd0949f2d75d99c500271977474f05363dd1968f2e35266ce887efe7ceca0a` | `capture_browser_scenario` (red login) | Peticiones/respuestas JSON, `AppData`, `MessageList`, cookies, storage |
| `ev_913e9a4ef151aaa66534e4f0af597559f5c42cec379f8fdd94e9610d8226cd9a` | `capture_browser_scenario` (cabeceras) | CSP, HSTS, `X-Frame-Options`, `Set-Cookie`, `Server` |
| `ev_cebd0d92c97baf7a300b129709288fd6b9da099cbdfd668e26b8bbffb76fa96d` | `capture_browser_scenario` (`MessageList` completa) | `@Collection`, `uid`, `hash`, adjuntos, flags, headers |
| `ev_44d29d6cb2f3565420df921dc7a7793b876fcbaa29e89210b7a5cb040bcc76ec` | `capture_browser_scenario` (login + defaults) | Configuración efectiva devuelta por `Login`, `Folders`, `PluginsLink` |
| `ev_05d8e9d7f52d05acb9f18ca51e057b65345d5a54c0d277c2455f53ffa1ee190d` | `capture_browser_scenario` (compositor) | Abrir compositor no genera acción de red |
| `ev_3e932561a34ed5ce5432b931aa849d516f5546e0f4eac1ba0a4f0564e72992ed` | `capture_browser_scenario` (bloqueo UI) | `#V-PopupsIdentity` intercepta clics |
| `ev_7c56c7c92d364e8f47042f7b3374e8f23676efb7d301ec6d778fd23b4e250164` | `capture_browser_scenario` (cierre diálogo) | Cierre de identidad y confirmación `#V-PopupsAsk` |
| `ev_0e72f2fbdd0e9d783c87f28cc39f51636d9050d3372de5bad14b42dea5ccc6aa` | `capture_browser_scenario` (clic mensaje) | Clic completado sin `Message`; límite de la demo |
| `ev_b26c41d0a19ca2adb576a1983c55d48127c688691d77e918a0bea2e6efb19a5a` | `capture_browser_scenario` (teclado) | `Escape/ArrowDown/Enter` sin apertura de mensaje |

**SHA-256 del artefacto raíz:** `8a932c05f1a4103ea191a422be6f1796e01957c72d5a82c754d840cb9614bfc3`.

## 5. Anexo B — Evidencia de código (no REA)

| Tema | Archivo:línea |
|---|---|
| Dispatch de servicios | `snappymail/v/0.0.0/app/libraries/RainLoop/Service.php:73-131` |
| Detección admin | `Service.php:87-100` |
| `ServiceJson` y CSRF | `ServiceActions.php:73-182` |
| Serialización JSON | `ServiceActions.php:151-182`; `Actions/Response.php:9-56` |
| Traits de acciones | `Actions.php:8-16`; `Actions/User.php:11-20` |
| Login | `Actions/User.php:36-65`; `Actions/UserAuth.php:142-219` |
| Tokens/cookies | `Actions.php:22-40`; `Actions/UserAuth.php:250-430`; `snappymail/cookies.php` |
| CSRF | `RainLoop/Utils.php:69-91` |
| Conexión IMAP/TLS | `Model/Account.php:196-219`; `MailSo/Net/SSLContext.php:24-48` |
| Settings en ficheros | `Providers/Settings/DefaultSettings.php:12-48`; `Providers/Storage/FileStorage.php:17-181` |
| Sesiones y TTL | `FileStorage.php:47-50,160-167`; `UserAuth.php:174-178` |
| Caché | `Actions.php:473-501` |
| CSP/cabeceras | `Service.php:29-39,233-235,254`; `snappymail/http/csp.php:17-90` |
| AppData | `Actions.php:555-650`; `ServiceActions.php:627-638` |
| Listado de mensajes | `Actions/Messages.php:19-155` |
| Mensaje | `Actions/Messages.php:465-587`; `MailSo/Mail/Message.php:490-580` |
| Envío | `Actions/Messages.php:157-260,974-1094` |
| Carpetas | `Actions/Folders.php:47-112`; `MailSo/Imap/Folder.php:149-185` |
| Identidades | `Providers/Identities/FileIdentities.php:17-52` |
| Frontend transporte | `dev/Remote/AbstractFetch.js:8,42-62,127-199`; `dev/boot.js:63-144` |
| Frontend URLs | `dev/Common/Links.js:32-70,123-150` |
| Frontend compose | `dev/View/Popup/Compose.js:1485-1540` |
| Frontend login | `dev/View/User/Login.js:88-104` |
| Frontend lista | `dev/Stores/User/Messagelist.js:206-232,334-418,530-558` |

---

## 6. Próximo paso

Las decisiones de §3.10 están confirmadas y contrastadas con la demo 2.38.3c (§1.11). La Fase 3 se detalla en `docs/migracion-django-fase3.md`:

- configuración de `django-tailwind` + daisyUI (temas claro/oscuro, densidad compacta, tokens CSS);
- plantilla base con bloques y partials (`_folder_tree`, `_message_list`, `_message_view`, `_compose_form`, `_toast`);
- uso de Alpine **solo** para estado local (menús, modales, toggles) y su convivencia con HTMX;
- contratos exactos de `hx-trigger`/`hx-swap` por interacción y eventos `HX-Trigger`;
- plan de pruebas E2E y de accesibilidad.

No se ha generado código de proyecto todavía, conforme a tu restricción.
