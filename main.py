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
    from datetime import datetime
    import asyncio

    def now_str():
        return datetime.now().strftime("%H:%M %d.%m.%Y")

    def parse_duration(duration_str: str):
        h, m, s = map(int, duration_str.split(":"))
        from datetime import timedelta
        return timedelta(hours=h, minutes=m, seconds=s)


    
    link = video["Link"]
    duration = parse_duration(video["Duration"])

    # 1. Перейти на страницу видео
    await page.goto(link)
    await asyncio.sleep(3)  # дождаться полной загрузки

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

    # Добавляем название в объект video
    video["Title"] = video_title
    print(f"Название видео: {video_title}")


    print(f"[+] Начат просмотр: {link}")
    await asyncio.sleep(duration.total_seconds())  # имитация просмотра видео

    # 3. Оставить ответ на свой комментарий с временем окончания
    end_comment = now_str()
    try:
        # Найти твой комментарий по id канала
        comment_selector = f"a[href='/channel/{my_channel_id}/']"
        comment_element = await page.query_selector(comment_selector)
        if not comment_element:
            print("[!] Мой комментарий не найден, ответ не оставлен")
            return

        # Родительский блок комментария
        parent = await comment_element.evaluate_handle(
            "el => el.closest('.wdp-comment-item-module__comment-wrapper')"
        )

        # Нажать кнопку "Ответить"
        reply_button = await parent.query_selector("button.wdp-comment-reactions-module__button-answer")
        if not reply_button:
            print("[!] Кнопка 'Ответить' не найдена")
            return
        await reply_button.click()
        await asyncio.sleep(1)  # дождаться появления поля для ответа

        # Глобально ищем div contenteditable для ответа
        reply_field = await page.query_selector(
            "div.wdp-comment-input-module__textarea[contenteditable='true']:visible"
        )
        if not reply_field:
            print("[!] Поле для ответа не найдено")
            return

        await reply_field.click()  # установить фокус
        await reply_field.type(end_comment)  # delay=50ms имитация реального ввода

        # Найти глобально кнопку отправки ответа
        send_button = await page.wait_for_selector(
         "button.freyja_char-base-button__contained-accent_Z8hc1:not([disabled])",
            timeout=5000
        )
        await asyncio.sleep(1)

        if send_button:
            await send_button.click()
            print(f"[+] Ответ оставлен: {end_comment}")
        else:
            print("[!] Кнопка отправки ответа не активна")

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

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False
        )
        page = context.pages[0] if context.pages else await context.new_page()

        for video in videos:
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

    print("Все видео обработаны. Прогресс сохранён.")

if __name__ == "__main__":
    asyncio.run(main())
