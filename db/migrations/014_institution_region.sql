-- The region a city is in.
--
-- ROR's location carries a country_subdivision_name beside the city: Ohio
-- for Cleveland, Kanagawa for Yokohama, Bavaria for Munich. 136,657 of the
-- registry's 137,398 records have one, across 221 countries, so this is not
-- a US-only field even though a US state is the obvious example of it.
--
-- It was dropped when 013 was written, which left the dashboard saying
-- "Cleveland, United States" where it could have said which Cleveland.

alter table institution_ror add column if not exists region text;
