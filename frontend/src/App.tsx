import { useEffect, useMemo, useState } from 'react'
import './App.css'

type Page = 'dashboard' | 'income' | 'balance' | 'transactions' | 'imports'

type Metric = {
  label: string
  value: string
  helper: string
}

type StatementLine = {
  label: string
  amount: number
  kind?: 'subtotal' | 'total'
}

type BalanceSection = {
  title: string
  lines: StatementLine[]
}

type JournalEntry = {
  id: number
  date: string
  memo: string
  source: string
  debits: JournalAccountLine[]
  credits: JournalAccountLine[]
  amount: number
  status: 'Posted' | 'Draft'
}

type JournalAccountLine = {
  accountCode: string
  accountName: string
  amount: number
  memo: string
}

type ApiJournalEntry = Omit<JournalEntry, 'status'> & {
  status: string
}

type EtsyRow = {
  id: number
  date: string
  type: string
  title: string
  info: string
  amount: number
  feesTaxes: number
  net: number
  posted: boolean
  journalEntryId?: number | null
}

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const navItems: { id: Page; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'income', label: 'Income Statement' },
  { id: 'balance', label: 'Balance Sheet' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'imports', label: 'Imports' },
]

const metrics: Metric[] = [
  { label: 'Net income', value: '$149.79', helper: 'January 2026' },
  { label: 'Sales revenue', value: '$271.78', helper: '10 Etsy sales' },
  { label: 'Expenses', value: '$75.30', helper: 'Fees and shipping' },
  { label: 'Etsy clearing', value: '$149.79', helper: 'Current debit balance' },
]

const incomeLines: StatementLine[] = [
  { label: 'Sales revenue', amount: 271.78 },
  { label: 'Sales returns and allowances', amount: -48.57 },
  { label: 'Net revenue', amount: 223.21, kind: 'subtotal' },
  { label: 'Etsy fees expense', amount: -25.51 },
  { label: 'Shipping expense', amount: -49.79 },
  { label: 'Uncategorized adjustment', amount: 15.8 },
  { label: 'Net income', amount: 163.71, kind: 'total' },
]

const balanceSections: BalanceSection[] = [
  {
    title: 'Assets',
    lines: [
      { label: 'Cash', amount: 0 },
      { label: 'Etsy clearing', amount: 149.79 },
      { label: 'Inventory', amount: 0 },
      { label: 'Total assets', amount: 149.79, kind: 'total' },
    ],
  },
  {
    title: 'Liabilities',
    lines: [
      { label: 'Sales tax payable', amount: -13.92 },
      { label: 'Accounts payable', amount: 0 },
      { label: 'Total liabilities', amount: -13.92, kind: 'subtotal' },
    ],
  },
  {
    title: 'Equity',
    lines: [
      { label: 'Owner capital', amount: 0 },
      { label: 'Current earnings', amount: -163.71 },
      { label: 'Total equity', amount: -163.71, kind: 'subtotal' },
    ],
  },
]

const journalEntries: JournalEntry[] = [
  {
    id: 1,
    date: '2026-01-28',
    memo: 'Sale - Payment for Order #3957331642',
    source: 'Etsy',
    debits: [
      {
        accountCode: '1010',
        accountName: 'Etsy Clearing',
        amount: 13.35,
        memo: 'Sale - Payment for Order #3957331642',
      },
    ],
    credits: [
      {
        accountCode: '4000',
        accountName: 'Sales Revenue',
        amount: 13.35,
        memo: 'Sale - Payment for Order #3957331642',
      },
    ],
    amount: 13.35,
    status: 'Posted',
  },
  {
    id: 2,
    date: '2026-01-28',
    memo: 'Fee - Processing fee - Order #3957331642',
    source: 'Etsy',
    debits: [
      {
        accountCode: '5100',
        accountName: 'Etsy Fees Expense',
        amount: 0.65,
        memo: 'Fee - Processing fee - Order #3957331642',
      },
    ],
    credits: [
      {
        accountCode: '1010',
        accountName: 'Etsy Clearing',
        amount: 0.65,
        memo: 'Fee - Processing fee - Order #3957331642',
      },
    ],
    amount: 0.65,
    status: 'Posted',
  },
  {
    id: 3,
    date: '2026-01-28',
    memo: 'Tax - Sales tax paid by buyer - Order #3957331642',
    source: 'Etsy',
    debits: [
      {
        accountCode: '2100',
        accountName: 'Sales Tax Payable',
        amount: 0.76,
        memo: 'Tax - Sales tax paid by buyer - Order #3957331642',
      },
    ],
    credits: [
      {
        accountCode: '1010',
        accountName: 'Etsy Clearing',
        amount: 0.76,
        memo: 'Tax - Sales tax paid by buyer - Order #3957331642',
      },
    ],
    amount: 0.76,
    status: 'Posted',
  },
  {
    id: 4,
    date: '2026-01-30',
    memo: 'Shipping - USPS shipping label - Label #298680157835',
    source: 'Etsy',
    debits: [
      {
        accountCode: '5200',
        accountName: 'Shipping Expense',
        amount: 5.3,
        memo: 'Shipping - USPS shipping label - Label #298680157835',
      },
    ],
    credits: [
      {
        accountCode: '1010',
        accountName: 'Etsy Clearing',
        amount: 5.3,
        memo: 'Shipping - USPS shipping label - Label #298680157835',
      },
    ],
    amount: 5.3,
    status: 'Posted',
  },
]

function App() {
  const [activePage, setActivePage] = useState<Page>('dashboard')
  const [transactionView, setTransactionView] = useState<'journal' | 'raw'>(
    'journal',
  )
  const [apiJournalEntries, setApiJournalEntries] = useState<JournalEntry[]>([])
  const [apiEtsyRows, setApiEtsyRows] = useState<EtsyRow[]>([])
  const [transactionsLoading, setTransactionsLoading] = useState(true)
  const [transactionsError, setTransactionsError] = useState('')

  const pageTitle = useMemo(() => {
    return navItems.find((item) => item.id === activePage)?.label ?? 'Dashboard'
  }, [activePage])

  useEffect(() => {
    async function loadTransactions() {
      try {
        setTransactionsLoading(true)
        setTransactionsError('')

        const [journalResponse, etsyResponse] = await Promise.all([
          fetch('/api/transactions/journal'),
          fetch('/api/transactions/etsy'),
        ])

        if (!journalResponse.ok || !etsyResponse.ok) {
          throw new Error('Unable to load transactions from the API.')
        }

        const journalData = (await journalResponse.json()) as ApiJournalEntry[]
        const etsyData = (await etsyResponse.json()) as EtsyRow[]

        setApiJournalEntries(
          journalData.map((entry) => ({
            ...entry,
            source: formatSource(entry.source),
            status: formatStatus(entry.status),
          })),
        )
        setApiEtsyRows(etsyData)
      } catch (error) {
        setTransactionsError(
          error instanceof Error
            ? error.message
            : 'Unable to load transactions from the API.',
        )
      } finally {
        setTransactionsLoading(false)
      }
    }

    loadTransactions()
  }, [])

  return (
    <main className="app-shell">
      <aside className="sidebar" aria-label="Primary">
        <div>
          <p className="eyebrow">EZPrntz</p>
          <h1>Accounting System</h1>
        </div>
        <nav>
          {navItems.map((item) => (
            <button
              className={activePage === item.id ? 'active' : ''}
              key={item.id}
              onClick={() => setActivePage(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="month-card">
          <span>Current period</span>
          <strong>January 2026</strong>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Business finance</p>
            <h2>{pageTitle}</h2>
          </div>
          <div className="status-pill">
            <span></span>
            {activePage === 'transactions' ? 'Live API' : 'Mock data'}
          </div>
        </header>

        {activePage === 'dashboard' && <DashboardPage />}
        {activePage === 'income' && <IncomeStatementPage />}
        {activePage === 'balance' && <BalanceSheetPage />}
        {activePage === 'transactions' && (
          <TransactionsPage
            etsyRows={apiEtsyRows}
            journalEntries={apiJournalEntries}
            loading={transactionsLoading}
            error={transactionsError}
            transactionView={transactionView}
            setTransactionView={setTransactionView}
          />
        )}
        {activePage === 'imports' && <ImportsPage />}
      </section>
    </main>
  )
}

function formatSource(source: string): string {
  return source ? source.charAt(0).toUpperCase() + source.slice(1) : source
}

function formatStatus(status: string): 'Posted' | 'Draft' {
  return status.toLowerCase() === 'posted' ? 'Posted' : 'Draft'
}

function DashboardPage() {
  return (
    <>
      <section className="metrics-grid" aria-label="Monthly metrics">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </section>

      <section className="content-grid">
        <article className="panel wide">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Summary</p>
              <h3>January performance</h3>
            </div>
          </div>
          <p className="summary-text">
            EZPrntz posted positive income for January. Sales revenue was driven
            by 10 Etsy orders, while Etsy fees and shipping labels were the main
            costs. The next useful review is the uncategorized adjustment from
            the refund-related payment row.
          </p>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Expense mix</p>
              <h3>Cost pressure</h3>
            </div>
          </div>
          <div className="bars">
            <BarRow label="Shipping" amount={49.79} max={75.3} />
            <BarRow label="Etsy fees" amount={25.51} max={75.3} />
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Accounting</p>
              <h3>Posting status</h3>
            </div>
          </div>
          <div className="stat-list">
            <StatRow label="Raw Etsy rows" value="78" />
            <StatRow label="Posted rows" value="78" />
            <StatRow label="Journal entries" value="74" />
            <StatRow label="Unbalanced entries" value="0" />
          </div>
        </article>

        <article className="panel wide">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recent journal entries</p>
              <h3>Accounting activity</h3>
            </div>
          </div>
          <JournalTable rows={journalEntries.slice(0, 3)} />
        </article>
      </section>
    </>
  )
}

function IncomeStatementPage() {
  return (
    <section className="report-layout">
      <article className="panel report-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">For the month ended</p>
            <h3>January 31, 2026</h3>
          </div>
          <select aria-label="Report period" defaultValue="2026-01">
            <option value="2026-01">January 2026</option>
            <option value="2026-02">February 2026</option>
          </select>
        </div>
        <StatementTable lines={incomeLines} />
      </article>

      <aside className="report-side">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Margin</p>
              <h3>Net income rate</h3>
            </div>
          </div>
          <strong className="big-number">60.2%</strong>
          <p className="muted">Mock percentage based on current posted rows.</p>
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Review item</p>
              <h3>Uncategorized</h3>
            </div>
          </div>
          <p className="summary-text small">
            One Etsy payment row is mapped to Uncategorized Expense for now. It
            should be reviewed before this report is final.
          </p>
        </article>
      </aside>
    </section>
  )
}

function BalanceSheetPage() {
  return (
    <section className="report-layout">
      <article className="panel report-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">As of</p>
            <h3>January 31, 2026</h3>
          </div>
          <input aria-label="Balance sheet date" type="date" defaultValue="2026-01-31" />
        </div>
        <div className="balance-grid">
          {balanceSections.map((section) => (
            <div className="statement-section" key={section.title}>
              <h4>{section.title}</h4>
              <StatementTable lines={section.lines} compact />
            </div>
          ))}
        </div>
      </article>

      <aside className="report-side">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Equation</p>
              <h3>Accounting check</h3>
            </div>
          </div>
          <div className="equation">
            <span>Assets</span>
            <b>{money.format(149.79)}</b>
            <span>Liabilities + Equity</span>
            <b>{money.format(149.79)}</b>
          </div>
        </article>
      </aside>
    </section>
  )
}

function TransactionsPage({
  journalEntries,
  etsyRows,
  loading,
  error,
  transactionView,
  setTransactionView,
}: {
  journalEntries: JournalEntry[]
  etsyRows: EtsyRow[]
  loading: boolean
  error: string
  transactionView: 'journal' | 'raw'
  setTransactionView: (view: 'journal' | 'raw') => void
}) {
  const activeRows = transactionView === 'journal' ? journalEntries : etsyRows

  return (
    <section className="transactions-layout">
      <div className="transaction-actions-grid">
        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Manual entry</p>
              <h3>Add transaction</h3>
            </div>
          </div>
          <form className="manual-transaction-form">
            <label>
              Date
              <input type="date" defaultValue="2026-01-31" />
            </label>
            <label>
              Type
              <select defaultValue="expense">
                <option value="sale">Sale</option>
                <option value="expense">Expense</option>
                <option value="adjustment">Adjustment</option>
                <option value="owner">Owner activity</option>
              </select>
            </label>
            <label>
              Description
              <input placeholder="What happened?" />
            </label>
            <label>
              Amount
              <input min="0" placeholder="0.00" step="0.01" type="number" />
            </label>
          <button type="button">Add draft</button>
          </form>
        </article>

        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Correction</p>
              <h3>Void transaction</h3>
            </div>
          </div>
          <form className="void-transaction-form">
            <label>
              Transaction ID
              <input placeholder="Journal entry ID" />
            </label>
            <label>
              Reason
              <select defaultValue="mistake">
                <option value="mistake">Entered by mistake</option>
                <option value="duplicate">Duplicate record</option>
                <option value="wrong_account">Wrong account</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label>
              Note
              <input className="void-note-input" placeholder="Why is this being voided?" />
            </label>
            <button className="void-draft-button" type="button">Void draft</button>
          </form>
        </article>
      </div>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Find records</h3>
          </div>
        </div>
        <div className="filter-stack">
          <label>
            Search
            <input placeholder="Order, account, memo" />
          </label>
          <label>
            Account
            <select defaultValue="all">
              <option value="all">All accounts</option>
              <option value="1010">Etsy Clearing</option>
              <option value="4000">Sales Revenue</option>
              <option value="5100">Etsy Fees Expense</option>
            </select>
          </label>
          <label>
            Date range
            <select defaultValue="jan">
              <option value="jan">January 2026</option>
              <option value="all">All dates</option>
            </select>
          </label>
        </div>
      </article>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Accounting records</p>
            <h3>Transaction explorer</h3>
          </div>
          <div className="segmented">
            <button
              className={transactionView === 'journal' ? 'selected' : ''}
              onClick={() => setTransactionView('journal')}
              type="button"
            >
              Journal entries
            </button>
            <button
              className={transactionView === 'raw' ? 'selected' : ''}
              onClick={() => setTransactionView('raw')}
              type="button"
            >
              Raw Etsy rows
            </button>
          </div>
        </div>
        <div className="records-scroll">
          {loading ? (
            <StatusState title="Loading transactions" text="Reading posted journal entries and Etsy rows from the backend." />
          ) : error ? (
            <StatusState title="Could not load transactions" text={error} tone="error" />
          ) : activeRows.length === 0 ? (
            <StatusState title="No transactions found" text="Import and post transactions to see them here." />
          ) : transactionView === 'journal' ? (
            <JournalTable rows={journalEntries} />
          ) : (
            <RawEtsyTable rows={etsyRows} />
          )}
        </div>
      </article>
    </section>
  )
}

function ImportsPage() {
  return (
    <section className="content-grid">
      <article className="panel wide">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Upload</p>
            <h3>Import accounting data</h3>
          </div>
        </div>
        <div className="upload-zone">
          <strong>Etsy CSV upload</strong>
          <p>Drop a monthly Etsy statement here or choose a file.</p>
          <button type="button">Choose CSV</button>
        </div>
      </article>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Workflow</p>
            <h3>Import steps</h3>
          </div>
        </div>
        <div className="timeline">
          <TimelineItem label="Upload CSV" status="Ready" />
          <TimelineItem label="Parse rows" status="Backend" />
          <TimelineItem label="Seed accounts" status="Complete" />
          <TimelineItem label="Post journal entries" status="Complete" />
        </div>
      </article>

      <article className="panel wide full">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">History</p>
            <h3>Recent imports</h3>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Source</th>
                <th>Rows</th>
                <th>Posted</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>etsy_statement_2026_1.csv</td>
                <td>Etsy</td>
                <td>78</td>
                <td>78</td>
                <td><span className="tag positive">Complete</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  )
}

function MetricCard({ label, value, helper }: Metric) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <p>{helper}</p>
    </article>
  )
}

function BarRow({
  label,
  amount,
  max,
}: {
  label: string
  amount: number
  max: number
}) {
  return (
    <div className="bar-row">
      <div>
        <strong>{label}</strong>
        <span>{money.format(amount)}</span>
      </div>
      <div className="bar-track">
        <span style={{ width: `${Math.max(8, (amount / max) * 100)}%` }}></span>
      </div>
    </div>
  )
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function StatementTable({
  lines,
  compact = false,
}: {
  lines: StatementLine[]
  compact?: boolean
}) {
  return (
    <div className={compact ? 'statement-table compact' : 'statement-table'}>
      {lines.map((line) => (
        <div className={line.kind ?? ''} key={line.label}>
          <span>{line.label}</span>
          <strong>{money.format(line.amount)}</strong>
        </div>
      ))}
    </div>
  )
}

function JournalTable({ rows }: { rows: JournalEntry[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Memo</th>
            <th>Debit</th>
            <th>Credit</th>
            <th>Amount</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.date}</td>
              <td>{row.memo}</td>
              <td><AccountLineList lines={row.debits} /></td>
              <td><AccountLineList lines={row.credits} /></td>
              <td>{money.format(row.amount)}</td>
              <td><span className="tag positive">{row.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AccountLineList({ lines }: { lines: JournalAccountLine[] }) {
  return (
    <div className="account-lines">
      {lines.map((line) => (
        <span key={`${line.accountCode}-${line.amount}`}>
          {line.accountName}
          <small>{money.format(line.amount)}</small>
        </span>
      ))}
    </div>
  )
}

function RawEtsyTable({ rows }: { rows: EtsyRow[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Title</th>
            <th>Info</th>
            <th>Amount</th>
            <th>Fees and taxes</th>
            <th>Net</th>
            <th>Posted</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.date}</td>
              <td>{row.type}</td>
              <td>{row.title}</td>
              <td>{row.info || '-'}</td>
              <td>{money.format(row.amount)}</td>
              <td>{money.format(row.feesTaxes)}</td>
              <td>{money.format(row.net)}</td>
              <td>
                <span className={row.posted ? 'tag positive' : 'tag negative'}>
                  {row.posted ? 'Posted' : 'Open'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StatusState({
  title,
  text,
  tone = 'neutral',
}: {
  title: string
  text: string
  tone?: 'neutral' | 'error'
}) {
  return (
    <div className={tone === 'error' ? 'status-state error' : 'status-state'}>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  )
}

function TimelineItem({ label, status }: { label: string; status: string }) {
  return (
    <div className="timeline-item">
      <span></span>
      <div>
        <strong>{label}</strong>
        <p>{status}</p>
      </div>
    </div>
  )
}

export default App
