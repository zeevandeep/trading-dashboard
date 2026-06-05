"""Value + Quality composite signal.

Scores stocks on four factors:
  1. Earnings Yield (E/P) — higher = cheaper = better
  2. Return on Equity (ROE) — higher = better business
  3. Debt/Equity — lower = safer (inverted so higher rank = better)
  4. Earnings Growth — higher = growing faster

Each factor is cross-sectionally ranked (percentile), then combined into
an equal-weighted composite score. Stocks with missing data on any factor
are excluded.

Two modes:
  - **Live** (fetch_fundamentals): uses yfinance .info for current snapshot.
  - **Historical** (fetch_historical_fundamentals): uses yfinance annual
    financial statements (income_stmt + balance_sheet) for backtesting.
    Indian companies report March year-end; results are public by ~June,
    so a 3-month reporting lag is applied for point-in-time correctness.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from trading.utils.logging import setup_logging

log = setup_logging("value_quality")


def fetch_fundamentals(tickers: list[str], max_workers: int = 10) -> pd.DataFrame:
    """Fetch fundamental data for a list of tickers.

    Returns DataFrame with columns: ticker, pe, roe, de, earnings_growth, revenue_growth, market_cap.
    """
    results = []

    def _fetch_one(ticker: str) -> dict | None:
        try:
            yf_ticker = f"{ticker}.NS" if not ticker.endswith((".NS", ".BO")) else ticker
            info = yf.Ticker(yf_ticker).info
            if not info or info.get("regularMarketPrice") is None:
                return None
            return {
                "ticker": ticker,
                "pe": info.get("trailingPE"),
                "roe": info.get("returnOnEquity"),
                "de": info.get("debtToEquity"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "market_cap": info.get("marketCap"),
            }
        except Exception:
            return None

    log.info(f"Fetching fundamentals for {len(tickers)} tickers...")
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 25 == 0:
                log.info(f"  {done}/{len(tickers)} fetched...")
            result = future.result()
            if result:
                results.append(result)

    if not results:
        log.warning("No fundamentals fetched — yfinance returned no data")
        return pd.DataFrame()
    df = pd.DataFrame(results).set_index("ticker")
    log.info(f"Got fundamentals for {len(df)}/{len(tickers)} tickers")
    return df


def score_value_quality(fundamentals: pd.DataFrame) -> pd.Series:
    """Compute composite Value + Quality score.

    Returns a Series of scores indexed by ticker, higher = better.
    Stocks with missing data on key factors are dropped.
    """
    df = fundamentals.copy()

    # Compute Earnings Yield (inverse of P/E)
    df["earnings_yield"] = 1.0 / df["pe"]

    # Keep only stocks with all required factors
    required = ["earnings_yield", "roe", "de", "earnings_growth"]
    df = df.dropna(subset=required)

    # Remove negative P/E (loss-making companies)
    df = df[df["pe"] > 0]

    # Remove extreme outliers (top/bottom 1%)
    for col in required:
        lower = df[col].quantile(0.01)
        upper = df[col].quantile(0.99)
        df = df[(df[col] >= lower) & (df[col] <= upper)]

    if len(df) < 10:
        log.warning(f"Only {len(df)} stocks after filtering — too few for ranking")
        return pd.Series(dtype=float)

    # Rank each factor (percentile rank 0-1)
    # Higher is better for: earnings_yield, roe, earnings_growth
    # Lower is better for: de (so we invert)
    df["rank_ey"] = df["earnings_yield"].rank(pct=True)
    df["rank_roe"] = df["roe"].rank(pct=True)
    df["rank_de"] = (1.0 - df["de"].rank(pct=True))  # invert: low debt = high rank
    df["rank_eg"] = df["earnings_growth"].rank(pct=True)

    # Equal-weighted composite
    df["composite"] = (
        df["rank_ey"] + df["rank_roe"] + df["rank_de"] + df["rank_eg"]
    ) / 4.0

    scores = df["composite"].sort_values(ascending=False)
    log.info(f"Scored {len(scores)} stocks. Top 5: {list(scores.head().index)}")

    return scores


# ═══════════════════════════════════════════════════════════════════════════════
#  HISTORICAL FUNDAMENTALS (for backtesting)
# ═══════════════════════════════════════════════════════════════════════════════

REPORTING_LAG_MONTHS = 3  # Indian companies: March YE, results public by ~June

# Screener.in values are in Crores (1 Cr = 10^7 Rs)
_CR = 1e7


def _parse_screener_section(soup, section_name: str) -> dict[str, dict[str, float | None]]:
    """Parse a named section (P&L, Balance Sheet, etc.) from a Screener.in page."""
    from bs4 import BeautifulSoup  # noqa: F811

    for sec in soup.find_all("section"):
        h2 = sec.find("h2")
        if h2 and section_name.lower() in h2.text.strip().lower():
            tbl = sec.find("table", class_="data-table")
            if not tbl or not tbl.find("thead"):
                continue
            headers = [th.text.strip() for th in tbl.find("thead").find_all("th")][1:]
            data = {}
            for row in tbl.find("tbody").find_all("tr"):
                cells = row.find_all("td")
                label = cells[0].text.strip().replace("\xa0", " ")
                vals = []
                for c in cells[1:]:
                    txt = c.text.strip().replace(",", "").replace("%", "")
                    try:
                        vals.append(float(txt))
                    except ValueError:
                        vals.append(None)
                data[label] = dict(zip(headers, vals))
            return data
    return {}


def _parse_face_value(soup) -> float:
    """Extract face value from Screener.in company page."""
    for li in soup.find_all("li"):
        name = li.find("span", class_="name")
        value = li.find("span", class_="number")
        if name and "face value" in name.text.lower() and value:
            txt = value.text.strip().replace(",", "").replace("₹", "").strip()
            try:
                return float(txt)
            except ValueError:
                pass
    return 10.0  # default face value for most Indian companies


def _extract_from_screener(ticker: str) -> pd.DataFrame | None:
    """Fetch 10-15 years of annual fundamentals from Screener.in.

    Returns DataFrame indexed by fiscal year-end date with columns:
    net_income, equity, total_debt, shares, revenue (all in Rs, not Cr).
    """
    import time
    import requests
    from bs4 import BeautifulSoup

    # Try consolidated first; if too few years, fall back to standalone
    best_soup = None
    best_years = 0
    for suffix in ["/consolidated/", "/"]:
        url = f"https://www.screener.in/company/{ticker}{suffix}"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; JDQuant/1.0)"},
                timeout=15,
            )
            if resp.status_code != 200:
                continue
        except Exception:
            continue

        s = BeautifulSoup(resp.text, "html.parser")
        # Count P&L years
        for sec in s.find_all("section"):
            h2 = sec.find("h2")
            if h2 and "profit" in h2.text.lower():
                tbl = sec.find("table", class_="data-table")
                if tbl and tbl.find("thead"):
                    n = len(tbl.find("thead").find_all("th")) - 1
                    if n > best_years:
                        best_years = n
                        best_soup = s
                break
        if best_years >= 10:
            break  # consolidated has enough data

    if best_soup is None:
        return None

    soup = best_soup

    pl = _parse_screener_section(soup, "Profit & Loss")
    bs = _parse_screener_section(soup, "Balance Sheet")

    if not pl or not bs:
        return None

    face_value = _parse_face_value(soup)

    # Extract data keyed by "Mar YYYY"
    net_profit = pl.get("Net Profit +", {})
    sales = pl.get("Sales +", {})
    eq_capital = bs.get("Equity Capital", {})
    reserves = bs.get("Reserves", {})
    borrowings = bs.get("Borrowings +", {})

    if not net_profit:
        return None

    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    rows = []
    for period, ni_cr in net_profit.items():
        if ni_cr is None:
            continue

        parts = period.strip().split()
        if len(parts) != 2 or parts[0] not in month_map:
            continue

        try:
            year = int(parts[1])
        except ValueError:
            continue

        month = month_map[parts[0]]
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        dt = pd.Timestamp(year=year, month=month, day=last_day)

        rev_cr = sales.get(period)
        eq_cap_cr = eq_capital.get(period)
        res_cr = reserves.get(period)
        borrow_cr = borrowings.get(period)

        # Equity = Equity Capital + Reserves (in Cr)
        equity_cr = None
        if eq_cap_cr is not None and res_cr is not None:
            equity_cr = eq_cap_cr + res_cr

        # Shares = Equity Capital (Cr) * 1e7 / face_value
        shares = None
        if eq_cap_cr is not None and eq_cap_cr > 0:
            shares = eq_cap_cr * _CR / face_value

        rows.append({
            "date": dt,
            "net_income": ni_cr * _CR if ni_cr is not None else np.nan,
            "equity": equity_cr * _CR if equity_cr is not None else np.nan,
            "total_debt": borrow_cr * _CR if borrow_cr is not None else np.nan,
            "shares": shares if shares is not None else np.nan,
            "revenue": rev_cr * _CR if rev_cr is not None else np.nan,
        })

    if len(rows) < 2:
        return None

    df = pd.DataFrame(rows).set_index("date").sort_index()
    return df


def _mc_search(ticker: str) -> dict | None:
    """Resolve an NSE ticker to Moneycontrol's internal identifiers."""
    import requests

    try:
        resp = requests.get(
            "https://www.moneycontrol.com/mccode/common/autosuggestion_solr.php",
            params={"classic": "true", "query": ticker, "type": "1", "format": "json"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=10,
        )
        results = resp.json()
        for r in results:
            desc = r.get("pdt_dis_nm", "")
            if f", {ticker}," in desc or f", {ticker}<" in desc:
                url = r["link_src"]
                parts = url.split("/")
                sector = parts[5] if len(parts) > 5 else ""
                company = parts[6] if len(parts) > 6 else ""
                return {"sc_id": r["sc_id"], "sector": sector, "company": company}
    except Exception:
        pass
    return None


def _parse_mc_table(soup) -> dict[str, list[tuple[str, float | None]]]:
    """Parse a Moneycontrol financial table. Returns {row_label: [(year, value), ...]}."""
    tbl = soup.find("table", class_="mctable1")
    if not tbl:
        return {}

    rows = tbl.find_all("tr")
    if not rows:
        return {}

    # Header row has years like "Mar 26", "Mar 25", etc.
    header_cells = [td.text.strip() for td in rows[0].find_all("td")]
    years = header_cells[1:]  # skip the label column

    data = {}
    for row in rows[1:]:
        cells = [td.text.strip() for td in row.find_all("td")]
        if len(cells) < 2:
            continue
        label = cells[0]
        vals = []
        for i, yr in enumerate(years):
            if i + 1 < len(cells):
                txt = cells[i + 1].replace(",", "").replace("%", "").strip()
                try:
                    vals.append((yr, float(txt)))
                except ValueError:
                    vals.append((yr, None))
        data[label] = vals

    return data


def _extract_from_moneycontrol(ticker: str) -> pd.DataFrame | None:
    """Fetch 10-15 years of annual fundamentals from Moneycontrol.

    Returns DataFrame indexed by fiscal year-end date with columns:
    net_income, equity, total_debt, shares, revenue (all in Rs).
    """
    import requests
    from bs4 import BeautifulSoup

    # Step 1: Resolve ticker to Moneycontrol IDs
    mc = _mc_search(ticker)
    if not mc:
        return None

    sc_id = mc["sc_id"]
    sector = mc["sector"]
    company = mc["company"]

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    # Step 2: Fetch P&L and Balance Sheet across 3 pages (5 years each = 15 years)
    pl_data: dict[str, float | None] = {}
    bs_eq_cap: dict[str, float | None] = {}
    bs_reserves: dict[str, float | None] = {}
    bs_lt_borrow: dict[str, float | None] = {}
    bs_st_borrow: dict[str, float | None] = {}
    bs_bonus_eq: dict[str, float | None] = {}

    import time

    for page in [1, 2, 3]:
        # P&L
        try:
            url_pl = f"https://www.moneycontrol.com/financials/{company}/profit-lossVI/{sc_id}/{page}"
            resp = requests.get(url_pl, headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                data = _parse_mc_table(soup)

                for label, vals in data.items():
                    ll = label.lower()
                    if "profit/loss for the period" in ll or ("net profit" in ll and "minority" not in ll):
                        for yr, v in vals:
                            if yr and v is not None:
                                pl_data[yr] = v
        except Exception:
            pass

        time.sleep(0.3)

        # Balance Sheet
        try:
            url_bs = f"https://www.moneycontrol.com/financials/{company}/balance-sheetVI/{sc_id}/{page}"
            resp = requests.get(url_bs, headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                data = _parse_mc_table(soup)

                for label, vals in data.items():
                    ll = label.lower()
                    if "equity share capital" in ll:
                        for yr, v in vals:
                            if yr and v is not None:
                                bs_eq_cap[yr] = v
                    elif "total reserves and surplus" in ll:
                        for yr, v in vals:
                            if yr and v is not None:
                                bs_reserves[yr] = v
                    elif "long term borrowings" in ll and "current" not in ll:
                        for yr, v in vals:
                            if yr and v is not None:
                                bs_lt_borrow[yr] = v
                    elif "short term borrowings" in ll:
                        for yr, v in vals:
                            if yr and v is not None:
                                bs_st_borrow[yr] = v
                    elif "bonus equity" in ll:
                        for yr, v in vals:
                            if yr and v is not None:
                                bs_bonus_eq[yr] = v
        except Exception:
            pass

        time.sleep(0.3)

    if not pl_data or not bs_eq_cap:
        return None

    # Step 3: Build the DataFrame
    # Moneycontrol values are in Crores
    # Face value: derive from equity capital and bonus equity share capital
    # Default face value = 10 (most common in India)
    face_value = 10.0

    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    result_rows = []
    for period, ni_cr in pl_data.items():
        parts = period.strip().split()
        if len(parts) != 2 or parts[0] not in month_map:
            continue
        try:
            yr_short = int(parts[1])
        except ValueError:
            continue

        # Convert 2-digit year to 4-digit
        year = yr_short + 2000 if yr_short < 100 else yr_short
        month = month_map[parts[0]]
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        dt = pd.Timestamp(year=year, month=month, day=last_day)

        eq_cap_cr = bs_eq_cap.get(period)
        res_cr = bs_reserves.get(period)
        lt_borrow = bs_lt_borrow.get(period, 0) or 0
        st_borrow = bs_st_borrow.get(period, 0) or 0

        equity_cr = None
        if eq_cap_cr is not None and res_cr is not None:
            equity_cr = eq_cap_cr + res_cr

        shares = None
        if eq_cap_cr is not None and eq_cap_cr > 0:
            shares = eq_cap_cr * _CR / face_value

        total_debt_cr = lt_borrow + st_borrow

        result_rows.append({
            "date": dt,
            "net_income": ni_cr * _CR if ni_cr is not None else np.nan,
            "equity": equity_cr * _CR if equity_cr is not None else np.nan,
            "total_debt": total_debt_cr * _CR,
            "shares": shares if shares is not None else np.nan,
            "revenue": np.nan,
        })

    if len(result_rows) < 2:
        return None

    df = pd.DataFrame(result_rows).set_index("date").sort_index()
    return df


def _extract_fundamentals(ticker: str) -> pd.DataFrame | None:
    """Try Screener.in first, fall back to Moneycontrol."""
    df = _extract_from_screener(ticker)
    if df is not None and len(df) >= 2:
        return df
    df = _extract_from_moneycontrol(ticker)
    return df


def fetch_historical_fundamentals(
    tickers: list[str],
    max_workers: int = 10,
    cache_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch annual financial statements for all tickers from Screener.in.

    Returns {ticker: DataFrame} where each DataFrame has columns:
    net_income, equity, total_debt, shares, revenue — indexed by fiscal year-end.
    Typically provides 10-15 years of data (vs ~5 from yfinance).

    Results are cached to parquet if cache_dir is provided.
    """
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / "historical_fundamentals.parquet"
        if cache_file.exists():
            log.info(f"Loading cached historical fundamentals from {cache_file}")
            all_df = pd.read_parquet(cache_file)
            result = {}
            for ticker in all_df["ticker"].unique():
                result[ticker] = all_df[all_df["ticker"] == ticker].drop(columns=["ticker"]).set_index("date")
            # Check if cache has sufficient history (>8 years for most tickers)
            avg_years = sum(len(df) for df in result.values()) / max(len(result), 1)
            if avg_years >= 8:
                log.info(f"Loaded cached fundamentals for {len(result)} tickers (~{avg_years:.0f} years avg)")
                return result
            else:
                log.info(f"Cache has only ~{avg_years:.0f} years avg — refetching from Screener.in")

    result: dict[str, pd.DataFrame] = {}

    import time

    log.info(f"Fetching historical fundamentals for {len(tickers)} tickers (Screener.in → Moneycontrol fallback)...")
    for i, ticker in enumerate(tickers):
        if (i + 1) % 25 == 0:
            log.info(f"  {i + 1}/{len(tickers)} fetched ({len(result)} OK)...")
        df = _extract_fundamentals(ticker)
        if df is not None and len(df) >= 2:
            result[ticker] = df
        time.sleep(0.5)

    log.info(f"Got historical fundamentals for {len(result)}/{len(tickers)} tickers")

    if cache_dir is not None and result:
        frames = []
        for ticker, df in result.items():
            tmp = df.reset_index()
            tmp["ticker"] = ticker
            frames.append(tmp)
        pd.concat(frames, ignore_index=True).to_parquet(cache_file)
        log.info(f"Cached to {cache_file}")

    return result


def compute_historical_scores(
    fundamentals: dict[str, pd.DataFrame],
    prices: pd.DataFrame,
    rebalance_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Compute V+Q scores at each rebalance date using point-in-time data.

    Parameters
    ----------
    fundamentals: {ticker: DataFrame} from fetch_historical_fundamentals
    prices: wide DataFrame (date x ticker) of adjusted close prices
    rebalance_dates: dates at which to score (quarterly month-ends)

    Returns
    -------
    DataFrame (date x ticker) of composite V+Q scores, same shape convention
    as momentum scores — can be fed directly into top_n_equal_weight().
    """
    all_scores = {}

    # Find the earliest date any ticker has 2+ annual reports (minimum for YoY growth)
    earliest_usable = None
    for fdf in fundamentals.values():
        if len(fdf) >= 2:
            second_report = fdf.index[1]
            available_from = second_report + pd.DateOffset(months=REPORTING_LAG_MONTHS)
            if earliest_usable is None or available_from < earliest_usable:
                earliest_usable = available_from
    if earliest_usable is not None:
        rebalance_dates = rebalance_dates[rebalance_dates >= earliest_usable]
        log.info(f"Fundamental data available from {earliest_usable.date()}, {len(rebalance_dates)} rebalance dates to score")

    for rebal_date in rebalance_dates:
        # Point-in-time cutoff: only use financials reported before this date
        # Indian companies have ~3 month reporting lag from fiscal year-end
        cutoff = rebal_date - pd.DateOffset(months=REPORTING_LAG_MONTHS)

        fund_snapshot = {}
        for ticker, fdf in fundamentals.items():
            # Get the two most recent annual reports available by cutoff
            available = fdf[fdf.index <= cutoff]
            if len(available) < 2:
                continue

            latest = available.iloc[-1]
            prev = available.iloc[-2]

            ni = latest["net_income"]
            eq = latest["equity"]
            debt = latest["total_debt"]
            shares = latest["shares"]
            ni_prev = prev["net_income"]

            if pd.isna(ni) or pd.isna(eq) or eq <= 0 or pd.isna(shares) or shares <= 0:
                continue

            # EPS and P/E from price
            eps = ni / shares
            if eps <= 0:
                continue

            # Get price at rebalance date
            if ticker not in prices.columns:
                continue
            price_at = prices[ticker].loc[:rebal_date].dropna()
            if price_at.empty:
                continue
            price = float(price_at.iloc[-1])
            if price <= 0:
                continue

            pe = price / eps
            roe = ni / eq
            de = (debt / eq) if pd.notna(debt) else 0.0
            eg = (ni - ni_prev) / abs(ni_prev) if pd.notna(ni_prev) and abs(ni_prev) > 0 else np.nan

            fund_snapshot[ticker] = {
                "pe": pe, "roe": roe, "de": de, "earnings_growth": eg,
            }

        if len(fund_snapshot) < 10:
            log.warning(f"{rebal_date.date()}: only {len(fund_snapshot)} stocks with data, skipping")
            continue

        # Score using the same logic as score_value_quality
        df = pd.DataFrame(fund_snapshot).T
        scores = score_value_quality(df)
        if not scores.empty:
            all_scores[rebal_date] = scores

    if not all_scores:
        log.warning("No valid scoring dates — empty result")
        return pd.DataFrame()

    # Build wide DataFrame: (date x ticker), forward-filled daily for the backtest engine
    score_df = pd.DataFrame(all_scores).T.sort_index()
    score_df.index.name = "date"
    log.info(
        f"Historical V+Q scores: {len(score_df)} rebalance dates, "
        f"~{score_df.notna().sum(axis=1).mean():.0f} stocks scored per date"
    )
    return score_df
