/* Offline tests of the shipped LaTeX configuration and completion provider. */
"use strict";
const assert = require("node:assert/strict");
const latex = require("./static/editor/latex.js");

function fakeMonaco(registered = []) {
  const calls = [], definitions = new Map(), registry = registered.slice();
  const disposable = method => ({dispose() { calls.push(["dispose",method]); }});
  return {calls,definitions,languages:{
    CompletionItemKind:{Snippet:27}, CompletionItemInsertTextRule:{InsertAsSnippet:4},
    getLanguages:() => registry,
    register(value) { calls.push(["register",value]); registry.push(value); return {dispose() {
      calls.push(["dispose","register"]); registry.splice(registry.indexOf(value),1);
    }}; },
    setMonarchTokensProvider(id,value) { calls.push(["tokens",id]); definitions.set("tokens",value); return disposable("tokens"); },
    setLanguageConfiguration(id,value) { calls.push(["configuration",id]); definitions.set("configuration",value); return disposable("configuration"); },
    registerCompletionItemProvider(id,value) { calls.push(["completion",id]); definitions.set("completion",value); return disposable("completion"); }
  }};
}

const monaco = fakeMonaco();
const first = latex.install(monaco);
assert.equal(latex.install(monaco),first,"installation is idempotent per editor instance");
assert.deepEqual(monaco.calls.map(call => call[0]),["register","tokens","configuration","completion"]);
assert.equal(monaco.calls[0][1].id,"latex");
assert.ok(monaco.calls[0][1].extensions.includes(".tex"));
assert.equal(first.snippetCount,latex.snippets.length);
const preinstalled = fakeMonaco([{id:"latex"}]);
latex.install(preinstalled);
assert.equal(preinstalled.calls.filter(call => call[0] === "register").length,0,"existing LaTeX registration is preserved");
assert.throws(() => latex.install({}),/loaded Monaco/);

const config = monaco.definitions.get("configuration");
assert.equal(config.comments.lineComment,"%");
assert.deepEqual(config.brackets,[["{","}"],["[","]"],["(",")"]]);
assert.equal(config.autoClosingPairs.find(pair => pair.open === "{").close,"}");
assert.ok(config.autoClosingPairs.every(pair => pair.notIn.includes("comment")));
assert.ok(!config.autoClosingPairs.some(pair => pair.open === "$"),"typing display dollars is not interrupted by single-dollar auto closing");
assert.ok(config.surroundingPairs.some(pair => pair.open === "\\[" && pair.close === "\\]"));
assert.equal(config.indentationRules.increaseIndentPattern.test("\\begin{equation} % note"),true);
assert.equal(config.indentationRules.decreaseIndentPattern.test("  \\end{equation}"),true);
assert.equal(config.folding.markers.start.test("% region formula"),true);
assert.equal(config.folding.markers.end.test("% endregion"),true);
assert.deepEqual("\\operatorname x_1 12.5".match(new RegExp(config.wordPattern,"g")),["\\operatorname","x_1","12.5"]);

function model(text) { const lines=text.split("\n"); return {getLineContent:number => lines[number-1]}; }
const provider = monaco.definitions.get("completion");
function complete(text,lineNumber,column) {
  return provider.provideCompletionItems(model(text),{lineNumber,column}).suggestions;
}
function named(suggestions,label) { return suggestions.find(item => item.label === label); }
let suggestion = named(complete("\\fr",1,4),"\\frac");
assert.deepEqual(suggestion.range,{startLineNumber:1,endLineNumber:1,startColumn:1,endColumn:4});
assert.equal(suggestion.insertText,"\\frac{${1:numerator}}{${2:denominator}}$0");
assert.equal(suggestion.kind,27);
assert.equal(suggestion.insertTextRules,4);
assert.equal(suggestion.filterText,"\\frac");
suggestion = named(complete("prefix \\frac suffix",1,11),"\\frac");
assert.deepEqual(suggestion.range,{startLineNumber:1,endLineNumber:1,startColumn:8,endColumn:13},"mid-command completion replaces its suffix too");
const original="prefix \\frac suffix";
assert.equal(original.slice(0,suggestion.range.startColumn-1)+"\\frac{a}{b}"+original.slice(suggestion.range.endColumn-1),"prefix \\frac{a}{b} suffix");
suggestion = named(complete("甲🙂 \\sq",1,8),"\\sqrt");
assert.equal(suggestion.range.startColumn,5,"Monaco columns use JavaScript UTF-16 offsets");
assert.equal(suggestion.range.endColumn,8);
suggestion = named(complete("intro\n  frac",2,7),"\\frac");
assert.deepEqual(suggestion.range,{startLineNumber:2,endLineNumber:2,startColumn:3,endColumn:7});
assert.equal(suggestion.filterText,"frac");
assert.ok(named(complete("\\",1,2),"\\begin{equation}"));
assert.ok(named(complete("\\begin",1,7),"\\begin{align}"));
assert.equal(complete("% \\frac",1,9).length,0,"comments do not open local snippets");
assert.ok(named(complete("\\% \\fr",1,8),"\\frac"),"escaped percent is not a comment");
assert.equal(complete("\\\\% \\fr",1,9).length,0,"a percent after a literal double slash starts a comment");
assert.equal(complete("\\doesnotexist",1,14).length,0);
suggestion = named(complete("\\alp",1,5),"\\alpha");
assert.equal(suggestion.insertText,"\\alpha$0","symbol snippets stay plain insertions");
suggestion = named(complete("\\the",1,5),"\\begin{theorem}");
assert.equal(suggestion.detail,"定理环境 · amsthm");
assert.ok(named(complete("\\bmat",1,6),"\\begin{bmatrix}"));
assert.ok(named(complete("\\eq",1,4),"\\eqref"));

// Check every environment from actual snippet bodies, after expanding defaults.
// This catches a mismatched \end even when the completion registration succeeds.
function expandDefaults(text) {
  return text.replace(/\$\{\d+:([^{}]*(?:\\[A-Za-z]+[^{}]*)?)\}/g,"$1").replace(/\$\d+/g,"");
}
const required = ["section","subsection","equation","align","frac","sqrt","int","sum","table","figure",
  "theorem","definition","lemma","remark","proof","titleblock","abstract","toc","usepackage","bmatrix","vmatrix",
  "eqref","cite","footnote","text","mathrm","mathbb","mathcal","mathbf","hat","bar","vec","overline","underbrace",
  "binom","prod","left-paren","left-brace","alpha","theta","pi","omega","Gamma","Delta","partial","nabla","infty",
  "leq","geq","neq","in","forall"];
for (const name of required) assert.ok(latex.snippets.some(snippet => snippet.name === name),name+" is available locally");
for (const snippet of latex.snippets) {
  assert.ok(snippet.body.includes("$0"),snippet.name+" has a final cursor stop");
  assert.ok(Object.isFrozen(snippet));
  const body=expandDefaults(snippet.body), stack=[];
  for (const match of body.matchAll(/\\(begin|end)\{([^}]+)\}/g)) {
    if (match[1] === "begin") stack.push(match[2]);
    else assert.equal(stack.pop(),match[2],snippet.name+" environment wrappers match");
  }
  assert.deepEqual(stack,[],snippet.name+" closes all environments");
  const markers=[...snippet.body.matchAll(/\$\{(\d+):/g)].map(match => Number(match[1]));
  assert.equal(new Set(markers).size,markers.length,snippet.name+" has distinct editable fields");
  if (markers.length) assert.deepEqual(markers,[...Array(Math.max(...markers))].map((_,index) => index+1),snippet.name+" Tab order is sequential");
}
assert.match(latex.snippets.find(snippet => snippet.name === "align").body,/\\\\\n/);
assert.match(latex.snippets.find(snippet => snippet.name === "table").body,/\\end\{tabular\}[\s\S]*\\end\{table\}/);

// Exercise the shipped Monarch rules with a small generic line driver. It is
// intentionally not a second LaTeX grammar: all matching rules come from the
// exact object handed to Monaco above.
const grammar=monaco.definitions.get("tokens");
function flattened(state) {
  return grammar.tokenizer[state].flatMap(rule => rule.include ? flattened(rule.include.slice(1)) : [rule]);
}
function tokenize(text) {
  const states=["root"], tokens=[];
  for (const line of text.split("\n")) {
    let offset=0;
    while(offset < line.length) {
      let matched=false;
      for (const [expression,action] of flattened(states.at(-1))) {
        const match=new RegExp("^(?:"+expression.source+")",expression.flags).exec(line.slice(offset));
        if (!match || !match[0].length) continue;
        const actions=Array.isArray(action) ? action : [action];
        if (Array.isArray(action)) assert.equal(match.slice(1).join(""),match[0],"group tokens cover their matched source");
        actions.forEach((entry,index) => {
          const value=Array.isArray(action) ? match[index+1] : match[0];
          const token=typeof entry === "string" ? entry : entry.token;
          if (token) tokens.push({value,token});
          if (entry && entry.next) {
            if (entry.next === "@pop") { assert.ok(states.length > 1); states.pop(); }
            else states.push(entry.next.slice(1));
          }
        });
        offset += match[0].length;
        matched=true;
        break;
      }
      if (!matched) offset++;
    }
  }
  return {tokens,states};
}
let highlighted=tokenize("\\section{Title} % comment\n$x^2 + \\frac{1}{2}$");
assert.ok(highlighted.tokens.some(token => token.value === "\\section" && token.token === "keyword"));
assert.ok(highlighted.tokens.some(token => token.value === "% comment" && token.token === "comment"));
assert.ok(highlighted.tokens.some(token => token.value === "2" && token.token === "number"));
assert.ok(highlighted.tokens.some(token => token.value === "\\frac" && token.token === "keyword"));
assert.deepEqual(highlighted.states,["root"]);
for (const [open,close] of [["$$","$$"],["\\[","\\]"],["\\(","\\)"]]) {
  highlighted=tokenize(open+"x+\n\\sqrt{y}"+close);
  assert.deepEqual(highlighted.states,["root"],open+" math state closes");
  assert.ok(highlighted.tokens.some(token => token.value === "x" && token.token === "string"));
}
highlighted=tokenize("\\begin{align}\nx &= 1 \\\\\ny &= 2\n\\end{align}");
assert.deepEqual(highlighted.states,["root"]);
assert.ok(highlighted.tokens.some(token => token.value === "\\begin{align}" && token.token === "tag"));
assert.ok(highlighted.tokens.some(token => token.value === "&" && token.token === "operator"));
highlighted=tokenize("\\begin{verbatim}\n$x$ % literal\n\\end{verbatim}\n\\% real text");
assert.ok(!highlighted.tokens.some(token => token.token === "delimiter.math"));
assert.ok(!highlighted.tokens.some(token => token.token === "comment"));
assert.deepEqual(highlighted.states,["root"]);
highlighted=tokenize("\\begin{comment}\n$x$\n\\end{comment}\n$y$");
assert.equal(highlighted.tokens.filter(token => token.token === "delimiter.math").length,2);
assert.deepEqual(highlighted.states,["root"]);

first.dispose(); first.dispose();
assert.deepEqual(monaco.calls.filter(call => call[0] === "dispose").map(call => call[1]),["completion","configuration","tokens","register"]);
assert.notEqual(latex.install(monaco),first,"disposal permits a fresh installation");
console.log(`LaTeX language configuration, tokenizer, ${latex.snippets.length} local snippets, completion ranges and idempotence passed.`);
