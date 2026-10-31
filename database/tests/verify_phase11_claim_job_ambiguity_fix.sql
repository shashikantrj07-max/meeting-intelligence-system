-- Read-only catalog verification. Run only after the corrective migration.
do $$
declare
  claim_function oid :=
    'public.claim_next_meeting_processing_job(uuid,integer)'::regprocedure;
  function_definition text;
begin
  select pg_catalog.lower(pg_catalog.pg_get_functiondef(claim_function))
  into function_definition;

  if function_definition not like
    '%on conflict on constraint meeting_processing_meeting_id_key do update%'
  then
    raise exception 'Claim RPC does not use the unambiguous meeting-processing constraint';
  end if;

  if function_definition like '%on conflict (meeting_id)%' then
    raise exception 'Claim RPC still contains the ambiguous conflict target';
  end if;

  if not (
    select p.prosecdef
      and p.proconfig @> array['search_path=pg_catalog']
    from pg_catalog.pg_proc as p
    where p.oid = claim_function
  ) then
    raise exception 'Claim RPC security properties differ from the expected contract';
  end if;

  if not pg_catalog.has_function_privilege('service_role', claim_function, 'EXECUTE')
    or pg_catalog.has_function_privilege('anon', claim_function, 'EXECUTE')
    or pg_catalog.has_function_privilege('authenticated', claim_function, 'EXECUTE')
  then
    raise exception 'Claim RPC execute grants differ from the expected contract';
  end if;
end;
$$;
