const fs = require('fs');
const path = require('path');

const profilesDir = path.join(__dirname, '..', '..', 'datara-web', 'src', 'graph', 'profiles');

const content = fs.readFileSync(path.join(profilesDir, 'dag.ts'), 'utf-8');
const match = content.match(/nodeTypes:\s*(?:Record<string,\s*NodeSchema>\s*=\s*)?\{/);
const start = content.indexOf('{', match.index);

// Find http in the original content
const httpMatch = content.match(/http:\s*\{/);
if (httpMatch) {
  const httpStart = content.indexOf('{', httpMatch.index);
  console.log('http starts at:', httpStart);
  console.log('http starts with:', JSON.stringify(content.slice(httpStart, httpStart + 50)));

  // Find matching brace
  let depth = 0;
  let inStr = false;
  let strChar = null;
  let httpEnd = -1;
  for (let i = httpStart; i < content.length; i++) {
    const c = content[i];
    if (inStr) {
      if (c === '\\') { i++; continue; }
      if (c === strChar) inStr = false;
    } else {
      if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; }
      else if (c === '{') depth++;
      else if (c === '}') { depth--; if (depth === 0) { httpEnd = i; break; } }
    }
  }
  console.log('http ends at:', httpEnd);
  if (httpEnd > 0) {
    const httpStr = content.slice(httpStart, httpEnd + 1);
    console.log('http length:', httpStr.length);
    console.log('http ends with:', JSON.stringify(httpStr.slice(-50)));
  }
}
