(function () {
  function textNode(value) {
    return document.createTextNode(value || "");
  }

  function cloneAttributes(base, updates) {
    return Object.assign({}, base || {}, updates || {});
  }

  function pushText(ops, text, attrs) {
    if (!text) return;
    const op = { insert: text };
    if (attrs && Object.keys(attrs).length) op.attributes = attrs;
    ops.push(op);
  }

  function walk(node, attrs, ops) {
    if (node.nodeType === Node.TEXT_NODE) {
      pushText(ops, node.textContent, attrs);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = node.tagName.toLowerCase();
    let nextAttrs = attrs || {};
    if (["b", "strong"].includes(tag)) nextAttrs = cloneAttributes(nextAttrs, { bold: true });
    if (["i", "em"].includes(tag)) nextAttrs = cloneAttributes(nextAttrs, { italic: true });
    if (tag === "u") nextAttrs = cloneAttributes(nextAttrs, { underline: true });
    if (tag === "br") {
      pushText(ops, "\n", attrs);
      return;
    }
    Array.from(node.childNodes).forEach((child) => walk(child, nextAttrs, ops));
    if (["div", "p", "h1", "h2", "li", "blockquote"].includes(tag)) {
      const lineAttrs = {};
      if (tag === "h1") lineAttrs.header = 1;
      if (tag === "h2") lineAttrs.header = 2;
      if (tag === "li") lineAttrs.list = "bullet";
      if (tag === "blockquote") lineAttrs.blockquote = true;
      pushText(ops, "\n", Object.keys(lineAttrs).length ? lineAttrs : undefined);
    }
  }

  function deltaFromElement(element) {
    const ops = [];
    Array.from(element.childNodes).forEach((child) => walk(child, {}, ops));
    while (ops.length && ops[ops.length - 1].insert === "\n") {
      ops.pop();
    }
    return { ops };
  }

  function plainTextFromDelta(delta) {
    if (!delta || !Array.isArray(delta.ops)) return "";
    return delta.ops.map((op) => (typeof op.insert === "string" ? op.insert : "")).join("").trim();
  }

  function applyInline(text, attrs) {
    let node = textNode(text);
    if (!attrs) return node;
    if (attrs.bold) {
      const strong = document.createElement("strong");
      strong.appendChild(node);
      node = strong;
    }
    if (attrs.italic) {
      const em = document.createElement("em");
      em.appendChild(node);
      node = em;
    }
    if (attrs.underline) {
      const underline = document.createElement("u");
      underline.appendChild(node);
      node = underline;
    }
    return node;
  }

  function renderDelta(element, delta) {
    element.innerHTML = "";
    if (!delta || !Array.isArray(delta.ops) || !delta.ops.length) return;
    let paragraph = document.createElement("p");
    element.appendChild(paragraph);
    delta.ops.forEach((op) => {
      const insert = typeof op.insert === "string" ? op.insert : "";
      const parts = insert.split("\n");
      parts.forEach((part, index) => {
        if (part) paragraph.appendChild(applyInline(part, op.attributes));
        if (index < parts.length - 1) {
          if (op.attributes && op.attributes.header) {
            const heading = document.createElement(op.attributes.header === 1 ? "h1" : "h2");
            while (paragraph.firstChild) heading.appendChild(paragraph.firstChild);
            element.replaceChild(heading, paragraph);
          } else if (op.attributes && op.attributes.blockquote) {
            const quote = document.createElement("blockquote");
            while (paragraph.firstChild) quote.appendChild(paragraph.firstChild);
            element.replaceChild(quote, paragraph);
          }
          paragraph = document.createElement("p");
          element.appendChild(paragraph);
        }
      });
    });
    if (!paragraph.textContent.trim() && paragraph.childNodes.length === 0 && element.childNodes.length > 1) {
      paragraph.remove();
    }
  }

  function renderReadOnly(element, delta) {
    if (!element || !delta || !Array.isArray(delta.ops) || !delta.ops.length) return;
    renderDelta(element, delta);
  }

  function bindToolbar(editor, toolbar) {
    if (!toolbar) return;
    toolbar.querySelectorAll("[data-command]").forEach((button) => {
      button.addEventListener("click", () => {
        editor.focus();
        const command = button.dataset.command;
        const value = button.dataset.value || null;
        document.execCommand(command, false, value);
      });
    });
  }

  function bindForm(options) {
    const editor = document.getElementById(options.editorId);
    const deltaField = document.getElementById(options.deltaFieldId);
    const textField = document.getElementById(options.textFieldId);
    const toolbar = document.querySelector(options.toolbarSelector);
    if (!editor || !deltaField || !textField) return;
    renderDelta(editor, options.initialDelta || { ops: [] });
    bindToolbar(editor, toolbar);
    const sync = () => {
      const delta = deltaFromElement(editor);
      deltaField.value = JSON.stringify(delta);
      textField.value = plainTextFromDelta(delta);
    };
    editor.addEventListener("input", sync);
    editor.closest("form").addEventListener("submit", sync);
    sync();
  }

  window.JournalEditor = { bindForm, renderDelta, renderReadOnly, deltaFromElement, plainTextFromDelta };
})();
