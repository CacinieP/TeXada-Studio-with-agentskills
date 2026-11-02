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
  setTimeout: fn => fn(), clearTimeout() {}, alert: message => { throw new Error(message); },
});
const run = source => vm.runInContext(source, context);
new vm.Script(script);
run(script);
const pageLoadFiles = run('loadFiles');
const pageCompilePreview = run('compilePreview');
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
  assert.equal(get('btnSave').disabled,false,'accepted candidate must be immediately saveable');
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

  // A saved snapshot may finish after new typing; never mark the newer text saved.
  context.testEditor.setValue('draft snapshot');
  run("showCenter('edit'); curName='saved.tex'; savedContent='previous'; savedHash='previous-hash';");
  let saveRequest, finishSave, notifySave;
  const sawSave = new Promise(resolve => { notifySave=resolve; });
  context.saveWire=(url,options)=>new Promise(resolve=>{ saveRequest=JSON.parse(options.body);finishSave=()=>resolve({name:'saved.tex',sha256:hash('draft snapshot')});notifySave(); });
  run('j=saveWire');
  const saving=run('saveDocument()');await sawSave;
  context.testEditor.setValue('new typing');finishSave();await saving;
  assert.equal(saveRequest.expected_sha256,'previous-hash');
  assert.equal(run('savedContent'),'draft snapshot');
  assert.equal(run('isDirty()'),true);
  assert.equal(context.testEditor.getValue(),'new typing');

  // File names render as data and text, never as executable inline handlers.
  context.listWire=async()=>({files:['<img src=x onerror=alert(1)>.tex']});run('j=listWire');
  await pageLoadFiles();
  assert.match(get('files').innerHTML,/&lt;img/);
  assert.doesNotMatch(get('files').innerHTML,/<img|onclick=/);

  // A PDF without raster support remains downloadable, bound to its actual source.
  context.testEditor.setValue('compiled source');run("curName='saved.tex'; showCenter('edit');");
  context.previewWire=async()=>({compile_ok:true,preview_ok:false,ok:false,tag:'live-a',pdf:'/api/studio/pdf/saved.tex/live-a',pages:[],log:'raster unavailable'});
  run('j=previewWire');await pageCompilePreview('compiled source');
  assert.equal(get('btnPdf').classList.contains('hide'),false);
  let pdfFetches=0;
  context.fetch=async()=>{pdfFetches++;return {ok:true,blob:async()=>new Blob(['PDF'])};};
  await get('btnPdf').onclick();assert.equal(pdfFetches,1);
  context.testEditor.setValue('edited after compilation');
  await get('btnPdf').onclick();assert.equal(pdfFetches,1,'stale PDF must not be fetched');
  run('invalidatePreview()');assert.equal(run('lastPreviewTag'),null);
  assert.equal(get('btnPdf').classList.contains('hide'),true);

  // Even a response whose PDF bytes arrive later must keep its source binding.
  context.testEditor.setValue('PDF A');run("curName='a.tex';showCenter('edit');lastPreviewTag='live-a';previewBinding={name:'a.tex',content:'PDF A',pdf:'/api/studio/pdf/a.tex/live-a'};");
  let finishPdf,notifyPdf;const sawPdf=new Promise(resolve=>{notifyPdf=resolve;});let raceDownloads=0;
  context.captureRaceDownload=()=>{raceDownloads++;};run('download=captureRaceDownload');
  context.fetch=async()=>({ok:true,blob:()=>new Promise(resolve=>{finishPdf=()=>resolve(new Blob(['A PDF']));notifyPdf();})});
  const downloading=get('btnPdf').onclick();await sawPdf;
  context.testEditor.setValue('PDF B');run("curName='b.tex';fileEpoch++;");finishPdf();await downloading;
  assert.equal(raceDownloads,0,'late PDF must not be saved with another document name');

  // Document mutations freeze controls and preserve any concurrent editor change.
  context.testEditor.setValue('rename original');
  run("curName='rename-a.tex';savedContent='rename original';savedHash='hash-a';documentOrigin='local';");
  context.prompt=()=> 'rename-b.tex';
  let finishRename,notifyRename;const sawRename=new Promise(resolve=>{notifyRename=resolve;});
  context.renameWire=(url,options)=>new Promise(resolve=>{assert.match(url,/rename/);finishRename=()=>resolve({name:'rename-b.tex'});notifyRename();});
  run('j=renameWire');const renaming=get('btnRename').onclick();await sawRename;
  assert.equal(run('busy'),true);assert.equal(get('btnNew').disabled,true);
  context.testEditor.setValue('NEW DURING RENAME');finishRename();await renaming;
  assert.equal(context.testEditor.getValue(),'NEW DURING RENAME');
  assert.equal(run('curName'),'rename-a.tex');assert.equal(run('isDirty()'),true);assert.equal(run('busy'),false);
  context.prompt=()=> 'created.tex';
  let finishCreate,notifyCreate;const sawCreate=new Promise(resolve=>{notifyCreate=resolve;});
  context.createWire=()=>new Promise(resolve=>{finishCreate=()=>resolve({name:'created.tex'});notifyCreate();});
  run('j=createWire');const creating=get('btnNew').onclick();await sawCreate;
  context.testEditor.setValue('NEW DURING CREATE');finishCreate();await creating;
  assert.equal(context.testEditor.getValue(),'NEW DURING CREATE');assert.equal(run('curName'),'rename-a.tex');
  assert.equal(run('isDirty()'),true);assert.equal(run('busy'),false);

  context.testEditor.setValue('delete original');run("savedContent='delete original';documentOrigin='local';");context.confirm=()=>true;
  let finishDelete,notifyDelete;const sawDelete=new Promise(resolve=>{notifyDelete=resolve;});
  context.deleteWire=(url)=>url.includes('/delete?') ? new Promise(resolve=>{finishDelete=()=>resolve({ok:true});notifyDelete();}) : Promise.resolve({files:['remaining.tex']});
  run('j=deleteWire');const deleting=get('btnDelete').onclick();await sawDelete;
  context.testEditor.setValue('NEW DURING DELETE');finishDelete();await deleting;
  assert.equal(context.testEditor.getValue(),'NEW DURING DELETE');assert.equal(run('curName'),'rename-a.tex');

  context.testEditor.setValue('upload original');run("savedContent='upload original';j=async()=>({ok:true});");
  let finishRead,notifyRead;const sawRead=new Promise(resolve=>{notifyRead=resolve;});
  const uploadEvent={target:{value:'selected',files:[{name:'uploaded.tex',size:20,text:()=>new Promise(resolve=>{finishRead=()=>resolve('uploaded content');notifyRead();})}]}};
  const uploading=get('fileInput').onchange(uploadEvent);await sawRead;
  context.testEditor.setValue('NEW DURING UPLOAD');finishRead();await uploading;
  assert.equal(context.testEditor.getValue(),'NEW DURING UPLOAD');assert.equal(run('curName'),'rename-a.tex');

  context.testEditor.setValue('ocr original');run("savedContent='ocr original';");get('ocrName').value='ocr-new.tex';get('ocrCandidate').value='OCR source';
  let finishOcrCreate,notifyOcrCreate;const sawOcrCreate=new Promise(resolve=>{notifyOcrCreate=resolve;});
  context.ocrCreateWire=()=>new Promise(resolve=>{finishOcrCreate=()=>resolve({ok:true});notifyOcrCreate();});
  run('j=ocrCreateWire');const ocrCreating=get('btnOcrCreate').onclick();await sawOcrCreate;
  context.testEditor.setValue('NEW DURING OCR CREATE');finishOcrCreate();await ocrCreating;
  assert.equal(context.testEditor.getValue(),'NEW DURING OCR CREATE');assert.equal(run('curName'),'rename-a.tex');
  assert.equal(run('isDirty()'),true);assert.equal(run('busy'),false);

  // A late compile for earlier text cannot enable export for current edits.
  context.testEditor.setValue('pending compile');
  let finishCompile, notifyCompile;const sawCompile=new Promise(resolve=>{notifyCompile=resolve;});
  context.compileWire=()=>new Promise(resolve=>{finishCompile=()=>resolve({compile_ok:true,tag:'live-b',pdf:'/api/studio/pdf/saved.tex/live-b',pages:[]});notifyCompile();});
  run('j=compileWire');const compiling=pageCompilePreview('pending compile');await sawCompile;
  context.testEditor.setValue('newer edit');finishCompile();await compiling;
  assert.equal(run('previewBinding'),null,'late compilation must not bind newer editor content');

  // Normal candidate decisions persist before changing the editor.
  context.testEditor.setValue('review original');
  context.persistedResult={...resultFor('review original','review candidate'),job_id:'a'.repeat(32)};
  await run('applyResult(persistedResult)');let decisions=0;
  context.reviewWire=async(url,options)=>{const body=JSON.parse(options.body);decisions++;assert.match(url,/jobs\/a{32}\/decision/);return {job_id:'a'.repeat(32),decision:body.decision,original_sha256:hash('review original'),candidate_sha256:hash('review candidate')};};
  run('j=reviewWire');await get('btnReject').onclick();
  assert.equal(decisions,1);assert.equal(context.testEditor.getValue(),'review original');
  assert.equal(run('previewBinding'),null);

  // Testing a draft model address must never save or replace active configuration.
  get('modelBaseUrl').value='http://127.0.0.1:8080/v1';get('modelName').value='draft-model';
  const activeModelLabel=get('sb-model').textContent;let probeCalls=0;
  context.probeWire=async(url,options)=>{assert.match(url,/\/probe\?/);assert.equal(JSON.parse(options.body).model,'draft-model');probeCalls++;return {model_available:true,model:'draft-model'};};
  run('j=probeWire');await get('btnTestModel').onclick();
  assert.equal(probeCalls,1);assert.equal(get('sb-model').textContent,activeModelLabel,'probe must not display draft model as active');
  run('ocrFile=null');context.oversizeImage={name:'too-large.png',type:'image/png',size:13*1024*1024};
  run('chooseOcrFile(oversizeImage)');assert.equal(run('ocrFile'),null,'OCR file size must match 12 MiB server limit');

  get('sepE').listeners.get('mousedown')({ target: { closest: () => get('sepBtnE') }, preventDefault() { throw new Error('button started drag'); } });
  assert.equal(documentListeners.has('mousemove'), false);
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), true);
  assert.equal(get('previewPane').style.overflow, 'hidden');
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), false);
  assert.equal(get('previewPane').style.width, '43%');
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
  console.log('PASS: same-origin pinned Monaco configuration; JS syntax; unavailable/available diff navigation; problem navigation; file-switch disposal/reset; new-file diff; stale/reverted source guard; unicode handoff; async edit guards; idempotent adopt/reject; preview collapse/reopen/drag; snapshot-save race; escaped filenames; PDF/source binding; late compile guard; persisted review; deferred PDF and document mutation guards; critical CSS rules.');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => clearTimeout(testWatchdog));
