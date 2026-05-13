// Custom Indicators for react-financial-charts

// Wilder's Smoothing
function wildersSmoothing(data: number[], period: number) {
  const result: (number | undefined)[] = [];
  let sum = 0;
  for (let i = 0; i < data.length; i++) {
    if (i < period) {
      sum += data[i];
      if (i === period - 1) {
        result.push(sum / period);
      } else {
        result.push(undefined);
      }
    } else {
      const prev = result[i - 1] as number;
      result.push(prev + (data[i] - prev) / period);
    }
  }
  return result;
}

export function calculateCustomIndicators(data: any[]) {
  // Data must be sorted oldest to newest
  const period = 14; // Default ADX period

  // OBV
  let obv = 0;
  
  // RelVol (10 day SMA of Volume)
  const volPeriod = 10;
  let volSum = 0;

  // For ADX
  const trData: number[] = [];
  const plusDmData: number[] = [];
  const minusDmData: number[] = [];

  for (let i = 0; i < data.length; i++) {
    const d = data[i];
    const prevD = i > 0 ? data[i - 1] : data[0];

    // OBV
    if (i === 0) {
      obv = d.volume;
    } else {
      if (d.close > prevD.close) obv += d.volume;
      else if (d.close < prevD.close) obv -= d.volume;
    }
    d.obv = obv;

    // RelVol
    volSum += d.volume;
    if (i >= volPeriod) {
      volSum -= data[i - volPeriod].volume;
      const volSma = volSum / volPeriod;
      d.relVol = volSma === 0 ? 0 : d.volume / volSma;
    } else {
      d.relVol = 1; // Default
    }

    // ADX True Range
    const tr1 = d.high - d.low;
    const tr2 = Math.abs(d.high - prevD.close);
    const tr3 = Math.abs(d.low - prevD.close);
    const tr = Math.max(tr1, tr2, tr3);
    trData.push(tr);

    const upMove = d.high - prevD.high;
    const downMove = prevD.low - d.low;

    let plusDM = 0;
    if (upMove > downMove && upMove > 0) plusDM = upMove;

    let minusDM = 0;
    if (downMove > upMove && downMove > 0) minusDM = downMove;

    plusDmData.push(plusDM);
    minusDmData.push(minusDM);
  }

  // Smooth ADX components
  const smoothedTR = wildersSmoothing(trData, period);
  const smoothedPlusDM = wildersSmoothing(plusDmData, period);
  const smoothedMinusDM = wildersSmoothing(minusDmData, period);

  const dxData: number[] = [];
  for (let i = 0; i < data.length; i++) {
    const sTR = smoothedTR[i];
    const sPlusDM = smoothedPlusDM[i];
    const sMinusDM = smoothedMinusDM[i];

    if (sTR !== undefined && sPlusDM !== undefined && sMinusDM !== undefined && sTR !== 0) {
      const plusDI = 100 * (sPlusDM / sTR);
      const minusDI = 100 * (sMinusDM / sTR);
      const diSum = plusDI + minusDI;
      
      data[i].plusDI = plusDI;
      data[i].minusDI = minusDI;

      if (diSum === 0) {
        dxData.push(0);
      } else {
        dxData.push(100 * Math.abs(plusDI - minusDI) / diSum);
      }
    } else {
      dxData.push(0); // Dummy for initial period
    }
  }

  const adxRaw = wildersSmoothing(dxData, period);
  for (let i = 0; i < data.length; i++) {
    // Only assign if it's past the initial period calculation
    data[i].adx = i >= period * 2 - 1 ? adxRaw[i] : undefined;
  }

  return data;
}
