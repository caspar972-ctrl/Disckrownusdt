# Krown / CEX Listing Watch (gratis, API)

Tjekker offentlige exchange-API’er for nye handelspar og poster i Discord.
Announcements kører som backup.

Kører hvert 5. minut (grænsen på gratis GitHub Actions).

## API’er
- Binance spot + USDT-M futures
- Bybit spot + linear
- OKX spot + swap
- Coinbase Exchange products
- KuCoin, Gate, MEXC, Kraken

Første kørsel tager kun et snapshot, så du ikke får 20.000 alerts.
Næste kørsel poster kun nye par.

## Setup
1. Private GitHub-repo + upload filerne
2. Discord-webhook
3. Secret: DISCORD_WEBHOOK_URL
4. Actions → Listing Watch → Run workflow

Valgfri variable: KROWN_ONLY=1 (kun Krown-par og Krown-tekst)

## Hurtigere end 5 min
GitHub kan ikke. Kør python monitor.py med cron hvert 30-60 sek på en PC/VPS.
