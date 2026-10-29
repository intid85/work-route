-- Work Route community (Q&A boards). Run once in the Supabase SQL editor.
-- Anonymous posting with nickname + password (hashed). Reads are public; writes only through functions.
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.posts (
  id bigint generated always as identity primary key,
  lang text not null default 'ko' check (lang in ('ko','en','vi','id','es')),
  board text not null check (board in ('general','us','ca','uk','au','nz','de','jp','sg','kr')),
  kind text not null default 'qa' check (kind in ('qa')),
  title text not null check (char_length(title) between 2 and 120),
  body text not null check (char_length(body) between 2 and 8000),
  nickname text not null check (char_length(nickname) between 1 and 20),
  comment_count int not null default 0,
  hidden boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz
);
create index if not exists posts_board_idx on public.posts (lang, board, created_at desc) where not hidden;

create table if not exists public.comments (
  id bigint generated always as identity primary key,
  post_id bigint not null references public.posts(id) on delete cascade,
  body text not null check (char_length(body) between 1 and 4000),
  nickname text not null check (char_length(nickname) between 1 and 20),
  hidden boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists comments_post_idx on public.comments (post_id, created_at) where not hidden;

-- Password hashes live apart from the public rows and are never readable through the API.
create table if not exists public.secrets (
  kind text not null check (kind in ('post','comment')),
  ref_id bigint not null,
  pw_hash text not null,
  primary key (kind, ref_id)
);

alter table public.posts enable row level security;
alter table public.comments enable row level security;
alter table public.secrets enable row level security;

drop policy if exists posts_read on public.posts;
create policy posts_read on public.posts for select to anon, authenticated using (not hidden);
drop policy if exists comments_read on public.comments;
create policy comments_read on public.comments for select to anon, authenticated using (not hidden);
-- no policies on secrets: nobody can read or write it through the API

revoke insert, update, delete on public.posts, public.comments from anon, authenticated;
revoke all on public.secrets from anon, authenticated;

-- simple flood guard: max 5 posts / 20 comments per minute site-wide per nickname
create or replace function public.create_post(p_lang text, p_board text, p_title text, p_body text, p_nickname text, p_password text)
returns bigint language plpgsql security definer set search_path = public, extensions as $$
declare new_id bigint;
begin
  if char_length(coalesce(p_password,'')) < 4 then raise exception '비밀번호는 4자 이상'; end if;
  if (select count(*) from posts where nickname = trim(p_nickname) and created_at > now() - interval '1 minute') >= 5 then
    raise exception '잠시 후 다시 시도하세요';
  end if;
  insert into posts (lang, board, title, body, nickname)
    values (p_lang, p_board, trim(p_title), trim(p_body), trim(p_nickname)) returning id into new_id;
  insert into secrets values ('post', new_id, crypt(p_password, gen_salt('bf')));
  return new_id;
end $$;

create or replace function public.update_post(p_id bigint, p_password text, p_title text, p_body text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
begin
  if not exists (select 1 from secrets where kind='post' and ref_id=p_id and pw_hash = crypt(p_password, pw_hash)) then
    raise exception '비밀번호가 맞지 않습니다';
  end if;
  update posts set title = trim(p_title), body = trim(p_body), updated_at = now() where id = p_id and not hidden;
  return true;
end $$;

create or replace function public.delete_post(p_id bigint, p_password text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
begin
  if not exists (select 1 from secrets where kind='post' and ref_id=p_id and pw_hash = crypt(p_password, pw_hash)) then
    raise exception '비밀번호가 맞지 않습니다';
  end if;
  update posts set hidden = true where id = p_id;
  return true;
end $$;

create or replace function public.create_comment(p_post_id bigint, p_body text, p_nickname text, p_password text)
returns bigint language plpgsql security definer set search_path = public, extensions as $$
declare new_id bigint;
begin
  if char_length(coalesce(p_password,'')) < 4 then raise exception '비밀번호는 4자 이상'; end if;
  if not exists (select 1 from posts where id = p_post_id and not hidden) then raise exception '글이 없습니다'; end if;
  if (select count(*) from comments where nickname = trim(p_nickname) and created_at > now() - interval '1 minute') >= 20 then
    raise exception '잠시 후 다시 시도하세요';
  end if;
  insert into comments (post_id, body, nickname) values (p_post_id, trim(p_body), trim(p_nickname)) returning id into new_id;
  insert into secrets values ('comment', new_id, crypt(p_password, gen_salt('bf')));
  update posts set comment_count = comment_count + 1 where id = p_post_id;
  return new_id;
end $$;

create or replace function public.delete_comment(p_id bigint, p_password text)
returns boolean language plpgsql security definer set search_path = public, extensions as $$
declare pid bigint;
begin
  if not exists (select 1 from secrets where kind='comment' and ref_id=p_id and pw_hash = crypt(p_password, pw_hash)) then
    raise exception '비밀번호가 맞지 않습니다';
  end if;
  update comments set hidden = true where id = p_id and not hidden returning post_id into pid;
  if pid is not null then update posts set comment_count = greatest(comment_count - 1, 0) where id = pid; end if;
  return true;
end $$;

revoke all on function public.create_post, public.update_post, public.delete_post, public.create_comment, public.delete_comment from public;
grant execute on function public.create_post, public.update_post, public.delete_post, public.create_comment, public.delete_comment to anon, authenticated;
grant select on public.posts, public.comments to anon, authenticated;
