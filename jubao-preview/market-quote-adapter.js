/* 聚寶鯨 JUBAO QUANT | PUBLIC SPOT QUOTES ONLY | SANDBOX V1.0
 * Zero credentials / zero trading / no account or wallet access.
 * Snapshots may be delayed; status must not be called an exchange-time tick.
 */
(function(root) {
  'use strict';
  const SYMBOLS = Object.freeze(['BTCUSDT', 'ETHUSDT', 'SOLUSDT']);
  const API_URL = 'https://data-api.binance.vision/api/v3/ticker/price?symbols=%5B%22BTCUSDT%22%2C%22ETHUSDT%22%2C%22SOLUSDT%22%5D';
  const REFRESH_MS = 30000;
  const MAX_PRICE = 1000000000;
  const pricePattern = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;
  function parse(data) {
    if (!Array.isArray(data) || data.length !== SYMBOLS.length) throw Error('unexpected market data');
    const found = new Map();
    for (const row of data) {
      if (!row || !SYMBOLS.includes(row.symbol) || found.has(row.symbol)) throw Error('unknown or duplicate ticker');
      if (typeof row.price !== 'string' || !pricePattern.test(row.price)) throw Error('invalid quoted price');
      const num = Number(row.price);
      if (!Number.isFinite(num) || num <= 0 || num > MAX_PRICE) throw Error('out-of-range quote');
      found.set(row.symbol, num);
    }
    if (found.size !== SYMBOLS.length) throw Error('missing ticker');
    return Object.freeze({ BTC: found.get('BTCUSDT'), ETH: found.get('ETHUSDT'), SOL: found.get('SOLUSDT') });
  }
  async function load(fetchImpl, signal) {
    if (typeof fetchImpl !== 'function') throw Error('fetch unavailable');
    const response = await fetchImpl(API_URL, {
      method: 'GET', cache: 'no-store', credentials: 'omit', mode: 'cors',
      redirect: 'error', referrerPolicy: 'no-referrer', signal
    });
    if (!response || !response.ok) throw Error('market API unavailable');
    const prices = parse(await response.json());
    return Object.freeze({ prices, source: 'Binance Spot', quote: 'USDT', fetched_at_local: new Date().toISOString() });
  }
  const adapter = Object.freeze({ API_URL, REFRESH_MS, parse, load });
  if (typeof module !== 'undefined' && module.exports) module.exports = adapter;
  root.JubaoQuotes = adapter;
})(typeof window !== 'undefined' ? window : globalThis);
