/* Explicit corrections only: choosing a suggestion never commits or trains it. */
window.chooseObservationLabel = function({concept, suggestion='', subject=false}) {
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
  function fill(select,placeholder,values){select.replaceChildren(new Option(placeholder,''),...values.map(x=>new Option(x,x)))}
  fill(custom,'Loading saved labels…',[]);custom.disabled=true;
  fill(common,'Choose a common label…',['person','woman','man','girl','boy','couple','group','humanoid','robot','cyborg','anthro','animal','cat','dog','horse','bird','fish','panda','fox','tiger','car','motorcycle','bicycle','truck','bus','train','aircraft','boat','building','house','tree','flower','food','burger','chair','unidentified subject']);
  for(const [select,caption] of [[custom,'Previously entered labels'],[common,'Common labels']]){
   const label=document.createElement('label');label.textContent=caption;select.style.cssText='display:block;width:100%;margin:6px 0 12px';label.append(select);dialog.append(label);
   select.onchange=()=>{if(select.value){input.value=select.value;input.dispatchEvent(new Event('input'));}};
  }
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
  fetch('/api/observations/custom-labels').then(r=>{if(!r.ok)throw Error();return r.json()}).then(data=>{
   if(!dialog.isConnected)return;
   const labels=data.labels||[];fill(custom,labels.length?'Choose a saved label…':'No saved labels yet',labels);custom.disabled=!labels.length;
  }).catch(()=>{if(dialog.isConnected){fill(custom,'Saved labels unavailable',[]);status.textContent='Could not load saved labels. You can still type a label or choose a common term.'}});
 });
};
