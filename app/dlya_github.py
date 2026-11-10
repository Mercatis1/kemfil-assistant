# -*- coding: utf-8 -*-
"""
ЧИСТАЯ КОПИЯ ПРОЕКТА ДЛЯ GITHUB
===============================

Создаёт рядом с папкой бота папку «kemfil-assistant» — копию проекта, которую можно
спокойно выкладывать в интернет:
  - ключи (ГигаЧат, DeepSeek, ВКонтакте) заменены пустыми шаблонами с пояснениями;
  - нет журналов, ответов проверок, папки .venv и служебных файлов;
  - в конце программа проверяет каждый файл копии: если где-то всё же нашёлся настоящий
    ключ, копия удаляется, и программа сообщает, в каком файле была проблема.

Запуск: «prepare_github.bat» в папке бота.
Выкладывать на GitHub нужно папку «kemfil-assistant», а не саму папку бота.
"""

import os
import re
import shutil
import sys
from pathlib import Path

BOT_FOLDER = Path(__file__).resolve().parent.parent
COPY_FOLDER = BOT_FOLDER.parent / "kemfil-assistant"   # латинское имя — как у репозитория
MARKER = ".created_by_prepare_github"   # чтобы случайно не удалить чужую папку

# Что не копируем (пути — от папки бота, «*» — любые символы)
SKIP = [
    ".venv", "__pycache__", "*.pyc", "~$*",             # служебное
    "data/*_log.txt", "data/concerts_new",            # журналы и временные файлы
]
KEY_FILES = "keys/*_key.txt"                            # ключи — заменяем шаблонами
KEY_LOOKING = [                                          # на что похожи ключи
    re.compile(r"vk1\.a\.[\w-]{20,}"),                   # ВКонтакте
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),                # DeepSeek и похожие
    re.compile(r"\b[A-Za-z0-9+/]{60,}={0,2}"),           # ключ авторизации ГигаЧата (base64)
]


def skipped(relative):
    rel = relative.as_posix()
    return any(Path(rel).match(pattern) or rel == pattern or rel.startswith(pattern + "/")
               or any(part == pattern for part in relative.parts) for pattern in SKIP)


def real_keys():
    """Настоящие ключи из папки «keys» — чтобы убедиться, что их нет в копии."""
    keys = []
    for file in BOT_FOLDER.glob(KEY_FILES):
        for line in file.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and len(line) >= 16:
                keys.append(line)
    return keys


def key_template(file):
    """Шаблон файла ключа: только строки-пояснения, без самого ключа."""
    lines = [l for l in file.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
             if l.strip().startswith("#")]
    if not lines:
        lines = [f"# Вставьте сюда ключ (файл {file.name}) одной строкой. Ключ — секрет, не выкладывайте его."]
    return "\n".join(lines) + "\n\n"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if COPY_FOLDER.exists():
        if not (COPY_FOLDER / MARKER).exists():
            print(f"Папка «{COPY_FOLDER.name}» уже есть, но создана не этой программой.")
            print("Переименуйте или удалите её сами и запустите снова.")
            sys.exit(1)
        shutil.rmtree(COPY_FOLDER)

    copied, templated = 0, 0
    for path in sorted(BOT_FOLDER.rglob("*")):
        relative = path.relative_to(BOT_FOLDER)
        if skipped(relative) or path.is_dir():
            continue
        target = COPY_FOLDER / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.match(KEY_FILES):
            target.write_text(key_template(path), encoding="utf-8")
            templated += 1
        else:
            shutil.copy2(path, target)
            copied += 1
    (COPY_FOLDER / MARKER).write_text("Эту папку создаёт «prepare_github.bat».\n", encoding="utf-8")

    # Проверка: нет ли в копии настоящих ключей или чего-то похожего на ключ
    keys = real_keys()
    problems = []
    for file in COPY_FOLDER.rglob("*"):
        if not file.is_file() or file.suffix.lower() not in (".py", ".txt", ".md", ".bat", ".json", ".cfg", ".ini", ""):
            continue
        if file.stat().st_size > 5_000_000:  # большой индекс — только поиск настоящих ключей
            text = file.read_text(encoding="utf-8", errors="ignore")
            if any(k in text for k in keys):
                problems.append(file)
            continue
        text = file.read_text(encoding="utf-8", errors="ignore")
        if any(k in text for k in keys) or (
                file.suffix.lower() == ".txt" and file.parent.name == "keys"
                and any(p.search(text) for p in KEY_LOOKING)):
            problems.append(file)

    if problems:
        shutil.rmtree(COPY_FOLDER, ignore_errors=True)
        print("ОСТАНОВЛЕНО: в этих файлах найден ключ — копия удалена, выкладывать нечего:")
        for f in problems:
            print("  -", f.relative_to(COPY_FOLDER))
        print("Уберите ключ из этих файлов (ключи должны лежать только в папке «keys») и запустите снова.")
        sys.exit(1)

    print(f"Готово: скопировано файлов — {copied}, ключи заменены шаблонами — {templated}.")
    print("Проверка пройдена: настоящих ключей в копии нет.")
    print(f"Выкладывайте на GitHub эту папку: {COPY_FOLDER}")
    try:
        if not os.environ.get("NO_OPEN_FOLDER"):
            os.startfile(COPY_FOLDER)  # открыть папку в Проводнике
    except Exception:
        pass


if __name__ == "__main__":
    main()
