-- The position a researcher holds on the list they were published in.
--
-- `rank` is not that number. It orders every scientist Scopus scored, so on a
-- career-2024 list of 230,333 people it runs past 1.2 million. This column is
-- the number a reader assumes they are being shown: 1 for the top of the
-- edition, up to the size of the edition.
--
-- It is derived rather than published, and it is stored rather than counted
-- because counting is too slow to do eight times on a page load. Counting the
-- rows above one score takes about 30 ms, which is fine once and 240 ms for a
-- researcher's whole history -- the sparkline in the edition picker needs
-- exactly that, for every author the reader clicks.
--
-- Only the columns are created here. Filling them rewrites 2.7 million rows
-- and takes about eight minutes, which does not belong in a migration
-- transaction: an earlier attempt to do it here ran past its timeout, was
-- killed, and rolled back every edition it had already done. pipeline/
-- list_position.py does the backfill one edition at a time, committing as it
-- goes, and is safe to re-run.

alter table career_metrics   add column if not exists list_position integer;
alter table career_metrics   add column if not exists list_position_ns integer;
alter table singleyr_metrics add column if not exists list_position integer;
alter table singleyr_metrics add column if not exists list_position_ns integer;

-- Reading a position off the row a score lands beside, which is what
-- score_standing does, wants the score and the position in one index.
create index if not exists career_metrics_edition_score_idx
    on career_metrics (edition_id, c desc) include (rank, list_position);
create index if not exists singleyr_metrics_edition_score_idx
    on singleyr_metrics (edition_id, c desc) include (rank, list_position);
