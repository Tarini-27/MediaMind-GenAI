'use strict';
let chatRun=localStorage.getItem('gather-chat-id')||'',chatBusy=false,chatApproval=null,activeAnswer=null;
function answerHtml(answer){return `<h3>${esc(answer.title||'From your saves')}</h3>${(answer.claims||[]).map(c=>`<div class="answer-claim"><p>${esc(c.text)}</p><div class="answer-citations">${(c.citations||[]).map(p=>`<button class="citation-chip" data-cite-source="${validId(p.source_id)}" data-cite-time="${p.seconds??''}">${icon(p.media_url?'play':'bookmark')}${esc(p.title)}${p.timestamp?' · ≈'+esc(p.timestamp):''}</button>`).join('')}</div><small>${c.verification==='exact_source_quote'?'Source excerpt':c.verification==='model_checked_not_guaranteed'?'AI checked against cited evidence · please verify':'Citation checked · support needs review'}</small></div>`).join('')}${(answer.unknowns||[]).length?`<div class="notice"><strong>Limits & missing details</strong><ul>${answer.unknowns.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}`;}
window.refreshAssistant=async function(){
 const eligible=state.jobs.filter(j=>j.status==='approved'&&noteOf(j)?.evidence?.length);
 const older=state.jobs.filter(j=>j.status==='approved'&&!noteOf(j)?.evidence?.length);
 const coverage=$('#chat-coverage');coverage.hidden=!older.length;
 coverage.innerHTML=`${eligible.length} saves currently have reviewed evidence for cited answers. ${older.length} older ${older.length===1?'save has':'saves have'} no retained evidence. Open each and choose <strong>Reanalyse original</strong>, then review and approve the new notes. This needs your model connection. <button class="text-button" data-open="${validId(older[0]?.id||'')}">Open an older save ↗</button>`;

 const current=$('#chat-collection').value;$('#chat-collection').innerHTML='<option value="">All collections</option>'+state.collections.map(c=>`<option value="${validId(c.id)}">${esc(c.name)}</option>`).join('');$('#chat-collection').value=current;
 try{const m=await api('/api/memory');$('#memory-status').textContent=m.preferences.answer_style?'Saved: '+m.preferences.answer_style+' answers':'No preferences saved.';}catch{}
};
function approvalHtml(data){chatApproval=data;const box=$('#chat-approval');box.hidden=false;box.innerHTML=`<div class="eyebrow">YOUR APPROVAL NEEDED</div><h3>Save this exact note?</h3><p>This writes to your local notebook. Check the answer and its sources above.</p><label>Note title<input id="approval-title" value="${esc(data.note.title)}" maxlength="160"></label><div class="dialog-actions"><button class="button secondary" id="chat-reject">Reject</button><button class="button secondary" id="chat-edit">Update title & review again</button><button class="button primary" id="chat-approve">Approve & save</button></div>`;}
async function sendChat(resume=null){
 if(chatBusy)return;const question=$('#chat-question').value.trim();if(!resume&&!question)return;
 chatBusy=true;$('#chat-send').disabled=true;$('#agent-progress').hidden=false;$('#agent-progress').textContent=resume?'Resuming your review…':'Planning the search…';
 const log=$('#chat-messages');$('.chat-intro',log)?.remove();
 if(!resume){const user=document.createElement('div');user.className='chat-user';user.textContent=question;log.append(user);activeAnswer=document.createElement('article');activeAnswer.className='chat-answer';log.append(activeAnswer);$('#chat-question').value='';}
 const provider=$('#chat-provider').value;
 const after=$('#chat-after').value,before=$('#chat-before').value;
 const body={run_id:chatRun||undefined,question,resume,provider,model:provider==='gemini'?state.model:$('#router-model').value.trim(),api_key:provider==='gemini'?state.key:$('#router-key').value.trim(),memory:$('#chat-memory').checked,semantic:$('#chat-semantic').checked,save_requested:$('#chat-save').checked,filters:{category:$('#chat-topic').value,collection_id:$('#chat-collection').value,after:after?Date.parse(after+'T00:00:00')/1000:0,before:before?Date.parse(before+'T23:59:59')/1000:0}};
 try{
  const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-App-Request':'1'},body:JSON.stringify(body)});
  if(!response.ok){const e=await response.json();throw Error(e.error||'Request failed.');}
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  while(true){const {value,done}=await reader.read();pending+=decoder.decode(value||new Uint8Array(),{stream:!done});let cut;
   while((cut=pending.indexOf('\n\n'))>=0){const frame=pending.slice(0,cut);pending=pending.slice(cut+2);const line=frame.split('\n').find(x=>x.startsWith('data: '));if(!line)continue;const event=JSON.parse(line.slice(6));
    if(event.run_id){chatRun=event.run_id;localStorage.setItem('gather-chat-id',chatRun);}
    if(event.type==='stage')$('#agent-progress').textContent=({supervisor:'Planning your search',retriever:'Finding source evidence',writer:'Writing from your sources',verifier:'Checking source support',replan:'Revising unsupported details',finish:'Answer ready',review:'Waiting for your approval',publish:'Saving your approved note'})[event.stage]||event.stage;
    if(event.type==='approval')approvalHtml(event.data);
    if(event.type==='error')throw Error(event.message);
    if(event.type==='result'){
     if(!activeAnswer){activeAnswer=document.createElement('article');activeAnswer.className='chat-answer';log.append(activeAnswer);}
     activeAnswer.innerHTML=answerHtml(event.answer)+(event.warnings?.length?`<p class="search-warning">${event.warnings.map(esc).join(' ')}</p>`:'')+`<details><summary>How this answer was made</summary><ol>${(event.plan||[]).map(p=>`<li>${esc(p.step)} · ${esc(p.agent)} · ${esc(p.status)}</li>`).join('')}</ol><p>${event.metrics?.tool_calls||0} tool calls · ${event.metrics?.model_calls||0} model calls${event.metrics?.cost_usd!=null?' · $'+event.metrics.cost_usd.toFixed(5):' · cost unavailable'}</p></details>`;
     if(!event.pending){chatApproval=null;$('#chat-approval').hidden=true;}
     if(event.published?.published){toast('Approved note saved to your notebook.');await loadNotebook();}
    }
   }if(done)break;
  }
 }catch(e){toast(e.message,true);if(activeAnswer&&!activeAnswer.innerHTML)activeAnswer.textContent=e.message;}
 finally{chatBusy=false;$('#chat-send').disabled=false;$('#agent-progress').hidden=true;}
}
async function loadNotebook(){try{const data=await api('/api/notebook');$('#notebook-list').innerHTML=data.notes.length?data.notes.map(n=>`<details class="notebook-note"><summary>${esc(n.note.title)}</summary>${answerHtml(n.note)}<button class="text-button" data-remove-note="${validId(n.id)}">Delete note</button></details>`).join(''):'<p>No approved notebook notes yet.</p>';}catch(e){toast(e.message,true);}}
$('#chat-form').addEventListener('submit',e=>{e.preventDefault();sendChat();});
$('#new-chat').addEventListener('click',async()=>{if(chatBusy)return;if(chatRun){try{await api('/api/chat/delete',{run_id:chatRun});}catch(e){toast(e.message,true);return;}}chatRun='';chatApproval=null;activeAnswer=null;localStorage.removeItem('gather-chat-id');$('#chat-messages').innerHTML='<div class="chat-intro"><h2>A fresh start.</h2><p>Ask about your saved videos.</p></div>';$('#chat-approval').hidden=true;});
$('#notebook-refresh').addEventListener('click',loadNotebook);
$('#memory-save').addEventListener('click',async()=>{try{await api('/api/memory',{key:'answer_style',value:$('#memory-style').value,consent:$('#memory-consent').checked});await window.refreshAssistant();toast('Preference saved for 30 days.');}catch(e){toast(e.message,true);}});
$('#memory-delete').addEventListener('click',async()=>{try{await api('/api/memory',{action:'delete'});$('#chat-memory').checked=false;await window.refreshAssistant();toast('Preferences deleted.');}catch(e){toast(e.message,true);}});
document.addEventListener('click',async e=>{
 const cite=e.target.closest('[data-cite-source]');if(cite){await openPost(cite.dataset.citeSource);const video=$('#source-video'),t=Number(cite.dataset.citeTime);if(video&&cite.dataset.citeTime!==''){const seek=()=>{if(Number.isFinite(video.duration)&&t>video.duration){toast('Timestamp exceeds this clip; verify the source.',true);return;}video.currentTime=t;video.play().catch(()=>{});};if(video.readyState>=1)seek();else video.addEventListener('loadedmetadata',seek,{once:true});}return;}
 if(e.target.closest('#chat-approve')&&chatApproval)sendChat({action:'approve',approval_hash:chatApproval.approval_hash});
 if(e.target.closest('#chat-reject'))sendChat({action:'reject'});
 if(e.target.closest('#chat-edit'))sendChat({action:'edit',title:$('#approval-title').value});
 const del=e.target.closest('[data-remove-note]');if(del){try{await api('/api/notebook/delete',{id:del.dataset.removeNote});await loadNotebook();}catch(err){toast(err.message,true);}}
});
if(chatRun)api('/api/chat/'+chatRun).then(result=>{if(result.answer?.title){$('.chat-intro')?.remove();activeAnswer=document.createElement('article');activeAnswer.className='chat-answer';activeAnswer.innerHTML=answerHtml(result.answer);$('#chat-messages').append(activeAnswer);}if(result.approval)approvalHtml(result.approval);}).catch(()=>{chatRun='';localStorage.removeItem('gather-chat-id');});
