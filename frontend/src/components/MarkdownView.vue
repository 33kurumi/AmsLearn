<script setup>
/**
 * MarkdownView —— AI 回答统一渲染组件
 * Markdown 使用 marked，公式使用 KaTeX（$...$ / $$...$$ / \(...\) / \[...\]）。
 * 安全策略：marked 渲染后对 DOM 做白名单式清理（移除 script/style/iframe/form 等标签、
 * 所有 on* 事件属性与 javascript: 链接），再恢复 KaTeX / 代码块的 HTML，避免 XSS。
 */
import { computed } from 'vue'
import { marked } from 'marked'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps({
  content: { type: String, default: '' },
})

marked.setOptions({ gfm: true, breaks: true })

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderTex(tex, displayMode) {
  const source = String(tex || '').trim()
  if (!source) return ''
  try {
    return katex.renderToString(source, {
      displayMode,
      throwOnError: false,
      strict: false,
      trust: false,
      output: 'html',
    })
  } catch {
    return `<code>${escapeHtml(displayMode ? `$$${source}$$` : `$${source}$`)}</code>`
  }
}

function sanitizeHtml(html) {
  if (typeof document === 'undefined') return escapeHtml(html)
  const template = document.createElement('template')
  template.innerHTML = html
  const banned = ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'link', 'meta', 'base', 'svg', 'math']
  template.content.querySelectorAll(banned.join(',')).forEach((el) => el.remove())
  template.content.querySelectorAll('*').forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      const name = attr.name.toLowerCase()
      const value = attr.value || ''
      if (name.startsWith('on') || name === 'srcdoc' || name === 'formaction') {
        el.removeAttribute(attr.name)
        return
      }
      if (['href', 'src', 'xlink:href'].includes(name) && /^\s*(javascript|vbscript|data):/i.test(value)) {
        el.removeAttribute(attr.name)
      }
    })
  })
  return template.innerHTML
}

function renderMarkdown(source) {
  const raw = String(source || '').replace(/\r\n/g, '\n')
  if (!raw.trim()) return ''
  const codeBlocks = []
  const codeSpans = []
  const maths = []
  let text = raw

  // 1) 围栏代码块先占位，避免其中 $ 被当作公式
  text = text.replace(/^(`{3,}|~{3,})[^\n]*\n([\s\S]*?)^\1\s*$/gm, (match, fence, code) => {
    const id = codeBlocks.length
    codeBlocks.push(`<pre class="md-code"><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`)
    return `\n\nZZCODEBLOCK${id}ZZ\n\n`
  })

  // 2) 行内代码占位
  text = text.replace(/`([^`\n]+)`/g, (match, code) => {
    const id = codeSpans.length
    codeSpans.push(`<code>${escapeHtml(code)}</code>`)
    return `ZZCODESPAN${id}ZZ`
  })

  // 3) 块级公式 $$...$$ 与 \[...\]
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (match, tex) => {
    const id = maths.length
    maths.push(renderTex(tex, true))
    return `\n\nZZMATHBLOCK${id}ZZ\n\n`
  })
  text = text.replace(/\\\[([\s\S]+?)\\\]/g, (match, tex) => {
    const id = maths.length
    maths.push(renderTex(tex, true))
    return `\n\nZZMATHBLOCK${id}ZZ\n\n`
  })

  // 4) 行内公式 \(...\) 与 $...$（排除货币写法与空内容）
  text = text.replace(/\\\(([\s\S]+?)\\\)/g, (match, tex) => {
    const id = maths.length
    maths.push(renderTex(tex, false))
    return `ZZMATHSPAN${id}ZZ`
  })
  text = text.replace(/(^|[^$\\])\$(?!\$)([^\n$]{1,500}?)\$(?!\$)/g, (match, prefix, tex) => {
    if (!tex.trim() || /^\s/.test(tex) || /\s$/.test(tex)) return match
    const id = maths.length
    maths.push(renderTex(tex, false))
    return `${prefix}ZZMATHSPAN${id}ZZ`
  })

  let html
  try {
    html = marked.parse(text)
  } catch {
    html = `<p>${escapeHtml(raw)}</p>`
  }
  if (typeof html !== 'string') html = String(html)

  // 5) 清理不可信 HTML，再还原受控的公式 / 代码 HTML
  html = sanitizeHtml(html)

  html = html
    .replace(/<p>\s*ZZCODEBLOCK(\d+)ZZ\s*<\/p>/g, (match, id) => codeBlocks[Number(id)] || '')
    .replace(/<p>\s*ZZMATHBLOCK(\d+)ZZ\s*<\/p>/g, (match, id) => maths[Number(id)] || '')
    .replace(/ZZCODEBLOCK(\d+)ZZ/g, (match, id) => codeBlocks[Number(id)] || '')
    .replace(/ZZCODESPAN(\d+)ZZ/g, (match, id) => codeSpans[Number(id)] || '')
    .replace(/ZZMATHBLOCK(\d+)ZZ/g, (match, id) => maths[Number(id)] || '')
    .replace(/ZZMATHSPAN(\d+)ZZ/g, (match, id) => maths[Number(id)] || '')
  return html
}

const rendered = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div class="markdown-body" v-html="rendered"></div>
</template>
