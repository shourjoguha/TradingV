import { Component, ReactNode } from 'react'

interface Props {
  fallback?: ReactNode
  label?: string
  children: ReactNode
}

interface State {
  hasError: boolean
  message?: string
}

export class TabErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err?.message ?? 'Render error' }
  }

  componentDidCatch(err: Error) {
    // eslint-disable-next-line no-console
    console.error('[admin tab error]', this.props.label ?? 'tab', err)
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
            <div className="font-medium">Tab failed to render</div>
            <div className="text-xs text-muted-foreground mt-1">
              {this.state.message ?? 'unknown error'}
            </div>
          </div>
        )
      )
    }
    return this.props.children
  }
}
