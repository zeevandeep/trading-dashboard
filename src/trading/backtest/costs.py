"""Indian transaction cost model — NSE equity delivery (CNC).

Components for a round-trip trade (buy then sell later) on NSE:
- Brokerage: Zerodha charges ₹0 for equity delivery. We still include a 0 line for transparency.
- STT: 0.1% on buy + 0.1% on sell (delivery)
- Exchange transaction charges: 0.00297% (NSE) per side
- SEBI charges: 0.0001% per side
- Stamp duty: 0.015% on buy side only (post-July 2020 regime)
- GST: 18% on (brokerage + exchange charges + SEBI)
- Slippage: modeled separately as a bps haircut on trade price

Returns per-side cost as a fraction of notional traded (not round-trip).
Source: Zerodha charge list, SEBI circulars (2020 stamp duty unification).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostConfig:
    """Cost configuration. All values as fractions (0.001 = 0.1% = 10 bps)."""

    brokerage_per_side: float = 0.0          # Zerodha = 0 for CNC
    stt_buy: float = 0.001                    # 0.1% on buy (delivery)
    stt_sell: float = 0.001                   # 0.1% on sell (delivery)
    exchange_charge_per_side: float = 0.0000297  # NSE transaction charge
    sebi_per_side: float = 0.000001            # 0.0001%
    stamp_duty_buy: float = 0.00015            # 0.015% on buy
    gst_on_charges: float = 0.18               # 18% on (brokerage + exchange + SEBI)
    slippage_per_side: float = 0.003           # 30 bps — conservative for smallcaps


def one_way_cost(side: str, cfg: CostConfig = CostConfig()) -> float:
    """Cost as fraction of traded notional for one side (buy or sell).

    side: "buy" or "sell"
    """
    side = side.lower()
    if side not in ("buy", "sell"):
        raise ValueError(f"side must be 'buy' or 'sell', got {side}")

    # Statutory charges
    stt = cfg.stt_buy if side == "buy" else cfg.stt_sell
    stamp = cfg.stamp_duty_buy if side == "buy" else 0.0
    exch = cfg.exchange_charge_per_side
    sebi = cfg.sebi_per_side
    brokerage = cfg.brokerage_per_side

    # GST applies to (brokerage + exchange + SEBI)
    gst = cfg.gst_on_charges * (brokerage + exch + sebi)

    # Slippage (execution quality haircut)
    slip = cfg.slippage_per_side

    return brokerage + stt + exch + sebi + stamp + gst + slip


def round_trip_cost(cfg: CostConfig = CostConfig()) -> float:
    """Full round-trip cost = buy cost + sell cost, as fraction of notional."""
    return one_way_cost("buy", cfg) + one_way_cost("sell", cfg)
