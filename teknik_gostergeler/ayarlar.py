from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorConfig:
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0
    bollinger_ddof: int = 0


@dataclass(frozen=True)
class StrategyConfig:
    strategy_id: str = "daily_trade_v10_2"
    version: str = "10.2.0"
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    min_risk_reward: float = 1.8
    probability_horizons_days: tuple[int, ...] = (1, 3, 5)
    primary_probability_horizon_days: int = 3
