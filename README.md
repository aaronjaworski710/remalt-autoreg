# remalt-autoreg

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

- `remalt_autoreg.py` — авторег N акков (stdlib only, Python 3.9+): `python remalt_autoreg.py 5 [--threads 4] [--validate] [--stats]`
- `remalt_trial.py` — активатор Stripe-триала (7 дней): sign-in API → модалка на /pricing → Stripe Elements iframes (number/expiry/cvc + address) → hCaptcha-гейт (mouse-click по чекбоксу) → verify /api/stripe/subscription. Карта из локального `cards.json` (в репо НЕ хранится). Usage: `python remalt_trial.py [card_index] [email]`
- `remalt_gateway.py` — OpenAI-compatible шлюз поверх пула акков (stdlib only, порт 8400): `/v1/models`, `/v1/chat/completions` (только план-акки, failover по пулу), `/v1/analyze` (бесплатный webpage/analyze без плана), `/` дашборд. Ключ: env `REMALT_GATEWAY_KEY` или `gateway_key.txt`. Фоновый монитор плана каждые 5 мин через `/api/stripe/subscription`.
- `trial_probe.py` — разведка баланса/гейтов/триал-эндпоинтов по session token
- `rzp_camoufox.py` — старый флоу Razorpay checkout (deprecated — Razorpay-кнопка убрана с /pricing, остался только Stripe)

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

For research purposes only.
