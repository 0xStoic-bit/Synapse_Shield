# 1. Yeni Framework Desteği: Hangisi En Çok Ses Getirir?

Şu an Synapse Shield'da:
- **Backend:** FastAPI, Django, Flask
- **Frontend:** Vanilla JS SDK, React / Next.js (synapse-shield-react), Vue 3 / Nuxt 3 (synapse-shield-vue)

Python ekosisteminde şu an en çok yükselen ve bot korumasına en çok ihtiyaç duyan 2 modern asenkron framework var:

### A. Litestar (Eski adıyla Starlite) ⭐ (En Çok Tavsiye Ettiğim)
- **Neden?** FastAPI'nin günümüzdeki en büyük, en modern ve en hızlı ASGI rakibi. Yüksek performanslı enterprise ekipler ve FinTech firmaları doğrudan Litestar'a geçiyor.
- **Durum:** Şu an Litestar için açık kaynaklı neredeyse hiçbir Cloudflare Turnstile alternatifi bot koruma middleware'i yok!
- **Entegrasyon:** `src/synapse_shield/litestar.py` (Bir Litestar Middleware veya Guard olarak tek satırda entegre edilir).

### B. Sanic veya AIOHTTP
- **Neden?** Yüksek eşzamanlı (high-concurrency) mikroservislerin ve asenkron API'ların klasiği.
- **Entegrasyon:** `src/synapse_shield/sanic.py` (`@shield_protect_sanic` dekoratörü).

**Tavsiye:** v0.9.5'e Litestar (veya Sanic) desteği eklemek, Reddit (r/Python) ve Hacker News gibi yerlerde "Synapse Shield now supports Litestar & Sanic" duyurusuyla çok ciddi yeni bir kitle çeker!
