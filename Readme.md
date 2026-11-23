# captcha_v2_resolve

**By Vorem — v1.1.0**

[![Language: English](https://img.shields.io/badge/lang-English-2ea44f?style=for-the-badge)](#english)
[![Idioma: Español](https://img.shields.io/badge/idioma-Espa%C3%B1ol-c1272d?style=for-the-badge)](#spanish)

Universal reCAPTCHA v2 solver (audio challenge + Vosk). Works on any page. Runs on Linux and Termux, headless by default.

Resolvedor universal de reCAPTCHA v2 (audio challenge + Vosk). Funciona en cualquier página. Corre en Linux y Termux, headless por defecto.

---

<a name="english"></a>

# 🇬🇧 English

[⬆ Back to top](#captcha_v2_resolve) · [🇪🇸 Ir a Español](#spanish)

## Table of contents

- [What it is](#what-it-is)
- [What it solves](#what-it-solves)
- [Installation](#installation)
- [CLI usage](#cli-usage)
- [Library usage](#library-usage)
- [Arguments](#arguments)
- [Output](#output)
- [Errors](#errors)
- [Real limitations](#real-limitations)
- [Integration with other tools](#integration-with-other-tools)
- [Credits](#credits)
- [License](#license)

## What it is

`captcha_v2_resolve` is a command-line tool and Python library to solve **reCAPTCHA v2** (the "I'm not a robot" checkbox + audio challenge) on **any webpage**. It downloads the audio challenge, transcribes it locally with **Vosk** (offline, no API, free), fills the answer and verifies.

No 2captcha. No API keys. No cost per hit. Audio never leaves your machine.

- Headless by default (no browser window)
- Runs on Linux and Termux
- Uses `patchright` if installed (stealth), falls back to `playwright`
- Detects Google's `IpBlock` and fails clean instead of retrying forever

## What it solves

- Classic reCAPTCHA v2 checkbox + audio challenge
- Invisible reCAPTCHA v2 that appears after submit, click or event
- Multiple consecutive captcha rounds
- Complex flows: pre-filled inputs, intermediate buttons, modals, cookies, proxies
- `IpBlock` detection ("automated queries")

**Does not solve:** reCAPTCHA v3, hCaptcha, Cloudflare Turnstile, Arkose. v2 only.

## Installation

```bash
pip install playwright vosk
playwright install chromium

# recommended (stealth, fewer leaks)
pip install patchright
patchright install chromium

# ffmpeg
apt install -y ffmpeg     # debian / ubuntu / kali
pkg install ffmpeg        # termux

# vosk model (English, ~50 MB)
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

If `patchright` is installed, the tool uses it automatically. Otherwise it falls back to regular `playwright`.

## CLI usage

```bash
python3 captcha_v2_resolve --help
```

Every argument has a bilingual description (EN/ES). Examples cover the 6 most common patterns.

### 1. Captcha visible on page load

```bash
python3 captcha_v2_resolve https://example.com/form
```

### 2. Input + submit triggers the captcha

```bash
python3 captcha_v2_resolve https://example.com/login \
  --input 'input[name="user"]' --value 'john' \
  --submit 'button[type="submit"]'
```

### 3. Intermediate click (modal, "continue" button)

```bash
python3 captcha_v2_resolve https://example.com/page \
  --click '#open-modal' \
  --submit '#modal button[type="submit"]'
```

### 4. Cookies in, cookies out, JSON, screenshot on failure

```bash
python3 captcha_v2_resolve https://example.com/form \
  --cookies old.json --save-cookies new.json \
  --json --screenshot-on-fail fail.png
```

### 5. Residential proxy (avoid IpBlock)

```bash
python3 captcha_v2_resolve https://example.com/form \
  --proxy 'http://user:pass@host:8080'
```

### 6. Already solved (prior session)

```bash
python3 captcha_v2_resolve https://example.com/dashboard \
  --success-selector '#dashboard' \
  --cookies saved.json
```

If `#dashboard` appears before `--captcha-wait` seconds (default 10), the solver is skipped.

### 7. Debug with visible browser

```bash
python3 captcha_v2_resolve https://example.com/form --headed
```

## Library usage

Import `solve_captcha` in any Playwright project. Pass the page already open. Returns a dict.

```python
import asyncio
from playwright.async_api import async_playwright
from captcha_v2_resolve import solve_captcha

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        await page.goto("https://example.com/login")

        await page.fill('input[name="user"]', "john")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)

        result = await solve_captcha(
            page,
            model="vosk-model-small-en-us-0.15",
            max_rounds=5,
            verbose=False,
            timeout=60,
        )

        if result["ok"]:
            print("token:", result["token"])
        elif result["error"] == "ipblock":
            print("IP blocked — use a residential proxy")
        else:
            print("failed:", result["error"])

        await browser.close()

asyncio.run(main())
```

**Signature:**

```python
async def solve_captcha(
    page,                                   # Playwright Page (required)
    model="vosk-model-small-en-us-0.15",    # path to Vosk model
    max_rounds=5,                            # max captcha rounds
    verbose=False,                           # show spinner
    timeout=60,                              # max seconds
) -> dict:
    # {"ok": True,  "token": "..."}
    # {"ok": False, "error": "ipblock|captcha_failed|timeout"}
```

### Use on any page

The tool is not tied to any site. It detects Google reCAPTCHA iframes (`anchor` and `bframe`) on the page and acts. Any page using **reCAPTCHA v2** works with the same commands. Only `--input`, `--click`, `--submit` change per site.

| Page type | Selectors to use |
|---|---|
| Captcha visible on load | *(none)* |
| Form with input + button | `--input`, `--value`, `--submit` |
| Modal opener then captcha | `--click`, `--submit` |
| Captcha behind login | `--cookies` (prior session) + `--submit` |
| Already solved via prior session | `--success-selector`, `--cookies` |

## Arguments

| Argument | Description |
|---|---|
| `url` | target URL (required) |
| `--input` | CSS selector of input to fill before triggering captcha |
| `--value` | value to write into `--input` |
| `--click` | CSS selector to click before submit (modal, intermediate button) |
| `--submit` | CSS selector of the button that triggers the captcha |
| `--wait-selector` | CSS selector to wait for after navigation |
| `--wait-timeout` | `--wait-selector` timeout in seconds (default 15) |
| `--success-selector` | if present, assume captcha already solved and skip solver |
| `--check-selector` | CSS selector to verify destination after solve |
| `--captcha-wait` | seconds to wait for `--success-selector` before solving (default 10) |
| `--post-click-wait` | seconds after `--click` (default 1.5) |
| `--post-submit-wait` | seconds after `--submit` (default 3.0) |
| `--solve-timeout` | max seconds for the solve phase (default 90) |
| `--model` | path to Vosk model directory |
| `--max-rounds` | max captcha rounds (default 5) |
| `--proxy` | proxy URL (`http://host:port` or `socks5://host:port`) |
| `--cookies` | path to cookies JSON to load before navigating |
| `--save-cookies` | path to save cookies JSON after solve |
| `--user-agent` | custom User-Agent |
| `--locale` | browser locale (default `en-US`) |
| `--headed` | run with visible browser window |
| `--chrome-executable` | custom chromium/chrome executable path |
| `--screenshot-on-fail` | path to save screenshot if captcha fails |
| `--json` | output JSON (for piping) |
| `--quiet` | suppress banner and spinner |
| `--version` | print version |
| `--help` | bilingual help (EN/ES) |

## Output

**Success (text):**

```
OK
token: 03AGdBq24Jx8...
check: found
```

**Success (JSON):**

```json
{
  "ok": true,
  "token": "03AGdBq24Jx8...",
  "check_selector_found": true
}
```

**Error (text):**

```
ERROR: IP blocked by Google (automated queries)
```

**Error (JSON):**

```json
{"ok": false, "error": "captcha_failed"}
```

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | captcha solved (or already solved) |
| `1` | error |
| `130` | interrupted (Ctrl-C) |

## Errors

| error | Meaning |
|---|---|
| `ipblock` | Google blocked the IP ("automated queries") |
| `navigation_failed` | could not load the URL |
| `input_failed` | `--input` selector not found |
| `click_failed` | `--click` selector not found |
| `submit_failed` | `--submit` selector not found |
| `captcha_failed` | captcha appeared but not solved in `--max-rounds` |
| `timeout` | solve phase exceeded `--solve-timeout` |

## Real limitations

- **reCAPTCHA v2 only.** Not v3, hCaptcha, Turnstile, Arkose.
- **Depends on Google's audio endpoint.** If Google blocks the IP (`ipblock`), there is no browser-side bypass. You need to change IP (residential proxy or home network).
- **Vosk `small` model hits ~80–90%.** For higher accuracy use `--model vosk-model-en-us-0.22` (larger, slower).
- **Headless from a datacenter = frequent IpBlock.** Residential proxy or home IP recommended.

## Integration with other tools

Instead of duplicating the solver inside every project, import it:

```python
from captcha_v2_resolve import solve_captcha

result = await solve_captcha(page, verbose=False)
if not result["ok"]:
    return {"ok": False, "error": result["error"]}
token = result["token"]
```

## Credits

**captcha_v2_resolve v1.1.0 — By Vorem**

## License

MIT

---

<a name="spanish"></a>

# 🇪🇸 Español

[⬆ Volver arriba](#captcha_v2_resolve) · [🇬🇧 Go to English](#english)

## Índice

- [Qué es](#qué-es)
- [Qué resuelve](#qué-resuelve)
- [Instalación](#instalación)
- [Uso por CLI](#uso-por-cli)
- [Uso como librería](#uso-como-librería)
- [Argumentos](#argumentos)
- [Salida](#salida)
- [Errores](#errores)
- [Limitaciones reales](#limitaciones-reales)
- [Integración con otras herramientas](#integración-con-otras-herramientas)
- [Créditos](#créditos-1)
- [Licencia](#licencia)

## Qué es

`captcha_v2_resolve` es una herramienta de línea de comandos y librería de Python para resolver **reCAPTCHA v2** (el checkbox "no soy un robot" + audio challenge) en **cualquier página web**. Descarga el audio challenge, lo transcribe localmente con **Vosk** (offline, sin API, gratis), llena la respuesta y verifica.

Sin 2captcha. Sin API keys. Sin costo por hit. El audio nunca sale de tu máquina.

- Headless por defecto (sin ventana de navegador)
- Corre en Linux y Termux
- Usa `patchright` si está instalado (stealth), cae a `playwright` si no
- Detecta el `IpBlock` de Google y falla limpio en vez de reintentar sin sentido

## Qué resuelve

- reCAPTCHA v2 checkbox clásico + audio challenge
- reCAPTCHA v2 invisible que aparece tras submit, click o evento
- Múltiples rondas consecutivas de captcha
- Flujos complejos: input previo, botón intermedio, modal, cookies, proxy
- Detección de `IpBlock` ("automated queries")

**No resuelve:** reCAPTCHA v3, hCaptcha, Cloudflare Turnstile, Arkose. Solo v2.

## Instalación

```bash
pip install playwright vosk
playwright install chromium

# recomendado (stealth, menos leaks)
pip install patchright
patchright install chromium

# ffmpeg
apt install -y ffmpeg     # debian / ubuntu / kali
pkg install ffmpeg        # termux

# modelo vosk (inglés, ~50 MB)
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

Si `patchright` está instalado, la herramienta lo usa automáticamente. Si no, cae a `playwright` normal.

## Uso por CLI

```bash
python3 captcha_v2_resolve --help
```

Cada argumento tiene descripción bilingüe (EN/ES). Los ejemplos cubren los 6 patrones más comunes.

### 1. Captcha visible al cargar la página

```bash
python3 captcha_v2_resolve https://example.com/form
```

### 2. Input + submit que dispara el captcha

```bash
python3 captcha_v2_resolve https://example.com/login \
  --input 'input[name="user"]' --value 'john' \
  --submit 'button[type="submit"]'
```

### 3. Click intermedio (modal, botón "continuar")

```bash
python3 captcha_v2_resolve https://example.com/page \
  --click '#open-modal' \
  --submit '#modal button[type="submit"]'
```

### 4. Cargar cookies, guardar cookies, JSON, screenshot si falla

```bash
python3 captcha_v2_resolve https://example.com/form \
  --cookies old.json --save-cookies new.json \
  --json --screenshot-on-fail fail.png
```

### 5. Proxy residencial (evitar IpBlock)

```bash
python3 captcha_v2_resolve https://example.com/form \
  --proxy 'http://user:pass@host:8080'
```

### 6. Ya está resuelto (sesión previa)

```bash
python3 captcha_v2_resolve https://example.com/dashboard \
  --success-selector '#dashboard' \
  --cookies saved.json
```

Si `#dashboard` aparece antes de `--captcha-wait` segundos (default 10), el solver se salta.

### 7. Debug con navegador visible

```bash
python3 captcha_v2_resolve https://example.com/form --headed
```

## Uso como librería

Importás `solve_captcha` en cualquier proyecto Playwright. Le pasás la página ya abierta. Devuelve un dict.

```python
import asyncio
from playwright.async_api import async_playwright
from captcha_v2_resolve import solve_captcha

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = await browser.new_page()
        await page.goto("https://example.com/login")

        await page.fill('input[name="user"]', "john")
        await page.click('button[type="submit"]')
        await page.wait_for_timeout(3000)

        result = await solve_captcha(
            page,
            model="vosk-model-small-en-us-0.15",
            max_rounds=5,
            verbose=False,
            timeout=60,
        )

        if result["ok"]:
            print("token:", result["token"])
        elif result["error"] == "ipblock":
            print("IP bloqueada — usar proxy residencial")
        else:
            print("falló:", result["error"])

        await browser.close()

asyncio.run(main())
```

**Firma:**

```python
async def solve_captcha(
    page,                                   # Playwright Page (obligatorio)
    model="vosk-model-small-en-us-0.15",    # ruta al modelo Vosk
    max_rounds=5,                            # máximo de rondas
    verbose=False,                           # mostrar spinner
    timeout=60,                              # segundos máximos
) -> dict:
    # {"ok": True,  "token": "..."}
    # {"ok": False, "error": "ipblock|captcha_failed|timeout"}
```

### Uso en cualquier página

La herramienta no está casada con ningún sitio. Detecta los iframes de Google reCAPTCHA (`anchor` y `bframe`) en la página y actúa. Cualquier página con **reCAPTCHA v2** funciona con los mismos comandos. Solo cambian `--input`, `--click`, `--submit` según el HTML del sitio.

| Tipo de página | Selectores a usar |
|---|---|
| Captcha visible al cargar | *(ninguno)* |
| Form con input + botón | `--input`, `--value`, `--submit` |
| Botón que abre modal y adentro captcha | `--click`, `--submit` |
| Captcha detrás de login | `--cookies` (sesión previa) + `--submit` |
| Ya resuelto por sesión previa | `--success-selector`, `--cookies` |

## Argumentos

| Argumento | Descripción |
|---|---|
| `url` | URL objetivo (obligatorio) |
| `--input` | selector CSS del input a llenar antes del captcha |
| `--value` | valor a escribir en `--input` |
| `--click` | selector CSS a clickear antes del submit (modal, botón intermedio) |
| `--submit` | selector CSS del botón que dispara el captcha |
| `--wait-selector` | selector CSS a esperar tras navegar |
| `--wait-timeout` | timeout de `--wait-selector` en segundos (default 15) |
| `--success-selector` | si existe, asumir captcha ya resuelto y saltar el solver |
| `--check-selector` | selector CSS para verificar destino tras resolver |
| `--captcha-wait` | segundos a esperar `--success-selector` antes de resolver (default 10) |
| `--post-click-wait` | segundos tras `--click` (default 1.5) |
| `--post-submit-wait` | segundos tras `--submit` (default 3.0) |
| `--solve-timeout` | máximo de segundos para la fase de resolución (default 90) |
| `--model` | ruta al directorio del modelo Vosk |
| `--max-rounds` | máximo de rondas de captcha (default 5) |
| `--proxy` | URL del proxy (`http://host:port` o `socks5://host:port`) |
| `--cookies` | ruta al JSON de cookies a cargar antes de navegar |
| `--save-cookies` | ruta donde guardar cookies JSON tras resolver |
| `--user-agent` | User-Agent personalizado |
| `--locale` | locale del navegador (default `en-US`) |
| `--headed` | correr con ventana visible |
| `--chrome-executable` | ruta custom al ejecutable de chromium/chrome |
| `--screenshot-on-fail` | ruta del PNG si el captcha falla |
| `--json` | salida en JSON (para pipear) |
| `--quiet` | sin banner ni spinner |
| `--version` | versión |
| `--help` | ayuda bilingüe (EN/ES) |

## Salida

**Éxito (texto):**

```
OK
token: 03AGdBq24Jx8...
check: found
```

**Éxito (JSON):**

```json
{
  "ok": true,
  "token": "03AGdBq24Jx8...",
  "check_selector_found": true
}
```

**Error (texto):**

```
ERROR: IP blocked by Google (automated queries)
```

**Error (JSON):**

```json
{"ok": false, "error": "captcha_failed"}
```

**Códigos de salida:**

| Código | Significado |
|---|---|
| `0` | captcha resuelto (o ya estaba resuelto) |
| `1` | error |
| `130` | interrumpido (Ctrl-C) |

## Errores

| error | Significado |
|---|---|
| `ipblock` | Google bloqueó la IP ("automated queries") |
| `navigation_failed` | no se pudo cargar la URL |
| `input_failed` | selector `--input` no encontrado |
| `click_failed` | selector `--click` no encontrado |
| `submit_failed` | selector `--submit` no encontrado |
| `captcha_failed` | captcha apareció pero no se resolvió en `--max-rounds` |
| `timeout` | fase de resolución excedió `--solve-timeout` |

## Limitaciones reales

- **Solo reCAPTCHA v2.** No v3, hCaptcha, Turnstile, Arkose.
- **Depende del audio endpoint de Google.** Si Google bloquea la IP (`ipblock`), no hay bypass desde el browser. Necesitás cambiar IP (proxy residencial o red doméstica).
- **Modelo Vosk `small` acierta ~80–90%.** Para más precisión usá `--model vosk-model-en-us-0.22` (más grande, más lento).
- **Headless desde datacenter = IpBlock frecuente.** Recomendado proxy residencial o IP doméstica.

## Integración con otras herramientas

En vez de duplicar el solver en cada proyecto, lo importás:

```python
from captcha_v2_resolve import solve_captcha

result = await solve_captcha(page, verbose=False)
if not result["ok"]:
    return {"ok": False, "error": result["error"]}
token = result["token"]
```

## Créditos

**captcha_v2_resolve v1.1.0 — By Vorem**

## Licencia

MIT