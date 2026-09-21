# منزل H

محرر مخططات سحابي: ارفع PDF أو صورة، حوّلها إلى نموذج هندسي قابل للتعديل، ثم عدّل يدويًا أو عبر **H Engineer** مع معاينة أثر التغيير قبل اعتماده.

## المنفذ الآن

- PWA عربية Responsive للجوال والتابلت والكمبيوتر والشاشات العريضة.
- مسار: ابنِ مشروعك → تعديل مشروع → رفع → تحليل → منطقة التعديل.
- R2 للمصادر والنسخ الهندسية، وD1 للمشاريع وسجل النسخ.
- Queue لمعالجة المخططات خارج طلب المستخدم.
- Analyzer سحابي: PDF/Image + OCR عربي/إنجليزي + جدران + غرف + معايرة مقياس + درجات ثقة.
- H Engineer يدعم حاليًا أوامر المقاس مثل: `عدل غرفة النوم إلى 5×5`.
- كل اقتراح يظهر كـPreview ولا يُحفظ قبل الاعتماد.
- تحريك جدران يدويًا، Undo، وحفظ Revision.
- تحديث PWA دون حذف المشاريع السحابية.
- CI للواجهة والـAPI ومحرك التحليل.

## البنية

```text
apps/web             React + TypeScript + Vite PWA
apps/api             Cloudflare Worker + D1 + R2 + Queue
packages/contracts   Canonical FloorPlan contracts
services/analyzer    FastAPI + OpenCV + Tesseract + PyMuPDF
```

راجع `docs/ARCHITECTURE.md`.

## تشغيل سريع

```bash
npm install
npm run build
npm run dev:web
```

للـAnalyzer:

```bash
cd services/analyzer
pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
docker build -t manzil-h-analyzer .
```

أنشئ D1 وR2 وQueue، ثم انسخ `apps/api/wrangler.jsonc.example` إلى `wrangler.jsonc`. ضع نفس `INTERNAL_TOKEN` في Worker وAnalyzer.

> التصميم Free-first، لكن حصص الخدمات المجانية قابلة للتغيير. نموذج المشروع نفسه غير مربوط بمزود AI واحد.
