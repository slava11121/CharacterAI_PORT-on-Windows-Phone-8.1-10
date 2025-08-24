import os, re, asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "state.json")
HEADLESS = False  # когда всё стабильно — поставь True, чтобы окно не показывалось

app = FastAPI()
_pl = None
_browser = None

class SendReq(BaseModel):
    character_id: str   # GUID или полный URL /chat/<id>
    text: str

class ChatReq(BaseModel):
    character_id: str

def norm_char_id(s: str) -> str:
    s = s.strip()
    m = re.search(r"/chat/([^/?#]+)", s)
    return m.group(1) if m else s

async def click_if_exists(page, labels):
    for lbl in labels:
        try:
            btn = page.get_by_role("button", name=lbl)
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(0.2)
                return True
        except:
            pass
    return False

async def try_click_any(page, selectors_or_names):
    """Пробуем либо CSS/селектор, либо кнопку по имени (role=button)."""
    for s in selectors_or_names:
        try:
            if s.startswith(("//", "[", ".", "#")):
                loc = page.locator(s)
                if await loc.count() > 0:
                    await loc.first.click()
                    await page.wait_for_timeout(300)
                    return True
            else:
                btn = page.get_by_role("button", name=s)
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(300)
                    return True
        except:
            pass
    return False

async def find_composer(page):
    ta = page.locator("textarea")
    if await ta.count() > 0: return ta.first
    tb = page.locator("[role='textbox'][contenteditable='true']")
    if await tb.count() > 0: return tb.first
    ce = page.locator("[contenteditable='true']")
    if await ce.count() > 0: return ce.first
    return None

async def get_tail_texts(page, limit=50):
    """Хвост всех пузырей (только текст, порядок сверху->вниз)."""
    js = """
    (limit) => {
      function txt(el){ return (el.innerText||'').trim(); }
      const nodes = Array.from(document.body.querySelectorAll(
        '[data-testid*="message"], [class*="message"], [role="listitem"], [role="article"]'
      ));
      const arr = nodes.map(el => txt(el)).filter(t => t && t.length > 1);
      return arr.slice(-limit);
    }"""
    try:
        return await page.evaluate(js, limit)
    except:
        return []

def diff_new_items(before, after):
    """Новые элементы в after относительно before (срезаем общий суффикс)."""
    i = len(after) - 1
    j = len(before) - 1
    while i >= 0 and j >= 0 and after[i] == before[j]:
        i -= 1
        j -= 1
    return after[: i + 1]

async def scroll_to_bottom(page):
    try:
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
    except:
        pass

async def dom_items(page):
    js = """
    () => {
      function txt(el){ return (el.innerText||'').trim(); }
      const nodes = Array.from(document.body.querySelectorAll(
        '[data-testid*="message"],[class*="message"],[role="listitem"],[role="article"]'
      ));
      const out = [];
      for (const el of nodes){
        const t = txt(el);
        if(!t || t.length<2) continue;
        const style = window.getComputedStyle(el);
        const rightish = (style.textAlign === 'right') || (style.alignSelf === 'flex-end');
        const aEl = el.querySelector('[data-testid*="author"],[class*="author"],[class*="name"]');
        const author = aEl ? txt(aEl).toLowerCase() : "";
        const isUserText = /^you\\b/i.test(t) || author.includes("you");
        const isUser = rightish || isUserText;
        out.push({y: el.getBoundingClientRect().top, text: t, isUser, isBot: !isUser});
      }
      out.sort((a,b)=>a.y-b.y);
      return out;
    }"""
    return await page.evaluate(js)

async def count_users(page) -> int:
    items = await dom_items(page)
    return sum(1 for it in items if it["isUser"])

async def index_last_user(page) -> int:
    items = await dom_items(page)
    for i in range(len(items)-1, -1, -1):
        if items[i]["isUser"]:
            return i
    return -1

async def first_bot_after(page, idx) -> str:
    items = await dom_items(page)
    for i in range(idx+1, len(items)):
        if items[i]["isBot"] and len(items[i]["text"].strip())>1:
            return items[i]["text"].strip()
    return ""

async def open_chat(page, character_id) -> bool:
    """Открыть страницу чата и дождаться поля ввода."""
    char = norm_char_id(character_id)
    url_new = f"https://character.ai/chat/{char}"
    url_old = f"https://character.ai/chat?char={char}"

    async def goto(u):
        await page.goto(u, wait_until="domcontentloaded")
        try: await page.wait_for_load_state("networkidle", timeout=10000)
        except: pass
        await page.wait_for_timeout(800)
        await scroll_to_bottom(page)

    for _ in range(3):
        await goto(url_new)
        if not page.url.startswith("about:"):
            comp = await find_composer(page)
            if comp: return True
        await goto(url_old)
        comp = await find_composer(page)
        if comp: return True
        await page.evaluate("(u)=>{ location.href=u }", url_new)
        await page.wait_for_timeout(1200)
        comp = await find_composer(page)
        if comp: return True
    return False

async def ensure_browser():
    global _pl, _browser
    if _pl is None:
        _pl = await async_playwright().start()
    if _browser is None:
        _browser = await _pl.chromium.launch(
            headless=HEADLESS,
            args=["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"]
        )

async def new_context():
    await ensure_browser()
    if not os.path.exists(STATE_FILE) or os.path.getsize(STATE_FILE) < 2000:
        raise RuntimeError("state.json отсутствует или пуст. Запусти Login.bat и войди email+пароль.")
    return await _browser.new_context(storage_state=STATE_FILE)

@app.get("/health")
async def health():
    return {"status": "ok",
            "state_json_bytes": os.path.getsize(STATE_FILE) if os.path.exists(STATE_FILE) else 0}

@app.on_event("shutdown")
async def _shutdown():
    global _browser, _pl
    try:
        if _browser: await _browser.close()
    finally:
        if _pl: await _pl.stop()

@app.post("/send")
async def send(req: SendReq):
    ctx = await new_context()
    page = await ctx.new_page()
    try:
        char = norm_char_id(req.character_id)
        url_new = f"https://character.ai/chat/{char}"
        url_old = f"https://character.ai/chat?char={char}"

        async def goto(u):
            await page.goto(u, wait_until="domcontentloaded")
            try: await page.wait_for_load_state("networkidle", timeout=10000)
            except: pass
            await page.wait_for_timeout(800)
            await scroll_to_bottom(page)

        composer = None
        for _ in range(3):
            await goto(url_new)
            if not page.url.startswith("about:"):
                composer = await find_composer(page)
                if composer: break
            await goto(url_old)
            composer = await find_composer(page)
            if composer: break
            await page.evaluate("(u)=>{ location.href=u }", url_new)
            await page.wait_for_timeout(1200)
            composer = await find_composer(page)
            if composer: break

        await click_if_exists(page, ["Accept All","Accept all","Принять","Согласен"])
        await click_if_exists(page, ["Continue","Start chat","New chat","Start","Начать чат","Новый чат"])

        # нет входа — сразу сообщаем
        try:
            if await page.get_by_role("button", name="Login").count() > 0:
                return {"reply": "[нужен вход] Пересоздай state.json через Login.bat (email+пароль)."}
        except:
            pass

        if composer is None:
            return {"reply": "[ошибка] Не нашёл поле ввода (верстка/роут могли измениться)"}

        before_tail = await get_tail_texts(page, limit=50)
        base_users = await count_users(page)

        user_text = (req.text or "").strip()
        await composer.click()
        await composer.fill(user_text)

        sent = False
        for sel in ['[data-testid*="send"]','[aria-label*="Send"]','[title*="Send"]']:
            try:
                btn = page.locator(sel)
                if await btn.count() > 0:
                    await btn.first.click()
                    sent = True
                    break
            except:
                pass
        if not sent:
            try: await composer.press("Enter")
            except: pass

        await scroll_to_bottom(page)

        elapsed, step, max_user_ms = 0, 200, 8000
        while elapsed < max_user_ms:
            cur_users = await count_users(page)
            if cur_users >= base_users + 1:
                break
            await page.wait_for_timeout(step); elapsed += step

        base_idx = await index_last_user(page)
        if base_idx < 0:
            base_idx = await index_last_user(page)

        quiet_ms, max_ms = 2500, 60000
        elapsed, stable = 0, 0
        last_bot = ""

        while elapsed < max_ms:
            await page.wait_for_timeout(300)
            elapsed += 300

            cand1 = await first_bot_after(page, base_idx)

            after_tail = await get_tail_texts(page, limit=50)
            added = diff_new_items(before_tail, after_tail)
            cand2 = ""
            for t in reversed(added):
                if t.strip() and t.strip() != user_text:
                    cand2 = t.strip()
                    break

            candidate = cand2 or cand1

            if candidate and candidate != last_bot:
                last_bot = candidate
                stable = 0
            else:
                stable += 300
                if last_bot and stable >= quiet_ms:
                    break

        reply = last_bot or ""
        return {"reply": reply or "[пустой ответ]"}
    except Exception as e:
        return {"reply": f"[ошибка] {e}"}
    finally:
        try: await ctx.close()
        except: pass

@app.post("/chat/new")
async def chat_new(req: ChatReq):
    ctx = await new_context()
    page = await ctx.new_page()
    try:
        ok = await open_chat(page, req.character_id)
        if not ok:
            return {"ok": False, "error": "cannot open chat"}

        await click_if_exists(page, ["New chat", "Start new chat", "Start chat", "Начать чат", "Новый чат"])
        # fallback: меню с тремя точками -> New chat
        await try_click_any(page, ["More", "⋯", "[aria-label*='More']", "[data-testid*='more']"])
        await try_click_any(page, ["New chat", "Start new chat", "Начать чат", "Новый чат"])

        await page.wait_for_timeout(800)
        comp = await find_composer(page)
        tail = await get_tail_texts(page, 10)
        looks_clean = len("".join(tail).strip()) == 0
        return {"ok": bool(comp) or looks_clean}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try: await ctx.close()
        except: pass

@app.post("/chat/clear")
async def chat_clear(req: ChatReq):
    ctx = await new_context()
    page = await ctx.new_page()
    try:
        ok = await open_chat(page, req.character_id)
        if not ok:
            return {"ok": False, "error": "cannot open chat"}

        await try_click_any(page, ["Clear chat", "Clear messages", "Очистить чат", "Очистить сообщения"])
        await try_click_any(page, ["More", "⋯", "[aria-label*='More']", "[data-testid*='more']"])
        await try_click_any(page, ["Clear chat", "Clear messages", "Очистить чат", "Очистить сообщения"])
        await try_click_any(page, ["Clear", "Delete", "Yes", "OK", "Очистить", "Удалить", "Да"])

        await page.wait_for_timeout(800)
        tail = await get_tail_texts(page, 5)
        return {"ok": len(tail) == 0}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try: await ctx.close()
        except: pass

@app.post("/chat/peek")
async def chat_peek(req: ChatReq):
    ctx = await new_context()
    page = await ctx.new_page()
    try:
        ok = await open_chat(page, req.character_id)
        if not ok:
            return {"text": ""}

        items = await dom_items(page)
        txt = ""
        for i in range(len(items)-1, -1, -1):
            it = items[i]
            if it["isBot"] and it["text"].strip():
                txt = it["text"].strip()
                break
        return {"text": txt}
    except Exception as e:
        return {"text": ""}
    finally:
        try: await ctx.close()
        except: pass

@app.post("/chat/meta")
async def chat_meta(req: ChatReq):
    ctx = await new_context()
    page = await ctx.new_page()
    try:
        ok = await open_chat(page, req.character_id)
        if not ok:
            return {"name": "", "avatar": ""}

        js = """
        () => {
          function txt(el){return (el?.innerText||'').trim();}
          function attr(el,n){return (el?.getAttribute(n)||'').trim();}
          const out = {name:"", avatar:""};

          const nameCands = [
            'h1', '[data-testid*="name"]', '[class*="header"] h1',
            '[class*="name"]', '[role="heading"]'
          ];
          for (const sel of nameCands){
            const el = document.querySelector(sel);
            if (el && txt(el).length>1){ out.name = txt(el); break; }
          }
          if (!out.name || out.name.length<2){
            out.name = (document.title||'').replace(/\\s*[-|•].*$/,'').trim();
          }

          const imgCands = [
            'img[alt*="avatar" i]', 'img[src*="cdn"]', 'img[class*="avatar"]',
            '[data-testid*="avatar"] img', 'img'
          ];
          for (const sel of imgCands){
            const el = document.querySelector(sel);
            const s = attr(el,'src');
            if (s && s.startsWith('http')){ out.avatar = s; break; }
          }
          if (!out.avatar){
            const og = document.querySelector('meta[property="og:image"]');
            const c = attr(og,'content');
            if (c && c.startsWith('http')) out.avatar = c;
          }

          return out;
        }"""
        meta = await page.evaluate(js)
        return {"name": meta.get("name",""), "avatar": meta.get("avatar","")}
    except Exception:
        return {"name": "", "avatar": ""}
    finally:
        try: await ctx.close()
        except: pass
