# بوت إشارات التداول الاحترافي — XAUUSD أولاً

## نطاق الأصول
القائمة ثابتة داخل النظام:
1. XAUUSD
2. BTCUSDT (مزود البيانات: BTC/USD)
3. EURUSD

لا توجد آلية تسمح للمستخدم العادي بإضافة أصول أخرى.

## ما الذي يفعله؟
- تحليل متعدد الأطر الزمنية.
- محرك Scoring من 100 نقطة.
- قرار افتراضي: NO TRADE.
- EMA20/50/200, RSI, MACD, ATR, Volume, VWAP.
- Market Structure: HH/HL/LH/LL + breakout/retest proxy.
- دعم/مقاومة وسيولة مبنية على بيانات السعر.
- SL مبني على Structure + ATR.
- TP1/TP2/TP3.
- R/R validation.
- فلتر سبريد.
- فلتر تذبذب/سوق متذبذب.
- فلتر أخبار قابل للربط بمزوّد موثوق، مع fail-closed عند تفعيله وعدم توفر البيانات.
- منع تكرار الإشارة والـovertrading.
- Daily signal cap.
- مراقبة إشارات تم إرسالها: Entry Hit / TP1 / TP2 / TP3 / SL / Break-even / Trailing / Invalidated.
- سجل أداء في SQLite.
- Profit Factor, Average R, Expectancy, Max Drawdown, Win Rate.
- Backtesting harness بدون استخدام مستقبل البيانات.
- صلاحيات Admin.
- فحص الصحة الداخلي.

> الوضع النهائي هنا "Signal/Alert Bot" وليس تنفيذ أوامر لدى الوسيط.

## التشغيل
Python 3.12+ موصى به.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
python -m app
```

## متغيرات البيئة
انسخ `.env.example` إلى `.env`.

الحد الأدنى:
- TELEGRAM_BOT_TOKEN
- TWELVE_DATA_API_KEY
- ADMIN_TELEGRAM_IDS

لإرسال التنبيهات التلقائية إلى محادثة/قناة:
- TARGET_CHAT_ID

اختياري:
- MIN_CONFIDENCE=80
- RISK_PER_TRADE=0.005
- MAX_DAILY_TRADES=5
- MAX_SPREAD_PCT=0.0015
- SCAN_SECONDS=60
- NEWS_FILTER_ENABLED=false
- NEWS_BLOCK_MINUTES=15
- TRAILING_STOP_ENABLED=true
- BREAKEVEN_R=1.0

## ملاحظة الأخبار
لا يتم اختلاق الأخبار. عند `NEWS_FILTER_ENABLED=true` يجب توفير Adapter لمزود موثوق. إذا فشل مزود الأخبار، النظام يمنع الدخول بدلاً من التخمين.

## نشر Railway
الملف `Procfile` يشغل:
`worker: python -m app`

ضع المتغيرات في Railway Variables وليس GitHub.

## لا تستخدم بأموال حقيقية مباشرة
يجب تشغيل backtest + validation + paper trading أولاً، ثم مراجعة الأداء خارج العينة.

## اختبار
```bash
pytest -q
```

## Backtest
```bash
python -m backtest.run --csv data/sample.csv --symbol XAUUSD
```

## اختيار الأصل من Telegram
عند الضغط على:
- صفقة أو توصية
- سكالبينج

سيظهر اختيار ثابت للأصول الثلاثة فقط:
- الذهب XAUUSD
- Bitcoin BTCUSDT
- EURUSD

بعد اختيار الأصل، يتم تحليل الأصل المختار فقط ولا ينتقل النظام تلقائياً إلى أصل آخر.
