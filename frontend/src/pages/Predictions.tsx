import { PredictionsByHorizon } from './PredictionsByHorizon'
import { PredictionsByTarget } from './PredictionsByTarget'
import { Accuracy } from './Accuracy'
import { TabbedShell } from '../components/common/TabbedShell'

/**
 * Predictions tab shell. Phase 1 refactor — uses TabbedShell primitive.
 */
export function Predictions() {
  return (
    <TabbedShell
      basePath="/predictions"
      ariaLabel="Predictions view"
      tabs={[
        { id: 'horizon',  label: 'By Horizon', render: () => <PredictionsByHorizon /> },
        { id: 'target',   label: 'By Target',  render: () => <PredictionsByTarget /> },
        { id: 'accuracy', label: 'Accuracy',   render: () => <Accuracy /> },
      ]}
    />
  )
}

export default Predictions
