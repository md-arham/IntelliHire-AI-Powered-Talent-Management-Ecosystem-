import http.client
import json
import urllib.parse
from app.utils.settings import settings


def fetch_articles_for_topic(topic, language="en", limit=20):
    conn = http.client.HTTPSConnection("news-api14.p.rapidapi.com")

    headers = {
        "x-rapidapi-key": settings.RAPID_API_KEY_ARTICLES,
        "x-rapidapi-host": "news-api14.p.rapidapi.com",
    }

    query = urllib.parse.quote(topic)
    url = f"/v2/search/articles?query={query}&language={language}"

    conn.request("GET", url, headers=headers)
    res = conn.getresponse()
    data = res.read()
    result = json.loads(data.decode("utf-8"))

    return result.get("articles", [])[:limit]
