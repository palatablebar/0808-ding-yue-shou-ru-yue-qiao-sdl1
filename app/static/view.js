import {element, pretty} from './client.js';

const labels = {
  READY:'通过', MISMATCH:'差异待复核', PENDING:'待复核', APPROVED:'已签发', HELD:'已暂缓',
  ELIGIBLE:'可签发', SIGNED:'已签发',
};
const holdLabels = {
  UNATTRIBUTABLE_BAD_ROW:'坏行无法归组，整批暂缓',
  CROSS_GROUP_CONFLICT:'记录键跨组冲突',
  ISOLATED_BAD_ROW:'组内含隔离坏行',
  CASE_NOT_READY:'组内对账未通过',
};
const headers = ['业务分组', '输入行', '计算值', '参考值', '判定', '签发状态'];

export function badge(status) {
  return element('span', labels[status] || status, {class:'badge', 'data-result':status, title: status});
}

function releaseMap(report) {
  const plan = report.balance?.release;
  return new Map((plan?.cases || []).map(item => [item.case, item]));
}

export function snapshot(report, selected, stage) {
  const stats = report.intake;
  document.querySelector('[data-metric="input"]').textContent = stats.input;
  document.querySelector('[data-metric="accepted"]').textContent = stats.accepted;
  document.querySelector('[data-metric="isolated"]').textContent = stats.rejected + (stats.ungroupable?.length || 0);
  document.querySelector('[data-metric="cases"]').textContent = report.cases?.length ?? '—';
  const table = document.querySelector('#rows');
  table.replaceChildren();
  const head = element('tr');
  const body = table.createTBody();
  const releases = releaseMap(report);
  if (stage === 'intake') {
    head.append(...['源行', '记录键', '业务组', '原因码'].map(title => element('th', title, {scope:'col'})));
    for (const item of stats.isolation) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    for (const item of stats.ungroupable || []) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case || '—',`${item.reason}（无法归组）`].map(value=>element('td',value)));
    }
    for (const item of stats.cross_conflicts || []) {
      const tr = body.insertRow();
      tr.append(...[item.line,item.record,item.case,item.reason].map(value=>element('td',value)));
    }
    if (!stats.isolation.length && !(stats.ungroupable||[]).length && !(stats.cross_conflicts||[]).length) {
      body.insertRow().insertCell().textContent = '当前文件没有隔离行';
    }
  } else {
    head.append(...headers.map(title => element('th', title, {scope:'col'})));
    for (const row of report.cases || []) {
      const tr = body.insertRow();
      const button = element('button',row.case,{type:'button','data-case':row.case,'aria-pressed':String(row.case===selected)});
      tr.insertCell().append(button);
      [row.records.length, row.measure?.value ?? '—', row.measure?.expected ?? '—'].forEach(value=>tr.insertCell().textContent=value);
      tr.insertCell().append(badge(row.status));
      const plan = releases.get(row.case);
      const stateCell = tr.insertCell();
      if (plan) {
        stateCell.append(badge(plan.state));
        if (plan.hold_text?.length) {
          stateCell.append(element('span', plan.hold_text.join('；'), {class:'hold-reason', title: plan.hold_reasons.join(',')}));
        }
        if (plan.review?.note) {
          stateCell.append(element('span', `意见：${plan.review.note}`, {class:'hold-reason'}));
        }
      }
    }
  }
  table.createTHead().append(head);
  const picked = report.cases?.find(row=>row.case===selected);
  const pickedPlan = releases.get(selected);
  document.querySelector('#detail-title').textContent = picked ? `分组 ${picked.case}` : '采信摘要';
  const shown = picked ? (pickedPlan?.hold_reasons?.length
      ? {暂缓原因: Object.fromEntries(pickedPlan.hold_reasons.map(code => [code, holdLabels[code] || code])),
         ...(picked.measure?.evidence ?? picked.prep?.details ?? {}), 判定: picked.status}
      : (picked.measure?.evidence ?? picked.prep?.details ?? {原因:picked.status}))
    : stats.reasons;
  document.querySelector('#detail').textContent = pretty(shown);
  const plan = report.balance?.release;
  document.querySelector('#counts').textContent = plan
    ? `可签 ${plan.eligible} 组 · 已签 ${plan.signed} 组 · 暂缓 ${plan.held} 组${plan.batch_hold ? ' · 整批暂缓' : ''}`
    : `采信 ${stats.accepted} 行 · 隔离 ${stats.rejected} 行`;
}

export function history(items, active) {
  const target = document.querySelector('#history');
  target.replaceChildren();
  for (const run of items) {
    const button = element('button', run.id.slice(0,10), {'data-run':run.id,'aria-pressed':String(run.id===active),type:'button'});
    const item = element('li');
    item.append(button, badge(run.status));
    target.append(item);
  }
  if (!items.length) target.append(element('li','尚无执行批次'));
}
