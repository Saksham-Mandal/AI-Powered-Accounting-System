import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, FormEvent } from 'react'
import './App.css'

type Page =
  | 'dashboard'
  | 'agent'
  | 'imports'
  | 'transactions'
  | 'financial-statements'
  | 'closing'
  | 'post-closing-trial-balance'
  | 'ledger'
  | 'generate-csv'
  | 'balance-sheet'
  | 'income-summary'

type Metric = {
  label: string
  value: string
  helper: string
}

type StatementLine = {
  label: string
  amount: number
  kind?: 'section' | 'subtotal' | 'total'
  indent?: boolean
}

type BalanceSection = {
  title: string
  lines: StatementLine[]
}

type TrialBalanceLine = {
  accountCode: string
  accountName: string
  accountType: string
  debitBalance: number
  creditBalance: number
}

type ApiTrialBalanceLine = {
  account_code: string
  account_name: string
  account_type: string
  debit_balance: number
  credit_balance: number
}

type ApiTrialBalance = {
  lines: ApiTrialBalanceLine[]
  total_debit_balances: number
  total_credit_balances: number
  is_balanced: boolean
}

type ApiStatementLine = {
  account_code: string
  account_name: string
  account_type: string
  amount: number
}

type ApiIncomeStatement = {
  start_date: string
  end_date: string
  sections: {
    revenue: ApiStatementLine[]
    contra_revenue: ApiStatementLine[]
    expenses: ApiStatementLine[]
  }
  totals: {
    total_revenue: number
    total_contra_revenue: number
    net_revenue: number
    total_expenses: number
    net_income: number
  }
}

type ApiIncomeStatementSnapshot = {
  id: number
  periodId: number
  periodStart: string
  periodEnd: string
  periodLabel: string | null
  totalRevenue: number
  totalContraRevenue: number
  netRevenue: number
  totalExpenses: number
  netIncome: number
  createdAt: string
  statement: ApiIncomeStatement
}

type ApiBalanceSheet = {
  as_of_date: string
  sections: {
    assets: ApiStatementLine[]
    liabilities: ApiStatementLine[]
    equity: ApiStatementLine[]
  }
  totals: {
    total_assets: number
    total_liabilities: number
    total_equity: number
    total_liabilities_and_equity: number
  }
  is_balanced: boolean
}

type ApiBalanceSheetSnapshot = {
  id: number
  periodId: number
  periodLabel: string | null
  asOfDate: string
  totalAssets: number
  totalLiabilities: number
  totalEquity: number
  totalLiabilitiesAndEquity: number
  isBalanced: boolean
  createdAt: string
  statement: ApiBalanceSheet
}

type ImportResult = {
  filename: string
  contentType: string
  sizeBytes: number
  imported: number
  skipped: number
  totalRows: number
  posted: number
  postingSkipped: number
  totalUnposted: number
  status: string
  period?: AccountingPeriod | null
}

type ImportCsvType = 'etsy' | 'transactions'

type ImportHistoryRow = {
  id: number
  source: string
  filename: string
  rowCount: number
  storedRows: number
  postedRows: number
  importedAt: string
  status: string
  period?: {
    periodStart: string
    periodEnd: string
    label: string
  } | null
}

type Account = {
  id: number
  code: string
  name: string
  accountType: string
  normalBalance: string
}

type AccountingPeriod = {
  id: number
  periodStart: string
  periodEnd: string
  label: string
  status: string
  reviewedAt: string | null
  adjustedAt: string | null
  closedAt: string | null
  trialBalanceConfirmed: boolean
}

type JournalEntry = {
  id: number
  etsyId?: number | null
  date: string
  memo: string
  source: string
  debits: JournalAccountLine[]
  credits: JournalAccountLine[]
  amount: number
  status: 'Posted' | 'Draft' | 'Flagged'
  isFlagged?: boolean
  flaggedReason?: string | null
}

type JournalAccountLine = {
  accountCode: string
  accountName: string
  amount: number
  memo: string
}

type ApiJournalEntry = Omit<JournalEntry, 'status'> & {
  status: string
  reviewNote?: string | null
  flaggedReason?: string | null
  isFlagged?: boolean
}

type LedgerPeriod = {
  label: string
  periodStart: string | null
  periodEnd: string | null
  entries: JournalEntry[]
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

type ManualJournalEntryPayload = {
  entryDate: string
  memo: string
  lines: {
    accountCode: string
    debit: number
    credit: number
    memo: string
  }[]
}

type ClosingEntriesResponse = {
  generatedEntries?: number
  totalRevenues?: number
  totalExpenses?: number
  netIncome?: number
  closingEntries: ApiJournalEntry[]
}

type GeneratedCsvDraftRow = {
  entryDate: string
  memo: string
  debitAccount: string
  creditAccount: string
  debitAmount: number
  creditAmount: number
  source: string
  sourceId: string
}

type GeneratedCsvFile = {
  monthKey: string
  monthLabel: string
  filename: string
  rowCount: number
  csvText: string
}

type GenerateCsvResponse = {
  sourceFilename: string
  fileCount: number
  totalRows: number
  files: GeneratedCsvFile[]
}

type AgentHighlight = {
  label: string
  value: string
}

type AgentToolCall = {
  name: string
  arguments: Record<string, unknown>
  resultSummary: string | null
}

type AgentSource = {
  label: string
  tool: string
}

type AccountingAgentResponse = {
  answer: string
  highlights: AgentHighlight[]
  sources: AgentSource[]
  toolCalls: AgentToolCall[]
}

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const longDate = new Intl.DateTimeFormat('en-US', {
  month: 'long',
  day: 'numeric',
  year: 'numeric',
})

const navItems: { id: Page; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'agent', label: 'AI Agent' },
  { id: 'income-summary', label: 'Income Summary' },
  { id: 'balance-sheet', label: 'Balance Sheet' },
  { id: 'ledger', label: 'Ledger' },
]

const periodNavItems: { id: Page; label: string }[] = [
  { id: 'imports', label: 'Imports' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'financial-statements', label: 'Financial Statements' },
  { id: 'closing', label: 'Closing' },
  { id: 'post-closing-trial-balance', label: 'Post-Closing Trial Balance' },
]

function App() {
  const [activePage, setActivePage] = useState<Page>('dashboard')
  const [processPeriodOpen, setProcessPeriodOpen] = useState(false)
  const [transactionView, setTransactionView] = useState<'journal' | 'raw'>(
    'journal',
  )
  const [apiJournalEntries, setApiJournalEntries] = useState<JournalEntry[]>([])
  const [closingEntries, setClosingEntries] = useState<JournalEntry[]>([])
  const [closingLoading, setClosingLoading] = useState(false)
  const [closingError, setClosingError] = useState('')
  const [ledgerPeriods, setLedgerPeriods] = useState<LedgerPeriod[]>([])
  const [ledgerLoading, setLedgerLoading] = useState(true)
  const [ledgerError, setLedgerError] = useState('')
  const [apiEtsyRows, setApiEtsyRows] = useState<EtsyRow[]>([])
  const [transactionsLoading, setTransactionsLoading] = useState(true)
  const [transactionsError, setTransactionsError] = useState('')
  const [trialBalanceLines, setTrialBalanceLines] = useState<TrialBalanceLine[]>([])
  const [trialBalanceLoading, setTrialBalanceLoading] = useState(true)
  const [trialBalanceError, setTrialBalanceError] = useState('')
  const [postClosingTrialBalanceLines, setPostClosingTrialBalanceLines] =
    useState<TrialBalanceLine[]>([])
  const [postClosingTrialBalanceLoading, setPostClosingTrialBalanceLoading] =
    useState(false)
  const [postClosingTrialBalanceError, setPostClosingTrialBalanceError] =
    useState('')
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importHistory, setImportHistory] = useState<ImportHistoryRow[]>([])
  const [importsLoading, setImportsLoading] = useState(true)
  const [importLoading, setImportLoading] = useState(false)
  const [importError, setImportError] = useState('')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [currentPeriod, setCurrentPeriod] = useState<AccountingPeriod | null>(null)
  const [periodLoading, setPeriodLoading] = useState(false)
  const [periodError, setPeriodError] = useState('')
  const [periodConfirming, setPeriodConfirming] = useState(false)
  const [confirmingTrialBalance, setConfirmingTrialBalance] = useState(false)
  const [financialStatementsViewed, setFinancialStatementsViewed] =
    useState(false)
  const [postClosingTrialBalanceViewed, setPostClosingTrialBalanceViewed] =
    useState(false)
  const [periodProgressHydrated, setPeriodProgressHydrated] = useState(false)
  const [incomeStatement, setIncomeStatement] =
    useState<ApiIncomeStatement | null>(null)
  const [incomeLoading, setIncomeLoading] = useState(true)
  const [incomeError, setIncomeError] = useState('')
  const [incomeStatementSnapshots, setIncomeStatementSnapshots] = useState<
    ApiIncomeStatementSnapshot[]
  >([])
  const [incomeSnapshotsLoading, setIncomeSnapshotsLoading] = useState(true)
  const [incomeSnapshotsError, setIncomeSnapshotsError] = useState('')
  const [balanceSheet, setBalanceSheet] = useState<ApiBalanceSheet | null>(null)
  const [balanceSheetLoading, setBalanceSheetLoading] = useState(false)
  const [balanceSheetError, setBalanceSheetError] = useState('')
  const [selectedImportMonth, setSelectedImportMonth] = useState('')
  const [selectedImportYear, setSelectedImportYear] = useState('')
  const [selectedImportType, setSelectedImportType] = useState<ImportCsvType>('etsy')
  const [confirmedImportPeriod, setConfirmedImportPeriod] = useState<{
    month: string
    year: string
  } | null>(null)
  const [agentQuestion, setAgentQuestion] = useState('')
  const [agentSubmittedQuestion, setAgentSubmittedQuestion] = useState('')
  const [agentResponse, setAgentResponse] =
    useState<AccountingAgentResponse | null>(null)
  const [agentLoading, setAgentLoading] = useState(false)
  const [agentError, setAgentError] = useState('')

  const pageTitle = useMemo(() => {
    return (
      [...navItems, ...periodNavItems].find((item) => item.id === activePage)
        ?.label ?? 'Dashboard'
    )
  }, [activePage])

  const processPeriodActive = periodNavItems.some(
    (item) => item.id === activePage,
  )
  const activePeriodStep = periodNavItems.findIndex(
    (item) => item.id === activePage,
  )
  const selectedPeriodId = currentPeriod?.id ?? null
  const hasImportedCsv = importHistory.some(
    (row) => !currentPeriod || row.period?.periodStart === currentPeriod.periodStart,
  )
  const importsReady = !importsLoading
  const periodProgressStorageKey = currentPeriod
    ? `ezprntz-process-progress-${currentPeriod.id}-${currentPeriod.periodStart}`
    : ''
  const trialBalanceConfirmed = currentPeriod?.trialBalanceConfirmed ?? false
  const closingConfirmed =
    currentPeriod?.status === 'closed' || Boolean(currentPeriod?.closedAt)
  const isProcessStepLocked = useCallback(
    (page: Page) => {
      if (page === 'transactions') {
        return !currentPeriod || !importsReady || !hasImportedCsv
      }

      if (page === 'financial-statements') {
        return !currentPeriod || !trialBalanceConfirmed
      }

      if (page === 'closing') {
        return !currentPeriod || !trialBalanceConfirmed || !financialStatementsViewed
      }

      if (page === 'post-closing-trial-balance') {
        return !currentPeriod || !closingConfirmed
      }

      return false
    },
    [
      closingConfirmed,
      currentPeriod,
      financialStatementsViewed,
      hasImportedCsv,
      importsReady,
      trialBalanceConfirmed,
    ],
  )
  const currentPeriodLabel = currentPeriod?.label ?? 'No period selected'
  const currentPeriodStorageKey = 'ezprntz-current-period-id'

  useEffect(() => {
    async function loadSavedPeriod() {
      try {
        setPeriodLoading(true)
        setPeriodError('')

        const savedPeriodId = window.localStorage.getItem(currentPeriodStorageKey)
        const response = savedPeriodId
          ? await fetch(`/api/periods/${savedPeriodId}`)
          : await fetch('/api/periods')
        const data = await response.json()

        if (!response.ok) {
          throw new Error(data.detail ?? 'Unable to load accounting period.')
        }

        const period = savedPeriodId
          ? data as AccountingPeriod
          : (data as AccountingPeriod[])[0] ?? null

        if (!period) {
          return
        }

        setCurrentPeriod(period)
        const periodSelection = getPeriodSelectionFromStartDate(period.periodStart)

        if (periodSelection) {
          setSelectedImportMonth(periodSelection.month)
          setSelectedImportYear(periodSelection.year)
          setConfirmedImportPeriod(periodSelection)
        }
      } catch {
        window.localStorage.removeItem(currentPeriodStorageKey)
      } finally {
        setPeriodLoading(false)
      }
    }

    void loadSavedPeriod()
  }, [])

  useEffect(() => {
    if (!currentPeriod) {
      return
    }

    window.localStorage.setItem(currentPeriodStorageKey, String(currentPeriod.id))
  }, [currentPeriod])

  useEffect(() => {
    if (!periodProgressStorageKey) {
      setPeriodProgressHydrated(false)
      return
    }

    setPeriodProgressHydrated(false)
    const storedProgress = window.localStorage.getItem(periodProgressStorageKey)

    if (!storedProgress) {
      setFinancialStatementsViewed(false)
      setPostClosingTrialBalanceViewed(false)
      setPeriodProgressHydrated(true)
      return
    }

    try {
      const progress = JSON.parse(storedProgress) as {
        financialStatementsViewed?: boolean
        postClosingTrialBalanceViewed?: boolean
      }

      setFinancialStatementsViewed(Boolean(progress.financialStatementsViewed))
      setPostClosingTrialBalanceViewed(
        Boolean(progress.postClosingTrialBalanceViewed),
      )
    } catch {
      setFinancialStatementsViewed(false)
      setPostClosingTrialBalanceViewed(false)
    }

    setPeriodProgressHydrated(true)
  }, [periodProgressStorageKey])

  useEffect(() => {
    if (!periodProgressStorageKey || !periodProgressHydrated) {
      return
    }

    window.localStorage.setItem(
      periodProgressStorageKey,
      JSON.stringify({
        financialStatementsViewed,
        postClosingTrialBalanceViewed,
      }),
    )
  }, [
    financialStatementsViewed,
    periodProgressHydrated,
    periodProgressStorageKey,
    postClosingTrialBalanceViewed,
  ])

  function openProcessPeriod() {
    const nextOpen = !processPeriodOpen

    setProcessPeriodOpen(nextOpen)

    if (nextOpen && !processPeriodActive) {
      setActivePage('imports')
    }
  }

  function openMainPage(page: Page) {
    markProcessStepViewedOnExit(page)
    setActivePage(page)
    setProcessPeriodOpen(false)
  }

  function openPeriodPage(page: Page) {
    markProcessStepViewedOnExit(page)
    setActivePage(page)
  }

  function markProcessStepViewedOnExit(nextPage: Page) {
    if (
      activePage === 'financial-statements' &&
      nextPage !== 'financial-statements' &&
      currentPeriod?.trialBalanceConfirmed
    ) {
      setFinancialStatementsViewed(true)
    }

    if (
      activePage === 'post-closing-trial-balance' &&
      nextPage !== 'post-closing-trial-balance' &&
      closingConfirmed
    ) {
      setPostClosingTrialBalanceViewed(true)
    }
  }

  const loadTransactions = useCallback(async () => {
    if (!selectedPeriodId) {
      setApiJournalEntries([])
      setApiEtsyRows([])
      setTransactionsError('')
      setTransactionsLoading(false)
      return
    }

    try {
      setTransactionsLoading(true)
      setTransactionsError('')

      const [journalResponse, etsyResponse] = await Promise.all([
        fetch(`/api/periods/${selectedPeriodId}/transactions/journal`),
        fetch(`/api/periods/${selectedPeriodId}/transactions/etsy`),
      ])

      if (!journalResponse.ok || !etsyResponse.ok) {
        throw new Error('Unable to load transactions from the API.')
      }

      const journalData = (await journalResponse.json()) as ApiJournalEntry[]
      const etsyData = (await etsyResponse.json()) as EtsyRow[]

      setApiJournalEntries(
        journalData.map(formatJournalEntryFromApi),
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
  }, [selectedPeriodId])

  useEffect(() => {
    loadTransactions()
  }, [loadTransactions])

  const loadClosingEntries = useCallback(async () => {
    if (!selectedPeriodId) {
      setClosingEntries([])
      setClosingError('')
      setClosingLoading(false)
      return
    }

    try {
      setClosingLoading(true)
      setClosingError('')

      const response = await fetch(`/api/periods/${selectedPeriodId}/closing-entries`)
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail ?? 'Unable to load closing entries.')
      }

      const closingData = data as ClosingEntriesResponse
      setClosingEntries(
        closingData.closingEntries.map(formatJournalEntryFromApi),
      )
    } catch (error) {
      setClosingError(
        error instanceof Error
          ? error.message
          : 'Unable to load closing entries.',
      )
    } finally {
      setClosingLoading(false)
    }
  }, [selectedPeriodId])

  useEffect(() => {
    if (activePage === 'closing' && !isProcessStepLocked('closing')) {
      loadClosingEntries()
    }
  }, [activePage, isProcessStepLocked, loadClosingEntries])

  const loadLedger = useCallback(async () => {
    try {
      setLedgerLoading(true)
      setLedgerError('')

      const response = await fetch('/api/ledger')

      if (!response.ok) {
        throw new Error('Unable to load permanent ledger from the API.')
      }

      const data = (await response.json()) as LedgerPeriod[]
      setLedgerPeriods(
        data.map((period) => ({
          ...period,
          entries: period.entries.map(formatJournalEntryFromApi),
        })),
      )
    } catch (error) {
      setLedgerError(
        error instanceof Error
          ? error.message
          : 'Unable to load permanent ledger from the API.',
      )
    } finally {
      setLedgerLoading(false)
    }
  }, [])

  useEffect(() => {
    loadLedger()
  }, [loadLedger])

  const loadTrialBalance = useCallback(async () => {
    if (!selectedPeriodId) {
      setTrialBalanceLines([])
      setTrialBalanceError('')
      setTrialBalanceLoading(false)
      return
    }

    try {
      setTrialBalanceLoading(true)
      setTrialBalanceError('')

      const response = await fetch(`/api/periods/${selectedPeriodId}/reports/trial-balance`)

      if (!response.ok) {
        throw new Error('Unable to load trial balance from the API.')
      }

      const report = (await response.json()) as ApiTrialBalance

      setTrialBalanceLines(
        report.lines.map((line) => ({
          accountCode: line.account_code,
          accountName: line.account_name,
          accountType: formatAccountType(line.account_type),
          debitBalance: line.debit_balance,
          creditBalance: line.credit_balance,
        })),
      )
    } catch (error) {
      setTrialBalanceError(
        error instanceof Error
          ? error.message
          : 'Unable to load trial balance from the API.',
      )
    } finally {
      setTrialBalanceLoading(false)
    }
  }, [selectedPeriodId])

  useEffect(() => {
    loadTrialBalance()
  }, [loadTrialBalance])

  const loadPostClosingTrialBalance = useCallback(async (force = false) => {
    if (!selectedPeriodId || (!force && !closingConfirmed)) {
      setPostClosingTrialBalanceLines([])
      setPostClosingTrialBalanceError('')
      setPostClosingTrialBalanceLoading(false)
      return
    }

    try {
      setPostClosingTrialBalanceLoading(true)
      setPostClosingTrialBalanceError('')

      const response = await fetch(
        `/api/periods/${selectedPeriodId}/reports/post-closing-trial-balance`,
      )

      if (!response.ok) {
        throw new Error('Unable to load post-closing trial balance from the API.')
      }

      const report = (await response.json()) as ApiTrialBalance

      setPostClosingTrialBalanceLines(
        report.lines.map((line) => ({
          accountCode: line.account_code,
          accountName: line.account_name,
          accountType: formatAccountType(line.account_type),
          debitBalance: line.debit_balance,
          creditBalance: line.credit_balance,
        })),
      )
    } catch (error) {
      setPostClosingTrialBalanceError(
        error instanceof Error
          ? error.message
          : 'Unable to load post-closing trial balance from the API.',
      )
    } finally {
      setPostClosingTrialBalanceLoading(false)
    }
  }, [closingConfirmed, selectedPeriodId])

  useEffect(() => {
    if (activePage === 'post-closing-trial-balance') {
      loadPostClosingTrialBalance()
    }
  }, [activePage, loadPostClosingTrialBalance])

  const loadFinancialReports = useCallback(async () => {
    if (!selectedPeriodId) {
      setIncomeStatement(null)
      setIncomeError('')
      setIncomeLoading(false)
      return
    }

    try {
      setIncomeLoading(true)
      setIncomeError('')

      const incomeResponse = await fetch(
        `/api/periods/${selectedPeriodId}/reports/income-statement`,
      )

      if (!incomeResponse.ok) {
        throw new Error('Unable to load income statement from the API.')
      }

      const incomeReport = (await incomeResponse.json()) as ApiIncomeStatement

      setIncomeStatement(incomeReport)
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : 'Unable to load income statement from the API.'

      setIncomeError(message)
    } finally {
      setIncomeLoading(false)
    }
  }, [selectedPeriodId])

  useEffect(() => {
    loadFinancialReports()
  }, [loadFinancialReports])

  const loadIncomeStatementSnapshots = useCallback(async () => {
    try {
      setIncomeSnapshotsLoading(true)
      setIncomeSnapshotsError('')

      const response = await fetch('/api/reports/income-statements')

      if (!response.ok) {
        throw new Error('Unable to load saved income statements from the API.')
      }

      const snapshots = (await response.json()) as ApiIncomeStatementSnapshot[]
      setIncomeStatementSnapshots(snapshots)
    } catch (error) {
      setIncomeSnapshotsError(
        error instanceof Error
          ? error.message
          : 'Unable to load saved income statements from the API.',
      )
    } finally {
      setIncomeSnapshotsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadIncomeStatementSnapshots()
  }, [loadIncomeStatementSnapshots])

  const loadBalanceSheet = useCallback(async () => {
    try {
      setBalanceSheetLoading(true)
      setBalanceSheetError('')

      const response = await fetch('/api/reports/balance-sheet/latest')

      if (response.status === 404) {
        setBalanceSheet(null)
        return
      }

      if (!response.ok) {
        throw new Error('Unable to load the saved balance sheet from the API.')
      }

      const snapshot = (await response.json()) as ApiBalanceSheetSnapshot
      setBalanceSheet(snapshot.statement)
    } catch (error) {
      setBalanceSheetError(
        error instanceof Error
          ? error.message
          : 'Unable to load the saved balance sheet from the API.',
      )
    } finally {
      setBalanceSheetLoading(false)
    }
  }, [])

  useEffect(() => {
    loadBalanceSheet()
  }, [loadBalanceSheet])

  const loadImports = useCallback(async () => {
    if (!selectedPeriodId) {
      setImportHistory([])
      setImportError('')
      setImportsLoading(false)
      return
    }

    try {
      setImportsLoading(true)
      setImportError('')

      const response = await fetch(`/api/periods/${selectedPeriodId}/imports`)

      if (!response.ok) {
        throw new Error('Unable to load import history from the API.')
      }

      const imports = (await response.json()) as ImportHistoryRow[]
      setImportHistory(imports)
    } catch (error) {
      setImportError(
        error instanceof Error
          ? error.message
          : 'Unable to load import history from the API.',
      )
    } finally {
      setImportsLoading(false)
    }
  }, [selectedPeriodId])

  useEffect(() => {
    loadImports()
  }, [loadImports])

  useEffect(() => {
    if (confirmedImportPeriod || selectedImportMonth || selectedImportYear) {
      return
    }

    const latestPeriod = getLatestImportPeriodSelection(importHistory)

    if (!latestPeriod) {
      return
    }

    setSelectedImportMonth(latestPeriod.month)
    setSelectedImportYear(latestPeriod.year)
    setConfirmedImportPeriod(latestPeriod)
  }, [
    confirmedImportPeriod,
    importHistory,
    selectedImportMonth,
    selectedImportYear,
  ])

  const loadAccounts = useCallback(async () => {
    try {
      const response = await fetch('/api/accounts')

      if (!response.ok) {
        throw new Error('Unable to load accounts from the API.')
      }

      const accountData = (await response.json()) as Account[]
      setAccounts(accountData)
    } catch {
      setAccounts([])
    }
  }, [])

  useEffect(() => {
    loadAccounts()
  }, [loadAccounts])

  const confirmSelectedPeriod = useCallback(async (month: string, year: string) => {
    try {
      setPeriodConfirming(true)
      setPeriodLoading(true)
      setPeriodError('')

      const response = await fetch('/api/periods', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          month,
          year: Number(year),
        }),
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail ?? 'Unable to confirm accounting period.')
      }

      const period = data as AccountingPeriod
      setCurrentPeriod(period)
      setConfirmedImportPeriod({ month, year })
      setImportResult(null)
      setImportHistory([])
      setApiJournalEntries([])
      setApiEtsyRows([])
      setClosingEntries([])
      setTrialBalanceLines([])
      setPostClosingTrialBalanceLines([])
      setIncomeStatement(null)
      setAgentResponse(null)
      setAgentError('')
      setTransactionView('journal')
    } catch (error) {
      setPeriodError(
        error instanceof Error
          ? error.message
          : 'Unable to confirm accounting period.',
      )
    } finally {
      setPeriodConfirming(false)
      setPeriodLoading(false)
    }
  }, [])

  async function confirmTrialBalance() {
    if (!selectedPeriodId) {
      setPeriodError('Confirm an accounting period before confirming the trial balance.')
      return
    }

    try {
      setConfirmingTrialBalance(true)
      setPeriodError('')

      const response = await fetch(
        `/api/periods/${selectedPeriodId}/confirm-trial-balance`,
        {
          method: 'POST',
        },
      )

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail ?? 'Unable to confirm trial balance.')
      }

      const period = (await response.json()) as AccountingPeriod
      setCurrentPeriod(period)
      await Promise.all([
        loadTrialBalance(),
        loadFinancialReports(),
        loadIncomeStatementSnapshots(),
        loadLedger(),
        loadClosingEntries(),
      ])
      setActivePage('financial-statements')
    } catch (error) {
      setPeriodError(
        error instanceof Error
          ? error.message
          : 'Unable to confirm trial balance.',
      )
    } finally {
      setConfirmingTrialBalance(false)
    }
  }

  async function uploadImport(file: File, importType: ImportCsvType) {
    try {
      setImportLoading(true)
      setImportError('')

      if (!selectedPeriodId) {
        throw new Error('Confirm an accounting period before uploading a CSV.')
      }

      const detectedImportType = await detectImportCsvType(file)
      const finalImportType = detectedImportType ?? importType
      setSelectedImportType(finalImportType)

      const formData = new FormData()
      formData.append('file', file)
      const importPath =
        finalImportType === 'transactions'
          ? 'transactions'
          : 'etsy'

      const response = await fetch(
        `/api/periods/${selectedPeriodId}/imports/${importPath}`,
        {
          method: 'POST',
          body: formData,
        },
      )

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail ?? 'Unable to import this CSV file.')
      }

      setImportResult(data as ImportResult)
      setTransactionView('journal')
      await Promise.all([
        loadImports(),
        loadTransactions(),
        loadTrialBalance(),
        loadFinancialReports(),
      ])
    } catch (error) {
      setImportError(
        error instanceof Error
          ? error.message
          : 'Unable to import this CSV file.',
      )
    } finally {
      setImportLoading(false)
    }
  }

  async function deleteImport(importId: number) {
    setImportError('')

    const response = await fetch(`/api/imports/${importId}`, {
      method: 'DELETE',
    })
    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail ?? 'Unable to delete this CSV import.')
    }

    setImportResult(null)
    await Promise.all([
      loadImports(),
      loadTransactions(),
      loadTrialBalance(),
      loadFinancialReports(),
      loadLedger(),
    ])
  }

  async function addManualTransaction(payload: ManualJournalEntryPayload) {
    if (!selectedPeriodId) {
      throw new Error('Confirm an accounting period before adding a draft transaction.')
    }

    const response = await fetch(`/api/periods/${selectedPeriodId}/transactions/journal/manual`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail ?? 'Unable to add this draft transaction.')
    }

    await Promise.all([loadTransactions(), loadTrialBalance()])
  }

  async function voidJournalTransaction(
    journalEntryId: number,
    reason: string,
    note: string,
  ) {
    const response = await fetch(`/api/transactions/journal/${journalEntryId}/void`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason, note }),
    })

    const data = await response.json()

    if (!response.ok) {
      throw new Error(data.detail ?? 'Unable to void this draft transaction.')
    }

    await Promise.all([loadTransactions(), loadTrialBalance()])
  }

  async function askAccountingAgent(questionOverride?: string) {
    const question = (questionOverride ?? agentQuestion).trim()

    if (!question) {
      setAgentError('Ask the agent a question first.')
      return
    }

    try {
      setAgentLoading(true)
      setAgentError('')
      setAgentQuestion(question)
      setAgentSubmittedQuestion(question)
      setAgentResponse(null)

      const response = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: question,
          periodId: selectedPeriodId,
        }),
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail ?? 'Unable to ask the accounting agent.')
      }

      setAgentResponse(normalizeAgentResponse(data))
    } catch (error) {
      setAgentError(
        error instanceof Error
          ? error.message
          : 'Unable to ask the accounting agent.',
      )
    } finally {
      setAgentLoading(false)
    }
  }

  async function confirmClosingEntries() {
    if (!selectedPeriodId) {
      setClosingError('Confirm an accounting period before posting closing entries.')
      return
    }

    try {
      setClosingLoading(true)
      setClosingError('')

      const response = await fetch(
        `/api/periods/${selectedPeriodId}/confirm-closing-entries`,
        {
          method: 'POST',
        },
      )
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail ?? 'Unable to confirm closing entries.')
      }

      setCurrentPeriod(data as AccountingPeriod)
      await Promise.all([
        loadClosingEntries(),
        loadLedger(),
        loadPostClosingTrialBalance(true),
        loadBalanceSheet(),
        loadTrialBalance(),
        loadTransactions(),
      ])
    } catch (error) {
      setClosingError(
        error instanceof Error
          ? error.message
          : 'Unable to confirm closing entries.',
      )
    } finally {
      setClosingLoading(false)
    }
  }

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
              onClick={() => openMainPage(item.id)}
              type="button"
            >
              {item.label}
            </button>
          ))}
          <button
            className={processPeriodActive ? 'active parent-active' : ''}
            onClick={openProcessPeriod}
            type="button"
          >
            <span>Process Period</span>
            <span className="nav-chevron">{processPeriodOpen ? '-' : '+'}</span>
          </button>
          {processPeriodOpen && (
            <div className="subnav">
              {periodNavItems.map((item) => (
                <button
                  className={[
                    activePage === item.id ? 'active' : '',
                    isProcessStepLocked(item.id) ? 'locked' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  key={item.id}
                  onClick={() => openPeriodPage(item.id)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          )}
          <button
            className={activePage === 'generate-csv' ? 'active' : ''}
            onClick={() => openMainPage('generate-csv')}
            type="button"
          >
            Generate CSV
          </button>
        </nav>
        <div className="month-card">
          <span>Current period</span>
          <strong>{currentPeriodLabel}</strong>
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
            {activePage === 'dashboard' ||
            activePage === 'imports' ||
            activePage === 'transactions' ||
            activePage === 'financial-statements' ||
            activePage === 'balance-sheet' ||
            activePage === 'ledger' ||
            activePage === 'agent'
              ? 'Live API'
              : 'Mock data'}
          </div>
        </header>

        {processPeriodActive && (
          <PeriodProgress
            activeStep={activePeriodStep}
            isStepComplete={(page) => {
              if (page === 'imports') {
                return hasImportedCsv
              }

              if (page === 'transactions') {
                return trialBalanceConfirmed
              }

              if (page === 'financial-statements') {
                return trialBalanceConfirmed && financialStatementsViewed
              }

              if (page === 'closing') {
                return closingConfirmed
              }

              if (page === 'post-closing-trial-balance') {
                return closingConfirmed && postClosingTrialBalanceViewed
              }

              return false
            }}
            isStepLocked={isProcessStepLocked}
            items={periodNavItems}
            setActivePage={openPeriodPage}
          />
        )}

        {activePage === 'dashboard' && (
          <DashboardPage
            currentPeriod={currentPeriod}
            etsyRows={apiEtsyRows}
            importHistory={importHistory}
            importsLoading={importsLoading}
            incomeError={incomeError}
            incomeLoading={incomeLoading}
            incomeReport={incomeStatement}
            journalEntries={apiJournalEntries}
            transactionsError={transactionsError}
            transactionsLoading={transactionsLoading}
            trialBalanceError={trialBalanceError}
            trialBalanceLines={trialBalanceLines}
            trialBalanceLoading={trialBalanceLoading}
          />
        )}
        {activePage === 'agent' && (
          <AgentPage
            currentPeriodLabel={currentPeriodLabel}
            error={agentError}
            loading={agentLoading}
            onAsk={askAccountingAgent}
            question={agentQuestion}
            response={agentResponse}
            setQuestion={setAgentQuestion}
            submittedQuestion={agentSubmittedQuestion}
          />
        )}
        {activePage === 'ledger' && (
          <LedgerPage
            error={ledgerError}
            loading={ledgerLoading}
            periods={ledgerPeriods}
          />
        )}
        {activePage === 'generate-csv' && <GenerateCsvPage />}
        {activePage === 'balance-sheet' && (
          <StandaloneBalanceSheetPage
            closed={Boolean(balanceSheet)}
            error={balanceSheetError}
            loading={balanceSheetLoading}
            report={balanceSheet}
          />
        )}
        {activePage === 'income-summary' && (
          <IncomeSummaryPage
            error={incomeSnapshotsError}
            loading={incomeSnapshotsLoading}
            snapshots={incomeStatementSnapshots}
          />
        )}
        {activePage === 'imports' && (
          <ImportsPage
            error={importError}
            history={importHistory}
            importing={importLoading}
            loadingHistory={importsLoading}
            onConfirmPeriod={confirmSelectedPeriod}
            onDeleteImport={deleteImport}
            periodConfirming={periodConfirming}
            periodError={periodError}
            confirmedPeriod={confirmedImportPeriod}
            importType={selectedImportType}
            selectedMonth={selectedImportMonth}
            selectedYear={selectedImportYear}
            setConfirmedPeriod={setConfirmedImportPeriod}
            setImportType={setSelectedImportType}
            setSelectedMonth={setSelectedImportMonth}
            setSelectedYear={setSelectedImportYear}
            result={importResult}
            uploadImport={uploadImport}
          />
        )}
        {activePage === 'financial-statements' && (
          !isProcessStepLocked('financial-statements') ? (
            <FinancialStatementsPage
              incomeError={incomeError}
              incomeLoading={incomeLoading}
              incomeReport={incomeStatement}
              trialBalanceLines={trialBalanceLines}
            />
          ) : (
            <LockedProcessPage
              loading={periodLoading}
              text="Confirm the unadjusted trial balance in Transactions before viewing the adjusted trial balance and financial statements."
              title="Financial statements locked"
            />
          )
        )}
        {activePage === 'closing' && (
          !isProcessStepLocked('closing') ? (
            <ClosingPage
              confirmed={closingConfirmed}
              entries={closingEntries}
              error={closingError}
              generating={closingLoading}
              onConfirmClosingEntries={confirmClosingEntries}
            />
          ) : (
            <LockedProcessPage
              loading={periodLoading}
              text="Confirm the unadjusted trial balance and view the financial statements before reviewing closing entries."
              title="Closing locked"
            />
          )
        )}
        {activePage === 'post-closing-trial-balance' && (
          !isProcessStepLocked('post-closing-trial-balance') ? (
            <PostClosingTrialBalancePage
              error={postClosingTrialBalanceError}
              lines={postClosingTrialBalanceLines}
              loading={postClosingTrialBalanceLoading}
            />
          ) : (
            <LockedProcessPage
              loading={periodLoading}
              text="Confirm and post the closing entries before viewing the post-closing trial balance."
              title="Post-closing trial balance locked"
            />
          )
        )}
        {activePage === 'transactions' && (
          hasImportedCsv ? (
            <TransactionsPage
              accounts={accounts}
              confirmingTrialBalance={confirmingTrialBalance}
              etsyRows={apiEtsyRows}
              journalEntries={apiJournalEntries}
              loading={transactionsLoading}
              onAddManualTransaction={addManualTransaction}
              onConfirmTrialBalance={confirmTrialBalance}
              onVoidJournalTransaction={voidJournalTransaction}
              periodError={periodError}
              trialBalanceConfirmed={currentPeriod?.trialBalanceConfirmed ?? false}
              error={transactionsError}
              transactionView={transactionView}
              setTransactionView={setTransactionView}
              trialBalanceError={trialBalanceError}
              trialBalanceLines={trialBalanceLines}
              trialBalanceLoading={trialBalanceLoading}
            />
          ) : (
            <LockedProcessPage
              loading={importsLoading}
              text="Upload at least one CSV in Imports before reviewing proposed journal entries."
              title="Transactions locked"
            />
          )
        )}
      </section>
    </main>
  )
}

function formatSource(source: string): string {
  if (source === 'transaction_csv') {
    return 'Transaction CSV'
  }

  return source ? source.charAt(0).toUpperCase() + source.slice(1) : source
}

function normalizeAgentResponse(data: unknown): AccountingAgentResponse {
  const response = isRecord(data) ? data : {}

  return {
    answer: typeof response.answer === 'string' ? response.answer : '',
    highlights: Array.isArray(response.highlights)
      ? response.highlights.filter(isAgentHighlight)
      : [],
    sources: Array.isArray(response.sources)
      ? response.sources.filter(isAgentSource)
      : [],
    toolCalls: Array.isArray(response.toolCalls)
      ? response.toolCalls.filter(isAgentToolCall)
      : [],
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isAgentHighlight(value: unknown): value is AgentHighlight {
  return (
    isRecord(value) &&
    typeof value.label === 'string' &&
    typeof value.value === 'string'
  )
}

function isAgentSource(value: unknown): value is AgentSource {
  return (
    isRecord(value) &&
    typeof value.label === 'string' &&
    typeof value.tool === 'string'
  )
}

function isAgentToolCall(value: unknown): value is AgentToolCall {
  return (
    isRecord(value) &&
    typeof value.name === 'string' &&
    isRecord(value.arguments) &&
    (
      typeof value.resultSummary === 'string' ||
      value.resultSummary === null ||
      value.resultSummary === undefined
    )
  )
}

function formatAgentSources(sources: AgentSource[]): string {
  return sources.map((source) => source.label).join(', ')
}

function formatStatus(status: string, isFlagged = false): 'Posted' | 'Draft' | 'Flagged' {
  if (isFlagged) {
    return 'Flagged'
  }

  return status.toLowerCase() === 'posted' ? 'Posted' : 'Draft'
}

function formatJournalEntryFromApi(entry: ApiJournalEntry): JournalEntry {
  return {
    ...entry,
    source: formatSource(entry.source),
    status: formatStatus(entry.status, entry.isFlagged),
  }
}

function formatAccountType(accountType: string): string {
  return accountType
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

function formatReportDate(value: string): string {
  if (!value) {
    return 'Current period'
  }

  return longDate.format(new Date(`${value}T12:00:00`))
}

function roundCurrency(value: number): number {
  return Math.round(value * 100) / 100
}

function buildDashboardSummary(
  periodLabel: string,
  incomeReport: ApiIncomeStatement | null,
  trialBalanced: boolean,
  pendingEntries: number,
  flaggedEntries: number,
): string {
  if (!incomeReport) {
    return `Select or load an accounting period to see live dashboard results for ${periodLabel}.`
  }

  const netIncome = incomeReport.totals.net_income
  const netRevenue = incomeReport.totals.net_revenue
  const expenses = incomeReport.totals.total_expenses
  const incomeDirection = netIncome >= 0 ? 'positive' : 'negative'
  const reviewItems = [
    pendingEntries ? `${pendingEntries} pending entr${pendingEntries === 1 ? 'y' : 'ies'}` : '',
    flaggedEntries ? `${flaggedEntries} flagged entr${flaggedEntries === 1 ? 'y' : 'ies'}` : '',
    trialBalanced ? '' : 'an out-of-balance trial balance',
  ].filter(Boolean)

  return (
    `${periodLabel} currently shows ${incomeDirection} net income of ` +
    `${money.format(netIncome)} on ${money.format(netRevenue)} of net revenue ` +
    `and ${money.format(expenses)} of expenses. ` +
    (
      reviewItems.length
        ? `Review ${reviewItems.join(', ')} before finalizing the period.`
        : 'No pending, flagged, or trial-balance issues are showing in the dashboard data.'
    )
  )
}

function formatCompactDate(value: string): string {
  if (!value) {
    return '-'
  }

  const [year, month, day] = value.split('-')

  if (!year || !month || !day) {
    return value
  }

  return `${Number(month)}/${Number(day)}/${year.slice(-2)}`
}

function getLatestImportPeriodSelection(
  imports: ImportHistoryRow[],
): { month: string; year: string } | null {
  const latestImportWithPeriod = imports.find((row) => row.period?.periodStart)

  if (!latestImportWithPeriod?.period?.periodStart) {
    return null
  }

  return getPeriodSelectionFromStartDate(latestImportWithPeriod.period.periodStart)
}

function getPeriodSelectionFromStartDate(
  periodStart: string,
): { month: string; year: string } | null {
  const [year, month] = periodStart.split('-')
  const monthNumber = Number(month)
  const monthNames = [
    'january',
    'february',
    'march',
    'april',
    'may',
    'june',
    'july',
    'august',
    'september',
    'october',
    'november',
    'december',
  ]

  if (!year || monthNumber < 1 || monthNumber > 12) {
    return null
  }

  return {
    month: monthNames[monthNumber - 1],
    year,
  }
}

function parseApiErrorText(text: string): string {
  try {
    const data = JSON.parse(text) as { detail?: string }
    return data.detail || 'Unable to complete this request.'
  } catch {
    return text || 'Unable to complete this request.'
  }
}

async function detectImportCsvType(file: File): Promise<ImportCsvType | null> {
  const text = await file.text()
  const firstLine = text.split(/\r?\n/).find((line) => line.trim())

  if (!firstLine) {
    return null
  }

  const headers = new Set(
    parseCsvLine(firstLine).map((header) => header.trim().toLowerCase()),
  )

  if (
    headers.has('entry_date') &&
    headers.has('debit_account') &&
    headers.has('credit_account') &&
    headers.has('debit_amount') &&
    headers.has('credit_amount')
  ) {
    return 'transactions'
  }

  if (
    headers.has('date') &&
    headers.has('fees & taxes') &&
    headers.has('net')
  ) {
    return 'etsy'
  }

  return null
}

function parseGeneratedTransactionCsv(csvText: string): GeneratedCsvDraftRow[] {
  const lines = csvText.trim().split(/\r?\n/)

  if (lines.length < 2) {
    return []
  }

  const headers = parseCsvLine(lines[0])
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line)
    const row = Object.fromEntries(
      headers.map((header, index) => [header, values[index] ?? '']),
    )

    return {
      entryDate: row.entry_date,
      memo: row.memo,
      debitAccount: row.debit_account,
      creditAccount: row.credit_account,
      debitAmount: Number(row.debit_amount || 0),
      creditAmount: Number(row.credit_amount || 0),
      source: row.source,
      sourceId: row.source_id,
    }
  })
}

function parseCsvLine(line: string): string[] {
  const values: string[] = []
  let current = ''
  let inQuotes = false

  for (let index = 0; index < line.length; index += 1) {
    const character = line[index]
    const nextCharacter = line[index + 1]

    if (character === '"' && inQuotes && nextCharacter === '"') {
      current += '"'
      index += 1
      continue
    }

    if (character === '"') {
      inQuotes = !inQuotes
      continue
    }

    if (character === ',' && !inQuotes) {
      values.push(current)
      current = ''
      continue
    }

    current += character
  }

  values.push(current)
  return values
}

function formatGeneratedTransactionType(accountCode: string): string {
  const labels: Record<string, string> = {
    '5300': 'Materials Expense',
    '5400': 'Supplies Expense',
    '5500': 'Marketing Expense',
    '5600': 'Software Expense',
  }

  return labels[accountCode] ?? accountCode
}

function filterJournalEntries(
  entries: JournalEntry[],
  search: string,
  accountFilter: string,
): JournalEntry[] {
  const normalizedSearch = search.trim().toLowerCase()

  return entries.filter((entry) => {
    const accountLines = [...entry.debits, ...entry.credits]
    const matchesAccount =
      accountFilter === 'all' ||
      (accountFilter === 'flagged' && entry.isFlagged) ||
      accountLines.some((line) => line.accountCode === accountFilter)

    if (!matchesAccount) {
      return false
    }

    if (!normalizedSearch) {
      return true
    }

    const searchableText = [
      entry.id,
      entry.etsyId,
      entry.date,
      formatCompactDate(entry.date),
      entry.memo,
      entry.source,
      entry.status,
      entry.flaggedReason,
      ...accountLines.flatMap((line) => [
        line.accountCode,
        line.accountName,
        line.memo,
        line.amount,
      ]),
    ]
      .filter((value) => value !== null && value !== undefined)
      .join(' ')
      .toLowerCase()

    return searchableText.includes(normalizedSearch)
  })
}

function filterEtsyRows(rows: EtsyRow[], search: string): EtsyRow[] {
  const normalizedSearch = search.trim().toLowerCase()

  if (!normalizedSearch) {
    return rows
  }

  return rows.filter((row) => {
    const searchableText = [
      row.id,
      row.date,
      formatCompactDate(row.date),
      row.type,
      row.title,
      row.info,
      row.amount,
      row.feesTaxes,
      row.net,
      row.journalEntryId,
    ]
      .filter((value) => value !== null && value !== undefined)
      .join(' ')
      .toLowerCase()

    return searchableText.includes(normalizedSearch)
  })
}

function filterLedgerPeriods(
  periods: LedgerPeriod[],
  search: string,
  periodFilter: string,
  sortOrder: 'desc' | 'asc',
): LedgerPeriod[] {
  const normalizedSearch = search.trim().toLowerCase()

  return periods
    .filter((period) => {
      if (periodFilter === 'all') {
        return true
      }

      return (period.periodStart ?? period.label) === periodFilter
    })
    .map((period) => {
      if (!normalizedSearch) {
        return period
      }

      return {
        ...period,
        entries: period.entries.filter((entry) =>
          ledgerEntryMatchesSearch(entry, normalizedSearch),
        ),
      }
    })
    .filter((period) => period.entries.length > 0)
    .map((period) => ({
      ...period,
      entries: [...period.entries].sort((first, second) =>
        compareLedgerEntries(first, second, sortOrder),
      ),
    }))
    .sort((first, second) => compareLedgerPeriods(first, second, sortOrder))
}

function ledgerEntryMatchesSearch(
  entry: JournalEntry,
  normalizedSearch: string,
): boolean {
  const accountLines = [...entry.debits, ...entry.credits]
  const searchableText = [
    entry.id,
    entry.etsyId,
    entry.date,
    formatCompactDate(entry.date),
    entry.memo,
    entry.source,
    entry.status,
    entry.amount,
    ...accountLines.flatMap((line) => [
      line.accountCode,
      line.accountName,
      line.memo,
      line.amount,
    ]),
  ]
    .filter((value) => value !== null && value !== undefined)
    .join(' ')
    .toLowerCase()

  return searchableText.includes(normalizedSearch)
}

function compareLedgerEntries(
  first: JournalEntry,
  second: JournalEntry,
  sortOrder: 'desc' | 'asc',
): number {
  const direction = sortOrder === 'asc' ? 1 : -1
  const dateComparison = first.date.localeCompare(second.date)

  if (dateComparison !== 0) {
    return dateComparison * direction
  }

  return (first.id - second.id) * direction
}

function compareLedgerPeriods(
  first: LedgerPeriod,
  second: LedgerPeriod,
  sortOrder: 'desc' | 'asc',
): number {
  const direction = sortOrder === 'asc' ? 1 : -1
  const firstDate = first.periodStart ?? ''
  const secondDate = second.periodStart ?? ''

  return firstDate.localeCompare(secondDate) * direction
}

function statementLine(line: ApiStatementLine, amount = line.amount): StatementLine {
  return {
    label: line.account_name,
    amount,
  }
}

function balanceSheetLine(line: ApiStatementLine): StatementLine {
  return {
    label: line.account_name,
    amount: line.amount,
  }
}

function buildIncomeStatementLines(report: ApiIncomeStatement): StatementLine[] {
  return [
    { label: 'Revenues', amount: 0, kind: 'section' as const },
    ...report.sections.revenue.map((line) => ({
      ...statementLine(line),
      indent: true,
    })),
    ...report.sections.contra_revenue.map((line) =>
      ({
        ...statementLine(line, -Math.abs(line.amount)),
        indent: true,
      }),
    ),
    {
      label: 'Net revenue',
      amount: report.totals.net_revenue,
      kind: 'subtotal' as const,
    },
    { label: 'Expenses', amount: 0, kind: 'section' as const },
    ...report.sections.expenses.map((line) =>
      ({
        ...statementLine(line, -line.amount),
        indent: true,
      }),
    ),
    {
      label: 'Total expenses',
      amount: -report.totals.total_expenses,
      kind: 'subtotal' as const,
    },
    {
      label: 'Net income',
      amount: report.totals.net_income,
      kind: 'total' as const,
    },
  ]
}

function AgentPage({
  currentPeriodLabel,
  error,
  loading,
  onAsk,
  question,
  response,
  setQuestion,
  submittedQuestion,
}: {
  currentPeriodLabel: string
  error: string
  loading: boolean
  onAsk: (questionOverride?: string) => Promise<void>
  question: string
  response: AccountingAgentResponse | null
  setQuestion: (question: string) => void
  submittedQuestion: string
}) {
  async function submitAgentQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onAsk()
  }

  return (
    <section className="agent-chat-shell">
      <article className="panel agent-chat-panel">
        <header className="agent-chat-header">
          <div>
            <p className="eyebrow">Accounting agent</p>
            <h3>{currentPeriodLabel}</h3>
          </div>
          <span className="tag positive">Read-only</span>
        </header>

        <div className="agent-chat-log" aria-live="polite">
          <div className="agent-message-row assistant">
            <div className="agent-avatar">AI</div>
            <div className="agent-message">
              <strong>Accounting assistant</strong>
              <p>
                Ask me about reports, transactions, closing readiness, or anything
                you want this agent to eventually help with.
              </p>
            </div>
          </div>

          {submittedQuestion && (
            <div className="agent-message-row user">
              <div className="agent-message">
                <p>{submittedQuestion}</p>
              </div>
            </div>
          )}

          {loading && (
            <div className="agent-message-row assistant">
              <div className="agent-avatar">AI</div>
              <div className="agent-message thinking">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}

          {error && !loading && (
            <div className="agent-message-row assistant">
              <div className="agent-avatar">AI</div>
              <div className="agent-message error">
                <strong>Agent unavailable</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {response && !loading && !error && (
            <div className="agent-message-row assistant">
              <div className="agent-avatar">AI</div>
              <div className="agent-message">
                <strong>Accounting readout</strong>
                <p>{response.answer}</p>

                {response.highlights.length > 0 && (
                  <div className="agent-highlight-grid">
                    {response.highlights.map((highlight) => (
                      <div className="agent-highlight" key={highlight.label}>
                        <span>{highlight.label}</span>
                        <strong>{highlight.value}</strong>
                      </div>
                    ))}
                  </div>
                )}

                {response.toolCalls.length > 0 && (
                  <div className="agent-action-list">
                    <p className="eyebrow">Tools used</p>
                    {response.toolCalls.map((toolCall) => (
                      <div className="agent-action" key={`${toolCall.name}-${toolCall.resultSummary}`}>
                        <strong>{toolCall.name}</strong>
                        {toolCall.resultSummary ? (
                          <span>{toolCall.resultSummary}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}

                {response.sources.length > 0 && (
                  <p className="agent-sources">
                    Sources: {formatAgentSources(response.sources)}
                  </p>
                )}

              </div>
            </div>
          )}
        </div>

        <form className="agent-chat-form" onSubmit={submitAgentQuestion}>
          <textarea
            aria-label="Message the accounting agent"
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Message the accounting agent..."
            value={question}
          ></textarea>
          <button disabled={loading || !question.trim()} type="submit">
            Send
          </button>
        </form>
      </article>
    </section>
  )
}

function PeriodProgress({
  activeStep,
  isStepComplete = () => false,
  isStepLocked = () => false,
  items,
  setActivePage,
}: {
  activeStep: number
  isStepComplete?: (page: Page) => boolean
  isStepLocked?: (page: Page) => boolean
  items: { id: Page; label: string }[]
  setActivePage: (page: Page) => void
}) {
  return (
    <section className="period-progress" aria-label="Period process progress">
      <div className="period-progress-track">
        <div
          className="period-progress-segments"
          style={{ gridTemplateColumns: `repeat(${items.length - 1}, minmax(0, 1fr))` }}
        >
          {items.slice(0, -1).map((item) => (
            <span
              className={isStepComplete(item.id) ? 'complete' : ''}
              key={item.id}
            ></span>
          ))}
        </div>
      </div>
      <div className="period-progress-steps">
        {items.map((item, index) => {
          const complete = isStepComplete(item.id)
          const locked = isStepLocked(item.id)
          const state =
            complete
              ? 'complete'
              : index === activeStep
                ? 'current'
                : 'upcoming'

          return (
            <button
              className={`period-step ${state}${locked ? ' locked' : ''}`}
              key={item.id}
              onClick={() => setActivePage(item.id)}
              type="button"
            >
              <span className="period-step-dot">
                {complete ? '' : index + 1}
              </span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function LockedProcessPage({
  loading,
  text,
  title,
}: {
  loading: boolean
  text: string
  title: string
}) {
  return (
    <section className="content-grid">
      <article className="panel wide full locked-panel">
        <p className="eyebrow">Pending approval</p>
        <h3>{loading ? 'Checking period status...' : title}</h3>
        <p className="summary-text small">{text}</p>
      </article>
    </section>
  )
}

function DashboardPage({
  currentPeriod,
  etsyRows,
  importHistory,
  importsLoading,
  incomeError,
  incomeLoading,
  incomeReport,
  journalEntries,
  transactionsError,
  transactionsLoading,
  trialBalanceError,
  trialBalanceLines,
  trialBalanceLoading,
}: {
  currentPeriod: AccountingPeriod | null
  etsyRows: EtsyRow[]
  importHistory: ImportHistoryRow[]
  importsLoading: boolean
  incomeError: string
  incomeLoading: boolean
  incomeReport: ApiIncomeStatement | null
  journalEntries: JournalEntry[]
  transactionsError: string
  transactionsLoading: boolean
  trialBalanceError: string
  trialBalanceLines: TrialBalanceLine[]
  trialBalanceLoading: boolean
}) {
  const trialDebitTotal = trialBalanceLines.reduce(
    (total, line) => total + line.debitBalance,
    0,
  )
  const trialCreditTotal = trialBalanceLines.reduce(
    (total, line) => total + line.creditBalance,
    0,
  )
  const trialBalanced =
    trialBalanceLines.length > 0 &&
    roundCurrency(trialDebitTotal) === roundCurrency(trialCreditTotal)
  const periodLabel = currentPeriod?.label ?? 'No period selected'
  const importedRows = importHistory.reduce(
    (total, row) => total + row.storedRows,
    0,
  )
  const pendingEntries = journalEntries.filter((entry) => entry.status === 'Draft').length
  const flaggedEntries = journalEntries.filter((entry) => entry.status === 'Flagged').length
  const topExpenses = [...(incomeReport?.sections.expenses ?? [])]
    .sort((first, second) => Math.abs(second.amount) - Math.abs(first.amount))
    .slice(0, 4)
  const maxExpense = Math.max(
    ...topExpenses.map((line) => Math.abs(line.amount)),
    0,
  )
  const metrics: Metric[] = [
    {
      label: 'Net income',
      value: incomeReport ? money.format(incomeReport.totals.net_income) : '-',
      helper: incomeLoading ? 'Loading income statement' : periodLabel,
    },
    {
      label: 'Net revenue',
      value: incomeReport ? money.format(incomeReport.totals.net_revenue) : '-',
      helper: incomeReport
        ? `${incomeReport.sections.revenue.length} revenue account${incomeReport.sections.revenue.length === 1 ? '' : 's'}`
        : 'Waiting for report data',
    },
    {
      label: 'Expenses',
      value: incomeReport ? money.format(incomeReport.totals.total_expenses) : '-',
      helper: incomeReport
        ? `${incomeReport.sections.expenses.length} expense account${incomeReport.sections.expenses.length === 1 ? '' : 's'}`
        : 'Waiting for report data',
    },
    {
      label: 'Trial balance',
      value: trialBalanceLoading
        ? 'Loading'
        : trialBalanceLines.length
          ? trialBalanced
            ? 'Balanced'
            : 'Review'
          : '-',
      helper: trialBalanceLines.length
        ? `${money.format(trialDebitTotal)} debit / ${money.format(trialCreditTotal)} credit`
        : 'Waiting for balances',
    },
  ]
  const summaryText = buildDashboardSummary(
    periodLabel,
    incomeReport,
    trialBalanced,
    pendingEntries,
    flaggedEntries,
  )

  return (
    <>
      <section className="metrics-grid" aria-label="Monthly metrics">
        {metrics.map((metric) => (
          <MetricCard key={metric.label} {...metric} />
        ))}
      </section>

      <section className="content-grid">
        <article className="panel wide dashboard-summary-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Summary</p>
              <h3>{periodLabel}</h3>
            </div>
          </div>
          {incomeError || trialBalanceError ? (
            <StatusState
              title="Dashboard data unavailable"
              text={incomeError || trialBalanceError}
              tone="error"
            />
          ) : (
            <p className="summary-text">{summaryText}</p>
          )}
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Expense mix</p>
              <h3>Cost pressure</h3>
            </div>
          </div>
          {incomeLoading ? (
            <StatusState
              title="Loading expenses"
              text="Reading income statement lines from the backend."
            />
          ) : topExpenses.length ? (
            <div className="bars">
              {topExpenses.map((line) => (
                <BarRow
                  amount={Math.abs(line.amount)}
                  key={line.account_code}
                  label={line.account_name}
                  max={maxExpense}
                />
              ))}
            </div>
          ) : (
            <StatusState
              title="No expenses"
              text="No expense account balances are present for this period."
            />
          )}
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Accounting</p>
              <h3>Posting status</h3>
            </div>
          </div>
          <div className="stat-list">
            <StatRow
              label="CSV imports"
              value={importsLoading ? 'Loading' : String(importHistory.length)}
            />
            <StatRow
              label="Imported rows"
              value={importsLoading ? 'Loading' : String(importedRows)}
            />
            <StatRow
              label="Raw Etsy rows"
              value={transactionsLoading ? 'Loading' : String(etsyRows.length)}
            />
            <StatRow
              label="Journal entries"
              value={transactionsLoading ? 'Loading' : String(journalEntries.length)}
            />
            <StatRow label="Pending entries" value={String(pendingEntries)} />
            <StatRow label="Flagged entries" value={String(flaggedEntries)} />
          </div>
        </article>

        <article className="panel wide dashboard-journal-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Recent journal entries</p>
              <h3>Accounting activity</h3>
            </div>
          </div>
          {transactionsError ? (
            <StatusState
              title="Transactions unavailable"
              text={transactionsError}
              tone="error"
            />
          ) : transactionsLoading ? (
            <StatusState
              title="Loading journal entries"
              text="Reading proposed entries for the selected period."
            />
          ) : journalEntries.length ? (
            <JournalTable rows={journalEntries.slice(0, 5)} />
          ) : (
            <StatusState
              title="No journal entries"
              text="Import transactions to populate dashboard activity."
            />
          )}
        </article>
      </section>
    </>
  )
}

function LedgerPage({
  error,
  loading,
  periods,
}: {
  error: string
  loading: boolean
  periods: LedgerPeriod[]
}) {
  const [ledgerSearch, setLedgerSearch] = useState('')
  const [ledgerSortOrder, setLedgerSortOrder] = useState<'desc' | 'asc'>('desc')
  const [ledgerPeriodFilter, setLedgerPeriodFilter] = useState('all')
  const filteredPeriods = useMemo(
    () => filterLedgerPeriods(
      periods,
      ledgerSearch,
      ledgerPeriodFilter,
      ledgerSortOrder,
    ),
    [ledgerPeriodFilter, ledgerSearch, ledgerSortOrder, periods],
  )

  if (loading) {
    return (
      <section className="content-grid">
        <article className="panel wide full locked-panel">
          <p className="eyebrow">Posted ledger</p>
          <h3>Loading permanent ledger</h3>
          <p className="summary-text small">
            Reading posted journal entries from the backend.
          </p>
        </article>
      </section>
    )
  }

  if (error) {
    return (
      <section className="content-grid">
        <article className="panel wide full locked-panel">
          <p className="eyebrow">Posted ledger</p>
          <h3>Ledger unavailable</h3>
          <p className="summary-text small">{error}</p>
        </article>
      </section>
    )
  }

  if (periods.length === 0) {
    return (
      <section className="content-grid">
        <article className="panel wide full locked-panel">
          <p className="eyebrow">Posted ledger</p>
          <h3>No transactions posted yet</h3>
          <p className="summary-text small">
            Confirm a period review to post approved journal entries into the
            permanent ledger.
          </p>
        </article>
      </section>
    )
  }

  return (
    <section className="statements-stack">
      <article className="panel ledger-search-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Search</p>
            <h3>Find posted entries</h3>
          </div>
        </div>
        <div className="filter-stack ledger-filter-grid">
          <label>
            Search
            <input
              onChange={(event) => setLedgerSearch(event.target.value)}
              placeholder="ID, account, memo"
              value={ledgerSearch}
            />
          </label>
          <label>
            Sort
            <select
              onChange={(event) =>
                setLedgerSortOrder(event.target.value as 'desc' | 'asc')
              }
              value={ledgerSortOrder}
            >
              <option value="desc">Newest first</option>
              <option value="asc">Oldest first</option>
            </select>
          </label>
          <label>
            Period
            <select
              onChange={(event) => setLedgerPeriodFilter(event.target.value)}
              value={ledgerPeriodFilter}
            >
              <option value="all">All periods</option>
              {periods.map((period) => (
                <option
                  key={period.periodStart ?? period.label}
                  value={period.periodStart ?? period.label}
                >
                  {period.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </article>
      {filteredPeriods.length === 0 ? (
        <article className="panel locked-panel">
          <p className="eyebrow">Posted ledger</p>
          <h3>No matching entries</h3>
          <p className="summary-text small">
            Try a different memo, account, ID, amount, or period.
          </p>
        </article>
      ) : null}
      {filteredPeriods.map((period) => (
        <article className="panel" key={period.periodStart ?? period.label}>
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Posted ledger</p>
              <h3>{period.label}</h3>
            </div>
            <span className="tag positive">{period.entries.length} posted</span>
          </div>
          <GeneralJournalTable rows={period.entries} scroll />
        </article>
      ))}
    </section>
  )
}

function GenerateCsvPage() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [generatedCsvFiles, setGeneratedCsvFiles] = useState<GeneratedCsvFile[]>([])
  const [selectedGeneratedMonth, setSelectedGeneratedMonth] = useState('')
  const [generateCsvUploading, setGenerateCsvUploading] = useState(false)
  const [generateCsvError, setGenerateCsvError] = useState('')
  const [recentGeneratedImports, setRecentGeneratedImports] = useState<
    { filename: string; status: string; detail: string }[]
  >([])
  const selectedGeneratedFile =
    generatedCsvFiles.find((file) => file.monthKey === selectedGeneratedMonth) ??
    generatedCsvFiles[0] ??
    null
  const generatedCsvRows = selectedGeneratedFile
    ? parseGeneratedTransactionCsv(selectedGeneratedFile.csvText)
    : []

  async function handleGenerateCsvFile(file: File) {
    setGenerateCsvUploading(true)
    setGenerateCsvError('')

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/generate-csv/variable-costs', {
        method: 'POST',
        body: formData,
      })
      const text = await response.text()

      if (!response.ok) {
        throw new Error(parseApiErrorText(text))
      }

      const data = JSON.parse(text) as GenerateCsvResponse
      const files = data.files ?? []

      setGeneratedCsvFiles(files)
      setSelectedGeneratedMonth(files[0]?.monthKey ?? '')
      setRecentGeneratedImports((imports) => [
        {
          filename: file.name,
          status: 'Generated',
          detail: `${data.fileCount} monthly CSV${data.fileCount === 1 ? '' : 's'} / ${data.totalRows} rows`,
        },
        ...imports.filter((row) => row.filename !== file.name),
      ])
    } catch (error) {
      setGenerateCsvError(
        error instanceof Error
          ? error.message
          : 'Unable to generate this transaction CSV.',
      )
    } finally {
      setGenerateCsvUploading(false)
    }
  }

  function handleGenerateCsvFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]

    if (file) {
      void handleGenerateCsvFile(file)
    }

    event.target.value = ''
  }

  function handleGenerateCsvDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()

    const file = event.dataTransfer.files[0]

    if (file) {
      void handleGenerateCsvFile(file)
    }
  }

  function downloadGeneratedCsv(file: GeneratedCsvFile | null) {
    if (!file) {
      return
    }

    const blob = new Blob([file.csvText], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="generate-csv-layout">
      <div className="generate-csv-top-grid">
        <div className="generate-csv-left-stack">
          <article className="panel generate-csv-upload-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Upload</p>
                <h3>Import accounting data</h3>
              </div>
            </div>
            <div
              className={[
                'upload-zone',
                'generate-csv-upload-zone',
                generateCsvUploading ? 'is-loading' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onDragOver={(event) => event.preventDefault()}
              onDrop={handleGenerateCsvDrop}
            >
              <strong>Etsy CSV upload</strong>
              <p>
                {generateCsvUploading
                  ? 'Generating your transaction CSV...'
                  : 'Drop an Etsy order-items CSV here or choose a file.'}
              </p>
              <input
                accept=".csv,text/csv"
                onChange={handleGenerateCsvFileSelection}
                ref={fileInputRef}
                type="file"
              />
              <button
                disabled={generateCsvUploading}
                onClick={() => fileInputRef.current?.click()}
                type="button"
              >
                {generateCsvUploading ? 'Generating...' : 'Choose CSV'}
              </button>
              {generateCsvError && (
                <p className="inline-error">{generateCsvError}</p>
              )}
            </div>
          </article>

          <article className="panel">
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
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {recentGeneratedImports.length ? (
                    recentGeneratedImports.map((row) => (
                      <tr key={row.filename}>
                        <td>{row.filename}</td>
                        <td>
                          <span className="tag positive">{row.status}</span>
                          <span className="table-note">{row.detail}</span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={2}>No generated CSV imports yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>

      </div>

      <article className="panel csv-builder-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Transaction CSV</p>
            <h3>Draft rows</h3>
          </div>
          <div className="csv-action-group">
            {generatedCsvFiles.length > 1 && (
              <select
                onChange={(event) => setSelectedGeneratedMonth(event.target.value)}
                value={selectedGeneratedFile?.monthKey ?? ''}
              >
                {generatedCsvFiles.map((file) => (
                  <option key={file.monthKey} value={file.monthKey}>
                    {file.monthLabel}
                  </option>
                ))}
              </select>
            )}
            <button className="csv-secondary-button" type="button">Clear draft</button>
            <button className="csv-primary-button" type="button">Confirm rows</button>
          </div>
        </div>
        <div className="csv-preview-table">
          <div className="csv-preview-head">
            <span>Date</span>
            <span>Type</span>
            <span>Memo</span>
            <span>Amount</span>
          </div>
          {generatedCsvRows.length ? (
            generatedCsvRows.map((row, index) => (
              <div key={`${row.sourceId}-${row.debitAccount}-${index}`}>
                <span>{formatCompactDate(row.entryDate)}</span>
                <span>{formatGeneratedTransactionType(row.debitAccount)}</span>
                <span>{row.memo}</span>
                <strong>-{money.format(row.debitAmount)}</strong>
              </div>
            ))
          ) : (
            <div>
              <span>-</span>
              <span>-</span>
              <span>Upload an Etsy order-items CSV to generate monthly draft rows.</span>
              <strong>-</strong>
            </div>
          )}
        </div>
      </article>

      <article className="panel csv-output-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Output</p>
            <h3>Generated file preview</h3>
          </div>
          <span className="tag positive">
            {generatedCsvFiles.length
              ? `${generatedCsvFiles.length} monthly CSV${generatedCsvFiles.length === 1 ? '' : 's'}`
              : 'Transaction CSV'}
          </span>
        </div>
        {generatedCsvFiles.length ? (
          <div className="generated-files-list">
            {generatedCsvFiles.map((file) => (
              <div className="csv-output-card" key={file.monthKey}>
                <div>
                  <strong>{file.monthLabel}</strong>
                  <p>{file.filename} / {file.rowCount} rows</p>
                </div>
                <button
                  className="csv-primary-button"
                  onClick={() => downloadGeneratedCsv(file)}
                  type="button"
                >
                  Download CSV
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="csv-output-card">
            <div>
              <strong>generated_transactions.csv</strong>
              <p>Date, Type, Memo, Amount, Debit Account, Credit Account</p>
            </div>
            <button
              className="csv-primary-button"
              disabled
              type="button"
            >
              Download CSV
            </button>
          </div>
        )}
      </article>

    </section>
  )
}

function StandaloneBalanceSheetPage({
  closed,
  error,
  loading,
  report,
}: {
  closed: boolean
  error: string
  loading: boolean
  report: ApiBalanceSheet | null
}) {
  if (!loading && !error && !report) {
    return (
      <LockedProcessPage
        loading={false}
        title="Balance sheet locked"
        text="Finish closing entries and generate the post-closing trial balance to unlock the finalized balance sheet."
      />
    )
  }

  const sections: BalanceSection[] = report
    ? [
        {
          title: 'Assets',
          lines: [
            ...report.sections.assets.map(balanceSheetLine),
            {
              label: 'Total assets',
              amount: report.totals.total_assets,
              kind: 'total',
            },
          ],
        },
        {
          title: 'Liabilities',
          lines: [
            ...report.sections.liabilities.map(balanceSheetLine),
            {
              label: 'Total liabilities',
              amount: report.totals.total_liabilities,
              kind: 'subtotal',
            },
          ],
        },
        {
          title: 'Equity',
          lines: [
            ...report.sections.equity.map(balanceSheetLine),
            {
              label: 'Total equity',
              amount: report.totals.total_equity,
              kind: 'subtotal',
            },
          ],
        },
      ]
    : []
  const asOfLabel = report
    ? `As of ${formatReportDate(report.as_of_date)}`
    : 'Waiting for post-closing balances'
  const totalAssets = report?.totals.total_assets ?? 0
  const totalLiabilitiesAndEquity =
    report?.totals.total_liabilities_and_equity ?? 0

  return (
    <section className="report-layout">
      <article className="panel report-panel">
        <div className="statement-report-header">
          <h3>EZPrntz</h3>
          <p>Balance Sheet</p>
          <span>{asOfLabel}</span>
        </div>
        {loading ? (
          <StatusState
            text="Reading post-closing account balances from the backend."
            title="Loading balance sheet"
          />
        ) : error ? (
          <StatusState text={error} title="Balance sheet unavailable" tone="error" />
        ) : (
          <div className="balance-grid">
            {sections.map((section) => (
              <div className="statement-section" key={section.title}>
                <h4>{section.title}</h4>
                <StatementTable lines={section.lines} compact />
              </div>
            ))}
          </div>
        )}
      </article>

      <aside className="report-side">
        <article className="panel">
          <div className="panel-heading">
          <div>
            <p className="eyebrow">Equation</p>
            <h3>Chart preview</h3>
          </div>
        </div>
        <p className="summary-text small">
          {closed
            ? 'This balance sheet is pulled from post-closing account balances.'
            : 'The balance sheet remains zero until closing entries are posted.'}
        </p>
        <div className="equation">
          <span>Assets</span>
          <b>{money.format(totalAssets)}</b>
          <span>Liabilities + Equity</span>
          <b>{money.format(totalLiabilitiesAndEquity)}</b>
        </div>
        </article>
      </aside>
    </section>
  )
}

function IncomeSummaryPage({
  error,
  loading,
  snapshots,
}: {
  error: string
  loading: boolean
  snapshots: ApiIncomeStatementSnapshot[]
}) {
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<number | null>(null)
  const selectedSnapshot =
    snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    snapshots[0] ??
    null
  const lines = selectedSnapshot
    ? buildIncomeStatementLines(selectedSnapshot.statement)
    : []

  useEffect(() => {
    if (selectedSnapshotId !== null || snapshots.length === 0) {
      return
    }

    setSelectedSnapshotId(snapshots[0].id)
  }, [selectedSnapshotId, snapshots])

  return (
    <section className="report-layout">
      <article className="panel report-panel">
        <div className="statement-report-header">
          <h3>EZPrntz</h3>
          <p>Income Statement</p>
          <span>
            {selectedSnapshot
              ? `For the month ended ${formatReportDate(selectedSnapshot.periodEnd)}`
              : 'For the month ended'}
          </span>
        </div>
        {loading ? (
          <StatusState
            text="Reading saved income statements from the backend."
            title="Loading income statements"
          />
        ) : error ? (
          <StatusState text={error} title="Income statements unavailable" tone="error" />
        ) : selectedSnapshot ? (
          <StatementTable lines={lines} />
        ) : (
          <StatusState
            text="Confirm a trial balance to save the first income statement."
            title="No saved income statements"
          />
        )}
      </article>

      <aside className="report-side">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Processed periods</p>
              <h3>Saved statements</h3>
            </div>
          </div>
          <div className="filter-stack">
            <label>
              Period
              <select
                disabled={snapshots.length === 0}
                onChange={(event) =>
                  setSelectedSnapshotId(Number(event.target.value))
                }
                value={selectedSnapshot?.id ?? ''}
              >
                {snapshots.length === 0 ? (
                  <option value="">No saved statements</option>
                ) : null}
                {snapshots.map((snapshot) => (
                  <option key={snapshot.id} value={snapshot.id}>
                    {snapshot.periodLabel ??
                      `${formatReportDate(snapshot.periodStart)} - ${formatReportDate(
                        snapshot.periodEnd,
                      )}`}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!selectedSnapshot && (
            <p className="summary-text small">
              Saved income statements will appear here after financial
              statements are generated for a period.
            </p>
          )}
        </article>
      </aside>
    </section>
  )
}
function FinancialStatementsPage({
  trialBalanceLines,
  incomeReport,
  incomeLoading,
  incomeError,
}: {
  trialBalanceLines: TrialBalanceLine[]
  incomeReport: ApiIncomeStatement | null
  incomeLoading: boolean
  incomeError: string
}) {
  const [statementView, setStatementView] = useState<
    'adjusted-trial-balance' | 'income-statement'
  >('income-statement')

  return (
    <section className="statements-stack">
      <article className="panel statement-view-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Financial statements</p>
            <h3>Review period reports</h3>
          </div>
          <div className="segmented">
            <button
              className={
                statementView === 'income-statement' ? 'selected' : ''
              }
              onClick={() => setStatementView('income-statement')}
              type="button"
            >
              Income statement
            </button>
            <button
              className={
                statementView === 'adjusted-trial-balance' ? 'selected' : ''
              }
              onClick={() => setStatementView('adjusted-trial-balance')}
              type="button"
            >
              Adjusted trial balance
            </button>
          </div>
        </div>
      </article>

      {statementView === 'income-statement' ? (
        <IncomeStatementPage
          error={incomeError}
          loading={incomeLoading}
          report={incomeReport}
        />
      ) : (
        <AdjustedTrialBalancePage lines={trialBalanceLines} />
      )}
    </section>
  )
}

function IncomeStatementPage({
  report,
  loading,
  error,
}: {
  report: ApiIncomeStatement | null
  loading: boolean
  error: string
}) {
  const lines = report ? buildIncomeStatementLines(report) : []

  const netIncomeRate =
    report && report.totals.net_revenue
      ? (report.totals.net_income / report.totals.net_revenue) * 100
      : 0

  return (
    <section className="report-layout">
      <article className="panel report-panel">
        <div className="statement-report-header">
          <h3>EZPrntz</h3>
          <p>Income Statement</p>
          <span>
            {report
              ? `For the month ended ${formatReportDate(report.end_date)}`
              : 'For the month ended'}
          </span>
        </div>
        {loading ? (
          <StatusState
            text="Reading revenue and expense balances from the backend."
            title="Loading income statement"
          />
        ) : error ? (
          <StatusState text={error} title="Income statement unavailable" tone="error" />
        ) : report ? (
          <StatementTable lines={lines} />
        ) : (
          <StatusState
            text="Confirm the trial balance and refresh the report data."
            title="No income statement data"
          />
        )}
      </article>

      <aside className="report-side">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Margin</p>
              <h3>Net income rate</h3>
            </div>
          </div>
          <strong className="big-number">{netIncomeRate.toFixed(1)}%</strong>
          <p className="muted">Net income divided by net revenue.</p>
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Period</p>
              <h3>Report window</h3>
            </div>
          </div>
          <p className="summary-text small">
            {report
              ? `${formatReportDate(report.start_date)} through ${formatReportDate(
                  report.end_date,
                )}.`
              : 'The report window will appear after the backend responds.'}
          </p>
        </article>
      </aside>
    </section>
  )
}

function TrialBalancePage({
  lines,
  loading,
  error,
  heading = 'January 31, 2026',
  label = 'Before adjustments',
  scrollTable = false,
  showReviewActions = false,
  confirmed = false,
  confirming = false,
  confirmError = '',
  onConfirm,
  periodLabel = '',
  hidePeriodSelector = false,
}: {
  lines: TrialBalanceLine[]
  loading: boolean
  error: string
  heading?: string
  label?: string
  scrollTable?: boolean
  showReviewActions?: boolean
  confirmed?: boolean
  confirming?: boolean
  confirmError?: string
  onConfirm?: () => void
  periodLabel?: string
  hidePeriodSelector?: boolean
}) {
  return (
    <section
      className={
        showReviewActions
          ? 'trial-balance-layout with-review-actions'
          : 'trial-balance-layout'
      }
    >
      <article
        className={
          scrollTable
            ? 'panel report-panel review-trial-balance-panel'
            : 'panel report-panel'
        }
      >
        <div className="panel-heading">
          <div className="trial-balance-heading-stack">
            <p className="eyebrow">{label}</p>
            <h3>{heading}</h3>
            {periodLabel && (
              <p className="trial-balance-period">{periodLabel}</p>
            )}
          </div>
          {!showReviewActions && !hidePeriodSelector && (
            <select aria-label="Trial balance period" defaultValue="2026-01">
              <option value="2026-01">January 2026</option>
              <option value="2026-02">February 2026</option>
            </select>
          )}
        </div>
        {loading ? (
          <StatusState title="Loading trial balance" text="Reading account balances from the backend." />
        ) : error ? (
          <StatusState title="Could not load trial balance" text={error} tone="error" />
        ) : (
          <TrialBalanceTable lines={lines} scroll={scrollTable} />
        )}
      </article>
      {showReviewActions && (
        <aside className="report-side">
          <article className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Next step</p>
                <h3>Review entries</h3>
              </div>
            </div>
            <p className="summary-text small">
              Add manual transactions, void incorrect entries, then confirm the
              unadjusted trial balance before making adjustments.
            </p>
          </article>
          <article className="panel confirm-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Approval</p>
                <h3>Confirm balance</h3>
              </div>
            </div>
            <p className="summary-text small">
              {confirmed
                ? 'This trial balance has been confirmed for the period.'
                : 'Mark this trial balance as expected after your transaction review.'}
            </p>
            {confirmError && <p className="inline-error">{confirmError}</p>}
            <button
              disabled={confirmed || confirming}
              onClick={onConfirm}
              type="button"
            >
              {confirmed
                ? 'Trial balance confirmed'
                : confirming
                  ? 'Confirming...'
                  : 'Confirm trial balance'}
            </button>
          </article>
        </aside>
      )}
    </section>
  )
}

function AdjustedTrialBalancePage({
  lines,
}: {
  lines: TrialBalanceLine[]
}) {
  return (
    <TrialBalancePage
      error=""
      heading="Adjusted Trial Balance"
      label="After adjustments"
      lines={lines}
      loading={false}
      periodLabel="For the month ended January 2026"
      hidePeriodSelector
    />
  )
}

function ClosingPage({
  confirmed,
  entries,
  error,
  generating,
  onConfirmClosingEntries,
}: {
  confirmed: boolean
  entries: JournalEntry[]
  error: string
  generating: boolean
  onConfirmClosingEntries: () => Promise<void>
}) {
  return (
    <section className="transactions-layout closing-review-layout">
      <div className="transaction-actions-grid">
        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Manual entry</p>
              <h3>Add closing entry</h3>
            </div>
          </div>
          <form
            className="manual-transaction-form"
            onSubmit={(event) => event.preventDefault()}
          >
            <label>
              Date
              <input defaultValue="2026-01-31" type="date" />
            </label>
            <label>
              Memo
              <input placeholder="What is being closed?" />
            </label>
            <label>
              Debit account
              <select defaultValue="">
                <option value="" disabled>Choose account</option>
                <option value="3900">3900 - Income Summary</option>
                <option value="4000">4000 - Sales Revenue</option>
                <option value="5100">5100 - Etsy Fees Expense</option>
                <option value="5200">5200 - Shipping Expense</option>
              </select>
            </label>
            <label>
              Debit
              <input min="0" placeholder="0.00" step="0.01" type="number" />
            </label>
            <label>
              Credit account
              <select defaultValue="">
                <option value="" disabled>Choose account</option>
                <option value="3000">3000 - Capital</option>
                <option value="3900">3900 - Income Summary</option>
                <option value="4000">4000 - Sales Revenue</option>
                <option value="5200">5200 - Shipping Expense</option>
              </select>
            </label>
            <label>
              Credit
              <input min="0" placeholder="0.00" step="0.01" type="number" />
            </label>
            <button type="submit">Add draft</button>
          </form>
        </article>

        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Correction</p>
              <h3>Void closing entry</h3>
            </div>
          </div>
          <form
            className="void-transaction-form"
            onSubmit={(event) => event.preventDefault()}
          >
            <label>
              Transaction ID
              <input inputMode="numeric" placeholder="Closing entry ID" />
            </label>
            <label>
              Reason
              <select defaultValue="Entered by mistake">
                <option value="Entered by mistake">Entered by mistake</option>
                <option value="Duplicate record">Duplicate record</option>
                <option value="Wrong account">Wrong account</option>
                <option value="Other">Other</option>
              </select>
            </label>
            <label>
              Note
              <input
                className="void-note-input"
                placeholder="Why is this being voided?"
              />
            </label>
            <button className="void-draft-button" type="submit">
              Void draft
            </button>
          </form>
        </article>
      </div>

      <article className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Closing records</p>
            <h3>Transaction explorer</h3>
          </div>
          <span className="tag positive">
            {entries.length} {confirmed ? 'posted' : 'draft'}
          </span>
        </div>
        {error && <p className="inline-error">{error}</p>}
        <div className="records-scroll">
          {generating ? (
            <StatusState
              text="Reading prepared closing entries from the backend."
              title="Loading closing entries"
            />
          ) : entries.length === 0 ? (
            <StatusState
              text="There are no temporary account balances to close for this period."
              title="No closing entries needed"
            />
          ) : (
            <ProposedJournalTable
              rows={entries}
              showEtsyId={false}
            />
          )}
        </div>
      </article>

      <article className="panel confirm-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Approval</p>
            <h3>Confirm closing</h3>
          </div>
        </div>
        <p className="summary-text small">
          {confirmed
            ? 'Closing entries have been posted to the permanent ledger.'
            : entries.length === 0
              ? 'Confirming will close this accounting period without posting closing entries.'
              : 'Confirming will post these closing entries to the permanent ledger and close the accounting period.'}
        </p>
        <button
          disabled={confirmed || generating}
          onClick={() => {
            void onConfirmClosingEntries()
          }}
          type="button"
        >
          {confirmed
            ? 'Closing entries confirmed'
            : generating
              ? 'Confirming...'
              : 'Confirm closing entries'}
        </button>
      </article>
    </section>
  )
}

function PostClosingTrialBalancePage({
  error,
  lines,
  loading,
}: {
  error: string
  lines: TrialBalanceLine[]
  loading: boolean
}) {
  const postClosingLines = lines.filter((line) => {
    const accountType = line.accountType.toLowerCase()

    return (
      ['asset', 'liability', 'equity'].includes(accountType) &&
      line.accountCode !== '3900'
    )
  })

  return (
    <TrialBalancePage
      error={error}
      heading="Post-Closing Trial Balance"
      label="After closing entries"
      lines={postClosingLines}
      loading={loading}
      periodLabel="As of January 31, 2026"
      hidePeriodSelector
    />
  )
}

function TransactionsPage({
  accounts,
  confirmingTrialBalance,
  journalEntries,
  etsyRows,
  loading,
  onAddManualTransaction,
  onConfirmTrialBalance,
  onVoidJournalTransaction,
  periodError,
  trialBalanceConfirmed,
  error,
  transactionView,
  setTransactionView,
  trialBalanceError,
  trialBalanceLines,
  trialBalanceLoading,
}: {
  accounts: Account[]
  confirmingTrialBalance: boolean
  journalEntries: JournalEntry[]
  etsyRows: EtsyRow[]
  loading: boolean
  onAddManualTransaction: (payload: ManualJournalEntryPayload) => Promise<void>
  onConfirmTrialBalance: () => void
  onVoidJournalTransaction: (
    journalEntryId: number,
    reason: string,
    note: string,
  ) => Promise<void>
  periodError: string
  trialBalanceConfirmed: boolean
  error: string
  transactionView: 'journal' | 'raw'
  setTransactionView: (view: 'journal' | 'raw') => void
  trialBalanceError: string
  trialBalanceLines: TrialBalanceLine[]
  trialBalanceLoading: boolean
}) {
  const [manualDate, setManualDate] = useState('2026-01-31')
  const [manualMemo, setManualMemo] = useState('')
  const [manualDebitAccount, setManualDebitAccount] = useState('')
  const [manualDebitAmount, setManualDebitAmount] = useState('')
  const [manualCreditAccount, setManualCreditAccount] = useState('')
  const [manualCreditAmount, setManualCreditAmount] = useState('')
  const [manualSubmitting, setManualSubmitting] = useState(false)
  const [manualError, setManualError] = useState('')
  const [voidTransactionId, setVoidTransactionId] = useState('')
  const [voidReason, setVoidReason] = useState('Entered by mistake')
  const [voidNote, setVoidNote] = useState('')
  const [voidSubmitting, setVoidSubmitting] = useState(false)
  const [voidError, setVoidError] = useState('')
  const [recordSearch, setRecordSearch] = useState('')
  const [accountFilter, setAccountFilter] = useState('all')
  const filteredJournalEntries = useMemo(
    () => filterJournalEntries(journalEntries, recordSearch, accountFilter),
    [accountFilter, journalEntries, recordSearch],
  )
  const filteredEtsyRows = useMemo(
    () => filterEtsyRows(etsyRows, recordSearch),
    [etsyRows, recordSearch],
  )
  const activeRows =
    transactionView === 'journal' ? filteredJournalEntries : filteredEtsyRows

  async function handleManualTransactionSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()
    setManualError('')

    const debit = Number(manualDebitAmount)
    const credit = Number(manualCreditAmount)

    if (
      !manualDate ||
      !manualMemo.trim() ||
      !manualDebitAccount ||
      !manualCreditAccount ||
      Number.isNaN(debit) ||
      Number.isNaN(credit) ||
      debit <= 0 ||
      credit <= 0
    ) {
      setManualError('Fill out the date, memo, accounts, and amounts first.')
      return
    }

    try {
      setManualSubmitting(true)
      await onAddManualTransaction({
        entryDate: manualDate,
        memo: manualMemo.trim(),
        lines: [
          {
            accountCode: manualDebitAccount,
            debit,
            credit: 0,
            memo: manualMemo.trim(),
          },
          {
            accountCode: manualCreditAccount,
            debit: 0,
            credit,
            memo: manualMemo.trim(),
          },
        ],
      })
      setManualMemo('')
      setManualDebitAmount('')
      setManualCreditAmount('')
    } catch (error) {
      setManualError(
        error instanceof Error
          ? error.message
          : 'Unable to add this draft transaction.',
      )
    } finally {
      setManualSubmitting(false)
    }
  }

  async function handleVoidTransactionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setVoidError('')

    const journalEntryId = Number(voidTransactionId)

    if (!Number.isInteger(journalEntryId) || journalEntryId <= 0) {
      setVoidError('Enter a valid journal entry ID.')
      return
    }

    try {
      setVoidSubmitting(true)
      await onVoidJournalTransaction(
        journalEntryId,
        voidReason,
        voidNote.trim(),
      )
      setVoidTransactionId('')
      setVoidNote('')
    } catch (error) {
      setVoidError(
        error instanceof Error
          ? error.message
          : 'Unable to void this draft transaction.',
      )
    } finally {
      setVoidSubmitting(false)
    }
  }

  return (
    <section className="transactions-layout">
      <TrialBalancePage
        error={trialBalanceError}
        heading="Unadjusted Trial Balance"
        label="From posted journal entries"
        lines={trialBalanceLines}
        loading={trialBalanceLoading}
        periodLabel="For the month ended January 2026"
        confirmed={trialBalanceConfirmed}
        confirming={confirmingTrialBalance}
        confirmError={periodError}
        onConfirm={onConfirmTrialBalance}
        scrollTable
        showReviewActions
      />

      <div className="transaction-actions-grid">
        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Manual entry</p>
              <h3>Add transaction</h3>
            </div>
          </div>
          <form
            className="manual-transaction-form"
            onSubmit={handleManualTransactionSubmit}
          >
            <label>
              Date
              <input
                onChange={(event) => setManualDate(event.target.value)}
                type="date"
                value={manualDate}
              />
            </label>
            <label>
              Memo
              <input
                onChange={(event) => setManualMemo(event.target.value)}
                placeholder="What happened?"
                value={manualMemo}
              />
            </label>
            <label>
              Debit account
              <select
                onChange={(event) => setManualDebitAccount(event.target.value)}
                value={manualDebitAccount}
              >
                <option value="" disabled>Choose account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.code}>
                    {account.code} - {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Debit
              <input
                min="0"
                onChange={(event) => setManualDebitAmount(event.target.value)}
                placeholder="0.00"
                step="0.01"
                type="number"
                value={manualDebitAmount}
              />
            </label>
            <label>
              Credit account
              <select
                onChange={(event) => setManualCreditAccount(event.target.value)}
                value={manualCreditAccount}
              >
                <option value="" disabled>Choose account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.code}>
                    {account.code} - {account.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Credit
              <input
                min="0"
                onChange={(event) => setManualCreditAmount(event.target.value)}
                placeholder="0.00"
                step="0.01"
                type="number"
                value={manualCreditAmount}
              />
            </label>
            {manualError && <p className="form-message error">{manualError}</p>}
            <button disabled={manualSubmitting || accounts.length === 0} type="submit">
              {manualSubmitting ? 'Adding draft...' : 'Add draft'}
            </button>
          </form>
        </article>

        <article className="panel transaction-tool">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Correction</p>
              <h3>Void transaction</h3>
            </div>
          </div>
          <form
            className="void-transaction-form"
            onSubmit={handleVoidTransactionSubmit}
          >
            <label>
              Transaction ID
              <input
                inputMode="numeric"
                onChange={(event) => setVoidTransactionId(event.target.value)}
                placeholder="Journal entry ID"
                value={voidTransactionId}
              />
            </label>
            <label>
              Reason
              <select
                onChange={(event) => setVoidReason(event.target.value)}
                value={voidReason}
              >
                <option value="Entered by mistake">Entered by mistake</option>
                <option value="Duplicate record">Duplicate record</option>
                <option value="Wrong account">Wrong account</option>
                <option value="Other">Other</option>
              </select>
            </label>
            <label>
              Note
              <input
                className="void-note-input"
                onChange={(event) => setVoidNote(event.target.value)}
                placeholder="Why is this being voided?"
                value={voidNote}
              />
            </label>
            {voidError && <p className="form-message error">{voidError}</p>}
            <button
              className="void-draft-button"
              disabled={voidSubmitting}
              type="submit"
            >
              {voidSubmitting ? 'Voiding draft...' : 'Void draft'}
            </button>
          </form>
        </article>
      </div>

      <article className="panel transaction-filters-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Filters</p>
            <h3>Find records</h3>
          </div>
        </div>
        <div className="filter-stack transaction-filter-grid">
          <label>
            Search
            <input
              onChange={(event) => setRecordSearch(event.target.value)}
              placeholder="ID, account, memo"
              value={recordSearch}
            />
          </label>
          <label>
            Account
            <select
              onChange={(event) => setAccountFilter(event.target.value)}
              value={accountFilter}
            >
              <option value="all">All accounts</option>
              <option value="flagged">Flagged</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.code}>
                  {account.code} - {account.name}
                </option>
              ))}
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
          ) : activeRows.length === 0 && transactionView === 'journal' && etsyRows.length > 0 ? (
            <StatusState title="No journal entries yet" text="The CSV rows are imported, but they have not been posted into journal entries yet." />
          ) : activeRows.length === 0 ? (
            <StatusState title="No transactions found" text="Import and post transactions to see them here." />
          ) : transactionView === 'journal' ? (
            <ProposedJournalTable rows={filteredJournalEntries} />
          ) : (
            <RawEtsyTable rows={filteredEtsyRows} />
          )}
        </div>
      </article>
    </section>
  )
}

function ImportsPage({
  confirmedPeriod,
  error,
  history,
  importType,
  importing,
  loadingHistory,
  onConfirmPeriod,
  onDeleteImport,
  periodConfirming,
  periodError,
  result,
  selectedMonth,
  selectedYear,
  setConfirmedPeriod,
  setImportType,
  setSelectedMonth,
  setSelectedYear,
  uploadImport,
}: {
  confirmedPeriod: { month: string; year: string } | null
  error: string
  history: ImportHistoryRow[]
  importType: ImportCsvType
  importing: boolean
  loadingHistory: boolean
  onConfirmPeriod: (month: string, year: string) => Promise<void>
  onDeleteImport: (importId: number) => Promise<void>
  periodConfirming: boolean
  periodError: string
  result: ImportResult | null
  selectedMonth: string
  selectedYear: string
  setConfirmedPeriod: (period: { month: string; year: string } | null) => void
  setImportType: (importType: ImportCsvType) => void
  setSelectedMonth: (month: string) => void
  setSelectedYear: (year: string) => void
  uploadImport: (file: File, importType: ImportCsvType) => Promise<void>
}) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedDeleteImportId, setSelectedDeleteImportId] = useState('')
  const [deleteImportLoading, setDeleteImportLoading] = useState(false)
  const [deleteImportError, setDeleteImportError] = useState('')
  const periodSelected = selectedMonth !== '' && selectedYear.trim() !== ''
  const periodConfirmed =
    confirmedPeriod?.month === selectedMonth &&
    confirmedPeriod?.year === selectedYear.trim()

  function handleFileSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]

    if (file && periodConfirmed) {
      void uploadImport(file, importType)
    }

    event.target.value = ''
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()

    const file = event.dataTransfer.files[0]

    if (file && periodConfirmed) {
      void uploadImport(file, importType)
    }
  }

  function confirmPeriod() {
    if (!periodSelected) {
      return
    }

    void onConfirmPeriod(selectedMonth, selectedYear.trim())
  }

  async function handleDeleteImport() {
    const importId = Number(selectedDeleteImportId)

    setDeleteImportError('')

    if (!Number.isInteger(importId) || importId <= 0) {
      setDeleteImportError('Choose a CSV import to delete.')
      return
    }

    try {
      setDeleteImportLoading(true)
      await onDeleteImport(importId)
      setSelectedDeleteImportId('')
    } catch (error) {
      setDeleteImportError(
        error instanceof Error
          ? error.message
          : 'Unable to delete this CSV import.',
      )
    } finally {
      setDeleteImportLoading(false)
    }
  }

  return (
    <section className="content-grid">
      <article className="panel wide import-upload-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Upload</p>
            <h3>Import accounting data</h3>
          </div>
        </div>
        <label className="import-type-selector">
          CSV type
          <select
            onChange={(event) =>
              setImportType(event.target.value as ImportCsvType)
            }
            value={importType}
          >
            <option value="etsy">Etsy statement CSV</option>
            <option value="transactions">Generated transaction CSV</option>
          </select>
        </label>
        <div
          className={[
            'upload-zone',
            importing ? 'is-loading' : '',
            !periodConfirmed ? 'is-disabled' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <strong>
            {importType === 'transactions'
              ? 'Transaction CSV upload'
              : 'Etsy CSV upload'}
          </strong>
          <p>
            {importing
              ? `Importing your ${importType === 'transactions' ? 'transaction' : 'Etsy'} CSV...`
              : periodConfirmed
                ? importType === 'transactions'
                  ? 'Drop a generated transaction CSV here or choose a file.'
                  : 'Drop a monthly Etsy statement here or choose a file.'
                : 'Confirm an accounting month before uploading a CSV.'}
          </p>
          <input
            accept=".csv,text/csv"
            onChange={handleFileSelection}
            ref={fileInputRef}
            type="file"
          />
          <button
            disabled={importing || !periodConfirmed}
            onClick={() => fileInputRef.current?.click()}
            type="button"
          >
            {importing
              ? 'Importing...'
              : periodConfirmed
                ? 'Choose CSV'
                : 'Confirm period first'}
          </button>
          {error && <p className="inline-error">{error}</p>}
          {result && !error && (
            <div className="import-result">
              <strong>{result.filename}</strong>
              <span>
                {result.imported} rows imported, {result.posted} journal entries posted
              </span>
            </div>
          )}
        </div>
      </article>

      <div className="import-side-stack">
        <article className="panel period-selector-panel">
          <div>
            <p className="eyebrow">Period</p>
            <h3>Accounting month</h3>
          </div>
          <div className="period-selector-controls">
            <label>
              Month
              <select
                onChange={(event) => {
                  setSelectedMonth(event.target.value)
                  setConfirmedPeriod(null)
                }}
                value={selectedMonth}
              >
                <option value="" disabled>Choose month</option>
                <option value="january">January</option>
                <option value="february">February</option>
                <option value="march">March</option>
                <option value="april">April</option>
                <option value="may">May</option>
                <option value="june">June</option>
                <option value="july">July</option>
                <option value="august">August</option>
                <option value="september">September</option>
                <option value="october">October</option>
                <option value="november">November</option>
                <option value="december">December</option>
              </select>
            </label>
            <label>
              Year
              <input
                inputMode="numeric"
                onChange={(event) => {
                  setSelectedYear(event.target.value)
                  setConfirmedPeriod(null)
                }}
                placeholder="2026"
                value={selectedYear}
              />
            </label>
          </div>
          <button
            className="period-confirm-button"
            disabled={!periodSelected || periodConfirmed || periodConfirming}
            onClick={confirmPeriod}
            type="button"
          >
            {periodConfirming
              ? 'Confirming...'
              : periodConfirmed
                ? 'Period confirmed'
                : 'Confirm period'}
          </button>
          {periodError && <p className="form-message error">{periodError}</p>}
        </article>

        <article className="panel import-delete-panel">
          <div>
            <p className="eyebrow">Remove CSV</p>
            <h3>Delete an import</h3>
          </div>
          <label>
            CSV import
            <select
              disabled={loadingHistory || history.length === 0}
              onChange={(event) => setSelectedDeleteImportId(event.target.value)}
              value={selectedDeleteImportId}
            >
              <option value="">
                {history.length ? 'Choose import' : 'No imports available'}
              </option>
              {history.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.filename}
                </option>
              ))}
            </select>
          </label>
          <p className="summary-text small">
            This removes the selected CSV, its raw rows, and its unposted draft
            journal entries.
          </p>
          {deleteImportError && (
            <p className="form-message error">{deleteImportError}</p>
          )}
          <button
            className="danger-button"
            disabled={
              deleteImportLoading ||
              loadingHistory ||
              history.length === 0 ||
              selectedDeleteImportId === ''
            }
            onClick={handleDeleteImport}
            type="button"
          >
            {deleteImportLoading ? 'Deleting...' : 'Delete selected CSV'}
          </button>
        </article>
      </div>

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
              {loadingHistory ? (
                <tr>
                  <td colSpan={5}>Loading import history...</td>
                </tr>
              ) : history.length ? (
                history.map((row) => (
                  <tr key={row.id}>
                    <td>{row.filename}</td>
                    <td>{formatSource(row.source)}</td>
                    <td>{row.rowCount}</td>
                    <td>{row.postedRows}</td>
                    <td>
                      <span className="tag positive">
                        {row.status === 'posted' ? 'Posted' : 'Imported'}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5}>No imports found in the database.</td>
                </tr>
              )}
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
        <div
          className={[
            line.kind ?? '',
            line.indent ? 'indented' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          key={line.label}
        >
          <span>{line.label}</span>
          {line.kind === 'section' ? null : (
            <strong>{money.format(line.amount)}</strong>
          )}
        </div>
      ))}
    </div>
  )
}

function TrialBalanceTable({
  lines,
  scroll = false,
}: {
  lines: TrialBalanceLine[]
  scroll?: boolean
}) {
  return (
    <div className={scroll ? 'table-wrap trial-balance-scroll' : 'table-wrap'}>
      <table>
        <thead>
          <tr>
            <th>Account</th>
            <th>Type</th>
            <th>Debit balance</th>
            <th>Credit balance</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.accountCode}>
              <td>
                <div className="account-cell">
                  <strong>{line.accountName}</strong>
                  <span>{line.accountCode}</span>
                </div>
              </td>
              <td>{line.accountType}</td>
              <td>{line.debitBalance ? money.format(line.debitBalance) : '-'}</td>
              <td>{line.creditBalance ? money.format(line.creditBalance) : '-'}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td>Total</td>
            <td></td>
            <td>
              {money.format(
                lines.reduce((total, line) => total + line.debitBalance, 0),
              )}
            </td>
            <td>
              {money.format(
                lines.reduce((total, line) => total + line.creditBalance, 0),
              )}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

function GeneralJournalTable({
  rows,
  scroll = false,
}: {
  rows: JournalEntry[]
  scroll?: boolean
}) {
  return (
    <div
      className={
        scroll
          ? 'table-wrap general-journal-wrap general-journal-scroll'
          : 'table-wrap general-journal-wrap'
      }
    >
      <table className="general-journal-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Date</th>
            <th>Accounts</th>
            <th>Post ref</th>
            <th>Debit</th>
            <th>Credit</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((entry) => (
            <Fragment key={entry.id}>
              {entry.debits.map((line, index) => (
                <tr key={`${entry.id}-debit-${line.accountCode}-${index}`}>
                  <td>{index === 0 ? entry.id : ''}</td>
                  <td>{index === 0 ? formatCompactDate(entry.date) : ''}</td>
                  <td>{line.accountName}</td>
                  <td>{line.accountCode}</td>
                  <td className="ledger-money">{money.format(line.amount)}</td>
                  <td></td>
                </tr>
              ))}
              {entry.credits.map((line, index) => (
                <tr key={`${entry.id}-credit-${line.accountCode}-${index}`}>
                  <td>{entry.debits.length === 0 && index === 0 ? entry.id : ''}</td>
                  <td>{entry.debits.length === 0 && index === 0 ? formatCompactDate(entry.date) : ''}</td>
                  <td className="credit-particular">{line.accountName}</td>
                  <td>{line.accountCode}</td>
                  <td></td>
                  <td className="ledger-money">{money.format(line.amount)}</td>
                </tr>
              ))}
              <tr className="journal-memo-row">
                <td></td>
                <td></td>
                <td colSpan={4}>
                  {entry.memo || `Posted journal entry ${entry.id}`}
                </td>
              </tr>
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function JournalTable({ rows }: { rows: JournalEntry[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>EtsyID</th>
            <th>Date</th>
            <th>Memo</th>
            <th>Debit</th>
            <th>Credit</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.id}</td>
              <td className="numeric-id-cell">{row.etsyId ?? '-'}</td>
              <td>{formatCompactDate(row.date)}</td>
              <td>{row.memo}</td>
              <td><AccountLineList lines={row.debits} /></td>
              <td><AccountLineList lines={row.credits} /></td>
              <td><span className="tag positive">{row.status}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProposedJournalTable({
  rows,
  showEtsyId = true,
}: {
  rows: JournalEntry[]
  showEtsyId?: boolean
}) {
  const memoColSpan = showEtsyId ? 5 : 5

  return (
    <div className="table-wrap proposed-journal-wrap">
      <table
        className={[
          'general-journal-table',
          'proposed-journal-table',
          showEtsyId ? '' : 'no-etsy-id',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <colgroup>
          <col className="journal-col-id" />
          {showEtsyId && <col className="journal-col-etsy-id" />}
          <col className="journal-col-date" />
          <col className="journal-col-accounts" />
          <col className="journal-col-post-ref" />
          <col className="journal-col-money" />
          <col className="journal-col-money" />
          <col className="journal-col-status" />
        </colgroup>
        <thead>
          <tr>
            <th>ID</th>
            {showEtsyId && <th>EtsyID</th>}
            <th>Date</th>
            <th>Accounts</th>
            <th>Post ref</th>
            <th>Debit</th>
            <th>Credit</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((entry) => (
            <Fragment key={entry.id}>
              {entry.debits.map((line, index) => (
                <tr key={`${entry.id}-proposed-debit-${line.accountCode}-${index}`}>
                  <td>{index === 0 ? entry.id : ''}</td>
                  {showEtsyId && <td>{index === 0 ? entry.etsyId ?? '-' : ''}</td>}
                  <td>{index === 0 ? formatCompactDate(entry.date) : ''}</td>
                  <td>{line.accountName}</td>
                  <td>{line.accountCode}</td>
                  <td className="ledger-money">{money.format(line.amount)}</td>
                  <td></td>
                  <td>
                    {index === 0 ? (
                      <span className="tag positive">{entry.status}</span>
                    ) : null}
                  </td>
                </tr>
              ))}
              {entry.credits.map((line, index) => (
                <tr key={`${entry.id}-proposed-credit-${line.accountCode}-${index}`}>
                  <td>{entry.debits.length === 0 && index === 0 ? entry.id : ''}</td>
                  {showEtsyId && (
                    <td>
                      {entry.debits.length === 0 && index === 0
                        ? entry.etsyId ?? '-'
                        : ''}
                    </td>
                  )}
                  <td>
                    {entry.debits.length === 0 && index === 0
                      ? formatCompactDate(entry.date)
                      : ''}
                  </td>
                  <td className="credit-particular">{line.accountName}</td>
                  <td>{line.accountCode}</td>
                  <td></td>
                  <td className="ledger-money">{money.format(line.amount)}</td>
                  <td>
                    {entry.debits.length === 0 && index === 0 ? (
                      <span className="tag positive">{entry.status}</span>
                    ) : null}
                  </td>
                </tr>
              ))}
              <tr className="journal-memo-row">
                <td></td>
                {showEtsyId && <td></td>}
                <td></td>
                <td colSpan={memoColSpan}>
                  {entry.memo || `Proposed journal entry ${entry.id}`}
                </td>
              </tr>
            </Fragment>
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
            <th>ID</th>
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
              <td>{row.id}</td>
              <td>{formatCompactDate(row.date)}</td>
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

export default App
