'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const status = $('status');
  let csrf = null, confirmation = null, busy = false, controller = null, generation = 0;
  const labels = {
    reference:'Journey / directive reference',current_stage:'Current stage',original_classification:'Original classification',
    owning_department_reference:'Owning department reference',priority:'Priority',technical_status:'Technical status',
    dependency_state:'Dependency state',risk_state:'Risk state',approval_state:'Technical approval state',
    assigned_owner_reference:'Assigned owner reference',next_required_action:'Next required action',
    outcome_evidence_reference:'Outcome-evidence reference',revision:'Revision',last_authorized_update:'Last authorized update',
    history_references:'Append-only journey-history references'
  };
  function text(tag, value) { const node = document.createElement(tag); node.textContent = value; return node; }
  function announce(message, kind='', focus=false) {
    status.textContent=message; status.className='status '+kind;
    if(focus) status.focus();
  }
  function clearData() { $('records').replaceChildren(); $('details').replaceChildren(); $('counts').replaceChildren();document.querySelectorAll('.queue-items').forEach(node=>node.replaceChildren());document.querySelectorAll('.stages small').forEach(node=>node.textContent='Unavailable'); }
  function setBusy(value) { busy=value; $('refresh').disabled=value; $('prepare').disabled=value || !$('action').value; $('confirm').disabled=value || !$('understood').checked; }
  const errors = {
    400:'Technical failure: invalid request. No action was accepted.',
    403:'Denied: the local session, identity, or CSRF verification failed.',
    408:'Technical timeout: an action may have an uncertain result. Reload the authorized view; do not submit a new action.',
    409:'Blocked: stale revision, unresolved dependency, or a confirmation already used or expired.',
    429:'Blocked: the local request limit was reached.',503:'Service unavailable: no protected data is displayed.'
  };
  async function api(path, body) {
    const options={method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal};
    if(body) { options.headers={'Content-Type':'application/json; charset=utf-8'};options.body=JSON.stringify(body); }
    const response=await fetch('/command-center/api/'+path,options);
    if(!response.ok) { const error=new Error(errors[response.status] || 'Technical failure: the local service rejected the request.'); throw error; }
    if(!(response.headers.get('Content-Type')||'').startsWith('application/json')) throw new Error('Technical failure: unexpected response format.');
    const value=await response.json();
    if(!value || value.schema_version!==1 || value.state!=='inactive' || value.operational_authorized!==false) throw new Error('Technical failure: malformed service response.');
    return value;
  }
  function appendFields(dl, value) {
    for(const [key,label] of Object.entries(labels)) {
      const item=value[key];
      let display='Unresolved — not supplied by the authorized projection';
      if(typeof item==='string' || (typeof item==='number' && Number.isSafeInteger(item))) display=String(item);
      else if(Array.isArray(item) && item.every(x=>typeof x==='string')) display=item.length?item.join(', '):'No references supplied';
      dl.append(text('dt',label),text('dd',display));
    }
  }
  function render(value) {
    if(!Array.isArray(value.stages) || value.stages.join(',')!=='information,intelligence,decision,assignment,execution,measurement' ||
       !Array.isArray(value.items) || !Array.isArray(value.actions) || typeof value.csrf_token!=='string' || value.connectors_disabled!==7) throw new Error('Technical failure: malformed overview.');
    csrf=value.csrf_token;
    for(const [key,label] of Object.entries({information:'Information queue',intelligence:'Intelligence queue',decision:'Decision queue',assignment:'Assignment queue',execution:'Execution queue',measurement:'Measurement queue',blocked:'Blocked items'})) {
      const queue=value.queues?.find(queue=>queue.stage===key);
      const count=queue ? (key==='blocked'?null:queue.count) : (key==='blocked'?value.blocked_count:null);
      const card=text('div',label);card.className='count';card.append(text('strong',Number.isSafeInteger(count)?String(count):'Unresolved'));
      $('counts').append(card);
    }
    const ready=text('div','Readiness status');ready.className='count';ready.append(text('strong',value.readiness ? (value.readiness.synthetic_ready ? 'Synthetic ready (inactive)' : 'Not ready (inactive)') : 'Unresolved'));$('counts').append(ready);
    if(!Array.isArray(value.queues)||value.queues.length!==6||value.queues.map(q=>q.stage).join(',')!==value.stages.join(','))throw new Error('Technical failure: missing governed queues.');
    for(const queue of value.queues) {
      if(!Array.isArray(queue.items)||queue.count!==queue.items.length||!Number.isSafeInteger(queue.blocked_count))throw new Error('Technical failure: invalid queue counts.');
      const card=document.getElementById(queue.stage);card.querySelector('small').textContent=queue.count+' items · '+queue.blocked_count+' blocked';
      let list=card.querySelector('.queue-items');if(!list){list=document.createElement('div');list.className='queue-items';card.append(list);}list.replaceChildren();
      for(const item of queue.items)list.append(text('p',item.reference+' · '+item.technical_status+' · revision '+item.revision));
    }
    const governedItems=value.queues.flatMap(queue=>queue.items);
    for(const result of governedItems) {
      if(!result || !value.stages.includes(result.current_stage)) throw new Error('Technical failure: malformed governed projection.');
      const row=document.createElement('tr');
      for(const field of [result.reference || 'Authorized advisory view',result.original_classification || 'Unresolved',result.technical_status,result.revision ?? 'Unresolved',result.current_stage.toUpperCase()]) row.append(text('td',String(field)));
      $('records').append(row);
      const detail=document.createElement('details');detail.append(text('summary',result.reference || 'Authorized view'));
      const dl=document.createElement('dl');appendFields(dl,result);detail.append(dl);
      if(Array.isArray(result.events)) {
        const history=document.createElement('table');history.append(text('caption','Append-only authorized journey history'));
        const head=document.createElement('thead'),headRow=document.createElement('tr');
        for(const label of ['Sequence','Event reference','Disposition']) { const th=text('th',label);th.scope='col';headRow.append(th); }
        head.append(headRow);history.append(head);
        const rows=document.createElement('tbody');
        for(const event of result.events) { const line=document.createElement('tr');for(const field of [event.sequence,event.event_reference,event.disposition]) line.append(text('td',String(field)));rows.append(line); }
        history.append(rows);detail.append(history);
      }
      $('details').append(detail);
    }
    $('action').replaceChildren(new Option('No action selected — read only',''));
    for(const action of value.actions){const option=new Option(action.requested_action+(action.eligibility?.eligible?'':' — unavailable'),action.action_reference);option.disabled=action.eligibility?.eligible!==true;$('action').add(option);}
    announce(governedItems.length?'Authorized views loaded. Queue counts are server-calculated; unknown item fields remain explicitly unresolved.':'Empty: no authorized reference views are available. All six governed queues are empty.');
  }
  async function run(work) {
    if(busy) return;
    const sequence=++generation;controller=new AbortController();setBusy(true);
    const deadline=setTimeout(()=>controller.abort(),5000);
    try { await work(sequence); }
    catch(error) { if(sequence===generation) {clearData();$('action-error').textContent=error.name==='AbortError'?'The local request timed out. Reload before retrying.':error.message;announce(error.name==='AbortError'?'Technical timeout: reload the authorized view before retrying.':error.message,'error',true);} }
    finally { clearTimeout(deadline);if(sequence===generation)setBusy(false); }
  }
  function load() { return run(async sequence=>{clearData();announce('Loading authorized server projections…');const value=await api('overview');if(sequence===generation)render(value);}); }
  $('refresh').addEventListener('click',load);
  $('clear').addEventListener('click',()=>{
    generation+=1;if(controller)controller.abort();clearData();csrf=null;confirmation=null;$('action').value='';setBusy(false);
    if($('confirmation').open)$('confirmation').close();announce('View cleared. Reload before preparing any synthetic action.', '',true);
  });
  $('action').addEventListener('change',()=>setBusy(busy));
  $('action-form').addEventListener('submit',event=>{event.preventDefault();if(!csrf||!$('action').value)return;run(async sequence=>{
    announce('Checking route, policy, and confirmation prerequisites…');
    const value=await api('prepare',{action_reference:$('action').value,csrf_token:csrf});
    if(sequence!==generation)return;
    if(value.eligibility?.eligible!==true)throw new Error('Blocked: missing governed eligibility.');
    if(typeof value.request_reference!=='string'||typeof value.idempotency_key!=='string'||!Number.isInteger(value.expected_revision)||typeof value.csrf_token!=='string'||!Array.isArray(value.dependencies))throw new Error('Technical failure: invalid confirmation.');
    confirmation=value;$('confirmation-details').replaceChildren();
    for(const [label,item] of [['Requested action',value.requested_action],['Opaque target',value.target_reference],['Expected revision',value.expected_revision],['Owning department',value.owning_department_reference || 'Unresolved'],['Known dependencies','Resolved by current server-calculated eligibility; no protected dependency references exposed'],['Technical consequences',value.technical_consequences],['Boundary',value.warning]]) $('confirmation-details').append(text('dt',label),text('dd',String(item)));
    $('understood').checked=false;$('confirm').disabled=true;$('confirmation').showModal();$('understood').focus();announce('Confirmation required. No action has been submitted.');
  });});
  $('understood').addEventListener('change',()=>{$('confirm').disabled=busy||!$('understood').checked;});
  $('cancel').addEventListener('click',()=>{$('confirmation').close();confirmation=null;$('prepare').focus();});
  $('confirmation').addEventListener('cancel',()=>{confirmation=null;});
  $('confirmation-form').addEventListener('submit',event=>{
    event.preventDefault();if(busy||!confirmation||!$('understood').checked)return;
    const value=confirmation;confirmation=null;$('confirmation').close();
    run(async()=>{announce('Submitting confirmed synthetic action…');await api('confirm',{request_reference:value.request_reference,idempotency_key:value.idempotency_key,expected_revision:value.expected_revision,csrf_token:value.csrf_token,confirmed:true});clearData();announce('Successful synthetic action. It remains inactive; no organizational approval or external delivery occurred.','success',true);});
  });
  window.addEventListener('pagehide',()=>{generation+=1;if(controller)controller.abort();csrf=null;confirmation=null;clearData();});
  load();
})();
