import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  // Sanitize raw html breaks and line breaks before parsing blocks
  const normalized = content
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<hr\s*\/?>/gi, '\n---\n');

  const blocks = parseMarkdownBlocks(normalized);

  return (
    <div className="markdown-content" style={{ lineHeight: 1.65, fontSize: '13.5px', color: 'hsl(var(--fg))' }}>
      {blocks.map((block, index) => (
        <React.Fragment key={index}>{renderBlock(block)}</React.Fragment>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Block Parsing & Data Structures
// ---------------------------------------------------------------------------

type Block =
  | { type: 'heading'; level: number; text: string }
  | { type: 'code'; language: string; code: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }
  | { type: 'blockquote'; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'divider' };

function parseMarkdownBlocks(text: string): Block[] {
  const lines = text.split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 1. Fenced Code Blocks
    if (line.trim().startsWith('```')) {
      const language = line.trim().replace(/^```/, '').trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: 'code', language, code: codeLines.join('\n') });
      continue;
    }

    // 2. Horizontal Rules
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) {
      blocks.push({ type: 'divider' });
      i++;
      continue;
    }

    // 3. Headings
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      blocks.push({
        type: 'heading',
        level: headingMatch[1].length,
        text: headingMatch[2].trim(),
      });
      i++;
      continue;
    }

    // 4. Blockquotes
    if (line.trim().startsWith('>')) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].replace(/^>\s?/, ''));
        i++;
      }
      blocks.push({ type: 'blockquote', text: quoteLines.join(' ') });
      continue;
    }

    // 5. Tables
    if (line.includes('|') && i + 1 < lines.length && lines[i + 1].includes('|') && /[-:]+/.test(lines[i + 1])) {
      const headers = parseTableRow(line);
      i += 2; // skip header and separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|')) {
        const row = parseTableRow(lines[i]);
        if (row.length > 0) rows.push(row);
        i++;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    // 6. Unordered List
    if (/^[*+-]\s+/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length && /^[*+-]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[*+-]\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ul', items });
      continue;
    }

    // 7. Ordered List
    if (/^\d+\.\s+/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
        i++;
      }
      blocks.push({ type: 'ol', items });
      continue;
    }

    // 8. Empty lines
    if (!line.trim()) {
      i++;
      continue;
    }

    // 9. Regular Paragraph
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith('```') &&
      !lines[i].trim().startsWith('#') &&
      !lines[i].trim().startsWith('>') &&
      !/^[*+-]\s+/.test(lines[i].trim()) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !(lines[i].includes('|') && i + 1 < lines.length && lines[i + 1].includes('|') && /[-:]+/.test(lines[i + 1]))
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    blocks.push({ type: 'paragraph', text: paraLines.join('\n') });
  }

  return blocks;
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim());
}

// ---------------------------------------------------------------------------
// Block Rendering
// ---------------------------------------------------------------------------

function renderBlock(block: Block): React.ReactNode {
  switch (block.type) {
    case 'heading': {
      const Tag = `h${Math.min(block.level + 1, 6)}` as keyof React.JSX.IntrinsicElements;
      const size = block.level === 1 ? '17px' : block.level === 2 ? '15px' : '14px';
      const weight = block.level <= 2 ? 600 : 500;
      return (
        <Tag style={{ fontSize: size, fontWeight: weight, margin: '14px 0 6px', color: 'hsl(var(--fg))' }}>
          {renderInline(block.text)}
        </Tag>
      );
    }

    case 'code':
      return <CodeBlock code={block.code} language={block.language} />;

    case 'table':
      return (
        <div style={{ overflowX: 'auto', margin: '12px 0', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px', textAlign: 'left' }}>
            <thead>
              <tr style={{ backgroundColor: 'hsl(var(--muted)/0.5)', borderBottom: '1px solid hsl(var(--border))' }}>
                {block.headers.map((th, idx) => (
                  <th key={idx} style={{ padding: '8px 12px', fontWeight: 600 }}>
                    {renderInline(th)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rIdx) => (
                <tr
                  key={rIdx}
                  style={{
                    borderBottom: rIdx < block.rows.length - 1 ? '1px solid hsl(var(--border)/0.5)' : 'none',
                    backgroundColor: rIdx % 2 === 1 ? 'hsl(var(--muted)/0.15)' : 'transparent',
                  }}
                >
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} style={{ padding: '8px 12px' }}>
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case 'ul':
      return (
        <ul style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'disc' }}>
          {block.items.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );

    case 'ol':
      return (
        <ol style={{ margin: '8px 0', paddingLeft: '20px', listStyleType: 'decimal' }}>
          {block.items.map((item, idx) => (
            <li key={idx} style={{ marginBottom: '4px' }}>
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );

    case 'blockquote':
      return (
        <blockquote
          style={{
            margin: '10px 0',
            padding: '8px 14px',
            borderLeft: '3px solid hsl(var(--primary))',
            backgroundColor: 'hsl(var(--primary)/0.05)',
            borderRadius: '0 6px 6px 0',
            color: 'hsl(var(--muted-fg))',
            fontStyle: 'italic',
          }}
        >
          {renderInline(block.text)}
        </blockquote>
      );

    case 'divider':
      return <hr style={{ border: 'none', borderTop: '1px solid hsl(var(--border))', margin: '14px 0' }} />;

    case 'paragraph':
      return (
        <p style={{ margin: '6px 0', whiteSpace: 'pre-wrap' }}>
          {renderInline(block.text)}
        </p>
      );
  }
}

// ---------------------------------------------------------------------------
// Code Block with Copy Action
// ---------------------------------------------------------------------------

function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  return (
    <div
      style={{
        margin: '10px 0',
        borderRadius: '8px',
        border: '1px solid hsl(var(--border))',
        backgroundColor: 'hsl(var(--muted)/0.3)',
        overflow: 'hidden',
        fontSize: '12.5px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 10px',
          borderBottom: '1px solid hsl(var(--border)/0.5)',
          backgroundColor: 'hsl(var(--muted)/0.5)',
          fontSize: '11px',
          fontFamily: 'var(--font-mono)',
          color: 'hsl(var(--muted-fg))',
        }}
      >
        <span>{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="btn btn-ghost"
          style={{ padding: '2px 6px', fontSize: '11px', gap: '4px', height: '22px' }}
        >
          {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
          <span>{copied ? 'Copiato' : 'Copia'}</span>
        </button>
      </div>
      <pre
        style={{
          margin: 0,
          padding: '12px 14px',
          overflowX: 'auto',
          fontFamily: 'var(--font-mono)',
          lineHeight: 1.5,
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline Renderer (Bold, Italic, Inline Code, Links)
// ---------------------------------------------------------------------------

function renderInline(text: string): React.ReactNode {
  if (!text) return null;

  // Split by inline code first: `code`
  const codeParts = text.split(/(`[^`]+`)/g);

  return codeParts.map((part, pIdx) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={pIdx}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '0.9em',
            padding: '2px 5px',
            borderRadius: '4px',
            backgroundColor: 'hsl(var(--muted))',
            color: 'hsl(var(--primary))',
          }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    // Bold & Italic: **bold** or *italic*
    const formattedParts = part.split(/(\*\*[^*]+\*\*|\*[^*]+\*|__[^_]+__)/g);

    return (
      <React.Fragment key={pIdx}>
        {formattedParts.map((fPart, fIdx) => {
          if ((fPart.startsWith('**') && fPart.endsWith('**')) || (fPart.startsWith('__') && fPart.endsWith('__'))) {
            return <strong key={fIdx}>{fPart.slice(2, -2)}</strong>;
          }
          if (fPart.startsWith('*') && fPart.endsWith('*') && fPart.length > 2) {
            return <em key={fIdx}>{fPart.slice(1, -1)}</em>;
          }
          return fPart;
        })}
      </React.Fragment>
    );
  });
}
