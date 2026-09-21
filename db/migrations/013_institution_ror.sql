-- Where an institution actually is.
--
-- The published data gives an institution as a free-text name and a country,
-- and nothing else: no city, no coordinates, no identifier, in any edition
-- from 2017 to 2024. That is the source's shape, not something lost on the
-- way in.
--
-- ROR (the Research Organization Registry, ror.org) has all three for
-- 137,398 organisations, under an open licence, so the missing geography is
-- a matching problem. This table holds the result of that match and nothing
-- derived from it, so that a better matcher later replaces rows here without
-- touching anything else.
--
-- The match is deliberately narrow. Country must agree, one name may not
-- resolve to two organisations in that country, and the only trimming
-- allowed is dropping what follows a comma. A name that matches a record ROR
-- has withdrawn resolves to that record's stated successor, or to nothing.
-- See pipeline/ror_match.py for what was tried and rejected.
--
-- Coverage, measured against ROR v2.12-2026-08-25: 19,120 of 66,079
-- institutions (28.9%), which is 160,224 of the 230,333 researchers in
-- career-2024 (69.6%). The two numbers differ that much because the names
-- that match are the large institutions and the tail that does not is
-- departments, hospital wings and laboratory names. Anything reading this
-- table has to treat a missing row as normal rather than as an error.
--
-- `matched_on` says which spelling matched: 'name' is the string as
-- recorded, 'prefix' is what was left after dropping a trailing clause, so
-- a consumer can tell a whole-name match from a trimmed one. `name_type` is
-- which of the organisation's names matched, ROR's own classification, where
-- 'acronym' is the weakest evidence.
--
-- Filled by refresh_institution_ror() in pipeline/ror_match.py.

create table if not exists institution_ror (
    institution_id text primary key
        references institutions(institution_id),
    ror_id         text not null,
    ror_name       text,
    city           text,
    -- ROR's ISO2 country code, kept beside institutions.country_code, which
    -- is the published ISO3. They agree by construction: a candidate whose
    -- country disagrees is refused.
    country_code   text,
    lat            double precision,
    lng            double precision,
    matched_on     text not null,
    name_type      text not null,
    -- True when the name matched a record ROR has withdrawn and this row is
    -- its successor instead. The organisation is what the registry says
    -- superseded it; the city is the successor's. "Harvard Medical School"
    -- resolves this way to Harvard University, so the city reads Cambridge
    -- rather than Boston. A consumer that cannot accept that can filter it.
    via_successor  boolean not null default false,
    -- Which dump these rows came from, so a coverage number can be traced to
    -- a release. ROR publishes roughly monthly.
    dump_version   text
);

create index if not exists institution_ror_ror_idx
    on institution_ror (ror_id);
