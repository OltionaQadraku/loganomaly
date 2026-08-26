
const RISK_LABEL = { CRITICAL: 'Critical', HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low' };
const RISK_TONE = { CRITICAL: 'critical', HIGH: 'critical', MEDIUM: 'warning', LOW: 'good' };

export function riskDisplay(riskLevel) {
  if (!riskLevel) return { label: 'None', tone: 'good' };
  return { label: RISK_LABEL[riskLevel] || 'Low', tone: RISK_TONE[riskLevel] || 'good' };
}
