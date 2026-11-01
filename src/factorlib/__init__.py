from .config    import Params
from .data      import load_dataset, FactorDataset
from .factors   import compute_momentum, zscore_cross_section, winsorize
from .portfolio import assign_quantiles, build_weights, compute_turnover
from .engine    import run_backtest, BacktestResult
from .metrics   import compute_ic, compute_metrics, newey_west_t
from .plots     import (plot_quantile_bar, plot_ls_equity, plot_ic_series,
                        plot_quantile_equity, plot_yearly_heatmap)
