#!/usr/bin/env python3
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import requests
from lxml import html
from pdfminer.high_level import extract_text  # pip install pdfminer.six

# Base URLs
KAKTUS_WEB_HOMEPAGE = "https://www.mujkaktus.cz/"
KAKTUS_DOBIJECKA_URL = urljoin(KAKTUS_WEB_HOMEPAGE, "chces-pridat")

# File where we store the last‐seen PDF link
STATE_FILE = Path(__file__).parents[0] / "lastlink.txt"


def send_telegram_message(message):
    telegram_bot_token = os.environ["TELEGRAM_TOKEN"]
    telegram_group_name = os.environ["TELEGRAM_CHATID"]
    urlbase = "https://api.telegram.org/bot{}/sendMessage"
    url = urlbase.format(telegram_bot_token)
    payload = {
        "chat_id": telegram_group_name,
        "text": message,
        "parse_mode": "HTML",
        "link_preview_options": {
            "is_disabled": True,
        },
    }
    r = requests.post(url, json=payload).json()
    if not r["ok"]:
        print(r)
        raise RuntimeError("Telegram error")


def get_session_with_cookies(timeout: int = 30) -> requests.Session:
    session = requests.Session()
    session.get(KAKTUS_WEB_HOMEPAGE, timeout=timeout)
    return session


def link_matches_pattern(link: str) -> bool:
    today = datetime.now().strftime("%d%m%Y")
    pattern = re.compile(
        rf".*OP\-Odmena\-za\-dobiti\-FB_{today}\.pdf$"
    )
    return bool(pattern.match(link))


def load_last_link() -> str:
    try:
        return STATE_FILE.read_text().strip()
    except FileNotFoundError:
        return ""


def download_pdf(session: requests.Session, url: str) -> bytes:
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    return resp.content


def save_last_link(link: str):
    STATE_FILE.write_text(link)


def extract_datetime_range(text: str) -> str:
    regex = re.compile(
        r'od\s*'
        r'(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})'  # start date
        r'\s+od\s+'
        r'(\d{1,2}:\d{2})\s*hod\.\s*'
        r'do\s*'
        r'(\d{1,2}\.\s*\d{1,2}\.\s*\d{4})\s*'  # end date
        r'(\d{1,2}:\d{2})\s*hod\.',
        flags=re.IGNORECASE,
    )
    m = regex.search(text)
    if not m:
        raise ValueError("Date/time range not found in PDF text")
    return m.group(0).replace('\n', '')


def main():
    session = get_session_with_cookies()
    resp = session.get(KAKTUS_DOBIJECKA_URL, timeout=30)
    resp.raise_for_status()

    # 1) Parse HTML, find the single PDF link
    doc = html.fromstring(resp.content)
    anchors = doc.xpath(
                "//a[contains(normalize-space(.), "
                "'Celé podmínky v PDF')]"
              )
    if len(anchors) != 1:
        print(
            "[ERROR] Expected exactly one link, "
            f"found {len(anchors)}; exiting."
        )
        return

    raw_href = anchors[0].get("href")
    pdf_link = urljoin(KAKTUS_DOBIJECKA_URL, raw_href)

    # Skipping this for now, it seems superfluous and fragile to OC
    # # 2) Validate link format
    # if not link_matches_pattern(pdf_link):
    #     print(
    #         "[ERROR] Link does not match expected PDF pattern: "
    #         f"{pdf_link}"
    #     )
    #     return

    # 3) Check for new link
    last = load_last_link()
    if pdf_link == last:
        print("No change in PDF link; nothing to do.")
        return

    # 4) Download and extract text
    try:
        pdf_bytes = download_pdf(session, pdf_link)
        text = extract_text(BytesIO(pdf_bytes))
    except Exception as e:
        print(f"[ERROR] Download or text extraction failed: {e}")
        # fallback to sending basic notification below

    # 5) Try to parse the date/time range
    try:
        dt_range = extract_datetime_range(text)
        # build the detailed notification
        message = (
            "🔔 <b>Dobíječka je tady!</b>\n\n"
            f"Nabídka platí {dt_range}\n\n"
            f"<a href=\"{KAKTUS_DOBIJECKA_URL}\">Více informací</a>"
            " | "
            f"<a href=\"{pdf_link}\">Podmínky v PDF</a>"
        )
    except Exception:
        # fallback notification when we can’t find the time in PDF
        message = (
            "🔔 <b>Dnes bude asi dobíječka!</b>\n\n"
            "Nepodařilo se ale zjistit přesný čas.\n\n"
            f"<a href=\"{KAKTUS_DOBIJECKA_URL}\">Více informací</a>"
            " | "
            f"<a href=\"{pdf_link}\">Podmínky v PDF</a>"
        )

    # 6) Send the notification
    try:
        send_telegram_message(message)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
    else:
        print("Notification sent.")
        # 8) Save link so we don't resend - only when Telegram didn't fail
        save_last_link(pdf_link)


if __name__ == "__main__":
    main()
