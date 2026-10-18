# EtalonStrategy.py — la MEME logique que le bot (RSI survendu + tendance + stop 2xATR / objectif 2:1 / 24 h),
# ecrite pour Freqtrade afin d'avoir un ETALON : si le bot "maison" fait moins bien que ce Freqtrade dry-run
# sur les memes paires et la meme periode, le probleme est dans l'execution du bot, pas dans l'idee.
# Backtest : freqtrade backtesting --strategy EtalonStrategy --timerange 20260701- --timeframe 1h
from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter
from pandas import DataFrame
import talib.abstract as ta


class EtalonStrategy(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False
    startup_candle_count = 100
    process_only_new_candles = True
    use_custom_stoploss = True
    stoploss = -0.03                       # filet : jamais plus de 3 % (le custom stop 2xATR prend le relais)
    minimal_roi = {"0": 0.10}              # on sort sur l'objectif 2:1 via custom_exit, pas sur un ROI fixe
    trailing_stop = False

    rsi_achat = IntParameter(25, 45, default=38, space="buy")
    atr_mult = DecimalParameter(1.5, 3.0, default=2.0, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"] * 100
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["haut24"] = dataframe["high"].rolling(24).max()
        dataframe["hikkake"] = ta.CDLHIKKAKE(dataframe)
        dataframe["heure"] = dataframe["date"].dt.hour
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] < self.rsi_achat.value)
            & (dataframe["ema20"] >= dataframe["ema50"])                     # pas de contre-tendance 4h approx
            & (dataframe["atr_pct"].between(0.3, 1.5))
            & ((dataframe["haut24"] - dataframe["close"]) / dataframe["haut24"] * 100 > 1.0)
            & (~dataframe["heure"].between(12, 15))                           # pas 12h-16h UTC
            & (dataframe["volume"] > 0),
            "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if df is None or df.empty:
            return -0.01
        atr_pct = float(df["atr_pct"].iloc[-1])
        sl = min(3.0, max(0.8, float(self.atr_mult.value) * atr_pct)) / 100
        return -sl

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        df, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        atr_pct = float(df["atr_pct"].iloc[-1]) if df is not None and not df.empty else 0.5
        sl = min(3.0, max(0.8, float(self.atr_mult.value) * atr_pct)) / 100
        if current_profit >= 2 * sl:
            return "objectif_2_1"
        if (current_time - trade.open_date_utc).total_seconds() >= 24 * 3600:
            return "barriere_24h"
        return None
