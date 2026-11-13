"""Point-in-time inputs shared by HTTP, chat, and prediction MCP."""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.data import db
from app.data.underlying import daily_closes
from app.data.fetcher import find_nearest_expiry_friday, fetch_options_chain


@dataclass
class PredictionInputs:
    chains: dict[str, pd.DataFrame]
    spots: dict[str, float]
    expiry: date
    observation: date
    target: date
    meta: dict

    @property
    def spot(self):
        return self.spots[self.observation.isoformat()]

    @property
    def days_forward(self):
        return (self.target - self.observation).days


def prepare_prediction(ticker: str, start: date, end: date, target: date, *, allow_api: bool = True) -> PredictionInputs:
    if start > end:
        raise ValueError("Observation start must not be after observation end")
    if end >= date.today():
        raise ValueError("Observation must use a completed historical trading day")
    if target <= end:
        raise ValueError("target_date must be after obs_date_to")
    ticker = ticker.upper()
    desired = find_nearest_expiry_friday(end, (target - end).days)
    expiry = db.find_best_expiry_in_range(ticker, start, end, desired)
    source = "duckdb"
    if expiry is None and start == end and allow_api:
        stock = daily_closes(ticker, start, end)
        if end.isoformat() not in stock:
            raise ValueError("No actual stock close on the requested observation date")
        expiry = desired
        frame = fetch_options_chain(ticker, end, expiry, spot=stock[end.isoformat()]).assign(trade_date=end.isoformat())
        source = "massive_historical_options"
    elif expiry is None or expiry <= end:
        raise ValueError(f"No unexpired option chain for {ticker} in {start}..{end}. Refresh options data or choose an earlier observation.")
    else:
        frame = db.query_chains_range(ticker, start, end, expiry)
    chains = {str(day)[:10]: group[["strike", "last_price", "bid", "ask"]].reset_index(drop=True)
              for day, group in frame.groupby("trade_date")}
    observation = date.fromisoformat(max(chains))
    warnings = ["The model uses European-style pricing without dividend adjustments; option-implied probabilities are not calibrated real-world probabilities."]
    if observation != end:
        warnings.append(f"Latest available options observation is {observation}, not requested {end}; horizon uses the actual observation date.")
    try:
        actual = daily_closes(ticker, start, end, allow_api=allow_api)
    except Exception:
        actual = {}
        warnings.append("Daily stock prices could not be retrieved; options-derived estimates are used and may be inaccurate.")
    spots = {}
    estimated_dates = []
    for day, chain in chains.items():
        if day in actual:
            spots[day] = actual[day]
        else:
            row = chain.sort_values("strike").iloc[0]
            spots[day] = float(row["strike"] + row["last_price"])
            estimated_dates.append(day)
    if estimated_dates:
        warnings.append(f"{len(estimated_dates)} of {len(chains)} observation-day stock prices are estimated from options, not actual stock closes.")
    if expiry != target:
        warnings.append(f"Options expire {expiry}; the distribution for {target} assumes the fitted volatility applies to that different horizon.")
    meta = {
        "ticker": ticker, "obs_date_from": min(chains), "obs_date_to": observation.isoformat(),
        "obs_date": observation.isoformat(), "requested_obs_date_from": start.isoformat(),
        "requested_obs_date_to": end.isoformat(), "target_date": target.isoformat(),
        "days_forward": (target - observation).days, "days_averaged": len(chains),
        "spot": spots[observation.isoformat()], "expiry_used": expiry.isoformat(),
        "option_days_to_expiry": (expiry - observation).days, "data_source": source,
        "spot_source": "options_estimate" if observation.isoformat() in estimated_dates else "massive_daily_unadjusted",
        "estimated_spot_dates": estimated_dates, "warnings": warnings,
        "probability_basis": "risk_neutral_terminal", "mode": "backtest" if target < date.today() else "forecast",
    }
    return PredictionInputs(chains, spots, expiry, observation, target, meta)
