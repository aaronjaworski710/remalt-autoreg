# remalt-autoreg

## Quick start

```bash
git clone https://github.com/aaronjaworski710/remalt-autoreg && cd remalt-autoreg
python remalt_autoreg.py 3 --threads 2          # 3 аккаунта -> accounts.jsonl
python card_dashboard.py                        # http://127.0.0.1:8500 (кард-UI)
pip install "camoufox[geoip]" && python -m camoufox fetch   # только для активатора триала
python remalt_trial.py 0 your_acc@voidash.bond  # триал с картой #0 (cards.json / cards_live.json)
export REMALT_GATEWAY_KEY=*** && python remalt_gateway.py 8400
```

Requirements: Python 3.9+ (всё на stdlib, кроме `remalt_trial*.py` — им нужен Camoufox, см. requirements.txt). Чекер карт требует `STRIPE_PK` env = любой merchant publishable key (pk_live_...) с разрешённой токенизацией.

Remalt.com (AI content workspace, 15+ LLMs) — массовый авторег через чистый API и разведка абуз-поверхности. Без браузера, без капчи.

## Что за сервис

[Remalt](https://remalt.com) — AI-контент-воркспейс: GPT-6.1 Sol, Claude Opus 5.5, Grok 4.7, DeepSeek V4 Pro + BYOK, генерация постов LinkedIn/YouTube/Instagram, картинки (GPT Image 2.5, Nano Banana Pro), транскрибация, агентные brainboard-цепочки. Starter $29/мес, 3000 коинов. Стек: Next.js + better-auth + Supabase (`enohvkozrazgjpbmnkgr`) + Stripe/Razorpay.

## Авторег (проверено, 200 OK)

Полный флоу одним скриптом — `remalt_autoreg.py`:

1. Voidash inbox (бесплатная temp-mail с API): `POST api.voidash.com/api/v1/inboxes {"domain":"voidash.bond"}`
2. `POST /api/auth/sign-up/email {email, password, name}` → 200 + user id (better-auth, капчи НЕТ)
3. Письмо "Verify your email" приходит за ~5 сек → берём поле `magic_link` из Voidash API
4. `GET magic_link` → 302 на главную, email верифицирован
5. `POST /api/auth/sign-in/email` → session token (30 дней)

Скорость: ~10 сек/акк, лимитов на регистрацию с одного IP не обнаружено. Выход — `accounts.jsonl` (email, password, user_id, session_token, voidash_key).

## Что даёт акк

- `GET /api/stripe/subscription` → `storedCredits: 500`, `trialEligible: true`, но `tokenBalance.locked: true`
- AI-эндпоинты (`/api/chat`, `/api/image/generate`, `/api/linkedin/generate-post`) под гейтом `REMALT_FULL_ACCESS_REQUIRED`
- `/api/webpage/analyze` на мелких URL работает БЕЗ плана — бесплатный анализ страниц
- `/api/health` открыт наружу — сливает supabase project id, билд sha, статусы stripe/razorpay live
- Триалы: Stripe starter = 7 дней бесплатно (но $29 сразу в чекауте), Razorpay `starter_promo` = 1 месяц бесплатно (нужна карта, INR-биллинг)

## Эндпоинты (реверс из JS-чанков)

`/api/auth/sign-up/email`, `/api/auth/sign-in/email`, `/api/auth/verify-email?token=`, `/api/auth/get-session`,
`/api/stripe/checkout {item: starter|pro|refill_1000|refill_450}`, `/api/stripe/subscription`, `/api/stripe/subscription/cancel`,
`/api/razorpay/order {item: starter|pro|refill_1000|refill_450|starter_promo}`, `/api/razorpay/verify`, `/api/razorpay/webhook`,
`/api/chat`, `/api/image/generate`, `/api/image/analyze(-stream)`, `/api/linkedin/{generate-post,analyze,post,profile}`,
`/api/twitter/{post,profile}`, `/api/tiktok/{profile,video}`, `/api/instagram/reel`, `/api/transcribe`, `/api/voice/transcribe`, `/api/pdf/parse`, `/api/webpage/analyze`, `/api/templates/generate`

## Файлы

### Ядро
- `probe_full.py` — полный реверс API: 22 GET-эндпоинта + POST-пробы всех фич (chat/image/linkedin/transcribe/analyze)
- `probe_chat.py` — chat API shape (OpenAI-style `messages[]`) по всем моделям
- `remalt_autoreg.py` — авторег N акков (stdlib only, Python 3.9+): `python remalt_autoreg.py 5 [--threads 4] [--validate] [--stats]`
- `remalt_trial.py` — активатор Stripe-триала: sign-in API → модалка на /pricing → Stripe Elements iframes (number/expiry/cvc + address) → hCaptcha-гейт (mouse-click по чекбоксу) → verify /api/stripe/subscription. Карта из локального `cards.json`/`cards_live.json` (в репо НЕ хранится). Usage: `python remalt_trial.py [card_index] [email]`
- `remalt_gateway.py` — OpenAI-compatible шлюз поверх пула акков (stdlib only, порт 8400): `/v1/models`, `/v1/chat/completions` (только план-акки, failover по пулу), `/v1/analyze` (бесплатный webpage/analyze без плана), `/` дашборд. Ключ: env `REMALT_GATEWAY_KEY` или `gateway_key.txt`. Фоновый монитор плана каждые 5 мин через `/api/stripe/subscription`.
- `gen_check.py` — генератор карт из BIN (Luhn) + чекер через Stripe `/v1/payment_methods`. Usage: `STRIPE_PK=pk_live_xxx python gen_check.py 20` → `cards_live.json` (LIVE = токенизируется, не гарантия баланса).

### Альтернативные пути триала
- `hit_stripe.py` / `hit_checkout.py` — прямой Stripe checkout-session (API `/api/stripe/checkout {item: starter}` → cs_live URL → Camoufox fill). Мёртвый путь: PerimeterX блокирует submit на /c/pay.
- `rzp_activate.py` / `rzp_camoufox.py` / `rzp2.py` / `rzp3.py` — Razorpay `starter_promo` (1 мес бесплатно, ₹1800 после) + пробы UI на /pricing (deprecated — Razorpay-кнопка убрана, остался Stripe).
- `trial_modal.py` / `modal_check.py` / `rzp_dump.py` / `rzp_dump2.py` / `rzp_dump3.py` — диагностика фреймов/модалки: дамп Stripe Elements iframes, состояние кнопки триала.

### Разведка API
- `probe_api.py` — поверхность API по session token
- `probe_auth.py` — варианты auth (cookie plain/sig/both/bearer) — все 200 null без живой cookie jar
- `probe_session.py` — живой sign-in с cookie jar, инспекция set-cookie
- `probe_analyze.py` — webpage/analyze (бесплатная дырка без плана)
- `probe_free.py` — transcribe/linkedin free-эндпоинты
- `probe_order.py` — Razorpay order (поле `item`, не `plan`)
- `probe_trial.py` — триал-флоу разведка

### Утилиты
- `clean_zombies.py` — убийца зомби python/camoufox процессов (<5MB), из-за которых Camoufox не стартует (BrowserType.launch timeout)
- `card_dashboard.py` — веб-дахшорд для карт (stdlib, порт 8500): добавление карт вручную, генерация из любого BIN (Luhn), Stripe-чек по одной/всем, выбор аккаунта и запуск триала кнопкой, лог в реальном времени. Usage: `python card_dashboard.py` → http://127.0.0.1:8500
- `bins_catalog.json` — каталог рабочих BIN (MC/AMEX, привязка к таргетам) + 12 сгенерированных примеров карт

## Триал (проверено 2026-10)

- Кнопка `Start Starter trial` на /pricing открывает **встроенную модалку** (не редирект): Stripe Elements в iframes `js.stripe.com/v3/elements-inner-payment-*` (name=number/expiry/cvc) и `elements-inner-address-*` (name/country/addressLine1/locality/administrativeArea/postalCode)
- Сабмит: кнопка `Start free trial`; при submit Stripe эскалирует invisible hCaptcha → модалка «One more step... I am human» (iframe `newassets.hcaptcha.com`)
- hCaptcha-чекбокс кликается только **мышью по абсолютным координатам** iframe (locator.click внутри вложенного фрейма висит)
- `/c/pay` hosted-checkout (из `/api/stripe/checkout`) — мёртвый путь: submit блокируется PerimeterX (`px-cdn.net` CORS-коллектор), карта не отправляется
- Карта отклоняется → красный «An error occurred while processing your card», модалка закрывается сама = признак declines/успеха, проверять `/api/stripe/subscription`
- Кулдаун акка: после 2-3 неудачных сабмитов модалка перестаёт открываться (~10+ мин) — ротировать акки из пула

## Питфолы

- better-auth verify-ссылку брать из поля `magic_link` Voidash API, не regex'ом по html (html экранирует `&` → токен режется, verify 401)
- curl-регистрация проходит с User-Agent Mozilla; дефолтный curl UA не блокали, но лучше подставлять браузерный
- `/api/chat` с токеном без плана → `REMALT_FULL_ACCESS_REQUIRED`, 500 коинов `locked` до оплаты
- Stripe checkout для `starter` показывает $29 due today несмотря на "7-day free trial" — триал живёт в Razorpay `starter_promo`
- Кнопку `Start Starter trial` кликать через JS `scrollIntoView` + `page.mouse.click` по bounding-box центру — Playwright `scroll_into_view_if_needed` висит на Stripe re-render, а синтетический `element.click()` React игнорирует (модалка не открывается)
- Camoufox `BrowserType.launch: Timeout 180000ms` = зомби-процессы сожрали память → `clean_zombies.py`
- UA-карты (BIN 515462*) токенизируются в Stripe (LIVE на /v1/payment_methods), но подписочные платежи decline: «does not support this type of purchase» / «card was declined» — нужен international recurring friendly эмитент

For research purposes only.
