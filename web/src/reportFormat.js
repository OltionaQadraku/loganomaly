
export function parseReport(text) {
  if (!text) return null;

  const result = { whatHappened: '', why: [], means: '', check: '' };

  const whatHappened = text.match(/What happened:\s*(.+)/);
  if (whatHappened) result.whatHappened = whatHappened[1].trim();

  const why = text.match(/Why we think so:\n([\s\S]*?)(?:\n\nWhat this usually means:|$)/);
  if (why) {
    result.why = why[1]
      .split('\n')
      .map((line) => line.replace(/^\s*-\s*/, '').trim())
      .filter(Boolean);
  }

  const means = text.match(/What this usually means:\n\s*([\s\S]*?)(?:\n\nWhat to check:|$)/);
  if (means) result.means = means[1].trim();

  const check = text.match(/What to check:\n\s*([\s\S]*)$/);
  if (check) result.check = check[1].trim();

  return result;
}
