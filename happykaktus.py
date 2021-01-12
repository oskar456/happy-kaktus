#!/usr/bin/env python3

from pathlib import Path
from io import StringIO
import os

import lxml.html
import requests




def send_telegram_message(message):
    telegram_bot_token = os.environ["TELEGRAM_TOKEN"]
    telegram_group_name = os.environ["TELEGRAM_CHATID"]
    url = "https://api.telegram.org/bot{}/sendMessage".format(telegram_bot_token)
    payload = {
        "chat_id":telegram_group_name,
        "text": message,
        "parse_mode": "HTML",
    }
    r = requests.post(url, data=payload).json()
    if not r["ok"]:
        print(r)
        raise RuntimeError("Telegram error")


def get_last_newsitem():
    url = "https://www.mujkaktus.cz/novinky"
    s = requests.Session()
    doc = lxml.html.parse(StringIO(s.get(url).text))
    news = doc.find('//div[@class="journal-content-article"]')
    if news is None:
        raise ValueError("No news found")
    if len(news) > 1: 
        news.remove(news[-1]) # Odstraň poslední odstavec
    return news


def save_last_newsitem(news):
    p = Path(__file__).parents[0] / "lastitem.html"
    p.write_text(lxml.html.tostring(news, encoding="unicode"))


def load_saved_newsitem():
    p = Path(__file__).parents[0] / "lastitem.html"
    return lxml.html.fragment_fromstring(p.read_text())


def render_html(news):
    return "<b>{}</b>\n{}".format(news[0][0].text_content(), "".join(n.text_content().strip() for n in news[0][1:-1]))


def main():
    try:
        news = get_last_newsitem()
    except (ConnectionResetError, ValueError):
        print("Cannot get the news!")
        return
    print("Some news scraped!")
    try:
        saved = load_saved_newsitem()
        print("Old news:", saved.text_content().strip())
        print("New news:", news.text_content().strip())
        if saved.text_content().strip() == news.text_content().strip():
            print("Old news, same news.")
            return
    except FileNotFoundError:
        pass
    print("Sending the news:", render_html(news))
    send_telegram_message(render_html(news))
    save_last_newsitem(news)


if __name__ == '__main__':
    main()
