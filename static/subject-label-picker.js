window.uniqueConceptLabels=function(values){const names=new Map();for(const value of values||[]){const text=String(value?.concept??value??'').trim();if(!text)continue;const key=text.normalize('NFKC').toLowerCase();if(!names.has(key))names.set(key,text)}return [...names.values()].sort((a,b)=>a.localeCompare(b))};
/* Warm once per browser session, independently of opening the correction dialog. */
const observationLabelCache={labels:[],loaded:false,pending:null};
window.rememberObservationLabel=function(label){label=String(label||'').trim();if(label&&!observationLabelCache.labels.some(x=>x.toLowerCase()===label.toLowerCase())){observationLabelCache.labels.push(label);observationLabelCache.labels.sort((a,b)=>a.localeCompare(b))}};
window.preloadObservationLabels=function(){
 if(observationLabelCache.loaded)return Promise.resolve(observationLabelCache.labels);
 if(observationLabelCache.pending)return observationLabelCache.pending;
 observationLabelCache.pending=fetch('/api/observations/custom-labels').then(r=>{if(!r.ok)throw Error('Saved labels unavailable');return r.json()}).then(data=>{for(const label of data.labels||[])window.rememberObservationLabel(label);observationLabelCache.loaded=true;return observationLabelCache.labels}).finally(()=>{observationLabelCache.pending=null});
 return observationLabelCache.pending;
};
window.preloadObservationLabels().catch(()=>{});
/* Explicit corrections only: choosing a suggestion never commits or trains it. */
window.chooseObservationLabel = function({concept, suggestion='', subject=false, knownLabels=[]}) {
 return new Promise(resolve=>{
  const dialog=document.createElement('dialog');
  dialog.className='subjectLabelDialog';
  dialog.style.cssText='width:min(440px,calc(100vw - 32px));max-height:85dvh;overflow:auto;box-sizing:border-box';
  const title=document.createElement('h3');title.textContent=subject?'Assign subject identifier':'Correct detection label';
  const context=document.createElement('p');context.textContent='Currently: '+concept;
  const input=document.createElement('input');input.type='text';input.value=suggestion;input.autocomplete='off';input.maxLength=200;
  input.style.cssText='width:100%;box-sizing:border-box';
  const field=document.createElement('label');field.textContent='Label';field.append(input);
  const custom=document.createElement('select'),common=document.createElement('select');
  function fill(select,placeholder,values){select.replaceChildren(new Option(placeholder,''),...window.uniqueConceptLabels(values).map(x=>new Option(x,x)))}
  fill(custom,observationLabelCache.labels.length?'Choose a saved label…':observationLabelCache.loaded?'No saved labels yet':'Loading saved labels…',observationLabelCache.labels);custom.disabled=!observationLabelCache.labels.length;
  fill(common,'Choose a common label…',['person','woman','man','girl','boy','couple','group','humanoid','robot','cyborg','anthro','animal','cat','dog','horse','bird','fish','panda','fox','tiger','car','motorcycle','bicycle','truck','bus','train','aircraft','boat','building','house','tree','flower','food','burger','chair','unidentified subject']);
  for(const [select,caption] of [[custom,'Previously entered labels'],[common,'Common labels']]){
   const label=document.createElement('label');label.textContent=caption;select.style.cssText='display:block;width:100%;margin:6px 0 12px';label.append(select);dialog.append(label);
   select.onchange=()=>{if(select.value){input.value=select.value;input.dispatchEvent(new Event('input'));}};
  }
  const suggestions=document.createElement('datalist');suggestions.id='correctionConceptSuggestions';input.setAttribute('list',suggestions.id);dialog.append(suggestions);
  function updateSuggestions(){suggestions.replaceChildren(...window.uniqueConceptLabels([...knownLabels,...observationLabelCache.labels,...Array.from(common.options).map(x=>x.value)]).map(x=>new Option(x,x)))}
  updateSuggestions();
  const status=document.createElement('p');status.className='tiny';status.setAttribute('role','status');
  const form=document.createElement('form');form.method='dialog';
  const save=document.createElement('button');save.type='submit';save.textContent='Use label';
  const cancel=document.createElement('button');cancel.type='button';cancel.textContent='Cancel';
  input.oninput=()=>{save.disabled=!input.value.trim()};input.oninput();
  let result=null;
  form.onsubmit=event=>{event.preventDefault();if(input.value.trim()){result=input.value.trim();dialog.close()}};
  cancel.onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();resolve(result)},{once:true});
  form.append(save,cancel);dialog.prepend(title,context,field);dialog.append(status,form);document.body.append(dialog);dialog.showModal();input.focus();
  window.preloadObservationLabels().then(labels=>{
   updateSuggestions();
   if(!dialog.isConnected)return;
   fill(custom,labels.length?'Choose a saved label…':'No saved labels yet',labels);custom.disabled=!labels.length;
  }).catch(()=>{if(dialog.isConnected){fill(custom,'Saved labels unavailable',[]);status.textContent='Could not load saved labels. You can still type a label or choose a common term.'}});
 });
};
