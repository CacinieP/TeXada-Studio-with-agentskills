const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const {webcrypto, createHash} = require('node:crypto');
const hash = text => createHash('sha256').update(text, 'utf8').digest('hex');

// Exercise the page's own handlers offline; no browser or remote API calls.
const html = fs.readFileSync(process.argv[2] || path.join(__dirname, 'studio.html'), 'utf8');
const stylesheet = fs.readFileSync(path.join(__dirname, 'static', 'editor', 'studio.css'), 'utf8');
const templates = require('./static/editor/templates.js');
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const elements = new Map();
function eventTarget() {
  const registrations = new Map(), listeners = new Map();
  return {listeners, addEventListener(type,callback) {
    const callbacks=registrations.get(type) || [];
    if(!callbacks.includes(callback))callbacks.push(callback);
    registrations.set(type,callbacks);
    listeners.set(type,event=>{for(const listener of [...(registrations.get(type)||[])])listener(event);});
  }, removeEventListener(type,callback) {
    if(!callback){registrations.delete(type);listeners.delete(type);return;}
    const remaining=(registrations.get(type)||[]).filter(listener=>listener!==callback);
    if(remaining.length)registrations.set(type,remaining);else{registrations.delete(type);listeners.delete(type);}
  }};
}
const documentEvents=eventTarget(),windowEvents=eventTarget();
const documentListeners = documentEvents.listeners;
const windowListeners = windowEvents.listeners;
function classes(value = '') {
  const values = new Set(value.split(/\s+/).filter(Boolean));
  return {
    add: (...items) => items.forEach(x=>values.add(x)), remove: (...items) => items.forEach(x=>values.delete(x)), contains: x => values.has(x),
    toggle(x, force = !values.has(x)) { force ? values.add(x) : values.delete(x); return force; },
  };
}
// A small structural DOM, shared by all behavior checks. Focus and containment
// follow the actual page hierarchy, including closed details and dialogs.
const domNodes=[],nodeStack=[],voidTags=new Set(['area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr']);
function matchesSelector(node,selector) {
  return selector.split(',').some(part=>{
    let value=part.trim();
    const negatives=[...value.matchAll(/:not\(([^)]+)\)/g)].map(match=>match[1]);
    value=value.replace(/:not\([^)]+\)/g,'');
    if(negatives.some(negative=>matchesSelector(node,negative)))return false;
    if(value.includes(':disabled')&&!node.disabled)return false;
    if(value.includes(':enabled')&&node.disabled)return false;
    value=value.replace(/:(?:disabled|enabled)/g,'');
    const tag=value.match(/^[A-Za-z][\w-]*/)?.[0];
    if(tag&&node.tagName!==tag.toUpperCase())return false;
    for(const match of value.matchAll(/#([\w-]+)/g))if(node.id!==match[1])return false;
    for(const match of value.matchAll(/\.([\w-]+)/g))if(!node.classList.contains(match[1]))return false;
    for(const match of value.matchAll(/\[([\w-]+)(?:\s*=\s*["']?([^\]"']*)["']?)?\]/g)) {
      if(!node.hasAttribute(match[1]))return false;
      if(match[2]!==undefined&&node.getAttribute(match[1])!==match[2])return false;
    }
    return true;
  });
}
function visible(node) {
  for(let current=node;current;current=current.parentElement) {
    if(current.hidden||current.classList.contains('hide')||current.classList.contains('closed')||current.style.display==='none')return false;
    if(current.classList.contains('collapsed')&&current.id!=='bottom')return false;
    if(current.tagName==='DIALOG'&&!current.open)return false;
    if(current.tagName==='DETAILS'&&!current.open) {
      const summary=current.children.find(child=>child.tagName==='SUMMARY');
      if(!summary?.contains(node))return false;
    }
  }
  return true;
}
// Resolve simple selectors from the shipped CSS at a viewport width. This is
// sufficient to detect a mobile min-height overriding the collapsed pane; the
// real-browser checks remain responsible for full layout and raster rendering.
function cssAt(node,width) {
  const values=new Map();let order=0;
  function collect(css) {
    let cursor=0;
    while(cursor<css.length) {
      const opening=css.indexOf('{',cursor);if(opening<0)break;
      const header=css.slice(cursor,opening).trim();let closing=opening+1,depth=1;
      while(closing<css.length&&depth){if(css[closing]==='{')depth++;if(css[closing]==='}')depth--;closing++;}
      const body=css.slice(opening+1,closing-1);cursor=closing;
      if(header.startsWith('@media')) {
        const max=header.match(/max-width\s*:\s*(\d+)px/)?.[1],min=header.match(/min-width\s*:\s*(\d+)px/)?.[1];
        if((max||min)&&(!max||width<=Number(max))&&(!min||width>=Number(min)))collect(body);
        continue;
      }
      if(header.startsWith('@'))continue;
      for(const selector of header.split(',')) {
        const simple=selector.trim(),structure=simple.replace(/\[[^\]]+\]/g,'');
        if(!/^[#.]/.test(simple)||/[\s>+~:]/.test(structure)||!matchesSelector(node,simple))continue;
        const specificity=100*(simple.match(/#/g)||[]).length+10*((simple.match(/\./g)||[]).length+(simple.match(/\[/g)||[]).length);
        for(const declaration of body.split(';')) {
          const colon=declaration.indexOf(':');if(colon<0)continue;
          const property=declaration.slice(0,colon).trim(),raw=declaration.slice(colon+1).trim();
          const important=/!important\s*$/.test(raw),value=raw.replace(/\s*!important\s*$/,'').trim(),previous=values.get(property);
          const next={value,important,specificity,order:order++};
          if(!previous||(important&&!previous.important)||(important===previous.important&&(specificity>previous.specificity||(specificity===previous.specificity&&next.order>previous.order))))values.set(property,next);
        }
      }
    }
  }
  collect(stylesheet.replace(/\/\*[\s\S]*?\*\//g,''));
  return Object.fromEntries([...values].map(([property,entry])=>[property,entry.value]));
}
const markup=html.slice(0,html.indexOf('<script'));
for(const tag of markup.matchAll(/<\/?([A-Za-z][\w:-]*)\b[^>]*>/g)) {
  const name=tag[1].toLowerCase();
  if(tag[0].startsWith('</')){const at=nodeStack.map(node=>node.tagName.toLowerCase()).lastIndexOf(name);if(at>=0)nodeStack.length=at;continue;}
  const attrs=Object.fromEntries([...tag[0].matchAll(/([\w-]+)="([^"]*)"/g)].map(match=>[match[1],match[2]]));
  for(const boolean of ['disabled','hidden','open','checked'])if(new RegExp('\\s'+boolean+'(?=\\s|>|/)').test(tag[0]))attrs[boolean]='';
  const events=eventTarget(),style=Object.fromEntries((attrs.style||'').split(';').filter(Boolean).map(pair=>pair.split(':').map(value=>value.trim())));
  const node={id:attrs.id||'',tagName:name.toUpperCase(),attrs,children:[],parentElement:nodeStack.at(-1)||null,
    classList:classes(attrs.class),style,listeners:events.listeners,dataset:Object.fromEntries(Object.entries(attrs).filter(([key])=>key.startsWith('data-')).map(([key,value])=>[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase()),value])),
    disabled:Object.hasOwn(attrs,'disabled'),hidden:Object.hasOwn(attrs,'hidden'),open:Object.hasOwn(attrs,'open'),checked:Object.hasOwn(attrs,'checked'),
    textContent:'',innerHTML:'',value:attrs.value||'',offsetWidth:1000,isConnected:true,
    setAttribute(key,value){attrs[key]=String(value);if(['disabled','hidden','open','checked'].includes(key))this[key]=true;},
    getAttribute(key){if(key.startsWith('data-')){const field=key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase());if(Object.hasOwn(this.dataset,field))return this.dataset[field];}return Object.hasOwn(attrs,key)?attrs[key]:null;},
    hasAttribute(key){return ['disabled','hidden','open','checked'].includes(key)?this[key]:this.getAttribute(key)!==null;},
    removeAttribute(key){delete attrs[key];if(['disabled','hidden','open','checked'].includes(key))this[key]=false;},
    addEventListener:events.addEventListener,removeEventListener:events.removeEventListener,
    contains(child){for(let current=child;current;current=current.parentElement)if(current===this)return true;return false;},
    matches(selector){return matchesSelector(this,selector);},
    closest(selector){for(let current=this;current;current=current.parentElement)if(matchesSelector(current,selector))return current;return null;},
    querySelectorAll(selector){return domNodes.filter(child=>child!==this&&this.contains(child)&&matchesSelector(child,selector));},
    querySelector(selector){return this.querySelectorAll(selector)[0]||null;},
    focus(){if(!this.disabled&&visible(this)){context.document.activeElement=this;this.focused=true;}},
    click(){if(this.disabled)return;const event={target:this,currentTarget:this,preventDefault(){},stopPropagation(){}};const result=this.onclick?.(event);this.listeners.get('click')?.(event);return result;},
    showModal(){this.open=true;},close(){this.open=false;},scrollIntoView(){},
    getClientRects(){return visible(this)?[{width:100,height:30}]:[];},
    getBoundingClientRect:()=>({left:0,top:0,right:1000,bottom:1000,width:1000,height:1000})
  };
  Object.defineProperty(node,'offsetParent',{get:()=>visible(node)?node.parentElement:null});
  node.parentElement?.children.push(node);domNodes.push(node);if(node.id)elements.set(node.id,node);
  if(!voidTags.has(name)&&!tag[0].endsWith('/>'))nodeStack.push(node);
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
    setValue(value) { this.model.setValue(value); this.position=null; },
    getPosition() { return this.position || {lineNumber:1,column:(this.cursor || 0)+1}; },
    getSelection() { const p=this.getPosition(); return this.selection || {getStartPosition:()=>p,getEndPosition:()=>p}; },
    options:{}, layout() {}, updateOptions(options) { this.options={...this.options,...options}; }, revealLineInCenter(line) { this.line = line; }, setPosition(position) { this.position=position; }, focus() { this.focused=true;context.document.activeElement=this===context.testEditor?get('editor'):get('diff'); },
    getAction(id) { return {run:async()=>{this.lastAction=id;}}; },
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
const legacyPreferences=new Map([
  ['texada.rightpanelCollapsed','true'],['texada.rightpanelWidth','0px'],['texada.logHeight','0px'],
]);
const context = vm.createContext({
  URLSearchParams, URL, Blob, TextEncoder, crypto:webcrypto, require: amdRequire, monaco,
  location: { search: '' },
  window: { innerWidth:1440,innerHeight:900,addEventListener:windowEvents.addEventListener,TeXadaTemplates:templates,
    matchMedia(query){const max=Number(query.match(/max-width:\s*(\d+)px/)?.[1]||Infinity);return {matches:this.innerWidth<=max,media:query,addEventListener(){},removeEventListener(){}};} },
  document: {
    getElementById: get,
    documentElement:domNodes.find(node=>node.tagName==='HTML'),body:domNodes.find(node=>node.tagName==='BODY'),
    querySelectorAll:selector=>domNodes.filter(node=>matchesSelector(node,selector)),
    querySelector:selector=>domNodes.find(node=>matchesSelector(node,selector))||null,
    addEventListener:documentEvents.addEventListener,removeEventListener:documentEvents.removeEventListener,
  },
  ResizeObserver: class { observe() {} },
  fetch: async () => ({ ok: true, json: async () => ({ files: [], host:'PRIVATE-HOST-SENTINEL',platform:'PRIVATE-PLATFORM-SENTINEL',mem:'' }) }),
  localStorage:{getItem:key=>legacyPreferences.get(key)??null,setItem:(key,value)=>legacyPreferences.set(key,String(value))},
  setTimeout: fn => fn(), clearTimeout() {}, alert: message => { throw new Error(message); },
});
const run = source => vm.runInContext(source, context);
new vm.Script(script);
run(script);
const pageLoadFiles = run('loadFiles');
const pageCompilePreview = run('compilePreview');
const pageAnalyze = run('analyze');
const pageRestoreJob = run('restoreJob');
const pageFixHandler = get('btnFix').onclick;
windowListeners.get('load')();

const testWatchdog = setTimeout(() => { console.error("Studio behavior test did not complete"); process.exitCode = 1; }, 10000);
(async () => {
  await Promise.resolve(); await Promise.resolve();
  assert.equal(get('rightpanel').classList.contains('closed'),true,'Agent drawer starts closed');
  assert.equal(get('btnAgent').getAttribute('aria-expanded'),'false');
  assert.equal(get('activityAgent').getAttribute('aria-expanded'),'false');
  assert.equal(get('bottom').classList.contains('collapsed'),true,'problems and log start folded');
  assert.equal(get('btnProblems').getAttribute('aria-expanded'),'false');
  assert.equal(get('btnLog').getAttribute('aria-expanded'),'false');
  assert.equal(get('workflowPanel').open,false,'advanced Agent controls remain optional');
  assert.equal(get('exportMenu').classList.contains('hide'),true);
  assert.equal(get('btnPdf').disabled,true,'uncompiled PDF remains visible but unavailable');
  assert.equal(get('btnPdf').classList.contains('hide'),false);
  assert.equal(get('sidebar').classList.contains('collapsed'),false,'desktop document navigation is visible');
  assert.equal(get('rightpanel').style.width,'320px','legacy zero-width preference cannot hide an opened drawer');
  assert.notEqual(get('bottom').style.height,'0px','legacy zero log height is not imported');
  for(const node of domNodes)assert.doesNotMatch(node.textContent+node.innerHTML,/PRIVATE-(?:HOST|PLATFORM)-SENTINEL/,'device details never enter workspace chrome');

  run("showCenter('diff'); gotoLine(3);");
  assert.equal(run('diffShown'), false, 'uninitialized diff must not become active');
  assert.equal(get('duo').classList.contains('hide'), false);
  context.testEditor = editor('original');
  run('editor = testEditor; gotoLine(3);');
  assert.equal(context.testEditor.line, 3);

  context.result = { fixed_content: 'fixed', original_sha256:hash('original'), candidate_sha256:hash('fixed'), requires_review:true,
    problems_after: [], compile_before: { ok: true }, compile_after: { ok: true } };
  await run("applyResult(result)");
  assert.equal(get('rightpanel').classList.contains('closed'),false,'new candidates automatically reveal their review controls');
  assert.equal(get('btnAgent').getAttribute('aria-expanded'),'true');
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
  get('pvImgWrap').innerHTML='<img src="/api/studio/preview/old-document.png">';
  get('pvLog').textContent='old document compiler failure';get('pvLog').classList.remove('hide');
  const loading = run("loadFile('other.tex')");
  assert.doesNotMatch(get('pvImgWrap').innerHTML,/<img/,'opening another document removes the previous PDF even while its file request is pending');
  assert.equal(get('pvLog').textContent,'','switching documents clears the previous compiler log');
  assert.equal(get('pvLog').classList.contains('hide'),true);
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
  assert.equal(get('btnPdf').disabled,false);
  let pdfFetches=0;
  context.fetch=async()=>{pdfFetches++;return {ok:true,blob:async()=>new Blob(['PDF'])};};
  await get('btnPdf').onclick();assert.equal(pdfFetches,1);
  context.testEditor.setValue('edited after compilation');
  await get('btnPdf').onclick();assert.equal(pdfFetches,1,'stale PDF must not be fetched');
  get('pvImgWrap').innerHTML='<img src="/api/studio/preview/previous-document.png">';
  get('pvLog').textContent='previous document compiler log';get('pvLog').classList.remove('hide');
  run('invalidatePreview()');assert.equal(run('lastPreviewTag'),null);
  assert.equal(get('btnPdf').disabled,true);
  assert.equal(get('btnPdf').classList.contains('hide'),false,'invalid PDF stays discoverable in export menu');
  assert.doesNotMatch(get('pvImgWrap').innerHTML,/<img/,'invalidating a version removes its stale page, not just its export binding');
  assert.equal(get('pvLog').textContent,'','previous-document compiler details must not remain attached to the new version');
  assert.equal(get('pvLog').classList.contains('hide'),true);

  // Even a response whose PDF bytes arrive later must keep its source binding.
  context.testEditor.setValue('PDF A');run("curName='a.tex';showCenter('edit');lastPreviewTag='live-a';previewBinding={name:'a.tex',content:'PDF A',pdf:'/api/studio/pdf/a.tex/live-a'};setPdfAvailable(true);");
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

  // One-click Tectonic install posts to the tools endpoint and reports the outcome.
  context.toolsWire=url=>{assert.match(url,/api\/studio\/tools\/install/);return Promise.resolve({ok:true,version:'0.17.0',path:'/Users/example/.texada/bin/tectonic',tools:{tectonic:true,pdftoppm:false}});};
  run('j=toolsWire');
  await run('installLocalTools()');
  assert.match(get('installToolsHint').textContent,/已安装 Tectonic 0\.17\.0/,'success is reported next to the button');
  assert.equal(get('btnInstallTools').disabled,true,'button stays disabled after a successful install');
  context.toolsWire=()=>Promise.reject(new Error('SHA256 校验失败'));
  run('j=toolsWire');
  await run('installLocalTools()');
  assert.equal(get('btnInstallTools').disabled,false,'a failed install re-enables the button');
  assert.match(get('installToolsHint').textContent,/安装失败/,'failure reason is shown inline');

  // The template picker lists the shipped skeletons and creates from them verbatim.
  context.testEditor.setValue('template base');run("savedContent='template base';documentOrigin='local';");
  get('btnNewFromTemplate').onclick();
  assert.equal(get('templateDialog').open,true,'sidebar button opens the template picker');
  assert.match(get('templateList').innerHTML,/data-template-id="exam-paper"/,'picker lists shipped templates');
  context.prompt=()=> 'from-template.tex';
  let templateBody=null;
  context.createWire=(url,requestOptions)=>{templateBody=JSON.parse(requestOptions.body);return Promise.resolve({name:'from-template.tex'});};
  run('j=createWire');
  await run('createFromTemplate("exam-paper")');
  assert.equal(templateBody && templateBody.name,'from-template.tex','template creation posts the chosen file name');
  assert.equal(templateBody && templateBody.content,templates.list().find(template=>template.id==='exam-paper').content,'create posts the shipped template verbatim');
  assert.equal(get('templateDialog').open,false,'picker closes after creation');
  assert.equal(run('busy'),false);
  get('btnTemplateClose').onclick();
  assert.equal(get('templateDialog').open,false);

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

  // OCR has its own request lifecycle; it must never freeze the source editor
  // or let a second/obsolete response replace an edited review candidate.
  context.FileReader=class {
    readAsDataURL(){this.result='data:image/png;base64,AA==';this.onload();}
  };
  context.ocrA={name:'A.png',type:'image/png',size:100};
  context.ocrB={name:'B.png',type:'image/png',size:100};
  const ocrRequests=[];
  context.ocrWire=(url,options)=>new Promise((resolve,reject)=>{
    assert.match(url,/\/import\?/);ocrRequests.push({body:JSON.parse(options.body),resolve,reject});
  });
  const flushOcr=async()=>{await Promise.resolve();await Promise.resolve();};
  const recognized=(name,content)=>({name,content,requires_review:true});
  run("j=ocrWire;busy=false;ocrReviewActive=false;closeDialog('ocrDialog');openImportPanel();chooseOcrFile(ocrA);");
  get('ocrPages').value='1';
  const ocrPendingA=get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests.length,1);assert.equal(ocrRequests[0].body.name,'A.png');
  assert.equal(run('ocrRunning'),true);assert.equal(run('busy'),false);
  context.testEditor.setValue('source edit during OCR');
  run('chooseOcrFile(ocrB);lockDocumentMutation(false);');
  assert.equal(get('btnOcr').disabled,true,'choosing B or a document unlock cannot release the OCR lock');
  await get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests.length,1,'calling the disabled handler directly cannot start OCR B');
  get('ocrName').value='manual-review.tex';get('ocrCandidate').value='manual review edits';
  ocrRequests[0].resolve(recognized('A.tex','obsolete A'));await ocrPendingA;
  assert.equal(get('ocrName').value,'manual-review.tex');assert.equal(get('ocrCandidate').value,'manual review edits');
  assert.equal(get('ocrDialog').open,false,'an obsolete result cannot reopen review');
  assert.equal(context.testEditor.getValue(),'source edit during OCR','OCR leaves source edits intact');
  assert.equal(run('ocrRunning'),false);assert.equal(get('btnOcr').disabled,false);
  assert.equal(run('ocrFile.name'),'B.png','finally restores availability for the current selected file');

  const ocrPendingB=get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests.length,2);assert.equal(ocrRequests[1].body.name,'B.png');
  ocrRequests[1].resolve(recognized('B.tex','candidate B'));await ocrPendingB;
  assert.equal(get('ocrDialog').open,true);assert.equal(get('btnOcr').disabled,true);
  get('ocrName').value='corrected-B.tex';get('ocrCandidate').value='corrected B';
  get('ocrCandidate').listeners.get('input')({});
  run('chooseOcrFile(ocrA)');await get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests.length,2,'an active review blocks another request even through direct invocation');
  assert.equal(get('ocrCandidate').value,'corrected B');assert.equal(get('ocrName').value,'corrected-B.tex');
  let reviewCancelled=false;
  get('ocrDialog').listeners.get('cancel')({preventDefault(){reviewCancelled=true;}});
  assert.equal(reviewCancelled,true);assert.equal(run('ocrReviewActive'),false);assert.equal(get('btnOcr').disabled,false);

  // Closing and reopening import keeps the old request locked until it settles,
  // while its late success/error has no permission to alter the new session.
  const ocrCancelled=get('btnOcr').onclick();await flushOcr();
  get('btnImportClose').onclick();run('openImportPanel();chooseOcrFile(ocrB)');
  await get('btnOcr').onclick();assert.equal(ocrRequests.length,3);assert.equal(get('btnOcr').disabled,true);
  const reopenedHint=get('ocrHint').textContent;
  ocrRequests[2].resolve(recognized('late-A.tex','late A after close'));await ocrCancelled;
  assert.equal(get('ocrDialog').open,false);assert.equal(get('ocrCandidate').value,'corrected B');
  assert.equal(get('ocrHint').textContent,reopenedHint,'late result cannot replace the current session hint');
  assert.equal(get('btnOcr').disabled,false);
  const ocrEscaped=get('btnOcr').onclick();await flushOcr();
  let importCancelled=false;
  get('importDialog').listeners.get('cancel')({preventDefault(){importCancelled=true;}});
  run('openImportPanel()');const cancelledHint=get('ocrHint').textContent;
  ocrRequests[3].reject(new Error('obsolete failure'));await ocrEscaped;
  assert.equal(importCancelled,true);assert.equal(get('ocrDialog').open,false);
  assert.equal(get('ocrHint').textContent,cancelledHint,'an obsolete error cannot replace session feedback');
  assert.equal(get('btnOcr').disabled,false);

  // A current request also checks review edits before writing its result.
  const ocrEdited=get('btnOcr').onclick();await flushOcr();
  get('ocrCandidate').value='review modified while awaiting result';get('ocrCandidate').listeners.get('input')({});
  ocrRequests[4].resolve(recognized('ignored.tex','must not replace review'));await ocrEdited;
  assert.equal(get('ocrCandidate').value,'review modified while awaiting result');
  assert.equal(get('ocrName').value,'corrected-B.tex');assert.equal(get('ocrDialog').open,false);
  assert.equal(get('btnOcr').disabled,false);

  const ocrFailed=get('btnOcr').onclick();await flushOcr();
  ocrRequests[5].reject(new Error('model unavailable'));await ocrFailed;
  assert.equal(run('ocrRunning'),false);assert.equal(get('btnOcr').disabled,false,'a current failure can be retried');
  assert.match(get('ocrHint').textContent,/识别未完成/);
  const ocrRetried=get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests[6].body.name,'B.png');
  ocrRequests[6].resolve(recognized('retry.tex','retry candidate'));await ocrRetried;
  assert.equal(get('ocrCandidate').value,'retry candidate');assert.equal(get('ocrName').value,'retry.tex');
  assert.equal(get('ocrDialog').open,true);assert.equal(run('busy'),false);

  // PDF page splitting: chosen ranges reach the request and the review dialog splits per page.
  run('cancelOcrReview();openImportPanel();chooseOcrFile(ocrA);');
  get('ocrStart').value='3';get('ocrPages').value='2';
  const ocrSplitPending=get('btnOcr').onclick();await flushOcr();
  assert.equal(ocrRequests.at(-1).body.page_start,3,'the chosen start page reaches the import request');
  assert.equal(ocrRequests.at(-1).body.max_pages,2);
  ocrRequests.at(-1).resolve({name:'split-doc.tex',content:'merged candidate',requires_review:true,
    pages:[{page:3,body:'page three body'},{page:4,body:'page four body'}],source_pages:6,has_more_pages:true});
  await ocrSplitPending;await flushOcr();
  assert.equal(get('ocrDialog').open,true);
  assert.equal(get('ocrPageSplitField').hidden,false,'multi-page results expose the split controls');
  assert.equal(get('btnOcrSplit').hidden,false);
  assert.equal(get('btnOcrMore').hidden,false);
  assert.match(get('btnOcrMore').textContent,/第 5 页起/,'continuation proposes the next batch');
  assert.match(get('ocrPageList').innerHTML,/data-ocr-page="3"/,'page checkboxes are rendered');
  assert.equal(run('JSON.stringify(checkedOcrPageNumbers())'),'[3,4]');
  const togglePage=(page,checked)=>get('ocrPageList').listeners.get('change')({target:{checked,dataset:{ocrPage:String(page)}}});
  togglePage(4,false);
  assert.match(get('ocrCandidate').value,/page three body/);
  assert.doesNotMatch(get('ocrCandidate').value,/page four body/,'unchecked pages drop out of the merged candidate');
  assert.equal(get('ocrCandidate').value.split('\\clearpage').length-1,0,'a single remaining page has no page break');
  get('ocrCandidate').value='my manual edits';get('ocrCandidate').listeners.get('input')({});
  togglePage(3,false);
  assert.equal(get('ocrCandidate').value,'my manual edits','manual edits are never clobbered by page toggles');
  togglePage(3,true);togglePage(4,true);
  context.testEditor.setValue('split base');run("savedContent='split base';documentOrigin='local';busy=false;");
  let splitCreates=[];
  context.createWire=(url,options)=>{const body=JSON.parse(options.body);splitCreates.push(body);return Promise.resolve({name:body.name});};
  run('j=createWire');
  get('ocrName').value='split-doc.tex';
  await get('btnOcrSplit').onclick();
  assert.equal(splitCreates.length,2,'each checked page becomes its own document');
  assert.deepEqual(splitCreates.map(body=>body.name),['split-doc-第3页.tex','split-doc-第4页.tex']);
  assert.match(splitCreates[0].content,/page three body/);
  assert.match(splitCreates[1].content,/page four body/);
  assert.match(splitCreates[0].content,/\\begin\{document\}/,'split documents remain compilable');
  assert.match(splitCreates[0].content,/\\end\{document\}/);
  run('ocrReviewActive=true;openDialog("ocrDialog");');
  get('ocrName').value='retry.tex';get('ocrCandidate').value='retry candidate';
  run('savingDocument=true');await get('btnOcrCreate').onclick();
  assert.equal(get('ocrDialog').open,true,'waiting for source save cannot close an uncreated review');
  assert.equal(get('ocrCandidate').value,'retry candidate');assert.equal(ocrRequests.length,8);
  run('savingDocument=false');
  get('btnOcrCancel').onclick();get('btnImportClose').onclick();

  // Cancellation during local file reading must not later send the old file.
  let finishOcrRead;
  context.FileReader=class {
    readAsDataURL(){finishOcrRead=()=>{this.result='data:image/png;base64,AA==';this.onload();};}
  };
  run('openImportPanel();chooseOcrFile(ocrA)');const ocrReading=get('btnOcr').onclick();
  get('btnImportClose').onclick();run('openImportPanel();chooseOcrFile(ocrB)');
  await get('btnOcr').onclick();assert.equal(get('btnOcr').disabled,true);
  finishOcrRead();await ocrReading;
  assert.equal(ocrRequests.length,8,'cancelled file reading cannot send an obsolete model request');
  assert.equal(get('ocrCandidate').value,'retry candidate');assert.equal(get('ocrDialog').open,false);
  assert.equal(get('btnOcr').disabled,false);get('btnImportClose').onclick();

  // TeX outlines exclude comments and literal regions without shifting line positions.
  context.outlineSource=String.raw`% \section{Commented}
\section[Short]{A \textbf{nested {title}}}
\subsection{Second \% literal}
\begin{verbatim}
\section{Inside verbatim}
\end{verbatim}
\verb|\section{Inside verb}| \section*{Visible starred}
\begin{minted}{tex}
\section{Inside minted}
\end{minted}
\\section{Escaped command}
\subsubsection{你好 <script>}
`;
  const outline=run('extractDocumentOutline(outlineSource)');
  assert.deepEqual(Array.from(outline,entry=>[entry.label,entry.line,entry.level]),[
    ['A nested title',2,1],['Second % literal',3,2],['Visible starred',7,1],['你好 <script>',12,3],
  ]);
  assert.equal(outline[2].starred,true);
  assert.equal(run("extractDocumentOutline('\\\\section{Unclosed').length"),0);
  context.testEditor.setValue(context.outlineSource);run("showCenter('edit');updateOutline();jumpToOutline(1)");
  assert.equal(context.testEditor.position.lineNumber,3);
  assert.match(get('outline').innerHTML,/&lt;script&gt;/);
  assert.doesNotMatch(get('outline').innerHTML,/<script>/);

  // Preferences apply to Monaco and persist, without touching source text.
  const beforePreferences=context.testEditor.getValue();
  get('prefFontSize').value='19';get('prefFontSize').listeners.get('change')();
  get('prefWordWrap').checked=false;get('prefWordWrap').listeners.get('change')();
  get('prefMinimap').checked=true;get('prefMinimap').listeners.get('change')();
  assert.equal(context.testEditor.options.fontSize,19);
  assert.equal(context.testEditor.options.wordWrap,'off');
  assert.equal(context.testEditor.options.minimap.enabled,true);
  assert.equal(context.testEditor.getValue(),beforePreferences);
  get('btnEditorReset').onclick();assert.equal(context.testEditor.options.wordWrap,'on');
  assert.equal(context.testEditor.options.minimap.enabled,false);
  assert.equal(context.testEditor.options.fontSize,15);

  // Statistics count Unicode characters and reflect cursor and selection positions.
  context.testEditor.setValue('你好 x\nabc');
  context.testEditor.position={lineNumber:2,column:3};
  context.testEditor.selection={getStartPosition:()=>({lineNumber:1,column:1}),getEndPosition:()=>({lineNumber:1,column:3})};
  run('updateEditorStatus()');assert.equal(get('sb-position').textContent,'行 2，列 3');
  assert.equal(get('sb-selection').textContent,'已选 2 字符');
  assert.equal(run("editorStatistics('😀汉 a').characters"),4);
  context.testEditor.selection=null;

  // A real command list filters, navigates, executes Monaco actions and restores focus.
  let restoredFocus=0;context.document.activeElement={isConnected:true,focus(){restoredFocus++;context.document.activeElement=this;}};
  context.imeShortcut={isComposing:true,metaKey:true,shiftKey:true,key:'P',preventDefault:()=>{throw new Error('IME shortcut intercepted');}};
  run('handleGlobalEditorKey(imeShortcut)');assert.equal(run('commandPaletteOpen'),false);
  context.commandShortcut={metaKey:true,shiftKey:true,key:'P',preventDefault(){},stopPropagation(){}};
  run('handleGlobalEditorKey(commandShortcut)');assert.equal(run('commandPaletteOpen'),true);
  const initialCommand=run('selectedCommand');run('moveCommandSelection(1)');
  assert.notEqual(run('selectedCommand'),initialCommand);
  get('commandInput').value='查找和替换';get('commandInput').listeners.get('input')();
  assert.equal(run('filteredCommands.length'),1);
  context.safariImeEnter={key:'Enter',isComposing:false,keyCode:229,preventDefault(){throw new Error('IME confirmation intercepted');}};
  const actionBeforeIme=context.testEditor.lastAction;
  run('handleGlobalEditorKey(safariImeEnter)');
  assert.equal(run('commandPaletteOpen'),true,'Safari IME confirmation keeps the command palette open');
  assert.equal(context.testEditor.lastAction,actionBeforeIme,'confirming Chinese text must not execute the selected command');
  await run('executeCommand()');assert.equal(context.testEditor.lastAction,'editor.action.startFindReplaceAction');
  assert.equal(run('commandPaletteOpen'),false);assert.equal(restoredFocus,1);
  const focusBeforeReopening=context.document.activeElement;
  run('openCommandPalette()');context.escapeCommand={key:'Escape',preventDefault(){},stopPropagation(){}};
  run('handleGlobalEditorKey(escapeCommand)');assert.equal(run('commandPaletteOpen'),false);
  assert.equal(context.document.activeElement,focusBeforeReopening,'Escape restores focus after an editor action has moved it');
  get('btnFind').onclick();assert.equal(context.testEditor.lastAction,'actions.find');
  assert.equal(get('tab-edit').getAttribute('role'),'tab');
  assert.equal(get('tab-edit').getAttribute('aria-selected'),'true');
  assert.match(html,/src="\/static\/brand\/texada-studio\.png"/);
  assert.match(html,/href="\/static\/brand\/texada-studio-favicon\.png"/);
  assert.match(html,/src="\/static\/editor\/latex\.js"/);
  assert.match(get('btnSave').innerHTML,/<svg[^>]+aria-hidden="true"/);

  // Cursor and selection updates reuse full-text statistics and outline for one model version.
  let statisticsScans=0,outlineScans=0;
  context.originalStatistics=run('editorStatistics');context.originalOutlineExtractor=run('extractDocumentOutline');
  context.countedStatistics=(...args)=>{statisticsScans++;return context.originalStatistics(...args);};
  context.countedOutline=(...args)=>{outlineScans++;return context.originalOutlineExtractor(...args);};
  run('editorStatistics=countedStatistics;extractDocumentOutline=countedOutline;');
  context.testEditor.setValue(String.raw`\section{Cache regression}`+'\nA longer document line.'.repeat(10000));
  run("showCenter('edit');updateOutline();updateEditorStatus();");
  for(let i=1;i<=30;i++){context.testEditor.position={lineNumber:i,column:1};run('updateEditorStatus();updateOutline();');}
  assert.equal(statisticsScans,1,'moving cursor must not rescan full text statistics');
  assert.equal(outlineScans,1,'moving cursor must not re-extract document outline');
  context.testEditor.setValue(String.raw`\section{Changed version}`);
  run('updateEditorStatus();updateOutline();updateEditorStatus();updateOutline();');
  assert.equal(statisticsScans,2,'edited model version must rebuild cached statistics once');
  assert.equal(outlineScans,2,'edited model version must rebuild outline once');
  run('editorStatistics=originalStatistics;extractDocumentOutline=originalOutlineExtractor;');

  get('sepE').listeners.get('mousedown')({ target: { closest: () => get('sepBtnE') }, preventDefault() { throw new Error('button started drag'); } });
  assert.equal(documentListeners.has('mousemove'), false);
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), true);
  assert.equal(get('previewPane').style.overflow, 'hidden');
  get('sepBtnE').onclick();
  assert.equal(get('previewPane').classList.contains('collapsed'), false);
  assert.equal(get('previewPane').style.width, '50%');
  get('sepBtnE').onclick();
  get('sepE').listeners.get('mousedown')({ preventDefault() {} });
  documentListeners.get('mousemove')({ clientX: 600 });
  documentListeners.get('mouseup')();
  assert.equal(get('previewPane').classList.contains('collapsed'), false);
  assert.notEqual(get('previewPane').style.overflow, 'hidden');
  assert.equal(get('previewPane').style.width, '40%');

  // Activity controls operate the actual navigator, editor actions and dialogs.
  function pressKey(key,extra={}) {
    const event={key,target:context.document.activeElement,defaultPrevented:false,
      preventDefault(){this.defaultPrevented=true;},stopPropagation(){},...extra};
    documentListeners.get('keydown')?.(event);return event;
  }
  context.window.innerWidth=1440;
  run("toggleAgentDrawer(false,null,false);toggleNavigator(true,null,false);toggleBottomPanel('log',false);showCenter('edit');");
  get('activityDocuments').click();
  assert.equal(get('sidebar').classList.contains('collapsed'),true);
  assert.equal(get('activityDocuments').getAttribute('aria-expanded'),'false');
  get('activityDocuments').click();
  assert.equal(get('sidebar').classList.contains('collapsed'),false);
  assert.equal(get('activityDocuments').getAttribute('aria-expanded'),'true');
  get('activityAgent').click();
  assert.equal(get('rightpanel').classList.contains('closed'),false);
  assert.equal(get('btnAgent').getAttribute('aria-expanded'),'true');
  assert.equal(get('rightpanel').style.width,'320px','legacy collapsed widths cannot survive an explicit open');
  get('btnAgent').click();
  assert.equal(get('rightpanel').classList.contains('closed'),true);
  get('activitySearch').click();
  assert.equal(context.testEditor.lastAction,'actions.find');
  get('activityOcr').click();
  assert.equal(get('importDialog').open,true,'OCR activity opens the usable import dialog');
  get('btnImportClose').click();assert.equal(get('importDialog').open,false);
  get('activitySettings').click();assert.equal(get('editorSettingsDialog').open,true);
  get('btnEditorDone').click();assert.equal(get('editorSettingsDialog').open,false);

  // Background checks update counts; only an explicit check expands problems.
  context.testEditor.setValue('check source');run("curName='check.tex';savedContent='check source';");
  context.analysisWire=async()=>({problems:[{type:'formula',line:3,status:'RETRY',latex:'x+'}],summary:{formula:1,table:0}});
  run('j=analysisWire;');
  await pageAnalyze({reveal:false});
  assert.equal(String(get('probCount').textContent),'1');
  assert.equal(get('bottom').classList.contains('collapsed'),true,'startup checks do not seize editor space');
  context.originalPageAnalyze=pageAnalyze;run('analyze=originalPageAnalyze');
  await get('btnAnalyze').click();
  assert.equal(get('bottom').classList.contains('collapsed'),false);
  assert.equal(get('problemsPane').classList.contains('hide'),false);
  assert.equal(get('btnProblems').getAttribute('aria-expanded'),'true');
  get('btnLog').click();
  assert.equal(get('logPane').classList.contains('hide'),false);
  assert.equal(get('problemsPane').classList.contains('hide'),true);
  assert.equal(get('btnLog').getAttribute('aria-expanded'),'true');
  assert.notEqual(get('bottom').style.height,'0px','opening logs discards obsolete zero-height preference');
  get('btnLog').click();assert.equal(get('bottom').classList.contains('collapsed'),true);

  // Failed and recovered runs leave readable activity after the toast disappears.
  context.failedFixWire=async url=>url.includes('/fixstatus?')
    ? {done:true,error:'fixture repair failed',log:['persistent failed-fix details']}
    : url.includes('/fix?')?{job:'f'.repeat(32)}:{jobs:[]};
  run('j=failedFixWire;');
  await pageFixHandler();
  assert.equal(run('busy'),false);
  assert.equal(get('bottom').classList.contains('collapsed'),false);
  assert.equal(get('logPane').classList.contains('hide'),false);
  assert.match(get('joblog').innerHTML,/persistent failed-fix details/);
  assert.match(get('joblog').innerHTML,/fixture repair failed/);
  context.failedHistoryWire=async()=>({done:true,error:'fixture historical failure',log:['persistent historical failure details']});
  run("j=failedHistoryWire;toggleBottomPanel('log',false);");
  await pageRestoreJob('e'.repeat(32),'check.tex');
  assert.equal(get('bottom').classList.contains('collapsed'),false);
  assert.equal(get('logPane').classList.contains('hide'),false);
  assert.match(get('joblog').innerHTML,/persistent historical failure details/);

  // Floating Agent review traps keyboard focus and restores the invoking control.
  context.window.innerWidth=900;
  get('btnAgent').focus();get('btnAgent').click();
  assert.equal(get('rightpanel').getAttribute('role'),'dialog');
  assert.equal(get('rightpanel').getAttribute('aria-modal'),'true');
  assert.equal(get('inspectorBackdrop').classList.contains('hide'),false);
  assert.equal(context.document.activeElement,get('btnInspectorClose'));
  const agentFocusable=run("workspaceFocusable($('rightpanel'))");
  assert.equal(agentFocusable[0],get('btnInspectorClose'));
  assert.equal(agentFocusable.at(-1),get('btnRefreshJobs'));
  agentFocusable.at(-1).focus();assert.equal(pressKey('Tab').defaultPrevented,true);
  assert.equal(context.document.activeElement,agentFocusable[0]);
  assert.equal(pressKey('Tab',{shiftKey:true}).defaultPrevented,true);
  assert.equal(context.document.activeElement,agentFocusable.at(-1));
  pressKey('Escape');
  assert.equal(get('rightpanel').classList.contains('closed'),true);
  assert.equal(get('inspectorBackdrop').classList.contains('hide'),true);
  assert.equal(context.document.activeElement,get('btnAgent'));
  get('activityAgent').focus();get('activityAgent').click();get('inspectorBackdrop').click();
  assert.equal(context.document.activeElement,get('activityAgent'),'backdrop returns to the actual activity trigger');

  // A mobile navigator can be dismissed without leaving a modal overlay over search.
  context.window.innerWidth=640;
  run('toggleNavigator(false,null,false)');
  get('activityDocuments').focus();get('activityDocuments').click();
  assert.equal(get('sidebar').getAttribute('role'),'dialog');
  assert.equal(get('navigatorBackdrop').classList.contains('hide'),false);
  const navFocusable=run("workspaceFocusable($('sidebar'))");
  navFocusable.at(-1).focus();pressKey('Tab');assert.equal(context.document.activeElement,navFocusable[0]);
  pressKey('Escape');
  assert.equal(get('sidebar').classList.contains('collapsed'),true);
  assert.equal(context.document.activeElement,get('activityDocuments'));
  get('activityDocuments').click();get('navigatorBackdrop').click();
  assert.equal(get('sidebar').classList.contains('collapsed'),true);
  assert.equal(context.document.activeElement,get('activityDocuments'));
  get('activityDocuments').click();get('activitySearch').click();
  assert.equal(get('navigatorBackdrop').classList.contains('hide'),true,'search never leaves a modal navigator above the Monaco find widget');
  assert.equal(get('sidebar').classList.contains('collapsed'),true);
  assert.equal(context.testEditor.lastAction,'actions.find');
  assert.equal(context.document.activeElement,get('editor'));

  // Mobile preview collapse removes its 340px baseline from the actual cascade.
  if(get('previewPane').classList.contains('collapsed'))get('btnTogglePreview').click();
  assert.equal(get('btnTogglePreview').getAttribute('aria-pressed'),'true');
  assert.equal(cssAt(get('previewPane'),640)['min-height'],'340px');
  get('btnTogglePreview').click();
  assert.equal(get('previewPane').classList.contains('collapsed'),true);
  const collapsedMobile=cssAt(get('previewPane'),640);
  assert.equal(collapsedMobile.display,'none','collapsed mobile preview cannot leave a blank layout item');
  assert.equal(collapsedMobile['min-height'],'0');
  assert.equal(collapsedMobile.height,'0');
  assert.equal(get('btnTogglePreview').getAttribute('aria-pressed'),'false');
  get('btnTogglePreview').click();
  assert.equal(get('previewPane').classList.contains('collapsed'),false);
  assert.equal(get('btnTogglePreview').getAttribute('aria-pressed'),'true');

  // Problem links dismiss floating review/navigation and focus the requested source line.
  get('activityAgent').click();
  context.testEditor.focused=false;
  const problemHandler=get('problems').innerHTML.match(/onclick="([^"]+)"/)?.[1];
  assert.ok(problemHandler,'rendered problem exposes a working line action');run(problemHandler);
  assert.equal(get('inspectorBackdrop').classList.contains('hide'),true);
  assert.equal(get('navigatorBackdrop').classList.contains('hide'),true);
  assert.equal(context.testEditor.position.lineNumber,3);
  assert.equal(context.testEditor.focused,true);
  assert.equal(context.document.activeElement,get('editor'));

  // Export menus dismiss on action, Escape and outside clicks; disabled PDF is inert.
  context.window.innerWidth=1440;
  context.testEditor.setValue('source for menu export');
  run("showCenter('edit');curName='menu.tex';invalidatePreview();toggleBottomPanel('log',false);");
  let menuDownload=null,menuFetches=0;
  context.captureMenuDownload=(name,blob)=>{menuDownload={name,blob};};run('download=captureMenuDownload');
  context.fetch=async()=>{menuFetches++;throw new Error('disabled PDF initiated a request');};
  get('btnExportMenu').focus();get('btnExportMenu').click();
  assert.equal(get('exportMenu').classList.contains('hide'),false);
  assert.equal(get('btnExportMenu').getAttribute('aria-expanded'),'true');
  assert.equal(context.document.activeElement,get('btnExport'));
  assert.equal(get('btnPdf').disabled,true);get('btnPdf').click();
  assert.equal(menuFetches,0);assert.equal(menuDownload,null);
  pressKey('ArrowDown');assert.equal(context.document.activeElement,get('btnExport'),'menu navigation skips disabled PDF');
  pressKey('Escape');
  assert.equal(get('exportMenu').classList.contains('hide'),true);
  assert.equal(context.document.activeElement,get('btnExportMenu'));
  get('btnExportMenu').click();get('btnCompile').focus();
  documentListeners.get('click')({target:get('btnCompile')});
  assert.equal(get('exportMenu').classList.contains('hide'),true);
  assert.equal(context.document.activeElement,get('btnCompile'),'outside dismissal preserves the newly clicked focus');
  get('btnExportMenu').focus();get('btnExportMenu').click();await get('btnExport').click();
  assert.equal(get('exportMenu').classList.contains('hide'),true);
  assert.equal(context.document.activeElement,get('btnExportMenu'));
  assert.equal(menuDownload.name,'menu.tex');assert.equal(await menuDownload.blob.text(),'source for menu export');

  // Command capability is independent of closed drawers, details and proxy menus.
  run("toggleAgentDrawer(false,null,false);closeWorkspaceMenu(false);");
  assert.equal(visible(get('btnFix')),false);
  assert.equal(run("commandEnabled(EDITOR_COMMANDS.find(command=>command.id==='document.fix'))"),true);
  assert.equal(visible(get('btnEditorSettings')),false);
  run('openCommandPalette()');get('commandInput').value='编辑器设置';get('commandInput').listeners.get('input')();
  await run('executeCommand()');assert.equal(get('editorSettingsDialog').open,true);
  get('btnEditorDone').click();
  run("setPdfAvailable(false);openCommandPalette()");get('commandInput').value='导出 PDF';get('commandInput').listeners.get('input')();
  assert.equal(run('filteredCommands.length'),1);
  assert.equal(run('commandEnabled(filteredCommands[0])'),false);
  await run('executeCommand()');assert.equal(menuFetches,0,'command palette respects unavailable PDF capability');
  run('closeCommandPalette()');

  // Visible model state has three outcomes, and draft probing never changes active status.
  context.activeConfig={base_url:'http://127.0.0.1:8080/v1',model:'MiniCPM-V-4.7-1B',local_mode:true,tools:{tectonic:true,pdftoppm:true}};
  for(const [available,state,label] of [[null,'unchecked','未检查'],[true,'connected','已连接'],[false,'disconnected','未连接']]) {
    context.connectionState=available;run('displayConfig({...activeConfig,model_available:connectionState})');
    assert.equal(get('modelIndicator').dataset.state,state);
    assert.match(get('modelConnectionStatus').textContent,new RegExp(label));
    assert.equal(visible(get('modelConnectionStatus')),true,'connection status is readable without assistive-only text');
    const background=cssAt(get('modelIndicator'),1440).background;
    if(state==='connected')assert.equal(background,'var(--success)');
    else if(state==='disconnected')assert.equal(background,'var(--warning)');
    else assert.notEqual(background,'var(--success)','unchecked connection never presents a success color');
  }
  run('displayConfig({...activeConfig,model_available:true})');
  const activeLabel=get('sb-model').textContent;
  get('modelBaseUrl').value='http://127.0.0.1:9000/v1';get('modelName').value='unrelated-draft-model';
  context.unrelatedProbeWire=async()=>({model_available:false,message:'draft service unavailable'});run('j=unrelatedProbeWire');
  await get('btnTestModel').onclick();
  assert.equal(get('sb-model').textContent,activeLabel);
  assert.equal(get('modelIndicator').dataset.state,'connected','a failed draft probe does not downgrade a different active model');
  assert.match(get('modelConnectionStatus').textContent,/已连接/);
  assert.equal(run('studioConfig.model'),'MiniCPM-V-4.7-1B');
  for(const node of domNodes)assert.doesNotMatch(node.textContent+node.innerHTML,/PRIVATE-(?:HOST|PLATFORM)-SENTINEL/);

  assert.match(html, /<script src="\/static\/monaco\/0\.52\.2\/min\/vs\/loader\.js"><\/script>/);
  assert.equal(loaderConfig.paths.vs, '/static/monaco/0.52.2/min/vs');
  assert.doesNotMatch(script, /MonacoEnvironment|getWorkerUrl|cdn\.jsdelivr/);
  assert.match(html, /<link rel="stylesheet" href="\/static\/editor\/studio\.css">/);
  assert.match(stylesheet, /\.hide\s*\{\s*display:\s*none\s*!important;/);
  assert.match(stylesheet, /#previewPane\.collapsed\s*\{[^}]*padding:\s*0\s*!important;/);
  console.log('PASS: pinned local Monaco; all prior review/race/source/PDF guards; OCR request/review lifecycle, cancellation, stale results and retry; outline/preferences/statistics/cache; closed-by-default Agent/problems/log; activity actions; automatic candidate review; explicit/background checks; durable failure/history logs; mobile drawer/navigation Tab/Escape/backdrop/problem focus; mobile search reachability; collapsed mobile preview CSS cascade; export menu dismissal/disabled capability; commands behind closed panels; visible three-state model status and isolated draft probing; no device identifiers; brand assets and critical CSS.');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => clearTimeout(testWatchdog));
