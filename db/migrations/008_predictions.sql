-- Model estimates, kept apart from anything the publishers reported.
--
-- The retraction columns arrived with Mendeley version 7. career-2017 through
-- career-2022 carry no retraction data at all -- 955,512 rows where the value
-- is missing because nothing was tracked, not because nothing was retracted.
-- A model trained on career-2023 and tested on the held-out career-2024
-- edition estimates what those six editions would have said.
--
-- These are estimates for a quantity that was never measured. They live in
-- their own table rather than as columns on career_metrics so that no query
-- can return one beside a published figure without saying which is which,
-- and every row carries the run it came from.

create table if not exists prediction_runs (
    task            text primary key,
    task_type       text        not null,
    target_column   text        not null,
    trained_at      timestamptz not null default now(),
    epochs          integer,
    -- What the model scored on data it never saw. This is the honest summary
    -- of how much weight the estimates below can carry, and anything that
    -- displays them should display this too.
    metrics         jsonb       not null,
    -- The trivial baseline for the same split. A score without one is not a
    -- result: on the dropout task a single flag recording our own resolver's
    -- confusion scored 0.776 against the model's 0.814.
    baseline        jsonb       not null,
    -- Which graph the run used, so a core-graph result and an enriched-graph
    -- result cannot be confused for one another.
    graph_variant   text        not null default 'core',
    notes           text
);

create table if not exists predictions (
    task            text    not null references prediction_runs(task)
                            on delete cascade,
    metric_id       bigint  not null,
    author_id       text    not null references authors(author_id),
    edition_id      text    not null references editions(edition_id),
    -- Exactly one of these is set, depending on the task type.
    probability     double precision,
    value           double precision,
    primary key (task, metric_id)
);

create index if not exists predictions_author_idx
    on predictions (author_id, task);
create index if not exists predictions_edition_idx
    on predictions (edition_id, task);
