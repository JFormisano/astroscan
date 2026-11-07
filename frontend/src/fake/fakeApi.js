// DEV ONLY (Person C). Stands in for Person A's measurement routes when VITE_FAKE_API=1.
// Upload a photo whose file name contains "fail" to see the failed-solve screen.
import { fakeFailed, fakeSolved } from './fakeResult.js'

const STEPS = ['queued', 'detecting', 'solving', 'matching', 'scoring']
const STEP_MS = 1200
const started = {}

export async function createMeasurement(file) {
  await new Promise((r) => setTimeout(r, 600))
  const jobId = `${/fail/i.test(file.name) ? 'fake-failed' : 'fake'}-${Date.now()}`
  started[jobId] = Date.now()
  return { job_id: jobId }
}

export async function getMeasurement(jobId) {
  if (!jobId.startsWith('fake')) {
    const err = new Error('Not found')
    err.status = 404
    throw err
  }
  // After a refresh the start time is gone; treat the job as finished.
  const elapsed = Date.now() - (started[jobId] ?? 0)
  const i = Math.floor(elapsed / STEP_MS)
  if (i < STEPS.length) return { job_id: jobId, status: 'pending', step: STEPS[i] }
  if (jobId.startsWith('fake-failed')) return { job_id: jobId, status: 'failed', result: fakeFailed }
  return { job_id: jobId, status: 'solved', result: fakeSolved }
}
