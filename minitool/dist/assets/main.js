// AI赛事百晓生 · 小工具主逻辑（ES2017 / Chrome 61 基线）
(function () {
  'use strict';

  var DATA = window.EVENTS_DATA || { events: [], dropped: [], snap: '', today: '' };

  // 倒计时基准 = 用户打开当天的本地日期（非打包快照日期），快照日期仅作数据新鲜度提示
  function runtimeToday() {
    var n = new Date();
    function p(x) { return (x < 10 ? '0' : '') + x; }
    return n.getFullYear() + '-' + p(n.getMonth() + 1) + '-' + p(n.getDate());
  }
  var TODAY = runtimeToday();

  function daysFromSnapshot() {
    if (!DATA.snap) return null;
    return remainDays(DATA.snap, TODAY);
  }

  var STATE = { scope: '不限', region: '全部', form: '全部', elig: '全部', urgency: '全部', keyword: '' };

  var SCOPE_OPTIONS = ['不限', '国内', '国外'];
  var REGION_OPTIONS = ['全部', '大湾区', '珠三角', '长三角', '华北', '华东', '华南', '华中', '西南', '东北', '中国台湾', '全国', '国外'];
  var FORM_OPTIONS = ['全部', '线上', '线下', '混合'];
  var ELIG_OPTIONS = ['全部', '所有人可报', '社会组可报', '企业·团队可报', '纯学生限定'];
  var URGENCY_OPTIONS = ['全部', '将截止', '2周+'];

  function byId(id) { return document.getElementById(id); }

  function parseDeadline(str) {
    var m = /\d{4}-\d{2}-\d{2}/.exec(str || '');
    return m ? m[0] : '';
  }

  function remainDays(deadline, today) {
    var d = parseDeadline(deadline);
    if (!d) return null;
    var parts = d.split('-');
    var dl = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    var tp = today.split('-');
    var td = new Date(Number(tp[0]), Number(tp[1]) - 1, Number(tp[2]));
    return Math.round((dl - td) / 86400000);
  }

  // “形式”可能带补充说明（如“混合（线上初赛·线下决赛…）”），取首个关键词归类
  function formKey(form) {
    var f = form || '';
    if (f.indexOf('混合') === 0) return '混合';
    if (f.indexOf('线上') === 0) return '线上';
    if (f.indexOf('线下') === 0) return '线下';
    return '线上';
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function matchKeyword(el) {
    var kw = STATE.keyword;
    if (!kw) return true;
    var hay = [el.name, el.eligibility, el.note, el.deadline, el.scope, el.form]
      .join(' ').toLowerCase();
    return hay.indexOf(kw.toLowerCase()) !== -1;
  }

  function match(el) {
    if (!matchKeyword(el)) return false;
    if (STATE.scope !== '不限' && el.scope !== STATE.scope) return false;
    if (STATE.region !== '全部') {
      // 区域为多标签，命中任一即通过
      var regs = Array.isArray(el.regions) ? el.regions : [];
      if (regs.indexOf(STATE.region) === -1) return false;
    }
    if (STATE.form !== '全部' && formKey(el.form) !== STATE.form) return false;
    if (STATE.elig !== '全部' && (el.eligibility || '').indexOf(STATE.elig) === -1) return false;
    if (STATE.urgency !== '全部') {
      var days = remainDays(el.deadline, TODAY);
      if (days === null) return false;
      if (STATE.urgency === '将截止' && days > 7) return false;
      if (STATE.urgency === '2周+' && days <= 7) return false;
    }
    return true;
  }

  function chipRow(containerId, options, key) {
    var box = byId(containerId);
    box.textContent = '';
    options.forEach(function (opt) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'chip touchable' + (STATE[key] === opt ? ' chip-on' : '');
      b.textContent = opt;
      b.addEventListener('click', function () {
        STATE[key] = opt;
        renderChips();
        renderList();
      });
      box.appendChild(b);
    });
  }

  function renderChips() {
    chipRow('chipsScope', SCOPE_OPTIONS, 'scope');
    chipRow('chipsRegion', REGION_OPTIONS, 'region');
    chipRow('chipsForm', FORM_OPTIONS, 'form');
    chipRow('chipsElig', ELIG_OPTIONS, 'elig');
    chipRow('chipsUrgency', URGENCY_OPTIONS, 'urgency');
  }

  // 人群标签短桶：完整资格限制（如「需依托国内法人单位」「18+」）只留在表格产物，
  // 小工具内只给一目了然的人群归属，避免冗长文本与站外信息。
  function eligBucket(eligibility) {
    var e = String(eligibility || '');
    if (e.indexOf('纯学生限定') === 0) return '仅学生';
    if (e.indexOf('社会组可报') === 0) return '社会组可报';
    if (e.indexOf('企业·团队可报') === 0) return '企业/团队';
    if (e.indexOf('仅个人可报') === 0) return '仅个人';
    return '不限人群';
  }

  function cardHtml(el, idx) {
    var days = remainDays(el.deadline, TODAY);
    var remainCls = 'rem-unknown';
    var remain = '';
    if (days !== null) {
      if (days < 0) {
        remainCls = 'rem-over';
        remain = '已截止';
      } else if (days === 0) {
        remainCls = 'rem-urgent';
        remain = '今天截止';
      } else if (days <= 3) {
        remainCls = 'rem-urgent';
        remain = '还剩 ' + days + ' 天';
      } else if (days <= 7) {
        remainCls = 'rem-soon';
        remain = '还剩 ' + days + ' 天';
      } else {
        remainCls = 'rem-normal';
        remain = '还剩 ' + days + ' 天';
      }
    } else {
      remain = '赛期中';
    }
    var dl = parseDeadline(el.deadline) || el.deadline || '';
    var tags =
      '<span class="tag tag-scope">' + escapeHtml(el.scope) + '</span>' +
      '<span class="tag tag-form">' + escapeHtml(formKey(el.form)) + '</span>' +
      '<span class="tag tag-elig">' + escapeHtml(eligBucket(el.eligibility)) + '</span>' +
      '<span class="tag tag-region">' + escapeHtml((el.regions || []).join('·') || el.scope) + '</span>' +
      (el.chip ? '<span class="tag tag-chip">' + escapeHtml(el.chip) + '</span>' : '');
    return '<article class="card">' +
      '<div class="card-top">' +
        '<div class="card-idx">' + idx + '</div>' +
        '<div class="card-main">' +
          '<h2 class="card-name">' + escapeHtml(el.name) + '</h2>' +
          '<div class="card-meta">' + tags + '</div>' +
          '<p class="card-deadline">' +
            '<span class="rem ' + remainCls + '">' + escapeHtml(remain) + '</span>' +
            '<span class="dl">截止 ' + escapeHtml(dl) + '</span>' +
          '</p>' +
          (el.note ? '<p class="card-note">' + escapeHtml(el.note) + '</p>' : '') +
        '</div>' +
      '</div>' +
    '</article>';
  }

  function renderList() {
    var list = byId('list');
    var shown = DATA.events.filter(match);
    var html = '';
    for (var i = 0; i < shown.length; i++) {
      html += cardHtml(shown[i], i + 1);
    }
    list.textContent = '';
    if (html) {
      var wrap = document.createElement('div');
      wrap.innerHTML = html; // 内容均经 escapeHtml 转义
      while (wrap.firstChild) list.appendChild(wrap.firstChild);
    }
    byId('empty').hidden = shown.length > 0;
  }

  function renderHeader() {
    var events = DATA.events;
    var online = events.filter(function (e) { return formKey(e.form) === '线上'; }).length;
    var domestic = events.filter(function (e) { return e.scope === '国内'; }).length;
    var age = daysFromSnapshot();
    var hero = '今天 ' + TODAY + ' · 共 ' + events.length + ' 个报名进行中';
    if (age !== null && age > 0) {
      hero += ' · 数据更新于 ' + DATA.snap;
      if (age >= 3) {
        hero += '（' + age + ' 天前，部分赛事可能已截止，报名前请以官方页面为准）';
      }
    }
    byId('heroSub').textContent = hero;
    byId('heroStats').innerHTML =
      '<span class="stat-pill">线上 ' + online + '</span>' +
      '<span class="stat-pill">国内赛 ' + domestic + '</span>';
    byId('footSnap').textContent = '数据快照 ' + DATA.snap + ' · 倒计时按打开当天计算 · 另有 ' +
      (DATA.droppedCount || 0) + ' 项因口径不合未收录';
  }

  function bindSearch() {
    var input = byId('searchInput');
    var clear = byId('searchClear');
    if (!input) return;

    var timer = null;
    input.addEventListener('input', function () {
      var value = input.value;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        STATE.keyword = value.replace(/^\s+|\s+$/g, '');
        if (clear) clear.hidden = !STATE.keyword;
        renderList();
      }, 150);
    });

    if (clear) {
      clear.addEventListener('click', function () {
        input.value = '';
        STATE.keyword = '';
        clear.hidden = true;
        renderList();
        input.focus();
      });
    }
  }

  function init() {
    renderHeader();
    renderChips();
    bindSearch();
    renderList();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
