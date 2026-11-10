# -*- coding: utf-8 -*-
"""
СБОРЩИК АФИШИ ФИЛАРМОНИИ КУЗБАССА
=================================

Что делает программа:
  1. Открывает афишу на сайте https://www.kemfil.ru и находит все месяцы.
  2. Из каждого месяца берёт список концертов (дату, время, пометки «ОТМЕНА»,
     «ПЕРЕНОС», «Пушкинская карта»).
  3. Открывает страницу каждого предстоящего концерта и забирает подробности.
  4. Сохраняет каждый концерт в отдельный текстовый файл в папке «data/concerts».
  5. Сохраняет постоянные страницы для зрителей (контакты, возврат билетов и т.д.)
     в папку «data/info».

Как запустить (подробнее — в файле README.md):
  Полный сбор:            .venv\\Scripts\\python.exe collector\\sborshik.py
  Проба на 3 концертах:   .venv\\Scripts\\python.exe collector\\sborshik.py --proba 3
"""

# ============================================================================
#  НАСТРОЙКИ
#  Всё, что может понадобиться поменять, собрано здесь.
#  Текст в кавычках менять можно, имена слева от знака «=» — не трогайте.
# ============================================================================

from pathlib import Path

# Адрес сайта. От него считаются короткие адреса вида "/contact".
SITE_URL = "https://www.kemfil.ru"

# Страница афиши. Программа откроет её и найдёт ссылки на все месяцы.
AFISHA_URL = "https://www.kemfil.ru/afisha"

# Программа открывает ТОЛЬКО страницы этих сайтов.
# Ссылки на другие сайты (например, продажа билетов на intickets.ru)
# записываются в файл, но программа по ним не ходит.
ALLOWED_HOSTS = ["kemfil.ru", "www.kemfil.ru"]

# Пауза между обращениями к сайту, в секундах. Не ставьте меньше 1,
# чтобы не нагружать сайт.
PAUSE_SECONDS = 1

# Сколько секунд ждать ответа сайта, прежде чем считать, что страница не открылась.
TIMEOUT_SECONDS = 30

# Сколько раз пробовать открыть страницу, если с первого раза не получилось.
ATTEMPTS = 2

# Как программа «представляется» сайту: как обычный браузер.
# Никаких личных данных здесь нет и не должно быть.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

# Папки, куда сохраняются результаты. По умолчанию — рядом с этой программой.
PROGRAM_FOLDER = Path(__file__).resolve().parent.parent  # папка бота (эта программа лежит в её подпапке)
BASE_FOLDER = PROGRAM_FOLDER / "data"
CONCERTS_FOLDER = BASE_FOLDER / "concerts"
INFO_FOLDER = BASE_FOLDER / "info"
PEOPLE_FOLDER = BASE_FOLDER / "collectives"   # коллективы, их руководители и артисты

# Раздел сайта «Коллективы и артисты»
COLLECTIVES_URL = "https://www.kemfil.ru/collective"

# Файл, куда записываются ошибки и предупреждения последнего запуска.
LOG_FILE = BASE_FOLDER / "collector_log.txt"

# До какой даты включительно собирать концерты (год-месяц-день).
# Пустые кавычки "" — собирать всю афишу, сколько её есть на сайте.
COLLECT_UNTIL = "2026-12-31"

# Концерты, которые НЕ собирать: если на странице концерта есть такие слова.
# Сейчас — гастроли приглашённых коллективов (не концерты филармонии).
# Регистр букв и «ё»/«е» не важны. Чтобы собирать всё — оставьте пустые скобки [].
SKIP_IF_TEXT = [
    "обслуживает звукорежиссёр приглашенного коллектива",
]

# Что писать, если на сайте нет какого-то поля.
NOT_SPECIFIED = "не указано"

# Постоянные страницы для зрителей.
# Слева — имя файла (без .txt), справа — адрес страницы на сайте.
# Чтобы добавить страницу, допишите строку по образцу; чтобы убрать — удалите строку.
INFO_PAGES = {
    "Контакты": "/contact",
    "Как добраться": "/destination",
    "Как купить билет": "/afisha/ticketbuy",
    "Электронный билет": "/afisha/elbilet",
    "Возврат билетов": "/afisha/vozvrat",
    "Изменения в афише": "/afisha/izmenenia",
    "Пушкинская карта": "/pkarta",
    "Правила посещения": "/pravila",
    "Льготы": "/lgoty",
    "Акции": "/promotion",
    "Участникам СВО": "/uchastnikam-svo",
    "Частые вопросы": "/faq",
    "Доступная среда": "/dlya-zriteley-s-ovp",
    "Абонементы": "/abonements",
    "Буфет": "/bufet",
    "Безопасность": "/safety",
    "Залы": "/philharmony/halls",
    "Большой зал": "/philharmony/halls/bolshoy-zal",
    "Органный зал": "/philharmony/halls/organnyzal",
    # О филармонии — для приезжих и тех, кто спрашивает «что у вас за учреждение»
    "История": "/philharmony/history",
    "Проекты": "/project",
    "Музей": "/philharmony/museum",
    "Орган": "/philharmony/organ",
    "Борис Штоколов": "/philharmony/shtokolov",
    "Услуги": "/philharmony/services",
}

# ============================================================================
#  ДАЛЬШЕ — САМА ПРОГРАММА. Для обычной работы здесь ничего менять не нужно.
# ============================================================================

import argparse
import re
import shutil
import sys
import time
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Не найдены библиотеки requests и beautifulsoup4.")
    print("Запустите программу через окружение проекта: .venv\\Scripts\\python.exe collector\\sborshik.py")
    print("Если окружения ещё нет — см. раздел «Установка» в README.md.")
    sys.exit(1)


MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# Теги, после которых в тексте должна начинаться новая строка.
BLOCK_TAGS = [
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "blockquote", "dt", "dd",
]

# Всё, что не относится к тексту страницы: меню, кнопки, формы, карты, «Поделиться» и т.п.
JUNK_SELECTORS = [
    "script", "style", "noscript", "iframe", "form", "button", "nav", "select",
    "input", "textarea", "svg", "title", "meta", "link",
    "ul.uk-breadcrumb", ".ya-share2", ".modal", "div.card.afisha",
]

errors = []          # сюда собираются ошибки, чтобы посчитать их в конце
_last_request = 0.0  # время последнего обращения к сайту (для паузы)
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"})


# ----------------------------------------------------------------------------
#  Журнал и сообщения
# ----------------------------------------------------------------------------

def log(message):
    """Показывает сообщение на экране и записывает его в журнал."""
    print(message)
    # В журнал — одной строкой и не длиннее 300 знаков (журнал очищается при каждом запуске)
    short = " ".join(str(message).split())
    short = short[:300] + "…" if len(short) > 300 else short
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {short}\n")


def report_error(message):
    """Записывает ошибку. Программа после этого продолжает работу."""
    errors.append(message)
    log("ОШИБКА: " + message)


# ----------------------------------------------------------------------------
#  Обращение к сайту
# ----------------------------------------------------------------------------

def is_allowed(url):
    """Проверяет, что адрес относится к нашему сайту."""
    host = (urlparse(url).hostname or "").lower()
    return host in ALLOWED_HOSTS


def _polite_pause():
    """Ждёт, чтобы между обращениями к сайту прошло не меньше PAUSE_SECONDS."""
    global _last_request
    wait = max(PAUSE_SECONDS, 1) - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def fetch(url, raw=False):
    """
    Открывает страницу сайта и возвращает её в разобранном виде
    (или исходный HTML-текст, если raw=True).
    Если страница не открылась — записывает ошибку и возвращает None.
    Переадресации на другие сайты не выполняются.
    """
    if not is_allowed(url):
        report_error(f"Адрес не с сайта филармонии, пропускаю: {url}")
        return None

    problem = "неизвестная причина"
    for attempt in range(1, ATTEMPTS + 1):
        try:
            current = url
            for _ in range(5):  # не больше 5 переадресаций подряд
                _polite_pause()
                response = _session.get(current, timeout=TIMEOUT_SECONDS, allow_redirects=False)
                if response.status_code in (301, 302, 303, 307, 308):
                    current = urljoin(current, response.headers.get("Location", ""))
                    if not is_allowed(current):
                        report_error(f"Страница {url} отправляет на другой сайт ({current}), не иду туда")
                        return None
                    continue
                break
            if response.status_code == 200:
                html = response.content.decode("utf-8", errors="replace")
                return html if raw else BeautifulSoup(html, "html.parser")
            problem = f"сайт ответил кодом {response.status_code}"
        except requests.RequestException as e:
            problem = f"не удалось связаться с сайтом ({e.__class__.__name__})"
        if attempt < ATTEMPTS:
            time.sleep(5)

    report_error(f"Страница не открылась: {url} — {problem}")
    return None


# ----------------------------------------------------------------------------
#  Работа с текстом
# ----------------------------------------------------------------------------

def clean_text(text):
    """Убирает лишние пробелы, пустые строки и повторяющиеся подряд строки."""
    text = text.replace("\xa0", " ").replace("​", "").replace("\r", "")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = line.strip("|").strip()  # хвосты от таблиц
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return "\n".join(lines)


def one_line(element):
    """Текст элемента одной строкой."""
    if element is None:
        return ""
    return " ".join(clean_text(element.get_text(" ")).split())


def first_text(element):
    """Первый непустой кусочек текста внутри элемента (без вложенных блоков)."""
    if element is None:
        return ""
    for piece in element.strings:
        piece = " ".join(piece.split())
        if piece:
            return piece
    return ""


def element_text(element):
    """
    Превращает кусок страницы в аккуратный текст: абзацы — с новой строки,
    пункты списков — с «•», ячейки таблиц — через «|».
    """
    if element is None:
        return ""
    # Каждая строка таблицы — одной строкой текста: «ячейка | ячейка | ячейка»
    for row in element.find_all("tr"):
        cells = [one_line(cell) for cell in row.find_all(["td", "th"])]
        row.replace_with("\n" + " | ".join(c for c in cells if c) + "\n")
    for br in element.find_all("br"):
        br.replace_with("\n")
    for li in element.find_all("li"):
        if li.get_text(strip=True):  # пустые пункты (остатки меню) пропускаем
            li.insert(0, "• ")
    for tag in element.find_all(BLOCK_TAGS):
        tag.insert_before("\n")
        tag.append("\n")
    return clean_text(element.get_text())


def has_classes(*names):
    """Помощник для поиска: «у тега есть все эти классы оформления»."""
    wanted = set(names)
    return lambda tag: wanted.issubset(set(tag.get("class") or []))


def find_with_classes(where, tag_name, *names):
    if where is None:
        return None
    check = has_classes(*names)
    return where.find(lambda t: t.name == tag_name and check(t))


def find_buy_link(where):
    """Ссылка с надписью «Купить билет»."""
    if where is None:
        return ""
    for a in where.find_all("a", href=True):
        if "Купить билет" in a.get_text():
            return urljoin(SITE_URL + "/", a["href"])
    return ""


TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def safe_filename(name, max_length=80):
    """
    Имя файла латиницей: «Сказка с оркестром «Золушка»» → «skazka_s_orkestrom_zolushka».
    Латинские имена аккуратно выглядят на GitHub и не ломаются на разных компьютерах;
    само русское название хранится внутри файла.
    """
    latin = "".join(TRANSLIT.get(ch, ch) for ch in name.lower())
    latin = re.sub(r"[^a-z0-9]+", "_", latin).strip("_")
    if len(latin) > max_length:
        latin = latin[:max_length].rstrip("_")
    return latin or "bez_nazvaniya"


# ----------------------------------------------------------------------------
#  Афиша: список месяцев и карточки концертов
# ----------------------------------------------------------------------------

def find_months(soup):
    """Находит на афише ссылки на месяцы вида ?month=12&year=2026."""
    months = set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"month=(\d{1,2})&(?:amp;)?year=(\d{4})", a["href"])
        if m:
            months.add((int(m.group(2)), int(m.group(1))))
    return sorted(months)


def parse_cards(soup, year, month):
    """Разбирает карточки концертов на странице одного месяца афиши."""
    concerts = []
    for card in soup.select("div.card.afisha"):
        try:
            link = card.find("a", href=re.compile(r"concert\?id=\d+"))
            if link is None:
                continue
            page_url = urljoin(SITE_URL + "/", link["href"])
            concert_id = re.search(r"id=(\d+)", link["href"]).group(1)

            # Название и пометка «ОТМЕНА» / «ПЕРЕНОС»
            title, status = "", ""
            h2 = card.find("h2")
            if h2 is not None:
                badge = h2.find("span", class_="badge")
                if badge is not None:
                    status = one_line(badge)
                    badge.extract()
                title = one_line(h2)

            # Строка вида «05.11, чт / 19:00 / Большой зал / 6+»
            line = one_line(card.find("p", class_="d-md-none"))
            parts = [p.strip() for p in line.split("/")]
            dm = re.search(r"(\d{1,2})\.(\d{1,2})", parts[0] if parts else "")
            if not dm:
                report_error(f"Не нашёл дату в карточке концерта {page_url}")
                continue
            day, mon = int(dm.group(1)), int(dm.group(2))
            # Если месяц в карточке «меньше» месяца страницы (январь на декабрьской
            # странице) — значит, это уже следующий год.
            card_year = year + 1 if (mon < month and month - mon > 6) else year
            concert_date = date(card_year, mon, day)

            start_time = parts[1] if len(parts) > 1 and re.fullmatch(r"\d{1,2}:\d{2}", parts[1]) else ""
            rest = parts[2:]
            age = rest.pop() if rest and re.fullmatch(r"\d{1,2}\+", rest[-1]) else ""
            hall = " / ".join(rest)

            # Цена
            price = ""
            label = card.find(string=re.compile("Стоимость билетов"))
            if label is not None:
                price = one_line(label.find_next("span"))

            # Пушкинская карта: на афише у таких событий стоит значок с подписью
            pushkin = (
                card.find(attrs={"title": re.compile("Пушкинск", re.I)}) is not None
                or card.find("img", src=re.compile("pkarta")) is not None
            )

            # Короткий текст под названием (у отменённых там причина отмены)
            short = ""
            column = card.find("div", class_="col-md-6")
            if column is not None:
                short = one_line(column.find("p", class_="fw-light"))

            note = one_line(card.find("div", class_="alert"))

            concerts.append({
                "id": concert_id, "url": page_url, "title": title, "status": status,
                "date": concert_date, "time": start_time, "hall": hall, "age": age,
                "price": price, "pushkin": pushkin, "short": short, "note": note,
                "buy": find_buy_link(card),
            })
        except Exception as e:  # одна «сломанная» карточка не должна останавливать всё
            report_error(f"Не удалось разобрать карточку на афише {month:02d}.{year}: {e}")
    return concerts


# ----------------------------------------------------------------------------
#  Страница отдельного концерта
# ----------------------------------------------------------------------------

def parse_concert_page(soup):
    """Забирает подробности со страницы концерта."""
    info = {}
    # На странице есть блок с названием, датой, залом, ценой и кнопкой билета
    block = soup.find(lambda t: t.name == "div" and has_classes("uk-card", "uk-hidden@l")(t))
    where = block if block is not None else soup

    h1 = where.find("h1")
    if h1 is not None:
        badge = h1.find("span", class_="badge")
        if badge is not None:
            info["status"] = one_line(badge)
            badge.extract()
        info["title"] = one_line(h1)

    info["date_text"] = one_line(where.find("h2"))  # например «5 ноября, чт, 19:00»
    info["hall"] = first_text(find_with_classes(where, "p", "uk-text-large", "uk-text-secondary"))

    price_p = find_with_classes(where, "p", "uk-text-secondary", "uk-text-bold")
    info["price"] = first_text(price_p).strip(" •")
    if price_p is not None:
        info["age"] = one_line(price_p.find("span", class_="uk-text-bold"))

    info["buy"] = find_buy_link(where)

    # Вместо ссылки на билет иногда стоит надпись-кнопка, например «ВСЕ БИЛЕТЫ ПРОДАНЫ!»
    if block is not None:
        labels = [one_line(b) for b in block.find_all("button")]
        info["ticket_note"] = "; ".join(t for t in labels if t)

    # Продолжительность
    heading = soup.find(lambda t: t.name == "h2" and "Продолжительность" in t.get_text())
    if heading is not None:
        info["duration"] = one_line(heading.find_next("p"))

    # Примечания вроде «Событие обслуживает звукорежиссёр приглашённого коллектива»
    info["notes"] = [one_line(n) for n in soup.select("div.uk-alert-primary")]

    # Описание
    description = soup.find(lambda t: t.name == "div"
                            and has_classes("uk-text-large", "uk-text-secondary", "uk-padding-small")(t))
    info["description"] = element_text(description)
    return info


def check_date(card, date_text):
    """Сверяет дату в афише с датой на странице концерта; при расхождении — предупреждение."""
    m = re.search(r"(\d{1,2})\s+([а-яё]+)", date_text.lower())
    if not m or m.group(2) not in MONTHS:
        return
    if (int(m.group(1)), MONTHS[m.group(2)]) != (card["date"].day, card["date"].month):
        log(f"ПРЕДУПРЕЖДЕНИЕ: дата в афише ({card['date']:%d.%m}) и на странице "
            f"({date_text}) не совпадают: {card['url']}. Записываю дату из афиши.")


def build_concert_text(card, page):
    """Собирает текст файла концерта."""
    def pick(*values):
        for v in values:
            if v:
                return v
        return NOT_SPECIFIED

    title = pick(page.get("title"), card["title"])
    weekday = WEEKDAYS[card["date"].weekday()]
    time_match = re.search(r"\d{1,2}:\d{2}", page.get("date_text", ""))
    start_time = time_match.group(0) if time_match else card["time"]
    when = f"{card['date']:%d.%m.%Y}, {weekday}" + (f", {start_time}" if start_time else "")

    status_word = page.get("status") or card["status"]
    if status_word:
        status = status_word + (f". {card['short']}" if card["short"] else "")
    else:
        status = "по расписанию"
    if page.get("ticket_note"):
        status += f". {page['ticket_note']}"

    description = page.get("description") or ""
    notes = []
    for n in [card["note"]] + page.get("notes", []):
        if n and n not in notes and n not in description:
            notes.append(n)
    if notes:
        description = (description + "\n" if description else "") + "\n".join("Примечание: " + n for n in notes)

    lines = [
        f"Название: {title}",
        f"Дата и время: {when}",
        f"Зал: {pick(page.get('hall'), card['hall'])}",
        f"Возраст: {pick(page.get('age'), card['age'])}",
        f"Цена: {pick(page.get('price'), card['price'])}",
        f"Пушкинская карта: {'да' if card['pushkin'] else 'нет'}",
        f"Статус: {status}",
        f"Продолжительность: {pick(page.get('duration'))}",
        f"Ссылка: {pick(page.get('buy'), card['buy'])}",
        f"Страница концерта: {card['url']}",
        "Описание:",
        description or NOT_SPECIFIED,
    ]
    return title, "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
#  Постоянные страницы
# ----------------------------------------------------------------------------

def extract_page_text(soup):
    """Вынимает основной текст постоянной страницы без меню, подвала и кнопок."""
    main = soup.find("div", class_="container-xl")
    if main is None:
        return ""

    # Подвал сайта иногда оказывается внутри основного блока — убираем его
    for footer in main.find_all("div", class_="container-fluid"):
        footer.decompose()

    # Вкладки (например, «Описание», «Схема зала»): подписываем каждую заголовком
    for pane in main.select("div.tab-pane"):
        button = soup.find(id=pane.get("aria-labelledby")) if pane.get("aria-labelledby") else None
        if not pane.get_text(strip=True):
            pictures = [urljoin(SITE_URL + "/", img["src"]) for img in pane.find_all("img", src=True)]
            if pictures:
                pane.clear()
                pane.append("Картинка (текста нет): " + ", ".join(pictures))
        if button is not None:
            pane.insert(0, "\n" + one_line(button) + ":\n")

    for selector in JUNK_SELECTORS:
        for junk in main.select(selector):
            junk.decompose()
    for img in main.find_all("img"):
        img.decompose()

    return element_text(main)


def collect_info_pages():
    INFO_FOLDER.mkdir(parents=True, exist_ok=True)
    saved = 0
    for name, path in INFO_PAGES.items():
        url = urljoin(SITE_URL + "/", path)
        try:
            soup = fetch(url)
            if soup is None:
                continue
            text = extract_page_text(soup)
            if len(text) < 50:
                report_error(f"На странице {url} не нашёлся текст — возможно, сайт изменился")
                continue
            file = INFO_FOLDER / (safe_filename(name) + ".txt")
            # 1-я строка — адрес, 2-я — русское название страницы, дальше — текст
            file.write_text(url + "\nСтраница: " + name + "\n" + text + "\n", encoding="utf-8")
            saved += 1
            print(f"  сохранено: info/{file.name}")
        except Exception as e:
            report_error(f"Не удалось сохранить страницу {url}: {e}")
    return saved


# ----------------------------------------------------------------------------
#  Главный порядок работы
# ----------------------------------------------------------------------------

def collect_concerts(limit):
    """Собирает концерты во временную папку и затем заменяет ею «data/concerts»."""
    today = date.today()

    afisha = fetch(AFISHA_URL)
    if afisha is None:
        report_error("Не открылась афиша. Старые файлы концертов оставлены как есть.")
        return 0, 0

    until = date.fromisoformat(COLLECT_UNTIL) if COLLECT_UNTIL else date.max
    months = [ym for ym in find_months(afisha)
              if (today.year, today.month) <= ym <= (until.year, until.month)]
    if not months:
        report_error("На афише не нашлись ссылки на месяцы — возможно, сайт изменился. "
                     "Беру только текущий месяц.")
        months = [(today.year, today.month)]
    log(f"Месяцы в афише: {', '.join(f'{m:02d}.{y}' for y, m in months)}")

    # 1) Список концертов по месяцам
    cards = {}
    for year, month in months:
        soup = fetch(f"{AFISHA_URL}?month={month}&year={year}")
        if soup is None:
            continue
        found = parse_cards(soup, year, month)
        upcoming = [c for c in found if today <= c["date"] <= until]
        print(f"  {month:02d}.{year}: событий в афише {len(found)}, предстоящих {len(upcoming)}")
        for c in upcoming:
            cards.setdefault(c["id"], c)
        if limit and len(cards) >= limit:
            break

    concerts = sorted(cards.values(), key=lambda c: (c["date"], c["time"]))
    if limit:
        concerts = concerts[:limit]
    log(f"Предстоящих событий к сбору: {len(concerts)}"
        + (f" (по {until:%d.%m.%Y} включительно)" if COLLECT_UNTIL else ""))

    # 2) Подробности по каждому концерту — во временную папку
    temp_folder = BASE_FOLDER / "concerts_new"
    if temp_folder.exists():
        shutil.rmtree(temp_folder)
    temp_folder.mkdir(parents=True)

    # Windows не разрешает пути длиннее ~260 символов. Чем длиннее путь к папке,
    # тем короче придётся сделать название в имени файла (в самом файле оно полное).
    room = 245 - len(str(temp_folder)) - len("\\2026-11-05_") - len("_id00000.txt")
    name_length = max(20, min(80, room))

    saved, changed, skipped = 0, 0, 0
    skip_words = [w.lower().replace("ё", "е") for w in SKIP_IF_TEXT]
    for number, card in enumerate(concerts, 1):
        try:
            soup = fetch(card["url"])
            if soup is None:
                continue
            page = parse_concert_page(soup)
            check_date(card, page.get("date_text", ""))
            title, text = build_concert_text(card, page)
            if any(w in text.lower().replace("ё", "е") for w in skip_words):
                skipped += 1
                print(f"  [{number}/{len(concerts)}] пропущен (приглашённый коллектив): {title}")
                continue

            base_name = f"{card['date']:%Y-%m-%d}_{safe_filename(title, name_length)}"
            file = temp_folder / (base_name + ".txt")
            if file.exists():  # два сеанса в один день — добавляем время
                file = temp_folder / f"{base_name}_{card['time'].replace(':', '-')}.txt"
            if file.exists():
                file = temp_folder / f"{base_name}_id{card['id']}.txt"
            file.write_text(text, encoding="utf-8")
            saved += 1
            if card["status"] or page.get("status"):
                changed += 1
            print(f"  [{number}/{len(concerts)}] {file.name}")
        except Exception as e:
            report_error(f"Не удалось обработать концерт {card['url']}: {e}")

    # 3) Заменяем старую папку новой (только если что-то собрали)
    if saved == 0:
        shutil.rmtree(temp_folder, ignore_errors=True)
        report_error("Не сохранено ни одного концерта. Старые файлы оставлены как есть.")
        return 0, 0
    # Саму папку не трогаем (её может держать открытый Проводник) —
    # меняем только файлы внутри: старые удаляем, новые перекладываем.
    CONCERTS_FOLDER.mkdir(parents=True, exist_ok=True)
    for old_file in CONCERTS_FOLDER.glob("*.txt"):
        try:
            old_file.unlink()
        except OSError as e:
            report_error(f"Не удалось удалить старый файл «{old_file.name}» (возможно, он открыт): {e}")
    for new_file in temp_folder.glob("*.txt"):
        try:
            new_file.replace(CONCERTS_FOLDER / new_file.name)
        except OSError as e:
            report_error(f"Не удалось переложить файл «{new_file.name}»: {e}")
    try:
        temp_folder.rmdir()
    except OSError:
        pass  # если что-то не переложилось, временная папка останется — это не страшно
    if skipped:
        log(f"Пропущено концертов приглашённых коллективов (SKIP_IF_TEXT): {skipped}")
    return saved, changed


# ----------------------------------------------------------------------------
#  Коллективы и артисты: кто чем руководит и какие концерты у коллектива
# ----------------------------------------------------------------------------

def html_to_text(fragment, limit=1500):
    """Короткий текст из куска HTML (для описаний коллективов и артистов)."""
    soup = BeautifulSoup(fragment, "html.parser")
    for junk in soup.select("script, style, img, button"):
        junk.decompose()
    text = element_text(soup)
    return text[:limit].rsplit(" ", 1)[0] + " …" if len(text) > limit else text


def parse_collective_page(html, url):
    """
    Разбирает страницу коллектива или артиста. Возвращает словарь:
    название, тип, роли (должность → имя и ссылка), номера концертов, описание.
    """
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    name = " ".join(re.sub(r"<[^>]+>", " ", h1.group(1)).split()) if h1 else ""
    info = {"name": name, "url": url, "roles": [], "concerts": [], "description": "", "members": []}

    # Вкладка «Состав»: все артисты коллектива с подписью («Артист», «Фортепиано», «Директор»)
    begin = html.find('id="pills-sostav"')
    if begin > 0:
        end = min([i for i in (html.find('id="pills-concert"', begin), html.find('id="pills-media"', begin),
                               html.find('id="pills-descr"', begin)) if i > begin] or [begin + 100000])
        for person, role in re.findall(
                r'<h5 class="h5 card-title">\s*([^<]+?)\s*</h5>.*?<small class="text-muted">\s*([^<]*?)\s*</small>',
                html[begin:end], re.S):
            person = " ".join(person.split())
            if person and (person, role) not in info["members"]:
                info["members"].append((person, " ".join(role.split())))

    # Строка ролей вверху страницы коллектива: «Главный дирижёр — Василий Шульга» и т.п.
    start, stop = html.find("Год создания"), html.find("Страницы в Интернете")
    if start > 0:
        info["type"] = "коллектив"
        header = html[start:stop if stop > start else start + 5000]
        for role, link, person in re.findall(
                r'<h5 class="text-black-50[^"]*">\s*([^<]*?)\s*(?:</h5>)?\s*'
                r'<p class="h5[^"]*">\s*(?:<a href="((?:https?://(?:www\.)?kemfil\.ru)?/collective/[^"]+)">)?'
                r'\s*([^<]*)', header):
            role, person = role.strip(), person.strip()
            if role and person and role != "Год создания":
                info["roles"].append((role, person, urljoin(SITE_URL + "/", link) if link else ""))
    else:
        info["type"] = "артист"

    # Вкладка «Концерты»: номера концертов коллектива
    begin = html.find('id="pills-concert"')
    if begin > 0:
        end = html.find('id="pills-media"', begin)
        block = html[begin:end if end > begin else begin + 200000]
        info["concerts"] = sorted(set(re.findall(r"(?:concert|tickbuy)\?id=(\d+)", block)), key=int)

    # Описание: вкладка «Описание» у коллектива, основной текст у артиста
    begin = html.find('id="pills-descr"')
    if begin > 0:
        begin = html.find(">", begin) + 1  # текст начинается после закрывающей скобки тега
        end = html.find('id="pills-sostav"', begin)
        end = html.rfind("<", begin, end) if end > begin else begin + 20000  # до начала следующего тега
        info["description"] = html_to_text(html[begin:end])
    else:
        main_start = html.find('<div class="container-xl')
        main_end = html.find('<div class="container-fluid text-white')
        if main_start > 0:
            body = re.sub(r'<ul class="uk-breadcrumb">.*?</ul>|<h1[^>]*>.*?</h1>', "",
                          html[main_start:main_end if main_end > main_start else None], flags=re.S)
            info["description"] = html_to_text(body)
    return info


def collect_collectives():
    """Сохраняет коллективы, их руководителей и артистов в папку «data/collectives»."""
    listing = fetch(COLLECTIVES_URL, raw=True)
    if listing is None:
        report_error("Не открылась страница «Коллективы и артисты». Старые файлы оставлены.")
        return 0

    # Ссылки на коллективы и артистов + подпись (у артистов — специальность: «баритон»…)
    pages = {}
    for link, text in re.findall(r'<a[^>]+href="(/collective/[a-z0-9_-]+)"[^>]*>(.*?)</a>', listing, re.S):
        text = " ".join(re.sub(r"<[^>]+>", " ", text).split())
        pages.setdefault(urljoin(SITE_URL + "/", link), text)

    results, leaders = [], {}
    for url, caption in pages.items():
        html = fetch(url, raw=True)
        if html is None:
            continue
        try:
            info = parse_collective_page(html, url)
            if not info["name"]:
                info["name"] = caption
            # У артиста подпись в списке — «Олег Маликов баритон»: всё после имени — специальность
            if info["type"] == "артист" and caption.startswith(info["name"]):
                info["specialty"] = caption[len(info["name"]):].strip()
            results.append(info)
            for _, person, person_url in info["roles"]:
                if person_url and person_url not in pages:
                    leaders[person_url] = person
        except Exception as e:
            report_error(f"Не удалось разобрать страницу {url}: {e}")

    # Личные страницы руководителей (там полное имя с отчеством и биография)
    for url, person in leaders.items():
        html = fetch(url, raw=True)
        if html is None:
            continue
        try:
            info = parse_collective_page(html, url)
            info["type"] = "артист"
            info["name"] = info["name"] or person
            results.append(info)
        except Exception as e:
            report_error(f"Не удалось разобрать страницу {url}: {e}")

    if not results:
        report_error("Не нашлось ни одного коллектива — возможно, сайт изменился. Старые файлы оставлены.")
        return 0

    PEOPLE_FOLDER.mkdir(parents=True, exist_ok=True)
    for old in PEOPLE_FOLDER.glob("*.txt"):
        try:
            old.unlink()
        except OSError as e:
            report_error(f"Не удалось удалить старый файл «{old.name}»: {e}")
    for info in results:
        lines = [f"Название: {info['name']}", f"Тип: {info['type']}", f"Страница: {info['url']}"]
        if info.get("specialty"):
            lines.append(f"Специальность: {info['specialty']}")
        for role, person, person_url in info["roles"]:
            lines.append(f"Роль: {role} | {person} | {person_url}")
        for person, role in info.get("members", []):
            lines.append(f"Состав: {person} | {role}")
        if info["concerts"]:
            lines.append("Концерты: " + ", ".join(info["concerts"]))
        lines += ["Описание:", info["description"] or NOT_SPECIFIED]
        file = PEOPLE_FOLDER / (safe_filename(info["name"]) + ".txt")
        file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  сохранено: collectives/{file.name}")
    return len(results)


def main():
    parser = argparse.ArgumentParser(description="Сборщик афиши Филармонии Кузбасса")
    parser.add_argument("--proba", type=int, default=0, metavar="N",
                        help="пробный запуск: собрать только N ближайших концертов")
    parser.add_argument("--tolko-kollektivy", action="store_true",
                        help="собрать только коллективы и артистов (быстро, без афиши)")
    parser.add_argument("--bez-afishi", action="store_true",
                        help="собрать постоянные страницы и коллективы, афишу не трогать")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    BASE_FOLDER.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")  # журнал — только о последнем запуске
    started = time.monotonic()
    log(f"Запуск сборщика. Сегодня {date.today():%d.%m.%Y}."
        + (f" ПРОБНЫЙ ЗАПУСК: {args.proba} концерта(ов)." if args.proba else ""))

    saved = changed = info_saved = 0
    try:
        if not args.tolko_kollektivy:
            if not args.bez_afishi:
                print("\nСобираю концерты...")
                saved, changed = collect_concerts(args.proba)
            print("\nСобираю постоянные страницы...")
            info_saved = collect_info_pages()
        print("\nСобираю коллективы и артистов...")
        people_saved = collect_collectives()
    except KeyboardInterrupt:
        log("Сбор остановлен вручную. Папка с концертами не изменена.")
        sys.exit(1)

    minutes = (time.monotonic() - started) / 60
    log("")
    log("=" * 50)
    log("ИТОГ")
    if not args.tolko_kollektivy:
        log(f"Концертов сохранено: {saved} (из них с пометкой «отмена» или «перенос»: {changed})")
        log(f"Постоянных страниц сохранено: {info_saved} из {len(INFO_PAGES)}")
    log(f"Коллективов и артистов сохранено: {people_saved}")
    log(f"Ошибок: {len(errors)}" + (" — подробности в файле data/collector_log.txt" if errors else ""))
    log(f"Время работы: {minutes:.1f} мин.")
    log("=" * 50)


if __name__ == "__main__":
    main()
