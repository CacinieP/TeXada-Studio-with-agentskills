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
    {name:"emph", label:"\\emph", detail:"强调文字", prefixes:["emph", "italic"], body:"\\emph{${1:text}}$0"},
    {name:"theorem", label:"\\begin{theorem}", detail:"定理环境 · amsthm", prefixes:["theorem", "thm", "begin"], body:lines([
      "\\begin{theorem}", "\t${1:定理内容}", "\\end{theorem}", "$0"
    ])},
    {name:"definition", label:"\\begin{definition}", detail:"定义环境 · amsthm", prefixes:["definition", "def", "begin"], body:lines([
      "\\begin{definition}", "\t${1:定义内容}", "\\end{definition}", "$0"
    ])},
    {name:"lemma", label:"\\begin{lemma}", detail:"引理环境 · amsthm", prefixes:["lemma", "begin"], body:lines([
      "\\begin{lemma}", "\t${1:引理内容}", "\\end{lemma}", "$0"
    ])},
    {name:"remark", label:"\\begin{remark}", detail:"备注环境 · amsthm", prefixes:["remark", "begin"], body:lines([
      "\\begin{remark}", "\t${1:备注内容}", "\\end{remark}", "$0"
    ])},
    {name:"proof", label:"\\begin{proof}", detail:"证明环境 · amsthm", prefixes:["proof", "begin"], body:lines([
      "\\begin{proof}[${1:证明}]", "\t${2:论证过程}", "\\end{proof}", "$0"
    ])},
    {name:"titleblock", label:"\\maketitle", detail:"标题、作者与日期", prefixes:["title", "maketitle", "author"], body:lines([
      "\\title{${1:标题}}", "\\author{${2:作者}}", "\\date{${3:\\today}}", "\\maketitle", "$0"
    ])},
    {name:"abstract", label:"\\begin{abstract}", detail:"摘要环境", prefixes:["abstract", "begin"], body:lines([
      "\\begin{abstract}", "\t${1:摘要内容}", "\\end{abstract}", "$0"
    ])},
    {name:"toc", label:"\\tableofcontents", detail:"生成目录", prefixes:["toc", "tableofcontents", "contents"], body:"\\tableofcontents\n$0"},
    {name:"usepackage", label:"\\usepackage", detail:"载入宏包", prefixes:["usepackage", "package"], body:"\\usepackage{${1:amsmath}}$0"},
    {name:"bmatrix", label:"\\begin{bmatrix}", detail:"方括号矩阵 · amsmath", prefixes:["bmatrix", "matrix", "begin"], body:lines([
      "\\begin{bmatrix}", "\t${1:a} & ${2:b} \\\\", "\t${3:c} & ${4:d}", "\\end{bmatrix}$0"
    ])},
    {name:"vmatrix", label:"\\begin{vmatrix}", detail:"行列式 · amsmath", prefixes:["vmatrix", "matrix", "begin"], body:lines([
      "\\begin{vmatrix}", "\t${1:a} & ${2:b} \\\\", "\t${3:c} & ${4:d}", "\\end{vmatrix}$0"
    ])},
    {name:"eqref", label:"\\eqref", detail:"公式编号引用 · amsmath", prefixes:["eqref"], body:"\\eqref{${1:eq:label}}$0"},
    {name:"cite", label:"\\cite", detail:"参考文献引用", prefixes:["cite"], body:"\\cite{${1:key}}$0"},
    {name:"footnote", label:"\\footnote", detail:"脚注", prefixes:["footnote", "fn"], body:"\\footnote{${1:脚注内容}}$0"},
    {name:"text", label:"\\text", detail:"公式内文字 · amsmath", prefixes:["text"], body:"\\text{${1:文字}}$0"},
    {name:"mathrm", label:"\\mathrm", detail:"正体 · amsmath", prefixes:["mathrm", "rm"], body:"\\mathrm{${1:x}}$0"},
    {name:"mathbb", label:"\\mathbb", detail:"黑板粗体 · amssymb", prefixes:["mathbb", "bb"], body:"\\mathbb{${1:R}}$0"},
    {name:"mathcal", label:"\\mathcal", detail:"花体 · amssymb", prefixes:["mathcal", "cal"], body:"\\mathcal{${1:F}}$0"},
    {name:"mathbf", label:"\\mathbf", detail:"粗斜体", prefixes:["mathbf", "bf"], body:"\\mathbf{${1:x}}$0"},
    {name:"hat", label:"\\hat", detail:"帽子记号", prefixes:["hat"], body:"\\hat{${1:x}}$0"},
    {name:"bar", label:"\\bar", detail:"横线记号", prefixes:["bar"], body:"\\bar{${1:x}}$0"},
    {name:"vec", label:"\\vec", detail:"向量箭头", prefixes:["vec"], body:"\\vec{${1:v}}$0"},
    {name:"overline", label:"\\overline", detail:"上划线", prefixes:["overline"], body:"\\overline{${1:x}}$0"},
    {name:"underbrace", label:"\\underbrace", detail:"下花括号标注 · amsmath", prefixes:["underbrace"], body:"\\underbrace{${1:x}}_{${2:标注}}$0"},
    {name:"binom", label:"\\binom", detail:"二项式系数 · amsmath", prefixes:["binom", "choose"], body:"\\binom{${1:n}}{${2:k}}$0"},
    {name:"prod", label:"\\prod", detail:"连乘记号", prefixes:["prod", "product"], body:"\\prod_{${1:i=1}}^{${2:n}} ${3:a_i}$0"},
    {name:"left-paren", label:"\\left( … \\right)", detail:"自适应圆括号对", prefixes:["left", "left-right", "lr"], body:"\\left(${1:内容} \\right)$0"},
    {name:"left-brace", label:"\\left\\{ … \\right\\}", detail:"自适应花括号对", prefixes:["leftbrace", "left-brace"], body:"\\left\\\\{${1:内容} \\right\\\\}$0"},
    {name:"alpha", label:"\\alpha", detail:"希腊字母 α", prefixes:["alpha"], body:"\\alpha$0"},
    {name:"beta", label:"\\beta", detail:"希腊字母 β", prefixes:["beta"], body:"\\beta$0"},
    {name:"gamma", label:"\\gamma", detail:"希腊字母 γ", prefixes:["gamma"], body:"\\gamma$0"},
    {name:"delta", label:"\\delta", detail:"希腊字母 δ", prefixes:["delta"], body:"\\delta$0"},
    {name:"epsilon", label:"\\epsilon", detail:"希腊字母 ε", prefixes:["epsilon"], body:"\\epsilon$0"},
    {name:"theta", label:"\\theta", detail:"希腊字母 θ", prefixes:["theta"], body:"\\theta$0"},
    {name:"lambda", label:"\\lambda", detail:"希腊字母 λ", prefixes:["lambda"], body:"\\lambda$0"},
    {name:"mu", label:"\\mu", detail:"希腊字母 μ", prefixes:["mu"], body:"\\mu$0"},
    {name:"pi", label:"\\pi", detail:"希腊字母 π", prefixes:["pi"], body:"\\pi$0"},
    {name:"sigma", label:"\\sigma", detail:"希腊字母 σ", prefixes:["sigma"], body:"\\sigma$0"},
    {name:"phi", label:"\\phi", detail:"希腊字母 φ", prefixes:["phi"], body:"\\phi$0"},
    {name:"omega", label:"\\omega", detail:"希腊字母 ω", prefixes:["omega"], body:"\\omega$0"},
    {name:"Gamma", label:"\\Gamma", detail:"大写希腊字母 Γ", prefixes:["Gamma"], body:"\\Gamma$0"},
    {name:"Delta", label:"\\Delta", detail:"大写希腊字母 Δ", prefixes:["Delta"], body:"\\Delta$0"},
    {name:"partial", label:"\\partial", detail:"偏导记号 ∂", prefixes:["partial"], body:"\\partial$0"},
    {name:"nabla", label:"\\nabla", detail:"梯度算子 ∇", prefixes:["nabla"], body:"\\nabla$0"},
    {name:"infty", label:"\\infty", detail:"无穷 ∞", prefixes:["infty", "infinity"], body:"\\infty$0"},
    {name:"times", label:"\\times", detail:"乘号 ×", prefixes:["times"], body:"\\times$0"},
    {name:"cdot", label:"\\cdot", detail:"点乘 ⋅", prefixes:["cdot"], body:"\\cdot$0"},
    {name:"leq", label:"\\leq", detail:"小于等于 ≤", prefixes:["leq", "le"], body:"\\leq$0"},
    {name:"geq", label:"\\geq", detail:"大于等于 ≥", prefixes:["geq", "ge"], body:"\\geq$0"},
    {name:"neq", label:"\\neq", detail:"不等于 ≠", prefixes:["neq", "ne"], body:"\\neq$0"},
    {name:"approx", label:"\\approx", detail:"约等于 ≈", prefixes:["approx"], body:"\\approx$0"},
    {name:"in", label:"\\in", detail:"属于 ∈", prefixes:["in"], body:"\\in$0"},
    {name:"subset", label:"\\subset", detail:"子集 ⊂", prefixes:["subset"], body:"\\subset$0"},
    {name:"cup", label:"\\cup", detail:"并集 ∪", prefixes:["cup"], body:"\\cup$0"},
    {name:"cap", label:"\\cap", detail:"交集 ∩", prefixes:["cap"], body:"\\cap$0"},
    {name:"forall", label:"\\forall", detail:"全称量词 ∀", prefixes:["forall"], body:"\\forall$0"},
    {name:"exists", label:"\\exists", detail:"存在量词 ∃", prefixes:["exists"], body:"\\exists$0"}
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
        [/\\(?:subparagraph|subsubsection|subsection|section|paragraph|part|chapter)\*?(?![A-Za-z@])/, "keyword.section"],
        [/\\(?:documentclass|usepackage|RequirePackage|newtheorem|newcommand|renewcommand|providecommand|DeclareMathOperator|DeclarePairedDelimiter|def|let|input|include|includeonly|bibliography|addbibresource)(?![A-Za-z@])/, "keyword.directive"],
        [/(\\(?:label|pageref|eqref|autoref|cref|Cref|nocite|citep|citet|cite|ref)\*?)(\s*\{)([^}]*)(\})/, ["keyword.reference", "delimiter.bracket", "string.reference", "delimiter.bracket"]],
        [/\\(?:label|pageref|eqref|autoref|cref|Cref|nocite|citep|citet|cite|ref)\*?(?![A-Za-z@])/, "keyword.reference"],
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
