# monitor.py
# -*- coding: utf-8 -*-
"""
Monitora páginas oficiais da Maratón de Mendoza e Patagonian International Marathon
e gera um alerta quando detectar inscrições de 2026 abertas.

Fluxo:
- Baixa HTML das páginas.
- Procura "2026" + termos de inscrição e bloqueia se tiver termos de fechamento.
- Confere se há links típicos de inscrição (ex.: Eventick/Registration/WeTravel).
- Persiste estado em status.json para não enviar e-mail repetido.
- Gera alert.md quando houver novidade (o workflow usa como corpo do e-mail).
"""

import json
import os
import re
import time
from dataclasses import dataclass
from typing import List, Dict, Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

YEAR = "2026"
STATE_FILE = "status.json"
ALERT_FILE = "alert.md"
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GH-RegistrationsBot/1.0; +https://github.com/)",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8,pt-BR;q=0.7",
}


@dataclass
class Target:
    id: str
    name: str
    urls: List[str]
    positive_keywords: List[str]
    negative_keywords: List[str]
    require_year: bool = True
    must_have_link_patterns: Optional[List[str]] = None  # regex para hrefs de inscrição


TARGETS: List[Target] = [
    Target(
        id="mendoza",
        name="Maratón Internacional de Mendoza",
        urls=[
            "https://maratondemendoza.com/",
            "https://maratondemendoza.com/2026/",
            "https://maratondemendoza.com/2025/",
        ],
        positive_keywords=[
            "inscripción",
            "inscripciones",
            "inscribite",
            "registro",
            "regístrese",
            "register",
            "registration",
            "tickets",
            "venta",
            "comprar",
        ],
        negative_keywords=[
            "cerradas",
            "cerrada",
            "agotadas",
            "sold out",
            "closed",
            "finalizó",
            "fechadas",
            "encerradas",
        ],
        must_have_link_patterns=[
            r"eventick\.com\.ar",
            r"/inscripcion",
            r"/inscripciones",
            r"/register",
            r"/registration",
        ],
    ),
    Target(
        id="patagonia",
        name="Patagonian International Marathon",
        urls=[
            "https://www.patagonianinternationalmarathon.com/en/registration",
            "https://www.patagonianinternationalmarathon.com/en/calendar",
            "https://www.patagonianinternationalmarathon.com/en/",
        ],
        positive_keywords=[
            "registration",
            "register",
            "inscripción",
            "inscripciones",
            "inscreva-se",
            "super pre-sale",
            "pre-sale",
            "preventa",
            "venta",
            "tickets",
        ],
        negative_keywords=[
            "has closed",
            "closed",
            "cerradas",
            "cerrada",
            "fechadas",
            "sold out",
        ],
        must_have_link_patterns=[
            r"/en/registration",
            r"/registration",
            r"wetravel\.",
            r"/register",
        ],
    ),
]


def load_state() -> Dict[str, Dict]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # Estado inicial: ninguém foi notificado ainda
    return {t.id: {"notified_years": []} for t in TARGETS}


def save_state(state: Dict[str, Dict]):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200 and r.text:
            return r.text
    except requests.RequestException:
        return None
    return None


def text_has_open_signals(text: str, target: Target, year: str) -> bool:
    t = text.lower()
    if target.require_year and year not in t:
        return False
    if not any(k in t for k in target.positive_keywords):
        return False
    if any(k in t for k in target.negative_keywords):
        return False
    return True


def links_have_patterns(soup: BeautifulSoup, patterns: List[str]) -> bool:
    hrefs = [a.get("href") for a in soup.find_all("a", href=True)]
    for pat in patterns:
        rx = re.compile(pat, re.I)
        if any(h and rx.search(h) for h in hrefs):
            return True
    return False


def analyze_target(target: Target, year: str) -> Optional[Dict]:
    for url in target.urls:
        html = fetch(url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        if text_has_open_signals(text, target, year):
            if target.must_have_link_patterns and not links_have_patterns(
                soup, target.must_have_link_patterns
            ):
                # Sinais positivos, mas sem link típico de inscrição — aguardar
                continue
            return {"url": url, "ts": int(time.time())}
    return None


def main():
    state = load_state()
    alerts = []

    for target in TARGETS:
        if YEAR in state[target.id]["notified_years"]:
            continue
        result = analyze_target(target, YEAR)
        if result:
            alerts.append((target, result))
            state[target.id]["notified_years"].append(YEAR)

    save_state(state)

    if alerts:
        lines = [f"# Inscrições abertas {YEAR}\n"]
        for target, result in alerts:
            host = urlparse(result["url"]).netloc
            lines += [
                f"## {target.name} - detectado em {result['url']}",
                "",
                f"- Ano: **{YEAR}**",
                f"- Página analisada: `{host}`",
                f"- Critérios: termos de abertura + {YEAR} e link de inscrição presente",
                "",
            ]
        with open(ALERT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[INFO] Alertas gerados: {len(alerts)}")
    else:
        print("[INFO] Nada aberto ainda.")


if __name__ == "__main__":
    main()
