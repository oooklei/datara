const fs = require('fs');
const path = require('path');

const profilesDir = path.join(__dirname, '..', '..', 'datara-web', 'src', 'graph', 'profiles');

function findMatchingBrace(content, start) {
  let depth = 0;
  let inStr = false;
  let strChar = null;
  for (let i = start; i < content.length; i++) {
    const c = content[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === strChar) inStr = false;
    } else {
      if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; }
      else if (c === '{') depth++;
      else if (c === '}') { depth--; if (depth === 0) return i; }
    }
  }
  return -1;
}

const content = fs.readFileSync(path.join(profilesDir, 'dag.ts'), 'utf-8');
const match = content.match(/nodeTypes:\s*(?:Record<string,\s*NodeSchema>\s*=\s*)?\{/);
const start = content.indexOf('{', match.index);
const end = findMatchingBrace(content, start);
const nodeTypesStr = content.slice(start, end + 1);

// Remove comments
let inner = nodeTypesStr.slice(1, -1).trim();
inner = inner.replace(/\/\/.*$/gm, '');
inner = inner.replace(/\/\*[\s\S]*?\*\//g, '');

// Find http entry and check its value
const httpMatch = inner.match(/http:\s*\{/);
if (httpMatch) {
  const httpStart = inner.indexOf('{', httpMatch.index);
  const httpEnd = findMatchingBrace(inner, httpStart);
  const httpStr = inner.slice(httpStart, httpEnd + 1);
  console.log('http value length:', httpStr.length);
  console.log('http value starts with:', JSON.stringify(httpStr.slice(0, 50)));
  console.log('http value ends with:', JSON.stringify(httpStr.slice(-50)));

  // Now check what parseTsValue would do with this
  const trimmed = httpStr.trim();
  console.log('trimmed starts with {:', trimmed.startsWith('{'));
  console.log('trimmed ends with }:', trimmed.endsWith('}'));
}
