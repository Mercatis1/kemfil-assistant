# -*- coding: utf-8 -*-
"""
ПОМОЩНИК ФИЛАРМОНИИ КУЗБАССА: ОТВЕТЫ ЗРИТЕЛЯМ ПО БАЗЕ
=====================================================

Как это работает (RAG — «найти, потом ответить»):
  1. Сообщение зрителя (вместе с его предыдущими сообщениями) превращается
     в «отпечаток смысла» (модель bge-m3).
  2. В индексе ищутся подходящие кусочки — по смыслу, по точным словам
     и по названию концерта.
  3. Если в разговоре есть дата или период («в декабре», «на выходных»,
     «новогодняя программа»), дополнительно берутся все события этого периода.
     Если зритель сказал, что идёт с детьми или без детей, — события отбираются по возрасту.
  4. Найденное, начало разговора и инструкция (промпт) отдаются модели, и она пишет
     ответ только по этим сведениям. Инструкция лежит в папке «rules»
     (файл «system_prompt.txt»), модель выбирается ниже (CHAT_PROVIDER).

Сам по себе этот файл не запускается — с помощником разговаривают в окне (run_assistant.bat).
"""

# ============================================================================
#  НАСТРОЙКИ
# ============================================================================

from pathlib import Path

PROGRAM_FOLDER = Path(__file__).resolve().parent.parent  # папка бота (эта программа лежит в её подпапке)
INDEX_FILE = PROGRAM_FOLDER / "data" / "index.json"
PEOPLE_FILE = PROGRAM_FOLDER / "data" / "people.json"   # дирижёры, руководители, артисты

# Сколько концертов максимум показывать модели, когда зритель называет дирижёра или артиста
MAX_PERSON_CONCERTS = 10

# Сколько человек из одного сообщения учитывать («люблю Шульгу и Наталью Кузнецову»)
MAX_PERSONS = 3

OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"      # та же модель, что в indeksator.py (поиск всегда на этом компьютере)

# ---- КТО ПИШЕТ ОТВЕТЫ: переключатель ----
# Это модель, с которой открывается окно; в самом окне её можно сменить в списке сверху.
# "ollama"   — локальная модель на этом компьютере (CHAT_MODEL ниже). Данные никуда не уходят.
# "gigachat" — ГигаЧат от Сбера через интернет (GIGACHAT_MODEL ниже). Нужны ключ и сертификат
#              Минцифры (см. README). Сообщения зрителей уходят в Сбер (сервера в России).
# "deepseek" — DeepSeek через интернет (DEEPSEEK_MODEL ниже). Платно, сообщения зрителей
#              отправляются в зарубежную компанию.
# Перед тем как давать зрителям модель «через интернет», согласуйте это с юристом филармонии.
CHAT_PROVIDER = "gigachat"   # если ГигаЧат недоступен, окно само откроется с локальной моделью

CHAT_MODEL = "gemma3:4b"        # локальная модель (для CHAT_PROVIDER = "ollama"); прежняя — "qwen3.5:4b"

# Настройки ГигаЧата (для CHAT_PROVIDER = "gigachat"), по документации developers.sber.ru
GIGACHAT_MODEL = "GigaChat-2"   # лёгкая и быстрая; мощнее — "GigaChat-2-Pro", "GigaChat-2-Max"
GIGACHAT_SCOPE = "GIGACHAT_API_PERS"   # для физлиц; для организаций — "GIGACHAT_API_B2B" или "_CORP"
GIGACHAT_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_API_URL = "https://gigachat.devices.sberbank.ru/api/v1"
# Ключ авторизации ГигаЧата — секрет, как пароль. Хранится в отдельном файле одной строкой.
GIGACHAT_KEY_FILE = PROGRAM_FOLDER / "keys" / "gigachat_key.txt"
# Сайты Сбера подписаны российским сертификатом Минцифры — без него соединение не установится
GIGACHAT_CERT_FILE = PROGRAM_FOLDER / "keys" / "russian_trusted_root_ca.cer"

# Настройки DeepSeek (для CHAT_PROVIDER = "deepseek"), по документации api-docs.deepseek.com
DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-flash"   # быстрая и дешёвая; мощнее — "deepseek-v4-pro"
DEEPSEEK_THINKING = False           # режим «размышлений»: точнее, но медленнее и дороже
# Ключ DeepSeek — секрет, как пароль. Хранится в отдельном файле одной строкой.
DEEPSEEK_KEY_FILE = PROGRAM_FOLDER / "keys" / "deepseek_key.txt"

# Сколько кусочков отдавать модели после поиска
TOP_K = 8

# «Творчество» модели: 0 — строго и одинаково, 1 — свободнее.
# Чуть выше нуля, чтобы речь была живой, но факты не «плыли».
TEMPERATURE = 0.3

# Сколько текста модель «держит в голове» за раз (в токенах).
CONTEXT_SIZE = 8192

# Сколько последних обменов репликами помнит помощник (вопрос + ответ = один обмен)
HISTORY_TURNS = 3

# Показывать ли модели её собственные прошлые ответы. Проверка показала: маленькая
# модель склонна переписывать из них неподходящие варианты (например, детские спектакли
# после слов «у меня нет детей»). Поэтому по умолчанию модель видит только реплики зрителя.
HISTORY_WITH_REPLIES = False

# Сколько событий максимум показывать модели при вопросе о периоде
MAX_EVENTS_IN_PERIOD = 40

# Телефон кассы — на случай, если ответа в базе нет
CASHIER_PHONE = "+7 (3842) 58-32-11"

# Инструкция для модели (системный промпт) — в папке «rules», файл «system_prompt.txt».

USER_TEMPLATE = """Справочные сведения:
{% for doc in documents %}
---
{{ doc.content }}
{% endfor %}
{% if people %}
---
О ЛЮДЯХ И КОЛЛЕКТИВАХ ИЗ РАЗГОВОРА (дирижёры, артисты, коллективы и их концерты; у концертов людей указано, почему концерт подходит):
{{ people }}
{% endif %}
{% if afisha %}
---
ПОЛНАЯ АФИША НА ДАТЫ ИЗ РАЗГОВОРА (все события этих дней; отвечая про даты, опирайся на этот список):
{{ afisha }}
{% endif %}
{% if about %}
ЧТО ИЗВЕСТНО О ЗРИТЕЛЕ ИЗ РАЗГОВОРА: {{ about }}
{% endif %}

Сообщение зрителя: {{ question }}"""

# Подсказки модели о зрителе — их программа сама определяет по словам в разговоре
ABOUT_AUDIENCE = {
    "взрослые": "идёт без детей — не предлагай детские сказки и спектакли для малышей.",
    "дети": "идёт с ребёнком — предлагай события, подходящие детям.",
}

# ============================================================================
#  ДАЛЬШЕ — САМА ПРОГРАММА
# ============================================================================

import os
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")  # не отправлять статистику

import difflib
import re
import sys
from datetime import date, timedelta
from typing import Optional

import pravila

try:
    from haystack import Document, Pipeline, component
    from haystack.components.builders import ChatPromptBuilder
    from haystack.components.joiners import DocumentJoiner
    from haystack.components.retrievers.in_memory import (
        InMemoryBM25Retriever, InMemoryEmbeddingRetriever)
    from haystack.dataclasses import ChatMessage
    from haystack.document_stores.in_memory import InMemoryDocumentStore
    from haystack_integrations.components.embedders.ollama import OllamaTextEmbedder
    from haystack_integrations.components.generators.ollama import OllamaChatGenerator
except ImportError:
    print("Не найдены библиотеки Haystack. Запускайте через окружение проекта (run_assistant.bat).")
    sys.exit(1)


WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
MONTH_NAMES = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
               "августа", "сентября", "октября", "ноября", "декабря"]
MONTH_PATTERNS = [r"январ", r"феврал", r"март", r"апрел", r"\bма[йяе]\b", r"июн", r"июл",
                  r"август", r"сентябр", r"октябр", r"ноябр", r"декабр"]
WEEKDAY_PATTERNS = [r"понедельник", r"вторник", r"\bсред[уае]\b", r"четверг", r"пятниц",
                    r"суббот", r"воскресень"]


# ----------------------------------------------------------------------------
#  Даты в разговоре: «сегодня», «на выходных», «в декабре», «12 ноября», «Новый год»…
# ----------------------------------------------------------------------------

def month_range(year, month):
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return start, end


def new_year_period(today):
    """Новогодние праздники: с 15 декабря по 14 января (ближайшие)."""
    if today.month == 1 and today.day <= 14:
        return today, date(today.year, 1, 14)
    start = date(today.year, 12, 15)
    return max(start, today), date(today.year + 1, 1, 14)


def find_period(text, today):
    """Ищет в тексте дату или период. Возвращает (начало, конец) или None."""
    q = text.lower().replace("ё", "е")

    # «12 ноября», «12 ноября 2026»
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTH_NAMES) + r")(?:\s+(\d{4}))?", q)
    if m:
        month = MONTH_NAMES.index(m.group(2)) + 1
        year = int(m.group(3)) if m.group(3) else today.year + (month < today.month)
        try:
            day = date(year, month, int(m.group(1)))
            return day, day
        except ValueError:
            pass

    # «12.11» или «12.11.2026»
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", q)
    if m:
        month = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year + (month < today.month)
        if year < 100:
            year += 2000
        try:
            day = date(year, month, int(m.group(1)))
            return day, day
        except ValueError:
            pass

    if re.search(r"новогодн|новый год|новым годом|нового года|рождеств", q):
        return new_year_period(today)

    if "послезавтра" in q:
        return today + timedelta(2), today + timedelta(2)
    if "завтра" in q:
        return today + timedelta(1), today + timedelta(1)
    if "сегодня" in q:
        return today, today

    sunday = today + timedelta(6 - today.weekday())
    if "выходн" in q:
        saturday = sunday - timedelta(1)
        return max(saturday, today), sunday
    if "следующей неделе" in q or "следующую неделю" in q:
        return sunday + timedelta(1), sunday + timedelta(7)
    if "этой неделе" in q or "на неделе" in q:
        return today, sunday

    for number, pattern in enumerate(WEEKDAY_PATTERNS):
        if re.search(pattern, q):
            ahead = (number - today.weekday()) % 7
            day = today + timedelta(ahead)
            return day, day

    for number, pattern in enumerate(MONTH_PATTERNS, 1):
        if re.search(pattern, q):
            year = today.year + (number < today.month)
            start, end = month_range(year, number)
            return max(start, today), end

    return None


# ----------------------------------------------------------------------------
#  С детьми или без: «нет детей» — это НЕ просьба о детских спектаклях
# ----------------------------------------------------------------------------

WITHOUT_CHILDREN = re.compile(
    r"\b(нет|без|не будет|не с)\s+(\w+\s+)?(дет|ребен|малыш)"        # «нет детей», «без ребёнка»
    r"|\b(дет|ребен)\w*\s+(\w+\s+){0,2}(нет|не будет)\b"             # «детей у меня нет»
    r"|\bвзросл|\bдля себя|\bвдвоем|\bс мужем|\bс женой|\bс подругой|\bс другом"
    r"|\bс коллегами|\bромантич")
WITH_CHILDREN = re.compile(r"\b(дет|ребен|малыш|школьник|сын|доч|внук|внуч)")


def find_audience(text):
    """'дети', 'взрослые' или '' — по тому, что зритель сказал о себе."""
    q = text.lower().replace("ё", "е")
    if WITHOUT_CHILDREN.search(q):
        return "взрослые"
    if WITH_CHILDREN.search(q):
        return "дети"
    return ""


# Возраст цифрами: «ребёнку 5 лет», «сыну 8», «дочке 3 годика», «5-летний», «мне 15 лет»
AGE_PATTERNS = [
    re.compile(r"\b(\d{1,2})\s*-?\s*(?:лет|год|года|годик\w*|летн\w*|годовал\w*)\b"),
    re.compile(r"\b(?:ребенк\w*|ребен\w*|сын\w*|доч\w*|внук\w*|внучк\w*|малыш\w*)\s+(\d{1,2})\b"),
    # перечисление: «2 и 7 лет», «3, 5 и 9 лет» — берём и первые числа
    re.compile(r"\b(\d{1,2})(?=(?:\s*(?:,|и)\s*\d{1,2})+\s*-?\s*(?:лет|год|года|годик))"),
]


def find_age(text):
    """Возраст самого младшего, кто идёт на концерт (если назван цифрами), иначе None."""
    q = text.lower().replace("ё", "е")
    ages = [int(m) for pattern in AGE_PATTERNS for m in pattern.findall(q)]
    ages = [a for a in ages if a <= 99]
    return min(ages) if ages else None


def age_rating(doc):
    """«12+» → 12; если возраст не указан — 0."""
    m = re.search(r"(\d+)\s*\+", doc.meta.get("age", ""))
    return int(m.group(1)) if m else 0


def fits_audience(doc, audience, age=None):
    """
    Подходит ли событие по возрасту. Если возраст назван цифрами — строго по маркировке:
    ребёнку 5 лет подходят только 0+, ребёнку 12 — 0+, 6+ и 12+.
    """
    if age is not None:
        return age_rating(doc) <= age
    rating = doc.meta.get("age", "")
    if audience == "взрослые":
        return rating != "0+"
    if audience == "дети":
        return rating in ("0+", "6+")
    return True


# ----------------------------------------------------------------------------
#  Служебные вопросы, на которые отвечаем готовым текстом из «rules/ready_replies.txt»
#  (модель здесь путается: направляет в кассу или путает услугу съёмки с правилами для зрителей)
# ----------------------------------------------------------------------------

# Хочет выступить у нас, провести свой концерт, гастроли, арендовать зал
PERFORM_PATTERN = re.compile(
    r"\bвыступ(?:ить|ать|ление)\s+(?:у вас|в (?:вашей |нашей )?филармони|на (?:вашей )?сцене)"
    r"|\b(?:хочу|хотим|хотел\w*|можно|как)\b[^.?!]{0,30}\bвыступить\b"
    r"|\bаренд\w*|\bгастрол\w*\s+(?:у вас|в филармони)|\bсотрудничеств\w*"
    r"|\bпровести\s+(?:свой|наш|сольный|собственный)\s+концерт"
    r"|\bпопасть\s+(?:к вам\s+|в филармонию\s+)?на\s+(?:вашу\s+|большую\s+)?сцену"
    r"|\bу вас\s+дать\s+(?:\w+\s+)?концерт|\bдать\s+(?:\w+\s+)?концерт\w*\s+(?:у вас|в (?:вашей )?филармони)"
    r"|\bснять\s+(?:ваш\w*\s+|у вас\s+)?(?:большой |органный |камерный )?зал")   # «снять зал» — аренда
# Хочет заказать съёмку СВОЕГО выступления (а не спрашивает, можно ли зрителю снимать концерт)
SHOOT_WORDS = re.compile(
    r"\b(?:сним\w*|снять|сфотограф\w*|\w*съемк\w*)"
    r"|\b(?:видео|аудио)?запис\w*\s+(?:мо\w*|наш\w*|меня|нас)\s+(?:выступлен|концерт|хор|оркестр|ансамбл|групп|спектакл)")
SHOOT_MINE = re.compile(r"\b(?:мо[её]|мой|мою|моего|моей|наш\w*|нас|меня|заказ\w*)\b")


# Признаки того, что новое сообщение продолжает разговор о концертах, а не меняет тему
FOLLOWUP_START = re.compile(r"^\s*(?:а|и|тогда|ещ[её]|ну|а если|а что|а как|а есть|лучше)\b", re.I)
CONCERT_WORDS = re.compile(
    r"концерт|спектакл|сходить|пойти|посовет|посмотр|послуша|афиш|билет|\bдет|ребен|сказк|"
    r"программ|выходн|вечер|утр|суббот|воскресен|недел|январ|феврал|март|апрел|ма[йя]|июн|июл|"
    r"август|сентябр|октябр|ноябр|декабр|муж|жен|подруг|друг|взросл|лет\b|"
    # ответы на уточняющие вопросы: какая музыка, какое настроение, когда удобно
    r"музык|классик|симфон|орган|камерн|джаз|народн|фольклор|эстрад|песн|романс|опер|балет|хор|"
    r"фортепиан|скрипк|рок|торжествен|весел|легк|тих|днем|будн|компани|один|одна|вдвоем", re.I)


# Бытовые темы — всегда отдельный вопрос, даже если он короткий («а где туалет?»)
PRACTICAL_WORDS = re.compile(
    r"туалет|уборн|санузел|буфет|гардероб|парковк|\bеда|\bеду\b|поесть|напитк|"
    r"плохо|тошн|рвет|рвота|болит|врач|аптечк|скор(?:ую|ая)|жалоб|отрав|самочувств", re.I)


def is_followup(text):
    """Продолжение разговора о концертах («а без детей?», «в субботу») или новая тема."""
    if PRACTICAL_WORDS.search(text.lower().replace("ё", "е")):
        return False
    words = re.findall(r"\w+", text)
    if FOLLOWUP_START.search(text) or len(words) <= 4:
        return True
    return bool(CONCERT_WORDS.search(text.lower().replace("ё", "е")))


# Отзывы: зритель делится впечатлениями (радостью или недовольством)
REVIEWS_LINK = "https://www.kemfil.ru/reviews"
EVENT_WORDS = r"(?:концерт|вечер|спектакл|музык|программ|сказк|оркестр|хор|выступлен|праздник|исполнени)"
PRAISE_PATTERN = re.compile(
    r"понравил(?:ся|ась|ось|ись)|в восторге|восторг|браво|"
    r"(?:спасибо|благодар\w*) (?:вам )?за (?:\w+ )?" + EVENT_WORDS + "|"
    r"(?:прекрасн|отличн|чудесн|замечательн|великолепн|потрясающ)\w* " + EVENT_WORDS + "|"
    r"хочу (?:рассказать|поделиться)|оставить отзыв|написать отзыв", re.I)
COMPLAINT_PATTERN = re.compile(
    r"не понравил|отвратит|разочаров|жалоб|пожаловат|претензи|безобраз|хамств|нахамил|"
    r"(?:ужасн|отвратительн|кошмарн|худш)\w* (?:\w+ )?(?:" + EVENT_WORDS[3:-1] + r"|обслуж|буфет|звук|организац|зал|сервис|кассир)|"
    r"было ужасно|грубо (?:обслуж|ответ)|плохо обслуж|позор", re.I)
QUESTION_PATTERN = re.compile(
    r"\?|\b(?:когда|где|сколько|как|можно|подскаж|посовет|есть ли|будет|какой|какая|какие|что)\b", re.I)


def feedback_kind(text):
    """«понравилось», «недоволен» или "" — делится ли зритель впечатлениями."""
    q = text.lower().replace("ё", "е")
    if COMPLAINT_PATTERN.search(q):
        return "недоволен"
    if PRAISE_PATTERN.search(q):
        return "понравилось"
    return ""


def service_topic(text):
    """«заказать съёмку», «выступить у нас», «где туалет» или "" — по словам в сообщении."""
    q = text.lower().replace("ё", "е")
    if re.search(r"туалет|уборн|санузел|\bwc\b", q):
        return "где туалет"
    if SVO_PATTERN.search(q):
        # ГигаЧат на эту тему не отвечает (фильтр «чувствительных тем») — даём точный готовый текст
        return "участникам сво"
    if re.search(r"\bснять\s+(?:ваш\w*\s+|у вас\s+)?(?:большой |органный |камерный )?зал", q):
        return "выступить у нас"
    if SHOOT_WORDS.search(q) and SHOOT_MINE.search(q):
        return "заказать съёмку"
    if PERFORM_PATTERN.search(q):
        return "выступить у нас"
    return ""


# ----------------------------------------------------------------------------
#  Только концерты филармонии: выездные (другие города) — только если зритель сам
#  назвал свой город; концерты в школах — никогда (их проводят для учеников школы)
# ----------------------------------------------------------------------------

HOME_HALLS = ("Большой зал", "Органный зал", "Камерный зал", "Центральное фойе", "Малый зал")
SCHOOL_PATTERN = re.compile(r"\bСОШ\b|\bшкола\s*№|гимнази|лице[йя]", re.I)
# Слова в названии площадки, которые не являются названием города
PLACE_STOP_WORDS = ("дворец", "центр", "культур", "дом", "развит", "городск", "округ", "шахтер",
                    "алюминщ", "инск", "пгт", "кузнецк")


def place_of(hall):
    """«филармония», «школа» или «выезд» (другой город, дом культуры, музыкальная школа)."""
    if hall.strip() in HOME_HALLS:
        return "филармония"
    if SCHOOL_PATTERN.search(hall):
        return "школа"
    return "выезд"


def place_stems(hall):
    """Начала слов-названий в адресе площадки: «ДМШ №18 г.Юрга» → ["юрг"]."""
    stems = []
    for word in re.findall(r"[А-ЯЁ][а-яё]{3,}", hall):
        w = word.lower().replace("ё", "е")
        if w.startswith(PLACE_STOP_WORDS):
            continue
        stems.append(w[: len(w) - 1] if len(w) <= 5 else w[: max(5, len(w) - 3)])
    return stems


def visiting_halls(text, concerts):
    """Выездные площадки в городах, которые зритель сам назвал («я из Юрги»)."""
    words = re.findall(r"[а-яё]+", text.lower().replace("ё", "е"))
    halls = set()
    for doc in concerts:
        hall = doc.meta.get("hall", "")
        if place_of(hall) == "выезд" and any(
                w.startswith(stem) for stem in place_stems(hall) for w in words):
            halls.add(hall)
    return halls


def is_ours(doc, halls=()):
    """Концерт в залах филармонии или на выездной площадке в городе зрителя."""
    hall = doc.meta.get("hall", "")
    return place_of(hall) == "филармония" or hall in halls


# ----------------------------------------------------------------------------
#  Поиск по названию с учётом окончаний («Брамса» → «Брамс»)
# ----------------------------------------------------------------------------

# Начала слов, которые есть почти в каждом вопросе и не помогают найти событие
STOP_STEMS = (
    "концер", "спектак", "билет", "будет", "будут", "когда", "скольк", "можно", "какие",
    "какой", "какая", "какое", "филармон", "купит", "пушкинск", "карт", "начина", "сегодн",
    "завтр", "выходн", "недел", "есть", "стоит", "стоят", "хочу", "хотел", "подскаж",
    "пожалуйст", "здравств", "добрый", "через", "сейчас", "который", "детск", "ребен",
    "январ", "феврал", "март", "апрел", "июн", "июл", "август", "сентябр", "октябр",
    "ноябр", "декабр", "вечер", "утро", "днем", "сколько", "зале", "зала", "место", "мест",
    "програм", "сходит", "пойти", "посовет", "посмотр", "детей", "нет", "меня", "мужем",
    "женой", "подруг", "взросл", "интерес", "что-нибудь",
)


@component
class TitleSearch:
    """Ищет события, в названии которых встречаются слова из сообщения (без учёта окончаний)."""

    def __init__(self, store, top_k=8):
        self.concerts = store.filter_documents(
            filters={"field": "meta.type", "operator": "==", "value": "концерт"})
        self.top_k = top_k

    @component.output_types(documents=list[Document])
    def run(self, query: str):
        words = re.findall(r"[а-яa-z0-9]+", query.lower().replace("ё", "е"))
        stems = [w[: max(4, len(w) - 2)] for w in words
                 if len(w) >= 4 and not w.startswith(STOP_STEMS)]
        hits = []
        for doc in self.concerts:
            title = doc.meta.get("title", "").lower().replace("ё", "е")
            score = sum(1 for s in stems if s in title)
            if score:
                hits.append((score, doc))
        hits.sort(key=lambda x: (-x[0], x[1].meta.get("date", "")))
        return {"documents": [doc for _, doc in hits[: self.top_k]]}


SENSITIVE_PAGES = ("Участникам СВО",)
SVO_PATTERN = re.compile(r"(?<![а-я])сво(?![а-я])|специальн\w* военн\w* операц|ветеран\w* боев|мобилизован",
                         re.I)


@component
class Focus:
    """
    Наводит фокус на то, что важно зрителю:
    - если в разговоре есть даты — убирает карточки концертов с других дат,
      а для коротких периодов (до 3 дней) добавляет карточки всех событий этих дней;
    - если зритель идёт с детьми или без — убирает неподходящие по возрасту события.
    """

    def __init__(self, store, short_period_days=3, max_cards=6):
        self.concerts = store.filter_documents(
            filters={"field": "meta.type", "operator": "==", "value": "концерт"})
        self.short_period_days = short_period_days
        self.max_cards = max_cards

    @component.output_types(documents=list[Document])
    def run(self, documents: list[Document], start: str = "", end: str = "", audience: str = "",
            people_mode: bool = False, age: int = -1, halls: Optional[list[str]] = None,
            skip_pages: Optional[list[str]] = None):
        is_concert = lambda d: d.meta.get("type") == "концерт"
        # Страницы, которые в этом вопросе только мешают (например, «Проекты» — там названия
        # спектаклей прошлых лет без дат: модель выдавала их за ближайшую афишу)
        documents = [d for d in documents if d.meta.get("page") not in (skip_pages or [])]
        # Прошедшие концерты (база могла не обновиться) — не советуем
        today = date.today().isoformat()
        documents = [d for d in documents if not is_concert(d) or d.meta.get("date", "") >= today]
        age = None if age < 0 else age
        halls = halls or []
        suits = lambda d: is_ours(d, halls) and fits_audience(d, audience, age)
        if people_mode:
            # Зритель назвал конкретных людей: всё нужное о них — в справке «О людях».
            # Случайные концерты и карточки однофамильцев из общего поиска только путают модель.
            documents = [d for d in documents if d.meta.get("type") == "info"]
        # Страница «Участникам СВО» включает фильтр «чувствительных тем» ГигаЧата: с ней в запросе
        # он отказывается отвечать на любой вопрос. На вопросы о СВО отвечает готовый текст,
        # поэтому в остальных ответах эта страница не нужна.
        documents = [d for d in documents if d.meta.get("page") not in SENSITIVE_PAGES]
        kept = [d for d in documents if not is_concert(d) or suits(d)]
        if start:
            in_period = lambda d: start <= d.meta.get("date", "") <= end
            kept = [d for d in kept if not is_concert(d) or in_period(d)]
            days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
            if days <= self.short_period_days:
                cards = sorted((d for d in self.concerts if in_period(d) and suits(d) and not cancelled(d)),
                               key=lambda d: (d.meta["date"], d.meta.get("when", "")))
                if len(cards) <= self.max_cards:
                    ids = {d.id for d in kept}
                    kept += [d for d in cards if d.id not in ids]
            # У спектакля с многими сеансами оставляем одну карточку —
            # все даты модель видит в полной афише на период.
            seen, unique = set(), []
            for d in kept:
                title = d.meta.get("title") if is_concert(d) else None
                if title and title in seen:
                    continue
                seen.add(title)
                unique.append(d)
            kept = unique
        return {"documents": kept}


def short_status(status):
    """Короткая пометка для списка событий: «ОТМЕНА», «БИЛЕТОВ НЕТ» и т.п."""
    if not status or status == "по расписанию":
        return ""
    if "ПРОДАНЫ" in status.upper():
        return "на эту дату БИЛЕТОВ НЕТ"
    if status.startswith("ОТМЕНА"):
        return "ОТМЕНА — в этот день не состоится"
    if status.startswith("ПЕРЕНОС"):
        return "ПЕРЕНЕСЁН — в этот день не состоится. " + status[len("ПЕРЕНОС"):].strip(" .")[:90]
    return status[:90]


URL_PATTERN = re.compile(r"https?://[^\s<>«»\"')\]]+")
AFISHA_LINK = "https://www.kemfil.ru/afisha"
CJK_PATTERN = re.compile("[　-〿㐀-鿿＀-￯]+")  # иероглифы


# Приветствие в начале ответа: «Добрый день!», «Здравствуйте,» и т. п.
GREETING_PATTERN = re.compile(
    r"^\s*(добр(?:ый|ое|ого)\s+(?:день|вечер|утро|дня|вечера|утра)|здравствуйте|приветствую|привет"
    r"|уважаем(?:ый|ая)\s+зрител(?:ь|ьница)|дорог(?:ой|ая|ие)\s+(?:друг|друзья|зрител\w*|гост\w*))"
    r"\s*[!.,]*\s*", re.I)
# Пересказ просьбы вопросом в начале ответа: «Вы интересуетесь концертами…?»
# (и варианты «Вы, я вижу, интересуетесь…», «Вы интересуетесь…, и уточняете…»)
ECHO_PATTERN = re.compile(
    r"^\s*Вы(?:,\s*я\s+(?:вижу|понимаю|так понимаю),)?\s+"
    r"(?:интересуетесь|хотите|ищете|любите|планируете|уточняете|спрашиваете)[^.?!\n]*[.?!]\s*", re.I)
# Вежливое обращение «Вы» и его формы — пишем с заглавной буквы
POLITE_PATTERN = re.compile(
    r"\b(вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашего|вашей|вашему|вашим|вашими|ваших|вашу|вашем)\b")


def polish_reply(reply, question):
    """
    Страховка к правилам из инструкции (маленькие модели их иногда забывают):
    — убираем «Добрый день!» в начале ответа, если зритель сам не поздоровался;
    — убираем вводный вопрос «Вы интересуетесь…?», если после него есть ответ;
    — пишем «Вы», «Вас», «Ваш» с заглавной буквы.
    """
    if not GREETING_PATTERN.search(question):
        without = GREETING_PATTERN.sub("", reply, count=1)
        if without and without != reply:
            reply = without[0].upper() + without[1:]
    without = ECHO_PATTERN.sub("", reply, count=1)
    if without.strip():  # убираем, только если после вопроса есть сам ответ
        reply = without[0].upper() + without[1:]
    # Дежурный «продавецкий» вопрос в конце: «Какой вариант Вам ближе?», «Какое из предложений…?»
    without = SALES_QUESTION.sub("", reply).rstrip()
    if without.strip():
        reply = re.sub(r"\n{3,}", "\n\n", without)
    # «Продавецкая» первая строка-вступление: «Предлагаем Вам рассмотреть следующие концерты:»
    first, _, rest = reply.partition("\n")
    if rest.strip() and first.rstrip().endswith(":") and SALES_OPENING.search(first):
        reply = rest.lstrip("\n")
    # Заглушки в квадратных скобках, которые модель подсмотрела в образце («[даты]»)
    # («[ссылка]» и «[билет]» не трогаем — на их место потом встанет настоящая ссылка)
    reply = re.sub(r"[ \t]*:?[ \t]*\[(?!\s*(?:ссылк|билет|купить))[а-яё ]{2,25}\][ \t]*(?:—[ \t]*)?", " — ",
                   reply, flags=re.I)
    reply = re.sub(r"(?: — )+(?=\S)", " — ", reply)
    reply = re.sub(r"[ \t]*—[ \t]*$", "", reply, flags=re.M)
    reply = re.sub(r"[ \t]+([,.:])", r"\1", reply)
    # Строки справки, переписанные как есть: «- 11.11.2026, среда, 12:00 | Спектакль … | Камерный зал»
    reply = re.sub(r"[ \t]*\|[ \t]*", ", ", reply)
    reply = re.sub(r",\s*билет:\s*", ": ", reply)
    # Заголовки разделов инструкции, которые модель иногда повторяет зрителю
    reply = re.sub(r"[ \t]*(?:контактные данные|контакты) указаны ниже\.?", "", reply, flags=re.I)
    reply = re.sub(r"(?im)^\s*куда направ\w*[^:\n]*:\s*(\S)", lambda m: m.group(1).upper(), reply)
    # «Обычно такие концерты проходят весной», «в декабре традиционно звучит…» — почти всегда
    # выдумка: в базе есть только текущая афиша. Такие предложения убираем целиком.
    without = re.sub(r"(?:(?<=^)|(?<=[.!?…\n]))[ \t]*[^.!?…\n]*\b(?:традиционно|как правило|обычно проход\w*"
                     r"|часто проход\w*|ежегодно)\b[^.!?…\n]*[.!?…]?", "", reply, flags=re.I | re.M)
    if without.strip():
        reply = without
    # «отмечает 80-летие» — юбилей был в 2023 году, модель берёт его из заголовка страницы
    reply = re.sub(r"\s*(?:отмечает|празднует|встречает)\s+\d+-?летие(?:\s+(?:своей|творческой)\s+\w+)?", "", reply)
    # Состав исполнителей сайт не публикует — не обещаем «с его участием»
    reply = re.sub(r"\s+с (?:его|её|ее) участием", "", reply)
    reply = re.sub(r"\n{3,}", "\n\n", reply).strip()
    return POLITE_PATTERN.sub(lambda m: m.group(1).capitalize(), reply)


# Убираем только вопросы «о вариантах» — уточняющие вопросы о зрителе
# («Какая музыка Вам по душе?», «Сколько лет ребёнку?») остаются
SALES_QUESTION = re.compile(
    r"[ \t]*\b(?:какой|какое|какая|какие)\b[^.!?\n]*"
    r"(?:вариант|предложени|из (?:этих|них|вечеров|концертов)|мероприяти|выбер)[^.!?\n]*\?"
    r"|[ \t]*\b(?:какой|какое|какая|какие)\s+(?:концерт|спектакл|событи|вечер)\w*[^.!?\n]*"
    r"(?:заинтерес|понрав|ближе|выбер|подход)[^.!?\n]*\?", re.I)
SALES_OPENING = re.compile(r"вариант|предлага|предложени|рассмотр|следующ|позвольте|замечательн", re.I)


# «→ купить билет →», «билеты здесь:» в конце строки — место, где модель «потеряла» ссылку
TICKET_PLACEHOLDER = re.compile(
    r"[\s—–-]*(?:→\s*)?(?:купить билеты?|билеты?)(?:\s+можно)?(?:\s+(?:здесь|тут|по ссылке))?\s*[:→.]*\s*$", re.I)
# Строка похожа на предложение концерта, если в ней есть время или цена
OFFER_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\b|₽|\bруб")
MONTH_NUMBERS = {name: number for number, name in enumerate(MONTH_NAMES, 1)}


def plain(text):
    """Для сравнения названий: строчные буквы, ё → е, латинская Z → З («Zавет» = «Завет»), «№ 3» = «№3»."""
    text = text.lower().replace("ё", "е").replace("z", "з")
    return re.sub(r"\s+", " ", re.sub(r"№\s+", "№", text))


# Слова, которые есть во многих названиях и не помогают отличить один концерт от другого
GENERIC_TITLE_WORDS = (
    "концерт", "спектакл", "сказк", "музыкальн", "оркестр", "симфони", "программ", "вечер",
    "новогодн", "губернатор", "филармони", "экскурси", "закулись", "театр", "литературн",
    "премьер", "солист", "ансамбл", "фестивал", "семейн", "сольн", "героическ", "баллад",
    "орган",  # «в Органном зале» — это зал, а не название концерта
)


def title_stems(title):
    """Отличительные слова названия: «И. Брамс. Симфония №3» → ["брамс"]."""
    stems = []
    for word in re.findall(r"[а-яa-з]{5,}", plain(title)):
        if not word.startswith(GENERIC_TITLE_WORDS):
            stems.append(word[: max(5, len(word) - 2)])
    return stems


# «по этой ссылке: …», «купить можно здесь:» — модель сослалась на ссылку, но не дала её
LINK_WORDS_END = re.compile(r"(?:ссылк\w*|здесь|тут|на сайте)\s*:?\s*$", re.I)
ELLIPSIS_END = re.compile(r"\s*(?:\.{3}|…)\s*$")


def find_concert(text, concerts, need_fit=False):
    """
    Концерт, о котором строка: по названию (целиком или отличительным словам), а при
    сомнениях — по дате, времени и залу, которые в ней названы.
    need_fit=True — годится только концерт, у которого совпало название целиком
    или хотя бы дата, время или зал (чтобы не заменить верную ссылку неверной).
    """
    text = plain(text)
    times = set(re.findall(r"\b\d{1,2}:\d{2}\b", text))
    # Какие даты названы: «14 ноября», «14.11»
    dates = {(int(d), MONTH_NUMBERS[m]) for d, m in
             re.findall(r"\b(\d{1,2})\s+(" + "|".join(MONTH_NAMES) + r")", text)}
    dates |= {(int(d), int(m)) for d, m in re.findall(r"\b(\d{1,2})\.(\d{1,2})\b", text)}
    best = None
    words = re.findall(r"[а-яa-з]+", text)
    for doc in concerts:
        title = doc.meta.get("title", "")
        quoted = re.findall(r"«([^«»]{3,})»", title)
        keys = [plain(k) for k in quoted + [title] if len(k) >= 4]
        exact = max((len(k) for k in keys if k in text), default=0)
        # если названия целиком нет — узнаём по отличительным словам («симфония Брамса»)
        stems = title_stems(title)
        hits = sum(1 for s in stems if any(w.startswith(s) for w in words))
        if not exact and not hits:
            continue
        day = date.fromisoformat(doc.meta["date"])
        when = doc.meta.get("when", "")
        hall = plain(doc.meta.get("hall", ""))
        fit = (((day.day, day.month) in dates)
               + any(t in when for t in times)
               + (len(hall) >= 5 and hall[:-2] in text))
        if need_fit and not exact and not fit:
            continue
        # сначала точное название, потом совпадение даты/времени/зала, потом больше общих слов
        score = (exact > 0, fit, hits, exact, -day.toordinal())
        if best is None or score > best[0]:
            best = (score, doc)
    return best[1] if best else None


def concert_by_when(text, concerts):
    """
    Концерт по дате и времени, если названия в строке нет: «26 ноября в 18:30 — билеты: …».
    Возвращает концерт, только если в этот день и час он один.
    """
    text = plain(text)
    times = set(re.findall(r"\b\d{1,2}:\d{2}\b", text))
    dates = {(int(d), MONTH_NUMBERS[m]) for d, m in
             re.findall(r"\b(\d{1,2})\s+(" + "|".join(MONTH_NAMES) + r")", text)}
    dates |= {(int(d), int(m)) for d, m in re.findall(r"\b(\d{1,2})\.(\d{1,2})\b", text)}
    if not times or not dates:
        return None
    found = []
    for doc in concerts:
        day = date.fromisoformat(doc.meta["date"])
        if (day.day, day.month) in dates and any(t in doc.meta.get("when", "") for t in times):
            found.append(doc)
    return found[0] if len({d.meta.get("title") for d in found}) == 1 else None


def drop_unknown_events(reply, concerts):
    """
    Убирает абзацы, где предложено событие («Снегурочка», 11:00, 500 ₽), которого нет в базе:
    модель иногда берёт названия из страниц «Проекты» или «Абонементы» и придумывает даты.
    Абзац убираем, только если в нём есть название в кавычках, время или цена, а ни название,
    ни дата со временем не совпали ни с одним концертом.
    """
    paragraphs = reply.split("\n")
    norm = lambda s: " ".join(re.sub(r"[«»„“”\"'.,!?:;()—–\-]", " ", plain(s)).split())
    titles = [norm(d.meta.get("title", "")) for d in concerts]
    collectives = norm(" ".join(load_collectives()))

    def known(quote):
        q = norm(quote)
        # название концерта, его часть («Неофолк») или название коллектива («Отражение»)
        return len(q) < 4 or any(q in t or (len(t) > 6 and t in q) for t in titles) or q in collectives

    kept, dropped = [], False
    for p in paragraphs:
        quotes = re.findall(r"«([^«»]{3,})»", p)
        if quotes and OFFER_PATTERN.search(p) and not any(known(q) for q in quotes):
            dropped = True
            continue
        # Без кавычек: «Концерт Бориса Штоколова… 17 декабря, 19:00 — билеты: …» — если ни одно
        # отличительное слово ни одного названия из базы не встретилось, концерт выдуман
        if not quotes and "intickets" in p and OFFER_PATTERN.search(p):
            doc = find_concert(p, concerts)
            said = {(int(d), MONTH_NUMBERS[m]) for d, m in
                    re.findall(r"\b(\d{1,2})\s+(" + "|".join(MONTH_NAMES) + r")", plain(p))}
            day = date.fromisoformat(doc.meta["date"]) if doc else None
            if doc is None or (said and (day.day, day.month) not in said):
                dropped = True
                continue
        kept.append(p)
    if not dropped:
        return reply
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    if not (OFFER_PATTERN.search(result) or "http" in result):
        # предложено было только несуществующее событие — честно отправляем в афишу
        result = (result + "\n\n" if result else "") + \
            f"Подходящие события и даты лучше посмотреть в афише: {AFISHA_LINK}"
    return result


def fix_genitive_names(reply, people):
    """
    «под руководством Дмитрия Гани» → «— руководитель Дмитрий Ганин»: модель склоняет имена
    с ошибками, поэтому возвращаем имя в начальной форме, как оно записано на сайте.
    """
    def repl(m):
        first, last = m.group(2).lower(), m.group(3).lower()
        for p in people:
            parts = p["name"].split()
            if len(parts) >= 2 and first.startswith(name_stem(parts[0])[:4]) and \
                    last.startswith(name_stem(parts[-1])[:4]):
                role = "руководитель" if m.group(1) == "руководством" else "дирижёр"
                return f" — {role} {parts[0]} {parts[-1]}"
        return m.group(0)
    return re.sub(r"\s+под (?:художественным\s+)?(руководством|управлением) ([А-ЯЁ][а-яё]+) ([А-ЯЁ][а-яё]+)",
                  repl, reply)


def drop_unsuitable(reply, concerts, audience, age):
    """Убирает из ответа абзацы о событиях, которые не подходят зрителю по возрасту."""
    paragraphs = re.split(r"\n\s*\n|\n(?=\s*(?:\d+\.|[—–-])\s)", reply)
    kept = []
    for p in paragraphs:
        doc = find_concert(p, concerts, need_fit=True)
        if doc is not None and OFFER_PATTERN.search(p) and not fits_audience(doc, audience, age):
            continue
        kept.append(p)
    result = "\n\n".join(x.strip("\n") for x in kept)
    return result if result.strip() else reply


# «Хочу сходить на концерт», «посоветуйте что-нибудь» — общая просьба без дат
GENERAL_WISH = re.compile(r"хочу (?:сходить|пойти|на концерт|в филармонию)|посоветуй|куда сходить|что посмотреть"
                          r"|что послушать|куда пойти", re.I)
CHILD_WORDS = re.compile(r"ребен|ребён|сын|дочь|дочк|детьми|детей|внук|внучк", re.I)


def add_clarifying_question(reply, question, earlier, audience, age, period, named):
    """
    Уточняющий вопрос из rules/clarifying_questions.txt, если модель его не задала,
    а без него совет неточный: возраст ребёнка или дни.
    """
    if "?" in reply:
        return reply
    talk = " ".join(earlier + [question])
    if (age is None and audience != "взрослые" and (audience == "дети" or CHILD_WORDS.search(talk))
            and not re.search(r"нет детей|без детей|детей (?:у меня |у нас )?нет", talk, re.I)):
        return reply.rstrip() + "\n\nСколько лет ребёнку? Подберу по возрастной маркировке."
    if not period and not named and GENERAL_WISH.search(question):
        return reply.rstrip() + "\n\nНа какие дни смотрите — ближайшие выходные или есть конкретная дата?"
    return reply


def ticket_link(doc):
    buy = re.search(r"^Ссылка: (https?://\S+)", doc.content or "", re.M)
    return buy.group(1) if buy else doc.meta.get("url", AFISHA_LINK)


def sold_out(doc):
    return "ПРОДАНЫ" in doc.meta.get("status", "").upper()


def cancelled(doc):
    """Отменён или перенесён на другую дату — в этот день не состоится."""
    return doc.meta.get("status", "").upper().startswith(("ОТМЕНА", "ПЕРЕНОС"))


SOLD_OUT_NOTE = "на эту дату билетов уже нет"
# «[ссылка]», «[билет]» — место для ссылки из образца ответа
LINK_PLACEHOLDER = re.compile(r"\[\s*(?:ссылк|билет|купить)[^\]]{0,40}\]", re.I)


def with_link(line, doc):
    """Приписывает к строке ссылку на билет — или пометку, что билетов нет."""
    if cancelled(doc):
        return line.rstrip(" .,;:—–-") + " (этот концерт отменён или перенесён — подробности в афише)."
    if sold_out(doc):
        if re.search(r"продан|билетов (уже |больше )?нет|нет билетов|закончил", line, re.I):
            return line
        return line.rstrip(" .,;:—–-") + f" ({SOLD_OUT_NOTE})."
    url = ticket_link(doc)
    if re.search(r"билет\w*[^.!?]*$", line, re.I):   # «…, билеты от 800 ₽» → «…: ссылка»
        return line.rstrip(" .,;:—–-") + ": " + url
    return line.rstrip(" .,;:—–-") + " — билеты: " + url


def add_missing_links(reply, concerts, today):
    """
    Некоторые модели (например, ГигаЧат) вырезают ссылки из ответа. Дописываем настоящую
    ссылку на билет из базы:
    — если в строке предложен концерт (есть время или цена), а ссылки нет;
    — если строка кончается на «по этой ссылке: …» — концерт ищем в этой строке и выше.
    """
    upcoming = [d for d in concerts if d.meta.get("date", "") >= today.isoformat()]
    lines = reply.split("\n")
    # Если во всём ответе назван ровно один концерт (полным названием) — ссылка в строке без
    # названия («Спектакль идёт в Камерном зале… — билеты: …») относится к нему
    whole = plain(reply)
    named = [d for d in upcoming
             if any(len(k) >= 6 and plain(k) in whole
                    for k in re.findall(r"«([^«»]{3,})»", d.meta.get("title", "")) + [d.meta.get("title", "")])]
    only_one = (sorted(named, key=lambda d: d.meta["date"])[0]
                if len({d.meta.get("title") for d in named}) == 1 else None)
    def nearest(i):
        """Концерт в этой строке или выше — но только в пределах того же абзаца."""
        for j in range(i, max(-1, i - 5), -1):
            if j < i and not lines[j].strip():
                break
            # в самой строке — только уверенное совпадение («Время — 18:30» не «Время джаза»)
            doc = find_concert(lines[j], upcoming, need_fit=(j == i))
            if doc:
                return doc
        return None

    for i, line in enumerate(lines):
        if LINK_PLACEHOLDER.search(line) and "http" in line:
            # «…: [билет]: https://…» — ссылка уже есть, убираем лишнюю заглушку
            line = lines[i] = re.sub(r":\s*:", ":", LINK_PLACEHOLDER.sub("", line))
        if "intickets" in line:
            # Ссылка на билет есть — проверяем, что она от того же концерта, что назван в строке
            # (или выше в том же абзаце: «Время джаза…» в одной строке, «19:00, …: ссылка» — в другой)
            # (дата и время в самой строке надёжнее, чем случайное общее слово в названии)
            doc = (find_concert(line, upcoming, need_fit=True) or concert_by_when(line, upcoming)
                   or nearest(i) or only_one)
            if doc and (cancelled(doc) or sold_out(doc)):
                lines[i] = with_link(TICKET_PLACEHOLDER.sub(
                    "", re.sub(r"[\s:—–-]*https?://\S*intickets\S*", "", line)), doc)
            elif doc and ticket_link(doc) not in line:
                lines[i] = re.sub(r"https?://\S*intickets\S*?(?=[\s.,;)]*(?:\s|$))", ticket_link(doc), line, count=1)
            continue
        if LINK_PLACEHOLDER.search(line):
            # «…билеты от 500 ₽: [ссылка]» — концерт в этой строке или чуть выше
            doc = nearest(i)
            if doc and sold_out(doc):
                line = LINK_PLACEHOLDER.sub("", line).rstrip(" .,;:—–-") + f" ({SOLD_OUT_NOTE})."
            else:
                line = LINK_PLACEHOLDER.sub(ticket_link(doc) if doc else AFISHA_LINK, line)
            lines[i] = line
            continue
        if "http" in line:
            continue
        base = ELLIPSIS_END.sub("", line).rstrip()
        if LINK_WORDS_END.search(base):
            # «по этой ссылке: …» — ищем концерт сначала в этой строке, потом в 4 строках выше
            doc = nearest(i)
            if doc and sold_out(doc):
                lines[i] = base.rstrip(" :") + f" — {SOLD_OUT_NOTE}."
            else:
                lines[i] = base.rstrip(" :") + ": " + (ticket_link(doc) if doc else AFISHA_LINK)
        elif OFFER_PATTERN.search(line):
            doc = find_concert(line, upcoming)
            if doc:
                lines[i] = with_link(TICKET_PLACEHOLDER.sub("", line), doc)
    return "\n".join(lines)


def fix_links(reply, known_links):
    """
    Модель иногда портит длинные ссылки. Каждую ссылку в ответе сверяем с настоящими
    ссылками из базы: похожую испорченную заменяем на правильную, незнакомую — на афишу.
    """
    def check(match):
        url = match.group(0).rstrip(".,;:!?")
        tail = match.group(0)[len(url):]
        if url in known_links:
            return match.group(0)
        scored = sorted(((difflib.SequenceMatcher(None, url, k).ratio(), k) for k in known_links),
                        reverse=True)
        best = scored[0] if scored else (0, "")
        second = scored[1] if len(scored) > 1 else (0, "")
        # Берём замену, только если она явно ближе остальных — иначе даём ссылку на афишу
        if best[0] >= 0.8 and best[0] - second[0] > 0.03:
            return best[1] + tail
        return AFISHA_LINK + tail
    return URL_PATTERN.sub(check, reply)


# ----------------------------------------------------------------------------
#  Люди: «люблю Василия Сергеевича Шульгу» → концерты, где он дирижирует или руководит
# ----------------------------------------------------------------------------

def name_stem(word):
    """Начало слова без окончания (так же, как в indeksator.py)."""
    word = word.lower().replace("ё", "е")
    if len(word) <= 3:
        return word
    if len(word) <= 5:
        return word[: len(word) - 1]  # «Линь» → «лин» (Линя), «Ганин» → «гани» (Ганина)
    return word[: max(5, len(word) - 2)]


# Насколько важна причина: чем меньше число, тем выше в списке
REASON_ORDER = {"дирижирует": 0, "руководит": 1, "выступает": 2, "указан": 3, "упоминается": 4}


# ----------------------------------------------------------------------------
#  Коллективы: «ГЭДО», «ГОРНИ», «Сибирский калейдоскоп» → все ближайшие концерты коллектива
# ----------------------------------------------------------------------------

COLLECTIVES_FOLDER = PROGRAM_FOLDER / "data" / "collectives"


def alias_pattern(alias):
    """
    «ГЭДО» (сокращение заглавными) — только целым словом; «эстрадно-духов оркестр» — слова могут
    продолжаться окончаниями: найдёт «эстрадно-духового оркестра».
    """
    words = re.findall(r"[а-яёa-z0-9]+", alias.lower().replace("ё", "е"))
    if not words:
        return None
    if alias.isupper() and len(words) == 1:
        return re.compile(r"(?<![а-яa-z0-9])" + re.escape(words[0]) + r"(?![а-яa-z0-9])")
    return re.compile(r"(?<![а-яa-z0-9])"
                      + r"[^а-яa-z0-9]+".join(re.escape(w) + r"[а-яa-z0-9]*" for w in words))


def load_collectives():
    """{название коллектива: [номера концертов на сайте]} из data/collectives."""
    result = {}
    for file in sorted(COLLECTIVES_FOLDER.glob("*.txt")):
        text = file.read_text(encoding="utf-8")
        if not re.search(r"^Тип: коллектив", text, re.M):
            continue
        name = re.search(r"^Название: (.+)$", text, re.M)
        ids = re.search(r"^Концерты: (.+)$", text, re.M)
        if name:
            result[name.group(1).strip()] = re.findall(r"\d+", ids.group(1)) if ids else []
    return result


# Праздники, которые зрители называют без даты: «концерты ко Дню Победы»
HOLIDAYS = ((r"дн\w* победы", 5, 9), (r"международн\w* женск\w* дн|женск\w* дн\w* 8", 3, 8),
            (r"защитник\w* отечества", 2, 23), (r"дн\w* знаний", 9, 1))


def holiday_date(text, today):
    """Ближайшая дата праздника, названного в сообщении, или None."""
    q = text.lower().replace("ё", "е")
    for pattern, month, day in HOLIDAYS:
        if re.search(pattern, q):
            d = date(today.year, month, day)
            return d if d >= today else date(today.year + 1, month, day)
    return None


# «Что такое ваша филармония?», «я только переехал», «репертуарная политика», «какие коллективы»
ABOUT_PHILHARMONIC = re.compile(
    r"что (?:такое|за|из себя представляет)\s+(?:ваш\w*\s+|эта\s+)?филармони"
    r"|(?:расскаж\w*|узнать)[^.?!]{0,30}\bо (?:вашей |самой |этой )?филармони"
    r"|(?:только|недавно|только что) (?:при|пере)ехал|впервые (?:в кемерово|в городе|у вас)"
    r"|репертуарн\w* политик|какие (?:у вас |в филармонии )?(?:есть )?коллективы")
# «У меня недавно умер муж» — личная утрата (а не «концерт памяти погибших»)
GRIEF_PATTERN = re.compile(
    r"(?:у меня|у нас|мой|моя|мои|моего|моей|моих|недавно)[^.!?]{0,40}(?:умер|скончал|погиб|не стало)"
    r"|похорон|овдове|потерял\w* (?:мужа|жену|маму|папу|отца|мать|сына|дочь|ребенка|близк)")
ABOUT_PAGES = ("История", "Коллективы филармонии", "Залы", "Большой зал", "Органный зал", "Орган",
               "Музей", "Проекты", "Абонементы", "Контакты")


def collective_card(name):
    """Руководители и состав коллектива — строками для справки модели."""
    for file in sorted(COLLECTIVES_FOLDER.glob("*.txt")):
        text = file.read_text(encoding="utf-8")
        if not re.search(r"^Название: " + re.escape(name) + r"\s*$", text, re.M):
            continue
        lines = []
        roles = re.findall(r"^Роль: ([^|\n]+)\|([^|\n]+)", text, re.M)
        if roles:
            lines.append("Руководство: " + "; ".join(f"{r.strip().lower()} — {n.strip()}" for r, n in roles))
        members = re.findall(r"^Состав: ([^|\n]+)\|?(.*)$", text, re.M)
        if members:
            lines.append(f"Состав по сайту ({len(members)} чел.): "
                         + "; ".join(f"{n.strip()} — {r.strip().lower()}" if r.strip() else n.strip()
                                     for n, r in members))
            lines.append("Кто из состава занят в конкретном концерте или спектакле, сайт не пишет.")
        page = re.search(r"^Страница: (\S+)", text, re.M)
        if page:
            lines.append(f"Страница коллектива: {page.group(1)}")
        return lines
    return []


def find_collectives(text, collectives):
    """Коллективы, названные в тексте (по названию или по сокращению из rules/collective_aliases.txt)."""
    q = text.lower().replace("ё", "е")
    found = []
    aliases = pravila.collective_aliases()
    for name in collectives:
        names = [name] + aliases.get(name, [])
        for alias in names:
            pattern = alias_pattern(alias)
            if pattern and pattern.search(q):
                found.append(name)
                break
    return found


class PeopleFinder:
    """Находит в сообщении имена дирижёров и артистов и готовит о них справку для модели."""

    def __init__(self, store):
        self.people = []
        if PEOPLE_FILE.exists():
            import json
            self.people = json.loads(PEOPLE_FILE.read_text(encoding="utf-8"))
        # Концерты по номеру на сайте (номер берём из адреса страницы концерта)
        self.concerts = {}
        for doc in store.filter_documents(
                filters={"field": "meta.type", "operator": "==", "value": "концерт"}):
            m = re.search(r"id=(\d+)", doc.meta.get("url", ""))
            if m:
                self.concerts[m.group(1)] = doc

    def find(self, text):
        """Люди, названные в тексте (с учётом падежей; однофамильцев различает по имени)."""
        words = [w.lower().replace("ё", "е") for w in re.findall(r"[А-Яа-яЁё]+", text)]

        def said(part, is_surname=False):
            # При склонении фамилия не становится короче («Казанин» → «Казанина»),
            # поэтому «Казани» (город) на одну букву короче — это не дирижёр Казанин.
            stem = name_stem(part)
            shortest = len(part) if is_surname else len(part) - 1
            return len(stem) >= 3 and any(
                w.startswith(stem) and shortest <= len(w) <= len(part) + 3 for w in words)

        # В одном сообщении может быть несколько людей: «люблю Шульгу и Наталью Кузнецову».
        # Однофамильцев группируем: если имя названо — берём только того, чьё имя названо,
        # если названа одна фамилия — берём всех с этой фамилией.
        groups = {}  # фамилия → (точные совпадения, совпадения только по фамилии)
        for p in self.people:
            parts = p["name"].split()
            if len(parts) < 2:
                continue
            first, surname = parts[0], parts[-1]
            patronymic = parts[1] if len(parts) == 3 else ""
            exact, by_surname = groups.setdefault(surname.lower(), ([], []))
            if said(surname, is_surname=True):
                (exact if said(first) or (patronymic and said(patronymic)) else by_surname).append(p)
            elif patronymic and said(first) and said(patronymic):
                exact.append(p)  # «Василий Сергеевич» без фамилии
        found = []
        for exact, by_surname in groups.values():
            if exact:
                found += exact
            else:
                # Только фамилия: если у одного однофамильца есть концерты или роли, а у другого
                # нет — берём того, у кого есть (дирижёр Василий Шульга, а не музыковед Елизавета)
                active = [p for p in by_surname if p.get("concerts") or p.get("roles")]
                found += active or by_surname
        return found

    def describe(self, person, start=None, end=None, audience="", age=None, halls=()):
        """Справка о человеке: роли и концерты в афише с причиной, почему концерт подходит."""
        lines = [f"=== {person['name']}" + (f" ({person['specialty']})" if person.get("specialty") else "")
                 + " ==="]
        roles = []
        for r in person.get("roles", []):
            if r.get("member"):
                text = f"в составе коллектива «{r['collective']}» — {r['role'].lower()}"
            else:
                text = f"{r['role'].lower()} — {r['collective']}"
            if not r["leads"] and r.get("others"):
                text += f" (руководит коллективом: {', '.join(r['others'])})"
            roles.append(text)
        if roles:
            lines.append("Роли (у человека может быть несколько должностей в разных коллективах — "
                         "называйте все): " + "; ".join(roles) + ".")
        if person.get("about"):
            lines.append("О человеке: " + " ".join(person["about"].split())[:300])

        # Собираем концерты с причинами
        reasons = {}
        for c in person.get("concerts", []):
            word = c["how"].split()[0]
            how = c["how"]
            if c.get("collectives"):  # какой именно коллектив играет — чтобы модель не путала оркестры
                how += f"; на сцене — {', '.join(c['collectives'])}"
            reasons.setdefault(c["id"], []).append((REASON_ORDER.get(word, 4), how))
        for r in person.get("roles", []):
            for cid in r.get("concert_ids", []):
                if r.get("member"):
                    reasons.setdefault(cid, []).append(
                        (REASON_ORDER["указан"],
                         f"концерт коллектива «{r['collective']}», где он(а) в составе ({r['role'].lower()}); "
                         "занят(а) ли он(а) именно в этом концерте, на сайте не сказано"))
                else:
                    reasons.setdefault(cid, []).append(
                        (REASON_ORDER["руководит"],
                         f"коллектив под его руководством ({r['role'].lower()} — {r['collective']})"))

        items = []
        for cid, why in reasons.items():
            doc = self.concerts.get(cid)
            if doc is None:
                continue  # концерт прошёл или его нет в афише
            title = doc.meta.get("title", "")
            why = sorted(why)
            # Экскурсии «Закулисье» — не концерты под управлением дирижёра
            if title.lower().startswith("экскурсия") and (
                    why[0][0] == REASON_ORDER["руководит"] or "в составе" in why[0][1]):
                continue
            if start and not (start <= doc.meta.get("date", "") <= end):
                continue
            if not is_ours(doc, halls) or not fits_audience(doc, audience, age):
                continue
            items.append((why[0][0], doc.meta.get("date", ""), doc, why[0][1]))

        lines.append("Концерты в афише:")
        if not items:
            lines.append("- в ближайшей афише концертов, где он(а) дирижирует, руководит или выступает, не найдено")
        items.sort(key=lambda x: (x[0], x[1]))  # сначала «точно дирижирует», потом его коллектив, по дате
        for _, _, doc, why in items[:MAX_PERSON_CONCERTS]:
            m = doc.meta
            note = short_status(m.get("status", ""))
            buy = re.search(r"^Ссылка: (https?://\S+)", doc.content or "", re.M)
            # Начало описания именно этого концерта — чтобы модель не брала подробности у соседних
            about = (doc.content or "").split("Описание:", 1)[-1].strip()
            about = " ".join(about.split())
            about = about[:180].rsplit(" ", 1)[0] + "…" if len(about) > 180 else about
            lines.append(f"- {m['when']} | {m['title']} | {m['hall']} | возраст {m['age']} | {m['price']}"
                         f"{' | ' + note if note else ''}{' | билет: ' + buy.group(1) if buy else ''}"
                         f" | почему подходит: {why} | о концерте: {about}")
        if len(items) > MAX_PERSON_CONCERTS:
            lines.append(f"(и ещё {len(items) - MAX_PERSON_CONCERTS} — полная афиша: {AFISHA_LINK})")
        if any(not r["leads"] and not r.get("member") for r in person.get("roles", [])):
            lines.append("Где он(а) не главный дирижёр, в список вошли только концерты, в описании "
                         "которых прямо сказано, что дирижирует он(а).")
        if any(r.get("member") for r in person.get("roles", [])):
            lines.append("Состав исполнителей конкретного концерта или спектакля на сайте не публикуется. "
                         "Не утверждайте ни «участвует», ни «не участвует»: скажите, что он(а) в составе "
                         "коллектива, назовите ближайшие концерты коллектива и предложите уточнить состав "
                         f"в кассе ({CASHIER_PHONE}).")
        return "\n".join(lines)


def make_chat_generator():
    """Модель, которая пишет ответы: локальная (Ollama), ГигаЧат или DeepSeek — по CHAT_PROVIDER."""
    if CHAT_PROVIDER == "ollama":
        return OllamaChatGenerator(
            model=CHAT_MODEL, url=OLLAMA_URL, think=False, keep_alive="30m", timeout=300,
            generation_kwargs={"temperature": TEMPERATURE, "num_ctx": CONTEXT_SIZE})

    if CHAT_PROVIDER == "deepseek":
        from haystack.components.generators.chat import OpenAIChatGenerator
        from haystack.utils import Secret
        try:
            key = DEEPSEEK_KEY_FILE.read_text(encoding="utf-8-sig").strip()
        except OSError:
            key = ""
        if not key:
            raise FileNotFoundError(
                f"Нет ключа DeepSeek. Создайте файл «{DEEPSEEK_KEY_FILE.name}» в папке «keys» "
                "и вставьте в него ключ одной строкой — или верните CHAT_PROVIDER = \"ollama\".")
        # Ключ передаём через переменную окружения, чтобы он не попадал в журналы и настройки
        os.environ["DEEPSEEK_API_KEY"] = key
        kwargs = {"max_tokens": 1500,
                  "extra_body": {"thinking": {"type": "enabled" if DEEPSEEK_THINKING else "disabled"}}}
        if not DEEPSEEK_THINKING:
            kwargs["temperature"] = TEMPERATURE  # в режиме размышлений температура не действует
        return OpenAIChatGenerator(
            api_key=Secret.from_env_var("DEEPSEEK_API_KEY"), model=DEEPSEEK_MODEL,
            api_base_url=DEEPSEEK_URL, timeout=120, max_retries=2, generation_kwargs=kwargs)

    if CHAT_PROVIDER == "gigachat":
        from gigachat_api import GigaChatGenerator
        return GigaChatGenerator(
            key_file=GIGACHAT_KEY_FILE, cert_file=GIGACHAT_CERT_FILE, model=GIGACHAT_MODEL,
            scope=GIGACHAT_SCOPE, auth_url=GIGACHAT_AUTH_URL, api_url=GIGACHAT_API_URL,
            temperature=TEMPERATURE, max_tokens=1500,
            # если фильтр ГигаЧата по ошибке откажется отвечать — ответит локальная модель
            fallback=OllamaChatGenerator(
                model=CHAT_MODEL, url=OLLAMA_URL, think=False, keep_alive="30m", timeout=300,
                generation_kwargs={"temperature": TEMPERATURE, "num_ctx": CONTEXT_SIZE}))

    raise ValueError(f"Неизвестный CHAT_PROVIDER = «{CHAT_PROVIDER}». "
                     "Нужно \"ollama\", \"gigachat\" или \"deepseek\".")


def model_name():
    """Как называется модель, которая сейчас пишет ответы (для журналов и проверки)."""
    return {"deepseek": DEEPSEEK_MODEL, "gigachat": GIGACHAT_MODEL}.get(CHAT_PROVIDER, CHAT_MODEL)


def no_template(text):
    """
    Для реплик помощника: Haystack не обрабатывает их как шаблон, поэтому защита {% raw %}
    попала бы модели как есть (и та начинала её копировать). Просто разбиваем фигурные скобки.
    """
    return text.replace("{%", "{ %").replace("%}", "% }").replace("{{", "{ {").replace("}}", "} }")


def raw(text):
    """Защищает текст от того, чтобы фигурные скобки в нём приняли за команды шаблона."""
    return "{% raw %}" + text.replace("{% endraw %}", "") + "{% endraw %}"


# ----------------------------------------------------------------------------
#  Помощник
# ----------------------------------------------------------------------------

class Assistant:
    """Загружает индекс и отвечает зрителям. Его использует окно чата (okno.py)."""

    def __init__(self, store=None):
        """store — уже загруженный индекс (при смене модели в окне не читаем его заново)."""
        if store is None:
            if not INDEX_FILE.exists():
                raise FileNotFoundError(
                    f"Нет файла индекса «{INDEX_FILE}». Сначала запустите indeksator.py")
            store = InMemoryDocumentStore.load_from_disk(str(INDEX_FILE))
        self.store = store

        # Начальный шаблон нужен только чтобы перечислить, какие сведения подставляются;
        # настоящая инструкция читается из папки «rules» при каждом вопросе
        template = [ChatMessage.from_system("{{ today }} {{ phone }}"), ChatMessage.from_user(USER_TEMPLATE)]
        p = Pipeline()
        p.add_component("text_embedder", OllamaTextEmbedder(
            model=EMBEDDING_MODEL, url=OLLAMA_URL, keep_alive="30m"))
        p.add_component("by_meaning", InMemoryEmbeddingRetriever(self.store, top_k=TOP_K))
        p.add_component("by_words", InMemoryBM25Retriever(self.store, top_k=TOP_K))
        p.add_component("by_title", TitleSearch(self.store, top_k=TOP_K))
        p.add_component("joiner", DocumentJoiner(join_mode="reciprocal_rank_fusion", top_k=TOP_K))
        p.add_component("focus", Focus(self.store))
        p.add_component("prompt", ChatPromptBuilder(template=template, required_variables="*"))
        p.add_component("llm", make_chat_generator())

        p.connect("text_embedder.embedding", "by_meaning.query_embedding")
        p.connect("by_meaning.documents", "joiner.documents")
        p.connect("by_words.documents", "joiner.documents")
        p.connect("by_title.documents", "joiner.documents")
        p.connect("joiner.documents", "focus.documents")
        p.connect("focus.documents", "prompt.documents")
        p.connect("prompt.prompt", "llm.messages")
        self.pipeline = p
        self.people = PeopleFinder(self.store)
        self.collectives = load_collectives()
        # На странице коллектива на сайте перечислены не все его концерты (например, без тех,
        # где билеты уже проданы). Добавляем концерты, где коллектив назван в самом названии:
        # «А. Беляев «Голова профессора Доуэля». Литературный театр «Слово»».
        for name, ids in self.collectives.items():
            pattern = alias_pattern(name)
            for cid, doc in self.people.concerts.items():
                if cid not in ids and pattern and pattern.search(plain(doc.meta.get("title", ""))):
                    ids.append(cid)
        for person in self.people.people:  # те же концерты — артистам и руководителям коллектива
            for r in person.get("roles", []):
                if r.get("concert_ids") and r["collective"] in self.collectives:
                    r["concert_ids"] = list(self.collectives[r["collective"]])
        # Дата последнего концерта в базе — дальше афиша не загружена
        dates = [d.meta.get("date", "") for d in self.store.filter_documents(
            filters={"field": "meta.type", "operator": "==", "value": "концерт"})]
        self.last_date = date.fromisoformat(max(dates)) if any(dates) else None

    def events_in_period(self, start, end, audience="", age=None, halls=()):
        """Список событий за период; повторяющиеся спектакли — одной строкой."""
        concerts = self.store.filter_documents(
            filters={"field": "meta.type", "operator": "==", "value": "концерт"})
        chosen = sorted(
            (d for d in concerts
             if start.isoformat() <= d.meta["date"] <= end.isoformat()
             and is_ours(d, halls) and fits_audience(d, audience, age) and not cancelled(d)),
            key=lambda d: (d.meta["date"], d.meta.get("when", "")))
        if not chosen:
            return "В афише на этот период подходящих событий нет."

        # Повторяющиеся спектакли объединяем в одну строку со всеми датами
        groups = {}
        for d in chosen:
            key = (d.meta["title"], d.meta["hall"], d.meta["age"], d.meta["price"])
            note = short_status(d.meta.get("status", ""))
            groups.setdefault(key, []).append(d.meta["when"] + (f" ({note})" if note else ""))

        lines = [f"- {title} | {hall} | возраст {age} | {price} | даты: {'; '.join(whens)}"
                 for (title, hall, age, price), whens in list(groups.items())[:MAX_EVENTS_IN_PERIOD]]
        if len(groups) > MAX_EVENTS_IN_PERIOD:
            lines.append(f"(и ещё {len(groups) - MAX_EVENTS_IN_PERIOD} событий — полный список на сайте "
                         f"{AFISHA_LINK})")
        if age is not None:
            lines.insert(0, f"(самому младшему зрителю {age}: оставлены только события до {age}+)")
        elif audience == "взрослые":
            lines.insert(0, "(зритель идёт без детей: спектакли для малышей 0+ убраны)")
        elif audience == "дети":
            lines.insert(0, "(зритель идёт с ребёнком: отобраны только события 0+ и 6+)")
        return "\n".join(lines)

    def about_philharmonic(self):
        """Краткая справка о филармонии из постоянных страниц сайта (для общих вопросов)."""
        lines = ["=== О ФИЛАРМОНИИ (коротко, по страницам сайта) ===",
                 "Рассказывай только то, что написано ниже. В 1943 году появилось концертно-эстрадное бюро, "
                 "филармония создана в 1954 году. Не называй юбилеев и жанров, которых здесь нет."]
        for page in ABOUT_PAGES:
            docs = self.store.filter_documents(filters={"field": "meta.page", "operator": "==", "value": page})
            docs = sorted(docs, key=lambda d: d.meta.get("part", 0))[:1]
            for d in docs:
                text = " ".join((d.content or "").split())
                text = text[:700].rsplit(" ", 1)[0] + "…" if len(text) > 700 else text
                lines.append(f"Страница «{page}»: {text}")
        return "\n".join(lines)

    def describe_collective(self, name, start=None, end=None, audience="", age=None, halls=()):
        """Справка о коллективе для модели: все его ближайшие концерты (или в названные дни)."""
        short = ", ".join(a for a in pravila.collective_aliases().get(name, []) if a.isupper())
        lines = [f"=== КОЛЛЕКТИВ: {name}" + (f" (сокращённо: {short})" if short else "") + " ==="]
        lines += collective_card(name)
        lines.append("Концерты в афише:")
        docs = [self.people.concerts[cid] for cid in self.collectives.get(name, []) if cid in self.people.concerts]
        today = date.today().isoformat()
        docs = sorted((d for d in docs if d.meta.get("date", "") >= today and is_ours(d, halls)
                       and not cancelled(d) and fits_audience(d, audience, age)),
                      key=lambda d: (d.meta["date"], d.meta.get("when", "")))
        chosen = docs
        if start:
            chosen = [d for d in docs if start <= d.meta["date"] <= end]
            if not chosen and docs:
                lines.append("В названные дни концертов этого коллектива нет. Ближайшие после них:")
                chosen = [d for d in docs if d.meta["date"] > end] or docs
        if not chosen:
            lines.append("- в загруженной афише концертов этого коллектива нет")
        for d in chosen[:MAX_PERSON_CONCERTS]:
            m = d.meta
            note = short_status(m.get("status", ""))
            about = " ".join((d.content or "").split("Описание:", 1)[-1].split())
            about = about[:180].rsplit(" ", 1)[0] + "…" if len(about) > 180 else about
            lines.append(f"- {m['when']} | {m['title']} | {m['hall']} | возраст {m['age']} | {m['price']}"
                         f"{' | ' + note if note else ''} | билет: {ticket_link(d)} | о концерте: {about}")
        if len(chosen) > MAX_PERSON_CONCERTS:
            lines.append(f"(и ещё {len(chosen) - MAX_PERSON_CONCERTS} — полная афиша: {AFISHA_LINK})")
        return "\n".join(lines), chosen[:MAX_PERSON_CONCERTS]

    def no_events_reply(self, start, end, audience="", age=None, halls=()):
        """
        Готовый ответ, если в названные дни концертов нет: модель здесь не нужна (и могла бы
        выдумать концерт). Показываем ближайшие подходящие события после этих дней.
        """
        today = date.today()
        if start == end:
            when = ("Сегодня" if start == today else "Завтра" if start == today + timedelta(1)
                    else f"{start.day} {MONTH_NAMES[start.month - 1]}")
        else:
            when = (f"С {start.day} {MONTH_NAMES[start.month - 1]} "
                    f"по {end.day} {MONTH_NAMES[end.month - 1]}")
        concerts = [d for d in self.people.concerts.values() if is_ours(d, halls)]
        any_ours = any(start.isoformat() <= d.meta["date"] <= end.isoformat() for d in concerts)
        when += (" подходящих по возрасту концертов в филармонии нет" if any_ours
                 else " концертов в филармонии нет")
        after = max(end, today).isoformat()
        upcoming = sorted((d for d in concerts if d.meta["date"] > after
                           and fits_audience(d, audience, age) and not sold_out(d) and not cancelled(d)),
                          key=lambda d: (d.meta["date"], d.meta.get("when", "")))
        nearest, seen = [], set()
        for d in upcoming:  # спектакль с несколькими сеансами — одной строкой, по первому сеансу
            if d.meta["title"] not in seen:
                seen.add(d.meta["title"])
                nearest.append(d)
            if len(nearest) == 3:
                break
        lines = [f"— {d.meta['when']} — {d.meta['title']}, {d.meta['hall']}, {d.meta['age']}: {ticket_link(d)}"
                 for d in nearest] or ["— пока в загруженной афише ничего подходящего нет"]
        return pravila.reply("концертов нет", когда=when, ближайшие="\n".join(lines))

    def ask(self, question, history=None):
        """
        question — новое сообщение зрителя;
        history — предыдущие реплики: список пар (кто, текст), где кто — "зритель" или "помощник".
        Возвращает (ответ, найденные материалы, период или None).
        """
        history = (history or [])[-2 * HISTORY_TURNS:]
        today = date.today()
        self.fallback_used = False

        # Если новое сообщение — уточнение («а без детей?»), ищем вместе с двумя предыдущими
        # сообщениями зрителя. Если зритель сменил тему («где туалет?» после вопроса о еде) —
        # ищем только по новому сообщению, иначе поиск тянет старую тему и модель повторяется.
        all_earlier = [text for who, text in history if who == "зритель"][-2:]
        earlier = all_earlier if is_followup(question) else []
        search_text = " ".join(earlier + [question])

        # Выступить у нас, арендовать зал, заказать съёмку — точный готовый ответ без модели
        topic = service_topic(question)
        if topic:
            return pravila.reply(topic), [], None
        # Зритель делится впечатлениями без вопроса — сразу зовём на страницу отзывов
        feedback = feedback_kind(question)
        if feedback and not QUESTION_PATTERN.search(question):
            return pravila.reply(f"отзыв {feedback}"), [], None

        period = find_period(question, today) or find_period(" ".join(earlier), today)
        holiday = holiday_date(question, today)
        if not period and holiday:
            if self.last_date and holiday > self.last_date:
                # «Концерты ко Дню Победы?» в ноябре — афиши на май ещё нет; без этого модель
                # рассказывала, что такие концерты «обычно проходят», и советовала декабрьские
                return pravila.reply("афиша не загружена", до=f"{self.last_date:%d.%m.%Y}"), [], None
            period = (holiday - timedelta(days=6), holiday)  # концерты к празднику — в неделю до него
        if (period and self.last_date and period[0] > self.last_date
                and (CONCERT_WORDS.search(question.lower().replace("ё", "е")) or earlier)):
            # Спрашивают о датах, которых нет в базе (например, сборщик берёт афишу только
            # до конца года). Отвечаем готовым текстом — иначе модель может выдумать концерт.
            return pravila.reply("афиша не загружена", до=f"{self.last_date:%d.%m.%Y}"), [], period
        audience = find_audience(question) or find_audience(" ".join(earlier))
        # Возраст цифрами («ребёнку 5 лет») — точнее, чем просто «с детьми»
        age = find_age(question)
        if age is None:
            age = find_age(" ".join(earlier))
        # Выездные концерты — только если зритель назвал свой город («я из Юрги»)
        halls = visiting_halls(" ".join(all_earlier + [question]), self.people.concerts.values())
        about = ABOUT_AUDIENCE.get(audience, "")
        if age is not None:
            about = (f"самому младшему зрителю {age} — подходят только события с возрастной маркировкой "
                     f"не больше {age}+ (остальные уже убраны).")
        grief = bool(GRIEF_PATTERN.search(question.lower().replace("ё", "е")))
        if grief:
            about += (" Зритель пережил утрату или тяжёлое событие: начни ответ с одной короткой простой фразы "
                      "сочувствия («Примите мои соболезнования»), затем предложи 1–2 спокойных, светлых концерта; "
                      "юмористические, шумные и праздничные программы не предлагай.")
        if halls:
            about += (" Зритель назвал свой город — можно предлагать выездные концерты филармонии "
                      "там: " + "; ".join(sorted(halls)) + ".")
        afisha = self.events_in_period(*period, audience=audience, age=age, halls=halls) if period else ""
        if not period and age is not None and not service_topic(question):
            # «Ему 5 лет» без дат — даём модели все подходящие по возрасту события ближайшего месяца,
            # иначе поиск по словам «ему 5 лет» ничего не находит и модель выдумывает спектакль
            afisha = self.events_in_period(today, today + timedelta(days=30), audience=audience, age=age,
                                           halls=halls)
            if afisha.startswith("В афише на этот период подходящих событий нет"):
                afisha = ""
        about_concerts = bool(CONCERT_WORDS.search(question.lower().replace("ё", "е")) or earlier)
        if period and about_concerts and afisha.startswith("В афише на этот период подходящих событий нет"):
            # В эти дни концертов нет — отвечаем сами, без модели: она могла бы выдумать концерт
            return self.no_events_reply(*period, audience=audience, age=age, halls=halls), [], period
        today_text = f"{today:%d.%m.%Y}, {WEEKDAYS[today.weekday()]}"
        if self.last_date:  # чтобы модель не «вспоминала» майские концерты, которых нет в базе
            today_text += f" (афиша в справочных сведениях известна по {self.last_date:%d.%m.%Y})"

        # Названы ли в разговоре дирижёры или артисты (сначала в новом сообщении)
        persons = self.people.find(question) or self.people.find(" ".join(earlier))
        people_text = "\n\n".join(
            self.people.describe(p, *(d.isoformat() for d in period) if period else (None, None),
                                 audience=audience, age=age, halls=halls)
            for p in persons[:MAX_PERSONS])
        if len(persons[:MAX_PERSONS]) > 1:
            people_text = ("Это разные люди. У каждого — свой список концертов; "
                           "не переносите концерты одного человека к другому.\n\n" + people_text)
        known_people_urls = []  # ссылки из справки о людях тоже считаем настоящими
        for p in persons[:MAX_PERSONS]:
            known_people_urls.append(p.get("url", ""))

        # Названы ли коллективы («ГЭДО», «ГОРНИ», «Сибирский калейдоскоп») — даём все их концерты
        groups = find_collectives(question, self.collectives) or (
            find_collectives(" ".join(earlier), self.collectives) if earlier else [])
        collective_docs = []
        for name in groups[:MAX_PERSONS]:
            text, docs = self.describe_collective(
                name, *(d.isoformat() for d in period) if period else (None, None),
                audience=audience, age=age, halls=halls)
            people_text = (people_text + "\n\n" if people_text else "") + text
            collective_docs += docs
        if len(groups) > 1:
            people_text = ("Это разные коллективы — не переносите концерты одного коллектива к другому.\n\n"
                           + people_text)

        # Общий вопрос о самой филармонии («только переехал, что это за место?», «репертуарная
        # политика») — поиск по словам находит 1–2 случайные страницы, поэтому даём модели
        # сразу краткую справку из страниц «История», «Залы», «Музей», «Проекты», «Коллективы»
        if ABOUT_PHILHARMONIC.search(question.lower().replace("ё", "е")):
            people_text = (people_text + "\n\n" if people_text else "") + self.about_philharmonic()

        # Шаблон: инструкция + начало разговора + новое сообщение со справочными сведениями
        template = [ChatMessage.from_system(pravila.instruction())]
        # Образец разговора из папки «rules» — модель перенимает из него манеру ответа
        sample = pravila.example()
        if sample:
            facts, sample_question, sample_answer = sample
            template.append(ChatMessage.from_user(raw(
                "ОБРАЗЕЦ ТОНА. События в этом примере вымышленные — никогда не называй их зрителю.\n"
                f"Справочные сведения:\n{facts}\n\nСообщение зрителя: {sample_question}")))
            template.append(ChatMessage.from_assistant(no_template(sample_answer)))
        # Большие модели (ГигаЧат, DeepSeek) видят и свои прошлые ответы — так они понимают,
        # что уже сказали, и не повторяются. Маленькой локальной модели их не показываем.
        with_replies = HISTORY_WITH_REPLIES or CHAT_PROVIDER != "ollama"
        for who, text in history:
            if who != "зритель" and not with_replies:
                continue
            # Свои прошлые ответы даём модели коротко, чтобы она не повторяла их целиком
            if who == "зритель":
                template.append(ChatMessage.from_user(raw(text[:800])))
            else:
                template.append(ChatMessage.from_assistant(no_template(text[:400])))
        template.append(ChatMessage.from_user(USER_TEMPLATE))

        result = self.pipeline.run(
            {
                "text_embedder": {"text": search_text},
                "by_words": {"query": search_text},
                "by_title": {"query": search_text},
                "focus": {"start": period[0].isoformat() if period else "",
                          "end": period[1].isoformat() if period else "",
                          "audience": audience, "people_mode": bool(persons or groups),
                          "age": -1 if age is None else age, "halls": sorted(halls),
                          "skip_pages": [] if re.search(r"проект", question, re.I) else ["Проекты"]},
                "prompt": {"template": template,
                           # подсказку о горе ставим прямо у сообщения — так модель её не пропускает
                           "question": question + ("\n(Подсказка помощнику, зрителю её не пересказывать: "
                                                   "у зрителя горе — не предлагай юмористические, шумные "
                                                   "и праздничные программы, только спокойные.)" if grief else ""),
                           "afisha": afisha,
                           "about": about, "people": people_text,
                           "today": today_text, "phone": CASHIER_PHONE},
            },
            include_outputs_from={"focus"},
        )
        # Ответила ли запасная модель (ГигаЧат отказался из-за фильтра «чувствительных тем»)
        self.fallback_used = getattr(self.pipeline.get_component("llm"), "last_refused", False)
        reply = result["llm"]["replies"][0].text or ""
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S)
        reply = re.sub(r"\{%-?\s*(?:end)?raw\s*-?%\}", "", reply)  # служебные пометки шаблона
        # Пометки источников из справки («[коллектив: Камерный оркестр]») зрителю не нужны
        reply = re.sub(r"[ \t]*\[(?:коллектив|концерт|страница|артист|info|информация)\b[^\]\n]*\]", "", reply)
        reply = CJK_PATTERN.sub("", reply)  # страховка от иероглифов
        # Окно чата не показывает разметку — убираем звёздочки и решётки
        reply = reply.replace("**", "").replace("__", "")
        reply = re.sub(r"(?m)^\s*#+\s*", "", reply)
        reply = re.sub(r"\[([^\]]*)\]\((https?://[^)\s]+)\)", r"\2", reply)  # [текст](ссылка) → ссылка
        reply = re.sub(r"(?m)^(\s*)\*\s+", r"\1— ", reply)                   # «* пункт» → «— пункт»
        reply = re.sub(r"\*([^*\n]+)\*", r"\1", reply)                         # *курсив* → курсив
        reply = re.sub(r"[ \t]{2,}", " ", reply).strip()
        reply = polish_reply(reply, question)
        if grief and not re.search(r"соболезн|сочувств|очень жаль|сожалею", reply, re.I):
            reply = "Примите мои соболезнования.\n\n" + reply  # модель иногда пропускает сочувствие
        # Возраст и «без детей» — проверяем и готовый ответ: модель иногда повторяет событие
        # из своего прошлого ответа, которое теперь не подходит (концерт 6+ для пятилетнего)
        if age is not None or audience:
            reply = drop_unsuitable(reply, [d for d in self.people.concerts.values()
                                            if d.meta.get("date", "") >= today.isoformat()], audience, age)
        reply = drop_unknown_events(reply, list(self.people.concerts.values()))
        reply = fix_genitive_names(reply, self.people.people)
        reply = add_clarifying_question(reply, question, earlier, audience, age, period, persons or groups)

        # Сверяем ссылки в ответе с настоящими ссылками из найденных материалов
        known = (set(URL_PATTERN.findall(afisha)) | set(URL_PATTERN.findall(people_text))
                 | {u for u in known_people_urls if u})
        person_docs = [self.people.concerts[c["id"]] for p in persons[:MAX_PERSONS]
                       for c in p.get("concerts", []) if c["id"] in self.people.concerts]
        person_docs += [self.people.concerts[cid] for p in persons[:MAX_PERSONS] for r in p.get("roles", [])
                        for cid in r.get("concert_ids", []) if cid in self.people.concerts]
        for doc in result["focus"]["documents"] + person_docs + collective_docs:
            known.update(URL_PATTERN.findall(doc.content or ""))
            if doc.meta.get("url"):
                known.add(doc.meta["url"])
        known = {u.rstrip(".,;:!?") for u in known} | {AFISHA_LINK}
        if feedback:  # страница отзывов — только когда зритель делится впечатлениями,
            known.add(REVIEWS_LINK)  # иначе на неё «притягиваются» похожие испорченные ссылки
        reply = fix_links(reply, sorted(known))
        reply = add_missing_links(
            reply, [d for d in self.people.concerts.values() if is_ours(d, halls)], today)
        # Впечатления вместе с вопросом: модель ответила на вопрос, ссылку на отзывы добавляем сами
        if feedback and REVIEWS_LINK not in reply:
            reply += "\n\n" + pravila.reply("ссылка на отзыв")
        return reply, result["focus"]["documents"], period


def describe(doc):
    m = doc.meta
    if m.get("type") == "концерт":
        return f"концерт: {m.get('when')} — {m.get('title')} ({m.get('age')})"
    return f"страница «{m.get('page')}», кусочек {m.get('part')}"


if __name__ == "__main__":
    print("Помощник запускается из окна: дважды щёлкните «run_assistant.bat».")
