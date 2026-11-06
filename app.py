"""
Streamlit-приложение для сбора отзывов из Apple App Store через RSS-фид.
Запуск: streamlit run app.py
"""
import re
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st


# ============================================================
# Константы
# ============================================================
RSS_URL_TEMPLATE = (
    "https://itunes.apple.com/{country}/rss/customerreviews/"
    "page={page}/id={app_id}/sortby=mostrecent/json"
)
MAX_PAGES = 10  # ограничение Apple
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

COUNTRY_OPTIONS = [
    "us", "ru", "gb", "de", "fr", "it", "es", "ca",
    "au", "jp", "cn", "br", "in", "ua", "kz", "by",
]


# ============================================================
# Утилиты
# ============================================================
def extract_app_id(raw: str) -> int | None:
    """
    Извлекает числовой ID из строки. Поддерживает:
      - '389801252'
      - 'https://apps.apple.com/us/app/instagram/id389801252'
      - 'id389801252'
    """
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit() and len(raw) >= 6:
        return int(raw)
    match = re.search(r"id(\d+)", raw) or re.search(r"(\d{6,})", raw)
    if match:
        return int(match.group(1))
    return None


def fetch_reviews(app_id: int, country: str, max_pages: int = MAX_PAGES,
                  progress_cb=None) -> tuple[list[dict], list[str]]:
    """
    Собирает отзывы из RSS-фида Apple.
    Возвращает (список отзывов, лог).
    progress_cb(current, total, text) — для обновления st.progress.
    """
    reviews: list[dict] = []
    log: list[str] = []

    for page in range(1, max_pages + 1):
        url = RSS_URL_TEMPLATE.format(country=country, page=page, app_id=app_id)
        log.append(f"Страница {page}: {url}")

        if progress_cb:
            progress_cb(page - 1, max_pages, f"Загружаю страницу {page} из {max_pages}...")

        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
        except requests.RequestException as e:
            log.append(f"❌ Ошибка сети на странице {page}: {e}")
            break

        if response.status_code != 200:
            log.append(f"❌ Статус {response.status_code} на странице {page}. Останавливаюсь.")
            break

        try:
            data = response.json()
        except ValueError:
            log.append(f"⚠️ Страница {page}: не удалось распарсить JSON.")
            break

        feed = data.get("feed", {})
        entries = feed.get("entry", [])

        if isinstance(entries, dict):
            entries = [entries]

        entries = [e for e in entries if "im:rating" in e]

        if not entries:
            log.append(f"ℹ️ Страница {page} пуста — отзывы закончились.")
            break

        for entry in entries:
            reviews.append({
                "author":  entry.get("author", {}).get("name", {}).get("label", ""),
                "title":   entry.get("title", {}).get("label", ""),
                "content": entry.get("content", {}).get("label", ""),
                "rating":  entry.get("im:rating", {}).get("label", ""),
                "version": entry.get("im:version", {}).get("label", ""),
                "updated": entry.get("updated", {}).get("label", ""),
            })
        log.append(f"✅ Получено отзывов со страницы: {len(entries)}")
        time.sleep(0.7)

    if progress_cb:
        progress_cb(max_pages, max_pages, "Готово")

    return reviews, log


def to_dataframe(reviews: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(reviews)
    if df.empty:
        return df
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce").astype("Int64")
    df["updated"] = pd.to_datetime(df["updated"], errors="coerce", utc=True)
    return df


# ============================================================
# Streamlit UI
# ============================================================
st.set_page_config(
    page_title="App Store Reviews",
    page_icon="🍎",
    layout="wide",
)

st.title("🍎 Сбор отзывов из Apple App Store")
st.caption(
    "Данные берутся из публичного RSS-фида Apple. "
    "Максимум — 10 страниц (~500 отзывов), это ограничение самой Apple."
)


# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Параметры")

    app_id_input = st.text_input(
        "ID приложения или ссылка на App Store",
        value="389801252",
        help="Можно вставить чистый ID (389801252) или ссылку вида "
             "https://apps.apple.com/us/app/instagram/id389801252",
    )

    country = st.selectbox(
        "Страна",
        options=COUNTRY_OPTIONS,
        index=0,
        help="Код страны по ISO 3166-1 alpha-2",
    )

    custom_country = st.text_input(
        "…или введите свой код страны",
        value="",
        max_chars=2,
        help="Две латинские буквы. Оставьте пустым, чтобы использовать выбор выше.",
    )

    max_pages = st.slider(
        "Максимум страниц",
        min_value=1,
        max_value=MAX_PAGES,
        value=MAX_PAGES,
        help="Apple отдаёт не больше 10 страниц.",
    )

    start_btn = st.button("🚀 Собрать отзывы", type="primary", use_container_width=True)


# --- Валидация страны ---
final_country = custom_country.strip().lower() or country
if not re.fullmatch(r"[a-z]{2}", final_country):
    st.error("Код страны должен состоять из двух латинских букв.")
    st.stop()


# ============================================================
# Запуск сбора
# ============================================================
if start_btn:
    app_id = extract_app_id(app_id_input)
    if app_id is None:
        st.error(
            "Не удалось распознать ID приложения. "
            "Введите число (например, 389801252) или ссылку на App Store."
        )
        st.stop()

    st.info(
        f"**APP_ID** = `{app_id}`  |  "
        f"**COUNTRY** = `{final_country}`  |  "
        f"**MAX_PAGES** = `{max_pages}`"
    )

    progress_bar = st.progress(0, text="Начинаю сбор...")

    def update_progress(current: int, total: int, text: str) -> None:
        progress_bar.progress(min(current / total, 1.0), text=text)

    with st.spinner("Собираю отзывы..."):
        reviews, log = fetch_reviews(
            app_id=app_id,
            country=final_country,
            max_pages=max_pages,
            progress_cb=update_progress,
        )

    with st.expander("📜 Лог загрузки", expanded=False):
        st.code("\n".join(log), language="text")

    if not reviews:
        st.warning(
            "Отзывов не найдено. Проверьте ID и страну. "
            "Если приложение новое в выбранной стране — попробуйте `us`."
        )
        st.stop()

    df = to_dataframe(reviews)

    st.success(f"✅ Собрано отзывов: **{len(df)}**")

    # Метрики
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Всего отзывов", len(df))
    col2.metric("Средний рейтинг", f"{df['rating'].mean():.2f}")
    col3.metric("Уникальных версий", df["version"].nunique())
    col4.metric("Уникальных авторов", df["author"].nunique())

    # Предпросмотр
    st.subheader("Предпросмотр")
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "rating": st.column_config.NumberColumn("rating", format="%d ⭐"),
            "updated": st.column_config.DatetimeColumn("updated", format="YYYY-MM-DD HH:mm"),
        },
    )

    # Скачивание
    csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    filename = f"app_{app_id}_{final_country}_reviews_{datetime.now():%Y%m%d_%H%M%S}.csv"

    st.download_button(
        label="⬇️ Скачать CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
        type="primary",
    )
    st.caption(f"Файл будет сохранён как `{filename}`")
