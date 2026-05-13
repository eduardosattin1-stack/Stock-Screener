"use client";

import React, { useMemo } from "react";
import { format } from "d3-format";
import { timeFormat } from "d3-time-format";
import {
  ChartCanvas,
  Chart,
  CandlestickSeries,
  BarSeries,
  LineSeries,
  MACDSeries,
  RSISeries,
  BollingerSeries,
  XAxis,
  YAxis,
  CrossHairCursor,
  EdgeIndicator,
  MouseCoordinateX,
  MouseCoordinateY,
  OHLCTooltip,
  MovingAverageTooltip,
  MACDTooltip,
  RSITooltip,
  BollingerBandTooltip
} from "react-financial-charts";
import {
  ema,
  sma,
  macd,
  rsi,
  bollingerBand
} from "@react-financial-charts/indicators";
import { discontinuousTimeScaleProviderBuilder } from "@react-financial-charts/scales";

const priceFormat = format(".2f");
const timeFmt = timeFormat("%Y-%m-%d");

export default function ChartComponent({ data: initialData, width, height, ratio, symbol }: any) {
  // Setup indicators
  const ema20 = ema().options({ windowSize: 20 }).merge((d:any, c:any) => { d.ema20 = c }).accessor((d:any) => d.ema20);
  const ema50 = ema().options({ windowSize: 50 }).merge((d:any, c:any) => { d.ema50 = c }).accessor((d:any) => d.ema50);
  const sma200 = sma().options({ windowSize: 200 }).merge((d:any, c:any) => { d.sma200 = c }).accessor((d:any) => d.sma200);
  const macdCalc = macd().options({ fast: 12, slow: 26, signal: 9 }).merge((d:any, c:any) => { d.macd = c }).accessor((d:any) => d.macd);
  const rsiCalc = rsi().options({ windowSize: 14 }).merge((d:any, c:any) => { d.rsi = c }).accessor((d:any) => d.rsi);
  const bbCalc = bollingerBand().options({ windowSize: 20, multiplier: 2, sourcePath: "close", movingAverageType: "sma" }).merge((d:any, c:any) => { d.bb = c }).accessor((d:any) => d.bb);

  const calculatedData = useMemo(() => {
    const rawCalc = rsiCalc(macdCalc(sma200(ema50(ema20(bbCalc(initialData))))));
    return rawCalc.map((d: any) => ({
      ...d,
      macd: d.macd || { macd: undefined, signal: undefined, divergence: undefined },
      bb: d.bb || { top: undefined, bottom: undefined, middle: undefined },
    }));
  }, [initialData]);

  const { data, xScale, xAccessor, displayXAccessor } = useMemo(() => {
    const scaleProvider = discontinuousTimeScaleProviderBuilder().inputDateAccessor((d:any) => d.date);
    return scaleProvider(calculatedData);
  }, [calculatedData]);

  if (!data || data.length === 0) return null;

  // Viewport extents (show last 180 days by default)
  const max = xAccessor(data[data.length - 1]);
  const min = xAccessor(data[Math.max(0, data.length - 180)]);
  const xExtents = [min, max];

  if (!width || !height || width < 100 || height < 100) return null;

  const margin = { left: 0, right: 60, top: 0, bottom: 24 };
  const gridHeight = height - margin.top - margin.bottom;

  // Split height dynamically for multiple panes
  const priceH = gridHeight * 0.5;
  const volH = gridHeight * 0.1;
  const macdH = gridHeight * 0.25;
  const rsiH = gridHeight * 0.25;

  return (
    // @ts-ignore
    <ChartCanvas
      height={height}
      width={width}
      ratio={ratio}
      margin={margin}
      seriesName={symbol}
      data={data}
      xScale={xScale}
      xAccessor={xAccessor}
      displayXAccessor={displayXAccessor}
      xExtents={xExtents}
    >
      {/* 1. Price + Volume */}
      <Chart id={1} yExtents={(d:any) => [d?.high ? d.high * 1.05 : undefined, d?.low ? d.low * 0.95 : undefined, d?.bb?.top, d?.bb?.bottom]} height={priceH} padding={{ top: 20, bottom: 20 }}>
        {/* @ts-ignore */}
        <XAxis showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        {/* @ts-ignore */}
        <YAxis showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        
        {/* @ts-ignore */}
        <CandlestickSeries 
          fill={(d:any) => d?.close > d?.open ? "#10b981" : "#ef4444"}
          wickStroke={(d:any) => d?.close > d?.open ? "#10b981" : "#ef4444"}
        />
        {/* @ts-ignore */}
        <LineSeries yAccessor={ema20.accessor()} strokeStyle="#8b5cf6" />
        {/* @ts-ignore */}
        <LineSeries yAccessor={ema50.accessor()} strokeStyle="#3b82f6" />
        {/* @ts-ignore */}
        <LineSeries yAccessor={sma200.accessor()} strokeStyle="#f59e0b" />
        {/* @ts-ignore */}
        <BollingerSeries yAccessor={bbCalc.accessor()} />
        
        {/* @ts-ignore */}
        <MouseCoordinateY displayFormat={priceFormat} />
        {/* @ts-ignore */}
        <EdgeIndicator itemType="last" orient="right" edgeAt="right" yAccessor={(d:any) => d.close} fill={(d:any) => d.close > d.open ? "#10b981" : "#ef4444"} />
        
        {/* @ts-ignore */}
        <OHLCTooltip origin={[8, 16]} textFill="#374151" />
        {/* @ts-ignore */}
        <MovingAverageTooltip
          origin={[8, 36]}
          textFill="#374151"
          options={[
            { yAccessor: ema20.accessor(), type: "EMA", stroke: "#8b5cf6", windowSize: ema20.options().windowSize },
            { yAccessor: ema50.accessor(), type: "EMA", stroke: "#3b82f6", windowSize: ema50.options().windowSize },
            { yAccessor: sma200.accessor(), type: "SMA", stroke: "#f59e0b", windowSize: sma200.options().windowSize },
          ]}
        />
        {/* @ts-ignore */}
        <BollingerBandTooltip origin={[8, 56]} yAccessor={bbCalc.accessor()} options={bbCalc.options()} textFill="#374151" />
      </Chart>

      {/* 2. Volume (Overlaid on price chart bottom) */}
      <Chart id={2} yExtents={(d:any) => d.volume} height={volH} origin={(w, h) => [0, priceH - volH]}>
        {/* @ts-ignore */}
        <BarSeries yAccessor={(d:any) => d.volume} fillStyle={(d:any) => d.close > d.open ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"} />
      </Chart>

      {/* 3. MACD Pane */}
      <Chart id={3} yExtents={macdCalc.accessor()} height={macdH} origin={(w, h) => [0, priceH]} padding={{ top: 10, bottom: 10 }}>
        {/* @ts-ignore */}
        <XAxis showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        {/* @ts-ignore */}
        <YAxis ticks={4} showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        {/* @ts-ignore */}
        <MouseCoordinateY displayFormat={priceFormat} />
        
        {/* @ts-ignore */}
        <MACDSeries yAccessor={macdCalc.accessor()} />
        {/* @ts-ignore */}
        <MACDTooltip origin={[8, 16]} yAccessor={macdCalc.accessor()} options={macdCalc.options()} appearance={{ strokeStyle: { macd: "#3b82f6", signal: "#f59e0b" }, fillStyle: { divergence: "#8b5cf6" } }} textFill="#374151" />
      </Chart>

      {/* 4. RSI Pane */}
      <Chart id={4} yExtents={[0, 100]} height={rsiH} origin={(w, h) => [0, priceH + macdH]} padding={{ top: 10, bottom: 10 }}>
        {/* @ts-ignore */}
        <XAxis showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        {/* @ts-ignore */}
        <YAxis tickValues={[30, 50, 70]} showGridLines={true} strokeStyle="#e5e7eb" opacity={0.5} />
        
        {/* @ts-ignore */}
        <MouseCoordinateX displayFormat={timeFmt} />
        {/* @ts-ignore */}
        <MouseCoordinateY displayFormat={priceFormat} />
        
        {/* @ts-ignore */}
        <RSISeries yAccessor={rsiCalc.accessor()} />
        {/* @ts-ignore */}
        <RSITooltip origin={[8, 16]} yAccessor={rsiCalc.accessor()} options={rsiCalc.options()} textFill="#374151" />
      </Chart>

      {/* @ts-ignore */}
      <CrossHairCursor strokeStyle="#9ca3af" />
    </ChartCanvas>
  );
}
