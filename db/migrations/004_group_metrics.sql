-- Task 7: group aggregates as a materialized view.
--
-- Replaces code_test_preproc/02_data_preproc_for_speed.ipynb's
-- process_data_by_country, which computed a five-number summary (min, q1,
-- median, q3, max) plus a count, for every metric, for every country, field
-- and institution, for every edition, and pickled the result.
--
-- RULING R19: numbered 004, not 002 as the brief said, because migrations
-- apply in sorted filename order and this view groups by country_code, which
-- only exists once 003_row_country.sql has run.
--
-- RULING R17: grouped by career_metrics.country_code / singleyr_metrics.country_code
-- directly (added by 003), not by joining through institutions. 22,327 rows
-- have no institution at all and would vanish from a country aggregate built
-- by joining through institutions; another ~39,476 carry a country that
-- disagrees with their institution's.
--
-- Metrics covered: process_data_by_country's metrics_list was
--   ['rank','c','nc','h','hm','ncs','ncsf','ncsfl','nps','cpsf','npsfl','npciting']
-- plus the same list with a ' (ns)' suffix, plus 'np' and 'self%' -- 26 in
-- total. Every one of those has a same-named (non-suffixed) or _ns-suffixed
-- or self_pct column on career_metrics / singleyr_metrics (001_schema.sql).
-- Metric names here match the column names (e.g. 'nc_ns', 'self_pct'); the
-- notebook's cosmetic '(ns)'/'self%' spellings are a display concern for
-- whatever reads this view, not stored here.
--
-- Null handling: process_data_by_country dropped rows with a null grouping
-- key (dropna(subset=[aggmetric])) but did NOT drop rows with a null value
-- for an individual metric before computing percentiles over that metric's
-- column -- a stray NaN would have silently poisoned that one metric's
-- summary. This view instead excludes, per metric, only the rows where that
-- particular metric is null, so a null in one column never contaminates
-- another metric's summary and `n` is an honest non-null count for that
-- metric. This is a deliberate improvement, not a faithful reproduction of
-- that incidental behaviour.
--
-- Quartiles use percentile_cont, matching the notebook's
-- np.percentile(stuff, [25, 50, 75]) (linear interpolation).
create materialized view group_metrics as
with career_unpivot as (
    select
        cm.edition_id,
        cm.country_code,
        cm.field_id,
        cm.institution_id,
        v.metric,
        v.value
    from career_metrics cm
    cross join lateral (values
        ('rank', cm.rank::double precision),
        ('c', cm.c),
        ('nc', cm.nc::double precision),
        ('h', cm.h::double precision),
        ('hm', cm.hm),
        ('ncs', cm.ncs::double precision),
        ('ncsf', cm.ncsf::double precision),
        ('ncsfl', cm.ncsfl::double precision),
        ('nps', cm.nps::double precision),
        ('cpsf', cm.cpsf::double precision),
        ('npsfl', cm.npsfl::double precision),
        ('npciting', cm.npciting::double precision),
        ('rank_ns', cm.rank_ns::double precision),
        ('c_ns', cm.c_ns),
        ('nc_ns', cm.nc_ns::double precision),
        ('h_ns', cm.h_ns::double precision),
        ('hm_ns', cm.hm_ns),
        ('ncs_ns', cm.ncs_ns::double precision),
        ('ncsf_ns', cm.ncsf_ns::double precision),
        ('ncsfl_ns', cm.ncsfl_ns::double precision),
        ('nps_ns', cm.nps_ns::double precision),
        ('cpsf_ns', cm.cpsf_ns::double precision),
        ('npsfl_ns', cm.npsfl_ns::double precision),
        ('npciting_ns', cm.npciting_ns::double precision),
        ('np', cm.np::double precision),
        ('self_pct', cm.self_pct)
    ) as v(metric, value)
    where v.value is not null
),
singleyr_unpivot as (
    select
        sm.edition_id,
        sm.country_code,
        sm.field_id,
        sm.institution_id,
        v.metric,
        v.value
    from singleyr_metrics sm
    cross join lateral (values
        ('rank', sm.rank::double precision),
        ('c', sm.c),
        ('nc', sm.nc::double precision),
        ('h', sm.h::double precision),
        ('hm', sm.hm),
        ('ncs', sm.ncs::double precision),
        ('ncsf', sm.ncsf::double precision),
        ('ncsfl', sm.ncsfl::double precision),
        ('nps', sm.nps::double precision),
        ('cpsf', sm.cpsf::double precision),
        ('npsfl', sm.npsfl::double precision),
        ('npciting', sm.npciting::double precision),
        ('rank_ns', sm.rank_ns::double precision),
        ('c_ns', sm.c_ns),
        ('nc_ns', sm.nc_ns::double precision),
        ('h_ns', sm.h_ns::double precision),
        ('hm_ns', sm.hm_ns),
        ('ncs_ns', sm.ncs_ns::double precision),
        ('ncsf_ns', sm.ncsf_ns::double precision),
        ('ncsfl_ns', sm.ncsfl_ns::double precision),
        ('nps_ns', sm.nps_ns::double precision),
        ('cpsf_ns', sm.cpsf_ns::double precision),
        ('npsfl_ns', sm.npsfl_ns::double precision),
        ('npciting_ns', sm.npciting_ns::double precision),
        ('np', sm.np::double precision),
        ('self_pct', sm.self_pct)
    ) as v(metric, value)
    where v.value is not null
)
select edition_id, 'cntry'::text as group_kind, country_code as group_value, metric,
       min(value) as min,
       percentile_cont(0.25) within group (order by value) as q1,
       percentile_cont(0.5) within group (order by value) as median,
       percentile_cont(0.75) within group (order by value) as q3,
       max(value) as max,
       count(*) as n
from career_unpivot
where country_code is not null
group by edition_id, country_code, metric
union all
select cu.edition_id, 'sm-field'::text, f.name, cu.metric,
       min(cu.value), percentile_cont(0.25) within group (order by cu.value),
       percentile_cont(0.5) within group (order by cu.value),
       percentile_cont(0.75) within group (order by cu.value),
       max(cu.value), count(*)
from career_unpivot cu
join fields f on f.field_id = cu.field_id
where cu.field_id is not null
group by cu.edition_id, f.name, cu.metric
union all
select cu.edition_id, 'inst_name'::text, i.inst_name, cu.metric,
       min(cu.value), percentile_cont(0.25) within group (order by cu.value),
       percentile_cont(0.5) within group (order by cu.value),
       percentile_cont(0.75) within group (order by cu.value),
       max(cu.value), count(*)
from career_unpivot cu
join institutions i on i.institution_id = cu.institution_id
where cu.institution_id is not null
group by cu.edition_id, i.inst_name, cu.metric
union all
select edition_id, 'cntry'::text, country_code, metric,
       min(value), percentile_cont(0.25) within group (order by value),
       percentile_cont(0.5) within group (order by value),
       percentile_cont(0.75) within group (order by value),
       max(value), count(*)
from singleyr_unpivot
where country_code is not null
group by edition_id, country_code, metric
union all
select su.edition_id, 'sm-field'::text, f.name, su.metric,
       min(su.value), percentile_cont(0.25) within group (order by su.value),
       percentile_cont(0.5) within group (order by su.value),
       percentile_cont(0.75) within group (order by su.value),
       max(su.value), count(*)
from singleyr_unpivot su
join fields f on f.field_id = su.field_id
where su.field_id is not null
group by su.edition_id, f.name, su.metric
union all
select su.edition_id, 'inst_name'::text, i.inst_name, su.metric,
       min(su.value), percentile_cont(0.25) within group (order by su.value),
       percentile_cont(0.5) within group (order by su.value),
       percentile_cont(0.75) within group (order by su.value),
       max(su.value), count(*)
from singleyr_unpivot su
join institutions i on i.institution_id = su.institution_id
where su.institution_id is not null
group by su.edition_id, i.inst_name, su.metric
with data;

create unique index group_metrics_key_idx
    on group_metrics (edition_id, group_kind, group_value, metric);
