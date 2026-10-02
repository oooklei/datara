const fs = require('fs');
const path = require('path');

const profilesDir = path.join(__dirname, '..', '..', 'datara-web', 'src', 'graph', 'profiles');

const profileFiles = {
  dag: 'dag.ts',
  etl: 'etl.ts',
  stream: 'stream.ts',
  topo: 'topo.ts',
  er: 'er.ts',
  lineage: 'lineage.ts',
  relation: 'relation.ts',
};

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

function extractNodeTypes(content) {
  const match = content.match(/nodeTypes:\s*(?:Record<string,\s*NodeSchema>\s*=\s*)?\{/);
  if (!match) return {};

  const start = content.indexOf('{', match.index);
  const end = findMatchingBrace(content, start);
  if (end === -1) return {};

  const nodeTypesStr = content.slice(start, end + 1);
  return parseTsObject(nodeTypesStr);
}

function parseTsObject(s) {
  s = s.trim();
  if (!s.startsWith('{') || !s.endsWith('}')) return {};

  let inner = s.slice(1, -1).trim();
  if (!inner) return {};

  // Remove comments
  inner = inner.replace(/\/\/.*$/gm, '');
  inner = inner.replace(/\/\*[\s\S]*?\*\//g, '');

  const result = {};
  let depth = 0;
  let current = '';
  let inStr = false;
  let strChar = null;
  const parts = [];

  for (const c of inner) {
    if (inStr) {
      current += c;
      if (c === '\\') continue;
      if (c === strChar) inStr = false;
    } else {
      if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; current += c; }
      else if (c === '{' || c === '[') { depth++; current += c; }
      else if (c === '}' || c === ']') { depth--; current += c; }
      else if (c === ',' && depth === 0) { parts.push(current); current = ''; }
      else current += c;
    }
  }
  if (current.trim()) parts.push(current);

  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;

    // Find first colon at depth 0
    let colonPos = -1;
    let d = 0;
    let inS = false;
    let sc = null;
    for (let i = 0; i < trimmed.length; i++) {
      const c = trimmed[i];
      if (inS) {
        if (c === '\\') continue;
        if (c === sc) inS = false;
      } else {
        if (c === '"' || c === "'" || c === '`') { inS = true; sc = c; }
        else if (c === '{' || c === '[') d++;
        else if (c === '}' || c === ']') d--;
        else if (c === ':' && d === 0) { colonPos = i; break; }
      }
    }

    if (colonPos === -1) continue;

    let key = trimmed.slice(0, colonPos).trim();
    const valueStr = trimmed.slice(colonPos + 1).trim();

    if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
      key = key.slice(1, -1);
    }

    if (key.includes('/*') || key.includes('*/') || !key.trim()) continue;

    result[key] = parseTsValue(valueStr);
  }

  return result;
}

function parseTsValue(s) {
  s = s.trim();
  if (!s) return null;

  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  if (s.startsWith('`') && s.endsWith('`')) return s.slice(1, -1);

  if (s === 'true') return true;
  if (s === 'false') return false;
  if (s === 'null') return null;

  const num = Number(s);
  if (!isNaN(num) && s !== '') return num;

  if (s.startsWith('[') && s.endsWith(']')) {
    const inner = s.slice(1, -1).trim();
    if (!inner) return [];
    const items = [];
    let depth = 0;
    let current = '';
    let inStr = false;
    let strChar = null;
    for (const c of inner) {
      if (inStr) {
        current += c;
        if (c === '\\') continue;
        if (c === strChar) inStr = false;
      } else {
        if (c === '"' || c === "'" || c === '`') { inStr = true; strChar = c; current += c; }
        else if (c === '{' || c === '[') { depth++; current += c; }
        else if (c === '}' || c === ']') { depth--; current += c; }
        else if (c === ',' && depth === 0) { items.push(parseTsValue(current)); current = ''; }
        else current += c;
      }
    }
    if (current.trim()) items.push(parseTsValue(current));
    return items;
  }

  if (s.startsWith('{') && s.endsWith('}')) {
    return parseTsObject(s);
  }

  return s;
}

// Main
const result = {};
for (const [profile, filename] of Object.entries(profileFiles)) {
  const filepath = path.join(profilesDir, filename);
  if (!fs.existsSync(filepath)) continue;
  const content = fs.readFileSync(filepath, 'utf-8');
  result[profile] = extractNodeTypes(content);
}

console.log(JSON.stringify(result, null, 2));
