const ALLOWED = /^[A-Z0-9_]{3,6}$/;
const SCAN_SYMBOLS = "ASELS,DSTKF,QNBTR,BOSSA,ENPRA,HEDEF,GARAN,ENKAI,TUPRS,KCHOL,THYAO,BIMAS,ISBTR,ISCTR,ISKUR,KTLEV,AKBNK,ASTOR,VAKBN,YKBNK,HALKB,FROTO,EREGL,CCOLA,TCELL,ODINE,TTKOM,SAHOL,TRALT,ISDMR,TOASO,QNBFK,GUBRF,KLRHO,OZATD,SISE,SELEC,ENJSA,DOCO,TURSG,KENT,AEFES,MGROS,PKENT,INVES,TERA,AKSEN,MAGEN,TRGYO,KLNMA,SASA,OYAKC,TAVHL,AHGAZ,IEYHO,ENERY,PGSUS,ZRGYO,POLHO,TEHOL,MPARK,AGHOL,GUNDG,EKGYO,LIDER,BRSAN,PEKGY,UFUK,RALYH,LYDHO,RGYAS,RYGYO,PASEU,ARCLK,AKFIS,EUPWR,TABGD,YGGYO,ANSGR,BSOKE,DOHOL,CVKMD,ISMEN,GLRMK,BRYAT,AYGAZ,ECILC,ARMGD,PETKM,SKBNK,TKFEN,KOZAA,TRMET,AKCNS,CWENE,AKSA,TTRAK,CIMSA,TRHOL,BIGEN,AGESA,ANHYT,TBORG,OTKAR,KRDMA,KRDMB,KRDMD,GENIL,KLSER,ALKLC,ALARK,RYSAS,DOAS,MOGAN,CLEBI,GESAN,ULKER,ECZYT,GLYHO,NUHCM".split(",");

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/api/history") {
      return historyResponse(url, ctx);
    }
    if (url.pathname === "/api/quote") {
      return quoteResponse(url);
    }
    if (url.pathname === "/api/scan") {
      return scanResponse(url, ctx);
    }
    return env.ASSETS.fetch(request);
  },
};

async function quoteResponse(url) {
  const symbol = String(url.searchParams.get("symbol") || "").trim().toUpperCase();
  if (!ALLOWED.test(symbol)) return json({ error: "Geçerli bir BIST kodu girin." }, 400);
  const target = `https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.IS?range=5d&interval=1d`;
  const response = await fetch(target, { headers: { "User-Agent": "BorsaAnalizPWA/1.2" }, cf: { cacheTtl: 60, cacheEverything: true } });
  if (!response.ok) return json({ error: "Son fiyat alınamadı." }, 502);
  const raw = await response.json(), chart = raw?.chart?.result?.[0], quote = chart?.indicators?.quote?.[0];
  if (!chart || !quote) return json({ error: "Geçerli fiyat bulunamadı." }, 502);
  const lastClose = [...(quote.close || [])].reverse().find(Number.isFinite);
  const marketPrice = chart.meta?.regularMarketPrice;
  const price = Number.isFinite(marketPrice) ? marketPrice : lastClose;
  const timestamp = chart.meta?.regularMarketTime || chart.timestamp?.at(-1);
  if (!Number.isFinite(price)) return json({ error: "Geçerli fiyat bulunamadı." }, 502);
  return json({ symbol, price, timestamp, source: "Yahoo Finance", delayed: true });
}

async function scanResponse(url, ctx) {
  const offset = Math.max(0, Math.min(SCAN_SYMBOLS.length, Number(url.searchParams.get("offset")) || 0));
  const limit = Math.max(1, Math.min(4, Number(url.searchParams.get("limit")) || 4));
  const symbols = SCAN_SYMBOLS.slice(offset, offset + limit);
  const settled = await Promise.allSettled(symbols.map(symbol => fetchChart(symbol, ctx)));
  const candidates = settled.flatMap((item, index) => item.status === "fulfilled" ? [scoreCandidate(symbols[index], item.value)].filter(Boolean) : []);
  return json({ candidates, processed: symbols.length, next: offset + symbols.length, total: SCAN_SYMBOLS.length });
}

async function fetchChart(symbol, ctx) {
  const target = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.IS?range=1y&interval=1d`);
  const cache = caches.default, key = new Request(target.toString());
  let response = await cache.match(key);
  if (!response) {
    response = await fetch(key, { headers: { "User-Agent": "BorsaAnalizPWA/1.1" } });
    if (!response.ok) throw new Error("Veri alınamadı");
    response = new Response(response.body, response);
    response.headers.set("Cache-Control", "public, max-age=1800");
    ctx.waitUntil(cache.put(key, response.clone()));
  }
  const raw = await response.json(), chart = raw?.chart?.result?.[0], quote = chart?.indicators?.quote?.[0];
  const closes = chart?.indicators?.adjclose?.[0]?.adjclose || quote?.close;
  if (!chart || !quote || !closes) throw new Error("Geçmiş yok");
  return chart.timestamp.map((t, i) => ({ t, c: closes[i], h: quote.high[i], l: quote.low[i], v: quote.volume[i] }))
    .filter(row => [row.c, row.h, row.l].every(Number.isFinite));
}

function scoreCandidate(symbol, rows) {
  if (rows.length < 200) return null;
  const closes = rows.map(x => x.c), volumes = rows.map(x => x.v || 0), price = closes.at(-1);
  if (!(price > 1 && price <= 50)) return null;
  const turnover = average(rows.slice(-20).map(x => x.c * x.v));
  if (turnover < 5_000_000) return null;
  const e20 = emaLast(closes, 20), e50 = emaLast(closes, 50), e200 = emaLast(closes, 200), r = rsiLast(closes, 14);
  const fast = emaSeries(closes, 12), slow = emaSeries(closes, 26), macd = fast.map((x, i) => x - slow[i]), signal = emaLast(macd, 9);
  const ret20 = (price / closes.at(-21) - 1) * 100, ret60 = (price / closes.at(-61) - 1) * 100;
  const volumeRatio = volumes.at(-1) / Math.max(average(volumes.slice(-20)), 1);
  const tr = rows.slice(1).map((x, i) => Math.max(x.h - x.l, Math.abs(x.h - rows[i].c), Math.abs(x.l - rows[i].c)));
  const atr = average(tr.slice(-14)), support = Math.min(...rows.slice(-20).map(x => x.l));
  const stop = Math.min(price * .985, Math.max(price - atr * 1.5, support * .98));
  const target = price + Math.max(atr * 2.2, price * .08), rr = (target - price) / Math.max(price - stop, .01);
  let score = 0; const reasons = [], risks = [];
  if (price > e20) { score += 12; reasons.push("Fiyat EMA20 üzerinde"); } else risks.push("Fiyat EMA20 altında");
  if (e20 > e50) { score += 18; reasons.push("Kısa trend pozitif"); } else risks.push("EMA20, EMA50 altında");
  if (price > e200) { score += 15; reasons.push("Uzun trend korunuyor"); } else risks.push("Fiyat EMA200 altında");
  if (r >= 45 && r <= 68) { score += 18; reasons.push(`RSI dengeli (${r.toFixed(1)})`); } else if (r >= 72) risks.push("RSI aşırı alıma yakın");
  if (macd.at(-1) > signal) { score += 15; reasons.push("MACD pozitif"); } else risks.push("MACD teyidi yok");
  if (volumeRatio >= 1.15) { score += 12; reasons.push("Hacim desteği var"); }
  if (ret20 > 0 && ret20 < 20) { score += 5; reasons.push("20 günlük momentum pozitif"); }
  if (ret60 > 0) score += 5;
  if (rr >= 1.5) { score += 5; reasons.push(`Risk/getiri 1:${rr.toFixed(1)}`); } else risks.push("Risk/getiri zayıf");
  score = Math.min(100, score);
  if (score < 48) return null;
  const status = score >= 75 && price <= e20 * 1.04 ? "ALIM BÖLGESİNDE" : price > e20 * 1.08 ? "GERİ ÇEKİLME BEKLE" : "TEYİT BEKLE";
  return { symbol, price, score, status, buyLow: Math.min(price * .98, e20), buyHigh: price * 1.01, target, stop, rr, reasons, risks, turnover };
}

function emaSeries(values, period) { const k = 2 / (period + 1), out = [values[0]]; for (let i = 1; i < values.length; i++) out.push(values[i] * k + out[i - 1] * (1 - k)); return out; }
function emaLast(values, period) { return emaSeries(values, period).at(-1); }
function rsiLast(values, period) { let gains = 0, losses = 0; for (let i = values.length - period; i < values.length; i++) { const d = values[i] - values[i - 1]; if (d > 0) gains += d; else losses -= d; } return losses ? 100 - 100 / (1 + gains / losses) : 100; }
function average(values) { return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1); }

async function historyResponse(url, ctx) {
  const symbol = String(url.searchParams.get("symbol") || "").trim().toUpperCase();
  if (!ALLOWED.test(symbol)) return json({ error: "Geçerli bir BIST kodu girin." }, 400);

  const target = new URL(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}.IS`);
  target.searchParams.set("range", "2y");
  target.searchParams.set("interval", "1d");
  target.searchParams.set("events", "div,splits");

  const cache = caches.default;
  const key = new Request(target.toString(), { method: "GET" });
  let response = await cache.match(key);
  if (!response) {
    response = await fetch(key, { headers: { "User-Agent": "BorsaAnalizPWA/1.0" } });
    if (response.ok) {
      response = new Response(response.body, response);
      response.headers.set("Cache-Control", "public, max-age=900");
      ctx.waitUntil(cache.put(key, response.clone()));
    }
  }
  if (!response.ok) return json({ error: "Piyasa verisi alınamadı." }, 502);

  const raw = await response.json();
  const chart = raw?.chart?.result?.[0];
  const quote = chart?.indicators?.quote?.[0];
  const closes = chart?.indicators?.adjclose?.[0]?.adjclose || quote?.close;
  if (!chart || !quote || !closes) return json({ error: "Yeterli fiyat geçmişi bulunamadı." }, 502);

  const rows = chart.timestamp.map((timestamp, index) => ({
    t: timestamp,
    o: quote.open[index], h: quote.high[index], l: quote.low[index],
    c: closes[index], v: quote.volume[index],
  })).filter(row => [row.o, row.h, row.l, row.c].every(Number.isFinite));
  return json({ symbol, currency: chart.meta?.currency || "TRY", rows });
}

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
  });
}
