# Luxella Scraper

Multi-site price/stock tracker. Har naya site `sites.py` me ek config add karke jud jaata hai.

## Kaise kaam karta hai
1. `main.py` har site ko `sites.py` se padhta hai
2. Agar site ko proxy chahiye (`needs_proxy: True`), to GitHub Secrets se proxy use karta hai
3. Har product ka price/stock Supabase ke `products` table se compare hota hai
4. Kuch badla to `product_changes` table me log hota hai
5. GitHub Actions har 6 ghante ye poora process apne aap chalata hai — free

## Setup (ek baar ka kaam)

### 1. GitHub Secrets add karo
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret

Add karo:
- `SUPABASE_URL` — tera Supabase project URL
- `SUPABASE_SERVICE_KEY` — Supabase project settings -> API -> service_role key
- `PROXY_SERVER` — (sirf tough sites ke liye) proxy provider ka server address
- `PROXY_USERNAME` / `PROXY_PASSWORD` — proxy login

### 2. Naya site add karna
`sites.py` khol, neeche wale template ko copy karke fill kar:
- URL, tile selector, name/price/link selectors (inspect element se dhoondhna padega)
- `needs_browser: True` agar site JS se products load karti hai
- `needs_proxy: True` agar site block karti hai (test karke pata chalega)

### 3. Test (local, GitHub push se pehle)
```
pip install -r requirements.txt
playwright install chromium
export SUPABASE_URL="..."
export SUPABASE_SERVICE_KEY="..."
python main.py
```

### 4. Schedule badalna
`.github/workflows/scrape.yml` me `cron` line badlo:
- Har 6 ghante: `0 */6 * * *`
- Din me 2 baar (12 ghante): `0 3,15 * * *`
