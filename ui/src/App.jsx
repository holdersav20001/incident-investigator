import { useState, useEffect } from 'react'
import './App.css'

// ---------------------------------------------------------------------------
// Pipeline step definitions — drives both the form and the results view
// ---------------------------------------------------------------------------

const PIPELINE_STEPS = [
  {
    key: 'classification',
    label: 'Classification',
    description: 'Categorises the error using keyword rules (no LLM needed)',
    statusAfter: 'CLASSIFIED',
  },
  {
    key: 'diagnosis',
    label: 'Diagnosis',
    description: 'Identifies root cause and affected components (LLM)',
    statusAfter: 'DIAGNOSED',
  },
  {
    key: 'remediation',
    label: 'Remediation Plan',
    description: 'Proposes concrete fix steps and a rollback plan (LLM)',
    statusAfter: 'REMEDIATION_PROPOSED',
  },
  {
    key: 'simulation',
    label: 'Safety Simulation',
    description: 'Checks the plan for destructive SQL or unsafe operations',
    statusAfter: null, // bundled with remediation in the pipeline
  },
  {
    key: 'risk',
    label: 'Risk Assessment',
    description: 'Scores risk 0–100 based on environment, confidence, plan safety',
    statusAfter: 'RISK_ASSESSED',
  },
  {
    key: 'decision',
    label: 'Approval Decision',
    description: 'Routes to auto-approve, human review queue, or auto-reject',
    statusAfter: null,
  },
]

const TERMINAL_STATUSES = new Set(['APPROVED', 'REJECTED', 'APPROVAL_REQUIRED'])

const STATUS_COLOR = {
  RECEIVED:             '#6b7280',
  CLASSIFIED:           '#3b82f6',
  DIAGNOSED:            '#8b5cf6',
  REMEDIATION_PROPOSED: '#f59e0b',
  RISK_ASSESSED:        '#f97316',
  APPROVAL_REQUIRED:    '#facc15',
  APPROVED:             '#10b981',
  REJECTED:             '#ef4444',
}

const STATUS_LABEL = {
  RECEIVED:             'Received — not yet processed',
  CLASSIFIED:           'Classified — pipeline stalled here',
  DIAGNOSED:            'Diagnosed — pipeline stalled here',
  REMEDIATION_PROPOSED: 'Remediation proposed — pipeline stalled here',
  RISK_ASSESSED:        'Risk assessed — pipeline stalled here',
  APPROVAL_REQUIRED:    'Awaiting human approval',
  APPROVED:             'Auto-approved — low risk, safe to execute',
  REJECTED:             'Auto-rejected — unsafe plan or high risk',
}

const RISK_COLOR = { LOW: '#10b981', MEDIUM: '#f59e0b', HIGH: '#ef4444' }

const ERROR_TYPES = [
  'schema_mismatch', 'timeout', 'memory_error',
  'data_quality', 'connection_error', 'null_pointer', 'pipeline_failure', 'custom...',
]

// ---------------------------------------------------------------------------
// Step state logic — determines complete / failed / skipped per step
// ---------------------------------------------------------------------------

function getStepState(stepKey, incident) {
  const hasData = {
    classification: !!incident.classification,
    diagnosis:      !!incident.diagnosis,
    remediation:    !!incident.remediation,
    simulation:     !!incident.simulation,
    risk:           !!incident.risk,
    decision:       TERMINAL_STATUSES.has(incident.final_status || incident.status),
  }

  if (hasData[stepKey]) return 'complete'

  // Find index of last complete step
  const keys = PIPELINE_STEPS.map(s => s.key)
  const lastComplete = keys.reduce((acc, k, i) => hasData[k] ? i : acc, -1)
  const thisIdx = keys.indexOf(stepKey)

  if (thisIdx === lastComplete + 1 && incident.pipeline_error) return 'failed'
  return 'skipped'
}

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function Badge({ label, color, small }) {
  return (
    <span className={`badge ${small ? 'badge-sm' : ''}`} style={{ background: color }}>
      {label}
    </span>
  )
}

function ProgressBar({ value, color, max = 100 }) {
  const pct = Math.min(100, Math.round((value / max) * 100))
  return (
    <div className="progress-track">
      <div className="progress-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="progress-label">{value}</span>
    </div>
  )
}

function KV({ label, children }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{children}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Event form
// ---------------------------------------------------------------------------

function EventForm({ onResult, onLoading }) {
  const [form, setForm] = useState({
    source: 'airflow',
    environment: 'prod',
    job_name: '',
    error_type: 'schema_mismatch',
    error_message: '',
  })
  const [customType, setCustomType] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const set = field => e => setForm(f => ({ ...f, [field]: e.target.value }))

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    onLoading(true)

    try {
      const incident_id = crypto.randomUUID()

      const ingestRes = await fetch('/events/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          incident_id,
          source: form.source,
          environment: form.environment,
          job_name: form.job_name,
          error_type: form.error_type,
          error_message: form.error_message,
          timestamp: new Date().toISOString(),
        }),
      })
      if (!ingestRes.ok) {
        const err = await ingestRes.json()
        throw new Error(err.message || `Ingest failed (${ingestRes.status})`)
      }
      const { incident_id: id } = await ingestRes.json()

      const investRes = await fetch(`/incidents/${id}/investigate`, { method: 'POST' })
      const investData = await investRes.json()

      const detailRes = await fetch(`/incidents/${id}`)
      const detail = await detailRes.json()

      onResult({
        ...detail,
        final_status: investData.final_status,
        pipeline_error: investData.error || null,
        job_name: form.job_name,
        source: form.source,
      })
    } catch (err) {
      setError(err.message)
      onLoading(false)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="event-form" onSubmit={handleSubmit}>
      <div className="form-grid">
        <label>
          Source
          <select value={form.source} onChange={set('source')}>
            <option value="airflow">Airflow</option>
            <option value="cloudwatch">CloudWatch</option>
            <option value="manual">Manual</option>
            <option value="other">Other</option>
          </select>
        </label>

        <label>
          Environment
          <select value={form.environment} onChange={set('environment')}>
            <option value="prod">Production</option>
            <option value="staging">Staging</option>
            <option value="dev">Development</option>
          </select>
        </label>

        <label className="span-2">
          Job Name
          <input
            type="text"
            value={form.job_name}
            onChange={set('job_name')}
            placeholder="e.g. cdc_orders, etl_customers"
            required
          />
        </label>

        <label className="span-2">
          Error Type
          {!customType ? (
            <select
              value={form.error_type}
              onChange={e => {
                if (e.target.value === 'custom...') {
                  setCustomType(true)
                  setForm(f => ({ ...f, error_type: '' }))
                } else set('error_type')(e)
              }}
            >
              {ERROR_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
          ) : (
            <input
              type="text"
              value={form.error_type}
              onChange={set('error_type')}
              placeholder="Enter error type..."
              autoFocus required
            />
          )}
        </label>

        <label className="span-2">
          Error Message
          <textarea
            value={form.error_message}
            onChange={set('error_message')}
            placeholder="Paste the error message or describe the incident in detail..."
            rows={5}
            required
          />
        </label>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <button className="submit-btn" type="submit" disabled={submitting}>
        {submitting ? 'Investigating...' : 'Run Investigation'}
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Individual step renderers
// ---------------------------------------------------------------------------

function ClassificationDetail({ data }) {
  if (!data) return null
  const conf = Math.round((data.confidence ?? 0) * 100)
  const confColor = conf >= 80 ? '#10b981' : conf >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <>
      <KV label="Type">
        <Badge label={data.type} color="#3b82f6" />
      </KV>
      <KV label="Confidence">
        <ProgressBar value={conf} color={confColor} />
      </KV>
      {data.reasoning && <div className="reasoning">{data.reasoning}</div>}
    </>
  )
}

function DiagnosisDetail({ data }) {
  if (!data) return null
  return (
    <>
      <KV label="Root cause">{data.root_cause}</KV>
      {data.affected_components?.length > 0 && (
        <KV label="Affected">
          <div className="tag-row">
            {data.affected_components.map(c => <span key={c} className="tag">{c}</span>)}
          </div>
        </KV>
      )}
      {data.next_checks?.length > 0 && (
        <KV label="Next checks">
          <ul className="inline-list">
            {data.next_checks.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </KV>
      )}
    </>
  )
}

function RemediationDetail({ data }) {
  if (!data) return null
  const steps = data.plan ?? data.steps ?? []
  return (
    <>
      {steps.length > 0 && (
        <KV label="Steps">
          <ol className="remediation-steps">
            {steps.map((s, i) => (
              <li key={i}>
                {typeof s === 'string' ? s : s.step || s.description || JSON.stringify(s)}
                {s.tool && <span className="tool-badge">{s.tool}</span>}
              </li>
            ))}
          </ol>
        </KV>
      )}
      {(data.expected_time_minutes || data.estimated_duration) && (
        <KV label="Est. time">
          {data.expected_time_minutes
            ? `${data.expected_time_minutes} min`
            : data.estimated_duration}
        </KV>
      )}
      {data.rollback?.length > 0 && (
        <KV label="Rollback">
          <ul className="inline-list">
            {data.rollback.map((r, i) => <li key={i}>{typeof r === 'string' ? r : r.step}</li>)}
          </ul>
        </KV>
      )}
    </>
  )
}

function SimulationDetail({ data }) {
  if (!data) return null
  const safe = data.ok ?? data.safe
  return (
    <>
      <KV label="Safe to run">
        <Badge label={safe ? 'YES — safe' : 'NO — blocked'} color={safe ? '#10b981' : '#dc2626'} />
      </KV>
      {data.checks?.length > 0 && (
        <KV label="Checks">
          <div className="checks-list">
            {data.checks.map((c, i) => (
              <div key={i} className={`check-row ${c.ok ? 'check-ok' : 'check-fail'}`}>
                <span>{c.ok ? '✓' : '✗'}</span>
                <span>{c.name}</span>
                {c.value != null && <span className="check-val">{String(c.value)}</span>}
              </div>
            ))}
          </div>
        </KV>
      )}
      {(data.notes ?? data.issues)?.length > 0 && (
        <KV label="Notes">
          <ul className="issues">
            {(data.notes ?? data.issues).map((n, i) => <li key={i}>{n}</li>)}
          </ul>
        </KV>
      )}
    </>
  )
}

function RiskDetail({ data }) {
  if (!data) return null
  // API returns risk_score / risk_level (snake_case from Pydantic model)
  const score = data.risk_score ?? data.score
  const level = data.risk_level ?? data.level
  return (
    <>
      <KV label="Score">
        <ProgressBar value={score} color={RISK_COLOR[level] || '#6b7280'} />
      </KV>
      <KV label="Level">
        <Badge label={level} color={RISK_COLOR[level] || '#6b7280'} />
      </KV>
      {data.rationale && <div className="reasoning">{data.rationale}</div>}
      {data.recommendation && (
        <KV label="Recommendation">{data.recommendation.replace(/_/g, ' ')}</KV>
      )}
    </>
  )
}

function DecisionDetail({ incident }) {
  const outcome = incident.final_status || incident.status
  const color = STATUS_COLOR[outcome] || '#6b7280'
  return (
    <>
      <KV label="Outcome">
        <Badge label={outcome} color={color} />
      </KV>
      <div className="reasoning" style={{ marginTop: 8 }}>
        {STATUS_LABEL[outcome] || outcome}
      </div>
      {incident.approval_status && !TERMINAL_STATUSES.has(incident.approval_status) && (
        <KV label="Approval status">{incident.approval_status}</KV>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Step card — wraps each pipeline step with header + state indicator
// ---------------------------------------------------------------------------

function StepCard({ step, state, incident }) {
  const dataMap = {
    classification: incident.classification,
    diagnosis:      incident.diagnosis,
    remediation:    incident.remediation,
    simulation:     incident.simulation,
    risk:           incident.risk,
    decision:       incident,
  }
  const data = dataMap[step.key]

  return (
    <div className={`step-card state-${state}`}>
      <div className="step-header">
        <div className="step-header-left">
          <span className={`step-dot dot-${state}`} />
          <div>
            <div className="step-title">{step.label}</div>
            <div className="step-desc">{step.description}</div>
          </div>
        </div>
        <span className={`step-state-label state-label-${state}`}>
          {state === 'complete' ? 'Done' : state === 'failed' ? 'Failed' : 'Skipped'}
        </span>
      </div>

      {state === 'complete' && (
        <div className="step-body">
          {step.key === 'classification' && <ClassificationDetail data={data} />}
          {step.key === 'diagnosis'      && <DiagnosisDetail data={data} />}
          {step.key === 'remediation'    && <RemediationDetail data={data} />}
          {step.key === 'simulation'     && <SimulationDetail data={data} />}
          {step.key === 'risk'           && <RiskDetail data={data} />}
          {step.key === 'decision'       && <DecisionDetail incident={incident} />}
        </div>
      )}

      {state === 'failed' && incident.pipeline_error && (
        <div className="step-error">
          <strong>Error:</strong> {incident.pipeline_error}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pipeline view
// ---------------------------------------------------------------------------

function PipelineView({ incident }) {
  const outcome = incident.final_status || incident.status
  const outcomeColor = STATUS_COLOR[outcome] || '#6b7280'
  const isComplete = TERMINAL_STATUSES.has(outcome)

  return (
    <div className="pipeline-view">

      {/* Incident header */}
      <div className="pipeline-header">
        <div className="pipeline-meta">
          <div className="pipeline-job">{incident.job_name || 'Incident'}</div>
          <div className="pipeline-attrs">
            {incident.environment && <span className="attr-chip">{incident.environment}</span>}
            {incident.source      && <span className="attr-chip">{incident.source}</span>}
            <span className="attr-chip mono">#{incident.incident_id?.slice(0, 8)}</span>
          </div>
        </div>
        <div className="pipeline-outcome">
          <Badge label={outcome} color={outcomeColor} />
          <div className="outcome-desc">{STATUS_LABEL[outcome]}</div>
        </div>
      </div>

      {/* Pipeline error banner */}
      {incident.pipeline_error && (
        <div className="pipeline-error-banner">
          <strong>Pipeline halted.</strong> {incident.pipeline_error}
          {incident.pipeline_error.includes('KeyError') && (
            <span>
              {' '}— The LLM has no scripted response for this call.
              Set <code>LLM_PROVIDER=anthropic</code> and <code>ANTHROPIC_API_KEY</code> for real AI analysis.
            </span>
          )}
        </div>
      )}

      {/* Progress bar */}
      <div className="pipeline-progress">
        {PIPELINE_STEPS.map((step, i) => {
          const state = getStepState(step.key, incident)
          return (
            <div key={step.key} className={`progress-segment seg-${state}`}>
              <div className={`seg-dot seg-dot-${state}`} />
              {i < PIPELINE_STEPS.length - 1 && (
                <div className={`seg-line seg-line-${state === 'complete' ? 'complete' : 'pending'}`} />
              )}
            </div>
          )
        })}
      </div>

      {/* All steps */}
      <div className="steps">
        {PIPELINE_STEPS.map(step => (
          <StepCard
            key={step.key}
            step={step}
            state={getStepState(step.key, incident)}
            incident={incident}
          />
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

function Sidebar({ history, selectedId, onSelect, onNew }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <span>History</span>
        <button className="new-btn" onClick={onNew}>+ New</button>
      </div>
      {history.length === 0 ? (
        <div className="history-empty">No investigations yet</div>
      ) : (
        <ul className="history-list">
          {history.map(inc => {
            const outcome = inc.final_status || inc.status
            return (
              <li
                key={inc.incident_id}
                className={`history-item ${selectedId === inc.incident_id ? 'active' : ''}`}
                onClick={() => onSelect(inc)}
              >
                <div className="history-job">{inc.job_name || inc.incident_id?.slice(0, 8)}</div>
                <div className="history-meta">
                  <span className="history-env">{inc.environment}</span>
                  <span className="history-outcome" style={{ color: STATUS_COLOR[outcome] }}>
                    {outcome}
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </aside>
  )
}

// ---------------------------------------------------------------------------
// Loading overlay
// ---------------------------------------------------------------------------

function LoadingOverlay() {
  return (
    <div className="loading-overlay">
      <div className="spinner" />
      <div className="loading-text">Running investigation pipeline</div>
      <div className="loading-steps">
        Classify &rarr; Diagnose &rarr; Remediate &rarr; Simulate &rarr; Risk &rarr; Approve
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [history, setHistory] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState('form')

  // Load existing incidents from the API when the app first mounts
  useEffect(() => {
    fetch('/incidents?limit=50')
      .then(r => r.json())
      .then(items => {
        if (Array.isArray(items)) {
          // items are IncidentListItem stubs — mark them so we know to fetch
          // full details on click
          setHistory(items.map(i => ({ ...i, _stub: true })))
        }
      })
      .catch(() => {}) // silently ignore if API is down
  }, [])

  async function handleSelect(inc) {
    setView('result')
    if (!inc._stub) {
      // Already have full details (submitted in this session)
      setSelected(inc)
      return
    }
    // Fetch full incident detail for sidebar items loaded from the API
    try {
      const res = await fetch(`/incidents/${inc.incident_id}`)
      const detail = await res.json()
      setSelected({ ...detail, job_name: inc.job_name, source: inc.source })
    } catch {
      setSelected(inc) // fall back to stub on network error
    }
  }

  function handleResult(incident) {
    // Prepend the new investigation; remove any stub for the same id if present
    setHistory(prev => [
      incident,
      ...prev.filter(i => i.incident_id !== incident.incident_id),
    ])
    setSelected(incident)
    setLoading(false)
    setView('result')
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-title">Incident Investigator</div>
        <div className="app-subtitle">Autonomous data pipeline investigation</div>
      </header>

      <div className="app-body">
        <Sidebar
          history={history}
          selectedId={selected?.incident_id}
          onSelect={handleSelect}
          onNew={() => { setView('form'); setSelected(null) }}
        />

        <main className="main">
          {loading && <LoadingOverlay />}

          {!loading && view === 'form' && (
            <div className="form-wrapper">
              <h2>Submit Incident Event</h2>
              <p className="form-intro">
                Fill in the event details. The pipeline will classify, diagnose,
                plan a remediation, simulate it for safety, assess risk, and make
                an approval decision — all steps shown below the results.
              </p>
              <EventForm onResult={handleResult} onLoading={setLoading} />
            </div>
          )}

          {!loading && view === 'result' && selected && (
            <PipelineView incident={selected} />
          )}
        </main>
      </div>
    </div>
  )
}
