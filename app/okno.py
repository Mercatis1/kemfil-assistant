# -*- coding: utf-8 -*-
"""
ПОМОЩНИК ФИЛАРМОНИИ КУЗБАССА — ОКНО ЧАТА
========================================

Главная программа проекта: окно на компьютере, где можно разговаривать с помощником.
Запуск: двойной щелчок по «run_assistant.bat» в папке бота.

Что умеет:
  - отвечает по афише и страницам сайта филармонии (pomoshnik.py);
  - помнит разговор и понимает уточнения («а без детей?»);
  - модель можно сменить прямо в окне — список вверху: локальные модели Ollama,
    ГигаЧат (и DeepSeek, если рядом лежит его ключ);
  - на тревожные сообщения и грубость отвечает готовыми текстами из папки «rules»;
  - кнопка «Новый разговор» очищает чат и память.

Тексты ответов и инструкция для модели — в папке «rules»; правки действуют сразу.
Идея окна взята из учебного проекта haystack-rag-app_gui (файл gui.py).
"""

# ============================================================================
#  НАСТРОЙКИ
# ============================================================================

from pathlib import Path

PROGRAM_FOLDER = Path(__file__).resolve().parent.parent  # папка бота (эта программа лежит в её подпапке)
LOG_FILE = PROGRAM_FOLDER / "data" / "app_log.txt"
LOGO_FILE = Path(__file__).resolve().parent / "assets" / "logo.png"   # логотип с kemfil.ru

# Сколько полупрозрачных нот рассыпано по фону чата (0 — без нот)
BACKGROUND_NOTES = 28

TITLE = "Помощник Филармонии Кузбасса"
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 800
BUBBLE_MAX_WIDTH = 600  # самое широкое «облачко» сообщения, в точках экрана

# После скольких сообщений с матом помощник перестаёт отвечать (до «Нового разговора»)
RUDE_LIMIT = 3

# ---- Защита от спама (и от лишней траты токенов ГигаЧата) ----
MAX_MESSAGE_LENGTH = 1000     # самое длинное сообщение, в знаках
FLOOD_MESSAGES = 6            # не больше 6 сообщений…
FLOOD_SECONDS = 60            # …за 60 секунд
MAX_MODEL_ANSWERS_PER_HOUR = 60   # сколько раз в час можно обращаться к модели в одном разговоре

# ---- Журнал окна (data/app_log.txt) сам себя очищает ----
LOG_MAX_LINES = 2000      # когда записей становится больше…
LOG_KEEP_LINES = 1000     # …оставляем только последние 1000, старые удаляются
LOG_LINE_LENGTH = 300     # длинные записи (ошибки, тексты сообщений) обрезаются

# Записывать ли вопросы в журнал (только время и текст). Помогает улучшать правила,
# но прежде чем включать для зрителей — уточните правила филармонии о персональных данных.
LOG_QUESTIONS = False

# Цвета: тёмный фон, бордовый и золотой — как бархат и люстры концертного зала
BG = "#14110f"
PANEL = "#1f1a17"
ACCENT = "#c9a227"        # золотой
USER_BG = "#5a1f2b"       # бордовый
BOT_BG = "#2a2420"
NOTE_BG = "#3a2f14"       # подсказки для сотрудника
TEXT = "#f1ebe4"
MUTED = "#9c9086"
LINK = "#e6c45c"

# ============================================================================
#  ДАЛЬШЕ — САМА ПРОГРАММА
# ============================================================================

import random
import re
import sys
import time
from datetime import datetime

import flet as ft
import requests

import pomoshnik
import pravila
from krizis import crisis_kind
from maty import is_rude

URL_PATTERN = re.compile(r"https?://[^\s<>«»\"]+")
DEMO = {"model": None, "questions": []}   # демо-режим: см. конец файла
GREETING_WORDS = ("начать", "start", "привет", "здравствуйте", "добрый день", "меню")
RESTART_WORDS = ("заново", "сначала", "сброс")


def log(message):
    """
    Показывает сообщение в консоли и записывает его в журнал окна.
    Запись — одна строка, не длиннее LOG_LINE_LENGTH; когда записей больше LOG_MAX_LINES,
    в журнале остаются только последние LOG_KEEP_LINES.
    """
    message = " ".join(str(message).split())  # многострочные ошибки — в одну строку
    if len(message) > LOG_LINE_LENGTH:
        message = message[:LOG_LINE_LENGTH] + "…"
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}"
    print(line, flush=True)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        # Проверяем размер, только когда файл стал заметным (строк ~ по 100 знаков)
        if LOG_FILE.stat().st_size > LOG_MAX_LINES * 60:
            lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
            if len(lines) > LOG_MAX_LINES:
                LOG_FILE.write_text("\n".join(lines[-LOG_KEEP_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


# ----------------------------------------------------------------------------
#  Разговор: тревожные сообщения, грубость, команды и вопросы к помощнику
# ----------------------------------------------------------------------------

class Dialog:
    def __init__(self):
        self.reset()

    def reset(self):
        self.history = []     # [(кто, текст), ...]
        self.rude_count = 0
        self.stopped = False  # разговор прекращён из-за грубости
        self.message_times = []   # когда приходили сообщения (для защиты от спама)
        self.model_times = []     # когда обращались к модели
        self.last_text = ""

    def spam_reply(self, text):
        """Готовый ответ, если сообщение похоже на спам; иначе ""."""
        now = time.time()
        self.message_times = [t for t in self.message_times if now - t < FLOOD_SECONDS] + [now]
        if len(self.message_times) > FLOOD_MESSAGES:
            log("Защита от спама: слишком много сообщений подряд.")
            return pravila.reply("слишком часто")
        if len(text) > MAX_MESSAGE_LENGTH:
            log(f"Защита от спама: сообщение длиной {len(text)} знаков.")
            return pravila.reply("слишком длинное")
        same = re.sub(r"\W+", " ", text.lower()).strip()
        if same and same == self.last_text:
            return pravila.reply("повтор")
        self.last_text = same
        self.model_times = [t for t in self.model_times if now - t < 3600]
        if len(self.model_times) >= MAX_MODEL_ANSWERS_PER_HOUR:
            log("Защита от спама: исчерпан часовой лимит обращений к модели.")
            return pravila.reply("слишком часто")
        return ""

    def answer(self, assistant, text):
        """Возвращает (список ответов, получилось ли спросить модель)."""
        lowered = text.lower().strip("!.?, ")

        # Тревожные сообщения — первыми: даже если разговор прекращён или в сообщении мат
        kind = crisis_kind(text)
        if kind == "себе":
            phones = "\n".join("— " + p for p in pravila.phones())
            log("Тревожное сообщение: человек пишет, что ему очень плохо — показаны телефоны помощи.")
            return [pravila.reply("зрителю плохо", телефоны=phones)], True
        if kind == "угроза":
            log(f"ВНИМАНИЕ: сообщение с угрозой: «{text[:500]}»")
            return [pravila.reply("угроза")], True

        if self.stopped:
            return [], True
        if is_rude(text):
            self.rude_count += 1
            if self.rude_count >= RUDE_LIMIT:
                self.stopped = True
                self.history = []
                log(f"Разговор прекращён после {RUDE_LIMIT} сообщений с грубостью.")
                return [pravila.reply("грубость прощание")], True
            return [pravila.reply(f"грубость {min(self.rude_count, 2)}")], True

        if lowered in GREETING_WORDS:
            self.history = []
            return [pravila.reply("приветствие")], True
        if lowered in RESTART_WORDS:
            self.history = []
            return [pravila.reply("заново")], True

        spam = self.spam_reply(text)
        if spam:
            return [spam], True

        if LOG_QUESTIONS:
            log(f"Вопрос: {text}")
        self.model_times.append(time.time())
        try:
            reply, _, _ = assistant.ask(text, self.history)
        except Exception as e:
            log(f"ОШИБКА помощника ({pomoshnik.model_name()}): {e.__class__.__name__}: {e}")
            return [pravila.reply("не получилось ответить")], False
        self.history = (self.history + [("зритель", text), ("помощник", reply)])[-2 * pomoshnik.HISTORY_TURNS:]
        return [reply], True


# ----------------------------------------------------------------------------
#  Какие модели можно выбрать
# ----------------------------------------------------------------------------

def ollama_running():
    """Отвечает ли Ollama (она нужна всегда: через неё ищутся материалы в базе)."""
    try:
        return requests.get(pomoshnik.OLLAMA_URL, timeout=3).ok
    except requests.RequestException:
        return False


def model_choices():
    """[(ключ, подпись)] — локальные модели Ollama и модели через интернет."""
    choices = []
    try:
        tags = requests.get(f"{pomoshnik.OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        for m in sorted(tags, key=lambda m: m["name"]):
            name = m["name"]
            if name.split(":")[0] in (pomoshnik.EMBEDDING_MODEL, "bge-m3") or "embed" in name:
                continue  # модели для поиска, а не для ответов
            choices.append((f"ollama|{name}", f"{name} — на этом компьютере"))
    except (requests.RequestException, ValueError):
        pass
    if not any(key == f"ollama|{pomoshnik.CHAT_MODEL}" for key, _ in choices):
        choices.insert(0, (f"ollama|{pomoshnik.CHAT_MODEL}", f"{pomoshnik.CHAT_MODEL} — на этом компьютере"))
    choices.append((f"gigachat|{pomoshnik.GIGACHAT_MODEL}", f"ГигаЧат ({pomoshnik.GIGACHAT_MODEL}) — через интернет"))
    if pomoshnik.DEEPSEEK_KEY_FILE.exists():
        choices.append((f"deepseek|{pomoshnik.DEEPSEEK_MODEL}",
                        f"DeepSeek ({pomoshnik.DEEPSEEK_MODEL}) — через интернет"))
    return choices


def current_choice():
    return f"{pomoshnik.CHAT_PROVIDER}|{pomoshnik.model_name()}"


def apply_choice(key):
    """Переключает pomoshnik на выбранную модель."""
    provider, name = key.split("|", 1)
    pomoshnik.CHAT_PROVIDER = provider
    if provider == "ollama":
        pomoshnik.CHAT_MODEL = name
    elif provider == "gigachat":
        pomoshnik.GIGACHAT_MODEL = name
    elif provider == "deepseek":
        pomoshnik.DEEPSEEK_MODEL = name


def problem_hint():
    """Объясняет сотруднику, почему помощник не ответил."""
    if not ollama_running():
        return ("Ollama не запущена или зависла, поэтому помощник не может ответить (через Ollama "
                "ищутся сведения в базе — даже когда отвечает ГигаЧат). Запустите Ollama (меню «Пуск» → "
                "Ollama; если значок ламы уже есть возле часов — правой кнопкой → Quit Ollama "
                "и запустите снова). Окно перезапускать не нужно — просто задайте вопрос ещё раз.")
    if pomoshnik.CHAT_PROVIDER != "ollama":
        return ("Модель через интернет не ответила: проверьте интернет и ключ. Подробности — в файле "
                f"«data\\{LOG_FILE.name}». Можно выбрать локальную модель в списке сверху.")
    return (f"Ollama работает, но помощник выдал ошибку. Подробности — в файле «data\\{LOG_FILE.name}». "
            "Попробуйте задать вопрос ещё раз.")


# ----------------------------------------------------------------------------
#  Окно
# ----------------------------------------------------------------------------

def text_with_links(text):
    """Делит текст на обычные кусочки и ссылки, чтобы ссылки можно было нажимать."""
    spans, position = [], 0
    for match in URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(".,;:!?)")
        if match.start() > position:
            spans.append(ft.TextSpan(text[position:match.start()]))
        spans.append(ft.TextSpan(url, url=url, style=ft.TextStyle(
            color=LINK, decoration=ft.TextDecoration.UNDERLINE)))
        position = match.start() + len(url)
    if position < len(text):
        spans.append(ft.TextSpan(text[position:]))
    return spans


def background_notes():
    """Полупрозрачные ноты, рассыпанные по фону чата (каждый раз на тех же местах)."""
    rnd = random.Random(7)
    notes = []
    for _ in range(BACKGROUND_NOTES):
        notes.append(ft.Container(
            content=ft.Text(rnd.choice("♪♫♩♬"), size=rnd.randint(16, 44), color=ACCENT),
            left=rnd.randint(0, WINDOW_WIDTH - 80), top=rnd.randint(0, WINDOW_HEIGHT - 260),
            opacity=round(rnd.uniform(0.05, 0.13), 2), rotate=ft.Rotate(angle=rnd.uniform(-0.5, 0.5))))
    return notes


def logo():
    """Логотип филармонии в шапке; если файла нет — название текстом."""
    try:
        return ft.Image(src=LOGO_FILE.read_bytes(), height=40, fit=ft.BoxFit.CONTAIN)
    except OSError:
        return ft.Text(TITLE, size=18, weight=ft.FontWeight.BOLD, color=TEXT)


def bubble_width(text):
    """Короткому сообщению — узкое облачко, длинному — не шире BUBBLE_MAX_WIDTH."""
    longest = max((len(line) for line in text.splitlines()), default=1)
    return min(BUBBLE_MAX_WIDTH, max(60, longest * 8 + 32))


def main(page: ft.Page):
    page.title = TITLE
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG
    page.padding = 0
    page.window.width = WINDOW_WIDTH
    page.window.height = WINDOW_HEIGHT

    state = {"assistant": None, "busy": True, "dialog": Dialog(), "choice": current_choice()}

    chat_column = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, auto_scroll=True, expand=True)
    status_text = ft.Text("♪ Настраиваю инструменты: загружаю афишу…", color=MUTED, size=13)
    status_row = ft.Row([ft.ProgressRing(width=16, height=16, stroke_width=2, color=ACCENT), status_text],
                        spacing=8)

    def add_message(text, who="bot", note=""):
        """who: "user" — зритель, "bot" — помощник, "note" — подсказка для сотрудника."""
        is_user = who == "user"
        bubble = ft.Container(
            content=ft.Text(spans=text_with_links(text), color=TEXT, size=14, selectable=True),
            bgcolor={"user": USER_BG, "bot": BOT_BG, "note": NOTE_BG}[who],
            padding=12,
            width=bubble_width(text),
            border_radius=ft.BorderRadius.only(
                top_left=14, top_right=14,
                bottom_left=14 if is_user else 4,
                bottom_right=4 if is_user else 14),
        )
        column = [bubble] + ([ft.Text(note, color=MUTED, size=11)] if note else [])
        row = [ft.Column(column, spacing=3,
                         horizontal_alignment=ft.CrossAxisAlignment.END if is_user
                         else ft.CrossAxisAlignment.START)]
        if who == "bot":  # у помощника — золотой кружок с нотой
            row.insert(0, ft.CircleAvatar(content=ft.Text("♪", size=16, weight=ft.FontWeight.BOLD),
                                          bgcolor=ACCENT, color=BG, radius=15))
        elif who == "note":
            row.insert(0, ft.CircleAvatar(content=ft.Text("!", size=15, weight=ft.FontWeight.BOLD),
                                          bgcolor=NOTE_BG, color=ACCENT, radius=15))
        chat_column.controls.append(ft.Row(
            row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.START,
            alignment=ft.MainAxisAlignment.END if is_user else ft.MainAxisAlignment.START))

    def set_busy(busy, text=""):
        state["busy"] = busy
        status_text.value = text
        status_row.visible = busy
        send_button.disabled = busy
        model_select.disabled = busy
        page.update()

    def focus_input():
        page.run_task(message_input.focus)  # в flet 1.x «поставить курсор» — асинхронная команда

    def send(e=None):
        question = (message_input.value or "").strip()
        if not question or state["busy"] or state["assistant"] is None:
            return
        message_input.value = ""
        add_message(question, "user")
        set_busy(True, "♪ Сочиняю ответ…")
        page.run_thread(answer, question)

    def answer(question):
        started = time.monotonic()
        replies, ok = state["dialog"].answer(state["assistant"], question)
        seconds = time.monotonic() - started
        who = pomoshnik.model_name()
        if getattr(state["assistant"], "fallback_used", False):
            # Фильтр «чувствительных тем» ГигаЧата не пропустил вопрос — ответила запасная модель
            who = f"{pomoshnik.CHAT_MODEL} (ГигаЧат не ответил: «чувствительная тема»)"
            log(f"ГигаЧат отказался (чувствительная тема), ответила {pomoshnik.CHAT_MODEL}: {question[:200]}")
        note = f"♪ {who} · {seconds:.0f} сек." if seconds >= 1 else ""
        for i, reply in enumerate(replies):
            add_message(reply, "bot", note if i == len(replies) - 1 else "")
        if not replies:
            add_message("Помощник молчит: разговор прекращён из-за грубости. "
                        "Нажмите «Новый разговор», чтобы начать заново.", "note")
        if not ok:
            add_message("Подсказка для сотрудника: " + problem_hint(), "note")
        set_busy(False)
        focus_input()

    def new_conversation(e=None):
        if state["busy"]:
            return
        state["dialog"].reset()
        chat_column.controls.clear()
        add_message(pravila.reply("приветствие"))
        page.update()
        focus_input()

    def change_model(e):
        key = model_select.value
        if state["busy"] or key == state["choice"]:
            return
        set_busy(True, "♪ Меняю солиста: подключаю другую модель…")
        page.run_thread(switch_model, key)

    def switch_model(key):
        previous = state["choice"]
        apply_choice(key)
        try:
            state["assistant"] = pomoshnik.Assistant(store=state["assistant"].store)
            state["choice"] = key
            model_text.value = f"· отвечает {pomoshnik.model_name()}"
            add_message(f"Теперь отвечает {pomoshnik.model_name()}. Разговор продолжается.", "note")
            log(f"Модель сменена: {pomoshnik.model_name()} ({pomoshnik.CHAT_PROVIDER}).")
        except Exception as ex:
            apply_choice(previous)
            model_select.value = previous
            add_message(f"Не получилось подключить эту модель.\n\n{ex}", "note")
        set_busy(False)
        focus_input()

    def load():
        try:
            state["assistant"] = pomoshnik.Assistant()
        except Exception as ex:
            if pomoshnik.CHAT_PROVIDER == "ollama":
                status_row.visible = False
                add_message(f"Не получилось запустить помощника.\n\n{ex}\n\nПроверьте, что собран "
                            "индекс («update_afisha.bat»), и откройте окно заново.", "note")
                page.update()
                return
            # Модель через интернет не подключилась — открываемся на локальной
            add_message(f"Не получилось подключить {pomoshnik.model_name()}: {ex}\n\n"
                        f"Открываю окно с локальной моделью {pomoshnik.CHAT_MODEL}.", "note")
            apply_choice(f"ollama|{pomoshnik.CHAT_MODEL}")
            state["choice"] = model_select.value = current_choice()
            state["assistant"] = pomoshnik.Assistant()
        model_text.value = f"· отвечает {pomoshnik.model_name()}"
        log(f"Окно открыто, отвечает: {pomoshnik.model_name()} ({pomoshnik.CHAT_PROVIDER}).")
        add_message(pravila.reply("приветствие"))
        if not ollama_running():
            add_message("Подсказка для сотрудника: " + problem_hint(), "note")
        set_busy(False)
        focus_input()
        if DEMO["questions"] or DEMO["model"]:
            run_demo()

    def run_demo():
        """Демо-режим: окно само меняет модель и задаёт вопросы (для показа и скриншотов)."""
        if DEMO["model"]:
            model_select.value = DEMO["model"]
            set_busy(True, "♪ Меняю солиста: подключаю другую модель…")
            switch_model(DEMO["model"])
        for question in DEMO["questions"]:
            message_input.value = question
            send()
            while state["busy"]:
                time.sleep(0.3)
            time.sleep(0.5)
        log("Демо: все вопросы заданы.")

    message_input = ft.TextField(
        hint_text="Спросите о концертах, билетах, залах…",
        hint_style=ft.TextStyle(color=MUTED),
        text_style=ft.TextStyle(color=TEXT),
        fill_color=PANEL, filled=True, expand=True,
        shift_enter=True, min_lines=1, max_lines=5,
        on_submit=send,
        border_color=PANEL, focused_border_color=ACCENT,
    )
    send_button = ft.IconButton(icon=ft.Icons.SEND_ROUNDED, icon_color=ACCENT,
                                tooltip="Отправить (Enter)", on_click=send, disabled=True)
    model_text = ft.Text("", size=12, color=MUTED)
    model_select = ft.Dropdown(
        options=[ft.DropdownOption(key=key, text=label) for key, label in model_choices()],
        value=state["choice"], width=330, dense=True, text_size=13, disabled=True,
        color=TEXT, bgcolor=PANEL, border_color=MUTED, on_select=change_model,
        label="Кто отвечает")

    header = ft.Container(
        content=ft.Row([
            ft.Column([logo(), ft.Row([ft.Text("Помощник зрителя", size=12, color=TEXT), model_text],
                                      spacing=10)],
                      spacing=6, expand=True),
            model_select,
            ft.TextButton("Новый разговор", icon=ft.Icons.REFRESH, on_click=new_conversation,
                          style=ft.ButtonStyle(color=ACCENT)),
        ], spacing=16),
        bgcolor=PANEL, padding=ft.Padding.symmetric(horizontal=16, vertical=12),
        border=ft.Border.only(bottom=ft.BorderSide(width=1, color=ACCENT)),
    )

    # Чат поверх фона с нотами
    chat_area = ft.Stack([
        *background_notes(),
        ft.Container(content=ft.Column([chat_column, status_row], expand=True),
                     left=0, top=0, right=0, bottom=0),
    ], expand=True)

    page.add(ft.Column([
        header,
        ft.Container(content=chat_area, expand=True, padding=20),
        ft.Container(content=ft.Row([message_input, send_button], spacing=10), bgcolor=PANEL, padding=16),
    ], expand=True, spacing=0))

    page.run_thread(load)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # Демо-режим для показа: okno.py --model "ollama|gemma3:4b" --demo "Вопрос 1" "Вопрос 2"
    args = sys.argv[1:]
    if "--model" in args:
        DEMO["model"] = args[args.index("--model") + 1]
    if "--demo" in args:
        DEMO["questions"] = [a for a in args[args.index("--demo") + 1:] if not a.startswith("--")]
    ft.run(main)
