import json
import asyncio
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import pandas as pd
import os

INPUT_JSON = "links.json"
OUTPUT_XLSX = "videos_progress.xlsx"
USER_DATA_DIR = r"PlaywrightUserData"


def now_str():
    return datetime.now().strftime("%H:%M %d.%m.%Y")


def parse_duration(duration_str: str) -> timedelta:
    h, m, s = map(int, duration_str.split(":"))
    return timedelta(hours=h, minutes=m, seconds=s)


def save_progress(videos):
    with open(INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    pd.DataFrame(videos).to_excel(OUTPUT_XLSX, index=False)


async def watch_video(page, video, my_channel_id):
    """
    Открывает видео, оставляет комментарий с началом просмотра,
    ждёт окончания видео, оставляет ответ на свой комментарий с временем окончания.
    """

    link = video["Link"]
    duration = parse_duration(video["Duration"])

    # 1. Перейти на страницу видео
    await page.goto(link)
    await asyncio.sleep(3)  # дождаться полной загрузки

    # Проверка и закрытие pop-up, если он появился
    popup_btn = await page.query_selector("button.wdp-onboardings-inventory-module__closeIcon")
    if popup_btn:
        print("[i] Обнаружен pop-up. Закрываю...")
        await popup_btn.click()
        await asyncio.sleep(1)
    
    # 2. Оставить комментарий с началом просмотра
    start_comment = now_str()
    try:
        await page.fill(".wdp-comment-first-level-input-module__commentTextarea", start_comment)
        await page.click("text=Отправить")
        print(f"[+] Оставлен комментарий с началом просмотра: {start_comment}")
    except Exception as e:
        print(f"[!] Не удалось оставить комментарий для {link}: {e}")
        return

    # Получение названия видео
    title_element = await page.query_selector(
        ".video-pageinfo-container-module__videoTitleSection h1.video-pageinfo-container-module__videoTitleSectionHeader"
    )
    video_title = await title_element.inner_text() if title_element else "Unknown Title"
    video["Title"] = video_title
    print(f"Название видео: {video_title}")

    print(f"[+] Начат просмотр: {link}")
    await asyncio.sleep(duration.total_seconds())  # имитация просмотра видео

    # 3. Оставить ответ на свой комментарий с временем окончания
    end_comment = now_str()
    try:
        comment_selector = f"a[href='/channel/{my_channel_id}/']"
        comment_element = await page.query_selector(comment_selector)
        if not comment_element:
            print("[!] Мой комментарий не найден, ответ не оставлен")
            return

        parent = await comment_element.evaluate_handle(
            "el => el.closest('.wdp-comment-item-module__comment-wrapper')"
        )

        reply_button = await parent.query_selector("button.wdp-comment-reactions-module__button-answer")
        if not reply_button:
            print("[!] Кнопка 'Ответить' не найдена")
            return

        await reply_button.click()
        await asyncio.sleep(0.5)  # дождаться реакции страницы

        # Попробуем найти wrapper для ответа
        try:
            wrapper = await page.wait_for_selector(
                "div.wdp-answer-comment-module__wrapper",
                timeout=15000
            )
        except Exception:
            print("[!] Wrapper для ответа не появился (timeout)")
            wrapper = None

        # Определяем поле для ввода ответа
        if wrapper:
            reply_field = await wrapper.query_selector(
                "div.wdp-comment-input-module__textarea[contenteditable='true']"
            )
        else:
            all_reply_fields = await page.query_selector_all(
                "div.wdp-comment-input-module__textarea[contenteditable='true']"
            )
            reply_field = all_reply_fields[-1] if all_reply_fields else None

        if not reply_field:
            print("[!] Поле для ответа не найдено")
            return

        await reply_field.click()
        await asyncio.sleep(0.2)
        await reply_field.type(end_comment, delay=40)

        # Ищем кнопку "Ответить" внутри wrapper
        send_button = None
        attempts = 3
        for attempt in range(attempts):
            try:
                if wrapper:
                    send_button = await wrapper.wait_for_selector(
                        "button:has-text('Ответить'):not([disabled])",
                        timeout=10000
                    )
                else:
                    send_button = await page.wait_for_selector(
                        "div.wdp-answer-comment-module__wrapper button:has-text('Ответить'):not([disabled])",
                        timeout=10000
                    )

                if send_button:
                    await send_button.click()
                    await asyncio.sleep(0.5)
                    print(f"[+] Ответ оставлен: {end_comment}")
                    break
            except Exception as exc:
                print(f"[!] Попытка {attempt + 1}: кнопка отправки не появилась ({exc})")
                await asyncio.sleep(1)
                try:
                    await reply_field.click()
                except Exception:
                    pass

        if not send_button:
            print("[!] Не удалось отправить ответ: кнопка отправки не активировалась")
            try:
                await page.screenshot(path="debug_reply_failure.png", full_page=False)
                print("[!] Снимок сохранён: debug_reply_failure.png")
            except Exception:
                pass
            return

    except Exception as e:
        print(f"[!] Ошибка при ответе на комментарий: {e}")


def load_my_channel_id(file_path="user_info.txt"):
    if not os.path.exists(file_path):
        print(f"[!] Файл {file_path} не найден")
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


async def main():
    my_channel_id = load_my_channel_id()

    if not my_channel_id:
        print("[!] ID канала не загружен. Выход.")
        exit(1)

    if not os.path.exists(INPUT_JSON):
        print(f"Файл {INPUT_JSON} не найден.")
        return

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        videos = json.load(f)

    print("=== Rutube Watcher ===")
    print("1. Просмотреть все видео")
    print("2. Просмотреть часть видео")
    print("3. Авторизироваться в Rutube")
    choice = input("Выберите действие (1/2/3): ").strip()

    if choice == "3":
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto("https://rutube.ru/")  # Страница входа
            print("[+] Авторизуйтесь в открывшемся окне браузера")
            input("Нажмите Enter после завершения авторизации...")
            await context.close()
        return  # Выход после авторизации

    if choice == "1":
        videos_to_watch = videos
    elif choice == "2":
        count = input("Сколько видео вы хотите посмотреть? Введите число: ").strip()
        if not count.isdigit():
            print("[!] Некорректное число, выход.")
            return
        count = int(count)
        # Создаём срез для просмотра, но не трогаем исходный список
        videos_to_watch = [v for v in videos if not v.get("isWatched", False)][:count]
    else:
        print("[!] Некорректный выбор")
        return

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False
        )
        page = context.pages[0] if context.pages else await context.new_page()

        for video in videos_to_watch:
            if video.get("isWatched", False):
                continue

            video["Start"] = now_str()
            try:
                await watch_video(page, video, my_channel_id)
            except Exception as e:
                print(f"[Ошибка] {e}")
                save_progress(videos)
                continue

            video["End"] = now_str()
            video["isWatched"] = True
            save_progress(videos)
            print(f"[✓] Видео просмотрено: {video['Link']}")

        await context.close()

    print("Все выбранные видео обработаны. Прогресс сохранён.")



if __name__ == "__main__":
    asyncio.run(main())
