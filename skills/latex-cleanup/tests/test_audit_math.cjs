#!/usr/bin/env node
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const crypto=require('node:crypto');
const {extract,linesAndCode,escaped,parseArgs,normalizeAliases,run}=require('../scripts/audit_math.cjs');
let checks=0;
function check(text, contents, unmatched=0) {
  const x=extract(text);
  assert.deepEqual(x.formulas.map(f=>f.content),contents);
  assert.equal(x.unmatched.length,unmatched);
  for(const f of x.formulas){const size=f.display?2:1;assert.equal(text.slice(f.start+size,f.end-size),f.content);}
  checks++;
}
check('Paragraph $x$ then $$y\n+z$$.',['x','y\n+z']);
check('`$code$` and $x$',['x']);
check('```text\n$x$\n```\n$y$',['y']);
check('~~~\n$x$\n~~~\n$y$',['y']);
check('\\$5 and $x$',['x']);
check('\\\\$x$',['x']);
check('$x\ny$ ',[],2);
check('$$x',[],1);
check('<td>$x$</td>',['x']);
check('```\n$x$',[]);
check('`code``inner $x$` and $y$',['y']);
check('``code```inner $x$`` and $y$',['y']);
check('`code\n$x$\nend` and $y$',['y']);
check('``code\r\n$x$\r\nend`` and $y$',['y']);
check('`unclosed $x$\n\nend` and $y$',['x','y']);
check('`open $x$\n```\n$z$\n```\n`close $y$',['x','y']);
check('`$x$\\` and $y$',['y']);
check('\\` $x$',['x']);
const mapped='Prefix\n`code\r\n$x$\r\nend` and $y$';
assert.equal(extract(mapped).formulas[0].line,4);checks++;
assert.equal(linesAndCode(mapped).masked.length,mapped.length);checks++;
assert.deepEqual([...linesAndCode(mapped).masked.matchAll(/[\r\n]/g)].map(m=>m.index),[...mapped.matchAll(/[\r\n]/g)].map(m=>m.index));checks++;
assert.equal(extract('one\n$x$\n\n$$\nz\n$$').formulas[1].line,4);checks++;
assert.equal(escaped('\\\\\\$',3),true);checks++;
assert.throws(()=>parseArgs([]),/required/);checks++;
assert.deepEqual(parseArgs(['--manifest','a','--outdir','b']),{manifest:'a',outdir:'b'});checks++;
assert.deepEqual(normalizeAliases('x\\sp{2} + y\\sb{1} + \\hdots'),{normalized:'x^{2} + y_{1} + \\ldots',rules:['sp','sb','hdots']});checks++;
assert.deepEqual(normalizeAliases('\\sparse \\spectrum \\hdotsfor{3}'),{normalized:'\\sparse \\spectrum \\hdotsfor{3}',rules:[]});checks++;
assert.deepEqual(normalizeAliases('\\\\sp'),{normalized:'\\\\sp',rules:[]});checks++;
assert.deepEqual(normalizeAliases('\\\\\\sp'),{normalized:'\\\\^',rules:['sp']});checks++;
assert.deepEqual(normalizeAliases('\\operatorname{span}'),{normalized:'\\operatorname{span}',rules:[]});checks++;
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'latex-cleanup-audit-'));
try {
  const source=path.join(temp,'source.md'), manifest=path.join(temp,'manifest.json'), modulePath=path.join(temp,'fake-katex.cjs');
  const original=Buffer.from('`code``inner $x\\sp 2$` and $y$\n');
  fs.writeFileSync(source,original);
  fs.writeFileSync(modulePath,"module.exports={version:'test',renderToString:()=>''};\n");
  const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
  const book={id:'Book',source:'source.md',source_sha256:hash(original)};
  const prepare=books=>fs.writeFileSync(manifest,JSON.stringify({books}));
  const args=outdir=>({manifest,outdir,'katex-module':modulePath});
  prepare([book,{...book,id:'book'}]);
  let out=path.join(temp,'case-collision');
  assert.throws(()=>run(args(out)),/case-insensitively unique/);assert.equal(fs.existsSync(out),false);checks++;
  prepare([book,{...book,id:'LateFailure',source_sha256:'0'.repeat(64)}]);
  out=path.join(temp,'invalid-source');
  assert.throws(()=>run(args(out)),/SHA256 differs/);assert.equal(fs.existsSync(out),false);checks++;
  prepare([{...book,source:'missing.md'}]);
  out=path.join(temp,'missing-source');
  assert.throws(()=>run(args(out)),/ENOENT/);assert.equal(fs.existsSync(out),false);checks++;
  const invalid=Buffer.from([0xff]);fs.writeFileSync(path.join(temp,'invalid.md'),invalid);
  prepare([{...book,source:'invalid.md',source_sha256:hash(invalid)}]);
  out=path.join(temp,'invalid-utf8');
  assert.throws(()=>run(args(out)),/not valid UTF-8/);assert.equal(fs.existsSync(out),false);checks++;
  prepare([book]);out=path.join(temp,'existing');fs.mkdirSync(out);fs.writeFileSync(path.join(out,'keep.txt'),'keep');
  assert.throws(()=>run(args(out)),/must be new/);assert.equal(fs.readFileSync(path.join(out,'keep.txt'),'utf8'),'keep');checks++;
  out=path.join(temp,'successful');
  const savedLog=console.log;let result;
  try {console.log=()=>{};result=run(args(out));} finally {console.log=savedLog;}
  assert.equal(result.totals.formula_count,1);assert.equal(result.status,'completed');assert.deepEqual(fs.readFileSync(source),original);checks++;
  assert.throws(()=>run(args(out)),/must be new/);checks++;
} finally {fs.rmSync(temp,{recursive:true,force:true});}
console.log(JSON.stringify({checks,passed:true}));
