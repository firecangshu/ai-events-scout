// 小工具构建脚本：赛事数据 → 包内 data.js → 可上传 zip
// 用法：node build.js [--data <events_data.json>] [--out <目录>] [--zip <zip路径>]
//
// 关键特性：
//  1. 正斜杠路径写入（Windows Compress-Archive 会写反斜杠，redapp upload 会拒绝）
//  2. 固定时间戳，产物可复现 —— 同样的输入必得同样的 md5，便于核对线上版本
//  3. 只更新 data.js，其余文件（index.html / main.js / style.css）不动
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = __dirname;
const DIST = path.join(ROOT, 'dist');

function parseArgs(argv) {
  const out = { data: path.join(ROOT, '..', 'output', 'events_data.json') };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--data') out.data = argv[++i];
    else if (a === '--out') out.dist = argv[++i];
    else if (a === '--zip') out.zip = argv[++i];
  }
  out.dist = out.dist || DIST;
  out.zip = out.zip || path.join(ROOT, 'AI赛事百晓生_minitool.zip');
  return out;
}

// 只保留小工具展示所需的字段，避免把大字段/长描述打进包
function pickEvent(e) {
  return {
    name: e.name || '',
    scope: e.scope || '',
    form: e.form || '',
    eligibility: e.eligibility || '',
    deadline: e.deadline || '',
    note: e.note || '',
    chip: e.chip || '',
    regions: Array.isArray(e.regions) ? e.regions : []
  };
}

function buildDataJs(raw) {
  const payload = {
    snap: raw.snap || '',
    today: raw.today || raw.snap || '',
    events: (raw.events || []).map(pickEvent),
    // 只带剔除条数，不带剔除原因原文（原因含「报名入口」等表述，不进小红书侧包体）
    droppedCount: (raw.dropped || []).length
  };
  return '// 静态数据：由 events_data.json 生成，快照 ' + payload.snap +
    '\nwindow.EVENTS_DATA=' + JSON.stringify(payload) + ';\n';
}

// 固定时间戳 → 同样的输入产出同样的 md5
function buildZip(distDir, zipPath) {
  const files = [];
  (function walk(dir, prefix) {
    fs.readdirSync(dir).forEach(function (name) {
      if (name.startsWith('._') || name === '.DS_Store') return;
      const full = path.join(dir, name);
      const rel = prefix ? prefix + '/' + name : name;
      if (fs.statSync(full).isDirectory()) walk(full, rel);
      else files.push(rel);
    });
  })(distDir, '');

  const py = [
    'import os,sys,zipfile',
    'dist, out = sys.argv[1], sys.argv[2]',
    'if os.path.exists(out): os.remove(out)',
    'z = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED)',
    'for dp, dn, fn in os.walk(dist):',
    '    dn[:] = [d for d in dn if d not in ("__MACOSX", ".git", "node_modules")]',
    '    for f in sorted(fn):',
    '        if f.startswith("._") or f == ".DS_Store" or f.endswith(".map"): continue',
    '        rel = os.path.relpath(os.path.join(dp, f), dist).replace(os.sep, "/")',
    '        zi = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))',
    '        zi.compress_type = zipfile.ZIP_DEFLATED',
    '        zi.external_attr = 0o644 << 16',
    '        z.writestr(zi, open(os.path.join(dp, f), "rb").read())',
    'z.close()'
  ].join('\n');

  execFileSync('python3', ['-c', py, distDir, zipPath], { stdio: 'inherit' });
  return files;
}

function md5(file) {
  const crypto = require('crypto');
  return crypto.createHash('md5').update(fs.readFileSync(file)).digest('hex');
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!fs.existsSync(args.data)) {
    console.error('找不到数据文件：' + args.data);
    process.exit(1);
  }
  const raw = JSON.parse(fs.readFileSync(args.data, 'utf8'));

  const dataJs = buildDataJs(raw);
  fs.writeFileSync(path.join(args.dist, 'assets', 'data.js'), dataJs);

  const files = buildZip(args.dist, args.zip);

  console.log('数据文件:', args.data);
  console.log('赛事条数:', (raw.events || []).length,
    '| 带链接:', (raw.events || []).filter(function (e) { return e.link; }).length);
  console.log('包内文件:', files.join(', '));
  console.log('zip 路径:', args.zip);
  console.log('zip md5 :', md5(args.zip));
  console.log('');
  console.log('下一步：');
  console.log('  redapp upload --file "' + args.zip + '" --type pkg --dry-run --agent');
  console.log('  （预览需重新生成二维码并由用户扫码确认后，才能 submit 送审）');
}

main();
