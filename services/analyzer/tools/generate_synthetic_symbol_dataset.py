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
    base = np.full((size, size), rng.randint(244, 255), dtype=np.uint8)
    noise = np.random.default_rng(rng.randrange(2**32)).normal(0, rng.uniform(.8, 3.0), (size, size))
    base = np.clip(base.astype(np.float32) + noise, 225, 255).astype(np.uint8)

    # Architectural linework distractors.
    for _ in range(rng.randint(5, 16)):
        thickness = rng.choice([1, 1, 2, 2, 3, 5])
        shade = rng.randint(0, 90)
        if rng.random() < .78:
            if rng.random() < .5:
                y = rng.randint(8, size - 9)
                x1 = rng.randint(0, max(0, size - 70))
                x2 = rng.randint(min(size - 1, x1 + 35), size - 1)
                cv2.line(base, (x1, y), (x2, y), shade, thickness)
            else:
                x = rng.randint(8, size - 9)
                y1 = rng.randint(0, max(0, size - 70))
                y2 = rng.randint(min(size - 1, y1 + 35), size - 1)
                cv2.line(base, (x, y1), (x, y2), shade, thickness)
        else:
            x1, y1 = rng.randint(0, size - 1), rng.randint(0, size - 1)
            length = rng.randint(30, max(31, size // 3))
            angle = rng.choice([30, 45, 60, 120, 135, 150])
            x2 = int(round(x1 + math.cos(math.radians(angle)) * length))
            y2 = int(round(y1 + math.sin(math.radians(angle)) * length))
            cv2.line(base, (x1, y1), (x2, y2), shade, thickness)

    # Furniture-like rectangles/circles and tiny dimension text.
    for _ in range(rng.randint(2, 8)):
        x1 = rng.randint(4, size - 50)
        y1 = rng.randint(4, size - 50)
        x2 = min(size - 4, x1 + rng.randint(20, 90))
        y2 = min(size - 4, y1 + rng.randint(12, 70))
        if rng.random() < .55:
            cv2.rectangle(base, (x1, y1), (x2, y2), rng.randint(50, 155), rng.choice([1, 1, 2]))
        else:
            cv2.ellipse(
                base,
                ((x1 + x2) // 2, (y1 + y2) // 2),
                (max(4, (x2 - x1) // 2), max(4, (y2 - y1) // 2)),
                0, 0, 360, rng.randint(50, 155), 1,
            )
    if rng.random() < .7:
        cv2.putText(
            base,
            f"{rng.randint(1,9)}.{rng.randint(0,99):02d}",
            (rng.randint(5, size // 2), rng.randint(25, size - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            rng.uniform(.25, .45),
            rng.randint(55, 140),
            1,
            cv2.LINE_AA,
        )
    return base


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

    object_count = rng.randint(min_objects, max_objects)
    for _ in range(object_count):
        class_id = rng.randrange(len(CLASSES))
        base = DRAWERS[class_id](rng)
        target_long = rng.randint(max(28, size // 11), max(48, size // 4))
        patch = _augment_patch(base, rng, target_long)
        placed = _place(image, patch, rng, occupied)
        if placed is None:
            continue
        box, image = placed
        occupied.append(box)
        labels.append((class_id, box))

    # Occasional blank/hard-negative frame.
    if rng.random() < .08:
        labels.clear()

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
    label_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")


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
