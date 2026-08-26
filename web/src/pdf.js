import jsPDF from 'jspdf';
import { parseReport } from './reportFormat';
import { riskDisplay } from './risk';

const MARGIN = 15;
const PAGE_WIDTH = 210; 
const PAGE_HEIGHT = 297;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

function makeWriter(doc) {
  let y = MARGIN;

  function ensureSpace(needed) {
    if (y + needed > PAGE_HEIGHT - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  }

  return {
    heading(text, size = 16) {
      ensureSpace(size / 2 + 4);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(size);
      doc.text(text, MARGIN, y);
      y += size / 2 + 4;
    },
    label(text) {
      ensureSpace(6);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.text(text, MARGIN, y);
      y += 6;
    },
    paragraph(text, size = 10) {
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(size);
      const lines = doc.splitTextToSize(text, CONTENT_WIDTH);
      for (const line of lines) {
        ensureSpace(size / 2 + 2);
        doc.text(line, MARGIN, y);
        y += size / 2 + 2;
      }
    },
    bullet(text, size = 10) {
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(size);
      const lines = doc.splitTextToSize(`- ${text}`, CONTENT_WIDTH - 4);
      for (const line of lines) {
        ensureSpace(size / 2 + 2);
        doc.text(line, MARGIN + 2, y);
        y += size / 2 + 2;
      }
    },
    spacer(h = 4) {
      y += h;
    },
    rule() {
      ensureSpace(6);
      doc.setDrawColor(210);
      doc.line(MARGIN, y, PAGE_WIDTH - MARGIN, y);
      y += 6;
    },
  };
}

export function downloadAnalysisPdf(meta, groups) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const w = makeWriter(doc);
  const risk = riskDisplay(meta.risk_level);

  w.heading('LogSense analysis report', 18);
  w.paragraph(`File: ${meta.filename || 'Unknown'}`);
  if (meta.analyzed_at) {
    w.paragraph(`Analyzed: ${new Date(meta.analyzed_at).toLocaleString()}`);
  }
  w.spacer(2);
  if (meta.message) w.paragraph(meta.message);
  w.spacer(2);
  w.paragraph(
    `Lines read: ${meta.total_lines ?? 'N/A'}    Issues found: ${meta.anomalies_found ?? groups.length}    ` +
    `Risk level: ${risk.label}    Anomaly rate: ${meta.anomaly_rate ?? 'N/A'}%`
  );
  w.rule();

  if (!groups.length) {
    w.paragraph('No issues were found in this file.');
  }

  groups.forEach((group, i) => {
    w.heading(`${i + 1}. ${group.title}`, 13);
    w.paragraph(`Severity: ${group.severity}.  Found in ${group.examples.length} section(s).`);
    w.spacer(2);

    const sections = parseReport(group.report);
    if (sections) {
      if (sections.why.length) {
        w.label('Why we think so');
        sections.why.forEach((line) => w.bullet(line));
        w.spacer(2);
      }
      if (sections.means) {
        w.label('What this usually means');
        w.paragraph(sections.means);
        w.spacer(2);
      }
      if (sections.check) {
        w.label('What to check');
        w.paragraph(sections.check);
      }
    }
    w.spacer(6);
  });

  const safeName = (meta.filename || 'analysis').replace(/[^\w.-]+/g, '_');
  doc.save(`logsense-${safeName}.pdf`);
}
