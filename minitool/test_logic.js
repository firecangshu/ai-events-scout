// 离线逻辑测试：用最小 DOM stub 加载真实 main.js / data.js，
// 验证首屏渲染、关键词搜索、四组筛选与组合行为。
const fs = require('fs');
const vm = require('vm');

const BASE = 'e:/44.AI赛事百晓生/minitool/dist/assets';

function makeEl(tag) {
  const el = {
    tag: tag,
    _html: '',
    children: [],
    parent: null,
    _handlers: {},
    value: '',
    hidden: false,
    _text: '',
    style: {},
    className: '',
    get textContent() { return this._text; },
    set textContent(v) {
      // 真实 DOM：赋空字符串会移除全部子节点
      this._text = v;
      if (v === '') {
        this.children.forEach(function (c) { c.parent = null; });
        this.children = [];
        this._html = '';
      }
    },
    get innerHTML() { return this._html; },
    set innerHTML(v) {
      this._html = v;
      this.children = [];
      const n = (String(v).match(/<article/g) || []).length;
      for (let i = 0; i < n; i++) {
        const c = makeEl('article');
        c.parent = this;
        this.children.push(c);
      }
    },
    get firstChild() { return this.children.length ? this.children[0] : null; },
    appendChild(c) {
      if (c.parent) {
        c.parent.children = c.parent.children.filter(function (x) { return x !== c; });
      }
      c.parent = this;
      this.children.push(c);
    },
    addEventListener(t, fn) {
      (this._handlers[t] = this._handlers[t] || []).push(fn);
    },
    dispatch(t, ev) {
      (this._handlers[t] || []).forEach(function (fn) { fn(ev || {}); });
    },
    focus() {}
  };
  return el;
}

const byIdMap = {};
const document = {
  readyState: 'complete',
  getElementById: function (id) {
    if (!byIdMap[id]) byIdMap[id] = makeEl('div');
    return byIdMap[id];
  },
  createElement: function (tag) { return makeEl(tag); },
  addEventListener: function () {}
};

const sandbox = { document: document, setTimeout: setTimeout, clearTimeout: clearTimeout, console: console };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(BASE + '/data.js', 'utf8'), sandbox, { filename: 'data.js' });
vm.runInContext(fs.readFileSync(BASE + '/main.js', 'utf8'), sandbox, { filename: 'main.js' });

const DATA = sandbox.window.EVENTS_DATA;
const list = document.getElementById('list');
const input = document.getElementById('searchInput');

let failures = 0;
function check(name, actual, expected) {
  const ok = actual === expected;
  if (!ok) failures++;
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + '  实际=' + actual + ' 期望=' + expected);
}

function countCards() { return list.children.length; }
function chipByText(containerId, text) {
  const box = document.getElementById(containerId);
  for (let i = 0; i < box.children.length; i++) {
    if (box.children[i].textContent === text) return box.children[i];
  }
  return null;
}
function fireInput(value) {
  input.value = value;
  input.dispatch('input');
}
// 搜索有 150ms 防抖，断言前必须等待其触发
function fireInputAsync(value) {
  fireInput(value);
  return new Promise(function (resolve) { setTimeout(resolve, 220); });
}
function keywordCount(kw) {
  return DATA.events.filter(function (e) {
    return [e.name, e.eligibility, e.note, e.deadline, e.scope, e.form]
      .join(' ').toLowerCase().indexOf(kw.toLowerCase()) !== -1;
  }).length;
}
function remainDays(deadline) {
  const m = /\d{4}-\d{2}-\d{2}/.exec(deadline || '');
  if (!m) return null;
  const p = m[0].split('-');
  const dl = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  // 与 main.js 保持一致：按运行时当天计算（非快照日期）
  const n = new Date();
  const td = new Date(n.getFullYear(), n.getMonth(), n.getDate());
  return Math.round((dl - td) / 86400000);
}

// 1. 首屏渲染全部赛事
check('首屏渲染赛事数 = 数据条数', countCards(), DATA.events.length);

// 2. 关键词搜索（等待防抖触发）
const sample = DATA.events[0].name.slice(0, 3);

(async function run() {
  await fireInputAsync(sample);
  check('关键词「' + sample + '」过滤结果', countCards(), keywordCount(sample));

  // 3. 清除搜索后恢复全量
  await fireInputAsync('');
  check('清空关键词后恢复全量', countCards(), DATA.events.length);

  // 4. 地区筛选
  ['国内', '国外', '不限'].forEach(function (scope) {
    chipByText('chipsScope', scope).dispatch('click');
    const expect = DATA.events.filter(function (e) {
      return scope === '不限' || e.scope === scope;
    }).length;
    check('地区=' + scope + ' 筛选结果', countCards(), expect);
  });
  chipByText('chipsScope', '不限').dispatch('click');

  // 5. 形式筛选
  ['线上', '线下', '混合', '全部'].forEach(function (form) {
    chipByText('chipsForm', form).dispatch('click');
    const expect = DATA.events.filter(function (e) {
      if (form === '全部') return true;
      return String(e.form).indexOf(form) === 0;
    }).length;
    check('形式=' + form + ' 筛选结果', countCards(), expect);
  });
  chipByText('chipsForm', '全部').dispatch('click');

  // 6. 人群筛选
  chipByText('chipsElig', '所有人可报').dispatch('click');
  check('人群=所有人可报 筛选结果', countCards(),
    DATA.events.filter(function (e) { return String(e.eligibility).indexOf('所有人可报') !== -1; }).length);
  chipByText('chipsElig', '全部').dispatch('click');

  // 6. 区域筛选（多标签：命中任一即通过）
  ['大湾区', '长三角', '华南', '中国台湾', '全国'].forEach(function (rg) {
    chipByText('chipsRegion', rg).dispatch('click');
    const expectRg = DATA.events.filter(function (e) {
      return Array.isArray(e.regions) && e.regions.indexOf(rg) !== -1;
    }).length;
    check('区域=' + rg + ' 筛选结果', countCards(), expectRg);
  });
  chipByText('chipsRegion', '全部').dispatch('click');

  // 7. 状态筛选
  chipByText('chipsUrgency', '将截止').dispatch('click');
  check('状态=将截止 筛选结果', countCards(),
    DATA.events.filter(function (e) { const d = remainDays(e.deadline); return d !== null && d <= 7; }).length);
  chipByText('chipsUrgency', '全部').dispatch('click');

  // 8. 组合筛选：地区=国内 + 关键词
  chipByText('chipsScope', '国内').dispatch('click');
  await fireInputAsync('赛');
  check('地区=国内 + 关键词「赛」组合结果', countCards(),
    DATA.events.filter(function (e) {
      return e.scope === '国内' &&
        [e.name, e.eligibility, e.note, e.deadline, e.scope, e.form]
          .join(' ').toLowerCase().indexOf('赛') !== -1;
    }).length);

  // 9. 重置后回到全量
  await fireInputAsync('');
  chipByText('chipsScope', '不限').dispatch('click');
  check('全部重置后恢复全量', countCards(), DATA.events.length);

  // 10. 有结果时 empty 提示隐藏
  check('有结果时 empty 提示隐藏', document.getElementById('empty').hidden, true);

  // 11. 无匹配时 empty 提示显示
  await fireInputAsync('不存在的赛事关键词xyz');
  check('无匹配时卡片数归零', countCards(), 0);
  check('无匹配时 empty 提示显示', document.getElementById('empty').hidden, false);

  console.log('--------------------------------------------------');
  console.log(failures === 0 ? '全部通过（0 失败）' : failures + ' 项失败');
  process.exit(failures === 0 ? 0 : 1);
})();
