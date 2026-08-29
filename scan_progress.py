from __future__ import annotations

from dataclasses import dataclass, field
import re


COMPONENTS = (
    "core", "daily_trade", "short_term", "medium_term", "under_50",
    "high_movement", "watchlist", "portfolio", "performance",
)
TERMINAL_STATES = {"TAMAMLANDI", "HATA", "IPTAL"}
LEGACY_PROGRESS = re.compile(r"(?P<done>\d+)\s*/\s*(?P<total>\d+)\s+(?:teknik tamamland[ıi]|atland[ıi]|hata)", re.IGNORECASE)


@dataclass
class ProgressEvent:
    scan_id: str
    phase: str
    completed: int
    total: int
    message: str


def parse_progress_line(line: str) -> ProgressEvent | None:
    if not line.startswith("PROGRESS|"):
        return None
    parts = line.rstrip("\r\n").split("|", 5)
    if len(parts) != 6:
        return None
    try:
        completed, total = int(parts[3]), int(parts[4])
    except ValueError:
        return None
    if completed < 0 or total < 0:
        return None
    return ProgressEvent(parts[1], parts[2], completed, total, parts[5])


@dataclass
class ScanCoordinator:
    scan_id: str
    components: dict[str, str] = field(default_factory=lambda: {name: "BEKLIYOR" for name in COMPONENTS})
    stock_completed: int = 0
    stock_total: int = 0
    stock_valid: int = 0
    stock_failed: int = 0
    component_progress: dict[str, tuple[int, int]] = field(default_factory=dict)
    phase: str = "prepare"
    message: str = "Tarama hazırlanıyor"
    _percent: int = 0

    def start_component(self, name: str) -> None:
        if name in self.components and self.components[name] == "BEKLIYOR":
            self.components[name] = "CALISIYOR"

    def finish_component(self, name: str, state: str = "TAMAMLANDI") -> None:
        if name not in self.components:
            raise KeyError(name)
        if state not in TERMINAL_STATES:
            raise ValueError(state)
        self.components[name] = state
        done, total = self.component_progress.get(name, (0, 1))
        self.component_progress[name] = (max(done, total), max(1, total))
        self._recalculate()

    def update_component_progress(self, name: str, completed: int, total: int, message: str) -> None:
        if name not in self.components or self.components[name] in TERMINAL_STATES:
            return
        total = max(1, int(total))
        old_done, old_total = self.component_progress.get(name, (0, total))
        self.component_progress[name] = (max(old_done, min(int(completed), total)), max(old_total, total))
        self.phase, self.message = name, message
        self._recalculate()

    def finish_stock_work(self) -> None:
        """Kesin basarili core cikisinda kayip stdout olaylarini tamamla."""
        if self.stock_total > 0:
            self.stock_completed = self.stock_total
        self._recalculate()

    def accept_line(self, line: str) -> bool:
        event = parse_progress_line(line)
        if event is not None:
            if event.scan_id != self.scan_id:
                return False
            self.phase, self.message = event.phase, event.message
            # Bu olay yalniz ana analiz surecinin bittigini bildirir. Merkezi
            # tarama, diger bolumler de sonlanmadan tamamlanmis sayilamaz.
            if event.phase in {"complete", "core_complete"} and not self.all_terminal:
                self.phase = "transfer"
                self.message = "Ana tarama tamamlandı; bölümler hazırlanıyor"
            if event.phase == "stocks":
                self.stock_total = max(self.stock_total, event.total)
                self.stock_completed = max(self.stock_completed, min(event.completed, self.stock_total))
            elif event.phase == "universe":
                self.stock_total = max(self.stock_total, event.total)
            elif event.phase in self.components:
                self.update_component_progress(event.phase, event.completed, event.total, event.message)
            self._recalculate()
            return True
        legacy = LEGACY_PROGRESS.search(line)
        if legacy:
            completed, total = int(legacy.group("done")), int(legacy.group("total"))
            self.stock_total = max(self.stock_total, total)
            self.stock_completed = max(self.stock_completed, min(completed, self.stock_total))
            self.phase, self.message = "stocks", "Hisseler analiz ediliyor"
            self._recalculate()
            return True
        return False

    def _recalculate(self) -> None:
        auxiliary = [name for name in COMPONENTS if name != "core"]
        total_units = max(1, self.stock_total)
        completed_units = min(self.stock_completed, max(1, self.stock_total))
        for name in auxiliary:
            done, total = self.component_progress.get(name, (0, 1))
            total = max(1, total)
            total_units += total
            completed_units += total if self.components[name] in TERMINAL_STATES else min(done, total)
        candidate = int(completed_units * 100 / total_units)
        if not self.all_terminal:
            candidate = min(candidate, 99)
        else:
            candidate = 100
        self._percent = max(self._percent, candidate)

    @property
    def percent(self) -> int:
        return self._percent

    @property
    def all_terminal(self) -> bool:
        return all(state in TERMINAL_STATES for state in self.components.values())

    @property
    def any_error(self) -> bool:
        return any(state == "HATA" for state in self.components.values())
