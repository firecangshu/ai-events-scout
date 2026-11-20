// 速查表筛选器 + CSV 导出：抽取 HTML 里的真实内联脚本执行，验证行为
const fs = require('fs');
const vm = require('vm');
const path = require('path');

// 路径相对本脚本定位，避免受 cwd 影响
const ROOT = path.join(__dirname, '..');
const HTML = fs.readFileSync(path.join(ROOT, 'output', 'AI赛事报名速查表_2026-11-14.html'), 'utf8');
const DATA = JSON.parse(fs.readFileSync(path.join(ROOT, 'output', 'events_data.json'), 'utf8'));

// ---------- 解析卡片（用正则逐条提取属性，避免 split 截断属性名） ----------
const cardRe = /<div class="ev"\s+data-scope="([^"]*)"\s+data-form="([^"]*)"\s+data-elig="([^"]*)"\s+data-q="([^"]*)">/g;
const rawCards = [];
let m;
while ((m = cardRe.exec(HTML)) !== null) {
  rawCards.push({ scope: m[1], form: m[2], elig: m[3], q: m[4], start: m.index });
}
// 取每张卡片的内部 HTML（到下一个 data-scope 起点或 wrap 结束）
const cards = rawCards.map((c, i) => {
  const end = i + 1 < rawCards.length ? rawCards[i + 1].start : HTML.indexOf('<div class="foot">');
  return { ...c, inner: HTML.slice(c.start, end) };
});

// ---------- 最小 DOM stub ----------
function mkEl(tag, attrs, text, sel) {
  const el = {
    tag, attrs: attrs || {}, _text: text || '', sel: sel || '', children: [], parent: null,
    _h: {}, _kids: [],
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
      toggle(c, f) { if (f === undefined) f = !this._s.has(c); f ? this._s.add(c) : this._s.delete(c); }
    },
    get className() { return Array.from(this.classList._s).join(' '); },
    set className(v) { this.classList._s = new Set(String(v).split(' ').filter(Boolean)); },
    get textContent() { return this._text; },
    set textContent(v) { this._text = v; },
    getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    dispatch(t, e) { (this._h[t] || []).forEach(f => f.call(this, e || {})); },
    querySelector(sel) { return this._kids.filter(k => k.sel === sel)[0] || null; },
    querySelectorAll(sel) { return this._kids.filter(k => k.sel === sel); },
    appendChild(c) { c.parent = this; this.children.push(c); },
    removeChild(c) { this.children = this.children.filter(x => x !== c); },
    click() { this.dispatch('click'); }
  };
  return el;
}

// 为每张卡片构造真实子节点，供脚本内 querySelector 取值
const cardEls = cards.map(c => {
  const el = mkEl('div', {
    'data-scope': c.scope, 'data-form': c.form, 'data-elig': c.elig, 'data-q': c.q
  });
  el.classList.add('ev');
  const pick = cls => {
    const re = new RegExp('class="' + cls + '(?: [^"]*)?"[^>]*>([^<]*)<');
    const mm = c.inner.match(re);
    return mm ? mm[1] : '';
  };
  const goRe = c.inner.match(/<a class="go" href="([^"]*)"/);
  const tRe = /<span class="t t-[a-z]+">([^<]*)<\/span>/g;
  const tags = []; let tm;
  while ((tm = tRe.exec(c.inner)) !== null) tags.push(tm[1]);

  el._kids.push(mkEl('span', {}, pick('num'), '.num'));
  el._kids.push(mkEl('span', {}, pick('rem'), '.rem'));
  el._kids.push(mkEl('span', {}, pick('dl'), '.dl'));
  el._kids.push(mkEl('div', {}, pick('nm'), '.nm'));
  el._kids.push(mkEl('div', {}, pick('note'), '.note'));
  tags.forEach(t => el._kids.push(mkEl('span', {}, t, '.t')));
  const goEl = mkEl('a', goRe ? { href: goRe[1] } : {}, '去报名 →', '.go');
  el._kids.push(goEl);
  return el;
});

// 筛选按钮
const btnRe = /<button class="fbtn(?: on)?" data-g="([^"]*)" data-v="([^"]*)"/g;
const btns = [];
while ((m = btnRe.exec(HTML)) !== null) {
  const b = mkEl('button', { 'data-g': m[1], 'data-v': m[2] });
  b.classList.add('fbtn');
  btns.push(b);
}
btns.forEach(b => {
  b.parentNode = { querySelectorAll: () => btns.filter(x => x.getAttribute('data-g') === b.getAttribute('data-g')) };
});

const fcEl = mkEl('span', {}, '24');
const fqEl = mkEl('input', {});
const expEl = mkEl('button', {}, '导出 CSV');
const expXlsEl = mkEl('button', {}, '导出 Excel');

let capturedBlob = null, capturedName = null;
class FakeBlob {
  constructor(parts, opts) { this.parts = parts; this.opts = opts; }
  text() { return Promise.resolve(this.parts.join('')); }
}

const document = {
  getElementById(id) {
    if (id === 'fc') return fcEl;
    if (id === 'fq') return fqEl;
    if (id === 'fexp') return expEl;
    if (id === 'fexp2') return expXlsEl;
    return null;
  },
  querySelectorAll(sel) {
    if (sel === '.fbtn') return btns;
    if (sel === '#rows .ev') return cardEls;
    return [];
  },
  querySelector() { return null; },
  createElement(tag) {
    const e = mkEl(tag);
    if (tag === 'a') e.click = function () { capturedName = this.download; };
    return e;
  },
  body: { appendChild() {}, removeChild() {} }
};

const URLstub = {
  createObjectURL(blob) { capturedBlob = blob; return 'blob:stub'; },
  revokeObjectURL() {}
};

const sandbox = { document, URL: URLstub, Blob: FakeBlob, setTimeout, clearTimeout, console };
sandbox.window = sandbox;
vm.createContext(sandbox);

const scriptMatch = HTML.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) { console.error('未找到内联脚本'); process.exit(1); }
vm.runInContext(scriptMatch[1], sandbox, { filename: 'signup_table_inline.js' });

let fail = 0;
function chk(name, got, exp) {
  const ok = String(got) === String(exp);
  if (!ok) fail++;
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + '  实际=' + got + ' 期望=' + exp);
}
function clickBtn(g, v) {
  for (const b of btns) {
    if (b.getAttribute('data-g') === g && b.getAttribute('data-v') === v) { b.dispatch('click'); return true; }
  }
  return false;
}
const vis = () => cardEls.filter(e => !e.classList.contains('hide')).length;

setTimeout(() => {
  chk('初始显示全部', vis(), 24);
  chk('计数显示', fcEl.textContent, 24);

  clickBtn('elig', '仅学生'); chk('人群=仅学生', vis(), 8);
  clickBtn('scope', '国内'); chk('仅学生+国内', vis(), 5);
  clickBtn('scope', '国外'); chk('仅学生+国外', vis(), 3);
  clickBtn('scope', 'all'); chk('仅学生+不限地区', vis(), 8);
  clickBtn('elig', 'all'); chk('重置人群', vis(), 24);

  clickBtn('form', '混合'); chk('形式=混合', vis(), 9);
  clickBtn('form', '线上'); chk('形式=线上', vis(), 15);
  clickBtn('form', '线下'); chk('形式=线下', vis(), 0);
  clickBtn('form', 'all'); chk('重置形式', vis(), 24);

  clickBtn('scope', '国外'); chk('地区=国外', vis(), 7);
  clickBtn('scope', '不限'); chk('地区=不限', vis(), 2);
  clickBtn('scope', '国内'); chk('地区=国内', vis(), 15);
  clickBtn('scope', 'all'); chk('重置地区', vis(), 24);

  // 导出 CSV（先单独捕获，避免 Excel 导出覆盖）
  expEl.dispatch('click');
  const csvBlob = capturedBlob;
  const csvName = capturedName;
  chk('导出触发 Blob', csvBlob !== null, 'true');
  chk('导出文件名', csvName, 'AI赛事清单_筛选结果_2026-11-14.csv');

  // 导出 Excel（SpreadsheetML）
  capturedBlob = null; capturedName = null;
  expXlsEl.dispatch('click');
  const xlsBlob = capturedBlob;
  const xlsName = capturedName;
  chk('Excel 导出触发 Blob', xlsBlob !== null, 'true');
  chk('Excel 导出文件名', xlsName, 'AI赛事清单_筛选结果_2026-11-14.xls');

  if (csvBlob && xlsBlob) {
    Promise.all([csvBlob.text(), xlsBlob.text()]).then(res => {
      const csvTxt = res[0], xlsTxt = res[1];
      const lines = csvTxt.split('\r\n');
      chk('CSV 含 BOM', csvTxt.charCodeAt(0) === 0xFEFF, 'true');
      chk('CSV 行数(含表头)', lines.length, 25);
      chk('CSV 表头含关键列', lines[0].indexOf('赛事名称') !== -1 && lines[0].indexOf('报名入口') !== -1, 'true');
      chk('CSV 首行含赛事名', lines[1].indexOf('中国电科') !== -1, 'true');
      chk('CSV 首行含链接', lines[1].indexOf('http') !== -1, 'true');
      chk('CSV 行数与赛事数一致', lines.length - 1, DATA.events.length);

      // Excel 导出：SpreadsheetML 2003
      chk('Excel 含 SpreadsheetML 头', xlsTxt.indexOf('<?mso-application progid="Excel.Sheet"?>') !== -1, 'true');
      chk('Excel 含工作表名', xlsTxt.indexOf('ss:Name="AI赛事清单"') !== -1, 'true');
      const xlsRows = (xlsTxt.match(/<Row>/g) || []).length;
      chk('Excel 行数(含表头)', xlsRows, 25);
      chk('Excel 含赛事名', xlsTxt.indexOf('中国电科') !== -1, 'true');
      chk('Excel 含链接', xlsTxt.indexOf('https://wangxinbei.taiji.com.cn/') !== -1, 'true');
      chk('Excel 含筛选后条数校验', (xlsTxt.match(/<Row>/g) || []).length - 1, DATA.events.length);

      console.log('---');
      console.log('CSV 首行:', lines[1].slice(0, 160));
      console.log('Excel 片段:', xlsTxt.slice(xlsTxt.indexOf('<Table>'), xlsTxt.indexOf('<Table>') + 200));
      console.log('---');
      console.log(fail === 0 ? '全部通过（0 失败）' : fail + ' 项失败');
      process.exit(fail === 0 ? 0 : 1);
    });
  }
}, 400);
