import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Accordion } from '../ui/accordion'
import type { AskResponse, ResearchQueryRead } from '../../lib/types'
import { EvidenceItemRow } from './EvidenceItemRow'
import { ProposedActionCard } from './ProposedActionCard'

interface Props {
  response: AskResponse | ResearchQueryRead
}

export function AnswerCard({ response }: Props) {
  const queryId = 'query_id' in response ? response.query_id : response.id
  const verdict = response.verdict ?? ''
  const evidence = response.evidence ?? []
  const proposed = response.proposed_action
  const status = response.status

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 py-3">
        <CardTitle className="text-base">Verdict</CardTitle>
        <div className="flex items-center gap-2">
          <Badge variant={status === 'approved' ? 'default' : 'outline'}>{status}</Badge>
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground tabular-nums">
            ${(response.est_cost_usd ?? 0).toFixed(4)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="prose prose-sm max-w-none text-foreground/90 leading-relaxed">
          {verdict ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{verdict}</ReactMarkdown>
          ) : (
            <span className="text-muted-foreground italic">No verdict text returned.</span>
          )}
        </div>

        {proposed && (
          <ProposedActionCard
            queryId={queryId}
            proposed={proposed}
            status={status}
          />
        )}

        <div className="space-y-1.5">
          <div className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            Evidence ({evidence.length})
          </div>
          {evidence.length === 0 ? (
            <div className="rounded-2xl shadow-inset-sm bg-background p-3 text-xs text-muted-foreground">
              No evidence retrieved. The vault-indexer may not be running — start it with{' '}
              <code className="font-mono">uvicorn tools.vault_indexer.app:app --port 8001</code>{' '}
              and the next query will retrieve excerpts.
            </div>
          ) : (
            <Accordion type="multiple" className="space-y-1.5">
              {evidence.map((e, i) => (
                <EvidenceItemRow
                  key={`${e.vault_path}-${i}`}
                  item={e}
                  value={`ev-${i}`}
                />
              ))}
            </Accordion>
          )}
        </div>

        {response.answer_path && (
          <div className="text-[10px] font-mono text-muted-foreground truncate">
            archive: <span className="text-foreground/70">{response.answer_path}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
