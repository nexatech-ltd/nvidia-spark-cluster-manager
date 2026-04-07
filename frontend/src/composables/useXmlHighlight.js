function _esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function _hlTag(tag) {
  const m = tag.match(/^(<\/?)(\S+?)((?:\s[\s\S]*?)?)(\/?>)$/)
  if (!m) return _esc(tag)
  const [, open, name, attrs, close] = m
  let r = `<span class="xb">${_esc(open)}</span><span class="xt">${_esc(name)}</span>`
  if (attrs) {
    let last = 0
    const re = /([\w:-]+)\s*=\s*("[^"]*"|'[^']*')/g
    let am
    while ((am = re.exec(attrs)) !== null) {
      if (am.index > last) r += _esc(attrs.slice(last, am.index))
      r += `<span class="xa">${_esc(am[1])}</span>=<span class="xv">${_esc(am[2])}</span>`
      last = am.index + am[0].length
    }
    if (last < attrs.length) r += _esc(attrs.slice(last))
  }
  r += `<span class="xb">${_esc(close)}</span>`
  return r
}

export function highlightXml(raw) {
  if (!raw) return ''
  let out = '', i = 0
  const len = raw.length
  while (i < len) {
    if (raw[i] === '<') {
      if (raw.startsWith('<!--', i)) {
        const end = raw.indexOf('-->', i + 4)
        const j = end < 0 ? len : end + 3
        out += `<span class="xc">${_esc(raw.slice(i, j))}</span>`
        i = j
      } else if (raw.startsWith('<?', i)) {
        const end = raw.indexOf('?>', i + 2)
        const j = end < 0 ? len : end + 2
        out += `<span class="xp">${_esc(raw.slice(i, j))}</span>`
        i = j
      } else {
        let j = i + 1, inQ = false, qC = ''
        while (j < len) {
          if (inQ) { if (raw[j] === qC) inQ = false }
          else if (raw[j] === '"' || raw[j] === "'") { inQ = true; qC = raw[j] }
          else if (raw[j] === '>') { j++; break }
          j++
        }
        out += _hlTag(raw.slice(i, j))
        i = j
      }
    } else {
      const next = raw.indexOf('<', i)
      const j = next < 0 ? len : next
      out += _esc(raw.slice(i, j))
      i = j
    }
  }
  return out
}
