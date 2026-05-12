import { Schedule } from '../../pages/Schedule'

// Thin wrapper so the existing Schedule page renders unchanged inside the
// new admin tab shell. No props, no behaviour change. When Phase 4 ships
// the loop registry, manual fire/abort move into ProcessesTab; this stays
// dedicated to the daily-run schedule form.
export function SchedulePanel() {
  return <Schedule />
}
