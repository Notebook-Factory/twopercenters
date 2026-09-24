-- Migration 007: the two dropdown materialized views (review FINDING 4).
--
-- load_dropdown_opts() builds the option lists and the per-metric summary
-- statistics that the Compare and Author-vs-group tabs need in order to
-- render at all. Until this migration it did that with four `group by` scans
-- over both fact tables (2,730,673 rows): distinct country codes, distinct
-- institution names, distinct fields, and min/max/avg/stddev for twelve
-- metrics. That measured about 3 seconds warm on the development machine and
-- 7.2 seconds on the reviewer's, inside a callback, once per worker process.
--
-- Neither answer changes between builds, so both are precomputed here. This
-- is the same trade group_metrics already makes (RULING R21/R24), at a far
-- smaller size: the two views together are a few thousand rows.
--
-- Like group_metrics, these do NOT update themselves when the fact tables
-- change, so pipeline/build_relational.py refreshes them at the end of a
-- build, next to the group_metrics refresh (RULING R24).
--
-- Both views are created empty-but-populated on a fresh database, because
-- migrations run before any data is loaded. That is fine and is why the
-- build refreshes them; it is also why the build now refuses to run with no
-- editions (FINDING 3), so an empty database cannot be mistaken for a
-- successful build.

drop materialized view if exists dropdown_options;

create materialized view dropdown_options as
select edition_id, 'cntry'::text as option_kind, country_code as option_value
  from career_metrics
 where country_code is not null
 group by 1, 3
union all
select m.edition_id, 'inst_name'::text, i.inst_name
  from career_metrics m
  join institutions i on i.institution_id = m.institution_id
 group by 1, 3
union all
select m.edition_id, 'sm-field'::text, f.name
  from career_metrics m
  join fields f on f.field_id = m.field_id
 group by 1, 3
union all
select edition_id, 'cntry'::text, country_code
  from singleyr_metrics
 where country_code is not null
 group by 1, 3
union all
select m.edition_id, 'inst_name'::text, i.inst_name
  from singleyr_metrics m
  join institutions i on i.institution_id = m.institution_id
 group by 1, 3
union all
select m.edition_id, 'sm-field'::text, f.name
  from singleyr_metrics m
  join fields f on f.field_id = m.field_id
 group by 1, 3;

create index dropdown_options_idx
    on dropdown_options (edition_id, option_kind, option_value);

drop materialized view if exists dropdown_stats;

-- One row per (edition, metric). The wide subquery is one scan per fact
-- table; the lateral VALUES turns its 48 columns back into twelve rows, so
-- the view keeps the narrow shape the reader wants without scanning twice.
-- min/max are cast to double precision for a single uniform column type;
-- citations_lib/utils.py hands whole values back as ints, which is the type
-- the integer-valued metrics (h, nc, ncs, ...) had before this view existed.
create materialized view dropdown_stats as
select w.edition_id, v.metric, v.min_value, v.max_value,
       v.mean_value, v.std_value
from (
    select
        edition_id,
        min(nc)::double precision          as nc_min,
        max(nc)::double precision          as nc_max,
        avg(nc)::double precision          as nc_avg,
        stddev_samp(nc)::double precision  as nc_std,
        min(h)::double precision          as h_min,
        max(h)::double precision          as h_max,
        avg(h)::double precision          as h_avg,
        stddev_samp(h)::double precision  as h_std,
        min(hm)::double precision          as hm_min,
        max(hm)::double precision          as hm_max,
        avg(hm)::double precision          as hm_avg,
        stddev_samp(hm)::double precision  as hm_std,
        min(ncs)::double precision          as ncs_min,
        max(ncs)::double precision          as ncs_max,
        avg(ncs)::double precision          as ncs_avg,
        stddev_samp(ncs)::double precision  as ncs_std,
        min(ncsf)::double precision          as ncsf_min,
        max(ncsf)::double precision          as ncsf_max,
        avg(ncsf)::double precision          as ncsf_avg,
        stddev_samp(ncsf)::double precision  as ncsf_std,
        min(ncsfl)::double precision          as ncsfl_min,
        max(ncsfl)::double precision          as ncsfl_max,
        avg(ncsfl)::double precision          as ncsfl_avg,
        stddev_samp(ncsfl)::double precision  as ncsfl_std,
        min(nc_ns)::double precision          as nc_ns_min,
        max(nc_ns)::double precision          as nc_ns_max,
        avg(nc_ns)::double precision          as nc_ns_avg,
        stddev_samp(nc_ns)::double precision  as nc_ns_std,
        min(h_ns)::double precision          as h_ns_min,
        max(h_ns)::double precision          as h_ns_max,
        avg(h_ns)::double precision          as h_ns_avg,
        stddev_samp(h_ns)::double precision  as h_ns_std,
        min(hm_ns)::double precision          as hm_ns_min,
        max(hm_ns)::double precision          as hm_ns_max,
        avg(hm_ns)::double precision          as hm_ns_avg,
        stddev_samp(hm_ns)::double precision  as hm_ns_std,
        min(ncs_ns)::double precision          as ncs_ns_min,
        max(ncs_ns)::double precision          as ncs_ns_max,
        avg(ncs_ns)::double precision          as ncs_ns_avg,
        stddev_samp(ncs_ns)::double precision  as ncs_ns_std,
        min(ncsf_ns)::double precision          as ncsf_ns_min,
        max(ncsf_ns)::double precision          as ncsf_ns_max,
        avg(ncsf_ns)::double precision          as ncsf_ns_avg,
        stddev_samp(ncsf_ns)::double precision  as ncsf_ns_std,
        min(ncsfl_ns)::double precision          as ncsfl_ns_min,
        max(ncsfl_ns)::double precision          as ncsfl_ns_max,
        avg(ncsfl_ns)::double precision          as ncsfl_ns_avg,
        stddev_samp(ncsfl_ns)::double precision  as ncsfl_ns_std
    from career_metrics
    group by edition_id
) w,
lateral (values
        ('nc', w.nc_min, w.nc_max, w.nc_avg, w.nc_std),
        ('h', w.h_min, w.h_max, w.h_avg, w.h_std),
        ('hm', w.hm_min, w.hm_max, w.hm_avg, w.hm_std),
        ('ncs', w.ncs_min, w.ncs_max, w.ncs_avg, w.ncs_std),
        ('ncsf', w.ncsf_min, w.ncsf_max, w.ncsf_avg, w.ncsf_std),
        ('ncsfl', w.ncsfl_min, w.ncsfl_max, w.ncsfl_avg, w.ncsfl_std),
        ('nc_ns', w.nc_ns_min, w.nc_ns_max, w.nc_ns_avg, w.nc_ns_std),
        ('h_ns', w.h_ns_min, w.h_ns_max, w.h_ns_avg, w.h_ns_std),
        ('hm_ns', w.hm_ns_min, w.hm_ns_max, w.hm_ns_avg, w.hm_ns_std),
        ('ncs_ns', w.ncs_ns_min, w.ncs_ns_max, w.ncs_ns_avg, w.ncs_ns_std),
        ('ncsf_ns', w.ncsf_ns_min, w.ncsf_ns_max, w.ncsf_ns_avg, w.ncsf_ns_std),
        ('ncsfl_ns', w.ncsfl_ns_min, w.ncsfl_ns_max, w.ncsfl_ns_avg, w.ncsfl_ns_std)
) as v(metric, min_value, max_value, mean_value, std_value)
union all
select z.edition_id, v.metric, v.min_value, v.max_value,
       v.mean_value, v.std_value
from (
    select
        edition_id,
        min(nc)::double precision          as nc_min,
        max(nc)::double precision          as nc_max,
        avg(nc)::double precision          as nc_avg,
        stddev_samp(nc)::double precision  as nc_std,
        min(h)::double precision          as h_min,
        max(h)::double precision          as h_max,
        avg(h)::double precision          as h_avg,
        stddev_samp(h)::double precision  as h_std,
        min(hm)::double precision          as hm_min,
        max(hm)::double precision          as hm_max,
        avg(hm)::double precision          as hm_avg,
        stddev_samp(hm)::double precision  as hm_std,
        min(ncs)::double precision          as ncs_min,
        max(ncs)::double precision          as ncs_max,
        avg(ncs)::double precision          as ncs_avg,
        stddev_samp(ncs)::double precision  as ncs_std,
        min(ncsf)::double precision          as ncsf_min,
        max(ncsf)::double precision          as ncsf_max,
        avg(ncsf)::double precision          as ncsf_avg,
        stddev_samp(ncsf)::double precision  as ncsf_std,
        min(ncsfl)::double precision          as ncsfl_min,
        max(ncsfl)::double precision          as ncsfl_max,
        avg(ncsfl)::double precision          as ncsfl_avg,
        stddev_samp(ncsfl)::double precision  as ncsfl_std,
        min(nc_ns)::double precision          as nc_ns_min,
        max(nc_ns)::double precision          as nc_ns_max,
        avg(nc_ns)::double precision          as nc_ns_avg,
        stddev_samp(nc_ns)::double precision  as nc_ns_std,
        min(h_ns)::double precision          as h_ns_min,
        max(h_ns)::double precision          as h_ns_max,
        avg(h_ns)::double precision          as h_ns_avg,
        stddev_samp(h_ns)::double precision  as h_ns_std,
        min(hm_ns)::double precision          as hm_ns_min,
        max(hm_ns)::double precision          as hm_ns_max,
        avg(hm_ns)::double precision          as hm_ns_avg,
        stddev_samp(hm_ns)::double precision  as hm_ns_std,
        min(ncs_ns)::double precision          as ncs_ns_min,
        max(ncs_ns)::double precision          as ncs_ns_max,
        avg(ncs_ns)::double precision          as ncs_ns_avg,
        stddev_samp(ncs_ns)::double precision  as ncs_ns_std,
        min(ncsf_ns)::double precision          as ncsf_ns_min,
        max(ncsf_ns)::double precision          as ncsf_ns_max,
        avg(ncsf_ns)::double precision          as ncsf_ns_avg,
        stddev_samp(ncsf_ns)::double precision  as ncsf_ns_std,
        min(ncsfl_ns)::double precision          as ncsfl_ns_min,
        max(ncsfl_ns)::double precision          as ncsfl_ns_max,
        avg(ncsfl_ns)::double precision          as ncsfl_ns_avg,
        stddev_samp(ncsfl_ns)::double precision  as ncsfl_ns_std
    from singleyr_metrics
    group by edition_id
) z,
lateral (values
        ('nc', z.nc_min, z.nc_max, z.nc_avg, z.nc_std),
        ('h', z.h_min, z.h_max, z.h_avg, z.h_std),
        ('hm', z.hm_min, z.hm_max, z.hm_avg, z.hm_std),
        ('ncs', z.ncs_min, z.ncs_max, z.ncs_avg, z.ncs_std),
        ('ncsf', z.ncsf_min, z.ncsf_max, z.ncsf_avg, z.ncsf_std),
        ('ncsfl', z.ncsfl_min, z.ncsfl_max, z.ncsfl_avg, z.ncsfl_std),
        ('nc_ns', z.nc_ns_min, z.nc_ns_max, z.nc_ns_avg, z.nc_ns_std),
        ('h_ns', z.h_ns_min, z.h_ns_max, z.h_ns_avg, z.h_ns_std),
        ('hm_ns', z.hm_ns_min, z.hm_ns_max, z.hm_ns_avg, z.hm_ns_std),
        ('ncs_ns', z.ncs_ns_min, z.ncs_ns_max, z.ncs_ns_avg, z.ncs_ns_std),
        ('ncsf_ns', z.ncsf_ns_min, z.ncsf_ns_max, z.ncsf_ns_avg, z.ncsf_ns_std),
        ('ncsfl_ns', z.ncsfl_ns_min, z.ncsfl_ns_max, z.ncsfl_ns_avg, z.ncsfl_ns_std)
) as v(metric, min_value, max_value, mean_value, std_value);

create index dropdown_stats_idx on dropdown_stats (edition_id, metric);
