#!/usr/bin/env python3
import argparse
import asyncio
import base64
import json
import re
import subprocess
import sys
import threading
import time
import wave

try:
    from patchright.async_api import async_playwright
except ImportError:
    from playwright.async_api import async_playwright

TOOL = "captcha_v2_resolve"
AUTHOR = "By Vorem"
VERSION = "1.1.0"
IPBLOCK = re.compile(r"automated queries|sending automated|consultas automatizadas", re.I)

class K:
    END = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"

def col(t, k, bold=False):
    return (K.BOLD if bold else "") + k + str(t) + K.END

class Spin:
    F = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, enabled=True):
        self.enabled = enabled and sys.stderr.isatty()
        self._msg = ""
        self._stop = threading.Event()
        self._t = None

    def start(self, msg="working"):
        if not self.enabled:
            return
        self._msg = msg
        self._stop.clear()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def step(self, msg):
        self._msg = msg

    def _run(self):
        i = 0
        while not self._stop.is_set():
            f = self.F[i % len(self.F)]
            sys.stderr.write(f"\r  {col(f, K.CYAN)} {col(self._msg, K.DIM)}" + " " * 20)
            sys.stderr.flush()
            i += 1
            time.sleep(0.08)

    def stop(self):
        if not self.enabled:
            return
        self._stop.set()
        if self._t:
            self._t.join(timeout=1)
        sys.stderr.write("\r" + " " * 120 + "\r")
        sys.stderr.flush()

SPIN = Spin()

def banner():
    if not sys.stderr.isatty():
        return
    sys.stderr.write("\n")
    sys.stderr.write(f"  {col('╭──────────────────────────────────╮', K.MAGENTA)}\n")
    sys.stderr.write(f"  {col('│', K.MAGENTA)}  {col(TOOL, K.CYAN, bold=True)}  v{VERSION}          {col('│', K.MAGENTA)}\n")
    sys.stderr.write(f"  {col('│', K.MAGENTA)}  {col(AUTHOR, K.DIM)}                       {col('│', K.MAGENTA)}\n")
    sys.stderr.write(f"  {col('╰──────────────────────────────────╯', K.MAGENTA)}\n\n")
    sys.stderr.flush()

class Solver:
    def __init__(self, page, model="vosk-model-small-en-us-0.15", max_rounds=5, verbose=False):
        self.page = page
        self.model = model
        self.max_rounds = max_rounds
        self.verbose = verbose
        self._vosk = None

    def _s(self, msg):
        if self.verbose:
            SPIN.step(msg)

    async def state(self):
        for f in self.page.frames:
            if "recaptcha" in f.url:
                try:
                    txt = await f.evaluate("()=>document.body?.innerText||''")
                    if IPBLOCK.search(txt):
                        return "ipblock"
                except Exception:
                    pass
                if "anchor" in f.url or "bframe" in f.url:
                    return "captcha"
        return "none"

    async def _force(self, frame, sel):
        try:
            el = await frame.wait_for_selector(sel, timeout=5000)
            await el.click(force=True)
            return True
        except Exception:
            pass
        try:
            await frame.evaluate(
                "(s)=>{const b=document.querySelector(s);if(b){b.style.visibility='visible';b.style.display='block';b.click();}}",
                sel,
            )
            return True
        except Exception:
            return False

    async def _anchor(self):
        for _ in range(8):
            if await self.state() == "none":
                return None
            for f in self.page.frames:
                if "recaptcha" in f.url and "anchor" in f.url:
                    return f
            await self.page.wait_for_timeout(500)
        return None

    async def _bframe(self):
        for _ in range(15):
            if await self.state() == "none":
                return None
            for f in self.page.frames:
                if "recaptcha" in f.url and "bframe" in f.url:
                    return f
            await self.page.wait_for_timeout(500)
        return None

    def _transcribe(self, mp3, wav):
        from vosk import Model, KaldiRecognizer, SetLogLevel
        SetLogLevel(-1)
        subprocess.run(
            ["ffmpeg", "-y", "-i", mp3, "-ar", "16000", "-ac", "1", wav],
            check=True,
            capture_output=True,
        )
        if self._vosk is None:
            self._vosk = Model(self.model)
        wf = wave.open(wav, "rb")
        rec = KaldiRecognizer(self._vosk, wf.getframerate())
        while True:
            d = wf.readframes(4000)
            if not d:
                break
            rec.AcceptWaveform(d)
        return json.loads(rec.FinalResult()).get("text", "").strip()

    async def _round(self):
        if await self.state() == "none":
            return True
        self._s("click checkbox / marcar checkbox")
        anchor = await self._anchor()
        if anchor:
            for s in ("#recaptcha-anchor", ".recaptcha-checkbox-border", ".recaptcha-checkbox"):
                if await self._force(anchor, s):
                    break
            await self.page.wait_for_timeout(2000)
        if await self.state() == "none":
            return True

        self._s("open audio / abrir audio")
        bframe = await self._bframe()
        if not bframe:
            return await self.state() == "none"

        if not await self._force(bframe, "#recaptcha-audio-button"):
            return await self.state() == "none"
        await self.page.wait_for_timeout(2000)

        try:
            src = await bframe.evaluate(
                "()=>document.querySelector('audio#audio-source')?.src||document.querySelector('audio source')?.src||''"
            )
        except Exception:
            src = ""
        if not src:
            return False

        self._s("download audio / descargar audio")
        try:
            b64 = await bframe.evaluate(
                """async(s)=>{const r=await fetch(s,{credentials:'include'});const b=await r.arrayBuffer();let o='';const u=new Uint8Array(b);for(let i=0;i<u.length;i++)o+=String.fromCharCode(u[i]);return btoa(o);}""",
                src,
            )
            data = base64.b64decode(b64)
            if not data:
                return False
            with open("/tmp/cv2.mp3", "wb") as f:
                f.write(data)
        except Exception:
            return False

        self._s("transcribe / transcribir")
        try:
            text = await asyncio.to_thread(self._transcribe, "/tmp/cv2.mp3", "/tmp/cv2.wav")
        except Exception:
            return False
        if not text:
            return False
        text = re.sub(r"[^a-zA-Z0-9 ]", "", text).strip().lower()

        self._s("fill response / llenar respuesta")
        try:
            inp = await bframe.wait_for_selector("#audio-response", timeout=5000)
            await inp.fill(text)
        except Exception:
            return await self.state() == "none"

        self._s("verify / verificar")
        if not await self._force(bframe, "#recaptcha-verify-button"):
            return await self.state() == "none"
        await self.page.wait_for_timeout(4000)
        return await self.state() == "none"

    async def solve(self):
        for r in range(1, self.max_rounds + 1):
            st = await self.state()
            if st == "none":
                return "ok"
            if st == "ipblock":
                return "ipblock"
            if st == "captcha":
                self._s(f"round {r}/{self.max_rounds} · ronda {r}/{self.max_rounds}")
                await self._round()
                st2 = await self.state()
                if st2 == "none":
                    return "ok"
                if st2 == "ipblock":
                    return "ipblock"
                await self.page.wait_for_timeout(2000)
                continue
            await self.page.wait_for_timeout(1500)
        return "ok" if await self.state() == "none" else "fail"

    async def token(self):
        try:
            return await self.page.evaluate(
                "()=>{const e=document.querySelector('textarea[name=\"g-recaptcha-response\"]');return e?e.value:'';}"
            )
        except Exception:
            return ""

async def solve_captcha(page, model="vosk-model-small-en-us-0.15", max_rounds=5,
                        verbose=False, timeout=60):
    """
    EN: Solve reCAPTCHA v2 on an already-open Playwright page. Returns dict:
        {"ok": True, "token": "..."} | {"ok": False, "error": "ipblock|captcha_failed|timeout"}
    ES: Resuelve reCAPTCHA v2 en una página de Playwright ya abierta. Devuelve dict:
        {"ok": True, "token": "..."} | {"ok": False, "error": "ipblock|captcha_failed|timeout"}
    """
    solver = Solver(page, model=model, max_rounds=max_rounds, verbose=verbose)
    try:
        res = await asyncio.wait_for(solver.solve(), timeout=timeout)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout"}
    if res == "ipblock":
        return {"ok": False, "error": "ipblock"}
    if res == "fail":
        return {"ok": False, "error": "captcha_failed"}
    return {"ok": True, "token": await solver.token()}

async def run(args):
    async with async_playwright() as p:
        launch_kw = {
            "headless": not args.headed,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            "user_agent": args.user_agent,
            "locale": args.locale,
            "viewport": {"width": 1366, "height": 820},
        }
        if args.proxy:
            launch_kw["proxy"] = {"server": args.proxy}
        if args.chrome_executable:
            launch_kw["executable_path"] = args.chrome_executable
        browser = await p.chromium.launch(**launch_kw)

        ctx_kw = {}
        if args.cookies:
            try:
                data = json.load(open(args.cookies))
                if isinstance(data, list):
                    ctx_kw["storage_state"] = {"cookies": data, "origins": []}
            except Exception:
                pass
        ctx = await browser.new_context(**ctx_kw)
        page = await ctx.new_page()
        page.set_default_navigation_timeout(30000)
        page.set_default_timeout(20000)

        SPIN.start("navigate / navegar")
        try:
            await page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            await browser.close()
            SPIN.stop()
            return {"ok": False, "error": "navigation_failed", "message": str(e)}
        await page.wait_for_timeout(2000)

        if args.wait_selector:
            SPIN.step(f"wait / esperar {args.wait_selector}")
            try:
                await page.wait_for_selector(args.wait_selector, timeout=args.wait_timeout * 1000)
            except Exception:
                pass

        if args.input and args.value:
            SPIN.step(f"fill / llenar {args.input}")
            try:
                el = await page.wait_for_selector(args.input, timeout=10000)
                await el.fill(args.value)
            except Exception as e:
                await browser.close()
                SPIN.stop()
                return {"ok": False, "error": "input_failed", "message": str(e)}

        if args.click:
            SPIN.step(f"click / clic {args.click}")
            try:
                el = await page.wait_for_selector(args.click, timeout=10000)
                await el.click(force=True)
            except Exception as e:
                await browser.close()
                SPIN.stop()
                return {"ok": False, "error": "click_failed", "message": str(e)}
            await page.wait_for_timeout(args.post_click_wait * 1000)

        if args.submit:
            SPIN.step(f"submit / enviar {args.submit}")
            try:
                btn = await page.wait_for_selector(args.submit, timeout=10000)
                await btn.click(force=True)
            except Exception as e:
                await browser.close()
                SPIN.stop()
                return {"ok": False, "error": "submit_failed", "message": str(e)}
            await page.wait_for_timeout(args.post_submit_wait * 1000)

        if args.success_selector:
            SPIN.step("check success / verificar éxito")
            ok = False
            for _ in range(args.captcha_wait * 2):
                try:
                    await page.wait_for_selector(args.success_selector, timeout=500)
                    ok = True
                    break
                except Exception:
                    pass
                await page.wait_for_timeout(500)
            if ok:
                token = ""
                try:
                    token = await page.evaluate(
                        "()=>{const e=document.querySelector('textarea[name=\"g-recaptcha-response\"]');return e?e.value:'';}"
                    )
                except Exception:
                    pass
                extra = {}
                if args.check_selector:
                    try:
                        await page.wait_for_selector(args.check_selector, timeout=5000)
                        extra["check_selector_found"] = True
                    except Exception:
                        extra["check_selector_found"] = False
                if args.save_cookies:
                    try:
                        ck = await ctx.cookies()
                        with open(args.save_cookies, "w") as f:
                            json.dump(ck, f, indent=2)
                    except Exception:
                        pass
                await browser.close()
                SPIN.stop()
                return {"ok": True, "token": token, "note": "success_selector_found", **extra}

        SPIN.step("solve captcha / resolver captcha")
        result = await solve_captcha(
            page,
            model=args.model,
            max_rounds=args.max_rounds,
            verbose=True,
            timeout=args.solve_timeout,
        )

        extra = {}
        if args.check_selector:
            try:
                await page.wait_for_selector(args.check_selector, timeout=5000)
                extra["check_selector_found"] = True
            except Exception:
                extra["check_selector_found"] = False

        if args.save_cookies:
            try:
                ck = await ctx.cookies()
                with open(args.save_cookies, "w") as f:
                    json.dump(ck, f, indent=2)
            except Exception:
                pass

        if args.screenshot_on_fail and not result.get("ok"):
            try:
                await page.screenshot(path=args.screenshot_on_fail)
            except Exception:
                pass

        await browser.close()
        SPIN.stop()
        return {**result, **extra}

def output(result, as_json=False):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if result.get("ok"):
        print(col("OK", K.GREEN, bold=True))
        tok = result.get("token", "")
        if tok:
            print(f"token: {col(tok[:80] + ('...' if len(tok) > 80 else ''), K.DIM)}")
        if result.get("note"):
            print(f"note: {result['note']}")
        if "check_selector_found" in result:
            v = result["check_selector_found"]
            print(f"check: {col('found' if v else 'not found', K.GREEN if v else K.YELLOW)}")
        return 0
    e = result.get("error", "unknown")
    err_map = {
        "ipblock": "IP blocked by Google (automated queries) / IP bloqueada por Google",
        "navigation_failed": "navigation failed / navegación falló",
        "input_failed": "input selector failed / selector input falló",
        "click_failed": "click selector failed / selector click falló",
        "submit_failed": "submit selector failed / selector submit falló",
        "captcha_failed": "captcha not solved / captcha no resuelto",
        "timeout": "solve timed out / timeout al resolver",
    }
    print(col(f"ERROR: {err_map.get(e, e)}", K.RED, bold=True))
    if result.get("message"):
        print(f"  {col(result['message'], K.DIM)}")
    return 1

def bilingual(en, es):
    return f"{en}\n{es}"

def build_parser():
    examples = (
        "Ejemplos / Examples:\n"
        "\n"
        "  # 1. captcha visible al cargar la página / captcha visible on page load\n"
        "  captcha_v2_resolve https://example.com/form\n"
        "\n"
        "  # 2. llenar input y submit que dispara el captcha\n"
        "  #    fill input and submit that triggers the captcha\n"
        "  captcha_v2_resolve https://example.com/login \\\n"
        "    --input 'input[name=\"user\"]' --value 'john' \\\n"
        "    --submit 'button[type=\"submit\"]'\n"
        "\n"
        "  # 3. click intermedio (modal) antes del submit\n"
        "  #    intermediate click (modal) before submit\n"
        "  captcha_v2_resolve https://example.com/page \\\n"
        "    --click '#open-modal' --submit '#modal button'\n"
        "\n"
        "  # 4. cookies previas + guardar cookies + json + screenshot si falla\n"
        "  #    load cookies + save cookies + json + screenshot on fail\n"
        "  captcha_v2_resolve https://example.com/form \\\n"
        "    --cookies old.json --save-cookies new.json \\\n"
        "    --json --screenshot-on-fail fail.png\n"
        "\n"
        "  # 5. proxy residencial para evitar IpBlock\n"
        "  #    residential proxy to avoid IpBlock\n"
        "  captcha_v2_resolve https://example.com/form \\\n"
        "    --proxy 'http://user:pass@host:8080'\n"
        "\n"
        "  # 6. ver navegador para debug / show browser for debug\n"
        "  captcha_v2_resolve https://example.com/form --headed\n"
        "\n"
        "Librería / Library:\n"
        "  from captcha_v2_resolve import solve_captcha\n"
        "  result = await solve_captcha(page)\n"
        "  # -> {\"ok\": True, \"token\": \"...\"}\n"
        "  # -> {\"ok\": False, \"error\": \"ipblock|captcha_failed|timeout\"}\n"
    )

    ap = argparse.ArgumentParser(
        prog=TOOL,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            f"{TOOL} {VERSION} — {AUTHOR}\n\n"
            "EN: Universal reCAPTCHA v2 solver (audio challenge + Vosk). Works on any page.\n"
            "ES: Resolvedor universal de reCAPTCHA v2 (audio challenge + Vosk). Funciona en cualquier página.\n"
        ),
        epilog=examples,
    )
    ap.add_argument(
        "url",
        help=bilingual("target URL", "URL objetivo"),
    )
    ap.add_argument(
        "--input",
        help=bilingual(
            "CSS selector of input to fill before triggering captcha",
            "selector CSS del input a llenar antes de disparar el captcha",
        ),
    )
    ap.add_argument(
        "--value",
        help=bilingual("value to write into --input", "valor a escribir en --input"),
    )
    ap.add_argument(
        "--click",
        help=bilingual(
            "CSS selector to click before submit (modal, intermediate button)",
            "selector CSS a clickear antes del submit (modal, botón intermedio)",
        ),
    )
    ap.add_argument(
        "--submit",
        help=bilingual(
            "CSS selector of the button that triggers the captcha",
            "selector CSS del botón que dispara el captcha",
        ),
    )
    ap.add_argument(
        "--wait-selector",
        help=bilingual(
            "CSS selector to wait for after navigation",
            "selector CSS a esperar tras navegar",
        ),
    )
    ap.add_argument(
        "--wait-timeout",
        type=int,
        default=15,
        help=bilingual(
            "wait-selector timeout in seconds (default 15)",
            "timeout de --wait-selector en segundos (default 15)",
        ),
    )
    ap.add_argument(
        "--success-selector",
        help=bilingual(
            "if present, assume captcha already solved and skip solver",
            "si existe, asumir captcha ya resuelto y saltar el solver",
        ),
    )
    ap.add_argument(
        "--check-selector",
        help=bilingual(
            "CSS selector to verify destination after solve",
            "selector CSS para verificar que se llegó al destino tras resolver",
        ),
    )
    ap.add_argument(
        "--captcha-wait",
        type=int,
        default=10,
        help=bilingual(
            "seconds to wait for success-selector before solving (default 10)",
            "segundos a esperar success-selector antes de resolver (default 10)",
        ),
    )
    ap.add_argument(
        "--post-click-wait",
        type=float,
        default=1.5,
        help=bilingual("seconds after --click (default 1.5)", "segundos tras --click (default 1.5)"),
    )
    ap.add_argument(
        "--post-submit-wait",
        type=float,
        default=3.0,
        help=bilingual(
            "seconds after --submit (default 3.0)",
            "segundos tras --submit (default 3.0)",
        ),
    )
    ap.add_argument(
        "--solve-timeout",
        type=float,
        default=90.0,
        help=bilingual(
            "max seconds for the solve phase (default 90)",
            "máximo de segundos para la fase de resolución (default 90)",
        ),
    )
    ap.add_argument(
        "--model",
        default="vosk-model-small-en-us-0.15",
        help=bilingual(
            "path to Vosk model directory",
            "ruta al directorio del modelo Vosk",
        ),
    )
    ap.add_argument(
        "--max-rounds",
        type=int,
        default=5,
        help=bilingual("max captcha rounds (default 5)", "máximo de rondas de captcha (default 5)"),
    )
    ap.add_argument(
        "--proxy",
        help=bilingual(
            "proxy URL (http://host:port or socks5://host:port)",
            "URL del proxy (http://host:port o socks5://host:port)",
        ),
    )
    ap.add_argument(
        "--cookies",
        help=bilingual(
            "path to cookies JSON to load before navigating",
            "ruta al JSON de cookies a cargar antes de navegar",
        ),
    )
    ap.add_argument(
        "--save-cookies",
        help=bilingual(
            "path to save cookies JSON after solve",
            "ruta donde guardar cookies JSON tras resolver",
        ),
    )
    ap.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0",
        help=bilingual("custom User-Agent", "User-Agent personalizado"),
    )
    ap.add_argument(
        "--locale",
        default="en-US",
        help=bilingual("browser locale (default en-US)", "locale del navegador (default en-US)"),
    )
    ap.add_argument(
        "--headed",
        action="store_true",
        help=bilingual("run with visible browser window", "correr con ventana visible del navegador"),
    )
    ap.add_argument(
        "--chrome-executable",
        help=bilingual(
            "custom chromium/chrome executable path",
            "ruta custom al ejecutable de chromium/chrome",
        ),
    )
    ap.add_argument(
        "--screenshot-on-fail",
        help=bilingual(
            "path to save screenshot if captcha fails",
            "ruta del PNG si el captcha falla",
        ),
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help=bilingual("output JSON (for piping)", "salida en JSON (para pipear)"),
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help=bilingual("suppress banner and spinner", "sin banner ni spinner"),
    )
    ap.add_argument(
        "--version",
        action="version",
        version=f"{TOOL} {VERSION} {AUTHOR}",
    )
    return ap

def main():
    ap = build_parser()
    args = ap.parse_args()

    global SPIN
    if args.quiet:
        SPIN = Spin(enabled=False)
    else:
        SPIN = Spin(enabled=True)
        banner()

    try:
        result = asyncio.run(run(args))
    except KeyboardInterrupt:
        SPIN.stop()
        if args.json:
            print(json.dumps({"ok": False, "error": "interrupted"}))
        else:
            print(col("ERROR: interrupted / interrumpido", K.RED, bold=True))
        sys.exit(130)
    except Exception as e:
        SPIN.stop()
        if args.json:
            print(json.dumps({"ok": False, "error": "exception", "message": str(e)}))
        else:
            print(col(f"ERROR: {e}", K.RED, bold=True))
        sys.exit(1)
    finally:
        SPIN.stop()

    sys.exit(output(result, as_json=args.json))

if __name__ == "__main__":
    main()
