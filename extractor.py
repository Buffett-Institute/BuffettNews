"""
Scrapes an article URL and extracts the metadata fields the Buffett News
Page spreadsheet needs: title, publication date, source/outlet, a guess at
content type (Research vs. Buffett in the News), an author name, and alt
text for the article's main image.

Everything here is best-effort. The Flask app always shows the results in
an editable preview before anything is written to the spreadsheet, so a
wrong guess just means a quick manual correction rather than bad data.
"""
import json
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

import summarizer


_HTML_PARSER = "html.parser"  # built into Python; used if lxml isn't installed

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

RESEARCH_DOMAIN_HINTS = (
    "doi.org", "arxiv.org", "ncbi.nlm.nih.gov", "jstor.org", "springer.com",
    "sciencedirect.com", "wiley.com", "tandfonline.com", "nature.com",
    "pnas.org", "ssrn.com", "ieee.org", "academic.oup.com", "aaai.org",
    "journals.", "pubs.", "researchgate.net", "cambridge.org", "sagepub.com",
    "elsevier.com", "frontiersin.org", "plos.org", "mdpi.com",
)

SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "en", "for", "if", "in",
    "nor", "of", "on", "or", "per", "the", "to", "v", "vs", "via",
}


class ExtractionError(Exception):
    pass


REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_html(url: str) -> str:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (401, 403, 429):
            raise ExtractionError(
                f"{urlparse(url).netloc} blocked the automated fetch (HTTP "
                f"{exc.response.status_code}). Some outlets (e.g. the NYT, WSJ) reject "
                "scraper requests outright — fill in the fields manually below."
            ) from exc
        raise ExtractionError(f"Could not fetch the article URL: {exc}") from exc
    except requests.RequestException as exc:
        raise ExtractionError(f"Could not fetch the article URL: {exc}") from exc
    return resp.text


def smart_title_case(text: str) -> str:
    """Convert a headline to title case (AP/APA-style small-word rules),
    while preserving acronyms and camel-case brand names like 'iPhone'."""
    if not text:
        return text
    words = text.split(" ")
    n = len(words)
    result = []
    for i, word in enumerate(words):
        if word == "":
            result.append(word)
            continue
        alpha = re.sub(r"[^A-Za-z]", "", word)
        preserve_as_is = False
        if len(alpha) >= 2 and alpha.isupper() and len(alpha) <= 5:
            preserve_as_is = True  # acronym, e.g. AI, US, IPCC
        elif len(alpha) > 1 and alpha[1:] != alpha[1:].lower():
            preserve_as_is = True  # camelCase / internal caps, e.g. iPhone

        prev_ends_colon = i > 0 and words[i - 1].rstrip().endswith(":")

        if preserve_as_is:
            result.append(word)
            continue

        lower = word.lower()
        bare = re.sub(r"[^a-z'-]", "", lower)
        is_small = bare in SMALL_WORDS

        if i != 0 and i != n - 1 and is_small and not prev_ends_colon:
            result.append(lower)
        else:
            parts = re.split(r"(-)", word)
            capped_parts = []
            for part in parts:
                if part == "-" or part == "":
                    capped_parts.append(part)
                    continue
                lp = part.lower()
                first_alpha_idx = next((idx for idx, c in enumerate(lp) if c.isalpha()), None)
                if first_alpha_idx is None:
                    capped_parts.append(part)
                else:
                    capped_parts.append(
                        lp[:first_alpha_idx] + lp[first_alpha_idx].upper() + lp[first_alpha_idx + 1:]
                    )
            result.append("".join(capped_parts))
    return " ".join(result)


def _get_meta(soup, **attrs):
    for key, val in attrs.items():
        tag = soup.find("meta", attrs={key: val})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _meta_content_any(soup, names):
    for name in names:
        val = _get_meta(soup, property=name) or _get_meta(soup, name=name)
        if val:
            return val
    return None


def _extract_json_ld(soup):
    """Return the first Article-like JSON-LD object found on the page."""
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        # Some sites nest the real objects under @graph.
        expanded = []
        for c in candidates:
            if isinstance(c, dict) and "@graph" in c and isinstance(c["@graph"], list):
                expanded.extend(c["@graph"])
            else:
                expanded.append(c)
        for obj in expanded:
            if not isinstance(obj, dict):
                continue
            obj_type = obj.get("@type", "")
            types = obj_type if isinstance(obj_type, list) else [obj_type]
            if any(t for t in types if isinstance(t, str) and "Article" in t):
                return obj
    return None

def _extract_body_text(soup, max_chars=4000):
    """Pull visible paragraph text to give the summarizer real article
    content instead of just a thin meta description."""
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p) > 40)
    return text[:max_chars]


def _jsonld_str(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("@id")
    if isinstance(value, list) and value:
        return _jsonld_str(value[0])
    if isinstance(value, str):
        return value
    return None


def extract_title(soup, jsonld):
    raw = None
    if jsonld and jsonld.get("headline"):
        raw = jsonld["headline"]
    if not raw:
        raw = _meta_content_any(soup, ["og:title", "twitter:title"])
    if not raw and soup.title and soup.title.string:
        raw = soup.title.string
    if not raw:
        h1 = soup.find("h1")
        if h1:
            raw = h1.get_text(strip=True)
    if not raw:
        return None
    raw = re.sub(r"\s+", " ", raw).strip()
    # Strip common "Title | Site Name" / "Title - Site Name" suffixes.
    raw = re.split(r"\s[|–—-]\s(?=[^|]*$)", raw)[0].strip() if " | " in raw else raw
    return smart_title_case(raw)


def extract_date(soup, jsonld):
    raw = None
    if jsonld:
        raw = jsonld.get("datePublished") or jsonld.get("dateCreated")
    if not raw:
        raw = _meta_content_any(soup, [
            "article:published_time", "og:article:published_time",
            "datePublished", "publishdate", "pubdate", "date",
            "DC.date.issued", "sailthru.date", "parsely-pub-date",
        ])
    if not raw:
        time_tag = soup.find("time")
        if time_tag:
            raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
    if not raw:
        return None
    try:
        return dateparser.parse(raw, fuzzy=True)
    except (ValueError, OverflowError):
        return None


def extract_source(soup, jsonld, url):
    if jsonld and jsonld.get("publisher"):
        name = _jsonld_str(jsonld["publisher"])
        if name:
            return name
    site_name = _meta_content_any(soup, ["og:site_name", "application-name"])
    if site_name:
        return site_name
    domain = urlparse(url).netloc.replace("www.", "")
    domain = domain.split(".")[0]
    return domain.capitalize()


def extract_author(soup, jsonld):
    if jsonld and jsonld.get("author"):
        name = _jsonld_str(jsonld["author"])
        if name:
            return name
    meta_author = _meta_content_any(soup, ["author", "article:author", "parsely-author"])
    if meta_author and not meta_author.startswith("http"):
        return meta_author
    byline = soup.find(class_=re.compile(r"byline|author", re.I))
    if byline:
        text = byline.get_text(strip=True)
        text = re.sub(r"^(by|By)\s+", "", text)
        if text and len(text) < 80:
            return text
    return None


def extract_image_alt(soup, jsonld, base_url):
    image_url = _meta_content_any(soup, ["og:image", "twitter:image"])
    if not image_url and jsonld and jsonld.get("image"):
        img = jsonld["image"]
        if isinstance(img, dict):
            image_url = img.get("url")
        elif isinstance(img, list) and img:
            image_url = img[0] if isinstance(img[0], str) else img[0].get("url")
        elif isinstance(img, str):
            image_url = img

    if not image_url:
        return None, False  # (alt_text, has_image)

    image_url_abs = urljoin(base_url, image_url)
    filename = urlparse(image_url_abs).path.rsplit("/", 1)[-1]

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src:
            continue
        src_abs = urljoin(base_url, src)
        if src_abs == image_url_abs or (filename and filename in src_abs):
            alt = (img.get("alt") or "").strip()
            return (alt or None), True

    return None, True  # image exists but we couldn't locate a matching <img alt>





def build_short_description(soup, jsonld, connection_note, title):
    gist = _meta_content_any(soup, ["og:description", "twitter:description", "description"])
    if not gist and jsonld:
        gist = jsonld.get("description")
    if not gist:
        gist = title or ""
    gist = re.sub(r"\s+", " ", gist).strip()
    # Keep just the first sentence of the gist so the final result stays short.
    first_sentence = re.split(r"(?<=[.!?])\s+", gist)[0].rstrip(".") if gist else ""
    note = (connection_note or "").strip().rstrip(".")
    if first_sentence and note:
        return f"{first_sentence}, connecting to the Roberta Buffett Institute in that {note[0].lower()}{note[1:]}."
    if note:
        return f"{note[0].upper()}{note[1:]}."
    return f"{first_sentence}." if first_sentence else ""


def extract_article_metadata(url: str, connection_note: str = "") -> dict:
    html = fetch_html(url)
    soup = BeautifulSoup(html, _HTML_PARSER)
    jsonld = _extract_json_ld(soup)

    title = extract_title(soup, jsonld)
    date = extract_date(soup, jsonld)
    source = extract_source(soup, jsonld, url)
    author = extract_author(soup, jsonld)
    alt_text, has_image = extract_image_alt(soup, jsonld, url)

    #summmary
    gist = _meta_content_any(soup, ["og:description", "twitter:description", "description"])
    if not gist and jsonld:
        gist = jsonld.get("description")
    body_text = _extract_body_text(soup)
    description = summarizer.generate_short_description(
        title, body_text or gist, connection_note
    ) or build_short_description(soup, jsonld, connection_note, title)

    if not has_image:
        image_alt_final = f"Author: {author}" if author else ""
        image_note = "No image detected on the page; using author name."
    elif alt_text:
        image_alt_final = alt_text
        image_note = ""
    else:
        image_alt_final = f"Author: {author}" if author else ""
        image_note = "An image was found but had no alt text; using author name as a fallback. Please verify."

    return {
        "title": title or "",
        "date": date.strftime("%Y-%m-%d") if date else "",
        "source": source or "",
        "url": url,
        "image_alt": image_alt_final,
        "image_note": image_note,
        "short_description": description,
        "author": author or "",
    }
