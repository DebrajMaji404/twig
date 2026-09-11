/**
 * Twig JavaScript Codec (twig.js)
 * Pure, zero-dependency browser and Node.js implementation of the Twig serialization format.
 * Enables zero-latency in-browser encoding, decoding, and token estimation.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.Twig = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // --- Escaping utilities ---
  function escapeValue(val) {
    if (typeof val !== 'string') return String(val);
    return val
      .replace(/\\/g, '\\\\')
      .replace(/\|/g, '\\|')
      .replace(/\^/g, '\\^')
      .replace(/\n/g, '\\n')
      .replace(/^#(?=\d+)/, '\\#');
  }

  function unescapeValue(val) {
    if (typeof val !== 'string') return val;
    let res = '';
    let i = 0;
    while (i < val.length) {
      if (val[i] === '\\' && i + 1 < val.length) {
        const next = val[i + 1];
        if (next === 'n') res += '\n';
        else res += next;
        i += 2;
      } else {
        res += val[i];
        i++;
      }
    }
    return res;
  }

  function decodeScalar(raw) {
    if (raw === '#') return null;
    if (raw === 'true') return true;
    if (raw === 'false') return false;
    if (raw === '') return '';

    if (raw.startsWith("'")) {
      return unescapeValue(raw.slice(1));
    }

    if (raw.startsWith('*')) {
      const rest = raw.slice(1);
      if (rest === '') return [];
      const parts = rest.split('^');
      return parts.map((p) => decodeScalar(unescapeValue(p)));
    }

    if (/^-?\d+$/.test(raw)) {
      return parseInt(raw, 10);
    }
    if (/^-?\d+\.\d+$/.test(raw)) {
      return parseFloat(raw);
    }

    return unescapeValue(raw);
  }

  function encodeScalar(val) {
    if (val === null || val === undefined) return '#';
    if (typeof val === 'boolean') return val ? 'true' : 'false';
    if (typeof val === 'number') return String(val);
    if (Array.isArray(val)) {
      if (val.length === 0) return '*';
      return '*' + val.map((item) => escapeValue(encodeScalar(item))).join('^');
    }
    if (typeof val === 'string') {
      if (val === '') return '';
      if (
        val === 'true' ||
        val === 'false' ||
        val === '#' ||
        /^-?\d+(\.\d+)?$/.test(val) ||
        val.startsWith("'") ||
        val.startsWith('*') ||
        /^#\d+$/.test(val)
      ) {
        return "'" + escapeValue(val);
      }
      return escapeValue(val);
    }
    return escapeValue(String(val));
  }

  // --- Parser / Decoder ---
  function decode(text) {
    const lines = text.split(/\r?\n/);
    if (!lines.length) return [];

    let isSingle = false;
    let lineIdx = 0;

    if (lines[0].startsWith('@shape:')) {
      if (lines[0].trim() === '@shape:single') isSingle = true;
      lineIdx++;
    }

    const tableBlocks = [];
    let currentBlock = [];

    for (; lineIdx < lines.length; lineIdx++) {
      const line = lines[lineIdx];
      if (line.trim() === '===') {
        if (currentBlock.length) {
          tableBlocks.push(currentBlock);
          currentBlock = [];
        }
      } else {
        currentBlock.push(line);
      }
    }
    if (currentBlock.length) tableBlocks.push(currentBlock);

    const tables = {};

    for (const block of tableBlocks) {
      if (!block.length) continue;
      let tableName = 'root';
      const first = block[0].trim();
      let startI = 0;
      if (first.startsWith('table:')) {
        tableName = first.slice(6).trim();
        startI = 1;
      }

      let section = null;
      const treeLines = [];
      const typesList = [];
      const arraysLines = [];
      const dictEntries = {};
      const rowsList = [];

      for (let i = startI; i < block.length; i++) {
        const rawLine = block[i];
        const trimmed = rawLine.trim();
        if (!trimmed && section !== '@rows') continue;

        if (trimmed.startsWith('@')) {
          section = trimmed;
          continue;
        }

        if (section === '@tree') {
          if (trimmed) treeLines.push(trimmed);
        } else if (section === '@types') {
          if (trimmed) typesList.push(trimmed);
        } else if (section === '@arrays') {
          if (trimmed) arraysLines.push(trimmed);
        } else if (section === '@dict') {
          const eqIdx = trimmed.indexOf('=');
          if (eqIdx !== -1) {
            dictEntries[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1);
          }
        } else if (section === '@rows') {
          if (trimmed !== '') rowsList.push(rawLine);
        }
      }

      // Resolve tree
      const parentMap = {};
      for (const tline of treeLines) {
        const [code, rest] = tline.split('=');
        if (code && rest) {
          const [seg, pcode] = rest.split('^');
          parentMap[code.trim()] = { seg: seg.trim(), parent: pcode ? pcode.trim() : '-' };
        }
      }

      function resolvePath(field) {
        if (!field.includes('.')) return field;
        const [lcode, fname] = field.split('.', 2);
        if (!parentMap[lcode]) return field;
        const segments = [fname];
        let curr = lcode;
        while (curr && curr !== '-') {
          const info = parentMap[curr];
          if (!info) break;
          segments.unshift(info.seg);
          curr = info.parent;
        }
        return segments.join('.');
      }

      const resolvedTypes = typesList.map(resolvePath);
      const parsedRows = [];

      for (const rline of rowsList) {
        const rawVals = rline.split('|');
        const expandedVals = [];
        for (const rv of rawVals) {
          if (/^#\d+$/.test(rv)) {
            const count = parseInt(rv.slice(1), 10);
            for (let c = 0; c < count; c++) expandedVals.push(null);
          } else {
            expandedVals.push(decodeScalar(rv));
          }
        }
        parsedRows.push(expandedVals);
      }

      tables[tableName] = {
        types: resolvedTypes,
        rawTypes: typesList,
        rows: parsedRows,
        arrays: arraysLines,
      };
    }

    function reconstructTable(tableName) {
      const tbl = tables[tableName];
      if (!tbl) return [];

      const records = [];
      for (let r = 0; r < tbl.rows.length; r++) {
        const row = tbl.rows[r];
        const record = {};
        for (let col = 0; col < tbl.types.length; col++) {
          const path = tbl.types[col];
          const val = col < row.length ? row[col] : null;

          if (path === '_parent' || path === '_idx') continue;
          if (path.startsWith('$has:') || path.startsWith('$lvl:')) continue;

          if (path.includes('.')) {
            const parts = path.split('.');
            let curr = record;
            for (let p = 0; p < parts.length - 1; p++) {
              if (!curr[parts[p]]) curr[parts[p]] = {};
              curr = curr[parts[p]];
            }
            curr[parts[parts.length - 1]] = val;
          } else {
            record[path] = val;
          }
        }
        records.push(record);
      }

      // Link child arrays
      for (const arrLine of tbl.arrays) {
        const [childCode, fieldPath] = arrLine.split('=').map((s) => s.trim());
        const childTbl = tables[childCode];
        if (!childTbl) continue;

        const childRecords = reconstructTable(childCode);
        const parentIdxCol = childTbl.types.indexOf('_parent');
        const idxCol = childTbl.types.indexOf('_idx');

        const groups = {};
        for (let cr = 0; cr < childTbl.rows.length; cr++) {
          const crow = childTbl.rows[cr];
          const pidx = crow[parentIdxCol];
          const order = crow[idxCol] || 0;
          if (!groups[pidx]) groups[pidx] = [];
          groups[pidx].push({ order, data: childRecords[cr] });
        }

        for (let r = 0; r < records.length; r++) {
          const items = groups[r] || [];
          items.sort((a, b) => a.order - b.order);
          const finalArray = items.map((it) => it.data);

          if (fieldPath.includes('.')) {
            const parts = fieldPath.split('.');
            let curr = records[r];
            for (let p = 0; p < parts.length - 1; p++) {
              if (!curr[parts[p]]) curr[parts[p]] = {};
              curr = curr[parts[p]];
            }
            curr[parts[parts.length - 1]] = finalArray;
          } else {
            records[r][fieldPath] = finalArray;
          }
        }
      }

      return records;
    }

    const result = reconstructTable('root');
    if (isSingle) return result.length ? result[0] : {};
    return result;
  }

  // --- Fast Encoder ---
  function encode(data) {
    if (data === null || data === undefined) return 'table:root\n@types\nvalue\n@rows\n#';
    const isSingle = !Array.isArray(data);
    const records = isSingle ? [data] : data;

    if (!records.length) {
      return '@shape:list\ntable:root\n@types\n@rows';
    }

    // Collect schema
    const flatFields = [];
    const arrayFields = [];
    const treeMap = {};
    let levelCounter = 1;

    function analyze(obj, prefix = '') {
      if (!obj || typeof obj !== 'object') return;
      for (const k of Object.keys(obj)) {
        const fullKey = prefix ? `${prefix}.${k}` : k;
        const val = obj[k];

        if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
          if (!arrayFields.includes(fullKey)) arrayFields.push(fullKey);
        } else if (val && typeof val === 'object' && !Array.isArray(val)) {
          analyze(val, fullKey);
        } else {
          if (!flatFields.includes(fullKey)) flatFields.push(fullKey);
        }
      }
    }

    for (const r of records) analyze(r);

    // Build parent-pointer tree if deep nesting exists
    const treeHeader = [];
    const levelCodeMap = {}; // "address.present" -> "l2"

    const prefixSet = new Set();
    for (const f of flatFields) {
      if (f.includes('.')) {
        const parts = f.split('.');
        let cur = '';
        for (let i = 0; i < parts.length - 1; i++) {
          cur = cur ? `${cur}.${parts[i]}` : parts[i];
          prefixSet.add(cur);
        }
      }
    }

    const sortedPrefixes = Array.from(prefixSet).sort((a, b) => a.split('.').length - b.split('.').length);
    if (sortedPrefixes.length >= 2) {
      for (const p of sortedPrefixes) {
        const parts = p.split('.');
        const seg = parts[parts.length - 1];
        const parentP = parts.slice(0, -1).join('.');
        const pcode = parentP ? levelCodeMap[parentP] : '-';
        const code = `l${levelCounter++}`;
        levelCodeMap[p] = code;
        treeHeader.push(`${code}=${seg}^${pcode}`);
      }
    }

    // Field headers
    const typesHeader = flatFields.map((f) => {
      if (!f.includes('.')) return f;
      const parts = f.split('.');
      const parentP = parts.slice(0, -1).join('.');
      const fname = parts[parts.length - 1];
      if (levelCodeMap[parentP]) {
        return `${levelCodeMap[parentP]}.${fname}`;
      }
      return f;
    });

    // Generate rows
    const rows = [];
    for (const r of records) {
      const rowVals = flatFields.map((f) => {
        let curr = r;
        if (!f.includes('.')) return curr ? encodeScalar(curr[f]) : '#';
        const parts = f.split('.');
        for (const p of parts) {
          if (!curr || typeof curr !== 'object') return '#';
          curr = curr[p];
        }
        return encodeScalar(curr);
      });

      // Compress consecutive nulls (#N)
      const compressed = [];
      let nullRun = 0;
      for (const v of rowVals) {
        if (v === '#') {
          nullRun++;
        } else {
          if (nullRun > 1) {
            compressed.push(`#${nullRun}`);
          } else if (nullRun === 1) {
            compressed.push('#');
          }
          nullRun = 0;
          compressed.push(v);
        }
      }
      if (nullRun > 1) {
        compressed.push(`#${nullRun}`);
      } else if (nullRun === 1) {
        compressed.push('#');
      }
      rows.push(compressed.join('|'));
    }

    const out = [];
    if (isSingle) out.push('@shape:single');
    else out.push('@shape:list');

    out.push('table:root');
    if (treeHeader.length > 0) {
      out.push('@tree');
      out.push(...treeHeader);
    }
    out.push('@types');
    out.push(...typesHeader);

    // If arrays of objects exist, create child tables
    const childTables = [];
    if (arrayFields.length > 0) {
      out.push('@arrays');
      let cIdx = 1;
      for (const arrField of arrayFields) {
        const ccode = `c${cIdx++}`;
        out.push(`${ccode}=${arrField}`);

        const childRows = [];
        let childFlatKeys = [];
        for (let rIdx = 0; rIdx < records.length; rIdx++) {
          let curr = records[rIdx];
          const parts = arrField.split('.');
          for (const p of parts) {
            if (!curr) break;
            curr = curr[p];
          }
          if (Array.isArray(curr)) {
            for (let iIdx = 0; iIdx < curr.length; iIdx++) {
              const item = curr[iIdx];
              if (item && typeof item === 'object') {
                for (const k of Object.keys(item)) {
                  if (!childFlatKeys.includes(k) && typeof item[k] !== 'object') {
                    childFlatKeys.push(k);
                  }
                }
              }
            }
          }
        }

        const cTableLines = [`table:${ccode}`, '@types', '_parent', '_idx', ...childFlatKeys, '@rows'];

        for (let rIdx = 0; rIdx < records.length; rIdx++) {
          let curr = records[rIdx];
          const parts = arrField.split('.');
          for (const p of parts) {
            if (!curr) break;
            curr = curr[p];
          }
          if (Array.isArray(curr)) {
            for (let iIdx = 0; iIdx < curr.length; iIdx++) {
              const item = curr[iIdx];
              const vals = [String(rIdx), String(iIdx)];
              for (const k of childFlatKeys) {
                vals.push(item && item[k] !== undefined ? encodeScalar(item[k]) : '#');
              }
              cTableLines.push(vals.join('|'));
            }
          }
        }
        childTables.push(cTableLines.join('\n'));
      }
    }

    out.push('@rows');
    out.push(...rows);

    let finalStr = out.join('\n');
    if (childTables.length > 0) {
      finalStr += '\n===\n' + childTables.join('\n===\n');
    }
    return finalStr;
  }

  // --- Subword Token Estimator (calibrated for GPT-4o o200k & Claude) ---
  function estimateTokens(text) {
    if (!text) return 0;
    let tokens = 0;
    // Regex matches words, numbers, CJK glyphs, and punctuation blocks
    const regex = /[\u4e00-\u9fa5]|[\u3040-\u30ff]|\w+|[^\w\s]|\s+/g;
    let match;
    while ((match = regex.exec(text)) !== null) {
      const piece = match[0];
      if (/^[\u4e00-\u9fa5\u3040-\u30ff]$/.test(piece)) {
        tokens += 1;
      } else if (/^\s+$/.test(piece)) {
        tokens += Math.ceil(piece.length / 4);
      } else if (/^\d+$/.test(piece)) {
        tokens += Math.ceil(piece.length / 3);
      } else if (piece.length <= 4) {
        tokens += 1;
      } else {
        tokens += Math.ceil(piece.length / 3.8);
      }
    }
    return Math.max(1, tokens);
  }

  return {
    encode: encode,
    decode: decode,
    estimateTokens: estimateTokens,
  };
});
