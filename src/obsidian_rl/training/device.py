"""Torch device detection. Reports capability; never alters global CUDA state."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DeviceReport:
    torch_version: str
    cuda_available: bool
    cuda_version: str | None
    device_name: str | None
    total_vram_mb: int | None
    selected_device: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_device(prefer: str = "auto") -> DeviceReport:
    """prefer: 'auto' | 'cpu' | 'cuda'. Falls back to CPU with an honest report."""
    import torch

    cuda_ok = bool(torch.cuda.is_available())
    name: str | None = None
    vram: int | None = None
    cuda_version: str | None = getattr(torch.version, "cuda", None)
    if cuda_ok:
        props = torch.cuda.get_device_properties(0)
        name = props.name
        vram = int(props.total_memory // (1024 * 1024))
    if prefer == "cpu":
        selected = "cpu"
    elif prefer == "cuda":
        if not cuda_ok:
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")
        selected = "cuda"
    else:
        selected = "cuda" if cuda_ok else "cpu"
    return DeviceReport(
        torch_version=torch.__version__,
        cuda_available=cuda_ok,
        cuda_version=cuda_version,
        device_name=name,
        total_vram_mb=vram,
        selected_device=selected,
    )
