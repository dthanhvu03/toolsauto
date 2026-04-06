/**
 * Platform Config — Simulation Engine (Pure Domain Logic)
 *
 * This module contains the job simulation engine that predicts execution
 * outcomes based on runtime configuration and selector health data.
 *
 * ALL functions here are PURE — no DOM access, no side effects.
 * They can be independently unit-tested.
 *
 * Extracted from platform_config.html (Phase P0 Refactoring)
 */

// ─── Config: Step ↔ Selector Mapping ──────────────────────────
const STEP_SELECTOR_MAP = {
  feed_browse: ['feed_container', 'post_container'],
  pre_scan: ['overlay_close', 'banner_dismiss', 'popup_close'],
  type_comment: ['comment_box', 'comment_submit'],
  upload_media: ['media_input', 'upload_button'],
  publish_post: ['publish_button', 'confirm_post']
};

// ─── Selector Helpers ─────────────────────────────────────────

function normalizeSelectorItems(selectorData) {
  return Array.isArray(selectorData?.items) ? selectorData.items : [];
}

function getSelectorByKey(selectorItems, key) {
  return selectorItems.find(item => item.key === key);
}

function getMappedSelectorsForStep(stepName) {
  return STEP_SELECTOR_MAP[stepName] || [];
}

// ─── Step Classification ──────────────────────────────────────

function classifyStepFromSelectors(mappedItems, stepName) {
  const selectorKeys = getMappedSelectorsForStep(stepName);

  if (!selectorKeys.length) {
    return { execution_status: 'UNKNOWN', reason: 'Custom step.', action: '', confidence: 'LOW' };
  }
  if (!mappedItems.length || mappedItems.some(i => !i)) {
    return { execution_status: 'UNKNOWN', reason: `Thiếu telemetry: ${selectorKeys.join(', ')}.`, action: 'Chờ job.', confidence: 'LOW' };
  }

  const hasCriticalHigh = mappedItems.some(s => s.severity === 'critical' && String(s.confidence).toLowerCase() === 'high');
  if (hasCriticalHigh) {
    return { execution_status: 'FAIL', reason: `Selector [${mappedItems.find(s => s.severity === 'critical').key}] critical.`, action: 'Cập nhật selector.', confidence: 'HIGH' };
  }

  const hasCriticalLow = mappedItems.some(s => s.severity === 'critical');
  if (hasCriticalLow) {
    return { execution_status: 'RISK', reason: `Selector [${mappedItems.find(s => s.severity === 'critical').key}] critical (Low Conf).`, action: 'Quan sát.', confidence: 'MEDIUM' };
  }

  const hasWarning = mappedItems.some(s => s.severity === 'warning');
  if (hasWarning) {
    return { execution_status: 'RISK', reason: `Selector [${mappedItems.find(s => s.severity === 'warning').key}] warning.`, action: 'Kiểm tra.', confidence: 'MEDIUM' };
  }

  return { execution_status: 'OK', reason: 'Healthy.', action: '', confidence: 'HIGH' };
}

// ─── Shared Selector Risk Analysis ────────────────────────────

function buildSharedSelectorRisks(results, selectorItems) {
  const usage = {};
  results.forEach(step => (step.selector_keys || []).forEach(key => {
    if (!usage[key]) usage[key] = [];
    usage[key].push(step.step);
  }));

  const severityOrder = { critical: 0, warning: 1, unknown: 2 };

  return Object.entries(usage)
    .filter(([_, steps]) => steps.length >= 2)
    .map(([selectorKey, steps]) => ({
      selector_key: selectorKey,
      steps,
      severity: getSelectorByKey(selectorItems, selectorKey)?.severity || 'unknown'
    }))
    .sort((a, b) => (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99));
}

// ─── CTA Status Evaluation ────────────────────────────────────

function evaluateCTAStatus(runtimeData) {
  const cta = runtimeData?.cta_pool || {};
  if (Number(cta.total || 0) > 0 && Number(cta.effective || 0) === 0) {
    return { status: 'RISK', message: 'CTA không match.', action: 'Chỉnh rule.' };
  }
  if (cta.is_fallback) {
    return { status: 'INFO', message: 'Fallback tĩnh.', action: 'Thêm template.' };
  }
  return { status: 'OK', message: 'Bình thường.', action: '' };
}

// ─── Core Simulation Engine ───────────────────────────────────

function simulateJob(runtimeData, selectorData, options = {}) {
  const mode = options.mode || 'realistic';
  const selectorItems = normalizeSelectorItems(selectorData);
  const runtimeSteps = Array.isArray(runtimeData?.step_resolution)
    ? [...runtimeData.step_resolution].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
    : [];

  const result = {
    mode,
    overall: 'UNKNOWN',
    risk_level: 'low',
    confidence: 'LOW',
    summary: 'Simulation completed',
    stopped_early: false,
    first_failure: null,
    shared_risks: [],
    cta_status: evaluateCTAStatus(runtimeData),
    steps: []
  };

  if (!runtimeData || !runtimeSteps.length) return result;

  let shouldStop = false;

  for (const step of runtimeSteps) {
    const stepName = step.step;

    // SKIP steps are never executed
    if (step.status === 'SKIP') {
      result.steps.push({
        step: stepName, order: step.order || 0,
        execution_status: 'SKIPPED', runtime_status: 'SKIP',
        reason: 'Skip', selector_keys: [], action: '', confidence: 'LOW'
      });
      continue;
    }

    // Realistic mode: stop after first failure
    if (shouldStop && mode === 'realistic') {
      result.steps.push({
        step: stepName, order: step.order || 0,
        execution_status: 'NOT_EXECUTED', runtime_status: 'RUN',
        reason: 'Bị dừng do FAIL.', selector_keys: [], action: '', confidence: 'LOW'
      });
      continue;
    }

    // Classify this step based on selector health
    const selectorKeys = getMappedSelectorsForStep(stepName);
    const classified = classifyStepFromSelectors(
      selectorKeys.map(k => getSelectorByKey(selectorItems, k)),
      stepName
    );

    result.steps.push({
      step: stepName, order: step.order || 0,
      execution_status: classified.execution_status, runtime_status: 'RUN',
      reason: classified.reason, selector_keys: selectorKeys,
      action: classified.action, confidence: classified.confidence
    });

    // Track first failure for early-exit
    if (classified.execution_status === 'FAIL' && !result.first_failure) {
      result.first_failure = {
        step: stepName, selector_key: selectorKeys[0],
        reason: classified.reason, action: classified.action
      };
      if (mode === 'realistic') {
        shouldStop = true;
        result.stopped_early = true;
      }
    }
  }

  // ─── Aggregate Results ───
  const evaluatedSteps = result.steps.filter(
    r => r.runtime_status === 'RUN' && r.execution_status !== 'NOT_EXECUTED'
  );
  const statuses = evaluatedSteps.map(r => r.execution_status);

  result.overall = statuses.includes('FAIL') ? 'FAIL'
    : (statuses.includes('RISK') ? 'RISK'
      : (statuses.includes('OK') ? 'SUCCESS' : 'UNKNOWN'));

  result.risk_level = result.overall === 'FAIL' ? 'high'
    : (result.overall === 'RISK' ? 'medium' : 'low');

  // Confidence: based on coverage of known (non-UNKNOWN) steps
  if (evaluatedSteps.length > 0) {
    const knownSteps = evaluatedSteps.filter(r => r.execution_status !== 'UNKNOWN').length;
    const coverage = knownSteps / evaluatedSteps.length;
    result.confidence = coverage >= 0.8 ? 'HIGH' : (coverage >= 0.5 ? 'MEDIUM' : 'LOW');
  }

  result.summary = result.first_failure
    ? `Job có thể sập tại [${result.first_failure.step}]`
    : (result.overall === 'RISK' ? 'Rủi ro chập chờn.' : 'Ổn định.');

  result.shared_risks = buildSharedSelectorRisks(result.steps, selectorItems);

  return result;
}
