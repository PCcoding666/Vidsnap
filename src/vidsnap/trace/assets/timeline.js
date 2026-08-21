// Pure timeline math for recorded trace events; inlined into exported pages.
// Paired completed/failed events record offset_ms at completion and
// duration_ms for the span, so the span ends at offset_ms and starts at
// max(0, offset_ms - duration_ms); started/unpaired events stay point markers.
const NOT_RECORDED = "未记录";

function isRecorded(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function formatMs(value) {
  if (!isRecorded(value)) return NOT_RECORDED;
  if (value >= 1000) return (value / 1000).toFixed(2) + " s";
  return String(value) + " ms";
}

function formatBytes(value) {
  if (!isRecorded(value)) return NOT_RECORDED;
  if (value >= 1048576) return (value / 1048576).toFixed(2) + " MiB";
  if (value >= 1024) return (value / 1024).toFixed(1) + " KiB";
  return String(value) + " B";
}

function isPairedSpan(item) {
  return (
    (item.status === "completed" || item.status === "failed") &&
    isRecorded(item.offset_ms) &&
    isRecorded(item.duration_ms)
  );
}

function itemSpan(item) {
  if (!isRecorded(item.offset_ms)) return null;
  if (isPairedSpan(item)) {
    const end = item.offset_ms;
    return [Math.max(0, end - item.duration_ms), end];
  }
  return [item.offset_ms, item.offset_ms];
}

function timelineSpan(doc) {
  let total = isRecorded(doc.duration_ms) ? doc.duration_ms : null;
  let maxEnd = 0;
  for (const item of doc.items) {
    const span = itemSpan(item);
    if (span !== null && span[1] > maxEnd) maxEnd = span[1];
  }
  if (total === null || maxEnd > total) total = maxEnd;
  return total > 0 ? total : null;
}
