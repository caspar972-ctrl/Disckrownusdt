#!/usr/bin/env python3
"""Free CEX listing watcher: public APIs + announcements -> Discord."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SEEN_PATH = Path("seen.json")
TIMEOUT = 25
HEADERS = {
    "User-Agent": "KrownListingWatch/1.1 (+github-actions)"
}

LISTING_RE = re.compile(
    r"\b(list|lists|listed|listing|will list|to list|new listing|"
    r"new cryptocurrency listing|adds|trading pair|spot trading)\b",
    re.I,
)
KROWN_RE = re.compile(
    r"krown|wkrown|w-krown|krown network|krown coin|krowndex|\bkrwn\b",
    re.I,
)

ANNOUNCE_SOURCES = [
    {
        "name": "Binance listings page",
        "url": "https://www.binance.com/en/support/announcement/list/48",
        "kind": "html",
    },
    {
        "name": "Bybit new crypto",
        "url": "https://announcements.bybit.com/en/?category=new_crypto",
        "kind": "html",
    },
    {
        "name": "OKX new listings",
        "url": "https://www.okx.com/help/section/announcements-new-listings",
        "kind": "html",
    },
    {
        "name": "Coinbase roadmap",
        "url": (
            "https://www.coinbase.com/blog/"
            "increasing-transparency-for-new-asset-listings-on-coinbase"
        ),
        "kind": "html",
    },
    {
        "name": "Krown site",
        "url": "https://krown.network/",
        "kind": "html",
    },
    {
        "name": "Bitget announcements",
        "url": "https://www.bitget.com/support/sections/12508385025201",
        "kind": "html",
    },
    {
        "name": "Gate listings",
        "url": "https://www.gate.io/announcements/newlisted",
        "kind": "html",
    },
    {
        "name": "MEXC listings",
        "url": "https://www.mexc.com/announcements/new-listings",
        "kind": "html",
    },
    {
        "name": "KuCoin listings",
        "url": "https://www.kucoin.com/announcement/new-listings",
        "kind": "html",
    },
    {
        "name": "HTX announcements",
        "url": "https://www.htx.com/support/list/360000039481",
        "kind": "html",
    },
    {
        "name": "BingX listings",
        "url": "https://bingx.com/en/support/notice-center",
        "kind": "html",
    },
    {
        "name": "KrownDEX",
        "url": "https://krowndex.com/",
        "kind": "html",
    },
]


def load_state() -> dict:
    if not SEEN_PATH.exists():
        return {"ids": [], "pairs": {}}
    data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    data.setdefault("ids", [])
    data.setdefault("pairs", {})
    return data


def save_state(state: dict) -> None:
    state["ids"] = list(state.get("ids", []))[-4000:]
    SEEN_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def get_json(url: str, params: dict | None = None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"api fail {url}: {exc}", file=sys.stderr)
        return None


def post_json(url: str, payload: dict):
    try:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"api post fail {url}: {exc}", file=sys.stderr)
        return None


def get_text(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        print(f"html fail {url}: {exc}", file=sys.stderr)
        return None


def discord_post(webhook: str, content: str) -> None:
    r = requests.post(webhook, json={"content": content[:1900]}, timeout=TIMEOUT)
    if r.status_code >= 300:
        print(f"discord fail {r.status_code}: {r.text}", file=sys.stderr)


def is_krown(text: str) -> bool:
    return bool(KROWN_RE.search(text))


def fetch_pairs() -> list[dict]:
    """Return [{exchange, market, symbol, base, quote}]."""
    out: list[dict] = []

    # Binance spot
    data = get_json("https://api.binance.com/api/v3/exchangeInfo")
    if data and "symbols" in data:
        for s in data["symbols"]:
            out.append(
                {
                    "exchange": "Binance",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseAsset", ""),
                    "quote": s.get("quoteAsset", ""),
                    "status": s.get("status", ""),
                }
            )

    # Binance USDT-M futures
    data = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo")
    if data and "symbols" in data:
        for s in data["symbols"]:
            out.append(
                {
                    "exchange": "Binance",
                    "market": "futures",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseAsset", ""),
                    "quote": s.get("quoteAsset", ""),
                    "status": s.get("status", ""),
                }
            )

    # Bybit spot
    data = get_json(
        "https://api.bybit.com/v5/market/instruments-info",
        {"category": "spot", "limit": 1000},
    )
    if data and data.get("result", {}).get("list"):
        for s in data["result"]["list"]:
            out.append(
                {
                    "exchange": "Bybit",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCoin", ""),
                    "quote": s.get("quoteCoin", ""),
                    "status": s.get("status", ""),
                }
            )

    # Bybit linear perps
    data = get_json(
        "https://api.bybit.com/v5/market/instruments-info",
        {"category": "linear", "limit": 1000},
    )
    if data and data.get("result", {}).get("list"):
        for s in data["result"]["list"]:
            out.append(
                {
                    "exchange": "Bybit",
                    "market": "futures",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCoin", ""),
                    "quote": s.get("quoteCoin", ""),
                    "status": s.get("status", ""),
                }
            )

    # OKX spot
    data = get_json(
        "https://www.okx.com/api/v5/public/instruments", {"instType": "SPOT"}
    )
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "OKX",
                    "market": "spot",
                    "symbol": s.get("instId", ""),
                    "base": s.get("baseCcy", ""),
                    "quote": s.get("quoteCcy", ""),
                    "status": s.get("state", ""),
                }
            )

    # OKX swap
    data = get_json(
        "https://www.okx.com/api/v5/public/instruments", {"instType": "SWAP"}
    )
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "OKX",
                    "market": "futures",
                    "symbol": s.get("instId", ""),
                    "base": s.get("ctValCcy") or s.get("baseCcy", ""),
                    "quote": s.get("settleCcy") or s.get("quoteCcy", ""),
                    "status": s.get("state", ""),
                }
            )

    # Coinbase Exchange
    data = get_json("https://api.exchange.coinbase.com/products")
    if isinstance(data, list):
        for s in data:
            out.append(
                {
                    "exchange": "Coinbase",
                    "market": "spot",
                    "symbol": s.get("id", ""),
                    "base": s.get("base_currency", ""),
                    "quote": s.get("quote_currency", ""),
                    "status": s.get("status", ""),
                }
            )

    # KuCoin
    data = get_json("https://api.kucoin.com/api/v2/symbols")
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "KuCoin",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCurrency", ""),
                    "quote": s.get("quoteCurrency", ""),
                    "status": "online" if s.get("enableTrading") else "off",
                }
            )

    # Gate.io
    data = get_json("https://api.gateio.ws/api/v4/spot/currency_pairs")
    if isinstance(data, list):
        for s in data:
            out.append(
                {
                    "exchange": "Gate",
                    "market": "spot",
                    "symbol": s.get("id", ""),
                    "base": s.get("base", ""),
                    "quote": s.get("quote", ""),
                    "status": s.get("trade_status", ""),
                }
            )

    # MEXC
    data = get_json("https://api.mexc.com/api/v3/exchangeInfo")
    if data and data.get("symbols"):
        for s in data["symbols"]:
            out.append(
                {
                    "exchange": "MEXC",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseAsset", ""),
                    "quote": s.get("quoteAsset", ""),
                    "status": s.get("status", ""),
                }
            )

    # Kraken
    data = get_json("https://api.kraken.com/0/public/AssetPairs")
    if data and data.get("result"):
        for pair, s in data["result"].items():
            out.append(
                {
                    "exchange": "Kraken",
                    "market": "spot",
                    "symbol": s.get("wsname") or pair,
                    "base": (s.get("base") or "").replace("X", "", 1)
                    if s.get("base", "").startswith("X")
                    else s.get("base", ""),
                    "quote": s.get("quote", ""),
                    "status": "online",
                }
            )

    # Bitget spot
    data = get_json("https://api.bitget.com/api/v2/spot/public/symbols")
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "Bitget",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCoin", ""),
                    "quote": s.get("quoteCoin", ""),
                    "status": s.get("status", ""),
                }
            )

    # Upbit
    data = get_json("https://api.upbit.com/v1/market/all")
    if isinstance(data, list):
        for s in data:
            market = s.get("market", "")
            parts = market.split("-", 1)
            out.append(
                {
                    "exchange": "Upbit",
                    "market": "spot",
                    "symbol": market,
                    "base": parts[1] if len(parts) == 2 else market,
                    "quote": parts[0] if len(parts) == 2 else "",
                    "status": "online",
                }
            )

    # Crypto.com
    data = get_json(
        "https://api.crypto.com/exchange/v1/public/get-instruments"
    )
    instruments = []
    if data:
        instruments = (
            (data.get("result") or {}).get("data")
            or (data.get("result") or {}).get("instruments")
            or []
        )
    for s in instruments:
        out.append(
            {
                "exchange": "Crypto.com",
                "market": s.get("inst_type") or "spot",
                "symbol": s.get("symbol") or s.get("instrument_name") or "",
                "base": s.get("base_ccy") or s.get("base_currency") or "",
                "quote": s.get("quote_ccy") or s.get("quote_currency") or "",
                "status": s.get("tradable") or "online",
            }
        )

    # LBank
    data = get_json("https://api.lbank.info/v2/currencyPairs.do")
    pairs = []
    if isinstance(data, dict):
        pairs = data.get("data") or []
    elif isinstance(data, list):
        pairs = data
    for raw in pairs:
        symbol = raw if isinstance(raw, str) else str(raw)
        parts = symbol.split("_")
        out.append(
            {
                "exchange": "LBank",
                "market": "spot",
                "symbol": symbol.upper(),
                "base": parts[0].upper() if parts else symbol,
                "quote": parts[1].upper() if len(parts) > 1 else "",
                "status": "online",
            }
        )

    # Bitget futures
    data = get_json(
        "https://api.bitget.com/api/v2/mix/market/contracts",
        {"productType": "USDT-FUTURES"},
    )
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "Bitget",
                    "market": "futures",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCoin", ""),
                    "quote": s.get("quoteCoin", ""),
                    "status": s.get("symbolStatus") or s.get("offTime") or "online",
                }
            )

    # Gate futures
    data = get_json("https://api.gateio.ws/api/v4/futures/usdt/contracts")
    if isinstance(data, list):
        for s in data:
            name = s.get("name") or ""
            out.append(
                {
                    "exchange": "Gate",
                    "market": "futures",
                    "symbol": name,
                    "base": name.split("_")[0] if "_" in name else name,
                    "quote": "USDT",
                    "status": "online" if not s.get("in_delisting") else "off",
                }
            )

    # HTX / Huobi
    data = get_json("https://api.huobi.pro/v1/common/symbols")
    if data and data.get("data"):
        for s in data["data"]:
            out.append(
                {
                    "exchange": "HTX",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": (s.get("base-currency") or "").upper(),
                    "quote": (s.get("quote-currency") or "").upper(),
                    "status": s.get("state", ""),
                }
            )

    # BingX spot
    data = get_json("https://open-api.bingx.com/openApi/spot/v1/common/symbols")
    symbols = []
    if data:
        symbols = (data.get("data") or {}).get("symbols") or data.get("data") or []
        if isinstance(symbols, dict):
            symbols = symbols.get("symbols") or []
    if isinstance(symbols, list):
        for s in symbols:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "exchange": "BingX",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseAsset") or s.get("orgQuantityIncrement") or "",
                    "quote": s.get("quoteAsset", ""),
                    "status": s.get("status", "online"),
                }
            )

    # Gemini
    data = get_json("https://api.gemini.com/v1/symbols")
    if isinstance(data, list):
        for raw in data:
            symbol = str(raw).upper()
            out.append(
                {
                    "exchange": "Gemini",
                    "market": "spot",
                    "symbol": symbol,
                    "base": symbol,
                    "quote": "",
                    "status": "online",
                }
            )

    # Bitfinex
    data = get_json("https://api-pub.bitfinex.com/v2/tickers", {"symbols": "ALL"})
    if isinstance(data, list):
        for row in data:
            if not row or not isinstance(row, list):
                continue
            name = str(row[0])
            if not name.startswith("t"):
                continue
            out.append(
                {
                    "exchange": "Bitfinex",
                    "market": "spot",
                    "symbol": name[1:],
                    "base": name[1:],
                    "quote": "",
                    "status": "online",
                }
            )

    # Bithumb
    data = get_json("https://api.bithumb.com/public/ticker/ALL_KRW")
    if data and isinstance(data.get("data"), dict):
        for coin, _info in data["data"].items():
            if coin == "date":
                continue
            out.append(
                {
                    "exchange": "Bithumb",
                    "market": "spot",
                    "symbol": f"{coin}_KRW",
                    "base": coin,
                    "quote": "KRW",
                    "status": "online",
                }
            )

    # Hyperliquid perps
    data = post_json("https://api.hyperliquid.xyz/info", {"type": "meta"})
    universe = []
    if data:
        universe = data.get("universe") or []
    for s in universe:
        name = s.get("name") or ""
        if not name:
            continue
        out.append(
            {
                "exchange": "Hyperliquid",
                "market": "perps",
                "symbol": name,
                "base": name,
                "quote": "USD",
                "status": "offline" if s.get("isDelisted") else "online",
            }
        )

    # Binance COIN-M futures
    data = get_json("https://dapi.binance.com/dapi/v1/exchangeInfo")
    if data and data.get("symbols"):
        for s in data["symbols"]:
            out.append(
                {
                    "exchange": "Binance",
                    "market": "coin-futures",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseAsset", ""),
                    "quote": s.get("quoteAsset", ""),
                    "status": s.get("status", ""),
                }
            )

    # Bybit inverse
    data = get_json(
        "https://api.bybit.com/v5/market/instruments-info",
        {"category": "inverse", "limit": 1000},
    )
    if data and data.get("result", {}).get("list"):
        for s in data["result"]["list"]:
            out.append(
                {
                    "exchange": "Bybit",
                    "market": "inverse",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCoin", ""),
                    "quote": s.get("quoteCoin", ""),
                    "status": s.get("status", ""),
                }
            )

    # WhiteBIT
    data = get_json("https://whitebit.com/api/v4/public/markets")
    if isinstance(data, list):
        for s in data:
            out.append(
                {
                    "exchange": "WhiteBIT",
                    "market": s.get("type") or "spot",
                    "symbol": s.get("name", ""),
                    "base": s.get("stock", ""),
                    "quote": s.get("money", ""),
                    "status": "online" if s.get("tradesEnabled") else "off",
                }
            )

    # Poloniex
    data = get_json("https://api.poloniex.com/markets")
    if isinstance(data, list):
        for s in data:
            out.append(
                {
                    "exchange": "Poloniex",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCurrencyName", ""),
                    "quote": s.get("quoteCurrencyName", ""),
                    "status": s.get("state", ""),
                }
            )

    # BitMart
    data = get_json("https://api-cloud.bitmart.com/spot/v1/symbols")
    if data and isinstance((data.get("data") or {}).get("symbols"), list):
        for raw in data["data"]["symbols"]:
            symbol = str(raw)
            parts = symbol.split("_")
            out.append(
                {
                    "exchange": "BitMart",
                    "market": "spot",
                    "symbol": symbol,
                    "base": parts[0] if parts else symbol,
                    "quote": parts[1] if len(parts) > 1 else "",
                    "status": "online",
                }
            )

    # CoinEx
    data = get_json("https://api.coinex.com/v2/spot/market")
    markets = []
    if data:
        markets = data.get("data") or []
    if isinstance(markets, list):
        for s in markets:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "exchange": "CoinEx",
                    "market": "spot",
                    "symbol": s.get("market") or s.get("name") or "",
                    "base": s.get("base_ccy") or "",
                    "quote": s.get("quote_ccy") or "",
                    "status": s.get("status") or "online",
                }
            )

    # XT
    data = get_json("https://sapi.xt.com/v4/public/symbol")
    xt_list = []
    if data:
        xt_list = (data.get("result") or {}).get("symbols") or data.get("result") or []
    if isinstance(xt_list, list):
        for s in xt_list:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "exchange": "XT",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCurrency", ""),
                    "quote": s.get("quoteCurrency", ""),
                    "status": s.get("state") or s.get("status") or "online",
                }
            )

    # Phemex
    data = get_json("https://api.phemex.com/public/products")
    products = []
    if data:
        products = (data.get("data") or {}).get("products") or data.get("data") or []
    if isinstance(products, list):
        for s in products:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "exchange": "Phemex",
                    "market": s.get("type") or "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("baseCurrency") or s.get("contractUnderlyingAssets") or "",
                    "quote": s.get("quoteCurrency", ""),
                    "status": s.get("status", ""),
                }
            )

    # Woo X
    data = get_json("https://api.woo.org/v1/public/info")
    rows = []
    if data:
        rows = data.get("rows") or data.get("data") or []
    if isinstance(rows, list):
        for s in rows:
            if not isinstance(s, dict):
                continue
            out.append(
                {
                    "exchange": "WOO",
                    "market": "spot",
                    "symbol": s.get("symbol", ""),
                    "base": s.get("base_asset") or "",
                    "quote": s.get("quote_asset") or "",
                    "status": s.get("is_stable") or s.get("status") or "online",
                }
            )

    # CoinGecko listed coins named Krown (backup)
    data = get_json(
        "https://api.coingecko.com/api/v3/search", {"query": "krown"}
    )
    if data and data.get("coins"):
        for coin in data["coins"][:20]:
            name = f"{coin.get('name', '')} {coin.get('symbol', '')}"
            if not KROWN_RE.search(name):
                continue
            out.append(
                {
                    "exchange": "CoinGecko",
                    "market": "index",
                    "symbol": coin.get("symbol", ""),
                    "base": coin.get("id", ""),
                    "quote": "",
                    "status": "listed",
                }
            )

    return out


def pair_key(p: dict) -> str:
    return f"{p['exchange']}|{p['market']}|{p['symbol']}"


def pair_text(p: dict) -> str:
    return f"{p['exchange']} {p['market']} {p['symbol']} {p['base']} {p['quote']}"


def extract_html_items(source: str, url: str, html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    seen_local = set()
    for a in soup.find_all("a", href=True):
        title = " ".join(a.get_text(" ", strip=True).split())
        if len(title) < 12 or len(title) > 220:
            continue
        href = urljoin(url, a["href"])
        key = (title.lower(), href)
        if key in seen_local:
            continue
        seen_local.add(key)
        items.append({"source": source, "title": title, "url": href})
    return items


def extract_binance_cms() -> list[dict]:
    try:
        r = requests.post(
            "https://www.binance.com/bapi/composite/v1/public/cms/article/"
            "catalog/list/query",
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"type": 1, "catalogId": 48, "pageNo": 1, "pageSize": 20},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data") or {}
        articles = data.get("articles") or []
        if articles and isinstance(articles, list) and "articles" in articles[0]:
            flat = []
            for cat in articles:
                flat.extend(cat.get("articles") or [])
            articles = flat
        out = []
        for art in articles:
            title = art.get("title") or ""
            code = art.get("code") or art.get("id") or ""
            if not title:
                continue
            link = (
                f"https://www.binance.com/en/support/announcement/detail/{code}"
                if code
                else "https://www.binance.com/en/support/announcement/list/48"
            )
            out.append({"source": "Binance CMS", "title": title, "url": link})
        return out
    except Exception as exc:
        print(f"binance cms fail: {exc}", file=sys.stderr)
        return []


def announce_id(source: str, title: str, url: str) -> str:
    raw = f"{source}|{title.strip().lower()}|{url.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def main() -> int:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        print("Mangler DISCORD_WEBHOOK_URL", file=sys.stderr)
        return 1

    krown_only = os.environ.get("KROWN_ONLY", "1") == "1"
    state = load_state()
    known_pairs: dict = state.get("pairs") or {}
    known_ids = set(state.get("ids") or [])

    pairs = fetch_pairs()
    current_keys = {pair_key(p): p for p in pairs}

    # Snapshot new exchanges instead of alerting every existing pair.
    known_exchanges = {k.split("|", 1)[0] for k in known_pairs}
    current_exchanges = {p["exchange"] for p in current_keys.values()}
    snapshot_exchanges = current_exchanges - known_exchanges
    first_api_run = len(known_pairs) == 0
    new_pairs = []
    if first_api_run:
        print(f"api snapshot {len(current_keys)} pairs, no alerts this run")
    else:
        if snapshot_exchanges:
            print(f"snapshot new exchanges: {sorted(snapshot_exchanges)}")
        for key, p in current_keys.items():
            if key in known_pairs:
                continue
            if p["exchange"] in snapshot_exchanges:
                continue
            text = pair_text(p)
            if krown_only and not is_krown(text):
                continue
            new_pairs.append(p)

    # Cap flood if an exchange dumps 200 new pairs at once.
    krown_pairs = [p for p in new_pairs if is_krown(pair_text(p))]
    other_pairs = [p for p in new_pairs if p not in krown_pairs][:25]

    for p in krown_pairs + other_pairs:
        mark = "👑 KROWN LIVE PÅ API" if is_krown(pair_text(p)) else "🚨 Nyt par på API"
        discord_post(
            webhook,
            (
                f"{mark}\n"
                f"**Børs:** {p['exchange']}\n"
                f"**Marked:** {p['market']}\n"
                f"**Par:** `{p['symbol']}`\n"
                f"**Base/Quote:** {p['base']} / {p['quote']}\n"
                f"**Status:** {p.get('status') or '?'}"
            ),
        )
        print(f"posted pair {pair_key(p)}")

    state["pairs"] = {k: True for k in current_keys}

    # Announcements (slower / noisier backup)
    found = extract_binance_cms()
    for src in ANNOUNCE_SOURCES:
        html = get_text(src["url"])
        if html:
            found.extend(extract_html_items(src["name"], src["url"], html))

    posted_ann = 0
    for item in found:
        title = item["title"]
        interesting = is_krown(title) or (not krown_only and LISTING_RE.search(title))
        if not interesting:
            continue
        iid = announce_id(item["source"], title, item["url"])
        if iid in known_ids:
            continue
        known_ids.add(iid)
        prefix = "👑 KROWN ANNOUNCEMENT" if is_krown(title) else "📢 Listing announcement"
        discord_post(
            webhook,
            f"{prefix}\n**Kilde:** {item['source']}\n**Titel:** {title}\n{item['url']}",
        )
        posted_ann += 1

    state["ids"] = list(known_ids)
    save_state(state)
    print(
        f"done pairs={len(current_keys)} new_pairs={len(new_pairs)} "
        f"announcements={posted_ann} first_api_run={first_api_run}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
