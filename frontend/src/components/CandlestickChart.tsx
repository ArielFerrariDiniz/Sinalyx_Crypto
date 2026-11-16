import { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { MarketCandle } from '../services/api';

function chartRows(candles: MarketCandle[]) {
  const valid = candles.flatMap(candle => {
    const open = Number(candle.open);
    const high = Number(candle.high);
    const low = Number(candle.low);
    const close = Number(candle.close);
    const volume = Number(candle.volume);
    if (![open, high, low, close, volume].every(Number.isFinite)) return [];
    const time = Math.floor(candle.open_time / 1000) as UTCTimestamp;
    return [{
      candle: { time, open, high, low, close } satisfies CandlestickData<UTCTimestamp>,
      volume: {
        time,
        value: volume,
        color: close >= open ? 'rgba(65, 191, 143, .42)' : 'rgba(224, 103, 117, .42)',
      } satisfies HistogramData<UTCTimestamp>,
      openTime: candle.open_time,
    }];
  });
  return valid.sort((left, right) => left.openTime - right.openTime);
}

export function CandlestickChart({ candles, hasOlder, loadingOlder, onLoadOlder }: {
  candles: MarketCandle[];
  hasOlder: boolean;
  loadingOlder: boolean;
  onLoadOlder: () => Promise<void>;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ReturnType<IChartApi['addSeries']> | null>(null);
  const volumeSeriesRef = useRef<ReturnType<IChartApi['addSeries']> | null>(null);
  const previousOpenTimesRef = useRef<number[] | null>(null);
  const lastAutoLoadRef = useRef(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      width: Math.max(320, container.clientWidth),
      height: 440,
      layout: {
        background: { type: ColorType.Solid, color: '#101319' },
        textColor: '#9ba5b4',
        attributionLogo: true,
        fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif',
      },
      grid: {
        vertLines: { color: '#1e242e' },
        horzLines: { color: '#1e242e' },
      },
      rightPriceScale: { borderColor: '#303642' },
      timeScale: { borderColor: '#303642', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: '#596273' }, horzLine: { color: '#596273' } },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#41bf8f',
      downColor: '#e06775',
      borderUpColor: '#41bf8f',
      borderDownColor: '#e06775',
      wickUpColor: '#41bf8f',
      wickDownColor: '#e06775',
      priceFormat: { type: 'price', precision: 12, minMove: 0.000000000001 },
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 }, visible: false });
    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const observer = new ResizeObserver(entries => {
      const width = entries[0]?.contentRect.width;
      if (width && width > 0) chart.resize(width, 440);
    });
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      previousOpenTimesRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries || candles.length === 0) return;
    const rows = chartRows(candles);
    if (rows.length === 0) return;

    const nextOpenTimes = rows.map(row => row.openTime);
    const previousOpenTimes = previousOpenTimesRef.current;
    const visible = previousOpenTimes ? chart.timeScale().getVisibleLogicalRange() : null;
    candleSeries.setData(rows.map(row => row.candle));
    volumeSeries.setData(rows.map(row => row.volume));

    if (!previousOpenTimes) {
      chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, rows.length - 90), to: rows.length + 5 });
    } else if (nextOpenTimes[0] < previousOpenTimes[0] && visible) {
      const previousFirst = previousOpenTimes[0];
      const inserted = nextOpenTimes.filter(openTime => openTime < previousFirst).length;
      if (inserted > 0) chart.timeScale().setVisibleLogicalRange({ from: visible.from + inserted, to: visible.to + inserted });
    }
    previousOpenTimesRef.current = nextOpenTimes;
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !hasOlder || loadingOlder) return;
    const onVisibleRange = (range: { from: number; to: number } | null) => {
      if (!range || range.from > 8 || Date.now() - lastAutoLoadRef.current < 900) return;
      lastAutoLoadRef.current = Date.now();
      void onLoadOlder();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(onVisibleRange);
    return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(onVisibleRange);
  }, [hasOlder, loadingOlder, onLoadOlder]);

  return <div className="candlestick-chart" ref={containerRef} aria-label="Gráfico interativo de candles e volume" />;
}
