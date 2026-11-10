# -*- coding: utf-8 -*-
"""
ЧТЕНИЕ ПРАВИЛ ИЗ ПАПКИ «rules»
================================

Все тексты, которые определяют поведение помощника, лежат в папке «rules»
обычными текстовыми файлами — их можно править в Блокноте без программирования:

  system_prompt.txt — как модель говорит и что ей можно (системный промпт);
  ready_replies.txt        — приветствие, ответы на грубость, тревожные сообщения;
  help_phones.txt          — телефоны для человека, которому плохо.

Файлы читаются заново при каждом использовании, поэтому правки действуют сразу.
Строки, которые начинаются с «#», — пояснения, программа их пропускает.
"""

import re
from pathlib import Path

RULES_FOLDER = Path(__file__).resolve().parent.parent / "rules"
INSTRUCTION_FILE = RULES_FOLDER / "system_prompt.txt"
REPLIES_FILE = RULES_FOLDER / "ready_replies.txt"
PHONES_FILE = RULES_FOLDER / "help_phones.txt"


def read_lines(path):
    """Строки файла без пояснений «#…»."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise FileNotFoundError(f"Нет файла правил «{path.name}» в папке «{RULES_FOLDER.name}».")
    return [line.rstrip() for line in text.splitlines() if not line.lstrip().startswith("#")]


QUESTIONS_FILE = RULES_FOLDER / "clarifying_questions.txt"


def instruction():
    """Инструкция для модели (системный промпт) + уточняющие вопросы, если файл есть."""
    text = "\n".join(read_lines(INSTRUCTION_FILE)).strip()
    if QUESTIONS_FILE.exists():
        text += "\n\n" + "\n".join(read_lines(QUESTIONS_FILE)).strip()
    return text


EXAMPLE_FILE = RULES_FOLDER / "answer_example.txt"


def example():
    """
    Образец разговора для модели: (сведения, вопрос, ответ) или None, если образца нет.
    Модели легче перенять манеру из примера, чем выполнить список запретов.
    """
    try:
        lines = read_lines(EXAMPLE_FILE)
    except FileNotFoundError:
        return None
    parts, current = {}, None
    for line in lines:
        header = re.fullmatch(r"\s*\[(.+?)\]\s*", line)
        if header:
            current = header.group(1).strip().lower()
            parts[current] = []
        elif current:
            parts[current].append(line)
    texts = {k: "\n".join(v).strip() for k, v in parts.items()}
    if not all(texts.get(k) for k in ("сведения", "вопрос", "ответ")):
        return None
    return texts["сведения"], texts["вопрос"], texts["ответ"]


ALIASES_FILE = RULES_FOLDER / "collective_aliases.txt"


def collective_aliases():
    """{точное название коллектива: [как его называют зрители, …]} из collective_aliases.txt."""
    result = {}
    try:
        lines = read_lines(ALIASES_FILE)
    except FileNotFoundError:
        return result
    for line in lines:
        if "=" not in line:
            continue
        name, names = line.split("=", 1)
        result[name.strip()] = [n.strip() for n in names.split(",") if n.strip()]
    return result


def phones():
    """Телефоны помощи — по одному в строке."""
    return [line.strip() for line in read_lines(PHONES_FILE) if line.strip()]


def reply(name, **values):
    """
    Готовый ответ по названию из «ready_replies.txt»: reply("приветствие").
    Вместо {телефоны} и других слов в фигурных скобках подставляются значения.
    """
    sections, current = {}, None
    for line in read_lines(REPLIES_FILE):
        header = re.fullmatch(r"\s*\[(.+?)\]\s*", line)
        if header:
            current = header.group(1).strip().lower()
            sections[current] = []
        elif current:
            sections[current].append(line)
    if name not in sections:
        raise KeyError(f"В файле «{REPLIES_FILE.name}» нет ответа [{name}].")
    text = "\n".join(sections[name]).strip()
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


if __name__ == "__main__":
    # Проверка: показать, как программа видит правила
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(instruction()[:300], "…\n")
    for name in ("приветствие", "заново", "не получилось ответить", "грубость 1", "грубость 2",
                 "грубость прощание", "угроза"):
        print(f"[{name}] {reply(name)[:80]}…")
    print("[зрителю плохо]", reply("зрителю плохо", телефоны="\n".join("— " + p for p in phones())))
