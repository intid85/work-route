/* Work Route community board: list, read, write, comment. Talks to Supabase REST directly. */
(function () {
  const root = document.querySelector('[data-community]');
  if (!root) return;
  const API = root.dataset.url + '/rest/v1';
  const KEY = root.dataset.key;
  const LANG = root.dataset.lang || 'ko';
  const BUILT = Date.parse(root.dataset.built || '') || 0;   // posts older than the build have static pages
  const BASE = root.dataset.base;                            // path to community/ from this page
  const BOARDS = Object.fromEntries(JSON.parse(root.dataset.boards));  // [[code, name], ...] in display order
  const T = {
    all: '전체', empty: '아직 글이 없습니다. 첫 질문을 남겨보세요.', write: '질문하기', more: '더 보기',
    title: '제목', body: '내용', nick: '닉네임', pw: '비밀번호(수정·삭제용, 4자 이상)', board: '나라',
    submit: '등록', cancel: '취소', comment: '답변 달기', comments: '답변', del: '삭제', edit: '수정',
    pwAsk: '비밀번호를 입력하세요', back: '목록으로', saved: '등록했습니다.', failed: '실패: ',
    deleted: '삭제했습니다.', noComments: '아직 답변이 없습니다.', loading: '불러오는 중…',
    rule: '개인정보(여권번호·연락처)와 광고·알선 글은 올리지 마세요. 정확한 내용은 각국 이민청에서 확인하세요.'
  };
  const H = { apikey: KEY, 'Content-Type': 'application/json' };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const when = iso => { const d = new Date(iso); const m = (Date.now() - d) / 6e4;
    return m < 1 ? '방금' : m < 60 ? Math.floor(m) + '분 전' : m < 1440 ? Math.floor(m / 60) + '시간 전' : d.toLocaleDateString('ko-KR'); };
  async function get(path) { const r = await fetch(API + path, { headers: H }); if (!r.ok) throw new Error((await r.json()).message || r.status); return r.json(); }
  async function rpc(fn, args) {
    const r = await fetch(API + '/rpc/' + fn, { method: 'POST', headers: H, body: JSON.stringify(args) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.message || r.status);
    return j;
  }
  const params = new URLSearchParams(location.search);
  let board = params.get('b') || root.dataset.board || '';
  const postId = params.get('p') || root.dataset.post || '';
  let offset = 0;
  const PAGE = 30;

  function postHref(p) {
    return Date.parse(p.created_at) < BUILT ? BASE + 'post/' + p.id + '/index.html' : BASE + 'index.html?p=' + p.id;
  }
  function setUrl(q) { history.replaceState(null, '', location.pathname + (q ? '?' + q : '')); }

  /* ---------- list ---------- */
  function tabs() {
    const codes = [''].concat(Object.keys(BOARDS));
    return '<div class="cm-tabs" role="tablist">' + codes.map(c =>
      `<button role="tab" data-b="${c}" aria-selected="${c === board}">${c ? esc(BOARDS[c]) : T.all}</button>`).join('') + '</div>';
  }
  async function showList() {
    root.innerHTML = tabs() +
      `<div class="cm-bar"><button class="cm-btn cm-btn--primary" data-act="new">${T.write}</button></div>` +
      `<ul class="cm-list" aria-live="polite"><li class="cm-empty">${T.loading}</li></ul>` +
      `<div class="cm-more" hidden><button class="cm-btn" data-act="more">${T.more}</button></div>`;
    offset = 0; await loadMore(true);
  }
  async function loadMore(first) {
    const ul = root.querySelector('.cm-list');
    let q = `/posts?select=id,board,title,nickname,comment_count,created_at&lang=eq.${LANG}&order=created_at.desc&limit=${PAGE}&offset=${offset}`;
    if (board) q += `&board=eq.${board}`;
    try {
      const rows = await get(q);
      if (first) ul.innerHTML = '';
      if (first && !rows.length) ul.innerHTML = `<li class="cm-empty">${T.empty}</li>`;
      ul.insertAdjacentHTML('beforeend', rows.map(p => `<li><a href="${postHref(p)}">
        <span class="cm-board">${esc(BOARDS[p.board] || '')}</span>
        <span class="cm-title">${esc(p.title)}</span>
        <span class="cm-meta">${esc(p.nickname)} · ${when(p.created_at)}${p.comment_count ? ` · ${T.comments} ${p.comment_count}` : ''}</span></a></li>`).join(''));
      offset += rows.length;
      root.querySelector('.cm-more').hidden = rows.length < PAGE;
    } catch (e) { ul.innerHTML = `<li class="cm-empty">${T.failed}${esc(e.message)}</li>`; }
  }

  /* ---------- write ---------- */
  function form(p) {
    const opts = Object.entries(BOARDS).map(([c, n]) => `<option value="${c}" ${c === (p ? p.board : board || 'general') ? 'selected' : ''}>${esc(n)}</option>`).join('');
    root.innerHTML = `<form class="cm-form">
      <p class="hint">${T.rule}</p>
      ${p ? '' : `<label>${T.board}<select name="board">${opts}</select></label>`}
      <label>${T.title}<input name="title" maxlength="120" required minlength="2" value="${p ? esc(p.title) : ''}"></label>
      <label>${T.body}<textarea name="body" rows="10" maxlength="8000" required minlength="2">${p ? esc(p.body) : ''}</textarea></label>
      ${p ? '' : `<div class="cm-row"><label>${T.nick}<input name="nick" maxlength="20" required autocomplete="nickname"></label>`}
      ${p ? `<label>${T.pw}<input name="pw" type="password" required minlength="4"></label>` :
            `<label>${T.pw}<input name="pw" type="password" required minlength="4" autocomplete="new-password"></label></div>`}
      <input name="website" class="cm-hp" tabindex="-1" autocomplete="off" aria-hidden="true">
      <div class="cm-bar"><button class="cm-btn cm-btn--primary" type="submit">${T.submit}</button>
      <button class="cm-btn" type="button" data-act="${p ? 'view' : 'list'}" data-id="${p ? p.id : ''}">${T.cancel}</button></div>
      <p class="cm-msg" role="status"></p></form>`;
    try { root.querySelector('[name=nick]').value = localStorage.getItem('cm-nick') || ''; } catch (e) {}
    root.querySelector('form').addEventListener('submit', async ev => {
      ev.preventDefault();
      const f = ev.target, msg = f.querySelector('.cm-msg');
      if (f.website.value) return;
      f.querySelector('[type=submit]').disabled = true;
      try {
        if (p) {
          await rpc('update_post', { p_id: p.id, p_password: f.pw.value, p_title: f.title.value, p_body: f.body.value });
          showPost(p.id);
        } else {
          try { localStorage.setItem('cm-nick', f.nick.value); } catch (e) {}
          const id = await rpc('create_post', { p_lang: LANG, p_board: f.board.value, p_title: f.title.value,
            p_body: f.body.value, p_nickname: f.nick.value, p_password: f.pw.value });
          setUrl('p=' + id); showPost(id);
        }
      } catch (e) { msg.textContent = T.failed + e.message; f.querySelector('[type=submit]').disabled = false; }
    });
  }

  /* ---------- read ---------- */
  async function showPost(id) {
    root.innerHTML = `<p>${T.loading}</p>`;
    try {
      const [p] = await get(`/posts?id=eq.${encodeURIComponent(id)}&select=*`);
      if (!p) { root.innerHTML = `<p>${T.deleted}</p><p><a href="${BASE}index.html">${T.back}</a></p>`; return; }
      const cs = await get(`/comments?post_id=eq.${p.id}&select=id,body,nickname,created_at&order=created_at`);
      root.innerHTML = `<article class="cm-post">
        <p class="cm-board">${esc(BOARDS[p.board] || '')}</p>
        <h2>${esc(p.title)}</h2>
        <p class="cm-meta">${esc(p.nickname)} · ${when(p.created_at)}${p.updated_at ? ' · 수정됨' : ''}</p>
        <div class="cm-body">${esc(p.body)}</div>
        <div class="cm-bar"><a class="cm-btn" href="${BASE}index.html${p.board ? '?b=' + p.board : ''}">${T.back}</a>
          <button class="cm-btn" data-act="edit">${T.edit}</button><button class="cm-btn" data-act="delpost">${T.del}</button></div>
      </article>
      <section class="cm-comments"><h3>${T.comments} ${cs.length}</h3>
        ${cs.length ? '<ul>' + cs.map(c => `<li><p class="cm-meta">${esc(c.nickname)} · ${when(c.created_at)}
          <button class="cm-link" data-act="delc" data-id="${c.id}">${T.del}</button></p><div class="cm-body">${esc(c.body)}</div></li>`).join('') + '</ul>'
          : `<p class="hint">${T.noComments}</p>`}
        <form class="cm-form cm-cform"><label>${T.comment}<textarea name="body" rows="4" maxlength="4000" required></textarea></label>
          <div class="cm-row"><label>${T.nick}<input name="nick" maxlength="20" required></label>
          <label>${T.pw}<input name="pw" type="password" required minlength="4" autocomplete="new-password"></label></div>
          <input name="website" class="cm-hp" tabindex="-1" autocomplete="off" aria-hidden="true">
          <div class="cm-bar"><button class="cm-btn cm-btn--primary" type="submit">${T.submit}</button></div><p class="cm-msg" role="status"></p></form>
      </section>`;
      try { root.querySelector('.cm-cform [name=nick]').value = localStorage.getItem('cm-nick') || ''; } catch (e) {}
      root.querySelector('[data-act=edit]').onclick = () => form(p);
      root.querySelector('[data-act=delpost]').onclick = async () => {
        const pw = prompt(T.pwAsk); if (!pw) return;
        try { await rpc('delete_post', { p_id: p.id, p_password: pw }); location.href = BASE + 'index.html'; } catch (e) { alert(T.failed + e.message); }
      };
      root.querySelectorAll('[data-act=delc]').forEach(b => b.onclick = async () => {
        const pw = prompt(T.pwAsk); if (!pw) return;
        try { await rpc('delete_comment', { p_id: +b.dataset.id, p_password: pw }); showPost(p.id); } catch (e) { alert(T.failed + e.message); }
      });
      root.querySelector('.cm-cform').addEventListener('submit', async ev => {
        ev.preventDefault();
        const f = ev.target; if (f.website.value) return;
        f.querySelector('[type=submit]').disabled = true;
        try {
          try { localStorage.setItem('cm-nick', f.nick.value); } catch (e) {}
          await rpc('create_comment', { p_post_id: p.id, p_body: f.body.value, p_nickname: f.nick.value, p_password: f.pw.value });
          showPost(p.id);
        } catch (e) { f.querySelector('.cm-msg').textContent = T.failed + e.message; f.querySelector('[type=submit]').disabled = false; }
      });
    } catch (e) { root.innerHTML = `<p>${T.failed}${esc(e.message)}</p>`; }
  }

  root.addEventListener('click', ev => {
    const b = ev.target.closest('button[data-b], button[data-act]');
    if (!b) return;
    if (b.dataset.b !== undefined) { board = b.dataset.b; setUrl(board ? 'b=' + board : ''); showList(); }
    else if (b.dataset.act === 'new') form(null);
    else if (b.dataset.act === 'list') showList();
    else if (b.dataset.act === 'more') loadMore(false);
    else if (b.dataset.act === 'view') showPost(b.dataset.id);
  });

  // A static post page ships the post as HTML for search engines; the live view (with comments) replaces it.
  postId ? showPost(postId) : showList();
})();
