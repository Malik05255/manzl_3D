# منزل H — Architecture

## الأساس

الصورة الأصلية ليست المشروع. بعد الرفع يتم إنشاء **Canonical FloorPlanModel** يحوي الجدران والغرف والفتحات والنصوص والمقياس والثقة. جميع التعديلات تحفظ كـRevisions من هذا النموذج.

```text
Web / PWA
   │
   ▼
Cloudflare Worker
   ├─ D1: metadata + revisions
   ├─ R2: source + canonical plan files
   └─ Queue
       │
       ▼
Managed Analyzer
   ├─ protected source pull
   ├─ PDF / image normalization
   ├─ Arabic + English OCR
   ├─ walls + rooms
   ├─ metric calibration
   ├─ confidence validation
   └─ geometry-aware edit proposals
```

Analyzer يسحب المصدر من endpoint داخلي محمي بدل تمرير ملف كبير داخل Queue Worker، لتقليل ضغط الذاكرة وفصل التخزين عن الحوسبة.

## H Engineer

```text
Command
 → room resolution
 → metric constraints
 → adjacency search
 → candidate shared-wall moves
 → impact calculation
 → preview
 → server re-validation
 → user approval
 → revision
```

مثال: `عدل غرفة النوم إلى 5×5`. يولد المحرك بدائل حسب الغرف المجاورة واتجاه التوسعة. عند الاعتماد يعيد الخادم حساب الاقتراح، ولا يثق عميًا ببيانات Preview القادمة من المتصفح.

## قواعد الجودة

- لا يوجد تعديل بالمتر إذا لم يثبت المقياس.
- الاكتشاف منخفض الثقة لا يتحول إلى عنصر مؤكد.
- لا نخترع بابًا أو نافذة عند عدم كفاية الدليل.
- كل اعتماد ينتج Revision جديدة.
- المصدر الأصلي منفصل عن النموذج الهندسي.
- فهم اللغة يمكن تطويره بمزود AI لاحقًا، لكن القيود الهندسية تبقى مستقلة.

## المستقبل

الإنشاء من الصفر و3D سيستهلكان نفس FloorPlanModel. Renderer ثلاثي الأبعاد سيحوّل عناصر 2D نفسها إلى Meshes؛ لذلك لا يلزم هدم الأساس عند إضافة التجول الواقعي.
