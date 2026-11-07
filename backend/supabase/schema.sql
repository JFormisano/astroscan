-- AstroScan: measurements table + image bucket. Paste into the Supabase SQL editor.
-- Owner: Person A. Matches CLAUDE.md section 3 "Data model", plus `step`, `result` and `error`
-- (needed so GET /api/measurements/{job_id} can serve status, the result JSON and failure messages).

create table if not exists measurements (
  id             uuid primary key,
  created_at     timestamptz not null default now(),
  status         text not null default 'pending' check (status in ('pending', 'solved', 'failed')),
  step           text,
  taken_at_utc   timestamptz,
  lat_rounded    double precision,
  lon_rounded    double precision,
  score          smallint,
  limiting_mag   double precision,
  pct_lost       double precision,
  confidence     text check (confidence in ('high', 'medium', 'low')),
  flags          jsonb not null default '{}'::jsonb,  -- exposure_s, iso, f_number, solve_seconds, solver_used, ...
  image_url      text,                                -- EXIF-stripped copy
  solved         boolean not null default false,
  is_demo        boolean not null default false,
  result         jsonb,                               -- full result JSON (docs/result-schema.json)
  error          jsonb                                -- {code, message, next_step, detected_stars?}
);

create index if not exists measurements_status_idx on measurements (status);

-- Public bucket for the EXIF-stripped photos (they contain no location data).
insert into storage.buckets (id, name, public) values ('images', 'images', true)
on conflict (id) do nothing;
