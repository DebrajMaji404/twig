/**
 * Twig JavaScript Codec (twig.js)
 * Pure, zero-dependency browser and Node.js implementation of the Twig serialization format.
 * Enables zero-latency in-browser encoding, decoding, and token estimation.
 * Supports Twig 2.0 specification with backward compatibility for legacy text.
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

  const FIELD_SEP = '|';
  const LIST_SEP = '^';
  const LIST_MARK = '*';
  const STR_MARK = "'";
  const ABSENT_TOKEN = '!';
  const NULL_TOKEN = '';
  const OLD_NULL_TOKEN = '#';
  const LIST_NULL = '#';
  const ABSENT = Symbol('ABSENT');

  const NUM_RE = /^-?[1-9]\d*|0$/;
  const FLOAT_RE = /^-?(?:\d+\.?\d*|\.\d+)[eE][+-]?\d+|-?\d+\.\d+$/;

  // --- Escaping utilities ---
  function escapeValue(val) {
    if (typeof val !== 'string') return String(val);
    return val
      .replace(/\\/g, '\\\\')
      .replace(/\n/g, '\\n')
      .replace(/\|/g, '\\|')
      .replace(/\^/g, '\\^');
  }

  function unescapeValue(val) {
    if (typeof val !== 'string') return val;
    let res = '';
    let i = 0;
    const n = val.length;
    while (i < n) {
      if (val[i] === '\\' && i + 1 < n) {
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

  function awareSplit(s, sep) {
    if (!s.includes('\\')) return s.split(sep);
    const parts = [];
    const buf = [];
    let i = 0;
    const n = s.length;
    while (i < n) {
      const c = s[i];
      if (c === '\\' && i + 1 < n) {
        buf.push(c, s[i + 1]);
        i += 2;
        continue;
      }
      if (c === sep) {
        parts.push(buf.join(''));
        buf.length = 0;
        i++;
        continue;
      }
      buf.push(c);
      i++;
    }
    parts.push(buf.join(''));
    return parts;
  }

  function splitPath(path) {
    if (!path.includes('.')) {
      return [path.includes('\\') ? path.replace(/\\\./g, '.').replace(/\\\\/g, '\\') : path];
    }
    if (!path.includes('\\')) {
      return path.split('.');
    }
    const parts = path.split(/(?<!\\)\./);
    return parts.map((p) => p.replace(/\\(.)/g, '$1'));
  }

  function escapeKey(k) {
    if (k.includes('.') || k.includes('\\')) {
      return k.replace(/\\/g, '\\\\').replace(/\./g, '\\.');
    }
    return k;
  }

  function decodeScalar(raw) {
    if (raw.startsWith(STR_MARK)) {
      return unescapeValue(raw.slice(1));
    }
    if (raw === NULL_TOKEN || raw === OLD_NULL_TOKEN) {
      return null;
    }
    if (raw === 'T' || raw === 'true') return true;
    if (raw === 'F' || raw === 'false') return false;

    if (raw.startsWith(LIST_MARK)) {
      const rest = raw.slice(1);
      if (rest === '') return [];
      const parts = awareSplit(rest, LIST_SEP);
      return parts.map((p) => (p === LIST_NULL ? null : decodeScalar(p)));
    }

    if (NUM_RE.test(raw)) {
      return parseInt(raw, 10);
    }
    if (FLOAT_RE.test(raw)) {
      return parseFloat(raw);
    }

    return unescapeValue(raw);
  }

  function encodeScalar(val) {
    if (val === null || val === undefined) return NULL_TOKEN;
    if (typeof val === 'boolean') return val ? 'T' : 'F';
    if (typeof val === 'number') return String(val);
    if (Array.isArray(val)) {
      if (val.length === 0) return LIST_MARK;
      return LIST_MARK + val.map((item) => (item === null || item === undefined ? LIST_NULL : encodeScalar(item))).join(LIST_SEP);
    }
    if (typeof val === 'string') {
      const needsMark = (
        val === 'true' ||
        val === 'false' ||
        val === 'T' ||
        val === 'F' ||
        val === '' ||
        val === ABSENT_TOKEN ||
        val === OLD_NULL_TOKEN ||
        val.startsWith(LIST_MARK) ||
        val.startsWith(STR_MARK) ||
        val.startsWith('&') ||
        (val.startsWith(ABSENT_TOKEN) && val.length > 1 && /^\d+$/.test(val.slice(1))) ||
        (val.startsWith(OLD_NULL_TOKEN) && val.length > 1 && /^\d+$/.test(val.slice(1))) ||
        NUM_RE.test(val) ||
        FLOAT_RE.test(val)
      );
      const escaped = escapeValue(val);
      return needsMark ? STR_MARK + escaped : escaped;
    }
    return escapeValue(String(val));
  }

  // --- Parser / Decoder ---
  function decode(text) {
    if (!text) return [];

    let shape = 'list';
    let content = text;
    if (content.startsWith('~L\n') || content.startsWith('~L\r\n')) {
      shape = 'list';
      content = content.replace(/^~L\r?\n/, '');
    } else if (content.startsWith('~S\n') || content.startsWith('~S\r\n')) {
      shape = 'single';
      content = content.replace(/^~S\r?\n/, '');
    } else if (content.startsWith('@shape:')) {
      const firstLineEnd = content.indexOf('\n');
      const marker = content.slice(0, firstLineEnd).trim();
      shape = marker.slice('@shape:'.length).trim();
      content = content.slice(firstLineEnd + 1);
    }

    const rawBlocks = content.split(/\r?\n===\r?\n/);
    const tables = {};

    for (const rawBlock of rawBlocks) {
      const block = rawBlock.trim();
      if (!block) continue;
      const lines = block.split(/\r?\n/);

      let tableCode = 'root';
      const firstLine = lines[0].trim();
      if (firstLine.startsWith('T:')) {
        tableCode = firstLine.slice(2).trim();
      } else if (firstLine.startsWith('table:')) {
        tableCode = firstLine.slice(6).trim();
      }

      const sections = {};
      let currentSection = null;

      for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.startsWith('@')) {
          if (line.includes(':') && !line.startsWith('@rows')) {
            const colonIdx = line.indexOf(':');
            const sname = line.slice(1, colonIdx);
            const inline = line.slice(colonIdx + 1);
            sections[sname] = inline ? [inline] : [];
            currentSection = null;
          } else {
            const sname = line.slice(1).trim();
            sections[sname] = [];
            currentSection = sname;
          }
        } else if (currentSection !== null) {
          sections[currentSection].push(line);
        }
      }

      // Parse @tree
      const levelName = {};
      const levelParentCode = {};
      for (const rawLine of sections.tree || []) {
        const entries = rawLine.includes(',') ? rawLine.split(',') : [rawLine];
        for (let entry of entries) {
          entry = entry.trim();
          if (!entry) continue;
          const [code, rest] = entry.split('=', 2);
          const [name, pcode] = rest.split('^', 2);
          levelName[code.trim()] = name.trim();
          levelParentCode[code.trim()] = (!pcode || pcode.trim() === '-') ? null : pcode.trim();
        }
      }

      function fullPath(lvlCode, leaf) {
        if (levelName[lvlCode]) {
          const chain = [];
          let code = lvlCode;
          while (code) {
            chain.push(escapeKey(levelName[code]));
            code = levelParentCode[code];
          }
          return chain.reverse().join('.') + '.' + leaf;
        }
        return `${lvlCode}.${leaf}`;
      }

      function levelOnlyPath(lvlCode) {
        const chain = [];
        let code = lvlCode;
        while (code) {
          chain.push(escapeKey(levelName[code]));
          code = levelParentCode[code];
        }
        return chain.reverse().join('.');
      }

      const levelFullPaths = {};
      for (const code of Object.keys(levelName)) {
        levelFullPaths[code] = levelOnlyPath(code);
      }

      // Parse @types
      const fieldOrder = [];
      for (const rawLine of sections.types || []) {
        if (!rawLine) continue;
        let items = [];
        if (rawLine.includes(',')) items = rawLine.split(',');
        else if (rawLine.includes(FIELD_SEP)) items = awareSplit(rawLine, FIELD_SEP);
        else items = [rawLine];

        for (let item of items) {
          item = item.trim();
          if (!item) continue;
          const parts = item.split(/(?<!\\)\./);
          if (parts.length > 1) {
            const lvl = parts.slice(0, -1).join('.');
            const leaf = parts[parts.length - 1];
            fieldOrder.push(fullPath(lvl, leaf));
          } else {
            fieldOrder.push(item);
          }
        }
      }

      // Parse @arrays
      const arrayPath = {};
      const arrayOrder = [];
      for (const rawLine of sections.arrays || []) {
        if (!rawLine) continue;
        const entries = rawLine.includes(',') ? rawLine.split(',') : [rawLine];
        for (let entry of entries) {
          entry = entry.trim();
          if (!entry) continue;
          const [acode, rest] = entry.split('=', 2);
          const parts = rest.split(/(?<!\\)\./);
          if (parts.length > 1) {
            const lvl = parts.slice(0, -1).join('.');
            const leaf = parts[parts.length - 1];
            arrayPath[acode] = fullPath(lvl, leaf);
          } else {
            arrayPath[acode] = rest;
          }
          arrayOrder.push(acode);
        }
      }

      // Parse @dict
      const dictMap = {};
      for (const rawLine of sections.dict || []) {
        if (!rawLine) continue;
        const entries = rawLine.includes(',') ? rawLine.split(',') : [rawLine];
        for (let entry of entries) {
          entry = entry.trim();
          if (!entry) continue;
          const eqIdx = entry.indexOf('=');
          if (eqIdx !== -1) {
            dictMap[entry.slice(0, eqIdx).trim()] = entry.slice(eqIdx + 1);
          }
        }
      }

      // Parse @rows
      const rows = [];
      for (const line of sections.rows || []) {
        const rawVals = line ? awareSplit(line, FIELD_SEP) : [];
        const vals = [];
        for (let v of rawVals) {
          if (dictMap[v]) v = dictMap[v];
          if (v.startsWith(ABSENT_TOKEN) && v.length > 1 && /^\d+$/.test(v.slice(1))) {
            const cnt = parseInt(v.slice(1), 10);
            for (let c = 0; c < cnt; c++) vals.push(ABSENT_TOKEN);
          } else if (v === OLD_NULL_TOKEN) {
            vals.push(NULL_TOKEN);
          } else if (v.startsWith(OLD_NULL_TOKEN) && v.length > 1 && /^\d+$/.test(v.slice(1))) {
            const cnt = parseInt(v.slice(1), 10);
            for (let c = 0; c < cnt; c++) vals.push(NULL_TOKEN);
          } else {
            vals.push(v);
          }
        }

        const row = {};
        for (let idx = 0; idx < fieldOrder.length; idx++) {
          const path = fieldOrder[idx];
          if (idx < vals.length) {
            const val = vals[idx];
            row[path] = val === ABSENT_TOKEN ? ABSENT : decodeScalar(val);
          } else {
            row[path] = ABSENT;
          }
        }
        rows.push(row);
      }

      tables[tableCode] = {
        fieldOrder,
        arrayOrder,
        arrayPath,
        rows,
        levelFullPaths,
      };
    }

    function setDotted(record, path, value) {
      const parts = splitPath(path);
      let curr = record;
      for (let i = 0; i < parts.length - 1; i++) {
        const p = parts[i];
        if (!curr[p] || typeof curr[p] !== 'object') curr[p] = {};
        curr = curr[p];
      }
      curr[parts[parts.length - 1]] = value;
    }

    function buildRecord(tableCode, rowIndex) {
      const tbl = tables[tableCode];
      if (!tbl) return {};
      const row = tbl.rows[rowIndex];
      const record = {};

      // Fill leaf fields
      for (const path of Object.keys(row)) {
        if (path === '_parent' || path === '_idx') continue;
        if (path.startsWith('$has:') || path.startsWith('$lvl:')) continue;
        const val = row[path];
        if (val !== ABSENT) {
          setDotted(record, path, val);
        }
      }

      // Empty dict branches ($lvl:)
      for (const path of Object.keys(row)) {
        if (!path.startsWith('$lvl:') || row[path] !== true) continue;
        const code = path.slice('$lvl:'.length);
        const branchPath = tbl.levelFullPaths[code];
        if (!branchPath) continue;
        const parts = splitPath(branchPath);
        let curr = record;
        let exists = true;
        for (const p of parts) {
          if (!curr || typeof curr !== 'object' || !(p in curr)) {
            exists = false;
            break;
          }
          curr = curr[p];
        }
        if (!exists) {
          setDotted(record, branchPath, {});
        }
      }

      // Child arrays
      for (const acode of tbl.arrayOrder) {
        const hasFlag = row[`$has:${acode}`];
        if (hasFlag === false) continue;

        const childTableCode = acode;
        const arrFieldPath = tbl.arrayPath[acode];
        const childTbl = tables[childTableCode];
        let recordItems = [];

        if (childTbl) {
          const matching = [];
          for (let i = 0; i < childTbl.rows.length; i++) {
            const crow = childTbl.rows[i];
            if (crow._parent === rowIndex || crow._parent === String(rowIndex)) {
              const idxVal = crow._idx !== undefined ? parseInt(crow._idx, 10) : 0;
              matching.push({ idx: isNaN(idxVal) ? 0 : idxVal, rowIdx: i });
            }
          }
          matching.sort((a, b) => a.idx - b.idx);
          recordItems = matching.map((m) => buildRecord(childTableCode, m.rowIdx));
        }

        setDotted(record, arrFieldPath, recordItems);
      }

      return record;
    }

    const rootTable = tables.root;
    if (!rootTable) return [];
    const results = [];
    for (let i = 0; i < rootTable.rows.length; i++) {
      results.push(buildRecord('root', i));
    }

    if (shape === 'single') return results.length ? results[0] : {};
    return results;
  }

  // --- Fast Encoder ---
  function encode(data) {
    if (data === null || data === undefined) return '';
    const isSingle = !Array.isArray(data);
    const records = isSingle ? [data] : data;
    if (!records.length) return '';

    // Collect schema
    const flatFields = [];
    const arrayFields = [];

    function analyze(obj, prefix = '') {
      if (!obj || typeof obj !== 'object') return;
      for (const k of Object.keys(obj)) {
        const escaped = escapeKey(k);
        const fullKey = prefix ? `${prefix}.${escaped}` : escaped;
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

    function resolvePath(rec, path) {
      const parts = splitPath(path);
      let curr = rec;
      for (const p of parts) {
        if (!curr || typeof curr !== 'object' || !(p in curr)) return [false, null];
        curr = curr[p];
      }
      return [true, curr];
    }

    const rows = [];
    for (const r of records) {
      const vals = [];
      for (const f of flatFields) {
        const [found, val] = resolvePath(r, f);
        if (!found) {
          vals.push(ABSENT_TOKEN);
        } else {
          vals.push(encodeScalar(val));
        }
      }
      while (vals.length && vals[vals.length - 1] === ABSENT_TOKEN) {
        vals.pop();
      }
      rows.push(vals.join(FIELD_SEP));
    }

    const shape = isSingle ? '~S' : '~L';
    const lines = [shape, 'T:root'];
    if (flatFields.length) {
      lines.push(`@types:${flatFields.join(',')}`);
    }
    lines.push('@rows');
    lines.push(...rows);

    return lines.join('\n');
  }

  // --- Subword Token Estimator (calibrated for GPT-4o o200k & Claude) ---
  function estimateTokens(text) {
    if (!text) return 0;
    let tokens = 0;
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
