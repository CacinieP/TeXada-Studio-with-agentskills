/* Local LaTeX editing support for Monaco. No model or network requests. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TeXadaLatex = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const installations = new WeakMap();
  const lines = parts => parts.join("\n");
  const snippets = Object.freeze([
    {name:"section", label:"\\section", detail:"章节标题", prefixes:["section", "sec"], body:"\\section{${1:Title}}\n$0"},
    {name:"subsection", label:"\\subsection", detail:"小节标题", prefixes:["subsection", "subsec"], body:"\\subsection{${1:Title}}\n$0"},
    {name:"subsubsection", label:"\\subsubsection", detail:"三级标题", prefixes:["subsubsection"], body:"\\subsubsection{${1:Title}}\n$0"},
    {name:"equation", label:"\\begin{equation}", detail:"编号公式 · amsmath", prefixes:["equation", "eq", "begin"], body:lines([
      "\\begin{equation}", "\t${1:x = y}", "\\end{equation}", "$0"
    ])},
    {name:"equation-star", label:"\\begin{equation*}", detail:"无编号公式 · amsmath", prefixes:["equation*", "eqstar", "begin"], body:lines([
      "\\begin{equation*}", "\t${1:x = y}", "\\end{equation*}", "$0"
    ])},
    {name:"align", label:"\\begin{align}", detail:"多行对齐公式 · amsmath", prefixes:["align", "begin"], body:lines([
      "\\begin{align}", "\t${1:a} &= ${2:b} \\\\", "\t${3:c} &= ${4:d}", "\\end{align}", "$0"
    ])},
    {name:"align-star", label:"\\begin{align*}", detail:"无编号对齐公式 · amsmath", prefixes:["align*", "alignstar", "begin"], body:lines([
      "\\begin{align*}", "\t${1:a} &= ${2:b} \\\\", "\t${3:c} &= ${4:d}", "\\end{align*}", "$0"
    ])},
    {name:"display", label:"\\[ … \\]", detail:"显示公式", prefixes:["display", "math"], body:lines(["\\[", "\t${1:x = y}", "\\]", "$0"])},
    {name:"frac", label:"\\frac", detail:"分式", prefixes:["frac"], body:"\\frac{${1:numerator}}{${2:denominator}}$0"},
    {name:"sqrt", label:"\\sqrt", detail:"平方根", prefixes:["sqrt"], body:"\\sqrt{${1:x}}$0"},
    {name:"nth-root", label:"\\sqrt[n]", detail:"n 次根", prefixes:["root", "nthroot"], body:"\\sqrt[${1:n}]{${2:x}}$0"},
    {name:"int", label:"\\int", detail:"定积分记号", prefixes:["int", "integral"], body:"\\int_{${1:a}}^{${2:b}} ${3:f(x)}\\,\\mathrm{d}${4:x}$0"},
    {name:"sum", label:"\\sum", detail:"求和记号", prefixes:["sum"], body:"\\sum_{${1:i=1}}^{${2:n}} ${3:a_i}$0"},
    {name:"lim", label:"\\lim", detail:"极限记号", prefixes:["lim", "limit"], body:"\\lim_{${1:x \\to 0}} ${2:f(x)}$0"},
    {name:"matrix", label:"\\begin{pmatrix}", detail:"矩阵 · amsmath", prefixes:["matrix", "pmatrix", "begin"], body:lines([
      "\\begin{pmatrix}", "\t${1:a} & ${2:b} \\\\", "\t${3:c} & ${4:d}", "\\end{pmatrix}$0"
    ])},
    {name:"cases", label:"\\begin{cases}", detail:"分段表达式 · amsmath", prefixes:["cases", "begin"], body:lines([
      "\\begin{cases}", "\t${1:x}, & ${2:x > 0} \\\\", "\t${3:0}, & ${4:x \\leq 0}", "\\end{cases}$0"
    ])},
    {name:"table", label:"\\begin{table}", detail:"表格、标题与引用标签", prefixes:["table", "tabular", "begin"], body:lines([
      "\\begin{table}[${1:htbp}]", "\t\\centering", "\t\\begin{tabular}{${2:ll}}", "\t\t\\hline",
      "\t\t${3:Heading 1} & ${4:Heading 2} \\\\", "\t\t\\hline", "\t\t${5:Value 1} & ${6:Value 2} \\\\",
      "\t\t\\hline", "\t\\end{tabular}", "\t\\caption{${7:Caption}}", "\t\\label{tab:${8:label}}", "\\end{table}", "$0"
    ])},
    {name:"figure", label:"\\begin{figure}", detail:"图片、标题与引用标签 · graphicx", prefixes:["figure", "fig", "begin"], body:lines([
      "\\begin{figure}[${1:htbp}]", "\t\\centering", "\t\\includegraphics[width=${2:0.8}\\linewidth]{${3:figure.pdf}}",
      "\t\\caption{${4:Caption}}", "\t\\label{fig:${5:label}}", "\\end{figure}", "$0"
    ])},
    {name:"itemize", label:"\\begin{itemize}", detail:"无序列表", prefixes:["itemize", "item", "begin"], body:lines([
      "\\begin{itemize}", "\t\\item ${1:First item}", "\t\\item ${2:Second item}", "\\end{itemize}", "$0"
    ])},
    {name:"enumerate", label:"\\begin{enumerate}", detail:"有序列表", prefixes:["enumerate", "enum", "begin"], body:lines([
      "\\begin{enumerate}", "\t\\item ${1:First item}", "\t\\item ${2:Second item}", "\\end{enumerate}", "$0"
    ])},
    {name:"document", label:"LaTeX document", detail:"本地新文档模板 · amsmath / graphicx", prefixes:["document", "article"], body:lines([
      "\\documentclass{${1:article}}", "\\usepackage{amsmath,amssymb,graphicx}", "", "\\begin{document}", "${2:Document text}", "", "\\end{document}", "$0"
    ])},
    {name:"label", label:"\\label", detail:"引用标签", prefixes:["label"], body:"\\label{${1:label}}$0"},
    {name:"ref", label:"\\ref", detail:"引用已有标签", prefixes:["ref"], body:"\\ref{${1:label}}$0"},
    {name:"textbf", label:"\\textbf", detail:"粗体文字", prefixes:["textbf", "bold"], body:"\\textbf{${1:text}}$0"},
    {name:"emph", label:"\\emph", detail:"强调文字", prefixes:["emph", "italic"], body:"\\emph{${1:text}}$0"}
  ].map(item => Object.freeze({...item, prefixes:Object.freeze(item.prefixes)})));

  const configuration = {
    comments:{lineComment:"%"},
    brackets:[["{","}"], ["[","]"], ["(",")"]],
    autoClosingPairs:[
      {open:"{",close:"}",notIn:["comment", "string"]},
      {open:"[",close:"]",notIn:["comment", "string"]},
      {open:"(",close:")",notIn:["comment", "string"]}
    ],
    surroundingPairs:[{open:"{",close:"}"}, {open:"[",close:"]"}, {open:"(",close:")"},
      {open:"$",close:"$"}, {open:"\\[",close:"\\]"}, {open:"\\(",close:"\\)"}],
    wordPattern:/\\[A-Za-z@]+\*?|[A-Za-z@][A-Za-z0-9_@]*|\d+(?:\.\d+)?/,
    indentationRules:{
      increaseIndentPattern:/\\begin\s*\{[^}]+\}(?:\[[^\]]*\])?\s*(?:%.*)?$/,
      decreaseIndentPattern:/^\s*\\end\s*\{[^}]+\}/
    },
    folding:{markers:{start:/^\s*%\s*(?:region|#region)\b/, end:/^\s*%\s*(?:endregion|#endregion)\b/}}
  };

  const monarch = {
    defaultToken:"", tokenPostfix:".latex",
    tokenizer:{
      root:[
        [/\s+/, ""],
        [/%.*$/, "comment"],
        [/\\verb\*?([^A-Za-z\s]).*?\1/, "string"],
        [/\\begin\s*\{comment\}/, {token:"comment",next:"@commentBlock"}],
        [/\\begin\s*\{(?:verbatim\*?|Verbatim\*?|lstlisting\*?|minted\*?)\}/, {token:"tag",next:"@verbatim"}],
        [/\\begin\s*\{(?:equation\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?|displaymath|math|eqnarray\*?)\}/, {token:"tag",next:"@mathEnvironment"}],
        [/\$\$/, {token:"delimiter.math",next:"@dollarDisplay"}],
        [/\$/, {token:"delimiter.math",next:"@dollarInline"}],
        [/\\\[/, {token:"delimiter.math",next:"@bracketMath"}],
        [/\\\(/, {token:"delimiter.math",next:"@parenMath"}],
        {include:"@commands"},
        [/[{}\[\]()]/, "delimiter.bracket"],
        [/[#&_^~]/, "operator"],
        [/\d+(?:\.\d+)?/, "number"],
        [/[^\\%$#&_^~{}\[\]()0-9]+/, ""]
      ],
      commands:[
        [/(\\(?:begin|end))(\s*\{)([^}]*)(\})/, ["keyword", "delimiter.bracket", "tag", "delimiter.bracket"]],
        [/\\[A-Za-z@]+\*?/, "keyword"],
        [/\\[^A-Za-z@\s]/, "keyword"],
        [/\\$/, "keyword"]
      ],
      math:[
        [/%.*$/, "comment"],
        {include:"@commands"},
        [/[{}\[\]()]/, "delimiter.bracket"],
        [/[&_^=+*/<>|:\-]/, "operator"],
        [/\d+(?:\.\d+)?/, "number"],
        [/[^\\%$&_^=+*/<>|:\-{}\[\]()0-9]+/, "string"],
        [/./, "string"]
      ],
      dollarInline:[[/\$/, {token:"delimiter.math",next:"@pop"}], {include:"@math"}],
      dollarDisplay:[[/\$\$/, {token:"delimiter.math",next:"@pop"}], {include:"@math"}],
      bracketMath:[[/\\\]/, {token:"delimiter.math",next:"@pop"}], {include:"@math"}],
      parenMath:[[/\\\)/, {token:"delimiter.math",next:"@pop"}], {include:"@math"}],
      mathEnvironment:[
        [/\\end\s*\{(?:equation\*?|align\*?|alignat\*?|flalign\*?|gather\*?|multline\*?|displaymath|math|eqnarray\*?)\}/, {token:"tag",next:"@pop"}],
        {include:"@math"}
      ],
      verbatim:[
        [/\\end\s*\{(?:verbatim\*?|Verbatim\*?|lstlisting\*?|minted\*?)\}/, {token:"tag",next:"@pop"}],
        [/[^\\]+/, "string"], [/./, "string"]
      ],
      commentBlock:[[/\\end\s*\{comment\}/, {token:"comment",next:"@pop"}], [/[^\\]+/, "comment"], [/./, "comment"]]
    }
  };

  function escaped(text, offset) {
    let slashes = 0;
    while (offset > 0 && text[--offset] === "\\") slashes++;
    return slashes % 2 === 1;
  }

  function completionRange(model, position) {
    const line = model.getLineContent(position.lineNumber);
    const cursor = Math.max(0, Math.min(line.length, position.column - 1));
    let start = cursor, end = cursor;
    if (start > 0 && line[start - 1] === "*") start--;
    while (start > 0 && /[A-Za-z@]/.test(line[start - 1])) start--;
    if (start > 0 && line[start - 1] === "\\" && !escaped(line, start - 1)) start--;
    while (end < line.length && /[A-Za-z@]/.test(line[end])) end++;
    if (end < line.length && line[end] === "*") end++;
    return {range:{startLineNumber:position.lineNumber, endLineNumber:position.lineNumber,
      startColumn:start + 1, endColumn:end + 1}, prefix:line.slice(start,cursor)};
  }

  function inLineComment(model, position) {
    const line = model.getLineContent(position.lineNumber);
    for (let index = 0; index < Math.min(line.length,position.column - 1); index++) {
      if (line[index] === "%" && !escaped(line,index)) return true;
    }
    return false;
  }

  function completionProvider(monaco) {
    return {
      triggerCharacters:["\\"],
      provideCompletionItems(model, position) {
        if (inLineComment(model,position)) return {suggestions:[]};
        const {range,prefix} = completionRange(model,position);
        const slash = prefix.startsWith("\\"), query = prefix.replace(/^\\/,"").toLowerCase();
        const suggestions = [];
        snippets.forEach((snippet,index) => {
          const alias = snippet.prefixes.find(item => item.toLowerCase().startsWith(query));
          if (alias === undefined) return;
          suggestions.push({label:snippet.label, detail:snippet.detail,
            documentation:{value:"本地 LaTeX 片段；Tab 切换占位符。"},
            kind:monaco.languages.CompletionItemKind.Snippet,
            insertText:snippet.body, insertTextRules:monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
            filterText:(slash ? "\\" : "") + alias, sortText:String(index).padStart(3,"0"), range:{...range}});
        });
        return {suggestions};
      }
    };
  }

  function install(monaco) {
    if (!monaco || !monaco.languages || typeof monaco.languages.register !== "function"
        || typeof monaco.languages.setMonarchTokensProvider !== "function"
        || typeof monaco.languages.setLanguageConfiguration !== "function"
        || typeof monaco.languages.registerCompletionItemProvider !== "function") {
      throw new TypeError("TeXadaLatex.install requires a loaded Monaco editor.");
    }
    if (installations.has(monaco)) return installations.get(monaco);
    const languages = monaco.languages, disposables = [];
    try {
      if (!languages.getLanguages().some(language => language.id === "latex")) {
        disposables.push(languages.register({id:"latex", extensions:[".tex",".ltx",".sty",".cls"],
          aliases:["LaTeX","TeX","latex"], mimetypes:["text/x-tex","text/x-latex"]}));
      }
      disposables.push(languages.setMonarchTokensProvider("latex",monarch));
      disposables.push(languages.setLanguageConfiguration("latex",configuration));
      disposables.push(languages.registerCompletionItemProvider("latex",completionProvider(monaco)));
    } catch (error) {
      disposables.reverse().forEach(item => { if (item && typeof item.dispose === "function") item.dispose(); });
      throw error;
    }
    let disposed = false;
    const installation = Object.freeze({id:"latex", snippetCount:snippets.length, dispose() {
      if (disposed) return;
      disposed = true;
      disposables.reverse().forEach(item => { if (item && typeof item.dispose === "function") item.dispose(); });
      installations.delete(monaco);
    }});
    installations.set(monaco,installation);
    return installation;
  }

  return Object.freeze({install, snippets, configuration, monarch, completionRange});
});
