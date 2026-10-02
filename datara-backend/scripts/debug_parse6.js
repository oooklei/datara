const fs = require('fs');
const path = require('path');

const profilesDir = path.join(__dirname, '..', '..', 'datara-web', 'src', 'graph', 'profiles');

const content = fs.readFileSync(path.join(profilesDir, 'dag.ts'), 'utf-8');
const match = content.match(/nodeTypes:\s*(?:Record<string,\s*NodeSchema>\s*=\s*)?\{/);
const start = content.indexOf('{', match.index);

// Find matching brace for nodeTypes
let depth = 0;
let inStr = false;
let strChar = null;
let end = -1;
for (let i = start; i < content.length; i++) {
  const c = content[i];
  if (inStr) {
    if (c === '\\') { i++; continue; }
    if (c === strChar) inStr = false;
  } else {
    if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; }
    else if (c === '{') depth++;
    else if (c === '}') { depth--; if (depth === 0) { end = i; break; } }
  }
}

const nodeTypesStr = content.slice(start, end + 1);
let inner = nodeTypesStr.slice(1, -1).trim();
inner = inner.replace(/\/\/.*$/gm, '');
inner = inner.replace(/\/\*[\s\S]*?\*\//g, '');

// Find http entry in inner
const httpMatch = inner.match(/http:\s*\{/);
if (httpMatch) {
  const httpStart = inner.indexOf('{', httpMatch.index);

  // Trace through http value character by character
  let d = 0;
  let inS = false;
  let sc = null;
  let lastDepth = 0;
  for (let i = httpStart; i < inner.length; i++) {
    const c = inner[i];
    if (inS) {
      if (c === '\\') { i++; continue; }
      if (c === sc) inS = false;
    } else {
      if (c === '"' || c === "'" || c === '`') { inS = true; sc = c; }
      else if (c === '{') d++;
      else if (c === '}') {
        d--;
        if (d === 0) {
          console.log('Found matching brace at', i);
          console.log('Context:', JSON.stringify(inner.slice(i - 20, i + 20)));
          break;
        }
      }
    }
    if (i > httpStart + 2000) {
      console.log('Giving up after 2000 chars');
      console.log('Current depth:', d);
      console.log('Current char:', JSON.stringify(c));
      console.log('Context:', JSON.stringify(inner.slice(i - 50, i + 50)));
      break;
    }
  }
}
