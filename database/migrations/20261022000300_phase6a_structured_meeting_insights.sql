-- Phase 6A: add structured discussion, question, and next-step insights.

alter table public.meeting_insights
  add column discussion_points jsonb not null default '[]'::jsonb,
  add column open_questions jsonb not null default '[]'::jsonb,
  add column next_steps jsonb not null default '[]'::jsonb;
