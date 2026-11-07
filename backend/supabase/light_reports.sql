-- AstroScan: light reports table (feature #9). Owner: Person D.
-- Paste into the Supabase SQL editor AFTER schema.sql (which creates the `images` bucket;
-- report photos go in that bucket under light-reports/).
-- Matches CLAUDE.md section 3 "Data model", plus `controller` (who the draft is addressed to)
-- and `draft_source` ('ai' or 'template', so we can tell when the AI was unavailable).

create table if not exists light_reports (
  id               uuid primary key,
  created_at       timestamptz not null default now(),
  lat_rounded      double precision not null,   -- ~1 km; raw coordinates are never stored
  lon_rounded      double precision not null,
  photo_url        text,                        -- EXIF-stripped copy, or null (photo is optional)
  category         text not null,
  controller       text not null default 'unknown',
  note             text,
  drafted_message  text not null,
  draft_source     text not null default 'template' check (draft_source in ('ai', 'template')),
  measurement_id   uuid                         -- nullable: the sky measurement this came from, if any
);

create index if not exists light_reports_created_at_idx on light_reports (created_at desc);
