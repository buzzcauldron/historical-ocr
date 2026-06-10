"""Lightweight ResNet page classifier: print vs manuscript."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

MaterialLabel = Literal["print", "manuscript"]
CLASS_NAMES: tuple[MaterialLabel, ...] = ("print", "manuscript")


@dataclass(frozen=True)
class PageCnnCheckpoint:
    path: Path
    image_size: int
    classes: tuple[MaterialLabel, ...]
    val_accuracy: float | None = None


def torch_available() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def build_model(num_classes: int = 2, *, backbone: str = "resnet18"):
    import torch.nn as nn
    from torchvision import models

    if backbone != "resnet18":
        raise ValueError(f"Unsupported backbone: {backbone}")

    weights = None
    net = models.resnet18(weights=weights)
    net.conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)
    net.fc = nn.Linear(net.fc.in_features, num_classes)
    return net


def _image_transform(image_size: int, train: bool):
    from torchvision import transforms

    ops = [
        transforms.Grayscale(num_output_channels=1),
        transforms.Resize((image_size, image_size)),
    ]
    if train:
        ops.extend(
            [
                transforms.RandomAffine(degrees=2, translate=(0.02, 0.02), scale=(0.95, 1.05)),
                transforms.RandomAutocontrast(),
            ],
        )
    ops.append(transforms.ToTensor())
    ops.append(transforms.Normalize(mean=[0.5], std=[0.5]))
    return transforms.Compose(ops)


def _iter_class_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    rows: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}:
            continue
        try:
            from PIL import Image

            with Image.open(path) as im:
                im.verify()
        except Exception:
            continue
        rows.append(path)
    return rows


def _collect_labeled_images(
    data_dir: Path,
    *,
    extra_dirs: list[Path] | None = None,
) -> list[tuple[Path, int]]:
    roots = [data_dir, *(extra_dirs or [])]
    rows: list[tuple[Path, int]] = []
    seen: set[Path] = set()
    for root in roots:
        for label in CLASS_NAMES:
            folder = root / label
            idx = CLASS_NAMES.index(label)
            for path in _iter_class_images(folder):
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                rows.append((path, idx))
    return rows


def train_page_cnn(
    data_dir: Path,
    out_path: Path,
    *,
    extra_dirs: list[Path] | None = None,
    epochs: int = 15,
    batch_size: int = 16,
    lr: float = 1e-3,
    image_size: int = 224,
    val_fraction: float = 0.2,
    seed: int = 42,
    log_fn: Callable[[str], None] | None = None,
) -> PageCnnCheckpoint:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, Dataset, Subset

    labeled = _collect_labeled_images(data_dir, extra_dirs=extra_dirs)
    if len(labeled) < 4:
        roots = [str(data_dir)] + [str(p) for p in (extra_dirs or [])]
        raise ValueError(
            f"Need at least 4 labeled images under {{print,manuscript}}/ in {roots} "
            f"(found {len(labeled)})",
        )

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    class _PageDataset(Dataset):
        def __init__(self, rows: list[tuple[Path, int]], train: bool) -> None:
            self.rows = rows
            self.transform = _image_transform(image_size, train=train)

        def __len__(self) -> int:
            return len(self.rows)

        def __getitem__(self, index: int):
            from PIL import Image

            path, label = self.rows[index]
            with Image.open(path) as im:
                tensor = self.transform(im.convert("RGB"))
            return tensor, label

    rng = torch.Generator().manual_seed(seed)
    indices = torch.randperm(len(labeled), generator=rng).tolist()
    n_val = max(1, int(len(labeled) * val_fraction))
    val_idx = set(indices[:n_val])
    train_rows = [labeled[i] for i in range(len(labeled)) if i not in val_idx]
    val_rows = [labeled[i] for i in range(len(labeled)) if i in val_idx]

    train_loader = DataLoader(
        _PageDataset(train_rows, train=True),
        batch_size=min(batch_size, len(train_rows)),
        shuffle=True,
    )
    val_loader = DataLoader(
        _PageDataset(val_rows, train=False),
        batch_size=min(batch_size, len(val_rows)),
        shuffle=False,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(len(CLASS_NAMES)).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()

    best_acc = 0.0
    best_state = None

    for epoch in range(1, epochs + 1):
        model.train()
        running_loss = 0.0
        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item())

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for batch_x, batch_y in val_loader:
                batch_x = batch_x.to(device)
                batch_y = batch_y.to(device)
                preds = model(batch_x).argmax(dim=1)
                correct += int((preds == batch_y).sum().item())
                total += int(batch_y.size(0))
        acc = correct / max(total, 1)
        _log(
            f"epoch {epoch}/{epochs}  loss={running_loss / max(len(train_loader), 1):.4f}  "
            f"val_acc={acc:.3f}  ({len(train_rows)} train / {len(val_rows)} val)",
        )
        if acc >= best_acc:
            best_acc = acc
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state_dict": best_state,
        "classes": list(CLASS_NAMES),
        "image_size": image_size,
        "backbone": "resnet18",
        "val_accuracy": best_acc,
        "train_count": len(train_rows),
        "val_count": len(val_rows),
        "data_dir": str(data_dir.resolve()),
        "extra_dirs": [str(p.resolve()) for p in (extra_dirs or [])],
    }
    import torch

    torch.save(payload, out_path)
    _log(f"saved {out_path} (val_acc={best_acc:.3f})")
    return PageCnnCheckpoint(
        path=out_path,
        image_size=image_size,
        classes=CLASS_NAMES,
        val_accuracy=best_acc,
    )


def load_checkpoint(path: Path) -> tuple[object, PageCnnCheckpoint]:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    classes = tuple(payload.get("classes", CLASS_NAMES))
    image_size = int(payload.get("image_size", 224))
    model = build_model(len(classes))
    model.load_state_dict(payload["state_dict"])
    model.eval()
    meta = PageCnnCheckpoint(
        path=path,
        image_size=image_size,
        classes=classes,  # type: ignore[arg-type]
        val_accuracy=payload.get("val_accuracy"),
    )
    return model, meta


def predict_image(
    model: object,
    meta: PageCnnCheckpoint,
    image_path: Path,
) -> tuple[MaterialLabel, float]:
    import torch
    from PIL import Image

    transform = _image_transform(meta.image_size, train=False)
    with Image.open(image_path) as im:
        tensor = transform(im.convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        logits = model(tensor)  # type: ignore[operator]
        probs = torch.softmax(logits, dim=1)[0]
        idx = int(probs.argmax().item())
        score = float(probs[idx].item())
    return meta.classes[idx], score


def predict_image_path(
    model_path: Path,
    image_path: Path,
) -> tuple[MaterialLabel, float]:
    model, meta = load_checkpoint(model_path)
    return predict_image(model, meta, image_path)


def checkpoint_summary(path: Path) -> dict:
    import torch

    payload = torch.load(path, map_location="cpu", weights_only=False)
    return {
        "path": str(path),
        "classes": payload.get("classes", list(CLASS_NAMES)),
        "image_size": payload.get("image_size", 224),
        "val_accuracy": payload.get("val_accuracy"),
        "train_count": payload.get("train_count"),
        "val_count": payload.get("val_count"),
        "data_dir": payload.get("data_dir"),
    }
