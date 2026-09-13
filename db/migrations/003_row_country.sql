-- RULING R17: the country a row carries is its own, not its institution's.
--
-- The source gives every row an inst_name and a cntry independently. Reading
-- country back through institutions.country_code loses that: an institution is
-- identified by its normalised name alone (which is what R15 assumes when it
-- says 'CEA LETI\xa0' would otherwise become a second institution), and 3,389
-- of the 66,079 institution names appear with more than one country across the
-- editions. Measured against the source, 33,028 of 2,730,673 rows would be
-- served a country that is not theirs, and 22,327 rows have no institution at
-- all, so 55,355 rows (2.03%) would be served wrongly or not at all.
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
