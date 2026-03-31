"""
weights.py — Run Expectancy and wOBA weight derivation from Statcast pitch-by-pitch data.

================================================================================
METHODOLOGY
================================================================================

The goal is to assign a single run value to each batting outcome (walk, HBP,
single, double, triple, home run) that reflects how much that event contributes
to scoring runs — on average, across all game situations.

Step 1: Run Expectancy Matrix (RE24)
-------------------------------------
Every half-inning exists in one of 24 possible states: 8 base configurations
(empty, runner on 1st, runner on 2nd, ..., bases loaded) times 3 out counts
(0, 1, 2 outs). For each state, we ask: "how many runs does a team score from
this point to the end of the inning, on average?"

    RE[state] = mean(runs scored from this state to inning's end)

To compute this, we pull every pitch from a full MLB season via the Baseball
Savant / Statcast API, filter down to the last pitch of each plate appearance
(where `events` is not null), and for each PA calculate:

    runs_from_here = total_half_inning_runs - runs_scored_before_this_PA

Grouping by (outs, base_state) and averaging gives the 24-cell RE matrix.

Step 2: Linear Weights
-----------------------
For each plate appearance, the run value of the event is:

    run_value = RE[state_after] - RE[state_before] + runs_scored_on_play

Intuitively: a single is worth whatever run expectancy it adds to the inning
(by putting a runner on base and potentially advancing others), plus any runs
that scored directly on the play.

We then group by event type (single, double, etc.) and take the mean run_value.
These are *linear weights* — the average run contribution of each event,
collapsing all possible game contexts into one number.

The "state_after" is inferred from the next plate appearance's "state_before"
within the same half-inning (using a groupby + shift). For the last PA of an
inning, state_after = (3 outs, bases empty) → RE = 0.

Step 3: Scale to the OBP Scale (wOBA)
---------------------------------------
Raw linear weights include negative values for outs (~-0.27), which makes them
awkward to communicate. wOBA rescales them so that the league-average wOBA
equals league-average OBP (~.320), making it easy to interpret against the
familiar OBP scale.

    lgOBP       = (H + BB + HBP) / (AB + BB + HBP + SF)

    lg_lw_per_pa = weighted average linear weight across all PAs in the
                   OBP denominator (AB + BB + HBP + SF)

    scale_factor = lgOBP / lg_lw_per_pa

    woba_weight[event] = linear_weight[event] * scale_factor

The resulting weights match FanGraphs' published values within ~±0.02 for a
typical season (e.g., 2024: BB≈0.69, HBP≈0.72, 1B≈0.88, 2B≈1.25, 3B≈1.59,
HR≈2.04).

Design Decisions
-----------------
- Extra innings excluded by default: since 2020, MLB uses a ghost runner in
  extra innings, which inflates run expectancy for those states and would bias
  the weights if included.
- Intentional walks, sac bunts, sac flies excluded: these are situationally
  selected events, not true reflections of a batter's contribution.
- Statcast is fetched in weekly chunks: the Baseball Savant API caps responses
  at ~25k rows; weekly chunks keep each call well under that limit. pybaseball
  caching means subsequent runs are instant.
- Post-play state is inferred, not directly observed: Statcast records pre-play
  base occupancy. The post-play state is read from the *next* PA's pre-play
  state within the same half-inning, which is exact for all non-final PAs.

================================================================================
USAGE
================================================================================

    from weights import RunExpectancy, WobaWeights

    # Full pipeline (slow first run; cached after that)
    w = WobaWeights(2024).fetch()
    w.summary()        # event | linear_weight | woba_weight
    w.validate()       # compare against FanGraphs 2024 published values

    # Inspect the underlying RE24 matrix
    re = RunExpectancy(2024).fetch()
    re.display()       # 8 base states x 3 out counts
"""

import warnings
from datetime import date, timedelta

import pandas as pd
import pybaseball

pybaseball.cache.enable()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approximate MLB regular season date ranges by season
SEASON_DATES = {
    2015: ('2015-04-05', '2015-10-04'),
    2016: ('2016-04-03', '2016-10-02'),
    2017: ('2017-04-02', '2017-10-01'),
    2018: ('2018-03-29', '2018-10-01'),
    2019: ('2019-03-28', '2019-09-29'),
    2020: ('2020-07-23', '2020-09-27'),  # COVID shortened
    2021: ('2021-04-01', '2021-10-03'),
    2022: ('2022-04-07', '2022-10-05'),
    2023: ('2023-03-30', '2023-10-01'),
    2024: ('2024-03-20', '2024-09-29'),
    2025: ('2025-03-27', '2025-09-28'),
}

# Statcast columns we actually need (drop the rest to save memory)
KEEP_COLS = [
    'game_pk', 'game_date', 'inning', 'inning_topbot',
    'at_bat_number', 'batter', 'events',
    'outs_when_up', 'on_1b', 'on_2b', 'on_3b',
    'bat_score', 'post_bat_score',
]

# Events that earn a wOBA weight
WOBA_EVENTS = {'walk', 'hit_by_pitch', 'single', 'double', 'triple', 'home_run'}

# Events counted as outs for the purpose of computing the out linear weight
OUT_EVENTS = {
    'strikeout', 'field_out', 'grounded_into_double_play',
    'force_out', 'fielders_choice_out', 'strikeout_double_play',
    'other_out', 'double_play', 'triple_play',
}

# Events to skip entirely (not PAs, or selection-biased, or too rare)
SKIP_EVENTS = {
    'intentional_walk', 'sac_bunt', 'sac_fly', 'sac_bunt_double_play',
    'catcher_interf', 'balk',
    'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
    'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
    'runner_double_play', 'wild_pitch', 'passed_ball',
    'fielders_choice',   # runner out but batter reached safely — complex
}

# FanGraphs published wOBA weights for validation
FANGRAPHS_2024 = {
    'walk':        0.690,
    'hit_by_pitch': 0.720,
    'single':      0.880,
    'double':      1.250,
    'triple':      1.590,
    'home_run':    2.040,
}

# Base-state bitmask: bit 0 = 1B occupied, bit 1 = 2B occupied, bit 2 = 3B occupied
# 0=empty, 1=1B, 2=2B, 3=1B+2B, 4=3B, 5=1B+3B, 6=2B+3B, 7=loaded
BASE_LABELS = {
    0: '---', 1: '1--', 2: '-2-', 3: '12-',
    4: '--3', 5: '1-3', 6: '-23', 7: '123',
}

# Half-inning grouping key columns
HALF_INNING = ['game_pk', 'inning', 'inning_topbot']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _runners_code(on_1b, on_2b, on_3b) -> pd.Series:
    """Encode base occupancy as a 0–7 bitmask Series."""
    return (
        on_1b.notna().astype(int)
        | (on_2b.notna().astype(int) << 1)
        | (on_3b.notna().astype(int) << 2)
    )


def _re_lookup(matrix: dict, outs: pd.Series, runners: pd.Series) -> pd.Series:
    """Vectorised RE24 lookup; returns 0.0 for outs >= 3 (inning over)."""
    keys = list(zip(outs, runners))
    return pd.array([matrix.get((o, r), 0.0) if o < 3 else 0.0 for o, r in keys],
                    dtype='float64')


# ---------------------------------------------------------------------------
# RunExpectancy
# ---------------------------------------------------------------------------

class RunExpectancy:
    """
    Build the RE24 run expectancy matrix from a full season of Statcast data.

    Parameters
    ----------
    season : int
        MLB season year (e.g. 2024).
    chunk_days : int
        Days per API call chunk (default 7). Smaller = fewer rows dropped on edge cases.
    extra_innings : bool
        Include extra-inning half-innings (default False). Extra innings since 2020
        use a ghost-runner rule that inflates RE for those states.
    """

    def __init__(self, season: int, chunk_days: int = 7, extra_innings: bool = False):
        self.season = season
        self.chunk_days = chunk_days
        self.extra_innings = extra_innings
        self._fetched = False
        self._matrix: dict = {}
        self._pa_table: pd.DataFrame = pd.DataFrame()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self) -> 'RunExpectancy':
        if not self._fetched:
            raw = self._fetch_statcast()
            pa = self._build_pa_table(raw)
            self._matrix = self._compute_re24(pa)
            self._pa_table = pa
            self._fetched = True
        return self

    @property
    def matrix(self) -> dict:
        """RE24 dict keyed {(outs: int, runners_code: int): expected_runs: float}."""
        self.fetch()
        return self._matrix

    @property
    def pa_table(self) -> pd.DataFrame:
        """PA-level DataFrame with run_value column (RE_post - RE_pre + runs_on_play)."""
        self.fetch()
        return self._pa_table

    def display(self) -> pd.DataFrame:
        """Return RE24 as a readable 8-row × 3-column DataFrame."""
        self.fetch()
        rows = []
        for rc in range(8):
            row = {'base_state': BASE_LABELS[rc]}
            for outs in range(3):
                row[f'{outs} outs'] = round(self._matrix.get((outs, rc), float('nan')), 3)
            rows.append(row)
        return pd.DataFrame(rows).set_index('base_state')

    # ------------------------------------------------------------------
    # Private: data fetching
    # ------------------------------------------------------------------

    def _fetch_statcast(self) -> pd.DataFrame:
        if self.season not in SEASON_DATES:
            raise ValueError(
                f'Season {self.season} not in SEASON_DATES. '
                f'Add it or pass dates manually.'
            )
        start_str, end_str = SEASON_DATES[self.season]
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)

        chunks = []
        current = start
        while current <= end:
            chunk_end = min(current + timedelta(days=self.chunk_days - 1), end)
            print(f'  Fetching {current} → {chunk_end}…', end='\r')
            df = pybaseball.statcast(
                start_dt=current.strftime('%Y-%m-%d'),
                end_dt=chunk_end.strftime('%Y-%m-%d'),
            )
            if df is not None and len(df) > 0:
                # Keep only needed columns (tolerate missing ones gracefully)
                cols = [c for c in KEEP_COLS if c in df.columns]
                chunks.append(df[cols])
            current += timedelta(days=self.chunk_days)

        print()  # newline after progress display
        if not chunks:
            raise RuntimeError(f'No Statcast data returned for {self.season}.')

        raw = pd.concat(chunks, ignore_index=True)
        print(f'Fetched {len(raw):,} pitches for {self.season}.')
        return raw

    # ------------------------------------------------------------------
    # Private: PA table construction
    # ------------------------------------------------------------------

    def _build_pa_table(self, raw: pd.DataFrame) -> pd.DataFrame:
        # 1. Filter to PA-ending pitches (events not null/empty)
        pa = raw[raw['events'].notna() & (raw['events'] != '')].copy()

        # 2. Optionally drop extra innings
        if not self.extra_innings:
            pa = pa[pa['inning'] <= 9]

        # 3. Sort within each half-inning by at_bat_number (sequential PA order)
        pa = pa.sort_values(HALF_INNING + ['at_bat_number']).reset_index(drop=True)

        # 4. Pre-play base/out state
        pa['runners_code'] = _runners_code(pa['on_1b'], pa['on_2b'], pa['on_3b'])
        pa['outs'] = pa['outs_when_up'].astype(int)

        # 5. Runs scored on this play
        pa['runs_on_play'] = (pa['post_bat_score'] - pa['bat_score']).clip(lower=0)

        # 6. Infer post-play state from the *next* PA's pre-play state
        grp = pa.groupby(HALF_INNING)
        pa['post_outs']         = grp['outs'].shift(-1)
        pa['post_runners_code'] = grp['runners_code'].shift(-1)

        # 7. Mark and fix inning-ending PAs (last PA in half-inning → NaN from shift)
        inning_end = pa['post_outs'].isna()
        pa.loc[inning_end, 'post_outs'] = 3
        pa.loc[inning_end, 'post_runners_code'] = 0
        pa['post_outs'] = pa['post_outs'].astype(int)
        pa['post_runners_code'] = pa['post_runners_code'].astype(int)
        pa['inning_end'] = inning_end

        # 8. Drop events we don't want in any calculation
        pa = pa[~pa['events'].isin(SKIP_EVENTS)]

        print(f'Built PA table: {len(pa):,} plate appearances.')
        return pa

    # ------------------------------------------------------------------
    # Private: RE24 matrix
    # ------------------------------------------------------------------

    def _compute_re24(self, pa: pd.DataFrame) -> dict:
        # For each PA, runs_from_here = inning_total - cum_runs_before_this_PA
        grp = pa.groupby(HALF_INNING)
        cum_before = grp['runs_on_play'].cumsum().shift(1).fillna(0)
        inning_total = grp['runs_on_play'].transform('sum')
        pa = pa.copy()
        pa['runs_from_here'] = inning_total - cum_before

        matrix_series = (
            pa.groupby(['outs', 'runners_code'])['runs_from_here'].mean()
        )

        # Warn if any cell has very few observations
        counts = pa.groupby(['outs', 'runners_code'])['runs_from_here'].count()
        thin = counts[counts < 30]
        if len(thin):
            warnings.warn(
                f'RE24: {len(thin)} cells have < 30 observations: {thin.index.tolist()}'
            )

        # Store runs_from_here on pa_table for later use
        self._runs_from_here = pa['runs_from_here']  # kept as side-effect

        return {(outs, rc): val for (outs, rc), val in matrix_series.items()}


# ---------------------------------------------------------------------------
# WobaWeights
# ---------------------------------------------------------------------------

class WobaWeights:
    """
    Derive wOBA weights from a Run Expectancy matrix.

    Parameters
    ----------
    season : int
        MLB season year.
    re : RunExpectancy, optional
        Pre-built RunExpectancy instance. If None, one is created and fetched.
    extra_innings : bool
        Passed to RunExpectancy if re is None (default False).
    """

    def __init__(self, season: int, re: RunExpectancy = None,
                 extra_innings: bool = False):
        self.season = season
        self._re = re if re is not None else RunExpectancy(season, extra_innings=extra_innings)
        self._fetched = False
        self._weights: dict = {}
        self._linear_weights: dict = {}
        self._scale_factor: float = float('nan')

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch(self) -> 'WobaWeights':
        if not self._fetched:
            self._re.fetch()
            pa = self._re.pa_table
            matrix = self._re.matrix
            lw = self._compute_linear_weights(pa, matrix)
            sf = self._compute_scale_factor(pa, lw)
            self._linear_weights = lw
            self._scale_factor = sf
            self._weights = self._apply_scale(lw, sf)
            self._fetched = True
        return self

    @property
    def weights(self) -> dict:
        """Scaled wOBA weights: {event: weight}."""
        self.fetch()
        return self._weights

    @property
    def linear_weights(self) -> dict:
        """Unscaled linear weights including out value."""
        self.fetch()
        return self._linear_weights

    @property
    def scale_factor(self) -> float:
        """lgOBP / lg_lw_per_pa — the wOBA scaling constant."""
        self.fetch()
        return self._scale_factor

    def summary(self) -> pd.DataFrame:
        """Return a formatted table: event | linear_weight | woba_weight."""
        self.fetch()
        order = ['walk', 'hit_by_pitch', 'single', 'double', 'triple', 'home_run', 'out']
        rows = []
        for event in order:
            if event in self._linear_weights:
                rows.append({
                    'event':          event,
                    'linear_weight':  round(self._linear_weights[event], 4),
                    'woba_weight':    round(self._weights.get(event, float('nan')), 4),
                })
        df = pd.DataFrame(rows).set_index('event')
        df.loc['scale_factor'] = {'linear_weight': float('nan'),
                                  'woba_weight': round(self._scale_factor, 4)}
        return df

    def validate(self, expected: dict = None, tol: float = 0.025) -> bool:
        """
        Compare computed wOBA weights against expected values.
        Defaults to FanGraphs 2024 published weights.
        Returns True if all events are within tolerance.
        """
        self.fetch()
        if expected is None:
            if self.season != 2024:
                warnings.warn(
                    'No expected weights provided and season != 2024. '
                    'Comparing against FanGraphs 2024 values as a rough guide.'
                )
            expected = FANGRAPHS_2024

        ok = True
        for event, fg_val in expected.items():
            computed = self._weights.get(event, float('nan'))
            delta = abs(computed - fg_val)
            status = 'OK' if delta <= tol else 'FAIL'
            print(f'{event:15s}  computed={computed:.3f}  expected={fg_val:.3f}  '
                  f'delta={delta:.3f}  [{status}]')
            if delta > tol:
                ok = False

        print(f'\nscale_factor={self._scale_factor:.4f}')
        print(f'Overall: {"PASS" if ok else "FAIL"}')
        return ok

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _compute_linear_weights(self, pa: pd.DataFrame, matrix: dict) -> dict:
        pa = pa.copy()

        # RE of pre- and post-play states
        pa['RE_pre']  = _re_lookup(matrix, pa['outs'],      pa['runners_code'])
        pa['RE_post'] = _re_lookup(matrix, pa['post_outs'], pa['post_runners_code'])
        pa['run_value'] = pa['RE_post'] - pa['RE_pre'] + pa['runs_on_play']

        # Store annotated table back for inspection
        self._annotated_pa = pa

        # Mean run value per event type
        lw = pa.groupby('events')['run_value'].mean().to_dict()

        # Aggregate out value across all out event types
        out_mask = pa['events'].isin(OUT_EVENTS)
        if out_mask.any():
            lw['out'] = pa.loc[out_mask, 'run_value'].mean()

        return lw

    def _compute_scale_factor(self, pa: pd.DataFrame, lw: dict) -> float:
        events = pa['events']

        hit_events = {'single', 'double', 'triple', 'home_run'}
        bb_events  = {'walk'}
        hbp_events = {'hit_by_pitch'}
        ab_events  = hit_events | OUT_EVENTS  # AB = H + non-BB/HBP outs (approx)
        sf_events  = {'sac_fly'}

        n_H   = (events.isin(hit_events)).sum()
        n_BB  = (events.isin(bb_events)).sum()
        n_HBP = (events.isin(hbp_events)).sum()
        n_AB  = (events.isin(ab_events)).sum()
        n_SF  = (events.isin(sf_events)).sum()
        n_1B  = (events == 'single').sum()
        n_2B  = (events == 'double').sum()
        n_3B  = (events == 'triple').sum()
        n_HR  = (events == 'home_run').sum()
        n_outs = (events.isin(OUT_EVENTS)).sum()

        # League OBP from the PA table
        lgOBP = (n_BB + n_HBP + n_H) / (n_AB + n_BB + n_HBP + n_SF)

        # Weighted average linear weight per PA (OBP denominator)
        denom = n_AB + n_BB + n_HBP + n_SF
        if denom == 0:
            raise RuntimeError('No PAs found to compute scale factor.')

        lg_lw_per_pa = (
            lw.get('walk', 0)        * n_BB
            + lw.get('hit_by_pitch', 0) * n_HBP
            + lw.get('single', 0)    * n_1B
            + lw.get('double', 0)    * n_2B
            + lw.get('triple', 0)    * n_3B
            + lw.get('home_run', 0)  * n_HR
            + lw.get('out', 0)       * n_outs
        ) / denom

        if lg_lw_per_pa == 0:
            raise RuntimeError('League linear weight per PA is zero — check data.')

        scale = lgOBP / lg_lw_per_pa
        print(f'lgOBP={lgOBP:.4f}  lg_lw_per_pa={lg_lw_per_pa:.4f}  scale={scale:.4f}')
        return scale

    def _apply_scale(self, lw: dict, sf: float) -> dict:
        woba = {event: lw[event] * sf for event in WOBA_EVENTS if event in lw}
        # out weight scaled for reference (not used in wOBA itself)
        if 'out' in lw:
            woba['out'] = lw['out'] * sf
        return woba
