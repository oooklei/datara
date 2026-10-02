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

// Show http area before comment removal
const httpMatchBefore = inner.match(/http:\s*\{/);
if (httpMatchBefore) {
  const httpStart = inner.indexOf('{', httpMatchBefore.index);
  console.log('BEFORE comment removal:');
  console.log('http starts with:', JSON.stringify(inner.slice(httpStart, httpStart + 100)));
}

// Remove comments
inner = inner.replace(/\/\/.*$/gm, '');
inner = inner.replace(/\/\*[\s\S]*?\*\//g, '');

// Show http area after comment removal
const httpMatchAfter = inner.match(/http:\s*\{/);
if (httpMatchAfter) {
  const httpStart = inner.indexOf('{', httpMatchAfter.index);
  console.log('AFTER comment removal:');
  console.log('http starts with:', JSON.stringify(inner.slice(httpStart, httpStart + 100)));
  console.log('http area (200 chars):', JSON.stringify(inner.slice(httpStart, httpStart + 200)));
}
