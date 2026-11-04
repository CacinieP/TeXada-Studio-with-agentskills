/* Offline tests of the shipped document templates. */
"use strict";
const assert = require("node:assert/strict");
const templates = require("./static/editor/templates.js");

assert.equal(typeof templates.list, "function");
assert.equal(typeof templates.defaultContent, "function");
assert.ok(Object.isFrozen(templates), "the template API is frozen");

const list = templates.list();
const expectedIds = ["blank", "lecture-notes", "exam-paper", "beamer", "english-article"];
assert.equal(list.length, expectedIds.length, "exactly the shipped template families are offered");
assert.deepEqual(list.map(template => template.id), expectedIds);
assert.equal(new Set(list.map(template => template.id)).size, list.length, "template ids are unique");
assert.equal(new Set(list.map(template => template.name)).size, list.length, "template names are unique");
for (const template of list) {
  assert.ok(Object.isFrozen(template), template.id + " is frozen");
  assert.ok(template.id && template.name && template.description, template.id + " has catalog fields");
  assert.ok(template.description.length <= 40, template.id + " keeps a short description");
  assert.ok(template.content.endsWith("\n"), template.id + " ends with a newline");
  assert.match(template.content, /\\documentclass/, template.id + " declares a document class");
  assert.match(template.content, /\\begin\{document\}/, template.id + " starts a document");
  assert.doesNotMatch(template.content, /\\includegraphics|\\bibliography/, template.id + " stays self-contained without external files");
  const stack = [];
  for (const match of template.content.matchAll(/\\(begin|end)\{([^}]+)\}/g)) {
    if (match[1] === "begin") stack.push(match[2]);
    else assert.equal(stack.pop(), match[2], template.id + " environment wrappers match");
  }
  assert.deepEqual(stack, [], template.id + " closes all environments");
  const dollars = (template.content.match(/(?<!\\)\$/g) || []).length;
  assert.equal(dollars % 2, 0, template.id + " has paired inline math dollars");
}

const blank = list.find(template => template.id === "blank");
assert.equal(templates.defaultContent(), blank.content, "new documents start from the blank template");
assert.match(blank.content, /\\documentclass\[UTF8,fontset=fandol\]\{ctexart\}/, "blank keeps the local fandol starter document");

const lecture = list.find(template => template.id === "lecture-notes");
assert.match(lecture.content, /\\newtheorem\{theorem\}/, "lecture notes define theorem environments");
const exam = list.find(template => template.id === "exam-paper");
assert.doesNotMatch(exam.content, /\\documentclass.*exam/, "exam paper avoids the exam.cls dependency");
const beamer = list.find(template => template.id === "beamer");
assert.match(beamer.content, /\\begin\{frame\}/, "beamer template provides frames");
const english = list.find(template => template.id === "english-article");
assert.match(english.content, /\\documentclass(\[\w+\])?\{article\}/, "english article uses the article class");

console.log(`${list.length} document templates, structure, pairing and defaults passed.`);
