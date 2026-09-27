#!/usr/bin/env node
// Read-only KaTeX diagnostic of original MinerU Markdown. Never rewrites content.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
function parseArgs(argv) {
  const args={};
  for(let i=0;i<argv.length;i++) {
    if(!['--manifest','--outdir','--katex-module'].includes(argv[i])||!argv[i+1]) throw Error('Usage: audit_math.cjs --manifest FILE --outdir DIRECTORY [--katex-module PATH]');
    args[argv[i].slice(2)]=argv[++i];
  }
  if(!args.manifest||!args.outdir)throw Error('--manifest and --outdir are required');
  return args;
}
const sha = x => crypto.createHash('sha256').update(x).digest('hex');
const parameters = {throwOnError:true, strict:'ignore', trust:false, maxExpand:1000, maxSize:500};
const limitations = [
  'Lexical dollar-delimited extraction excludes fenced code and matched inline code spans, including spans across consecutive nonblank lines; escaped dollars are ignored. This is not a complete Markdown block parser. HTML table text is included.',
  'Inline dollars cannot cross a newline; display dollars can. Unmatched delimiters are counted separately. Other math dialects and completely missing math delimiters are not covered.',
  'KaTeX compatibility is not TeX compilation or mathematical/content correctness. Parse success does not establish fidelity to the source PDF.',
  'PDF page ranges come from MinerU original 20-page segment markers; the exact physical page of each formula is not inferred.',
  'Source fragments and absolute local paths are retained in local failure files only; sanitized summaries include hashes and locations without full OCR text.'
];
function escaped(text, i) {let n=0; while(i>0 && text[--i]==='\\') n++; return n%2===1;}
function linesAndCode(text) {
  const starts=[0], masked=text.split('');
  const proseRanges=[];
  let fence=null, proseStart=null;
  const finishProse=end=>{if(proseStart!==null){proseRanges.push([proseStart,end]);proseStart=null;}};
  for (let a=0;a<text.length;) {
    let b=text.indexOf('\n',a); if(b<0)b=text.length;
    const line=text.slice(a,b), m=/^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      for(let j=a;j<b;j++)masked[j]=' ';
      if(m && m[1][0]===fence[0] && m[1].length>=fence.length && !m[2].trim())fence=null;
    } else if(m && (m[1][0]!=='`'||!m[2].includes('`'))) {
      finishProse(a);
      fence=m[1];for(let j=a;j<b;j++)masked[j]=' ';
    } else if(!line.trim()) {
      finishProse(a);
    } else {
      if(proseStart===null)proseStart=a;
    }
    a=b+1;if(b<text.length)starts.push(a);
  }
  finishProse(text.length);
  for(const [start,end] of proseRanges) {
    const runs=[...text.slice(start,end).matchAll(/`+/g)].map(m=>({start:start+m.index,length:m[0].length}));
    // A longer run is not a closing delimiter. Index the next exact-length run,
    // allowing newlines inside a code span but never a blank line or code fence.
    const next=new Array(runs.length).fill(-1), last=new Map();
    for(let i=runs.length-1;i>=0;i--){next[i]=last.get(runs[i].length)??-1;last.set(runs[i].length,i);}
    for(let i=0;i<runs.length;i++) {
      if(escaped(text,runs[i].start)||next[i]<0)continue;
      const close=next[i], stop=runs[close].start+runs[close].length;
      for(let j=runs[i].start;j<stop;j++)if(text[j]!=='\n'&&text[j]!=='\r')masked[j]=' ';
      i=close;
    }
  }
  return {starts, masked:masked.join(''), unclosedCodeFence:!!fence};
}
function lineOf(starts, offset) {let lo=0,hi=starts.length;while(lo+1<hi){const mid=(lo+hi)>>1;if(starts[mid]<=offset)lo=mid;else hi=mid;}return lo+1;}
function extract(text) {
  const {starts,masked,unclosedCodeFence}=linesAndCode(text), formulas=[], unmatched=[];
  for(let i=0;i<masked.length;i++) {
    if(masked[i]!=='$'||escaped(masked,i))continue;
    const display=masked[i+1]==='$', size=display?2:1;
    let j=i+size, found=-1;
    for(;j<masked.length;j++) {
      if(!display&&masked[j]==='\n')break;
      if(masked[j]==='$'&&!escaped(masked,j)) {
        if(display&&masked[j+1]==='$'){found=j;break;}
        if(!display){found=j;break;}
      }
    }
    if(found<0){unmatched.push({line:lineOf(starts,i),kind:display?'display':'inline',offset:i});i+=size-1;continue;}
    formulas.push({start:i,end:found+size,content:text.slice(i+size,found),display,line:lineOf(starts,i),end_line:lineOf(starts,found+size-1)});
    i=found+size-1;
  }
  return {formulas,unmatched,unclosedCodeFence,starts};
}
function typeOf(error) {
  const e=error.replace(/^KaTeX parse error: /,'');
  if(/Undefined control sequence/.test(e))return 'undefined_control_sequence';
  if(/Expected.*got/.test(e))return 'expected_token';
  if(/No such environment/.test(e))return 'unsupported_environment';
  if(/Double superscript/.test(e))return 'double_superscript';
  if(/Double subscript/.test(e))return 'double_subscript';
  if(/Too many expansions/.test(e))return 'macro_expansion_limit';
  if(/Extra alignment tab/.test(e))return 'extra_alignment_tab';
  if(/Unexpected character/.test(e))return 'unexpected_character';
  if(/Invalid size/.test(e))return 'invalid_size';
  return e.split(/ at position| at end/)[0];
}
function normalizeAliases(formula) {
  const rules=[];
  const normalized=formula.replace(/\\([A-Za-z]+|.)/gs,(token,command)=>{
    if(!['sp','sb','hdots'].includes(command))return token;
    rules.push(command);return {sp:'^',sb:'_',hdots:'\\ldots'}[command];
  });
  return {normalized,rules};
}
function run(args) {
const out=path.resolve(args.outdir), manifestPath=path.resolve(args.manifest);
if(fs.existsSync(out))throw Error('Output directory must be new');
const inventory=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
if(!inventory||!Array.isArray(inventory.books)||!inventory.books.length)throw Error('Manifest requires a nonempty books array');
const ids=new Set(), inputs=[];
for(const b of inventory.books) {
  if(!b||typeof b.id!=='string'||!/^[-A-Za-z0-9_]+$/.test(b.id)||ids.has(b.id.toLowerCase())||typeof b.source!=='string'||!b.source||typeof b.source_sha256!=='string'||!/^([a-f0-9]{64})$/.test(b.source_sha256))throw Error('Each book requires a case-insensitively unique safe id, source and lowercase SHA256');
  ids.add(b.id.toLowerCase());
  const sourcePath=path.resolve(path.dirname(manifestPath),b.source);
  const stat=fs.lstatSync(sourcePath);
  if(!stat.isFile()||stat.isSymbolicLink())throw Error(b.id+': source must be a regular, non-symlink file');
  const bytes=fs.readFileSync(sourcePath), text=bytes.toString('utf8');
  if(sha(bytes)!==b.source_sha256)throw Error(b.id+': source SHA256 differs from manifest');
  if(!Buffer.from(text,'utf8').equals(bytes))throw Error(b.id+': source is not valid UTF-8');
  inputs.push({book:b,sourcePath,bytes,text});
}
const katex=require(args['katex-module'] ? path.resolve(args['katex-module']) : 'katex');
fs.mkdirSync(path.dirname(out),{recursive:true});
fs.mkdirSync(out);
const summaries=[],allTypes={},candidateSummary=[],start=Date.now();
for(const {book,sourcePath,bytes,text} of inputs) {
  const name=book.id;
  const parsed=extract(text), markers=[...text.matchAll(/<!-- 原 PDF 第 (\d+)-(\d+) 页 -->/g)].map(m=>({offset:m.index,start:Number(m[1]),end:Number(m[2]),line:lineOf(parsed.starts,m.index)}));
  let markerIndex=-1,failed=0;const byType={},failures=[],candidates=[],unique=new Set(),cache=new Map();
  const segments=markers.map(m=>({pdf_page_start:m.start,pdf_page_end:m.end,formula_count:0,passed:0,failed:0}));
  for(let i=0;i<parsed.formulas.length;i++) {
    const f=parsed.formulas[i];while(markerIndex+1<markers.length&&markers[markerIndex+1].offset<=f.start)markerIndex++;
    const seg=segments[markerIndex],key=(f.display?'D:':'I:')+f.content;unique.add(key);
    if(seg)seg.formula_count++;
    let error=cache.get(key);
    if(error===undefined) {
      try {katex.renderToString(f.content,{...parameters,displayMode:f.display});error=null;}catch(e){error=e.message;}
      cache.set(key,error);
    }
    if(error) {
      failed++;if(seg)seg.failed++;const type=typeOf(error);byType[type]=(byType[type]||0)+1;allTypes[type]=(allTypes[type]||0)+1;
      const failure={index:i+1,line:f.line,end_line:f.end_line,pdf_page_start:seg?.pdf_page_start??null,pdf_page_end:seg?.pdf_page_end??null,display:f.display,sha256:sha(f.content),type,error,formula:f.content,utf16_start:f.start,utf16_end:f.end,unicode_start:[...text.slice(0,f.start)].length,unicode_end:[...text.slice(0,f.end)].length,byte_start:Buffer.byteLength(text.slice(0,f.start)),byte_end:Buffer.byteLength(text.slice(0,f.end))};
      failures.push(failure);
      // Only established kernel/amsmath aliases. Never guess missing symbols.
      const {normalized,rules}=normalizeAliases(f.content);
      // Conservatively exclude documents/formulas that can redefine meanings, and
      // aliases in any formula with a text-mode command. No implicit math-mode guess.
      const redefinition=/\\(?:newcommand|renewcommand|providecommand|def|gdef|edef|xdef|let)\b/.test(text);
      const textMode=/\\(?:text[a-zA-Z]*|mbox|hbox|verb)\b/.test(f.content);
      if(rules.length&&!redefinition&&!textMode) {
        let afterError=null;try{katex.renderToString(normalized,{...parameters,displayMode:f.display});}catch(e){afterError=e.message;}
        if(!afterError) {
          const delimiter=f.display?'$$':'$';
          candidates.push({id:name+'-formula-'+(i+1),source_sha256:sha(bytes),line:f.line,end_line:f.end_line,pdf_page_start:seg?.pdf_page_start??null,pdf_page_end:seg?.pdf_page_end??null,utf16_start:failure.utf16_start,utf16_end:failure.utf16_end,unicode_start:failure.unicode_start,unicode_end:failure.unicode_end,byte_start:failure.byte_start,byte_end:failure.byte_end,old:delimiter+f.content+delimiter,new:delimiter+normalized+delimiter,rules,before_error:error,after_katex:'passed',source_semantics:'kernel/amsmath math aliases only; no source PDF correctness claim'});
        }
      }
    } else if(seg)seg.passed++;
  }
  const summary={book:name,title:book.title??name,source_sha256:sha(bytes),matches_inventory_sha256:sha(bytes)===book.source_sha256,formula_count:parsed.formulas.length,unique_formulas:unique.size,passed:parsed.formulas.length-failed,failed,failures_by_type:byType,unmatched_delimiters:parsed.unmatched.map(({line,kind})=>({line,kind})),unclosed_code_fence:parsed.unclosedCodeFence,pdf_pages:book.pdf_pages??null,segments};
  summaries.push(summary);
  candidateSummary.push({book:name,source_sha256:sha(bytes),eligible_formulas:candidates.length,replacement_tokens:candidates.reduce((n,c)=>n+c.rules.length,0)});
  fs.writeFileSync(path.join(out,name+'-alias-candidates.local.json'),JSON.stringify({book:name,source:sourcePath,source_sha256:sha(bytes),offset_convention:'0-based half-open. utf16 offsets index JavaScript strings; unicode offsets count code points; byte offsets count UTF-8 bytes. old/new include math delimiters.',candidates},null,2)+'\n');
  fs.writeFileSync(path.join(out, name+'-formula-failures.local.json'),JSON.stringify({book:name,source:sourcePath,source_sha256:summary.source_sha256,failures,unmatched:parsed.unmatched},null,2)+'\n');
  fs.writeFileSync(path.join(out,'formula-summary.json'),JSON.stringify({version:1,status:'running',renderer:'KaTeX '+katex.version,parameters,limitations,books:summaries},null,2)+'\n');
  console.log(JSON.stringify({book:name,formulas:summary.formula_count,failed,unmatched:parsed.unmatched.length,elapsed_seconds:+((Date.now()-start)/1000).toFixed(1)}));
}
const sum=k=>summaries.reduce((a,b)=>a+b[k],0);
const final={version:1,status:'completed',renderer:'KaTeX '+katex.version,parameters,limitations,totals:{books:summaries.length,formula_count:sum('formula_count'),unique_per_book_sum:sum('unique_formulas'),passed:sum('passed'),failed:sum('failed'),books_with_failures:summaries.filter(b=>b.failed).length,unmatched_delimiters:summaries.reduce((a,b)=>a+b.unmatched_delimiters.length,0),source_hashes_match_inventory:summaries.every(b=>b.matches_inventory_sha256),elapsed_seconds:+((Date.now()-start)/1000).toFixed(1)},failures_by_type:allTypes,books:summaries};
fs.writeFileSync(path.join(out,'formula-summary.json'),JSON.stringify(final,null,2)+'\n');
console.log(JSON.stringify(final.totals));
fs.writeFileSync(path.join(out,'alias-candidate-summary.json'),JSON.stringify({policy:'Only sp->^, sb->_, hdots->ldots. Candidates must parse after replacement, contain no text-mode commands, and belong to sources without macro definitions. No files changed.',totals:{formulas:candidateSummary.reduce((n,c)=>n+c.eligible_formulas,0),replacement_tokens:candidateSummary.reduce((n,c)=>n+c.replacement_tokens,0)},books:candidateSummary},null,2)+'\n');
return final;
}
module.exports={extract,linesAndCode,escaped,typeOf,run,parseArgs,normalizeAliases};
if(require.main===module){try{run(parseArgs(process.argv.slice(2)));}catch(e){console.error(e.message);process.exitCode=1;}}
