create schema if not exists extensions;
create extension if not exists pg_trgm with schema extensions;

alter table public.meeting_transcripts
  add column search_vector tsvector
  generated always as (
    pg_catalog.to_tsvector('english'::regconfig, content)
  ) stored;

create index meeting_transcripts_search_vector_idx
  on public.meeting_transcripts using gin (search_vector);

set search_path = pg_catalog, public, extensions;

create index meetings_title_trgm_idx
  on public.meetings using gin (title gin_trgm_ops);

reset search_path;

create function public.search_my_meetings(
  p_query text,
  p_status text default 'all',
  p_limit integer default 25
)
returns table (
  meeting_id uuid,
  title text,
  description text,
  status text,
  meeting_date timestamptz,
  created_at timestamptz,
  updated_at timestamptz,
  has_transcript boolean,
  has_intelligence boolean,
  processing_stage text,
  last_updated timestamptz,
  search_context text,
  matched_in text
)
language plpgsql
stable
security invoker
set search_path = pg_catalog
as $$
begin
  if p_query is null
     or pg_catalog.length(pg_catalog.btrim(p_query)) < 3
     or pg_catalog.length(pg_catalog.btrim(p_query)) > 200 then
    raise exception using
      errcode = '22023',
      message = 'Meeting search query must contain 3 to 200 characters';
  end if;

  if p_status is null
     or p_status not in ('all', 'processing', 'completed', 'failed') then
    raise exception using
      errcode = '22023',
      message = 'Invalid meeting status filter';
  end if;

  if p_limit is null or p_limit < 1 or p_limit > 50 then
    raise exception using
      errcode = '22023',
      message = 'Meeting search limit must be between 1 and 50';
  end if;

  return query
  with query_values as (
    select
      pg_catalog.plainto_tsquery(
        'english'::regconfig,
        pg_catalog.btrim(p_query)
      ) as terms,
      '%' || pg_catalog.replace(
        pg_catalog.replace(
          pg_catalog.replace(pg_catalog.btrim(p_query), E'\\', E'\\\\'),
          '%',
          E'\\%'
        ),
        '_',
        E'\\_'
      ) || '%' as title_pattern
  ),
  matches as (
    select
      m.id as meeting_id,
      true as title_match,
      false as transcript_match,
      1.0::real as relevance
    from public.meetings as m
    cross join query_values as q
    where m.owner_id = auth.uid()
      and m.title ilike q.title_pattern escape E'\\'

    union all

    select
      m.id as meeting_id,
      false as title_match,
      true as transcript_match,
      pg_catalog.ts_rank(t.search_vector, q.terms) as relevance
    from public.meeting_transcripts as t
    join public.meetings as m on m.id = t.meeting_id
    cross join query_values as q
    where m.owner_id = auth.uid()
      and t.search_vector @@ q.terms
  ),
  ranked_matches as (
    select
      matches.meeting_id,
      pg_catalog.bool_or(matches.title_match) as title_match,
      pg_catalog.bool_or(matches.transcript_match) as transcript_match,
      pg_catalog.max(matches.relevance)
        + case when pg_catalog.bool_or(matches.title_match) then 0.25 else 0 end
        as relevance
    from matches
    group by matches.meeting_id
  ),
  limited_matches as (
    select
      r.meeting_id,
      r.title_match,
      r.transcript_match,
      r.relevance
    from ranked_matches as r
    join public.meetings as m on m.id = r.meeting_id
    left join public.meeting_processing as p on p.meeting_id = m.id
    where p_status = 'all'
       or (
         p_status = 'processing'
         and (
           m.status = 'processing'
           or p.stage in ('pending', 'transcribing', 'analyzing', 'retrying')
         )
       )
       or (
         p_status = 'completed'
         and (m.status = 'completed' or p.stage = 'completed')
       )
       or (
         p_status = 'failed'
         and (m.status = 'failed' or p.stage = 'failed')
       )
    order by r.relevance desc, m.created_at desc
    limit p_limit
  )
  select
    m.id,
    m.title,
    m.description,
    m.status,
    m.meeting_date,
    m.created_at,
    m.updated_at,
    t.meeting_id is not null,
    i.meeting_id is not null,
    p.stage,
    greatest(
      m.updated_at,
      coalesce(t.updated_at, m.updated_at),
      coalesce(i.updated_at, m.updated_at),
      coalesce(p.updated_at, m.updated_at)
    ),
    case
      when lm.transcript_match then pg_catalog.ts_headline(
        'english'::regconfig,
        t.content,
        q.terms,
        'MaxWords=24,MinWords=8,StartSel=[,StopSel=]'
      )
      else null
    end,
    case
      when lm.title_match and lm.transcript_match then 'title_and_transcript'
      when lm.transcript_match then 'transcript'
      else 'title'
    end
  from limited_matches as lm
  join public.meetings as m on m.id = lm.meeting_id
  left join public.meeting_transcripts as t on t.meeting_id = m.id
  left join public.meeting_insights as i on i.meeting_id = m.id
  left join public.meeting_processing as p on p.meeting_id = m.id
  cross join query_values as q
  order by lm.relevance desc, m.created_at desc;
end;
$$;

revoke all on function public.search_my_meetings(text, text, integer)
  from public, anon;
grant execute on function public.search_my_meetings(text, text, integer)
  to authenticated;
