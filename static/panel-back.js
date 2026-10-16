/* One same-URL history guard while panels are open; no guard on the bare grid. */
window.createPanelBackGuard=function({read,history,onPop}){
 let armed=false,retiring=false;
 function sync(){
  const panels=read();if(retiring)return;
  if(panels.length&&!armed){history.pushState({...history.state,n8visionPanelGuard:true},'');armed=true}
  else if(!panels.length&&armed){retiring=true;history.back()}
 }
 onPop(()=>{
  armed=false;
  if(retiring){retiring=false;sync();return}
  const panels=read();if(panels.length)panels[panels.length-1].close();
  sync();
 });
 return {sync};
};
(function(){
 if(!S.mobile)return;
 const ages=new Map();let serial=0;
 const panel=(key,close)=>({key,close});
 function read(){
  const panels=[],get=id=>document.getElementById(id);
  if(get('rail')?.classList.contains('railOpen'))panels.push(panel('rail',()=>setControlMenu(false)));
  if(get('filterDrawer')?.classList.contains('open'))panels.push(panel('filters',()=>setDrawer(false)));
  if(get('settingsDrawer')?.classList.contains('open'))panels.push(panel('settings',closeSettings));
  for(const [id,close] of [['interactionHelp',()=>get('interactionHelpClose')?.click()],['jobPrep',closeJobPrep],['refineWizard',()=>{get('refineWizard').hidden=true}],['workshopWizard',()=>{get('workshopWizard').hidden=true}]]){
   const node=get(id);if(node&&!node.hidden)panels.push(panel(node,close));
  }
  if(get('imageViewer')?.classList.contains('open')){
   panels.push(panel('inspector',closeViewer));
   if(get('imageViewer').classList.contains('maskCardMode'))panels.push(panel('mask',()=>get('maskClose')?.click()));
  }
  for(const dialog of document.querySelectorAll('dialog[open]'))panels.push(panel(dialog,()=>{
   const event=new Event('cancel',{cancelable:true});if(dialog.dispatchEvent(event))dialog.close();
  }));
  const keys=new Set(panels.map(p=>p.key));for(const key of ages.keys())if(!keys.has(key))ages.delete(key);
  for(const p of panels)if(!ages.has(p.key))ages.set(p.key,++serial);
  return panels.sort((a,b)=>ages.get(a.key)-ages.get(b.key));
 }
 const guard=createPanelBackGuard({read,history,onPop:fn=>window.addEventListener('popstate',fn)});
 new MutationObserver(()=>guard.sync()).observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','hidden','open']});
 guard.sync();
})();
