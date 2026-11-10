# -*- coding: utf-8 -*-
"""
ГИГАЧАТ (СБЕР) ДЛЯ ПОМОЩНИКА
============================

Подключает ГигаЧат как «модель, которая пишет ответы» — вместо локальной модели Ollama.
Поиск по базе при этом всё равно идёт на этом компьютере (Ollama + bge-m3),
в ГигаЧат уходят только найденные сведения и сообщения зрителя.

Как это устроено (по документации developers.sber.ru):
  1. По «ключу авторизации» из личного кабинета программа получает временный пропуск
     (токен) на 30 минут; когда он кончается, берёт новый сам.
  2. С пропуском отправляет инструкцию, разговор и сведения в ГигаЧат и получает ответ.
  3. Сайты Сбера защищены российским сертификатом Минцифры — его файл лежит
     в папке «keys» (как его получить — в README).

Проверка подключения (ключ и сертификат на месте?):
  .venv\\Scripts\\python.exe app\\gigachat_api.py
"""

import re
import ssl
import time
import uuid
from pathlib import Path

import requests
from haystack import component
from haystack.dataclasses import ChatMessage


def prepare_cert(cert_file):
    """
    Путь к сертификату в том виде, который понимает программа (текстовый PEM).
    Если с Госуслуг скачан двоичный вариант (DER), рядом создаётся текстовая копия.
    """
    cert_file = Path(cert_file)
    if not cert_file.exists():
        raise FileNotFoundError(
            f"Нет сертификата Минцифры: «{cert_file.parent.name}\\{cert_file.name}». "
            "Без него не получится соединиться с ГигаЧатом. Скачайте «Корневой сертификат» "
            "с официальной страницы https://www.gosuslugi.ru/crt и сохраните его под этим именем.")
    data = cert_file.read_bytes()
    if b"BEGIN CERTIFICATE" in data:
        return str(cert_file)
    pem_file = cert_file.with_suffix(".pem")
    if not pem_file.exists():
        pem_file.write_text(ssl.DER_cert_to_PEM_cert(data), encoding="ascii")
    return str(pem_file)


# Слова, из-за которых фильтр «чувствительных тем» ГигаЧата отказывается отвечать.
# Фразы с ними убираются из справки при второй попытке (вопрос зрителя не меняется).
SENSITIVE_WORDS = re.compile(
    r"(?<![а-яА-Я])СВО(?![а-яА-Я])|специальн\w* военн\w* операц|боев\w* действ|Донбасс|Донецк|Луганск"
    r"|Украин|Херсон|Запорож|мобилизац|Министерств\w* обороны|«Героями не рождаются»", re.I)


@component
class GigaChatGenerator:
    """Компонент Haystack: принимает сообщения, возвращает ответ ГигаЧата."""

    def __init__(self, key_file, cert_file, model="GigaChat-2", scope="GIGACHAT_API_PERS",
                 auth_url="https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                 api_url="https://gigachat.devices.sberbank.ru/api/v1",
                 temperature=0.3, max_tokens=1500, timeout=120, fallback=None):
        """fallback — запасная модель (компонент Haystack), если ГигаЧат откажется отвечать."""
        self.fallback = fallback
        key_file = Path(key_file)
        try:
            # Строки с «#» — пояснения; ключ — первая строка без «#»
            lines = [line.strip() for line in key_file.read_text(encoding="utf-8-sig").splitlines()]
            self.key = next((line for line in lines if line and not line.startswith("#")), "")
        except OSError:
            self.key = ""
        if not self.key:
            raise FileNotFoundError(
                f"Нет ключа ГигаЧата. Откройте файл «{key_file.name}» в папке «{key_file.parent.name}» "
                "и вставьте в пустую строку «Ключ авторизации» из личного кабинета ГигаЧата.")
        self.verify = prepare_cert(cert_file)
        self.model, self.scope = model, scope
        self.auth_url, self.api_url = auth_url, api_url.rstrip("/")
        self.temperature, self.max_tokens, self.timeout = temperature, max_tokens, timeout
        self.session = requests.Session()
        self.token, self.token_until = "", 0.0

    def _get_token(self, force=False):
        """Временный пропуск на 30 минут; берём новый за минуту до конца."""
        if self.token and not force and time.time() < self.token_until - 60:
            return self.token
        response = self.session.post(
            self.auth_url, data={"scope": self.scope}, verify=self.verify, timeout=30,
            headers={"Authorization": f"Basic {self.key}", "RqUID": str(uuid.uuid4()),
                     "Accept": "application/json"})
        if response.status_code in (400, 401):
            raise PermissionError(
                "ГигаЧат не принял ключ авторизации. Проверьте файл с ключом (ключ целиком, "
                f"одной строкой) и тип доступа GIGACHAT_SCOPE = «{self.scope}» в pomoshnik.py. "
                f"Ответ сервера: {response.text[:200]}")
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        expires = float(data.get("expires_at", 0))
        if expires > 1e12:  # время может прийти в миллисекундах
            expires /= 1000
        self.token_until = expires or time.time() + 25 * 60
        return self.token

    def available_models(self):
        """Названия моделей, доступных по этому ключу."""
        response = self.session.get(
            f"{self.api_url}/models", verify=self.verify, timeout=30,
            headers={"Authorization": f"Bearer {self._get_token()}"})
        response.raise_for_status()
        return [m.get("id", "") for m in response.json().get("data", [])]

    @staticmethod
    def _to_api(messages):
        """Сообщения Haystack → формат ГигаЧата; подряд идущие реплики одной роли склеиваем."""
        result = []
        for m in messages:
            role, text = m.role.value, m.text or ""
            if result and result[-1]["role"] == role:
                result[-1]["content"] += "\n\n" + text
            else:
                result.append({"role": role, "content": text})
        return result

    @staticmethod
    def _soften(api_messages):
        """
        Копия запроса без предложений, на которые срабатывает фильтр ГигаЧата: СВО, Донбасс,
        боевые действия и т.п. Проверка показала: такие слова в описании концерта (например,
        «проект «Донбасс. Возрождение»») приводят к отказу даже на безобидный вопрос.
        Последнюю строку «Сообщение зрителя: …» не трогаем.
        """
        softened = []
        for m in api_messages:
            text = m["content"]
            if m["role"] == "user":
                head, sep, question = text.rpartition("Сообщение зрителя:")
                if not sep:
                    head, question = text, ""
                parts = re.split(r"(?<=[.!?…])\s+|\n", head)
                head = "\n".join(p for p in parts if not SENSITIVE_WORDS.search(p))
                text = head + (("\n\n" + sep + question) if sep else "")
            softened.append({"role": m["role"], "content": text})
        return softened

    def _post(self, body):
        for attempt in (1, 2):
            try:
                response = self.session.post(
                    f"{self.api_url}/chat/completions", json=body, verify=self.verify, timeout=self.timeout,
                    headers={"Authorization": f"Bearer {self._get_token(force=attempt == 2)}"})
            except requests.ConnectionError:
                # Сервер разорвал соединение (бывает после паузы) — пробуем ещё раз с новым соединением
                if attempt == 2:
                    raise
                self.session = requests.Session()
                continue
            if response.status_code != 401:  # 401 — пропуск устарел, берём новый и пробуем снова
                break
        return response

    @component.output_types(replies=list[ChatMessage])
    def run(self, messages: list[ChatMessage]):
        self.last_refused = False  # для журнала и окна: ответила ли запасная модель
        body = {"model": self.model, "messages": self._to_api(messages),
                "temperature": self.temperature, "max_tokens": self.max_tokens}
        response = self._post(body)
        self._check(response)
        choice = response.json()["choices"][0]
        text = choice["message"].get("content", "")
        refused = choice.get("finish_reason") == "blacklist" or "чувствительными темами" in text
        if refused:
            # Вторая попытка: тот же вопрос, но без «острых» фраз в справочных сведениях
            body["messages"] = self._soften(body["messages"])
            response = self._post(body)
            self._check(response)
            choice = response.json()["choices"][0]
            text = choice["message"].get("content", "")
            refused = choice.get("finish_reason") == "blacklist" or "чувствительными темами" in text
            if not refused:
                print("ГигаЧат ответил со второй попытки (без «острых» фраз в справке).", flush=True)
        if refused and self.fallback is not None:
            self.last_refused = True
            print("ГигаЧат отказался отвечать (фильтр «чувствительных тем») — отвечает запасная модель.",
                  flush=True)
            return self.fallback.run(messages=messages)
        return {"replies": [ChatMessage.from_assistant(text)]}

    def _check(self, response):
        """Понятные сообщения об ошибках ГигаЧата."""
        if response.status_code == 404:
            try:
                names = ", ".join(self.available_models())
            except Exception:
                names = "не удалось узнать"
            raise ValueError(f"У ГигаЧата нет модели «{self.model}». Доступны: {names}. "
                             "Впишите нужное название в GIGACHAT_MODEL в pomoshnik.py.")
        if response.status_code == 402:
            raise PermissionError("В ГигаЧате закончились бесплатные или оплаченные токены "
                                  "(ответ 402). Проверьте баланс в личном кабинете.")
        if response.status_code == 429:
            raise PermissionError("ГигаЧат просит подождать: слишком много запросов (ответ 429).")
        response.raise_for_status()


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import pomoshnik
    try:
        g = GigaChatGenerator(
            key_file=pomoshnik.GIGACHAT_KEY_FILE, cert_file=pomoshnik.GIGACHAT_CERT_FILE,
            model=pomoshnik.GIGACHAT_MODEL, scope=pomoshnik.GIGACHAT_SCOPE,
            auth_url=pomoshnik.GIGACHAT_AUTH_URL, api_url=pomoshnik.GIGACHAT_API_URL)
        print("Ключ и сертификат на месте. Доступные модели:", ", ".join(g.available_models()))
        reply = g.run([ChatMessage.from_user("Ответь одним словом: столица России?")])["replies"][0]
        print(f"Проба ({pomoshnik.GIGACHAT_MODEL}):", reply.text)
    except Exception as e:
        print(f"Не получилось: {e.__class__.__name__}: {e}")
