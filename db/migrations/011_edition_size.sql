-- How many researchers each edition published.
--
-- Everything that reports a position needs this denominator, and counting it
-- is not cheap: `group by edition_id` over career_metrics is a sequential scan
-- of 1.4 million rows and takes 1.8 seconds, and fifteen separate indexed
-- counts still take 1.4. That cost landed on the first reader to look up an
-- author in each web worker.
--
-- It is a property of the edition, so it belongs on the edition. Filled by
-- pipeline/list_position.py, which is already walking every edition.

alter table editions add column if not exists published_rows integer;
