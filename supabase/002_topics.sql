-- Topics inside each country board, and an "official" flag for operator posts. Run once after schema.sql.
alter table public.posts add column if not exists topic text not null default 'work'
  check (topic in ('wh','study','work','pr','life'));
alter table public.posts add column if not exists official boolean not null default false;
create index if not exists posts_topic_idx on public.posts (lang, board, topic, created_at desc) where not hidden;

drop function if exists public.create_post(text, text, text, text, text, text);
create or replace function public.create_post(p_lang text, p_board text, p_topic text, p_title text, p_body text, p_nickname text, p_password text)
returns bigint language plpgsql security definer set search_path = public, extensions as $$
declare new_id bigint;
begin
  if char_length(coalesce(p_password,'')) < 4 then raise exception '비밀번호는 4자 이상'; end if;
  if trim(p_nickname) ilike '%운영자%' or trim(p_nickname) ilike '%work route%' then raise exception '사용할 수 없는 닉네임입니다'; end if;
  if (select count(*) from posts where nickname = trim(p_nickname) and created_at > now() - interval '1 minute') >= 5 then
    raise exception '잠시 후 다시 시도하세요';
  end if;
  insert into posts (lang, board, topic, title, body, nickname)
    values (p_lang, p_board, p_topic, trim(p_title), trim(p_body), trim(p_nickname)) returning id into new_id;
  insert into secrets values ('post', new_id, crypt(p_password, gen_salt('bf')));
  return new_id;
end $$;
revoke all on function public.create_post(text, text, text, text, text, text, text) from public;
grant execute on function public.create_post(text, text, text, text, text, text, text) to anon, authenticated;

-- operator posts are inserted directly here (SQL editor runs as the owner), so nobody else can mark a post official
