export default function ErrorPanel({ error }) {
  const detail = error?.detail ?? {};
  const message = error?.message || 'Something went wrong.';
  const isFormatError = detail.reason === 'FORMAT_NOT_RECOGNISED';

  return (
    <div className="panel error-panel">
      <h2>We couldn't analyse this file</h2>
      <p className="error-message">{message}</p>

      {isFormatError && (
        <>
          {typeof detail.skipped_lines === 'number' && (
            <p className="error-meta">{detail.skipped_lines} line(s) were skipped.</p>
          )}
          {detail.sample_lines?.length > 0 && (
            <>
              <p className="error-meta">A few of those lines looked like this:</p>
              <pre className="sample-lines">{detail.sample_lines.join('\n')}</pre>
            </>
          )}
          <p className="error-hint">
            LogSense currently expects HDFS-style log lines, for example:
            <br />
            <code>081109 203615 148 INFO dfs.DataNode$PacketResponder: Received block blk_38 ...</code>
          </p>
        </>
      )}
    </div>
  );
}
