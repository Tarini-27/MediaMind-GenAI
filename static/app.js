'use strict';
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon=(name,cls='')=>`<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const validId=id=>/^[a-z0-9]{1,40}$/.test(id)?id:'';
const labels={food:'Food',travel:'Travel',fitness:'Workouts',learning:'Learning',lifestyle:'Lifestyle',other:'Other'};
const symbols={food:'🍋',travel:'🌊',fitness:'✳',learning:'📖',lifestyle:'☀',other:'✧'};
const statusNames={saved:'Needs preparation',queued:'Preparing',processing:'Preparing',review:'Notes available · needs review',approved:'Search ready',failed:'Preparation needs attention'};
const state={feed:[],feedTopic:'',feedLimit:12,feedSignature:'',pendingFeedSave:null,feedSaving:false,jobs:[],collections:[],view:'feed',tab:'posts',topic:'all',collection:'',status:'all',key:'',serverKey:false,model:'gemini-3.5-flash-lite',input:'media',file:null,mime:'',selected:null,approval:null,assignment:null,search:null,searchSerial:0};
let toastTimer,pollTimer;
const posterReady=new Set(),posterPending=new Set();
async function api(path,body){const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-App-Request':'1'},body:JSON.stringify(body)};const res=await fetch(path,options);let data;try{data=await res.json();}catch{throw Error('Unexpected response from the local app.');}if(!res.ok)throw Error(data.error||'Request failed.');return data;}
function toast(text,error=false){const n=$('#toast');n.textContent=text;n.hidden=false;n.classList.toggle('error',error);clearTimeout(toastTimer);toastTimer=setTimeout(()=>n.hidden=true,5500);}
function failure(text){$('#import-feedback').hidden=false;$('#import-feedback').textContent=text;toast(text,true);}
function noteOf(j){return j.note||j.recipe;}
function topicOf(j){return j.category||noteOf(j)?.category||'other';}
function activeCollection(){return state.collections.find(c=>c.id===state.collection);}
function changeView(which){
 if(['feed','import','activity','assistant','course'].includes(which))state.view=which;else{state.view='library';if(which==='collections'){state.tab='collections';state.collection='';clearSearch(false);}else if(which==='saved'){state.tab='posts';state.collection='';clearSearch(false);}}
 $$('.view').forEach(n=>n.hidden=n.id!==`view-${state.view}`);
 $$('.nav-item[data-nav]').forEach(n=>n.classList.toggle('active',n.dataset.nav===(state.view==='library'?(state.tab==='collections'?'collections':which==='search'?'search':'saved'):state.view)));
 $('#breadcrumb').textContent=({feed:'Feed',import:'Add a video',activity:'Processing details',assistant:'Ask your saves',course:'Course tools'})[state.view]||'Saved';
 if(state.view==='feed')renderFeed();if(state.view==='library')renderLibrary();if(state.view==='activity')renderActivity();if(state.view==='assistant'&&window.refreshAssistant)window.refreshAssistant();
 window.scrollTo({top:0,behavior:'instant'});if(which==='search')$('#search-input').focus();
}
async function refresh(){
 const [jobs,collections,feed]=await Promise.all([api('/api/jobs'),api('/api/collections'),api('/api/feed')]);state.jobs=jobs.jobs;state.collections=collections.collections;state.feed=feed.items;
 $('#nav-count').textContent=state.jobs.length;$('#saved-count').textContent=state.jobs.length;$('#collection-count').textContent=state.collections.length;
 $('#draft-count').textContent=state.jobs.filter(j=>['review','queued','processing'].includes(j.status)).length;
 const reviewed=state.jobs.filter(j=>j.search_ready).length;
 $('#coverage-text').textContent=`${reviewed} of ${state.jobs.length} saved videos are ready for search`;
 const old=$('#source-collection').value;$('#source-collection').innerHTML='<option value="">All saves only</option>'+state.collections.map(c=>`<option value="${validId(c.id)}">${esc(c.name)}</option>`).join('');if(state.collections.some(c=>c.id===old))$('#source-collection').value=old;
 if(state.view==='feed')renderFeed();if(state.view==='library')renderLibrary();if(state.view==='activity')renderActivity();if(state.view==='assistant'&&window.refreshAssistant)window.refreshAssistant();
 clearTimeout(pollTimer);if(state.jobs.some(j=>['queued','processing'].includes(j.status)))pollTimer=setTimeout(()=>refresh().catch(e=>toast(e.message,true)),2000);
}
function sourceArt(j,compact=false){
 const t=topicOf(j);const r=noteOf(j);const id=validId(j.id);
 if(j.has_media&&j.mime.startsWith('image/'))return `<img src="/media/${id}" alt="${esc(r?.title||j.filename)}" loading="lazy">`;
 if(j.has_media&&j.mime.startsWith('video/'))return j.has_thumbnail||posterReady.has(id)?`<img src="/poster/${id}" alt="${esc(r?.title||j.filename)}" loading="lazy">`:`<video class="grid-video" data-video-id="${id}" muted playsinline preload="auto" src="/media/${id}#t=0.3" aria-hidden="true"></video>`;
 return `<div class="note-art ${esc(t)}"><span class="art-symbol">${symbols[t]||'✧'}</span><span class="art-line"></span><span class="art-caption">${esc(r?.title||j.filename)}</span></div>`;
}
function postCard(j){const r=noteOf(j),title=r?.title||j.filename;const type=j.mime.startsWith('video/')?'film':j.mime.startsWith('image/')?'grid':'bookmark';
 return `<article class="post-card"><button class="post-image" data-open="${validId(j.id)}" aria-label="Open ${esc(title)}">${sourceArt(j)}<span class="post-topic">${labels[topicOf(j)]||'Other'}</span><span class="post-type">${icon(type)}</span>${j.mode==='demo'?'<span class="demo-flag">DEMO · TEXT SOURCE</span>':''}<span class="post-collection">${icon('folder')}<span>${esc(j.collections?.[0]?.name||'All saves')}</span><span class="post-ai">${j.status==='approved'?'✧':j.status==='processing'?'◷':''}</span></span></button><div class="post-info"><button data-open="${validId(j.id)}"><h3>${esc(title)}</h3><p>${esc(j.mode==='demo'?'Synthetic example':statusNames[j.status]||j.stage)}</p></button><button class="save-icon" data-assign="${validId(j.id)}" aria-label="Organise ${esc(title)}">${icon('bookmark')}</button></div></article>`;
}
async function cachePoster(v){
 const id=v.dataset.videoId;if(!id||posterReady.has(id)||posterPending.has(id)||!v.videoWidth)return;
 posterPending.add(id);
 try{
  const canvas=document.createElement('canvas');canvas.width=Math.min(400,v.videoWidth);canvas.height=Math.round(canvas.width*v.videoHeight/v.videoWidth);canvas.getContext('2d').drawImage(v,0,0,canvas.width,canvas.height);
  const data=canvas.toDataURL('image/jpeg',0.72).split(',')[1];await api('/api/thumbnail',{id,data});posterReady.add(id);
  $$('.grid-video').filter(n=>n.dataset.videoId===id).forEach(n=>{const image=document.createElement('img');image.src='/poster/'+id;image.alt='Saved video preview';n.replaceWith(image);});
 }catch{ /* Original video remains the fallback; thumbnail generation never blocks a save. */ }
 finally{posterPending.delete(id);}
}
function decorateMedia(){ $$('.grid-video').forEach(v=>{v.addEventListener('loadedmetadata',()=>{if(v.duration>0.3)v.currentTime=0.3;},{once:true});v.addEventListener('seeked',()=>cachePoster(v),{once:true});if(v.readyState>=2)cachePoster(v);});}
function filteredJobs(){let jobs=state.jobs;if(state.collection){const ids=new Set(activeCollection()?.item_ids||[]);jobs=jobs.filter(j=>ids.has(j.id));}if(state.topic!=='all')jobs=jobs.filter(j=>topicOf(j)===state.topic);if(state.status!=='all')jobs=jobs.filter(j=>j.status===state.status);return jobs;}
function renderLibrary(){
 const collection=activeCollection();$('#library-heading').innerHTML=collection?esc(collection.name)+'<span class="heading-dot">.</span>':'Saved<span class="heading-dot">.</span>';
 $('#library-description').textContent=collection?'One collection. All the things you wanted to remember.':'The places, recipes, workouts and little things you want to come back to.';
 $('#tab-posts').classList.toggle('selected',state.tab==='posts');$('#tab-collections').classList.toggle('selected',state.tab==='collections');
 $('#collection-context').hidden=!collection;if(collection)$('#collection-context').innerHTML=`<button id="back-collections">← All collections</button><button data-delete-collection="${validId(collection.id)}">Delete collection</button>`;
 $('#topic-filters').hidden=state.tab==='collections';$('#posts-meta').hidden=state.tab==='collections';$('#post-grid').hidden=state.tab==='collections';$('#collection-grid').hidden=state.tab!=='collections';
 $$('#topic-filters button').forEach(b=>b.classList.toggle('active',b.dataset.topic===state.topic));
 if(state.tab==='collections'){
  $('#empty-state').hidden=true;renderCollections();return;
 }
 let jobs=filteredJobs();if(state.search){const ids=new Set(jobs.map(j=>j.id));jobs=state.search.results.map(x=>x.job).filter(j=>ids.has(j.id));}
 $('#visible-count').textContent=`${jobs.length} ${jobs.length===1?'save':'saves'}${state.search?' found':''}`;
 $('#post-grid').innerHTML=jobs.map(postCard).join('');
 $('#empty-state').hidden=state.jobs.length>0||!!state.search;
 if(!jobs.length&&state.jobs.length)$('#post-grid').innerHTML=`<div class="empty-filter">${state.search?.loading?'Searching your saves…':state.search?.error?'Search could not finish. Check the message above and retry.':state.search?'No saved videos match. Try another description or check that the relevant video is search ready.':'No saves in this view yet. Add a source or change your filters.'}</div>`;
 decorateMedia();
}
function renderCollections(){
 $('#collection-grid').innerHTML=state.collections.map(c=>{const jobs=c.item_ids.map(id=>state.jobs.find(j=>j.id===id)).filter(Boolean).slice(0,4);return `<button class="collection-card" data-collection="${validId(c.id)}"><div class="collection-cover ${jobs.length?'':'empty-cover'}">${jobs.length?Array.from({length:4},(_,i)=>`<div class="collection-cell">${jobs[i]?sourceArt(jobs[i],true):'<div class="note-art other"></div>'}</div>`).join(''):icon('folder')}</div><h3>${esc(c.name)}</h3><p>${c.count} ${c.count===1?'save':'saves'}</p></button>`;}).join('');decorateMedia();
}
function renderActivity(){
 const jobs=state.jobs.filter(j=>j.status!=='saved');$('#activity-empty').hidden=jobs.length>0;
 $('#activity-list').innerHTML=jobs.map(j=>`<article class="activity-row"><div class="activity-icon">${icon(j.mime.startsWith('video/')?'film':'bookmark')}</div><div class="activity-content"><h3>${esc(noteOf(j)?.title||j.filename)}</h3><p>${esc(j.stage)}${j.elapsed?' · '+j.elapsed.toFixed(1)+'s':''} · ${j.mode==='demo'?'Synthetic source':j.mode==='manual'?'Local notes parser':esc(j.model)}</p>${j.error?`<p class="inline-error">${esc(j.error)}</p>`:''}</div><div class="activity-actions"><span class="status-label ${esc(j.status)}">${['processing','queued'].includes(j.status)?'<span class="spinner"></span>':''}${statusNames[j.status]||j.status}</span><button class="button secondary" data-open="${validId(j.id)}">${j.status==='review'?'Review notes':'Open save'} ↗</button>${j.status==='failed'?`<button class="button secondary" data-analyse="${validId(j.id)}">Retry</button>`:''}</div></article>`).join('');
}
function clearSearch(render=true){state.search=null;state.searchSerial++;$('#search-input').value='';$('#search-summary').hidden=true;$('#search-button').disabled=false;$('#search-button').innerHTML=icon('spark')+'Find it';if(render)renderLibrary();}
async function runSearch(e){
 e?.preventDefault();const query=$('#search-input').value.trim();if(!query)return;
 state.tab='posts';state.search={results:[],loading:true};renderLibrary();const serial=++state.searchSerial;const b=$('#search-button');b.disabled=true;b.textContent='Finding…';$('#search-summary').hidden=false;$('#search-summary').innerHTML='<span class="spinner"></span> Looking through your saved videos…';
 try{const result=await api('/api/search',{query,category:state.topic,collection_id:state.collection,semantic:$('#semantic-toggle').checked,api_key:state.key,model:state.model});if(serial!==state.searchSerial)return;state.search=result;$('#search-summary').innerHTML=`<button class="clear-search" id="clear-search">Clear ×</button><strong>${esc(result.answer)}</strong><p>${esc(result.search_mode)} · ${result.elapsed_ms} ms${state.collection?' · this collection':''}</p>${result.warning?`<p class="search-warning">${esc(result.warning)}</p>`:''}<small>Search covers prepared saved videos. Items still preparing will appear after completion.</small>`;renderLibrary();}catch(e){if(serial!==state.searchSerial)return;state.search={results:[],error:true};$('#search-summary').innerHTML=`<button class="clear-search" id="clear-search">Clear ×</button><strong>Search could not finish.</strong><p>${esc(e.message)}</p>`;renderLibrary();}finally{if(serial===state.searchSerial){b.disabled=false;b.innerHTML=icon('spark')+'Find it';}}
}
async function demoLibrary(){try{await api('/api/demo-library',{});await refresh();state.tab='posts';state.collection='';changeView('saved');toast('Demo text sources added. Review a note before searching its contents.');}catch(e){toast(e.message,true);}}
function updateImport(){
 $('#media-fields').hidden=false;$('#notes-fields').hidden=true;$('#analysis-choice').hidden=true;$('#connection-help').hidden=true;
 $('#import-submit').innerHTML='Add to feed '+icon('plus');$('#import-explanation').textContent='Then use the bookmark to save it to a collection.';
}
function setFile(file){
 if(!file)return;if(file.size>15*1024*1024){failure('Choose a source of 15 MB or smaller.');return;}
 let mime=file.type;if(!mime){mime={mp4:'video/mp4',webm:'video/webm',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',webp:'image/webp'}[file.name.split('.').pop().toLowerCase()]||'';}
 if(!['image/jpeg','image/png','image/webp','video/mp4','video/webm'].includes(mime)){failure('Supported formats: MP4, WebM, PNG, JPG and WebP.');return;}
 state.file=file;state.mime=mime;$('#file-preview').hidden=false;$('#file-preview').textContent=`✓ ${file.name} · ${(file.size/1024/1024).toFixed(2)} MB · ready to save`;$('#import-feedback').hidden=true;
}
function file64(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(Error('Could not read the source file.'));r.readAsDataURL(file);});}
async function importSource(e){
 e.preventDefault();const b=$('#import-submit');$('#import-feedback').hidden=true;
 try{
  if(!state.file)throw Error('Choose a video or photo.');b.disabled=true;b.textContent='Adding…';
  await api('/api/feed/upload',{filename:$('#source-title').value.trim()||state.file.name,mime:state.mime,data:await file64(state.file)});
  state.file=null;$('#file-input').value='';$('#file-preview').hidden=true;$('#source-title').value='';state.feedTopic='';state.feedLimit=12;
  await refresh();changeView('feed');toast('Added to your feed. Use the bookmark to save it to a collection.');
 }catch(e){failure(e.message);}finally{b.disabled=false;updateImport();}
}
function pointsHtml(items){return `<ul class="points-list">${items.map(p=>`<li>${esc(p.text)}<small>${p.reviewer_edited?'Reviewer edited':esc((p.evidence_ids||[]).join(', '))}</small></li>`).join('')}</ul>`;}
function noteBody(n){return `<p class="note-summary">${esc(n.summary)}</p>${n.key_points?.length?`<div class="detail-section"><h3>Key takeaways</h3>${pointsHtml(n.key_points)}</div>`:''}${n.ingredients?.length?`<div class="detail-section"><h3>Ingredients</h3><ul class="ingredient-list">${n.ingredients.map(i=>`<li><div>${esc(i.name)}${i.reviewer_edited?' · edited':''}</div><span>${esc(i.quantity)} · ${esc((i.evidence_ids||[]).join(', '))}</span></li>`).join('')}</ul></div>`:''}${n.steps?.length?`<div class="detail-section"><h3>${n.category==='food'?'Method':'Steps shown'}</h3>${pointsHtml(n.steps)}</div>`:''}`;}
function evidenceHtml(n){return (n.evidence||[]).map(e=>`<div class="evidence-item"><strong>${esc(e.id)}</strong>${e.timestamp?`<button class="timestamp-button" data-timestamp="${esc(e.timestamp)}">▷ ${esc(e.timestamp)}</button>`:''}<div>${esc(e.quote)}</div><small>${{provided_text:'Provided source text',spoken:'Model-reported speech',visible_text:'Model-reported visible text',visual:'Model-reported visual observation'}[e.kind]||'Source'}${e.timestamp?' · approximate timestamp':''}</small></div>`).join('')||'<p>No source references available.</p>';}
function editFields(n){return `<div class="review-edit"><div class="field"><label for="edit-title">Title</label><input id="edit-title" maxlength="160" value="${esc(n.title)}"></div><div class="field"><label for="edit-summary">Summary</label><textarea id="edit-summary" rows="3">${esc(n.summary)}</textarea></div><div class="field"><label for="edit-points">Key takeaways <span>one per line</span></label><textarea id="edit-points" rows="4">${esc((n.key_points||[]).map(p=>p.text).join('\n'))}</textarea></div>${n.ingredients?.length?`<div class="field"><label for="edit-ingredients">Ingredients <span>name | quantity</span></label><textarea id="edit-ingredients" rows="5">${esc(n.ingredients.map(i=>i.name+' | '+i.quantity).join('\n'))}</textarea></div>`:''}${n.steps?.length?`<div class="field"><label for="edit-steps">Steps <span>one per line</span></label><textarea id="edit-steps" rows="5">${esc(n.steps.map(p=>p.text).join('\n'))}</textarea></div>`:''}<small>Changed points, steps and ingredients are labelled as reviewer edits and lose automatic evidence attribution.</small></div>`;}
async function openPost(id){
 try{
  const j=await api('/api/jobs/'+validId(id));state.selected=j;state.approval=null;const n=noteOf(j),review=j.status==='review';const media=j.has_media?(j.mime.startsWith('video/')?`<video id="source-video" controls playsinline preload="metadata" src="/media/${validId(j.id)}"></video>`:`<img src="/media/${validId(j.id)}" alt="${esc(n?.title||j.filename)}">`):`<div class="source-text-label">${j.mode==='demo'?'SYNTHETIC DEMO TEXT · NO VIDEO ANALYSED':'ORIGINAL SOURCE NOTES'}</div><pre class="source-text">${esc(j.source_text)}</pre>`;
  const empty=`<div class="empty-note">${icon('spark')}<h3>${j.status==='saved'?'Saved. Ready when you are.':j.status==='failed'?'Your source is safe. Analysis needs attention.':'Finding the useful details…'}</h3><p>${j.status==='saved'?'Prepare this older save once to create its searchable notes and embedding automatically.':j.status==='failed'?esc(j.error):'Preparing the notes and embedding automatically. You can keep browsing while it works.'}</p>${['saved','failed'].includes(j.status)?`<button class="button primary" data-analyse="${validId(j.id)}">${icon('spark')}${j.status==='failed'?'Retry preparation':'Prepare for search'}</button>`:''}</div>`;
  $('#post-detail').innerHTML=`<div class="post-dialog-header"><div><span class="avatar">Y</span><span>Your saved post</span><span class="source-id">${j.id.slice(0,8)}</span></div><button class="close-dialog icon-button" aria-label="Close post">×</button></div><div class="post-layout"><div class="post-media-pane">${media}</div><div class="post-notes-pane"><div class="detail-meta"><span class="tag">${labels[topicOf(j)]||'Other'}</span><span class="status-label ${esc(j.status)}">${statusNames[j.status]||j.status}</span></div><h2>${esc(n?.title||j.filename)}</h2><div class="detail-meta">${j.mode==='demo'?'Synthetic text example':j.mode==='manual'?'Local structured-note import':j.mode==='bookmark'?'Saved original · no model called':esc(j.model)}${j.auto_index?' · AI-generated notes':''}${j.elapsed?' · '+j.elapsed+'s preparation':''}</div><button class="text-button" data-assign="${validId(j.id)}">${icon('folder')} ${esc(j.collections.map(c=>c.name).join(', ')||'Add to a collection')}</button>${j.error&&n?`<div class="notice error">${esc(j.error)} <button class="button secondary" data-analyse="${validId(j.id)}">Retry preparation</button></div>`:''}${n?(review?editFields(n):noteBody(n)):empty}${n&&!n.evidence?.length?'<div class="notice">These older notes have no retained evidence references. Reanalyse the original to create evidence-linked notes with the updated extractor.</div>':''}${j.previous_note?`<details><summary class="evidence-heading">Previous note retained</summary>${noteBody(j.previous_note)}</details>`:''}${n?.unknowns?.length?`<div class="detail-section"><h3>What we don’t know</h3><div class="notice"><ul class="unknown-list">${n.unknowns.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div></div>`:''}${n?`<details><summary class="evidence-heading">Source evidence · ${n.evidence?.length||0} references</summary><p>${esc(j.metrics?.evidence_note||'Compare model-reported details with the original source.')}</p>${evidenceHtml(n)}</details>`:''}<details><summary class="evidence-heading">Processing trace</summary><ol class="trace-list">${(j.events||[]).map(e=>`<li>${esc(e.stage)}<small>${esc(e.detail)}</small></li>`).join('')}</ol></details><details class="advanced-note-tools"><summary>Note tools</summary><div class="detail-actions">${review?`<button class="button primary" id="preview-approval">Review & make searchable ${icon('arrow')}</button>`:j.status==='approved'?`${j.auto_index?'':`<button class="button secondary" id="build-index" ${j.has_embedding?'disabled':''}>${icon('spark')}${j.has_embedding?'Semantic index ready':'Build semantic index'}</button>`}<a class="button secondary" href="/export/${validId(j.id)}" download="saved-note-${j.id.slice(0,8)}.json">Export notes ↗</a>`:''}${n&&['approved','review'].includes(j.status)?`<button class="button secondary" data-reanalyse="${validId(j.id)}">Reanalyse original</button>`:''}<button class="button danger" data-delete="${validId(j.id)}" ${['processing','queued'].includes(j.status)?'disabled':''}>Remove save</button></div></details></div></div>`;
  if(!$('#post-dialog').open)$('#post-dialog').showModal();
 }catch(e){toast(e.message,true);}
}
function readEdits(){const edits={title:$('#edit-title').value,summary:$('#edit-summary').value,key_points:$('#edit-points').value.split('\n').filter(x=>x.trim()).map(text=>({text:text.trim()}))};if($('#edit-ingredients'))edits.ingredients=$('#edit-ingredients').value.split('\n').filter(x=>x.trim()).map(x=>{const [name,...quantity]=x.split('|');return {name:name.trim(),quantity:quantity.join('|').trim()||'Not stated'};});if($('#edit-steps'))edits.steps=$('#edit-steps').value.split('\n').filter(x=>x.trim()).map(text=>({text:text.trim()}));return edits;}
async function previewApproval(){const b=$('#preview-approval');b.disabled=true;try{const edits=readEdits(),res=await api('/api/review',{id:state.selected.id,edits});state.approval={id:state.selected.id,edits,approval_hash:res.approval_hash};$('#approval-content').innerHTML=`<div class="approval-note"><h3>${esc(res.recipe.title)}</h3>${noteBody(res.recipe)}</div><div class="approval-hash">Exact-note fingerprint: ${esc(res.approval_hash.slice(0,24))}…</div>`;$('#approval-dialog').showModal();}catch(e){toast(e.message,true);}finally{b.disabled=false;}}
async function approve(){if(!state.approval)return;const b=$('#confirm-approval');b.disabled=true;try{await api('/api/approve',state.approval);$('#approval-dialog').close();$('#post-dialog').close();state.approval=null;state.search=null;$('#search-summary').hidden=true;await refresh();changeView('saved');toast('Notes reviewed and searchable. The original stays linked.');}catch(e){toast(e.message,true);}finally{b.disabled=false;}}
async function analyse(id,reanalyse=false){const j=state.jobs.find(j=>j.id===id)||state.selected;if(reanalyse&&!confirm('Analyse this source again? Your previous note will be retained. The notes and embedding will be rebuilt automatically.'))return;if(!state.key&&!state.serverKey){$('#settings-dialog').showModal();toast('Connect AI in Settings, then retry preparation.',true);return;}try{await api(reanalyse?'/api/reanalyze':j.status==='saved'?'/api/analyze':'/api/retry',{id,api_key:state.key,model:state.model,auto_index:true});$('#post-dialog').close();await refresh();toast('Preparing your saved video for search.');}catch(e){toast(e.message,true);}}
async function removeSave(id){if(!confirm('Remove this save, its original source, notes and search entry? Exported copies are not affected.'))return;try{await api('/api/delete',{id});if(state.selected?.id===id)$('#post-dialog').close();state.search=null;$('#search-summary').hidden=true;await refresh();toast('Save removed from the workspace and its collections.');}catch(e){toast(e.message,true);}}
async function buildIndex(){const b=$('#build-index');b.disabled=true;b.textContent='Building index…';try{await api('/api/embed',{id:state.selected.id,api_key:state.key});await refresh();await openPost(state.selected.id);toast('Semantic index ready for this save.');}catch(e){b.disabled=false;b.textContent='Build semantic index';toast(e.message,true);}}
function collectionDialog(jobId=null){state.assignment=jobId;$('#collection-error').hidden=true;$('#collection-create').hidden=!!jobId;$('#collection-assignment').hidden=!jobId;$('#collection-dialog-title').textContent=jobId?'Save to collections':'New collection';$('#collection-save').textContent=jobId?'Save changes':'Create collection';$('#collection-name').value='';if(jobId){const j=state.jobs.find(j=>j.id===jobId)||state.selected;const current=new Set((j?.collections||[]).map(c=>c.id));$('#collection-assignment').innerHTML=state.collections.map(c=>`<label class="collection-option"><input type="checkbox" value="${validId(c.id)}" ${current.has(c.id)?'checked':''}>${esc(c.name)}<small>${c.count} saves</small></label>`).join('')||'<p>Create a collection first from the Saved view.</p>';}$('#collection-dialog').showModal();}
async function saveCollection(e){e.preventDefault();const b=$('#collection-save');b.disabled=true;try{if(state.assignment){await api('/api/assign',{id:state.assignment,collections:$$('#collection-assignment input:checked').map(x=>x.value)});}else{await api('/api/collections',{name:$('#collection-name').value.trim()});}$('#collection-dialog').close();await refresh();if(state.selected&&$('#post-dialog').open)await openPost(state.selected.id);toast(state.assignment?'Collections updated.':'Collection created.');}catch(e){$('#collection-error').hidden=false;$('#collection-error').textContent=e.message;}finally{b.disabled=false;}}
async function deleteCollection(id){if(!confirm('Delete this collection? Its saved posts will stay in All saves.'))return;try{await api('/api/collections',{action:'delete',id});state.collection='';state.tab='collections';clearSearch(false);await refresh();toast('Collection deleted. Original saves kept.');}catch(e){toast(e.message,true);}}
async function checkModels(){const b=$('#check-models');b.disabled=true;b.textContent='Checking…';const result=$('#model-check-result');result.hidden=false;result.textContent='Checking model access with Google…';try{const data=await api('/api/models',{api_key:$('#api-key').value.trim()||state.key});if(!data.models.length)throw Error('No compatible models listed for this key.');$('#available-models').innerHTML=data.models.map(m=>`<option value="${esc(m.id)}">${esc(m.id)}</option>`).join('');const current=$('#model-id').value.trim();if(data.models.some(m=>m.id===current))$('#available-models').value=current;$('#model-id').value=$('#available-models').value;$('#model-picker').hidden=false;result.textContent='Choose a model, then test and apply it. Listing does not guarantee quota or generation access.';}catch(e){result.textContent=e.message;}finally{b.disabled=false;b.textContent='Check available models';}}
async function applySettings(){const b=$('#settings-save'),key=$('#api-key').value.trim(),model=$('#model-id').value.trim()||'gemini-3.5-flash-lite';if(!key&&!state.serverKey){state.key='';state.model=model;$('#key-status').classList.remove('ready');updateImport();$('#settings-dialog').close();toast('Saving without AI remains available.');return;}b.disabled=true;b.textContent='Testing connection…';const result=$('#model-check-result');result.hidden=false;result.textContent='Testing one small text request…';try{await api('/api/test-model',{api_key:key,model});state.key=key;state.model=model;$('#key-status').classList.add('ready');updateImport();$('#settings-dialog').close();toast('AI connected. Saves will now prepare automatically.');if(state.pendingFeedSave)await saveFeedSelection();}catch(e){result.textContent=e.message;}finally{b.disabled=false;b.textContent='Test & use these settings';}}
function renderFeed(){
 const topics=[...new Set(state.feed.map(r=>r.topic))].sort();$('#feed-topic').innerHTML='<option value="">All interests</option>'+topics.map(t=>`<option value="${esc(t)}">${esc(t)}</option>`).join('');$('#feed-topic').value=state.feedTopic;
 const all=state.feed.filter(r=>!state.feedTopic||r.topic===state.feedTopic),rows=all.slice(0,state.feedLimit);$('#feed-count').textContent=`${all.length} videos to explore`;$('#feed-more').hidden=rows.length>=all.length;
 const signature=JSON.stringify(rows.map(r=>r.id));
 if(signature!==state.feedSignature){state.feedSignature=signature;$('#feed-grid').innerHTML=rows.map(r=>`<article class="feed-card" data-feed-card="${validId(r.id)}"><div class="feed-author"><span class="feed-avatar">${esc(r.topic[0])}</span><div><strong>${esc(r.topic)}</strong><small>${esc(r.credit)}</small></div></div><div class="feed-media">${r.mime.startsWith('video/')?`<video controls playsinline preload="none" ${r.poster_url?`poster="${esc(r.poster_url)}"`:''} src="${esc(r.media_url)}" aria-label="${esc(r.title)}"></video>`:`<img src="${esc(r.media_url)}" alt="${esc(r.title)}" loading="lazy">`}${r.silent?'<span class="feed-silent">Silent clip</span>':''}</div><div class="feed-caption"><button class="save-icon feed-bookmark" data-feed-save="${validId(r.id)}" aria-label="Save ${esc(r.title)} to a collection">${icon('bookmark')}</button><h2>${esc(r.title)}</h2><div class="feed-save-state" data-feed-status="${validId(r.id)}"></div></div></article>`).join('')||'<p>No videos in this collection yet.</p>';}
 for(const r of rows){const el=$(`[data-feed-status="${validId(r.id)}"]`),button=$(`[data-feed-save="${validId(r.id)}"]`);if(!el)continue;button.classList.toggle('is-saved',!!r.saved_id);button.title=r.saved_id?'Saved · organise collections':'Save to a collection';el.className='feed-save-state '+(r.search_ready?'ready':r.status==='failed'?'failed':'');el.textContent=r.search_ready?'✓ Saved · Search ready':['queued','processing'].includes(r.status)?'◷ Saved · Preparing for search…':r.status==='failed'?'Saved · Preparation needs attention. Tap the bookmark to retry.':r.saved_id?'Saved':'Save what you want to find again';}
}
function chooseFeedCollection(id){
 const item=state.feed.find(r=>r.id===id);if(!item)return;
 const job=state.jobs.find(j=>j.id===item.saved_id);state.pendingFeedSave={id,existingId:item.saved_id||'',collections:null};
 $('#feed-save-title').textContent=item.title;$('#feed-new-collection').value='';$('#feed-save-error').hidden=true;
 const selected=new Set(job?.collections?.map(c=>c.id)||[]);$('#feed-save-collections').innerHTML=state.collections.map(c=>`<label class="collection-option"><input type="checkbox" value="${validId(c.id)}" ${selected.has(c.id)?'checked':''}>${esc(c.name)}<small>${c.count} saves</small></label>`).join('');
 $('#feed-save-submit').textContent=item.status==='failed'?'Save & retry preparation':item.saved_id?'Update collections':'Save & prepare for search';$('#feed-save-dialog').showModal();
}
async function saveFeedSelection(e){
 e?.preventDefault();if(state.feedSaving||!state.pendingFeedSave)return;const request=state.pendingFeedSave,b=$('#feed-save-submit');
 try{
  state.feedSaving=true;b.disabled=true;$('#feed-save-error').hidden=true;
  if(request.collections===null){request.collections=$$('#feed-save-collections input:checked').map(n=>n.value);request.newCollection=$('#feed-new-collection').value.trim();}
  const item=state.feed.find(r=>r.id===request.id);
  if((!item?.saved_id||['failed','saved'].includes(item.status))&&!state.key&&!state.serverKey){$('#settings-dialog').showModal();toast('Connect AI once. Your selected video will then save and prepare automatically.');return;}
  if(request.newCollection){b.textContent='Creating collection…';const c=await api('/api/collections',{name:request.newCollection});request.collections.push(c.id);request.newCollection='';}
  b.textContent='Saving…';await api('/api/feed/save',{id:request.id,collections:request.collections,api_key:state.key,model:state.model});
  state.pendingFeedSave=null;$('#feed-save-dialog').close();await refresh();toast(item?.search_ready?'Collections updated. Already ready for search.':'Saved. Preparing for search automatically—you can keep browsing.');
 }catch(e){$('#feed-save-error').hidden=false;$('#feed-save-error').textContent=e.message;toast(e.message,true);}finally{state.feedSaving=false;b.disabled=false;b.textContent='Save & prepare for search';}
}
$('#feed-topic').addEventListener('change',e=>{state.feedTopic=e.target.value;state.feedLimit=12;renderFeed();});
$('#feed-more').addEventListener('click',()=>{state.feedLimit+=12;renderFeed();});
$('#feed-save-form').addEventListener('submit',saveFeedSelection);
$('#feed-save-dialog').addEventListener('close',()=>{if(!state.feedSaving)state.pendingFeedSave=null;});
document.addEventListener('play',e=>{if(e.target.tagName==='VIDEO')for(const v of $$('video'))if(v!==e.target)v.pause();},true);
document.addEventListener('click',e=>{
 const feedSave=e.target.closest('[data-feed-save]');if(feedSave){chooseFeedCollection(feedSave.dataset.feedSave);return;}
 const nav=e.target.closest('[data-nav]');if(nav){changeView(nav.dataset.nav);return;}
 const close=e.target.closest('.close-dialog');if(close){const d=close.closest('dialog');if(d.id==='post-dialog')$('#source-video')?.pause();d.close();return;}
 const open=e.target.closest('[data-open]');if(open){openPost(open.dataset.open);return;}
 const assign=e.target.closest('[data-assign]');if(assign){collectionDialog(assign.dataset.assign);return;}
 const del=e.target.closest('[data-delete]');if(del){removeSave(del.dataset.delete);return;}
 const re=e.target.closest('[data-reanalyse]');if(re){analyse(re.dataset.reanalyse,true);return;}
 const a=e.target.closest('[data-analyse]');if(a){analyse(a.dataset.analyse);return;}
 const c=e.target.closest('[data-collection]');if(c){state.collection=c.dataset.collection;state.topic='all';state.status='all';$('#status-filter').value='all';state.tab='posts';clearSearch(false);renderLibrary();return;}
 const dc=e.target.closest('[data-delete-collection]');if(dc){deleteCollection(dc.dataset.deleteCollection);return;}
 const topic=e.target.closest('[data-topic]');if(topic){state.topic=topic.dataset.topic;if(state.search)runSearch();else renderLibrary();return;}
 const query=e.target.closest('[data-query]');if(query){$('#search-input').value=query.dataset.query;runSearch();return;}
 const stamp=e.target.closest('[data-timestamp]');if(stamp){const v=$('#source-video');if(v){const [m,s]=stamp.dataset.timestamp.split(':').map(Number);v.currentTime=m*60+s;v.play().catch(()=>{});}else toast('This source is text or an image; there is no playable timestamp.');return;}
 if(e.target.closest('#clear-search'))clearSearch();if(e.target.closest('#preview-approval'))previewApproval();if(e.target.closest('#build-index'))buildIndex();
 if(e.target.closest('#connect-model'))$('#settings-dialog').showModal();
 if(e.target.closest('#back-collections')){state.collection='';state.tab='collections';clearSearch(false);renderLibrary();}
});
$('#tab-posts').addEventListener('click',()=>{state.tab='posts';renderLibrary();});$('#tab-collections').addEventListener('click',()=>{state.tab='collections';state.collection='';clearSearch(false);renderLibrary();});
$('#new-collection').addEventListener('click',()=>collectionDialog());$('#collection-form').addEventListener('submit',saveCollection);
$('#demo-button').addEventListener('click',demoLibrary);$('#empty-demo').addEventListener('click',demoLibrary);
$('#status-filter').addEventListener('change',e=>{state.status=e.target.value;renderLibrary();});
$('#search-form').addEventListener('submit',runSearch);$('#semantic-toggle').addEventListener('change',()=>{if($('#search-input').value.trim())runSearch();});$('#import-form').addEventListener('submit',importSource);
$('#input-media').addEventListener('click',()=>{state.input='media';updateImport();});$('#input-notes').addEventListener('click',()=>{state.input='notes';updateImport();});$('#analyse-now').addEventListener('change',updateImport);
$('#file-input').addEventListener('change',e=>setFile(e.target.files[0]));$('#dropzone').addEventListener('dragover',e=>{e.preventDefault();$('#dropzone').classList.add('dragging');});$('#dropzone').addEventListener('dragleave',()=>$('#dropzone').classList.remove('dragging'));$('#dropzone').addEventListener('drop',e=>{e.preventDefault();$('#dropzone').classList.remove('dragging');setFile(e.dataTransfer.files[0]);});
$('#settings-open').addEventListener('click',()=>$('#settings-dialog').showModal());$('#profile-home').addEventListener('click',()=>$('#settings-dialog').showModal());$('#profile-home').title='Model settings';$('#profile-home').setAttribute('aria-label','Model settings');
$('#check-models').addEventListener('click',checkModels);$('#available-models').addEventListener('change',e=>$('#model-id').value=e.target.value);$('#settings-save').addEventListener('click',applySettings);
$('#confirm-approval').addEventListener('click',approve);$('#refresh-jobs').addEventListener('click',()=>refresh().catch(e=>toast(e.message,true)));
$('#post-dialog').addEventListener('close',()=>$('#source-video')?.pause());
api('/api/config').then(c=>{state.model=c.model;state.serverKey=c.has_server_key;$('#model-id').value=state.model;$('#key-status').classList.toggle('ready',state.serverKey);updateImport();return refresh();}).catch(e=>toast('Could not connect: '+e.message,true));
