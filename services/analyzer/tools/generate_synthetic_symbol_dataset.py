from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

import cv2
import numpy as np
import yaml


CLASSES = [
    "single_swing_door",
    "double_swing_door",
    "toilet",
    "bathtub",
    "shower",
    "cooktop",
    "sink",
]


def _canvas(size: int = 160) -> np.ndarray:
    return np.full((size, size), 255, dtype=np.uint8)


def _stroke(rng: random.Random) -> int:
    return rng.choice([2, 2, 3, 3, 4])


def _single_door(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    hinge = (36, 124)
    radius = rng.randint(72, 92)
    end = (hinge[0] + radius, hinge[1])
    cv2.line(img, hinge, end, 0, t)
    cv2.ellipse(img, hinge, (radius, radius), 0, 270, 360, 0, max(1, t - 1))
    cv2.circle(img, hinge, max(2, t), 0, -1)
    return img


def _double_door(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    left = (26, 124)
    right = (134, 124)
    half = rng.randint(48, 58)
    cv2.line(img, left, (left[0] + half, left[1] - half), 0, t)
    cv2.line(img, right, (right[0] - half, right[1] - half), 0, t)
    cv2.ellipse(img, left, (half, half), 0, 270, 360, 0, max(1, t - 1))
    cv2.ellipse(img, right, (half, half), 0, 180, 270, 0, max(1, t - 1))
    return img


def _toilet(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    cv2.rectangle(img, (52, 24), (108, 51), 0, t)
    cv2.ellipse(img, (80, 91), (32, 43), 0, 0, 360, 0, t)
    cv2.ellipse(img, (80, 92), (19, 28), 0, 0, 360, 0, max(1, t - 1))
    cv2.line(img, (57, 49), (103, 49), 0, max(1, t - 1))
    return img


def _bathtub(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    cv2.rectangle(img, (24, 42), (136, 118), 0, t)
    cv2.ellipse(img, (80, 80), (46, 27), 0, 0, 360, 0, max(1, t - 1))
    cv2.circle(img, (117, 82), 4, 0, max(1, t - 1))
    if rng.random() < .5:
        cv2.line(img, (34, 50), (34, 110), 0, max(1, t - 1))
    return img


def _shower(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    cv2.rectangle(img, (32, 32), (128, 128), 0, t)
    cv2.line(img, (38, 38), (122, 122), 0, max(1, t - 1))
    cv2.line(img, (122, 38), (38, 122), 0, max(1, t - 1))
    cv2.circle(img, (80, 80), rng.randint(5, 9), 0, max(1, t - 1))
    return img


def _cooktop(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    cv2.rectangle(img, (30, 38), (130, 122), 0, t)
    for cx, cy in ((57, 64), (103, 64), (57, 98), (103, 98)):
        radius = rng.randint(13, 18)
        cv2.circle(img, (cx, cy), radius, 0, max(1, t - 1))
        if rng.random() < .65:
            cv2.circle(img, (cx, cy), max(2, radius // 3), 0, max(1, t - 1))
    return img


def _sink(rng: random.Random) -> np.ndarray:
    img = _canvas()
    t = _stroke(rng)
    if rng.random() < .5:
        cv2.rectangle(img, (30, 42), (130, 118), 0, t)
        cv2.ellipse(img, (80, 82), (38, 25), 0, 0, 360, 0, max(1, t - 1))
    else:
        cv2.ellipse(img, (80, 82), (52, 35), 0, 0, 360, 0, t)
        cv2.ellipse(img, (80, 82), (34, 20), 0, 0, 360, 0, max(1, t - 1))
    cv2.circle(img, (80, 83), 4, 0, max(1, t - 1))
    cv2.line(img, (80, 48), (80, 62), 0, max(1, t - 1))
    cv2.line(img, (80, 48), (94, 48), 0, max(1, t - 1))
    return img


DRAWERS = [
    _single_door,
    _double_door,
    _toilet,
    _bathtub,
    _shower,
    _cooktop,
    _sink,
]


def _augment_patch(
    patch: np.ndarray,
    rng: random.Random,
    target_long: int,
) -> np.ndarray:
    ys, xs = np.nonzero(patch < 245)
    if not len(xs):
        return patch
    crop = patch[max(0, ys.min() - 6): min(patch.shape[0], ys.max() + 7),
                 max(0, xs.min() - 6): min(patch.shape[1], xs.max() + 7)]
    h, w = crop.shape
    scale = target_long / max(h, w)
    resized = cv2.resize(
        crop,
        (max(12, int(round(w * scale))), max(12, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
    )
    angle = rng.choice([0, 0, 0, 90, 180, 270]) + rng.uniform(-5.0, 5.0)
    rh, rw = resized.shape
    diag = int(math.ceil(math.hypot(rh, rw))) + 12
    work = np.full((diag, diag), 255, dtype=np.uint8)
    y0 = (diag - rh) // 2
    x0 = (diag - rw) // 2
    work[y0:y0 + rh, x0:x0 + rw] = resized
    matrix = cv2.getRotationMatrix2D((diag / 2, diag / 2), angle, 1.0)
    return cv2.warpAffine(work, matrix, (diag, diag), borderValue=255)


def _background(size: int, rng: random.Random) -> np.ndarray:
    base = np.full((size, size), rng.randint(247, 255), dtype=np.uint8)
    noise = np.random.default_rng(rng.randrange(2**32)).normal(
        0,
        rng.uniform(.4, 1.8),
        (size, size),
    )
    base = np.clip(base.astype(np.float32) + noise, 232, 255).astype(np.uint8)

    # Room-like CAD context. Prefer orthogonal wall networks over arbitrary
    # clutter so training tiles resemble architectural plan crops.
    margin = rng.randint(max(6, size // 40), max(10, size // 18))
    wall_shade = rng.randint(0, 55)
    wall_thickness = rng.choice([3, 4, 5, 6, 7])
    cv2.rectangle(
        base,
        (margin, margin),
        (size - margin - 1, size - margin - 1),
        wall_shade,
        wall_thickness,
    )

    verticals = sorted({
        rng.randint(size // 4, size * 3 // 4)
        for _ in range(rng.randint(1, 3))
    })
    horizontals = sorted({
        rng.randint(size // 4, size * 3 // 4)
        for _ in range(rng.randint(1, 3))
    })
    for x in verticals:
        y1 = margin + rng.randint(0, max(1, size // 12))
        y2 = size - margin - rng.randint(0, max(1, size // 12))
        cv2.line(base, (x, y1), (x, y2), wall_shade, wall_thickness)
    for y in horizontals:
        x1 = margin + rng.randint(0, max(1, size // 12))
        x2 = size - margin - rng.randint(0, max(1, size // 12))
        cv2.line(base, (x1, y), (x2, y), wall_shade, wall_thickness)

    # Secondary CAD linework: furniture, dimensions, centre lines and text.
    for _ in range(rng.randint(4, 11)):
        shade = rng.randint(45, 155)
        thickness = rng.choice([1, 1, 1, 2])
        x1 = rng.randint(margin + 2, max(margin + 3, size - margin - 30))
        y1 = rng.randint(margin + 2, max(margin + 3, size - margin - 30))
        x2 = min(size - margin - 2, x1 + rng.randint(14, max(15, size // 4)))
        y2 = min(size - margin - 2, y1 + rng.randint(10, max(11, size // 5)))
        if rng.random() < .55:
            cv2.rectangle(base, (x1, y1), (x2, y2), shade, thickness)
        elif rng.random() < .75:
            cv2.ellipse(
                base,
                ((x1 + x2) // 2, (y1 + y2) // 2),
                (max(3, (x2 - x1) // 2), max(3, (y2 - y1) // 2)),
                0,
                0,
                360,
                shade,
                thickness,
            )
        else:
            cv2.line(base, (x1, y1), (x2, y2), shade, thickness)

    for _ in range(rng.randint(0, 3)):
        cv2.putText(
            base,
            rng.choice(["2.80", "3.20", "4.50", "BED", "WC", "KITCHEN"]),
            (
                rng.randint(margin + 2, max(margin + 3, size // 2)),
                rng.randint(margin + 15, size - margin - 4),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            rng.uniform(.22, .38),
            rng.randint(70, 155),
            1,
            cv2.LINE_AA,
        )
    return base


def _draw_context_around_object(
    image: np.ndarray,
    class_id: int,
    box: tuple[int, int, int, int],
    rng: random.Random,
) -> None:
    x1, y1, x2, y2 = box
    h, w = image.shape
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    shade = rng.randint(0, 60)
    thickness = rng.choice([3, 4, 5, 6])

    if class_id in {0, 1}:
        # Swing doors belong in a wall opening. Add wall stubs outside the
        # labelled door box, never through it.
        span = rng.randint(max(18, max(bw, bh)), max(24, max(bw, bh) * 3))
        if bw >= bh:
            cy = (y1 + y2) // 2
            cv2.line(
                image,
                (max(0, x1 - span), cy),
                (max(0, x1 - 2), cy),
                shade,
                thickness,
            )
            cv2.line(
                image,
                (min(w - 1, x2 + 2), cy),
                (min(w - 1, x2 + span), cy),
                shade,
                thickness,
            )
        else:
            cx = (x1 + x2) // 2
            cv2.line(
                image,
                (cx, max(0, y1 - span)),
                (cx, max(0, y1 - 2)),
                shade,
                thickness,
            )
            cv2.line(
                image,
                (cx, min(h - 1, y2 + 2)),
                (cx, min(h - 1, y2 + span)),
                shade,
                thickness,
            )
        return

    # Fixtures usually sit close to one or two room walls.
    side = rng.choice(["top", "bottom", "left", "right"])
    gap = rng.randint(3, max(4, min(14, max(bw, bh) // 3 + 2)))
    extension = rng.randint(max(10, max(bw, bh) // 2), max(18, max(bw, bh) * 2))
    if side == "top":
        y = max(0, y1 - gap)
        cv2.line(
            image,
            (max(0, x1 - extension), y),
            (min(w - 1, x2 + extension), y),
            shade,
            thickness,
        )
    elif side == "bottom":
        y = min(h - 1, y2 + gap)
        cv2.line(
            image,
            (max(0, x1 - extension), y),
            (min(w - 1, x2 + extension), y),
            shade,
            thickness,
        )
    elif side == "left":
        x = max(0, x1 - gap)
        cv2.line(
            image,
            (x, max(0, y1 - extension)),
            (x, min(h - 1, y2 + extension)),
            shade,
            thickness,
        )
    else:
        x = min(w - 1, x2 + gap)
        cv2.line(
            image,
            (x, max(0, y1 - extension)),
            (x, min(h - 1, y2 + extension)),
            shade,
            thickness,
        )



def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw = max(0, min(ax2, bx2) - max(ax1, bx1))
    ih = max(0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    if not inter:
        return 0.0
    aa = max(1, (ax2 - ax1) * (ay2 - ay1))
    bb = max(1, (bx2 - bx1) * (by2 - by1))
    return inter / min(aa, bb)


def _place(
    image: np.ndarray,
    patch: np.ndarray,
    rng: random.Random,
    occupied: list[tuple[int, int, int, int]],
) -> tuple[tuple[int, int, int, int], np.ndarray] | None:
    ys, xs = np.nonzero(patch < 245)
    if not len(xs):
        return None
    patch = patch[max(0, ys.min() - 2): ys.max() + 3, max(0, xs.min() - 2): xs.max() + 3]
    ph, pw = patch.shape
    h, w = image.shape
    if ph >= h - 8 or pw >= w - 8:
        return None
    for _ in range(40):
        x = rng.randint(4, w - pw - 4)
        y = rng.randint(4, h - ph - 4)
        mask = patch < 245
        ys2, xs2 = np.nonzero(mask)
        box = (x + int(xs2.min()), y + int(ys2.min()), x + int(xs2.max()) + 1, y + int(ys2.max()) + 1)
        if any(_overlap(box, other) > .22 for other in occupied):
            continue
        roi = image[y:y + ph, x:x + pw]
        roi[mask] = np.minimum(roi[mask], patch[mask])
        return box, image
    return None


def _write_sample(
    image_path: Path,
    label_path: Path,
    rng: random.Random,
    size: int,
    min_objects: int,
    max_objects: int,
) -> None:
    image = _background(size, rng)
    labels: list[tuple[int, tuple[int, int, int, int]]] = []
    occupied: list[tuple[int, int, int, int]] = []

    # Blank negatives must truly contain no target symbols. The previous
    # generator cleared labels after drawing targets, which accidentally
    # taught the detector that real symbols were background.
    blank_negative = rng.random() < .08
    object_count = 0 if blank_negative else rng.randint(min_objects, max_objects)

    for _ in range(object_count):
        class_id = rng.randrange(len(CLASSES))
        base = DRAWERS[class_id](rng)
        if rng.random() < .78:
            target_long = rng.randint(
                max(12, size // 26),
                max(28, size // 8),
            )
        else:
            target_long = rng.randint(
                max(24, size // 12),
                max(44, size // 5),
            )
        patch = _augment_patch(base, rng, target_long)
        placed = _place(image, patch, rng, occupied)
        if placed is None:
            continue
        box, image = placed
        occupied.append(box)
        labels.append((class_id, box))
        _draw_context_around_object(image, class_id, box, rng)

    # Light scan/print artifacts after target placement.
    if rng.random() < .45:
        image = cv2.GaussianBlur(image, (3, 3), rng.uniform(.15, .55))
    if rng.random() < .35:
        kernel = np.ones((2, 2), np.uint8)
        if rng.random() < .5:
            image = cv2.erode(image, kernel, iterations=1)
        else:
            image = cv2.dilate(image, kernel, iterations=1)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(image_path), image)
    rows = []
    for class_id, (x1, y1, x2, y2) in labels:
        cx = ((x1 + x2) / 2) / size
        cy = ((y1 + y2) / 2) / size
        bw = (x2 - x1) / size
        bh = (y2 - y1) / size
        rows.append(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    label_path.write_text(
        "\n".join(rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def generate(output: Path, train_count: int, val_count: int, size: int, seed: int) -> Path:
    rng = random.Random(seed)
    for split, count in (("train", train_count), ("val", val_count)):
        for index in range(count):
            sample_rng = random.Random(rng.randrange(2**63))
            _write_sample(
                output / "images" / split / f"{index:05d}.png",
                output / "labels" / split / f"{index:05d}.txt",
                sample_rng,
                size,
                1 if split == "train" else 1,
                5 if split == "train" else 4,
            )

    yaml_path = output / "data.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(output.resolve()),
                "train": "images/train",
                "val": "images/val",
                "names": {index: name for index, name in enumerate(CLASSES)},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return yaml_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train", type=int, default=1400)
    parser.add_argument("--val", type=int, default=280)
    parser.add_argument("--size", type=int, default=384)
    parser.add_argument("--seed", type=int, default=240922)
    args = parser.parse_args()
    path = generate(args.output, args.train, args.val, args.size, args.seed)
    print(path)


if __name__ == "__main__":
    main()
