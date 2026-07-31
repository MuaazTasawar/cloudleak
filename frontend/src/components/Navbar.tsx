export default function Navbar() {
  return (
    <nav className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[var(--color-accent)] font-bold text-lg">CloudLeak</span>
          <span className="text-xs text-[var(--color-text-muted)] border border-[var(--color-border)] rounded px-2 py-0.5">
            MVP
          </span>
        </div>
        <span className="text-sm text-[var(--color-text-muted)]">AWS Cost Anomaly Detection</span>
      </div>
    </nav>
  );
}
