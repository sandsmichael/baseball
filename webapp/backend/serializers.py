"""
DataFrame → JSON-safe conversion utilities.

pandas NaN / numpy numeric types are not JSON-serializable.
Every DataFrame that goes to the wire must pass through df_to_records().
"""
import math
from typing import Any

import numpy as np
import pandas as pd


def _clean(v: Any) -> Any:
    """Convert non-JSON-safe scalars to Python-native equivalents."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.ndarray,)):
        return v.tolist()
    return v


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """
    Convert a DataFrame to a list of JSON-safe dicts.

    Handles:
      - pandas NaN → None
      - numpy int64/float64 → int/float
      - named index → reset to column
      - infinity → None
    """
    if df is None or df.empty:
        return []
    df = df.reset_index(drop=False)
    # Drop pandas RangeIndex that was reset into a column named 'index'
    if 'index' in df.columns and df['index'].dtype == np.int64:
        try:
            if (df['index'] == range(len(df))).all():
                df = df.drop(columns='index')
        except Exception:
            pass
    records = df.where(df.notna(), None).to_dict(orient='records')
    return [{k: _clean(v) for k, v in row.items()} for row in records]


def series_to_dict(s: pd.Series) -> dict:
    """Convert a pandas Series to a JSON-safe dict."""
    return {str(k): _clean(v) for k, v in s.items()}
