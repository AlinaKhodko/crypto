insert into timeseries (
    data_source_id, download, sname, lname, data_type, ds_ticker, frequency
)
values (
    1,                          -- data_source.id for 'binance'
    true,
    'INJUSDT',                  -- no interval here
    'INJ/USDT',
    'price_ohlc',              -- or 'trade_price' if you prefer
    'INJUSDT',
    'irregular'                 -- any label you like
)
returning id;

insert into timeseries (data_source_id, download, sname, lname, data_type, ds_ticker, frequency)
values
  (1, true, 'BTCUSDT', 'Bitcoin',      'trade_price', 'BTCUSDT', 'irregular'),
  (1, true, 'ETHUSDT', 'Ethereum',     'trade_price', 'ETHUSDT', 'irregular'),
  (1, true, 'USDTUSDT','Tether',       'trade_price', 'USDTUSDT', 'irregular'),
  (1, true, 'USDCUSDT','USD Coin',     'trade_price', 'USDCUSDT', 'irregular'),
  (1, true, 'BNBUSDT', 'Binance Coin', 'trade_price', 'BNBUSDT', 'irregular'),
  (1, true, 'XRPUSDT', 'Ripple XRP',   'trade_price', 'XRPUSDT', 'irregular'),
  (1, true, 'ADAUSDT', 'Cardano ADA',  'trade_price', 'ADAUSDT', 'irregular'),
  (1, true, 'BUSDUSDT','Binance USD',  'trade_price', 'BUSDUSDT', 'irregular'),
  (1, true, 'SOLUSDT', 'Solana SOL',   'trade_price', 'SOLUSDT', 'irregular'),
  (1, true, 'DOTUSDT', 'Polkadot DOT','trade_price', 'DOTUSDT', 'irregular')
returning id;

-- Continuing from your previous series, assuming data_source_id = 1
insert into timeseries (data_source_id, download, sname, lname, data_type, ds_ticker, frequency)
values
  (1, true, 'TRXUSDT', 'TRON (TRX)',        'trade_price', 'TRXUSDT', 'irregular'),
  (1, true, 'DOGEUSDT', 'Dogecoin (DOGE)',  'trade_price', 'DOGEUSDT', 'irregular'),
  (1, true, 'LINKUSDT','Chainlink (LINK)',  'trade_price', 'LINKUSDT', 'irregular'),
  (1, true, 'AVAXUSDT','Avalanche (AVAX)',  'trade_price', 'AVAXUSDT', 'irregular'),
  (1, true, 'LTCUSDT','Litecoin (LTC)',     'trade_price', 'LTCUSDT', 'irregular'),
  (1, true, 'BCHUSDT','Bitcoin Cash (BCH)', 'trade_price', 'BCHUSDT', 'irregular'),
  (1, true, 'XMRUSDT','Monero (XMR)',       'trade_price', 'XMRUSDT', 'irregular'),
  (1, true, 'HYPEUSDT','Hyperliquid (HYPE)','trade_price', 'HYPEUSDT','irregular'),
  (1, true, 'HBARUSDT','Hedera (HBAR)',     'trade_price', 'HBARUSDT','irregular'),
  (1, true, 'EOSUSDT','EOS (EOS)',          'trade_price', 'EOSUSDT', 'irregular')
returning id;


-- Assuming data_source_id = 1 (Binance)
insert into timeseries (data_source_id, download, sname, lname, data_type, ds_ticker, frequency)
values
  (1, true, 'MATICUSDT', 'Polygon (MATIC)',        'trade_price', 'MATICUSDT', 'irregular'),
  (1, true, 'TONUSDT',   'Toncoin (TON)',          'trade_price', 'TONUSDT',   'irregular'),
  (1, true, 'SHIBUSDT',  'Shiba Inu (SHIB)',       'trade_price', 'SHIBUSDT',  'irregular'),
  (1, true, 'APTUSDT',   'Aptos (APT)',            'trade_price', 'APTUSDT',   'irregular'),
  (1, true, 'ARBUSDT',   'Arbitrum (ARB)',         'trade_price', 'ARBUSDT',   'irregular'),
  (1, true, 'OPUSDT',    'Optimism (OP)',          'trade_price', 'OPUSDT',    'irregular'),
  (1, true, 'ATOMUSDT',  'Cosmos (ATOM)',          'trade_price', 'ATOMUSDT',  'irregular'),
  (1, true, 'NEARUSDT',  'NEAR Protocol (NEAR)',   'trade_price', 'NEARUSDT',  'irregular'),
  (1, true, 'FILUSDT',   'Filecoin (FIL)',         'trade_price', 'FILUSDT',   'irregular'),
  (1, true, 'SANDUSDT',  'The Sandbox (SAND)',     'trade_price', 'SANDUSDT',  'irregular'),
  (1, true, 'AAVEUSDT',  'Aave (AAVE)',            'trade_price', 'AAVEUSDT',  'irregular'),
  (1, true, 'UNIUSDT',   'Uniswap (UNI)',          'trade_price', 'UNIUSDT',   'irregular'),
  (1, true, 'MKRUSDT',   'Maker (MKR)',            'trade_price', 'MKRUSDT',   'irregular'),
  (1, true, 'STXUSDT',   'Stacks (STX)',           'trade_price', 'STXUSDT',   'irregular'),
  (1, true, 'IMXUSDT',   'Immutable (IMX)',        'trade_price', 'IMXUSDT',   'irregular'),
  (1, true, 'TIAUSDT',   'Celestia (TIA)',         'trade_price', 'TIAUSDT',   'irregular'),
  (1, true, 'RUNEUSDT',  'THORChain (RUNE)',       'trade_price', 'RUNEUSDT',  'irregular'),
  (1, true, 'ALGOUSDT',  'Algorand (ALGO)',        'trade_price', 'ALGOUSDT',  'irregular'),
  (1, true, 'VETUSDT',   'VeChain (VET)',          'trade_price', 'VETUSDT',   'irregular')
returning id;

-- Strategy A: MA Sabres (TEMA) — NO Supertrend
insert into strategies (
    timeseries_id,
    name,
    params,
    version,
    use_on_frontend,
    use_in_analysis
)
values (
    (select id from timeseries where sname = 'ARBUSDT'),
    'MA Sabres (TEMA) — baseline',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 30,
      "length_sell": 120,
      "count_sell": 5,
      "supertrend_enabled": false
    }'::jsonb,
    1,
    true,
    true
)
returning id;

-- Strategy B: MA Sabres (TEMA) + Supertrend filter
insert into strategies (
    timeseries_id,
    name,
    params,
    version,
    use_on_frontend,
    use_in_analysis
)
values (
    (select id from timeseries where sname = 'ARBUSDT'),
    'MA Sabres (TEMA) + Supertrend',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 30,
      "length_sell": 120,
      "count_sell": 5,
      "supertrend_enabled": true,
      "supertrend": {
        "atr_period": 60,
        "multiplier": 2.0,
        "use_wilder_atr": true
      }
    }'::jsonb,
    1,
    true,
    true
)
returning id;


-- Strategy 1: MA Sabres (TEMA) — baseline (count_sell=5)
insert into strategies (
    timeseries_id, name, params, version, use_on_frontend, use_in_analysis
)
values (
    (select id from timeseries where sname = 'BTCUSDT'),
    'MA Sabres (TEMA) — baseline',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 30,
      "length_sell": 150,
      "count_sell": 5,
      "supertrend_enabled": false
    }'::jsonb,
    1, true, true
)
returning id;


-- Strategy 3: MA Sabres (TEMA) + Supertrend (ATR=80, x4, Wilder)
insert into strategies (
    timeseries_id, name, params, version, use_on_frontend, use_in_analysis
)
values (
    (select id from timeseries where sname = 'BTCUSDT'),
    'MA Sabres (TEMA) + Supertrend',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 30,
      "length_sell": 150,
      "count_sell": 10,
      "supertrend_enabled": true,
      "supertrend": {
        "atr_period": 80,
        "multiplier": 4,
        "use_wilder_atr": true
      }
    }'::jsonb,
    1, true, true
)
returning id;

insert into strategies (
    timeseries_id, name, params, version, use_on_frontend, use_in_analysis
)
values (
    (select id from timeseries where sname = 'SOLUSDT'),
    'MA Sabres (TEMA) + Supertrend',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 25,
      "length_sell": 120,
      "count_sell": 10,
      "supertrend_enabled": true,
      "supertrend": {
        "atr_period": 60,
        "multiplier": 2,
        "use_wilder_atr": true
      }
    }'::jsonb,
    1, true, true
)
returning id;

insert into strategies (
    timeseries_id, name, params, version, use_on_frontend, use_in_analysis
)
values (
    (select id from timeseries where sname = 'ETHUSDT'),
    'MA Sabres (TEMA) + Supertrend',
    '{
      "ma_type": "TEMA",
      "length_buy": 60,
      "count_buy": 20,
      "length_sell": 120,
      "count_sell": 10,
      "supertrend_enabled": true,
      "supertrend": {
        "atr_period": 40,
        "multiplier": 2,
        "use_wilder_atr": true
      }
    }'::jsonb,
    1, true, true
)
returning id;


select * from strategies;

