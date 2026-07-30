import type { MachineSection } from "@/lib/board-types";

export function MachineCard({ machine }: { machine: MachineSection }) {
  const diskWarn = machine.disk_pct >= 90;
  const failedWarn = machine.failed_units > 0;
  const netWarn = machine.net === "down";
  const aptWarn = machine.apt_updates > 50;

  return (
    <section className="board-card" data-accent="blue" aria-label="machine">
      <h2 className="board-card-title" data-accent="blue">
        machine
      </h2>
      <div className="machine-strip">
        <span>
          disk{" "}
          <span className={diskWarn ? "warn-val tabular" : "tabular"}>
            {machine.disk_pct.toFixed(0)}%
          </span>
        </span>
        <span>
          free{" "}
          <span className="tabular">{machine.free_gib.toFixed(1)} GiB</span>
        </span>
        <span>
          failed{" "}
          <span className={failedWarn ? "warn-val tabular" : "tabular"}>
            {machine.failed_units}
          </span>
        </span>
        <span>
          net{" "}
          <span className={netWarn ? "warn-val" : undefined}>{machine.net}</span>
        </span>
        <span>
          apt{" "}
          <span className={aptWarn ? "warn-val tabular" : "tabular"}>
            {machine.apt_updates}
          </span>
        </span>
      </div>
      <div className="board-card-footer">
        {machine.host}
        {machine.warn ? " · attention" : " · quiet"}
      </div>
    </section>
  );
}
