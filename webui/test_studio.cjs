const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');

// Exercise the page's own handlers offline; no browser or remote API calls.
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, 'studio.html'), 'utf8');
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const elements = new Map();
const documentListeners = new Map();
const windowListeners = new Map();
function classes(value = '') {
  const values = new Set(value.split(/\s+/).filter(Boolean));
  return {
    add: x => values.add(x), remove: x => values.delete(x), contains: x => values.has(x),
    toggle(x, force = !values.has(x)) { force ? values.add(x) : values.delete(x); return force; },
  };
}
for (const tag of html.matchAll(/<[^>]+\bid="([^"]+)"[^>]*>/g)) {
  const attrs = Object.fromEntries([...tag[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
  const listeners = new Map();
  const style = Object.fromEntries((attrs.style || '').split(';').filter(Boolean).map(pair => pair.split(':')));
  elements.set(attrs.id, {
    classList: classes(attrs.class), style, listeners, disabled: /\bdisabled\b/.test(tag[0]),
    textContent: '', innerHTML: '', offsetWidth: 1000,
    setAttribute: (key, value) => { attrs[key] = value; },
    getAttribute: key => attrs[key],
    addEventListener: (key, fn) => listeners.set(key, fn),
    getBoundingClientRect: () => ({ left: 0 }),
  });
}
const get = id => elements.get(id);
function model(value) {
  return { value, disposed: false, getValue() { return this.value; }, setValue(v) { this.value = v; }, dispose() { this.disposed = true; } };
}
function editor(value = '') {
  return {
    model: model(value), disposed: false,
    getModel() { return this.model; }, getValue() { return this.model.getValue(); },
    setValue(value) { this.model.setValue(value); },
    layout() {}, updateOptions() {}, revealLineInCenter(line) { this.line = line; }, setPosition() {}, focus() {},
    dispose() { this.disposed = true; },
  };
}
const monaco = { editor: {
  createModel: model,
  createDiffEditor: () => ({
    modified: editor(), disposed: false,
    setModel(models) { this.models = models; this.modified.model = models.modified; },
    getModifiedEditor() { return this.modified; },
    layout() {}, dispose() { this.disposed = true; },
  }),
} };
const amdRequire = () => {};
let loaderConfig;
amdRequire.config = config => { loaderConfig = config; };
const context = vm.createContext({
  URLSearchParams, URL, Blob, require: amdRequire, monaco,
  location: { search: '' },
  window: { addEventListener: (key, fn) => windowListeners.set(key, fn) },
  document: {
    getElementById: get,
    addEventListener: (key, fn) => documentListeners.set(key, fn),
    removeEventListener: key => documentListeners.delete(key),
  },
  ResizeObserver: class { observe() {} },
  fetch: async () => ({ ok: true, json: async () => ({ files: [], host: 'offline', mem: '' }) }),
  setTimeout: fn => fn(), alert: message => { throw new Error(message); },
});
const run = source => vm.runInContext(source, context);
new vm.Script(script);
run(script);
windowListeners.get('load')();

(async () => {
  run("showCenter('diff'); gotoLine(3);");
  assert.equal(run('diffShown'), false, 'uninitialized diff must not become active');
  assert.equal(get('duo').classList.contains('hide'), false);
  context.testEditor = editor('original');
  run('editor = testEditor; gotoLine(3);');
  assert.equal(context.testEditor.line, 3);

  context.result = { fixed_content: 'fixed', problems_after: [], compile_before: { ok: true }, compile_after: { ok: true } };
  run("preFix = editor.getValue(); applyResult(result); showCenter('diff'); gotoLine(7);");
  assert.equal(run('diffShown'), true, 'successful repair must enable diff');
  assert.equal(run('currentContent()'), 'fixed');
  assert.equal(run('diffEditor.getModifiedEditor().line'), 7);
  assert.equal(get('duo').classList.contains('hide'), true);
  assert.equal(get('diff').classList.contains('hide'), false);
  assert.equal(get('tab-diff').getAttribute('aria-disabled'), 'false');

  const oldDiff = run('diffEditor');
  const oldOriginal = run('origModel');
  const oldModified = run('modModel');
  let finishFile;
  context.fileRequest = () => new Promise(resolve => { finishFile = resolve; });
  run('j = fileRequest; loadFiles = async () => {}; analyze = async () => {}; compilePreview = async () => {};');
  const loading = run("loadFile('other.tex')");
  assert.equal(oldDiff.disposed && oldOriginal.disposed && oldModified.disposed, true);
  assert.equal(run('diffShown'), false, 'file switch leaves diff immediately');
  assert.equal(run('diffEditor === null && origModel === null && modModel === null'), true);
  assert.equal(get('btnDiff').disabled, true);
  assert.equal(get('tab-diff').getAttribute('aria-disabled'), 'true');
  run("showCenter('diff'); gotoLine(5);");
  assert.equal(run('diffShown'), false);
  finishFile({ content: 'other file' });
  await loading;
  assert.equal(context.testEditor.getValue(), 'other file');
  run("preFix = editor.getValue(); applyResult(result); showCenter('diff');");
  assert.equal(run('diffShown'), true, 'new file can get its own valid diff');

  let downloaded;
  context.captureDownload = (name, blob) => { downloaded = {name, blob}; };
  context.traceResult = { ...context.result, model: null, model_calls: 0, skill_mode: 'on',
    edits: [], elapsed_seconds: 1, trace: [{action: 'CANDIDATE_REJECTED', candidate: 'x+'}] };
  run('download = captureDownload; lastResult = traceResult; $("btnReport").onclick();');
  const report = await downloaded.blob.text();
  assert.match(report, /实际模型请求：0；模型：本次未调用/);
  assert.match(report, /CANDIDATE_REJECTED/);
  assert.match(report, /不表示人工已经采用/);

  get('sepE').listeners.get('mousedown')({ target: { closest: () => get('sepBtnE') }, preventDefault() { throw new Error('button started drag'); } });
  assert.equal(documentListeners.has('mousemove'), false);
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), true);
  assert.equal(get('previewPane').style.overflow, 'hidden');
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), false);
  assert.equal(get('previewPane').style.width, '38%');
  get('sepBtnE').onclick();
  get('sepE').listeners.get('mousedown')({ preventDefault() {} });
  documentListeners.get('mousemove')({ clientX: 600 });
  documentListeners.get('mouseup')();
  assert.equal(get('previewPane').classList.contains('collapsed'), false);
  assert.equal(get('previewPane').style.overflow, 'auto');
  assert.equal(get('previewPane').style.width, '40%');

  assert.match(html, /<script src="\/static\/monaco\/0\.52\.2\/min\/vs\/loader\.js"><\/script>/);
  assert.equal(loaderConfig.paths.vs, '/static/monaco/0.52.2/min/vs');
  assert.doesNotMatch(script, /MonacoEnvironment|getWorkerUrl|cdn\.jsdelivr/);
  assert.match(html, /\.hide\s*\{\s*display:none\s*!important;/);
  assert.match(html, /#previewPane\.collapsed\s*\{[^}]*padding:0\s*!important;/);
  console.log('PASS: same-origin pinned Monaco configuration; JS syntax; unavailable/available diff navigation; problem navigation; file-switch disposal/reset; new-file diff; preview collapse/reopen/drag; critical CSS rules.');
})().catch(error => { console.error(error); process.exitCode = 1; });
