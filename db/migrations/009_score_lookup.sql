-- Where a composite score lands in its edition.
--
-- The what-if calculator recomputes a researcher's composite score from the
-- six indicators that make it up, then has to answer the only question that
-- makes the new score mean anything: how many people in that edition score
-- higher. That is a count over `c` inside one edition, and it runs on every
-- keystroke, so it cannot be a sequential scan of 230,333 rows.
--
-- Both the self-citation-included and the self-citation-excluded score get
-- an index, because the dashboard's toggle switches between them and a
-- reader should not be able to feel which one they picked.

create index if not exists career_metrics_edition_c_idx
    on career_metrics (edition_id, c desc);
create index if not exists career_metrics_edition_c_ns_idx
    on career_metrics (edition_id, c_ns desc);

create index if not exists singleyr_metrics_edition_c_idx
    on singleyr_metrics (edition_id, c desc);
create index if not exists singleyr_metrics_edition_c_ns_idx
    on singleyr_metrics (edition_id, c_ns desc);
