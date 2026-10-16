/* Keep collection reminders visible; verbose run reports live in a modal drawer. */
window.createSubjectTrainingDetails=function({report,refresh,rollback,onOpen}){
 const dialog=document.createElement('dialog');dialog.id='subjectTrainingDetails';dialog.setAttribute('aria-labelledby','subjectTrainingDetailsTitle');
 dialog.style.cssText='width:min(680px,94vw);max-height:90dvh;overflow:auto;box-sizing:border-box;text-align:left';
 const heading=document.createElement('h3');heading.id='subjectTrainingDetailsTitle';heading.textContent='Subject training diagnostics';
 const close=document.createElement('button');close.type='button';close.textContent='Close';close.onclick=()=>dialog.close();
 const button=document.createElement('button');button.type='button';button.textContent='Training diagnostics…';button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls',dialog.id);button.setAttribute('aria-expanded','false');
 button.onclick=()=>{if(!dialog.open)dialog.showModal();button.setAttribute('aria-expanded','true');Promise.resolve().then(onOpen).catch(()=>{})};
 dialog.addEventListener('close',()=>{button.setAttribute('aria-expanded','false');button.focus({preventScroll:true})});
 dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close()});
 report.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';
 dialog.append(heading,close,report,refresh,rollback);document.body.append(dialog);
 const reminders=document.createElement('div');reminders.className='tiny';reminders.id='subjectIncompleteClasses';reminders.hidden=true;
 function updateIncomplete(classes){
  const incomplete=classes.filter(c=>Number(c.source_images)<3);reminders.replaceChildren();reminders.hidden=!incomplete.length;
  if(!incomplete.length)return;
  const title=document.createElement('b');title.textContent='Still collecting examples';reminders.append(title);
  for(const c of incomplete){const row=document.createElement('div');row.style.overflowWrap='anywhere';row.textContent=c.label+' · '+c.source_images+'/3 source images';reminders.append(row)}
 }
 return {button,reminders,dialog,updateIncomplete};
};
