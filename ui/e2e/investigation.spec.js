// @ts-check
import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Fill out the event form and submit. */
async function submitIncident(page, { jobName, errorType, errorMessage, environment, source } = {}) {
  // Fill form fields
  if (source) {
    await page.locator('select').first().selectOption(source)
  }
  if (environment) {
    await page.locator('select').nth(1).selectOption(environment)
  }

  await page.getByPlaceholder('e.g. cdc_orders').fill(jobName || 'e2e_test_job')

  if (errorType) {
    await page.locator('select').nth(2).selectOption(errorType)
  }

  await page.getByPlaceholder('Paste the error').fill(
    errorMessage || 'Column CUSTOMER_ID missing in target table'
  )

  // Submit
  await page.getByRole('button', { name: 'Run Investigation' }).click()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Incident Investigator E2E', () => {

  test('page loads with correct title and header', async ({ page }) => {
    await page.goto('/')

    await expect(page).toHaveTitle('Incident Investigator')
    await expect(page.locator('.app-title')).toHaveText('Incident Investigator')
    await expect(page.locator('.app-subtitle')).toContainText('Autonomous data pipeline')
  })

  test('shows the event form on initial load', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('Submit Incident Event')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Run Investigation' })).toBeVisible()
    await expect(page.getByPlaceholder('e.g. cdc_orders')).toBeVisible()
  })

  test('sidebar shows history section', async ({ page }) => {
    await page.goto('/')

    await expect(page.locator('.sidebar')).toBeVisible()
    await expect(page.getByText('History')).toBeVisible()
    await expect(page.getByRole('button', { name: '+ New' })).toBeVisible()
  })

  test('form validation requires all fields', async ({ page }) => {
    await page.goto('/')

    // Try submitting without filling required fields
    const submitBtn = page.getByRole('button', { name: 'Run Investigation' })

    // Job name is required — clicking submit should not navigate away
    await submitBtn.click()

    // Form should still be visible (HTML5 validation prevents submit)
    await expect(page.getByText('Submit Incident Event')).toBeVisible()
  })

  test('full investigation pipeline — submit and see results', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'cdc_orders_e2e',
      errorType: 'schema_mismatch',
      errorMessage: 'Column CUSTOMER_ID missing in target — schema drift detected',
      environment: 'dev',
      source: 'airflow',
    })

    // Should show loading overlay
    await expect(page.locator('.loading-overlay')).toBeVisible()
    await expect(page.getByText('Running investigation pipeline')).toBeVisible()

    // Wait for pipeline to complete — loading goes away, pipeline view appears
    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.loading-overlay')).not.toBeVisible()

    // Verify pipeline header shows the job name and source
    await expect(page.locator('.pipeline-job')).toHaveText('cdc_orders_e2e')
    await expect(page.locator('.pipeline-attrs')).toContainText('airflow')

    // Verify all 6 pipeline steps are rendered
    const stepCards = page.locator('.step-card')
    await expect(stepCards).toHaveCount(6)

    // Classification step should be complete
    const classificationCard = stepCards.nth(0)
    await expect(classificationCard).toHaveClass(/state-complete/)
    await expect(classificationCard.locator('.step-title')).toHaveText('Classification')

    // Check that a terminal status badge is shown
    const outcomeBadge = page.locator('.pipeline-outcome .badge')
    await expect(outcomeBadge).toBeVisible()
    const outcomeText = await outcomeBadge.textContent()
    expect(['APPROVED', 'REJECTED', 'APPROVAL_REQUIRED']).toContain(outcomeText)
  })

  test('completed investigation appears in sidebar', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'sidebar_test_job',
      errorMessage: 'Timeout waiting for database response after 30s',
      errorType: 'timeout',
    })

    // Wait for results
    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Check sidebar has the new entry
    const historyItem = page.locator('.history-item').first()
    await expect(historyItem).toContainText('sidebar_test_job')
  })

  test('clicking sidebar item loads full incident detail', async ({ page }) => {
    await page.goto('/')

    // Submit first investigation
    await submitIncident(page, {
      jobName: 'first_job',
      errorMessage: 'Schema mismatch on column user_id',
    })
    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Click "+ New" to go back to form
    await page.getByRole('button', { name: '+ New' }).click()
    await expect(page.getByText('Submit Incident Event')).toBeVisible()

    // Submit second investigation
    await submitIncident(page, {
      jobName: 'second_job',
      errorMessage: 'Connection timeout to Redshift cluster',
      errorType: 'timeout',
    })
    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Now click the first_job item in sidebar to switch back
    const firstItem = page.locator('.history-item').filter({ hasText: 'first_job' }).first()
    await firstItem.click()

    // Pipeline view should update to show the first job
    await expect(page.locator('.pipeline-job')).toHaveText('first_job')
  })

  test('new button returns to the form from results view', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'newbtn_test',
      errorMessage: 'Data quality check failed',
    })
    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Click "+ New"
    await page.getByRole('button', { name: '+ New' }).click()

    // Should be back on the form
    await expect(page.getByText('Submit Incident Event')).toBeVisible()
    await expect(page.locator('.pipeline-view')).not.toBeVisible()
  })

  test('pipeline steps show correct detail content', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'detail_check_job',
      errorType: 'schema_mismatch',
      errorMessage: 'Column CUSTOMER_ID not found in target table — possible schema drift',
      environment: 'prod',
    })

    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Classification should show a type badge
    const classCard = page.locator('.step-card').nth(0)
    await expect(classCard.locator('.badge')).toBeVisible()

    // Diagnosis should show root cause text
    const diagCard = page.locator('.step-card').nth(1)
    if (await diagCard.locator('.step-body').isVisible()) {
      await expect(diagCard.locator('.kv-label').first()).toHaveText('Root cause')
    }

    // Risk step should show a score
    const riskCard = page.locator('.step-card').nth(4)
    if (await riskCard.locator('.step-body').isVisible()) {
      await expect(riskCard.locator('.progress-label')).toBeVisible()
    }

    // Decision step should show an outcome badge
    const decisionCard = page.locator('.step-card').nth(5)
    if (await decisionCard.locator('.step-body').isVisible()) {
      await expect(decisionCard.locator('.badge')).toBeVisible()
    }
  })

  test('dev environment incident gets auto-approved', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'dev_auto_approve',
      errorType: 'schema_mismatch',
      errorMessage: 'Column mismatch on user_id field',
      environment: 'dev',
    })

    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Dev + schema_mismatch should result in auto-approve (low risk)
    const outcomeBadge = page.locator('.pipeline-outcome .badge')
    await expect(outcomeBadge).toHaveText('APPROVED')
  })

  test('prod environment incident requires human approval', async ({ page }) => {
    await page.goto('/')

    await submitIncident(page, {
      jobName: 'prod_human_review',
      errorType: 'schema_mismatch',
      errorMessage: 'Column mismatch on user_id — production pipeline affected',
      environment: 'prod',
    })

    await expect(page.locator('.pipeline-view')).toBeVisible({ timeout: 30_000 })

    // Prod + schema_mismatch should result in human review (medium risk)
    const outcomeBadge = page.locator('.pipeline-outcome .badge')
    await expect(outcomeBadge).toHaveText('APPROVAL_REQUIRED')
  })
})
