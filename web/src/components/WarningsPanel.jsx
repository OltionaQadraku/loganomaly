export default function WarningsPanel({ warnings }) {
  if (!warnings?.length) return null;

  return (
    <div className="panel warnings-panel">
      {warnings.map((warning, i) => (
        <p key={i} className="warning-line">{warning}</p>
      ))}
    </div>
  );
}
