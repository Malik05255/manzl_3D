# نشر منزل H كرابط

النشر الإنتاجي يتم يدويًا عبر GitHub Actions workflow باسم **Deploy Manzil H** حتى لا تُكشف المفاتيح داخل المستودع.

## GitHub Secrets المطلوبة

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`
- `MANZIL_INTERNAL_TOKEN`

يجب أن تكون قيمة `MANZIL_INTERNAL_TOKEN` نفسها مضبوطة في خدمة الـAnalyzer المنشورة.

## GitHub Variables المطلوبة

- `MANZIL_D1_DATABASE_ID`
- `MANZIL_ANALYZER_URL`
- `MANZIL_API_PUBLIC_URL`
- `MANZIL_WEB_ORIGIN`
- `MANZIL_PAGES_PROJECT`

اختياريًا يمكن تخصيص:

- `MANZIL_D1_DATABASE_NAME` — الافتراضي `manzil-h`
- `MANZIL_R2_BUCKET` — الافتراضي `manzil-h-assets`
- `MANZIL_ANALYZE_QUEUE` — الافتراضي `manzil-h-analysis`

## ما ينفذه الـWorkflow

1. يتحقق من الإعدادات المطلوبة.
2. يولد إعداد Worker بدون حفظ أسرار في Git.
3. يطبق D1 migrations على قاعدة البيانات البعيدة.
4. يضبط `INTERNAL_TOKEN` كـWorker secret.
5. ينشر Cloudflare Worker API.
6. يبني واجهة PWA باستخدام عنوان API الإنتاجي.
7. ينشر الواجهة على Cloudflare Pages.
8. يفحص `/health` و`/ready`.
9. يشغل رحلة E2E الفعلية: رفع → تحليل → Preview → حفظ → Restore.
10. يكتب روابط Web/API/Analyzer في GitHub Actions summary.

الـAnalyzer نفسه خدمة Python/OpenCV حاوية مستقلة، لذلك يجب نشر صورته في خدمة حاويات مناسبة ثم وضع رابطها في `MANZIL_ANALYZER_URL`.
