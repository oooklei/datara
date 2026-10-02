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

console.log('nodeTypes length:', nodeTypesStr.length);

// Find http entry
const httpMatch = nodeTypesStr.match(/http:\s*\{/);
if (httpMatch) {
  const httpStart = nodeTypesStr.indexOf('{', httpMatch.index);
  console.log('http starts at:', httpStart);
  console.log('http starts with:', JSON.stringify(nodeTypesStr.slice(httpStart, httpStart + 50)));

  // Find matching brace
  const httpEnd = findMatchingBrace(nodeTypesStr, httpStart);
  console.log('http ends at:', httpEnd);
  if (httpEnd > 0) {
    const httpStr = nodeTypesStr.slice(httpStart, httpEnd + 1);
    console.log('http length:', httpStr.length);
    console.log('http ends with:', JSON.stringify(httpStr.slice(-50)));
  }
}
