create table countries (
    country_code text primary key,
    name         text not null
);

create table institutions (
    institution_id text primary key,
    inst_name      text not null,
    country_code   text references countries(country_code)
);

create table fields (
    field_id text primary key,
    name     text not null
);

create table subfields (
    subfield_id text primary key,
    name        text not null,
    field_id    text references fields(field_id)
);

create table authors (
    author_id            text primary key,
    authfull_display     text not null,
    name_normalized      text not null,
    surname              text not null,
    first_initial        text not null,
    firstyr              integer,
    collision_group_size integer not null default 1,
    is_ambiguous         boolean not null default false,
    first_data_year      integer,
    last_data_year       integer
);

create index authors_name_normalized_idx on authors (name_normalized);
create index authors_block_idx on authors (surname, first_initial, firstyr);

create table editions (
    edition_id       text primary key,
    mendeley_version integer not null,
    data_year        integer not null,
    kind             text not null check (kind in ('career', 'singleyr')),
    observation_date date not null,
    published_date   date,
    source_filename  text,
    sha256           text,
    superseded_by    integer,
    columns_present  jsonb not null default '[]'::jsonb,
    unique (data_year, kind)
);

create table author_name_observations (
    observation_id    bigserial primary key,
    author_id         text not null references authors(author_id),
    edition_id        text not null references editions(edition_id),
    authfull_raw      text not null,
    resolution_method text not null,
    is_confident      boolean not null,
    unique (edition_id, authfull_raw, author_id)
);

create table metric_maxima (
    edition_id text not null references editions(edition_id),
    metric     text not null,
    max_value  double precision not null,
    primary key (edition_id, metric)
);

create table career_metrics (
    metric_id        bigserial primary key,
    author_id        text not null references authors(author_id),
    edition_id       text not null references editions(edition_id),
    institution_id   text references institutions(institution_id),
    field_id         text references fields(field_id),
    field_frac       double precision,
    subfield_1_id    text references subfields(subfield_id),
    subfield_1_frac  double precision,
    subfield_2_id    text references subfields(subfield_id),
    subfield_2_frac  double precision,
    observation_date date not null,

    rank integer, c double precision, h integer, hm double precision,
    nc bigint, np integer, nps integer, ncs bigint, cpsf integer,
    ncsf bigint, npsfl integer, ncsfl bigint, npciting bigint,
    cprat double precision, np_cited integer,

    rank_ns integer, c_ns double precision, h_ns integer, hm_ns double precision,
    nc_ns bigint, nps_ns integer, ncs_ns bigint, cpsf_ns integer,
    ncsf_ns bigint, npsfl_ns integer, ncsfl_ns bigint, npciting_ns bigint,
    cprat_ns double precision, np_cited_ns integer,

    self_pct double precision, firstyr integer, lastyr integer,
    rank_subfield integer, rank_subfield_ns integer, subfield_count integer,

    np_rw integer, nc_to_rw bigint, nc_rw bigint,
    np_d integer, nc_d bigint,

    unique (author_id, edition_id)
);

create index career_metrics_author_idx on career_metrics (author_id);
create index career_metrics_edition_idx on career_metrics (edition_id);
create index career_metrics_field_idx on career_metrics (field_id, edition_id);
create index career_metrics_cntry_idx on career_metrics (institution_id, edition_id);

create table singleyr_metrics (
    metric_id        bigserial primary key,
    author_id        text not null references authors(author_id),
    edition_id       text not null references editions(edition_id),
    institution_id   text references institutions(institution_id),
    field_id         text references fields(field_id),
    field_frac       double precision,
    subfield_1_id    text references subfields(subfield_id),
    subfield_1_frac  double precision,
    subfield_2_id    text references subfields(subfield_id),
    subfield_2_frac  double precision,
    observation_date date not null,

    rank integer, c double precision, h integer, hm double precision,
    nc bigint, np integer, nps integer, ncs bigint, cpsf integer,
    ncsf bigint, npsfl integer, ncsfl bigint, npciting bigint,
    cprat double precision, np_cited integer,

    rank_ns integer, c_ns double precision, h_ns integer, hm_ns double precision,
    nc_ns bigint, nps_ns integer, ncs_ns bigint, cpsf_ns integer,
    ncsf_ns bigint, npsfl_ns integer, ncsfl_ns bigint, npciting_ns bigint,
    cprat_ns double precision, np_cited_ns integer,

    self_pct double precision, firstyr integer, lastyr integer,
    rank_subfield integer, rank_subfield_ns integer, subfield_count integer,

    np_rw integer, nc_to_rw bigint, nc_rw bigint,
    np_d integer, nc_d bigint,

    unique (author_id, edition_id)
);

create index singleyr_metrics_author_idx on singleyr_metrics (author_id);
create index singleyr_metrics_edition_idx on singleyr_metrics (edition_id);
create index singleyr_metrics_field_idx on singleyr_metrics (field_id, edition_id);
create index singleyr_metrics_cntry_idx on singleyr_metrics (institution_id, edition_id);
