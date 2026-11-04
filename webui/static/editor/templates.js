/* Local document templates for TeXada Studio. No model or network requests. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TeXadaTemplates = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const templates = Object.freeze([
    Object.freeze({
      id: "blank",
      name: "空白文章",
      description: "ctexart + amsmath 的最小中文文档。",
      content: "\\documentclass[UTF8,fontset=fandol]{ctexart}\n\\usepackage{amsmath,amssymb}\n\\begin{document}\n\\section{新的文档}\n\n在这里开始写作。$E = mc^2$\n\n\\end{document}\n"
    }),
    Object.freeze({
      id: "lecture-notes",
      name: "数学讲义",
      description: "定理、定义与例题环境，amsthm 讲义骨架。",
      content: [
        "\\documentclass[UTF8,fontset=fandol]{ctexart}",
        "\\usepackage{amsmath,amssymb,amsthm}",
        "\\newtheorem{theorem}{定理}",
        "\\newtheorem{definition}[theorem]{定义}",
        "\\newtheorem{example}[theorem]{例}",
        "\\title{数学讲义：标题}",
        "\\author{作者}",
        "\\date{\\today}",
        "\\begin{document}",
        "\\maketitle",
        "\\tableofcontents",
        "",
        "\\section{引言}",
        "概述本讲内容与记号约定。",
        "",
        "\\section{主要结论}",
        "\\begin{theorem}[示例定理]",
        "设 $a, b$ 为实数，则",
        "\\begin{equation}",
        "  (a+b)^2 = a^2 + 2ab + b^2.",
        "  \\label{eq:example}",
        "\\end{equation}",
        "\\end{theorem}",
        "\\begin{proof}",
        "将左边展开并合并同类项即得。",
        "\\end{proof}",
        "",
        "\\begin{definition}[导数]",
        "函数 $f$ 在点 $x$ 处的导数定义为",
        "\\[",
        "  f'(x) = \\lim_{h \\to 0} \\frac{f(x+h)-f(x)}{h}.",
        "\\]",
        "\\end{definition}",
        "",
        "\\section{例题}",
        "\\begin{example}",
        "计算 $\\int_0^1 2x \\, \\mathrm{d}x$。",
        "\\end{example}",
        "",
        "\\end{document}\n"
      ].join("\n")
    }),
    Object.freeze({
      id: "exam-paper",
      name: "试卷",
      description: "填空、计算与证明三类大题的试卷骨架。",
      content: [
        "\\documentclass[UTF8,fontset=fandol]{ctexart}",
        "\\usepackage{amsmath,amssymb}",
        "\\title{《课程名称》期中测验}",
        "\\author{姓名：\\underline{\\hspace{3cm}} \\quad 学号：\\underline{\\hspace{3cm}}}",
        "\\date{总计 100 分，考试时间 90 分钟}",
        "\\begin{document}",
        "\\maketitle",
        "",
        "\\section*{一、填空题（每小题 5 分，共 20 分）}",
        "\\begin{enumerate}",
        "  \\item $\\int_0^1 x \\, \\mathrm{d}x = $ \\underline{\\hspace{2cm}}。",
        "  \\item 设 $f(x) = x^2$，则 $f'(x) = $ \\underline{\\hspace{2cm}}。",
        "\\end{enumerate}",
        "",
        "\\section*{二、计算题（每小题 15 分，共 60 分）}",
        "\\begin{enumerate}",
        "  \\item 求极限 $\\lim_{x \\to 0} \\dfrac{\\sin x}{x}$。",
        "  \\item 计算定积分 $\\int_0^{\\pi} \\sin x \\, \\mathrm{d}x$。",
        "\\end{enumerate}",
        "",
        "\\section*{三、证明题（共 20 分）}",
        "证明：对任意实数 $a$ 与 $b$，有 $a^2 + b^2 \\geq 2ab$。",
        "",
        "\\end{document}\n"
      ].join("\n")
    }),
    Object.freeze({
      id: "beamer",
      name: "Beamer 演示",
      description: "ctexbeamer 封面、目录与内容 frame 骨架。",
      content: [
        "\\documentclass[UTF8,fontset=fandol]{ctexbeamer}",
        "\\usepackage{amsmath,amssymb}",
        "\\title{报告标题}",
        "\\author{报告人}",
        "\\date{\\today}",
        "\\begin{document}",
        "",
        "\\begin{frame}",
        "  \\titlepage",
        "\\end{frame}",
        "",
        "\\begin{frame}{目录}",
        "  \\tableofcontents",
        "\\end{frame}",
        "",
        "\\section{背景}",
        "\\begin{frame}{背景与动机}",
        "  \\begin{itemize}",
        "    \\item 研究背景一",
        "    \\item 研究背景二",
        "  \\end{itemize}",
        "\\end{frame}",
        "",
        "\\section{方法}",
        "\\begin{frame}{核心方法}",
        "  核心公式：",
        "  \\begin{equation}",
        "    E = mc^2",
        "  \\end{equation}",
        "\\end{frame}",
        "",
        "\\begin{frame}{小结}",
        "  \\begin{itemize}",
        "    \\item 结论一",
        "    \\item 结论二",
        "  \\end{itemize}",
        "\\end{frame}",
        "",
        "\\end{document}\n"
      ].join("\n")
    }),
    Object.freeze({
      id: "english-article",
      name: "English article",
      description: "article + amsthm 英文论文骨架。",
      content: [
        "\\documentclass[11pt]{article}",
        "\\usepackage{amsmath,amssymb,amsthm,graphicx}",
        "\\newtheorem{theorem}{Theorem}",
        "\\newtheorem{definition}{Definition}",
        "\\title{Paper Title}",
        "\\author{Author Name}",
        "\\date{\\today}",
        "\\begin{document}",
        "\\maketitle",
        "",
        "\\begin{abstract}",
        "Summarize the problem, method and main result in a few sentences.",
        "\\end{abstract}",
        "",
        "\\section{Introduction}",
        "State the problem and the motivation of the paper.",
        "",
        "\\section{Main Result}",
        "\\begin{theorem}",
        "For all real numbers $a$ and $b$,",
        "\\begin{equation}",
        "  (a+b)^2 = a^2 + 2ab + b^2.",
        "  \\label{eq:intro}",
        "\\end{equation}",
        "\\end{theorem}",
        "\\begin{proof}",
        "Expand the left-hand side and collect terms.",
        "\\end{proof}",
        "Equation \\eqref{eq:intro} follows from the binomial theorem.",
        "",
        "\\section{Conclusion}",
        "Summarize findings and outline future work.",
        "",
        "\\end{document}\n"
      ].join("\n")
    })
  ]);

  function list() { return templates.slice(); }

  function defaultContent() {
    const blank = templates.find(template => template.id === "blank");
    if (!blank) throw new Error("TeXadaTemplates requires a blank template.");
    return blank.content;
  }

  return Object.freeze({list, defaultContent});
});
