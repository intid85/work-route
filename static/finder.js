/* Home-page finder: type a job, see which countries offer a route to permanent residence. */
(function () {
  var box = document.querySelector('[data-finder]');
  if (!box) return;
  var ko = document.documentElement.lang === 'ko';
  var data = JSON.parse(box.querySelector('.finder-data').textContent);
  var q = box.querySelector('input'), out = box.querySelector('.finder-out');
  var V = ko ? { yes: '가능', maybe: '조건부', hard: '어려움' } : { yes: 'Open', maybe: 'Conditional', hard: 'Hard' };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function norm(s) { return String(s || '').toLowerCase().replace(/\s+/g, ''); }
  function match(term) {
    var t = norm(term); if (!t) return [];
    var exact = data.entries.filter(function (e) { return norm(e.ko) === t || norm(e.en) === t; });
    if (exact.length) return exact;
    return data.entries.filter(function (e) {
      return (norm(e.ko) + '|' + norm(e.en) + '|' + norm(e.alias)).indexOf(t) !== -1 ||
        e.alias.toLowerCase().split(/\s+/).some(function (a) { return a && (/[^\x00-\x7f]/.test(a) ? a.length >= 2 : a.length >= 4) && t.indexOf(a.toLowerCase()) !== -1; });
    });
  }
  function card(e) {
    var counts = { yes: 0, maybe: 0, hard: 0 };
    e.countries.forEach(function (r) { counts[r.v]++; });
    return '<section class="finder-res"><h2>' + esc(ko ? e.ko : e.en) +
      (ko ? ' <span>· 가능 ' + counts.yes + '개국, 조건부 ' + counts.maybe + '개국</span>' : ' <span>· ' + counts.yes + ' open, ' + counts.maybe + ' conditional</span>') +
      '</h2><ul class="finder-grid">' + e.countries.map(function (r) {
        var name = data.names[r.c][ko ? 0 : 1];
        return '<li class="fv-' + r.v + '"><a href="' + esc(r.href) + '"><span class="fv-head"><b>' + esc(name) + '</b><span class="fv-badge">' + V[r.v] + '</span></span>' +
          '<span class="fv-route">' + esc(ko ? r.ko : r.en) + '</span>' + (r[ko ? 'ev_ko' : 'ev_en'] ? '<span class="fv-ev">' + esc(ko ? r.ev_ko : r.ev_en) + '</span>' : '') + '</a></li>';
      }).join('') + '</ul></section>';
  }
  function run(entries) {
    if (!entries.length) {
      out.innerHTML = '<p class="hint">' + (ko ? '아직 없는 직업입니다. 아래 목록에서 비슷한 직업을 골라 보세요.' : 'No match yet. Pick a similar job from the suggestions.') + '</p>';
      return;
    }
    out.innerHTML = entries.slice(0, 3).map(card).join('') +
      '<p class="hint">' + (ko ? '정부 공개 데이터와 2026년 10월 비자 규정 기준입니다. 결정 전에 각국 이민청에서 확인하세요.' : 'Based on government data and visa rules as of October 2026. Confirm with each immigration authority.') + '</p>';
  }
  box.addEventListener('submit', function (ev) { ev.preventDefault(); run(match(q.value)); });
  box.querySelectorAll('[data-pick]').forEach(function (b) {
    b.addEventListener('click', function () {
      var e = data.entries.filter(function (x) { return x.id === b.dataset.pick; });
      q.value = ko ? e[0].ko : e[0].en; run(e);
    });
  });
  q.addEventListener('change', function () { var m = match(q.value); if (m.length === 1) run(m); });
})();
