# -*- coding: utf-8 -*-
"""
«БИБЛИОТЕКАРЬ»: ПОДГОТОВКА БАЗЫ К ПОИСКУ
========================================

Что делает программа:
  1. Читает файлы, которые собрал сборщик (папки «data/concerts», «data/info» и «data/collectives»).
  2. Каждый концерт превращает в одну «карточку», длинные страницы для зрителей
     режет на небольшие кусочки.
  3. Для каждой карточки и кусочка просит модель bge-m3 (в Ollama) вычислить
     «отпечаток смысла» — набор чисел, по которому потом ищутся похожие тексты.
  4. Сохраняет всё в один файл «data/index.json». Его читает консультант.

Запускать после каждого сбора афиши:
  .venv\\Scripts\\python.exe collector\\indeksator.py
"""

# ============================================================================
#  НАСТРОЙКИ
# ============================================================================

from pathlib import Path

# Папки с текстами (их заполняет сборщик sborshik.py)
PROGRAM_FOLDER = Path(__file__).resolve().parent.parent  # папка бота (эта программа лежит в её подпапке)
BASE_FOLDER = PROGRAM_FOLDER / "data"
CONCERTS_FOLDER = BASE_FOLDER / "concerts"
INFO_FOLDER = BASE_FOLDER / "info"
PEOPLE_FOLDER = BASE_FOLDER / "collectives"

# Куда сохранить готовый индекс
INDEX_FILE = BASE_FOLDER / "index.json"

# Список людей (дирижёры, руководители, солисты) с их ролями и концертами
PEOPLE_FILE = BASE_FOLDER / "people.json"

# Роли, которые означают «руководит коллективом» — тогда все концерты коллектива
# считаются концертами этого человека (кроме экскурсий)
LEADING_ROLES = ("главный дирижер", "главный дирижёр", "художественный руководитель",
                 "главный балетмейстер")

# Роли, которые не относятся к выступлениям — такие люди в список не попадают
SKIP_ROLES = ("директор",)

# Должности из состава коллектива, с которыми человек не выходит на сцену. Такой человек
# попадает в список («кто директор хора?»), но концерты коллектива ему не приписываются.
# «Директор, концертмейстер» — выходит на сцену (концертмейстер).
NON_STAGE_ROLES = ("директор", "администратор", "заведующ", "менеджер", "инспектор",
                   "звукорежисс", "художник", "костюмер", "помощник", "специалист")

# Адрес Ollama на этом компьютере (обычно менять не нужно)
OLLAMA_URL = "http://localhost:11434"

# Модель для «отпечатков смысла». Её нужно один раз скачать: ollama pull bge-m3
EMBEDDING_MODEL = "bge-m3"

# Сколько символов описания концерта брать в карточку. Длинные биографии артистов
# мешают поиску и не нужны для ответов зрителям.
CONCERT_DESCRIPTION_LIMIT = 1200

# Примерный размер кусочка постоянной страницы, в символах
INFO_CHUNK_SIZE = 700

# ============================================================================
#  ДАЛЬШЕ — САМА ПРОГРАММА
# ============================================================================

import os
os.environ.setdefault("HAYSTACK_TELEMETRY_ENABLED", "False")  # не отправлять статистику

import json
import re
import sys
import time

try:
    from haystack import Document, Pipeline
    from haystack.components.writers import DocumentWriter
    from haystack.document_stores.in_memory import InMemoryDocumentStore
    from haystack_integrations.components.embedders.ollama import OllamaDocumentEmbedder
except ImportError:
    print("Не найдены библиотеки Haystack. Запускайте через окружение проекта:")
    print("  .venv\\Scripts\\python.exe collector\\indeksator.py")
    sys.exit(1)


def shorten(text, limit):
    """Обрезает текст по границе предложения, не длиннее limit символов."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("\n"))
    return (cut[: end + 1] if end > limit // 2 else cut).rstrip() + " …"


def read_concert(file):
    """Читает файл концерта: поля сверху («Название: …») и описание."""
    lines = file.read_text(encoding="utf-8").splitlines()
    fields, description = {}, []
    in_description = False
    for line in lines:
        if in_description:
            description.append(line)
        elif line.startswith("Описание:"):
            in_description = True
        elif ": " in line:
            key, value = line.split(": ", 1)
            fields[key.strip()] = value.strip()

    header = "\n".join(f"{k}: {v}" for k, v in fields.items())
    text = shorten("\n".join(description).strip(), CONCERT_DESCRIPTION_LIMIT)
    content = header + "\nОписание:\n" + (text or "не указано")

    return Document(
        content=content,
        meta={
            "type": "концерт",
            "date": file.name[:10],  # имя файла начинается с даты: 2026-11-05_...
            "title": fields.get("Название", ""),
            "when": fields.get("Дата и время", ""),
            "hall": fields.get("Зал", ""),
            "age": fields.get("Возраст", ""),
            "price": fields.get("Цена", ""),
            "status": fields.get("Статус", ""),
            "url": fields.get("Страница концерта", ""),
            "file": file.name,
        },
    )


def read_info_page(file):
    """Читает постоянную страницу и режет её на кусочки примерно по INFO_CHUNK_SIZE символов."""
    lines = file.read_text(encoding="utf-8").splitlines()
    url, body = (lines[0], lines[1:]) if lines else ("", [])
    # Русское название страницы — во 2-й строке «Страница: Контакты» (имя файла — латиницей)
    name = file.stem
    if body and body[0].startswith("Страница: "):
        name, body = body[0][len("Страница: "):].strip(), body[1:]

    chunks, current = [], []
    for line in body:
        if current and sum(len(x) for x in current) + len(line) > INFO_CHUNK_SIZE:
            chunks.append(current)
            current = current[-1:] if len(current[-1]) < 200 else []  # короткая строка-«мостик»
        current.append(line)
    if current:
        chunks.append(current)

    documents = []
    for number, chunk in enumerate(chunks, 1):
        documents.append(Document(
            content=f"Страница сайта: {name}\n" + "\n".join(chunk),
            meta={"type": "info", "page": name, "url": url, "part": number, "file": file.name},
        ))
    return documents


# ----------------------------------------------------------------------------
#  Люди: кто чем руководит и в каких концертах участвует
# ----------------------------------------------------------------------------

def name_stem(word):
    """Начало слова без окончания: «Шульгу» и «Шульга» → «шульг», «Василия» → «васил»."""
    word = word.lower().replace("ё", "е")
    if len(word) <= 3:
        return word
    if len(word) <= 5:
        return word[: len(word) - 1]  # «Линь» → «лин» (Линя), «Ганин» → «гани» (Ганина)
    return word[: max(5, len(word) - 2)]


def read_people_file(file):
    """Читает файл коллектива или артиста, который сохранил сборщик."""
    fields, roles, members, description, in_description = {}, [], [], [], False
    for line in file.read_text(encoding="utf-8").splitlines():
        if in_description:
            description.append(line)
        elif line.startswith("Описание:"):
            in_description = True
        elif line.startswith("Роль: "):
            parts = [p.strip() for p in line[len("Роль: "):].split("|")]
            roles.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
        elif line.startswith("Состав: "):
            parts = [p.strip() for p in line[len("Состав: "):].split("|")]
            members.append((parts[0], parts[1] if len(parts) > 1 else ""))
        elif ": " in line:
            key, value = line.split(": ", 1)
            fields[key] = value.strip()
    fields["roles"] = roles
    fields["members"] = members
    fields["description"] = "\n".join(description).strip()
    fields["concerts"] = [c.strip() for c in fields.get("Концерты", "").split(",") if c.strip()]
    return fields


def concert_role(sentence):
    """В какой роли человек упомянут в предложении из описания концерта."""
    s = sentence.lower().replace("ё", "е")
    if re.search(r"дириж|под управлением|за пультом", s):
        return "дирижирует (сказано в описании концерта)"
    if re.search(r"руковод|постановщик|постановк|хореограф|балетмейстер|режисс", s):
        return "указан руководителем или постановщиком (сказано в описании концерта)"
    if re.search(r"солист|исполн|выступ|при участии|прозвуч|за органом|вокал|споет|сыграет|музыковед|ведущ"
                 r"|сопрано|баритон|тенор|меццо|бас\b|орган|фортепиано|роял|скрипк|подарит|сольн", s):
        return "выступает (сказано в описании концерта)"
    return "упоминается в описании концерта"


def build_people(people_files, concert_files):
    """Составляет список людей: роли в коллективах и концерты, где они участвуют."""
    people = {}  # ключ — адрес личной страницы или имя

    def same_person(a, b):
        """«Ирина Латынникова» и «Ирина Николаевна Латынникова» — один человек."""
        a, b = a.lower().replace("ё", "е").split(), b.lower().replace("ё", "е").split()
        return len(a) >= 2 and len(b) >= 2 and a[0] == b[0] and a[-1] == b[-1]

    def person_entry(name, url=""):
        key = url or name
        if key not in people:
            # Тот же человек мог уже попасть в список под другим ключом (с личной страницей
            # или из другого коллектива) — тогда дописываем к нему, а не заводим двойника
            twin = next((k for k, p in people.items() if same_person(p["name"], name)
                         and (not url or not p["url"] or p["url"] == url)), None)
            if twin is not None:
                key = twin
            else:
                people[key] = {"name": name, "url": url, "specialty": "", "about": "",
                               "roles": [], "concerts": []}
        if len(name.split()) > len(people[key]["name"].split()):
            people[key]["name"] = name  # полное имя с отчеством лучше короткого
        if url and not people[key]["url"]:
            people[key]["url"] = url
        return people[key]

    files = [read_people_file(f) for f in people_files]
    for f in files:  # сначала артисты — у них полные имена
        if f.get("Тип") == "артист":
            p = person_entry(f.get("Название", ""), f.get("Страница", ""))
            p["specialty"] = f.get("Специальность", "")
            p["about"] = f["description"][:600]
    for f in files:  # потом роли в коллективах
        if f.get("Тип") != "коллектив":
            continue
        for role, name, url in f["roles"]:
            if role.lower().startswith(SKIP_ROLES):
                continue
            p = person_entry(name, url)
            leads = role.lower() in LEADING_ROLES
            others = [f"{r.lower()} — {n}" for r, n, _ in f["roles"]
                      if n != name and r.lower() in LEADING_ROLES]
            p["roles"].append({"role": role, "collective": f.get("Название", ""),
                               "collective_url": f.get("Страница", ""), "leads": leads,
                               "concert_ids": f["concerts"] if leads else [],
                               "others": others})

        # Состав коллектива (вкладка «Состав» на сайте): все артисты, а не только руководители.
        # Концерты коллектива даём каждому, кто выходит на сцену, с пометкой «в составе» —
        # кто именно занят в конкретном концерте или спектакле, сайт не пишет.
        leaders = [f"{r.lower()} — {n}" for r, n, _ in f["roles"] if r.lower() in LEADING_ROLES]
        for name, role in f.get("members", []):
            p = person_entry(name)
            if any(r["collective"] == f.get("Название", "") for r in p["roles"]):
                continue  # уже записан как руководитель этого коллектива
            on_stage = any(not part.strip().startswith(NON_STAGE_ROLES)
                           for part in role.lower().split(",") if part.strip()) or not role
            p["roles"].append({"role": role or "артист", "collective": f.get("Название", ""),
                               "collective_url": f.get("Страница", ""), "leads": False,
                               "member": True, "on_stage": on_stage,
                               "concert_ids": f["concerts"] if on_stage else [],
                               "others": [x for x in leaders if not x.endswith(name)]})

    # Какой коллектив играет в каком концерте (по спискам концертов на страницах коллективов)
    concert_collectives = {}
    for f in files:
        if f.get("Тип") == "коллектив":
            for cid in f["concerts"]:
                concert_collectives.setdefault(cid, []).append(f.get("Название", ""))

    # Где человек упомянут в описаниях концертов (по полному тексту, не обрезанному)
    surnames = {}
    for p in people.values():
        words = p["name"].split()
        if words:
            surnames.setdefault(name_stem(words[-1]), []).append(p)
    for file in concert_files:
        text = file.read_text(encoding="utf-8")
        concert_id = re.search(r"concert\?id=(\d+)", text)
        if not concert_id or "Описание:" not in text:
            continue
        description = text.split("Описание:", 1)[1]
        # Название тоже проверяем: «Сольный концерт Натальи Кузнецовой» — имя есть только там
        title = re.search(r"^Название: (.*)$", text, re.M)
        sentences = [("ЗАГОЛОВОК", title.group(1))] if title else []
        sentences += [("", s) for s in re.split(r"(?<=[.!?…])\s+|\n", description)]
        for kind, sentence in sentences:
            original = re.findall(r"[А-Яа-яЁё]+", sentence)
            words = [w.lower().replace("ё", "е") for w in original]
            # Фамилия засчитывается, только если написана с большой буквы
            # (иначе «музыка» сошла бы за «Музыкову»)
            capitalized = [w for w, o in zip(words, original) if o[:1].isupper()]
            for stem, candidates in surnames.items():
                if not any(w.startswith(stem) for w in capitalized):
                    continue
                for p in candidates:
                    first = name_stem(p["name"].split()[0])
                    # В том же предложении должно быть и имя: «Ольга Музыкова», «Василия Шульги».
                    # Так отсекаются однофамильцы (Василий и Елизавета Шульга) и случайные совпадения.
                    if not any(w.startswith(first) for w in capitalized):
                        continue
                    if kind == "ЗАГОЛОВОК":
                        how = ("выступает — сольный концерт (имя в названии концерта)"
                               if "сольн" in sentence.lower() else "выступает (имя в названии концерта)")
                    else:
                        how = concert_role(sentence)
                    # Если концерт уже записан с более слабой причиной («упоминается») — усиливаем
                    existing = next((c for c in p["concerts"] if c["id"] == concert_id.group(1)), None)
                    if existing is None:
                        p["concerts"].append({"id": concert_id.group(1), "how": how,
                                              "collectives": concert_collectives.get(concert_id.group(1), [])})
                    elif ROLE_STRENGTH.get(how.split()[0], 9) < ROLE_STRENGTH.get(existing["how"].split()[0], 9):
                        existing["how"] = how
    return list(people.values())


# Чем меньше число, тем важнее причина (как в pomoshnik.py)
ROLE_STRENGTH = {"дирижирует": 0, "выступает": 2, "указан": 3, "упоминается": 4}


def read_collective_document(file):
    """Карточка коллектива или артиста для общего поиска («кто дирижёр хора?»)."""
    f = read_people_file(file)
    lines = [f"{'Коллектив' if f.get('Тип') == 'коллектив' else 'Артист'} филармонии: {f.get('Название', '')}"]
    if f.get("Специальность"):
        lines.append(f"Специальность: {f['Специальность']}")
    for role, name, _ in f["roles"]:
        lines.append(f"{role}: {name}")
    if f.get("members"):
        lines.append("Состав коллектива (артисты): "
                     + "; ".join(f"{n} — {r.lower()}" if r else n for n, r in f["members"]))
    lines.append(f"Страница на сайте: {f.get('Страница', '')}")
    lines.append(f["description"][:900])
    return Document(content="\n".join(lines),
                    meta={"type": "коллектив", "page": f.get("Название", ""), "part": 1,
                          "url": f.get("Страница", ""), "file": file.name})


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    started = time.monotonic()

    concert_files = sorted(CONCERTS_FOLDER.glob("*.txt")) if CONCERTS_FOLDER.exists() else []
    info_files = sorted(INFO_FOLDER.glob("*.txt")) if INFO_FOLDER.exists() else []
    if not concert_files:
        print(f"В папке «{CONCERTS_FOLDER}» нет файлов. Сначала запустите сборщик: sborshik.py")
        sys.exit(1)

    documents = []
    for file in concert_files:
        try:
            documents.append(read_concert(file))
        except Exception as e:
            print(f"ОШИБКА: не удалось прочитать {file.name}: {e}")
    info_count = 0
    for file in info_files:
        try:
            parts = read_info_page(file)
            documents.extend(parts)
            info_count += len(parts)
        except Exception as e:
            print(f"ОШИБКА: не удалось прочитать {file.name}: {e}")

    people_files = sorted(PEOPLE_FOLDER.glob("*.txt")) if PEOPLE_FOLDER.exists() else []
    for file in people_files:
        try:
            documents.append(read_collective_document(file))
        except Exception as e:
            print(f"ОШИБКА: не удалось прочитать {file.name}: {e}")
    if people_files:
        # Один общий список «какие коллективы есть в филармонии» — иначе поиск находит
        # только 3–4 карточки и модель перечисляет коллективы не все
        cards = [read_people_file(f) for f in people_files]
        overview = [f"- {c.get('Название', '')}: "
                    + ("; ".join(f"{r.lower()} — {n}" for r, n, _ in c["roles"]) or "руководитель не указан")
                    + (f"; в составе {len(c['members'])} чел." if c.get("members") else "")
                    + f" — {c.get('Страница', '')}"
                    for c in cards if c.get("Тип") == "коллектив"]
        documents.append(Document(
            content="Коллективы филармонии Кузбасса (все творческие коллективы, полный список):\n"
                    + "\n".join(overview) + "\nВсе коллективы и артисты: https://www.kemfil.ru/collective",
            meta={"type": "коллектив", "page": "Коллективы филармонии", "part": 1,
                  "url": "https://www.kemfil.ru/collective", "file": "collectives_overview"}))
        people = build_people(people_files, concert_files)
        PEOPLE_FILE.write_text(json.dumps(people, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Людей в списке (дирижёры, руководители, артисты): {len(people)}")
    else:
        print("Папки «data/collectives» нет — поиск по дирижёрам и артистам будет недоступен.")

    print(f"Карточек концертов: {len(concert_files)}, кусочков постоянных страниц: {info_count}, "
          f"коллективов и артистов: {len(people_files)}")
    print(f"Вычисляю «отпечатки смысла» моделью {EMBEDDING_MODEL}...")

    store = InMemoryDocumentStore(embedding_similarity_function="cosine")
    pipeline = Pipeline()
    pipeline.add_component("embedder", OllamaDocumentEmbedder(
        model=EMBEDDING_MODEL, url=OLLAMA_URL, batch_size=16, progress_bar=True))
    pipeline.add_component("writer", DocumentWriter(document_store=store))
    pipeline.connect("embedder.documents", "writer.documents")

    try:
        pipeline.run({"embedder": {"documents": documents}})
    except Exception as e:
        print(f"\nОШИБКА: не получилось обратиться к Ollama ({e.__class__.__name__}: {e}).")
        print("Проверьте, что Ollama запущена и модель скачана командой: ollama pull " + EMBEDDING_MODEL)
        print("Старый индекс оставлен без изменений.")
        sys.exit(1)

    # Сохраняем во временный файл и только потом заменяем старый индекс
    temp_file = INDEX_FILE.with_suffix(".new.json")
    store.save_to_disk(str(temp_file))
    os.replace(temp_file, INDEX_FILE)

    print(f"\nГотово: в индексе {store.count_documents()} записей, файл «{INDEX_FILE.relative_to(PROGRAM_FOLDER)}».")
    print(f"Время работы: {time.monotonic() - started:.0f} сек.")


if __name__ == "__main__":
    main()
