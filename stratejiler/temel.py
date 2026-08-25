from __future__ import annotations
from typing import Any, Literal, Protocol, runtime_checkable


@runtime_checkable
class TradeStrategy(Protocol):
    strategy_id: str
    version: str
    status: Literal["experimental", "validated", "retired"]
    required_timeframes: tuple[str, ...]

    def compute_features(self, market_data: Any, config: Any) -> Any: ...
    def generate_signal(self, features: Any, config: Any) -> Any: ...
    def explain(self, signal: Any) -> str: ...


class StrategyRegistry:
    """Deneysel stratejileri ana karardan izole eden küçük kayıt defteri."""
    def __init__(self) -> None:
        self._strategies: dict[str, TradeStrategy] = {}

    def register(self, strategy: TradeStrategy) -> None:
        if not isinstance(strategy, TradeStrategy):
            raise TypeError("Strateji TradeStrategy sözleşmesini karşılamıyor")
        if strategy.strategy_id in self._strategies:
            raise ValueError(f"Tekrarlanan strateji kimliği: {strategy.strategy_id}")
        self._strategies[strategy.strategy_id] = strategy

    def get(self, strategy_id: str) -> TradeStrategy:
        return self._strategies[strategy_id]

    def validated(self) -> tuple[TradeStrategy, ...]:
        return tuple(item for item in self._strategies.values() if item.status == "validated")
