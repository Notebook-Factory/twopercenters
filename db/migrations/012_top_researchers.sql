-- The ten highest researchers per metric, per edition.
--
-- The fact tables carry one index that helps a question of this shape,
-- (edition_id, c desc), and nothing for the other six indicators. Measured
-- cold on career-2024: the top ten by c takes 46 ms, by h 38 ms, and by ncsf
-- 640 ms, because that one sorts about 150,000 rows to return ten. Seven
-- metrics in two column sets, on every change of the picker, is several
-- seconds of sorting for an answer that changes only when an edition is
-- loaded.
--
-- The alternative was 24 new btree indexes, one per metric per column set per
-- fact table. That is a large amount of index to carry for seven questions
-- whose complete answer is under 2,100 rows: 7 metrics x 2 column sets x 10
-- positions x 15 editions.
--
-- What is stored is the ordering and nothing else. The rank, the list
-- position, the institution and the field all come from the fact row, which
-- the read joins anyway to resolve names, so storing copies here would add a
-- second place for them to go stale and would make this fill depend on
-- pipeline/list_position.py having already run.
--
-- Filled by refresh_top_researchers() in pipeline/build_relational.py, in the
-- same way metric_maxima is filled, and read by top_researchers() in
-- citations_lib/utils.py.

create table if not exists top_researchers (
    kind       text not null,
    edition_id text not null references editions(edition_id),
    metric     text not null,
    ns         boolean not null,
    position   smallint not null,
    author_id  text not null references authors(author_id),
    value      double precision not null,
    primary key (edition_id, metric, ns, position)
);

create index if not exists top_researchers_author_idx
    on top_researchers (author_id);
