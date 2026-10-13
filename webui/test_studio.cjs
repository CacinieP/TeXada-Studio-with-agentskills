const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const {webcrypto, createHash} = require('node:crypto');
const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');

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
  return { value, version: 1, disposed: false, getValue() { return this.value; },
    getVersionId() { return this.version; }, setValue(v) { this.value = v; this.version++; },
    getOffsetAt(p) { return this.value.split('\n').slice(0, p.lineNumber - 1).reduce((n, s) => n + s.length + 1, 0) + p.column - 1; },
    dispose() { this.disposed = true; } };
}
function editor(value = '') {
  return {
    model: model(value), disposed: false,
    getModel() { return this.model; }, getValue() { return this.model.getValue(); },
    setValue(value) { this.model.setValue(value); },
    getPosition() { return {lineNumber:1,column:(this.cursor || 0)+1}; },
    getSelection() { const p=this.getPosition(); return {getStartPosition:()=>p,getEndPosition:()=>p}; },
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
  URLSearchParams, URL, Blob, TextEncoder, crypto:webcrypto, require: amdRequire, monaco,
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

const testWatchdog = setTimeout(() => { console.error("Studio behavior test did not complete"); process.exitCode = 1; }, 10000);
(async () => {
  run("showCenter('diff'); gotoLine(3);");
  assert.equal(run('diffShown'), false, 'uninitialized diff must not become active');
  assert.equal(get('duo').classList.contains('hide'), false);
  context.testEditor = editor('original');
  run('editor = testEditor; gotoLine(3);');
  assert.equal(context.testEditor.line, 3);

  context.result = { fixed_content: 'fixed', original_sha256:hash('original'), candidate_sha256:hash('fixed'), requires_review:true,
    problems_after: [], compile_before: { ok: true }, compile_after: { ok: true } };
  await run("applyResult(result)");
  run("showCenter('diff'); gotoLine(7);");
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
  context.result.original_sha256 = hash("other file");
  await run("applyResult(result)");
  run("showCenter('diff');");
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


  // Every adoption is tied to the original editor version and full source hash.
  function resultFor(source, fixed) {
    return {requires_review:true, fixed_content:fixed, original_sha256:hash(source), candidate_sha256:hash(fixed),
            problems_after:[], compile_before:{ok:true}, compile_after:{ok:true}};
  }
  context.testEditor.setValue('source');
  context.guardResult = resultFor('source','candidate');
  await run('applyResult(guardResult)');
  context.testEditor.setValue('new user edit');
  await get('btnAccept').onclick();
  assert.equal(context.testEditor.getValue(),'new user edit','stale normal candidate must not overwrite user edit');
  assert.equal(get('btnAccept').disabled,true);
  context.testEditor.setValue('source');
  context.guardResult = resultFor('source','candidate');
  await run('applyResult(guardResult)');
  context.testEditor.setValue('temporary'); context.testEditor.setValue('source');
  await get('btnAccept').onclick();
  assert.equal(context.testEditor.getValue(),'source','edit then revert still changes revision');
  await run('applyResult(guardResult)');
  const beforeVersion=context.testEditor.model.version;
  await get('btnAccept').onclick();
  assert.equal(context.testEditor.getValue(),'candidate');
  await get('btnAccept').onclick();
  assert.equal(context.testEditor.model.version,beforeVersion+1,'duplicate adoption must not apply again');

  function handoffResult(body) {
    const points=Array.from(body.content), range=body.source_range;
    const original=points.slice(range.start,range.end).join(''), candidate=original+'1';
    const fixed=points.slice(0,range.start).join('')+candidate+points.slice(range.end).join('');
    const binding={input_hash:hash(original),parent_revision:null,candidate_hash:hash(candidate),current_revision:1};
    return {...resultFor(body.content,fixed), source_revision:body.revision, handoff_transfer_id:body.transfer_id,
      handoff:{schema_version:1,transfer_id:body.transfer_id,document_sha256:hash(body.content),input_sha256:hash(original),
               source_range:range, original_latex:original, expected_revision:body.revision, checkpoint:'MiniCPM-V-4.7-1B',
               status:'review_required',candidate,candidate_sha256:hash(candidate),parent_revision:null,candidate_revision:1,
               review:{id:'test-review',status:'pending',binding}}};
  }
  run('handoffEnabled=true');
  context.testEditor.setValue('😀 prefix $x+$ suffix');
  context.testEditor.cursor=context.testEditor.getValue().indexOf('x+');
  let transferBody, handoffProposal, decisionCalls=0;
  context.handoffWire=async (url,options) => {
    const body=JSON.parse(options.body);
    if(url.startsWith('/api/studio/handoff?')) {
      transferBody=body; handoffProposal=handoffResult(body); return handoffProposal;
    }
    decisionCalls++;
    return {transfer_id:handoffProposal.handoff_transfer_id,decision:body.decision,
            review:{...handoffProposal.handoff.review,status:body.decision==='accept'?'accepted':'rejected'},
            original_sha256:handoffProposal.original_sha256,candidate_sha256:handoffProposal.candidate_sha256,
            source_revision:handoffProposal.source_revision};
  };
  run('j=handoffWire');
  await get('btnHandoff').onclick();
  assert.equal(transferBody.source_range.encoding,'unicode-codepoints');
  assert.equal(transferBody.source_range.start,Array.from(transferBody.content.slice(0,transferBody.content.indexOf('x+'))).length);
  assert.equal(context.testEditor.getValue(),'😀 prefix $x+$ suffix','handoff response creates a candidate buffer only');
  await get('btnAccept').onclick();
  assert.equal(context.testEditor.getValue(),'😀 prefix $x+1$ suffix');
  await get('btnAccept').onclick();
  assert.equal(decisionCalls,1,'duplicate handoff adoption must not post again');

  // An edit while either handoff or review HTTP is pending preserves the new source.
  context.testEditor.setValue('😀 prefix $x+$ suffix');
  context.testEditor.cursor=context.testEditor.getValue().indexOf('x+');
  let finishHandoff, notifyHandoff;
  const sawHandoff=new Promise(resolve=>{notifyHandoff=resolve;});
  context.deferredHandoff=(url,options)=>new Promise(resolve=>{
    const body=JSON.parse(options.body);finishHandoff=()=>resolve(handoffResult(body));notifyHandoff();
  });
  run('j=deferredHandoff');
  const pendingHandoff=get('btnHandoff').onclick();
  await sawHandoff;
  context.testEditor.setValue('edited during handoff'); finishHandoff();
  await pendingHandoff;
  assert.equal(context.testEditor.getValue(),'edited during handoff');
  assert.equal(run('lastResult'),null);

  context.testEditor.setValue('😀 prefix $x+$ suffix');
  context.testEditor.cursor=context.testEditor.getValue().indexOf('x+');
  run('j=handoffWire'); await get('btnHandoff').onclick();
  let finishDecision, notifyDecision;
  const sawDecision=new Promise(resolve=>{notifyDecision=resolve;});
  context.deferredDecision=(url,options)=>new Promise(resolve=>{
    const body=JSON.parse(options.body);
    finishDecision=()=>resolve({transfer_id:handoffProposal.handoff_transfer_id,decision:body.decision,
      review:{...handoffProposal.handoff.review,status:'accepted'},original_sha256:handoffProposal.original_sha256,
      candidate_sha256:handoffProposal.candidate_sha256,source_revision:handoffProposal.source_revision});
    notifyDecision();
  });
  run('j=deferredDecision');
  const pendingDecision=get('btnAccept').onclick();await sawDecision;
  context.testEditor.setValue('edited during review');finishDecision();await pendingDecision;
  assert.equal(context.testEditor.getValue(),'edited during review','post-request source/version check must prevent stale adoption');

  context.testEditor.setValue('😀 prefix $x+$ suffix');
  context.testEditor.cursor=context.testEditor.getValue().indexOf('x+');
  run('j=handoffWire');await get('btnHandoff').onclick();
  await get('btnReject').onclick();
  assert.equal(context.testEditor.getValue(),'😀 prefix $x+$ suffix');
  assert.equal(run('lastResult.local_decision'),'reject');

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
  console.log('PASS: same-origin pinned Monaco configuration; JS syntax; unavailable/available diff navigation; problem navigation; file-switch disposal/reset; new-file diff; stale/reverted source guard; unicode handoff; async edit guards; idempotent adopt/reject; preview collapse/reopen/drag; critical CSS rules.');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => clearTimeout(testWatchdog));
