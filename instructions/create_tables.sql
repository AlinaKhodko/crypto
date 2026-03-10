create table timeseries (
    id               serial primary key,                           -- Data source for series
    data_source_id   int4 not null,                                -- Data source ID
    download         bool not null default true,                   -- Perform daily downloads of data by ETL scripts?
    sname            text not null,                                -- Short unique name for series
    lname            text,                                         -- Long name for series
    map_name         text,                                         -- Name for series to display on the map
    city_id          int4,                                         -- Linked time series city
    data_source_params jsonb,                                      -- Series-specific params (e.g. url/code/id)
    attributes       jsonb,                                        -- Unstructured attributes
    category_id      int4,                                         -- Category of key stat
    frequency        text,                                         -- Frequency
    agg              text,                                         -- Aggregate function
    data_type        text,                                         -- Type of data in time series
    ds_ticker        text,                                         -- Data source ticker
    to_delete        bool not null default false,                  -- Specifies the entry to be deleted
    display_ticker   text,                                         -- Display ticker
    currency_id      int4                                          -- Currency ID
);


create table data_source (
    id      serial primary key,       -- Data source ID
    name    text not null,            -- Data source name
    params  jsonb                     -- Unstructured parameters
);

create table if not exists ohlc (
    id bigserial primary key,
    timeseries_id int not null references timeseries(id),
    datetime timestamptz not null,
    value numeric,
    open numeric,
    high numeric,
    low numeric,
    volume numeric,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    unique (timeseries_id, datetime)
);

create table strategies (
    id serial primary key,
    timeseries_id int not null references timeseries(id) on delete cascade,
    name text not null,
    params jsonb not null,
    version int not null default 1,               -- strategy version number
    use_on_frontend boolean not null default true,   -- visible to end users (UI, dashboards, etc.)
    use_in_analysis boolean not null default true    -- included in batch analytics/optimizations
);

alter table strategies
  add constraint unique_strategy_version unique (timeseries_id, name, version);

create table strategies_signals (
    id serial primary key,
    datetime timestamp with time zone not null,     -- always UTC
    timeseries_id int not null references timeseries(id) on delete cascade,
    strategy_id int not null references strategies(id) on delete cascade,
    signal text not null check (signal in ('buy','sell')),
    created_at timestamp with time zone not null default (now() at time zone 'utc'),
    unique (timeseries_id, strategy_id, datetime)
);

set time zone 'UTC';