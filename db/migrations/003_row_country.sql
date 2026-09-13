-- THIS MIGRATION ADDS COLUMNS BUT DOES NOT BACKFILL THEM.
--
-- Applying it to a database that already holds fact rows leaves country_code
-- NULL on every one of them. There is deliberately no backfill statement,
-- because the value cannot be recovered from what is already stored: that is
-- the whole point of the ruling below. It has to come from the source files.
-- The supported path is a rebuild, `python pipeline/build_relational.py
-- data_clean` against a freshly migrated empty schema, which is also how
-- production works (a dump is loaded into a freshly migrated database).
--
-- RULING R17: the country a row carries is its own, not its institution's.
--
-- The source gives every row an inst_name and a cntry independently. Reading
-- country back through institutions.country_code loses that: an institution is
-- identified by its normalised name alone (which is what R15 assumes when it
-- says 'CEA LETI\xa0' would otherwise become a second institution), and 3,389
-- of the 66,079 institution names appear with more than one country across the
-- editions.
--
-- Measured on the loaded data, after NFKC normalisation and strip, out of
-- 2,730,673 rows:
--   39,476 rows have an institution whose country_code is not the row's own
--          (23,617 of those disagree with both values present; the rest are a
--          row with no country whose institution has one, which would be
--          answered with a country the row never carried)
--      695 rows have a country but no institution at all, so no answer could
--          be produced for them
--   40,171 rows (1.47%) would therefore be served a country that is not theirs
--          or none at all.
--
-- The dashboard depends on the per-row value: create_fig_helper_functions.py
-- groups by cntry, and the author card renders the author's own country.
--
-- institutions.country_code stays as it is. It is the institution's own
-- attribute and it is not wrong, it is a different thing.
alter table career_metrics
    add column country_code text references countries(country_code);
alter table singleyr_metrics
    add column country_code text references countries(country_code);

-- Task 7 groups by country within an edition.
create index career_metrics_country_idx
    on career_metrics (country_code, edition_id);
create index singleyr_metrics_country_idx
    on singleyr_metrics (country_code, edition_id);

-- RULING R18: the loader's orphan-author cleanup looks up
-- author_name_observations by author_id alone. The only index that covered
-- that column was the unique (edition_id, authfull_raw, author_id) constraint,
-- which leads with edition_id, so the lookup could not use it and Postgres
-- anti-joined the whole table instead. That single delete grew to about two
-- and a half minutes on the last edition of a full build.
create index author_name_observations_author_idx
    on author_name_observations (author_id);
