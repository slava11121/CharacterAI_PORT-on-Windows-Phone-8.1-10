# -*- coding: utf-8 -*-
# ОДИН ФАЙЛ. Открывает https://character.ai/, даёшь логин руками,
# скрипт ждёт исчезновения "Log in/Login" БЕЗ .count(), потом Enter в консоли -> сохраняется state.json
import os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = Path(__file__).parent.resolve()
STATE_FILE = BASE / "state.json"
START_URL = "https://character.ai/"

def msvcrt_enter_pressed():
    try:
        import msvcrt
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            return ch in ("\r", "\n")
    except Exception:
        pass
    return False

def main():
    os.system("chcp 65001 >nul")
    os.environ["PYTHONIOENCODING"] = "utf-8"

    print(f"[i] Рабочая папка: {BASE}")
    print(f"[i] Файл сессии будет сохранён в: {STATE_FILE}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-gpu","--disable-dev-shm-usage","--no-sandbox"]
        )
        ctx = browser.new_context()
        page = ctx.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(45000)

        page.goto(START_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except PWTimeout:
            pass

        # Маркеры
        login_marker = page.locator(
            "button:has-text('Log in'), button:has-text('Login'), "
            "a:has-text('Log in'), a:has-text('Login')"
        )
        authed_marker = page.locator(
            "a[href*='logout'], img[alt*='avatar'], [aria-label*='profile' i]"
        )

        print("\n[i] ВОЙДИ В АККАУНТ (email + пароль; не Google/Apple).")
        print("[i] Скрипт продолжит, когда 'Log in/Login' исчезнет. "
              "Можно форсировать — нажми Enter в консоли.")

        # Ожидаем вход без .count()
        while True:
            if msvcrt_enter_pressed():
                break
            try:
                # уже авторизованы?
                authed_marker.first.wait_for(timeout=1000)
                break
            except PWTimeout:
                pass
            try:
                # кнопка логина скрылась/отцепилась?
                login_marker.first.wait_for(state="hidden", timeout=1000)
                break
            except PWTimeout:
                pass
            try:
                page.wait_for_load_state("networkidle", timeout=1500)
            except PWTimeout:
                pass

        input("\n[i] Если вход выполнен — НАЖМИ Enter здесь в консоли... ")

        ctx.storage_state(path=str(STATE_FILE))
        size = STATE_FILE.stat().st_size if STATE_FILE.exists() else 0
        print(f"[ok] Сохранено: {STATE_FILE} ({size} bytes)")

        ctx.close()
        browser.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем")
        sys.exit(1)
