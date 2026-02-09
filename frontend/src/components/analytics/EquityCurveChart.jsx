import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { performanceAPI } from '../../services/api';

const EquityCurveChart = () => {
  const chartContainerRef = useRef();
  const chartRef = useRef();
  const cashSeriesRef = useRef();
  const totalSeriesRef = useRef();
  const benchmarkSeriesRef = useRef();
  
  const [timeframe, setTimeframe] = useState('1w');
  const [loading, setLoading] = useState(true);
  const initialEquityRef = useRef(0);

  const fetchHistory = async (tf) => {
    setLoading(true);
    try {
      const response = await performanceAPI.history(tf);
      const data = response.data.history || [];
      
      if (data.length > 0) {
        initialEquityRef.current = data[0].total_equity;
      }
      
      const cashData = data.map(p => ({
        time: new Date(p.timestamp).getTime() / 1000,
        value: p.cash_balance
      }));
      
      const totalData = data.map(p => ({
        time: new Date(p.timestamp).getTime() / 1000,
        value: p.total_equity
      }));

      // Calculate benchmark series based on alpha
      // alpha = total_return - benchmark_return
      // benchmark_return = total_return - alpha
      const firstTotalEquity = data.length > 0 ? data[0].total_equity : 0;
      const benchmarkData = data.map(p => {
        const totalReturn = (p.total_equity - (firstTotalEquity || p.total_equity)) / (firstTotalEquity || 1);
        const benchmarkReturn = totalReturn - (p.alpha || 0);
        const benchmarkValue = (firstTotalEquity || p.total_equity) * (1 + benchmarkReturn);
        return {
          time: new Date(p.timestamp).getTime() / 1000,
          value: benchmarkValue
        };
      });
      
      if (cashSeriesRef.current) cashSeriesRef.current.setData(cashData);
      if (totalSeriesRef.current) totalSeriesRef.current.setData(totalData);
      if (benchmarkSeriesRef.current) benchmarkSeriesRef.current.setData(benchmarkData);
      
    } catch (err) {
      console.error('Failed to fetch equity history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const handleResize = () => {
      chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
    };

    chartRef.current = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    // Total Equity (Top layer of the stack)
    totalSeriesRef.current = chartRef.current.addAreaSeries({
      lineColor: '#38bdf8',
      topColor: 'rgba(56, 189, 248, 0.4)',
      bottomColor: 'rgba(56, 189, 248, 0.0)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      title: 'Total Equity'
    });

    // Cash Balance (Bottom layer of the stack)
    cashSeriesRef.current = chartRef.current.addAreaSeries({
      lineColor: '#10b981',
      topColor: 'rgba(16, 185, 129, 0.6)',
      bottomColor: 'rgba(16, 185, 129, 0.1)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      title: 'Cash'
    });

    // Benchmark (Line overlay)
    benchmarkSeriesRef.current = chartRef.current.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      lineStyle: 2, // Dashed
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      title: 'Benchmark'
    });

    window.addEventListener('resize', handleResize);

    fetchHistory(timeframe);

    // SSE for live updates
    const eventSource = new EventSource(performanceAPI.streamURL, { withCredentials: true });
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const time = new Date(data.timestamp).getTime() / 1000;
        
        if (cashSeriesRef.current) {
          cashSeriesRef.current.update({ time, value: data.cash_balance });
        }
        if (totalSeriesRef.current) {
          totalSeriesRef.current.update({ time, value: data.total_equity });
        }
        if (benchmarkSeriesRef.current && initialEquityRef.current > 0) {
          const totalReturn = (data.total_equity - initialEquityRef.current) / initialEquityRef.current;
          const benchmarkReturn = totalReturn - (data.alpha || 0);
          const benchmarkValue = initialEquityRef.current * (1 + benchmarkReturn);
          benchmarkSeriesRef.current.update({ time, value: benchmarkValue });
        }
      } catch (err) {
        console.error('Failed to update chart via SSE:', err);
      }
    };

    return () => {
      window.removeEventListener('resize', handleResize);
      chartRef.current.remove();
      eventSource.close();
    };
  }, []);

  useEffect(() => {
    if (chartRef.current) {
        fetchHistory(timeframe);
    }
  }, [timeframe]);

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/60 p-6 shadow-lg shadow-black/40">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">Equity Curve</h3>
          <p className="text-xs text-gray-400">Cash vs Total Asset Value</p>
        </div>
        <div className="flex bg-gray-950/50 p-1 rounded-lg border border-gray-800">
          {['1d', '1w', '1m', '3m', 'all'].map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                timeframe === tf
                  ? 'bg-blue-600 text-white shadow-lg'
                  : 'text-gray-400 hover:text-white hover:bg-gray-800'
              }`}
            >
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="relative">
        {loading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-gray-900/20 backdrop-blur-[1px]">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent" />
          </div>
        )}
        <div ref={chartContainerRef} />
      </div>

      <div className="mt-4 flex items-center justify-center gap-6">
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-emerald-500" />
          <span className="text-xs text-gray-400">Cash Balance</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full bg-sky-500" />
          <span className="text-xs text-gray-400">Total Equity (Cash + Assets)</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-0.5 w-4 bg-amber-500" />
          <span className="text-xs text-gray-400">Benchmark (BTC)</span>
        </div>
      </div>
    </div>
  );
};

export default EquityCurveChart;
