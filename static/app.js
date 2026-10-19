const mobileDevice=!!(navigator.userAgentData?.mobile||/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)||(navigator.maxTouchPoints>0&&matchMedia('(pointer: coarse)').matches&&Math.min(screen.width,screen.height)<=900));
let mobilePager=null,mobilePageTask=null,mobileLayoutTask=null;
const mobileColumnPrefs={portrait:3,landscape:5};
for(const orientation of ['portrait','landscape'])try{const value=Number(localStorage.getItem('n8vision.columns.'+orientation));if(value)mobileColumnPrefs[orientation]=Math.max(1,Math.min(orientation==='portrait'?3:8,value))}catch(_){}
function mobileOrientation(){const v=window.visualViewport;return (v?.width||innerWidth)>(v?.height||innerHeight)?'landscape':'portrait'}
function mobileColumns(){return mobileColumnPrefs[mobileOrientation()]}
const S={edition:null,capabilities:{inference:false,processing:false},mobile:mobileDevice,viewer:null,path:null,parent:null,files:[],dirs:[],selected:new Set(),treeOpen:true,semantic:null,models:[],enabledModels:new Set(),obsRevision:0,qualityPath:null,boxes:false,masks:false,drawer:false,discovered:[],magnets:new Map(),magnetSeq:0,compare:null,sortKey:'none',sortDir:'asc',gridDetail:'hover',selectionAnchor:null,softCtrl:false,softShift:false,multiWork:[],multiIndex:-1,viewerStretch:false,viewerClean:false,defaultRoot:null,filterPresets:{},sanityBadges:'compact',hideAllBadges:readBadgePreference(),thumbnailCache:null,imageGridEnabled:true,uncappedUnsanity:false,storageClass:null,scopeRoot:null,scopeRecursive:false,catalogRecursive:false,scopeRootDirs:[],scopeSelections:new Set(),scopeSelectionAnchor:null,gridGapTenths:1,gridRedrawEpoch:0,ringBufferRows:50,ringSouthBias:2,thumbWarmEnabled:true,archiveRoots:[],promptTranslator:{model:'',type:'stable_diffusion',device:'default'},checkpointLibrary:null,textStreamSeen:new Set()};const $=s=>document.querySelector(s),enc=encodeURIComponent;
function pagedBrowse(){return S.mobile||!!S.desktopWindowed}
try{S.desktopWindowed=localStorage.getItem('n8vision.desktopWindowed')==='1';const size=Number(localStorage.getItem('n8vision.desktopWindowSize'));S.desktopWindowSize=Number.isInteger(size)&&size>=1000&&size<=100000&&size%1000===0?size:4000}catch(_){S.desktopWindowed=false;S.desktopWindowSize=4000}
function readBadgePreference(){try{return localStorage.getItem('n8vision.hideAllBadges')==='1'}catch(_){return false}}
function applyBadgeVisibility(){
 document.body.dataset.hideBadges=String(!!S.hideAllBadges);
 const control=$('#hideAllBadges');if(control)control.checked=!!S.hideAllBadges;
}
applyBadgeVisibility();
const hideAllBadgesControl=$('#hideAllBadges');
if(hideAllBadgesControl)hideAllBadgesControl.onchange=e=>{
 S.hideAllBadges=!!e.target.checked;
 try{localStorage.setItem('n8vision.hideAllBadges',S.hideAllBadges?'1':'0')}catch(_){}
 applyBadgeVisibility();
};
let gridGovernorLast=0;
function gridActivity(reason='grid'){
 const now=performance.now();if(now-gridGovernorLast<40)return;gridGovernorLast=now;
 const body=JSON.stringify({reason});
 try{
  const h={'Content-Type':'application/json'},c=credential();if(c)h['X-N8Vision-Credential']=c;
  fetch('/api/grid/activity',{method:'POST',headers:h,body,keepalive:true}).catch(()=>{});
 }catch(_){}
}
function credential(){return localStorage.getItem('n8visionCredential')||''}async function j(url,opt={}){opt={...opt,headers:{...(opt.headers||{})}};const c=credential();if(c)opt.headers['X-N8Vision-Credential']=c;const r=await fetch(url,opt);const text=await r.text();if(!r.ok){const error=new Error(`${url} returned HTTP ${r.status}${text?`: ${text}`:''}`);try{error.response=JSON.parse(text)}catch(_){}throw error;}if(!text.trim())throw new Error(`${url} returned an empty response`);try{const data=JSON.parse(text);if(isAssetMutation(url,String(opt.method||'GET').toUpperCase()))invalidateVisibleAssets({pixels:mutationTouchesPixels(url)});return data}catch(e){if(e instanceof SyntaxError)throw new Error(`${url} returned invalid JSON (HTTP ${r.status}): ${e.message}`);throw e}}// I.2i: event-driven invalidation. No periodic cache sweeper.
let assetEpoch=0;
function invalidateVisibleAssets({pixels=false}={}){
 assetEpoch++;
 S.obsRevision=String(S.obsRevision||0).split('-')[0]+'-'+assetEpoch;
 if(pixels)S.gridRedrawEpoch=(S.gridRedrawEpoch||0)+1;
 document.querySelectorAll('img.gridGeomLayer, img.viewerSavedMasks').forEach(im=>{
  try{const u=new URL(im.src,location.href);u.searchParams.set('rev',S.obsRevision);im.src=u.pathname+u.search}catch(_e){}
 });
 if(pixels)document.querySelectorAll('img.gridThumb').forEach(im=>{
  try{const u=new URL(im.src,location.href);u.searchParams.set('r',String(S.gridRedrawEpoch));im.src=u.pathname+u.search}catch(_e){}
 });
}
function isAssetMutation(url,method){
 if(!['POST','PUT','PATCH','DELETE'].includes(method))return false;
 // Reads, launches and configuration writes are not asset mutations.
 return /^\/api\/(?:dev\/analysis(?:\/shown)?|observations\/(?:teach|correct)|learning\/(?:sam-mask-save|save-mask)|(?:files?|images?)\/(?:delete|move|rename|replace|restore)|(?:delete|move|rename|replace|restore|trash|recycle|undo)(?:\/|$)|mv\/(?:move|delete|rename)|orphans\/purge)/.test(url);
}
function mutationTouchesPixels(url){return /(?:delete|move|rename|replace|restore|trash|recycle|undo|orphans\/purge)/.test(url)}
async function acceptPairing(){const u=new URL(location.href),pair=u.searchParams.get('pair');if(!pair)return;try{const r=await j('/api/network/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pairing_token:pair,device_name:(navigator.platform||'Device')+' · '+(navigator.userAgentData?.brands?.[0]?.brand||navigator.userAgent.split(' ')[0]||'Browser')})});localStorage.setItem('n8visionCredential',r.credential);u.searchParams.delete('pair');history.replaceState({},'',u.pathname+u.search+u.hash)}catch(e){alert('N8Vision pairing failed: '+e.message)}}function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function markEditionControls(){
 const group=(id,cap)=>{const node=$(id);if(node)node.closest('section').dataset.capability=cap};
 group('#classifyBtn','inference');group('#similarBtn','inference');group('#mvStatus','inference');group('#stopAnalysisBtn','inference');
 for(const id of ['#semantic','#semanticBtn','#clearSemanticBtn','#uncappedUnsanity']){const node=$(id);if(node)node.dataset.capability='inference';}
 for(const id of ['#orderingModeBtn','#orderingPanel','#regenerateBtn','#refineWizard','#workshopWizard','#savePromptTranslatorBtn','#checkpointLibraryStatus','#refreshCheckpointLibraryBtn']){const node=$(id);if(node)node.dataset.capability='processing';}
 const uncapped=$('#uncappedUnsanity');if(uncapped?.closest('label')?.nextElementSibling)uncapped.closest('label').nextElementSibling.dataset.capability='inference';
 for(const option of $('#sortKey')?.options||[])if(['similarity','uniqueness'].includes(option.value))option.dataset.capability='inference';
 for(const id of ['#rasterThumb','#rasterThreshold','#rasterLight','#rasterMedium','#rasterHeavy','#rasterGradeB','#uncappedUnsanity']){const node=$(id);if(node)node.closest('label')?.setAttribute('data-capability','inference');}
}
function applyEdition(info){
 S.edition=info.edition;S.capabilities=info;
 document.body.dataset.edition=info.edition;document.body.dataset.inference=String(!!info.inference);document.body.dataset.processing=String(!!info.processing);document.body.classList.remove('editionPending');
 const version=document.querySelector('.brand span');if(version)version.textContent=(info.version||'I.2t-l-Z2b')+' · '+info.name;
 if(!info.processing)setMode('explore');
 document.body.dataset.subjectIntelligence=String(!!info.subject_intelligence);
 if(info.subject_intelligence&&!document.getElementById('subjectSeparateBtn')){
  const section=document.createElement('section'),heading=document.createElement('h3'),button=document.createElement('button'),detail=document.createElement('p');
  heading.textContent='Subject extraction and naming';button.id='subjectSeparateBtn';button.textContent='Separate selected subjects · BiRefNet';
  detail.className='tiny';detail.title='Subjectified filter: + requires named subjects; − excludes fully named images. Images with unidentified or unresolved subjects remain eligible. This status describes labels, not verified accuracy.';detail.textContent='BiRefNet extracts unnamed foreground regions only. Touching subjects may remain joined and need mask editing or subject reconstruction. Naming is a separate optional action. First use downloads model weights.';
  button.onclick=async()=>{
   const paths=subjectificationTargets();if(!paths.length)return alert('Select images to separate their subjects. The Subjectified filter also excludes selected images that do not match.');
   button.disabled=true;
   try{const result=await post('/api/subjects/separate',{paths});$('#status').textContent='Subject separation queued · '+result.id;scheduleJobsPoll(500)}catch(error){alert(error.message)}finally{button.disabled=false}
  };
  const yolast=document.createElement('button');yolast.textContent='Name selected subjects · YOLAST';
  const passLabel=document.createElement('label'),passLimit=document.createElement('input');passLimit.type='number';passLimit.min='1';passLimit.max='100';passLimit.step='1';passLimit.value='8';passLabel.append(document.createTextNode('YOLAST maximum passes per image '),passLimit);
  j('/api/subjects/naming/settings').then(settings=>passLimit.value=settings.max_passes).catch(()=>{});
  const namingHelp=document.createElement('p');namingHelp.className='tiny';namingHelp.textContent='Optional YOLO-World naming, capped across all subjects and retries per image. Names only unidentified masks; preserves their pixels. Or skip YOLAST and use Recognize learned classes.';
  yolast.onclick=async()=>{const paths=subjectificationTargets(),max_passes=Number(passLimit.value);if(!paths.length)return alert('Select images with extracted subject masks.');if(!Number.isInteger(max_passes)||max_passes<1||max_passes>100)return alert('Choose 1–100 passes per image.');yolast.disabled=true;try{const result=await post('/api/subjects/name',{paths,max_passes});$('#status').textContent='YOLAST naming queued · '+result.id;scheduleJobsPoll(500)}catch(error){alert(error.message)}finally{yolast.disabled=false}};
  const qwen=document.createElement('button');qwen.id='subjectQwenBtn';qwen.textContent='Inspect selected subjects with the language model';
  qwen.onclick=async()=>{const paths=[...S.selected];if(!paths.length)return alert('Select images with subject masks first.');qwen.disabled=true;try{const result=await post('/api/subjects/interpret',{paths});$('#status').textContent='Language model subject review queued · '+result.id;scheduleJobsPoll(500)}catch(error){alert(error.message)}finally{qwen.disabled=false}};
  const qwenHelp=document.createElement('p');qwenHelp.className='tiny';qwenHelp.textContent='Uses the selected Prompt Translator model in Comfy with image input. Draft names and visible features appear in the inspector; labels and masks stay unchanged.';
  const reconstruct=document.createElement('button');reconstruct.id='subjectReconstructBtn';reconstruct.textContent='Assemble selected subjects';
  const parser=document.createElement('select');parser.id='subjectParser';parser.setAttribute('aria-label','Subject reconstruction model');parser.innerHTML='<option value="partglee">PartGLEE</option><option value="langhops">LangHOPS</option>';
  reconstruct.onclick=async()=>{const paths=[...S.selected];if(!paths.length)return alert('Select images to reconstruct.');reconstruct.disabled=true;try{const result=await post('/api/subjects/reconstruct',{paths,engine:parser.value});$('#status').textContent='Subject reconstruction queued · '+result.id;scheduleJobsPoll(500)}catch(error){alert(error.message)}finally{reconstruct.disabled=false}};
  const parserHelp=document.createElement('p');parserHelp.className='tiny';parserHelp.textContent='Optional pretrained object/part models. Run Install-SubjectParts once. Ownership starts as a draft; confirm parts before teaching.';
  const autoLabel=document.createElement('label'),autoLM=document.createElement('input');autoLM.type='checkbox';autoLM.id='autoSubjectLM';autoLabel.append(autoLM,document.createTextNode(' Automatically inspect unidentified subjects with the language model'));
  j('/api/subjects/reconstruction/settings').then(settings=>autoLM.checked=!!settings.auto_language_model).catch(()=>{});
  autoLM.onchange=async()=>{try{await j('/api/subjects/reconstruction/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_language_model:autoLM.checked})})}catch(error){autoLM.checked=!autoLM.checked;alert(error.message)}};
  const train=document.createElement('button'),recognize=document.createElement('button'),rollback=document.createElement('button'),trainingStatus=document.createElement('p');train.id='trainSubjectClassesBtn';train.textContent='Train learned subject classes';recognize.id='recognizeSubjectClassesBtn';recognize.textContent='Recognize learned classes in selected subjects';rollback.id='rollbackSubjectClassesBtn';rollback.textContent='Restore previous class model';trainingStatus.id='subjectClassStatus';trainingStatus.className='tiny';
  const trainingLamp=document.createElement('span'),trainingCaption=document.createElement('span');trainingLamp.id='subjectTrainingLamp';trainingCaption.id='subjectTrainingCaption';Object.assign(trainingLamp.style,{display:'inline-block',width:'10px',height:'10px',borderRadius:'50%',marginRight:'8px'});train.textContent='';train.append(trainingLamp,trainingCaption);train.setAttribute('aria-live','polite');
  const showTrainingState=state=>{const busy=state.training?.state==='running',queued=state.training?.state==='queued',pending=!!state.training?.queued_update,last=state.runs?.[0]?.state;const color=busy?'#e9b44c':queued?'#66aaff':last==='active'?'#66d58c':last==='rejected'?'#ef8c42':last==='failed'?'#ed6464':'#999';trainingLamp.style.background=color;trainingLamp.style.boxShadow='0 0 5px '+color;trainingCaption.textContent=busy?(pending?'Training · next pass queued':'Training · click to queue next pass'):queued?'Training queued':last==='active'?'Training complete · train again':last==='rejected'?'Validation failed · train again':last==='failed'?'Training failed · retry':'Train learned subject classes';train.disabled=pending;train.title=busy?'Current pass continues. One follow-up pass uses the latest confirmed lessons.':'Train confirmed composite classes';S.classTrainingBusy=busy||queued;};
  const autoTrainLabel=document.createElement('label'),autoTrain=document.createElement('input');autoTrain.type='checkbox';autoTrain.id='autoTrainSubjectClasses';autoTrainLabel.append(autoTrain,document.createTextNode(' Train after manual Learn Subject commits'));
  const refreshTraining=async()=>{try{const state=await j('/api/subjects/classes/status');autoTrain.checked=state.auto_train;showTrainingState(state);trainingDetails.updateIncomplete(state.classes||[]);trainingStatus.textContent=state.classes.length?state.classes.map(c=>`${c.label}: ${c.source_images} source images${c.ready?'':' (needs 3)'}`).join(' · ')+(state.active?' · Active trained model':' · Needs two ready classes before training'):'Confirm an LLM-proposed or corrected Subject label, then Learn Subject. At least three source images per class; source-disjoint folds test every eligible example. Classes are admitted separately; exact labels remain separate.';const latest=state.runs?.[0];if(latest){let report={};try{report=JSON.parse(latest.report||'{}')}catch(_){}trainingStatus.textContent+='\nLast training: '+(latest.state==='active'?'activated':latest.state==='rejected'?'not activated — validation failed':latest.state)+(report.validation?' ('+Math.round(report.validation.accuracy*100)+'% overall accepted'+(report.partial_activation?'; partial class update':'')+')':'');if(report.diagnostics?.length)trainingStatus.textContent+='\n'+report.diagnostics.join('\n');else if(report.validation?.per_class)trainingStatus.textContent+='\nHeld-out results: '+Object.entries(report.validation.per_class).map(([name,value])=>name+': '+Math.round(value*100)+'%').join(' · ');if(report.error)trainingStatus.textContent+='\n'+report.error;}trainingStatus.style.whiteSpace='pre-wrap';recognize.disabled=!state.active;rollback.disabled=!state.active?.previous_revision;}catch(error){trainingStatus.textContent=error.message}};
  autoTrain.onchange=async()=>{try{await j('/api/subjects/classes/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({auto_train:autoTrain.checked})})}catch(error){alert(error.message)}};
  train.onclick=async()=>{try{const job=await post('/api/subjects/classes/train',{});$('#status').textContent=job.queued_update?'Training is running; one follow-up pass queued':'Composite class training queued · '+job.id;await refreshTraining();scheduleJobsPoll(500)}catch(error){alert(error.message)}};
  const applyRecognitionLabel=document.createElement('label'),applyRecognition=document.createElement('input');applyRecognition.type='checkbox';applyRecognition.checked=true;applyRecognitionLabel.append(applyRecognition,document.createTextNode(' Apply accepted learned labels to unidentified subjects'));
  recognize.onclick=async()=>{const paths=[...S.selected];if(!paths.length)return alert('Select images with assembled subject masks first.');try{const job=await post('/api/subjects/classes/recognize',{paths,apply_unidentified:applyRecognition.checked});$('#status').textContent='Learned class recognition queued · '+job.id;scheduleJobsPoll(500)}catch(error){alert(error.message)}};
  rollback.onclick=async()=>{try{await post('/api/subjects/classes/rollback',{});await refreshTraining();$('#status').textContent='Previous validated class model restored'}catch(error){alert(error.message)}};
  const refreshClassStatus=document.createElement('button');refreshClassStatus.id='refreshSubjectClassStatusBtn';refreshClassStatus.textContent='Refresh class training status';refreshClassStatus.onclick=refreshTraining;S.refreshSubjectClassStatus=refreshTraining;recognize.disabled=true;rollback.disabled=true;
  const trainingDetails=createSubjectTrainingDetails({report:trainingStatus,refresh:refreshClassStatus,rollback,onOpen:refreshTraining});
  section.append(autoTrainLabel,train,applyRecognitionLabel,recognize,trainingDetails.button,trainingDetails.reminders);
  section.append(heading,button,detail,passLabel,yolast,namingHelp,parser,reconstruct,parserHelp,autoLabel,qwen,qwenHelp);$('#classifyBtn')?.closest('section')?.after(section);
 }
}
const translator=$('#promptTranslatorModel');if(translator)translator.closest('section').dataset.capability='processing';
markEditionControls();

const gridWork=createGridWorkQueue({ready:()=>!browseEverRequested||S.gridHasPainted||S._rootBrowseComplete,idle:fn=>window.requestIdleCallback?window.requestIdleCallback(fn,{timeout:1000}):setTimeout(fn,0)});
function gridFirstPaint(){if(S.gridHasPainted)return;S.gridHasPainted=true;console.info('[N8Vision] First grid mounted · resident images='+S.files.length+' · mode='+(S.mobile?'mobile':S.desktopWindowed?'window '+S.desktopWindowSize:'full catalog'));requestAnimationFrame(()=>setTimeout(()=>gridWork.kick(),0));}
async function init(){
 await acceptPairing();
 if(credential())await post('/api/network/media-session',{});
 applyEdition(await j('/api/edition'));
 showLiteIntroduction();
 // Processing shelves are initialized after the initial grid paint.
 try{const c=await j('/api/config');S.gridDetail=c.grid_detail||'hover';S.gridGapTenths=Number.isFinite(Number(c.grid_gap_tenths))?Number(c.grid_gap_tenths):1;document.documentElement.style.setProperty('--grid-gap-tenths',S.gridGapTenths);S.sanityBadges=c.sanity_badges||'compact';S.defaultRoot=c.default_root||null;S.filterPresets=c.filter_presets||{};S.thumbnailCache=c.thumbnail_cache||null;S.ringBufferRows=Math.max(1,Number(c.ringworld?.buffer_rows)||50);S.ringSouthBias=Math.max(1,Number(c.ringworld?.south_bias)||2);S.thumbWarmEnabled=c.thumbnail_warm?.enabled!==false;S.promptTranslator=c.prompt_translator||{model:'',type:'stable_diffusion',device:'default'};S.checkpointLibrary=c.checkpoint_library||null;const dot=$('#deleteOrphanThumbs');if(dot)dot.checked=S.thumbnailCache.delete_orphans_on_maintenance!==false;const rs=c.sanity||{};S.uncappedUnsanity=!!rs.uncapped_unsanity;[['#rasterThumb','thumbnail'],['#rasterThreshold','edge_threshold'],['#rasterLight','light_blur'],['#rasterMedium','medium_blur'],['#rasterHeavy','heavy_blur'],['#rasterGradeB','grade_b_largest_fraction']].forEach(([sel,key])=>{const el=$(sel);if(el&&rs[key]!==undefined)el.value=rs[key]});document.body.dataset.gridDetail=S.gridDetail;refreshPresetSelect();updateDefaultRootLabel();updateThumbnailCacheLabel()}catch(e){}
 // Restore an in-place server restart before falling back to the saved default scope.
 let restartState=null;try{restartState=JSON.parse(sessionStorage.getItem('n8vision.restartState')||'null');sessionStorage.removeItem('n8vision.restartState')}catch(e){}
 if(restartState?.recursive!==undefined)$('#recursive').checked=!!restartState.recursive;
 const restartRoot=restartState?.scopeRoot||restartState?.path;
 const startupBrowse=(!browseEverRequested&&restartRoot)?load(restartRoot,true,'startup/restart').then(()=>{if(restartState?.path&&pathInsideScope(restartState.path)&&canonPath(restartState.path)!==canonPath(S.path))focusCatalog(restartState.path,false,'restart-restore')}):((!browseEverRequested&&S.defaultRoot)?load(S.defaultRoot,true,'startup/default-root'):Promise.resolve());
 // Initial images get the network/DOM/DB ahead of optional menu discovery.
 gridWork.enqueue('startup-menus',async()=>{
  if(S.capabilities.processing){loadRefineRecipe();loadWorkshopFunctions();}
  S.refreshSubjectClassStatus?.();
  const archiveRootsReady=refreshArchiveRoots();
  const volumesReady=j('/api/roots').then(rr=>{
   $('#roots').innerHTML=rr.roots.map(x=>`<div class="root" data-p="${esc(x)}">${esc(x)}</div>`).join('');
   document.querySelectorAll('.root').forEach(x=>x.onclick=()=>browseOnly(x.dataset.p,'volume-browse'));
  }).catch(e=>console.warn('Volume list unavailable at startup',e));
  await Promise.allSettled([archiveRootsReady,volumesReady,refreshHealth(),refreshModels(true),refreshDiscovered()]);
  if(S.capabilities.inference)scheduleJobsPoll(1000);
 });
 await startupBrowse;
 gridWork.kick();
}
async function refreshHealth(){const h=await j('/api/health'),a=h.hardware?.accelerator||{};const hw=a.available?`<b>Accelerator:</b> ${esc(a.name||a.kind)} · ${esc(String(a.vram_gb??'?'))} GB · CUDA ${esc(String(a.cuda_build||'?'))}`:`<b>Accelerator:</b> CPU fallback${a.reason?`<br><span class="tiny">${esc(a.reason)}</span>`:''}`;$('#mvStatus').innerHTML=hw+'<br><br>'+h.providers.map(p=>`${p.installed?'✓':'○'} ${esc(p.name)}<br><span class="tiny">${esc(p.detail)}</span>`).join('<br>')}
async function refreshArchiveRoots(){
 try{const r=await j('/api/archive-roots');S.archiveRoots=r.roots||[];renderArchiveRoots();updateScanButton()}catch(e){S.archiveRoots=[];renderArchiveRoots()}
}
// I.2q: A root switch consumes the last completed catalog immediately. A new
// filesystem verification is a separate transaction and never owns the viewport.
const rootCatalogs=new Map(),rootLastLook=new Map();
function rootCatalogKey(path,recursive){return canonPath(path)+'|'+(recursive?'recursive':'direct')}
function rememberRootCatalog(){
 if(S.mobile||!S.scopeRoot||!S._rootBrowseComplete)return;
 const key=rootCatalogKey(S.scopeRoot,S.catalogRecursive),anchor=topLeftGridPath();
 rootCatalogs.set(key,{path:S.scopeRoot,parent:S.parent,files:S.files,dirs:S.scopeRootDirs,recursive:S.catalogRecursive});
 if(anchor)rootLastLook.set(key,anchor);
}
function restoreRootCatalog(entry){
 // Retire any in-flight browse before it can commit a packet to the new view.
 browseGeneration++;if(browseController)browseController.abort();browseController=null;stopBrowseHeartbeat();
 S._rootBrowseComplete=true;S.selected.clear();S.semantic=null;S.compare=null;S.path=entry.path;S.parent=entry.parent;
 S.files=entry.files;S.dirs=entry.dirs;S.scopeRoot=entry.path;
 S.catalogRecursive=entry.recursive;S.scopeRecursive=entry.recursive;
 S.scopeRootDirs=entry.dirs;S.scopeSelections.clear();S.scopeSelectionAnchor=null;
 S._n8LazyRenames=new Set();
 const v=S.virtualGrid;v.rowReady=new Map();v.prepGeneration++;v.archiveWarmCursor=0;
 if(v.archiveWarmTimer){(window.cancelIdleCallback||clearTimeout)(v.archiveWarmTimer);v.archiveWarmTimer=0}
 if(v.scoutDecayTimer){clearTimeout(v.scoutDecayTimer);v.scoutDecayTimer=0}
 v.cursor=0;invalidateRingLayout();$('#path').value=S.path;
 $('#recursive').checked=entry.recursive;renderScopeFolders();setTree(S.treeOpen);updateScanButton();renderArchiveRoots();
 render();$('#status').textContent=`Browsing cached catalog · ${S.files.length.toLocaleString()} known files`;
}
async function switchArchiveRoot(path){
 if(pagedBrowse()){$('#recursive').checked=true;return load(path,true,'paged-archive-root')}
 const key=rootCatalogKey(path,true),entry=rootCatalogs.get(key);
 if(!entry){$('#recursive').checked=true;return load(path,true,'archive-root')}
 rememberRootCatalog();restoreRootCatalog(entry);
 // The verifier owns a transaction, not the current grid. Changes become
 // available on the next root visit or explicit redraw, never via a rehome.
 verifyRootCatalog(entry,key);
}
// I.2t: root visits and idle polling consume additions without a browse transaction.
const noticeCursors=new Map();let noticeBusy=false;
async function verifyRootCatalog(entry,key){
 if(noticeBusy)return;noticeBusy=true;
 try{
  const packet=await j(`/api/browse/new?path=${enc(entry.path)}&recursive=${entry.recursive}&since=${noticeCursors.get(key)?.cursor||0}&epoch=${enc(noticeCursors.get(key)?.epoch||'')}`);
  const current=rootCatalogs.get(key);if(!current)return;
  const active=S._rootBrowseComplete&&rootCatalogKey(S.scopeRoot,S.catalogRecursive)===key;
  if(active&&!S.viewer&&Number(packet.observation_revision||0)>Number(String(S.obsRevision).split('-')[0]))refreshJobs();
  const known=new Set(current.files.map(f=>canonPath(f.path))),added=[];
  for(const f of packet.files||[])if(!known.has(canonPath(f.path))){known.add(canonPath(f.path));current.files.push(f);added.push(f)}
  noticeCursors.set(key,{cursor:packet.cursor,epoch:packet.epoch});
  if(added.length&&active){
   // Preserve the packed rows and mounted cards. New visible records go at the tail.
   if(S.files!==current.files)S.files.push(...added);
   const v=S.virtualGrid,old=v.files,oldPaths=new Set(old.map(f=>canonPath(f.path)));
   const tail=visibleFiles().filter(f=>!oldPaths.has(canonPath(f.path)));
   if(tail.length){
    const layout=virtualGridLayout(old),rows=visualRows(tail,Math.max(1,layout.gw-layout.gap*2),layout.thumb,layout.gap);
    old.push(...tail);layout.rows.push(...rows);v.rows=layout.rows;
   }
   refreshSelectionUI();renderScopeFolders();updateArchiveNavigator();prepareNeighborhood();
   if(v.files.length===tail.length)paintRing();
   $('#status').textContent=`New Noticer · ${added.length} new images`;
  }
 }catch(e){console.warn('New Noticer unavailable',e)}finally{noticeBusy=false}
}
let exploreTreeBusy=false;
async function refreshExploreTree(){
 const root=S.scopeRoot||S.path;
 if(exploreTreeBusy||!root||!S._rootBrowseComplete)return;
 exploreTreeBusy=true;
 try{
  const previous=S.exploreTree,revision=previous&&canonPath(previous.root)===canonPath(root)?previous.revision:'';
  const tree=await j(`/api/directory-tree?path=${enc(root)}&since=${enc(revision)}`);
  if(canonPath(S.scopeRoot||S.path)!==canonPath(root)||tree.incomplete||!Array.isArray(tree.paths))return;
  S.exploreTree=tree;folderMenuIndex=null;renderScopeFolders();
 }catch(error){console.warn('Folder tree refresh unavailable',error)}finally{exploreTreeBusy=false}
}
async function noticeSweep(){
 try{await refreshExploreTree();if(S.viewer||S.mobile)return;for(const [key,entry] of rootCatalogs)await verifyRootCatalog(entry,key)}
 finally{setTimeout(noticeSweep,5000)}
}
setTimeout(noticeSweep,5000);
function renderArchiveRoots(){const box=$('#archiveRoots');if(!box)return;if(!S.archiveRoots.length){box.innerHTML='<span class="tiny">No archive roots yet.</span>';return}const names=S.archiveRoots.map(p=>{const q=String(p).replace(/[\\/]+$/,'');return {path:p,name:q.split(/[\\/]/).pop()||p}}),counts=new Map();for(const x of names)counts.set(x.name,(counts.get(x.name)||0)+1);box.innerHTML=names.map(x=>`<button type="button" class="archiveRootLink ${canonPath(S.scopeRoot)===canonPath(x.path)?'active':''}" data-p="${esc(x.path)}" title="${esc(x.path)}">${esc(counts.get(x.name)>1?x.path:x.name)}</button>`).join('');box.querySelectorAll('.archiveRootLink').forEach(b=>b.onclick=()=>switchArchiveRoot(b.dataset.p))}
function isVolumeRoot(path){const p=String(path||'').replace(/\//g,'\\');return /^[A-Za-z]:\\?$/.test(p)||p==='/' }
async function browseOnly(path,reason='browse-only'){const prior=$('#recursive').checked;$('#recursive').checked=false;try{return await load(path,false,reason)}finally{$('#recursive').checked=prior;updateScanButton()}}
function updateScanButton(){const b=$('#goBtn');if(!b)return;const p=$('#path').value||S.path||'';const covered=(S.archiveRoots||[]).some(r=>{const a=canonPath(r),q=canonPath(p);return q===a||q.startsWith(a+'\\')});b.textContent='Scan';b.disabled=isVolumeRoot(p)||covered;b.title=isVolumeRoot(p)?'Whole-volume archive roots are config-file-only':covered?'This folder is already inside an archive root':'Adopt this folder as an archive root and recursively scan it'}
async function scanCurrent(){const p=$('#path').value||S.path;if(!p)return;if(isVolumeRoot(p))return alert('Whole-volume archive roots are deliberately config-file-only. Add this drive to archive_roots in data/n8vision_config.json if you really mean it.');try{const r=await post('/api/archive-roots/scan',{path:p});await refreshArchiveRoots();$('#recursive').checked=true;await load(r.root||p,true,'archive-scan');const absorbed=(r.absorbed||[]).length;$('#status').textContent=r.already_covered?'Already covered by '+(r.root||p):`Archive root committed${absorbed?` · absorbed ${absorbed} child root${absorbed===1?'':'s'}`:''}`;}catch(e){alert(e.message)}}
function setTree(open){S.treeOpen=open;$('#locationTree').classList.toggle('collapsed',!open);$('#locationBar').textContent=S.path?`${S.path} ${open?'▴':'▾'}`:`Choose location ${open?'▴':'▾'}`}
let browseGeneration=0,browseController=null,browseHeartbeat=null,browseEverRequested=false;
function browseTx(){return `${Date.now().toString(36)}-${(++browseGeneration).toString(36)}-${Math.random().toString(36).slice(2,10)}`}
async function browsePulse(tx){
 try{await j('/api/browse/heartbeat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tx})})}catch(e){}
}
function startBrowseHeartbeat(tx){
 if(browseHeartbeat)clearInterval(browseHeartbeat);
 browseHeartbeat=setInterval(()=>browsePulse(tx),10000);
}
function stopBrowseHeartbeat(){if(browseHeartbeat){clearInterval(browseHeartbeat);browseHeartbeat=null}}
async function signalBrowseStable(tx){
 // P.28: "stable" means the virtualizer proved that a non-empty logical result has
 // actually mounted visible cards. Two paint frames alone were a false positive.
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 const v=S.virtualGrid,g=$('#grid'),logical=(v.files||[]).length,mounted=g?g.querySelectorAll('.card').length:0;
 if(S.imageGridEnabled&&logical>0&&mounted===0){
  console.error(`[N8Vision] Grid NOT stable · tx=${tx} · logical=${logical} · mounted=0 · scrollTop=${g?.scrollTop||0} · client=${g?.clientWidth||0}x${g?.clientHeight||0} · scrollHeight=${g?.scrollHeight||0}`);
  $('#status').textContent='Grid render failed — browse data retained';
  return false;
 }
 console.info(`[N8Vision] Grid stable proof · tx=${tx} · logical=${logical} · mounted=${mounted} · scrollTop=${g?.scrollTop||0} · scrollHeight=${g?.scrollHeight||0}`);
 try{await j('/api/browse/stable',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tx})});launchVerifyArmed=true;scheduleLaunchVerification(5000);return true}catch(e){console.warn('Browse stabilization acknowledgement failed',e);return false}
}

function canonPath(p){return String(p||'').replace(/\//g,'\\').replace(/\\+$/,'').toLowerCase()}
function pathInsideScope(path){
 if(!S.scopeRoot||!S.scopeRecursive)return false;
 const p=canonPath(path),r=canonPath(S.scopeRoot);return p===r||p.startsWith(r+'\\')
}
function immediateCatalogDirs(path){
 const base=String(path||'').replace(/[\\\/]+$/,''),cbase=canonPath(base),seen=new Map();
 if(S.exploreTree&&canonPath(S.exploreTree.root)===canonPath(S.scopeRoot)){
  for(const p of S.exploreTree.paths){const cp=canonPath(p);if(!cp.startsWith(cbase+'\\'))continue;const rest=p.slice(base.length+1);if(!rest.includes('\\'))seen.set(cp,{path:p,name:rest});}
  return [...seen.values()].sort((a,b)=>a.name.localeCompare(b.name));
 }
 if(cbase===canonPath(S.scopeRoot))for(const d of(S.scopeRootDirs||[]))seen.set(canonPath(d.path),d);
 for(const f of S.files){
  const fp=String(f.path||'').replace(/\//g,'\\'),cfp=fp.toLowerCase();
  if(!cfp.startsWith(cbase+'\\'))continue;
  const rest=fp.slice(base.length+1),cut=rest.indexOf('\\');if(cut<=0)continue;
  const name=rest.slice(0,cut),p=base+'\\'+name;seen.set(canonPath(p),{name,path:p})
 }
 return [...seen.values()].sort((a,b)=>a.name.localeCompare(b.name,undefined,{sensitivity:'base'}))
}
let folderMenuIndex=null,folderMenuVersion=0;
function renderScopeFolders(){if(S._rootBrowseComplete)folderMenuIndex=null;const version=++folderMenuVersion;gridWork.enqueue('folder-menu',()=>buildScopeFolderMenu(version));}
async function buildScopeFolderMenu(version){
 const box=$('#folders');if(!box)return;
 const root=String(S.scopeRoot||S.path||'').replace(/[\\/]+$/,''),cr=canonPath(root),files=S.files;
 if(!folderMenuIndex||folderMenuIndex.root!==cr||folderMenuIndex.files!==files||folderMenuIndex.scanned>files.length)folderMenuIndex={root:cr,files,scanned:0,dirs:new Map()};
 const index=folderMenuIndex;
 const current=()=>version===folderMenuVersion&&index===folderMenuIndex&&files===S.files&&canonPath(S.scopeRoot||S.path||'')===cr;
 const yieldUI=()=>new Promise(resolve=>setTimeout(resolve,0));
 const tree=S.exploreTree&&canonPath(S.exploreTree.root)===cr?S.exploreTree:null;
 if(tree){index.dirs=new Map(tree.paths.map(path=>[canonPath(path),path]));index.scanned=files.length;}
 else for(const d of S.scopeRootDirs||[])index.dirs.set(canonPath(d.path),d.path);
 let slice=performance.now();
 while(index.scanned<files.length){
  let dir=String(files[index.scanned++].path||'').replace(/\//g,'\\').replace(/\\[^\\]+$/,'');
  while(dir&&canonPath(dir)!==cr&&canonPath(dir).startsWith(cr+'\\')){index.dirs.set(canonPath(dir),dir);const up=dir.replace(/\\[^\\]+$/,'');if(up===dir)break;dir=up;}
  if(performance.now()-slice>6){await yieldUI();if(!current())return;slice=performance.now();}
 }
 if(!current())return;
 const rows=[...index.dirs.values()].sort((a,b)=>a.localeCompare(b,undefined,{sensitivity:'base'}));
 const fragment=document.createDocumentFragment();
 for(let i=0;i<rows.length;i++){
  const path=rows[i],rel=path.slice(root.length).replace(/^\\+/,''),depth=rel?rel.split('\\').length-1:0,name=path.replace(/[\\/]+$/,'').split(/[\\/]/).pop()||path;
  const node=document.createElement('div');node.className='folder';node.dataset.p=path;node.style.paddingLeft=(5+depth*14)+'px';node.title=path;node.textContent=name;fragment.append(node);
  if(i%100===99){await yieldUI();if(!current())return;}
 }
 if(!current())return;box.replaceChildren(fragment);bindFolderScopes();
}

function renderFolderSelection(){document.querySelectorAll('#folders .folder').forEach(x=>x.classList.toggle('scopeSelected',S.scopeSelections.has(canonPath(x.dataset.p))))}
function bindFolderScopes(){const rows=[...document.querySelectorAll('#folders .folder')];rows.forEach((x,i)=>x.onclick=e=>{e.preventDefault();e.stopPropagation();const key=canonPath(x.dataset.p),multi=e.ctrlKey||e.metaKey||S.softCtrl,range=e.shiftKey||S.softShift;if(range&&S.scopeSelectionAnchor!==null){const a=Math.min(S.scopeSelectionAnchor,i),b=Math.max(S.scopeSelectionAnchor,i);if(!multi)S.scopeSelections.clear();for(let n=a;n<=b;n++)S.scopeSelections.add(canonPath(rows[n].dataset.p));}else if(multi){if(S.scopeSelections.has(key))S.scopeSelections.delete(key);else S.scopeSelections.add(key);S.scopeSelectionAnchor=i;}else{S.scopeSelections.clear();S.scopeSelections.add(key);S.scopeSelectionAnchor=i;}renderFolderSelection();render();$('#status').textContent=`Graph bounded by ${S.scopeSelections.size} folder${S.scopeSelections.size===1?'':'s'} · ${visibleFiles().length.toLocaleString()} shown`;});renderFolderSelection()}
function focusCatalog(path,commit=false,reason='catalog-focus'){if(pagedBrowse())return false;gridActivity('catalog-focus');
 if(!pathInsideScope(path))return false;
 const p=String(path).replace(/[\\\/]+$/,'');S.selected.clear();S.semantic=null;S.compare=null;S.path=p;
 const cp=canonPath(p),cr=canonPath(S.scopeRoot);S.parent=cp===cr?null:p.replace(/[\\\/][^\\\/]+$/,'');
 S.dirs=immediateCatalogDirs(p);$('#path').value=p;
 renderScopeFolders();
 setTree(S.treeOpen);const grid=$('#grid');if(grid)grid.scrollTop=0;render();
 $('#status').textContent=`Focused · ${visibleFiles().length.toLocaleString()} shown of ${S.files.length.toLocaleString()} catalogued`;
 console.info(`[N8Vision] Catalog focus · reason=${reason} · ${p} · no filesystem browse`);return true
}
function navigateTo(path,commit=false,reason='ui/navigation'){
 if(!pagedBrowse()&&pathInsideScope(path))return Promise.resolve(focusCatalog(path,commit,reason));
 return browseOnly(path,reason)
}

async function load(path,commit=false,reason='ui/navigation'){rememberRootCatalog();gridActivity('filesystem-browse');
 const previousMobileTx=S.mobileBrowseTx||'';if(pagedBrowse()||mobilePager){mobilePager?.close();mobilePager=null;rootCatalogs.clear();S.mobileNavigationPosition=0;S.mobileNavigationDirty=false;}
 browseEverRequested=true;
 const generation=browseGeneration+1,tx=browseTx();
 console.info(`[N8Vision] Browse request · tx=${tx} · reason=${reason} · path=${path} · recursive=${$('#recursive').checked}`);
 if(browseController)browseController.abort();
 const controller=new AbortController();browseController=controller;startBrowseHeartbeat(tx);
 $('#status').textContent='Opening location…';
 let d;
 try{d=await j(`/api/browse/start?path=${enc(path)}&recursive=${$('#recursive').checked}&tx=${enc(tx)}${S.mobile?'&mobile=true':S.desktopWindowed?'&windowed=true':''}&previous_tx=${enc(previousMobileTx)}`,{signal:controller.signal})}
 catch(e){if(e?.name==='AbortError')return;if(generation===browseGeneration){$('#status').textContent=`Browse failed — keeping ${S.path||'current location'}`;console.warn('Browse failed; navigation state preserved',path,e);stopBrowseHeartbeat();S._rootBrowseComplete=true;gridWork.kick()}return}
 if(generation!==browseGeneration)return;
 if(d.browse_tx!==tx){console.warn('Discarded mismatched browse transaction',d.browse_tx,tx);return}
 // Commit the location when the bounded start packet arrives. Files then arrive as 500-file bites.
 S.gridHasPainted=false;S._rootBrowseComplete=false;S.selectionRequest=(S.selectionRequest||0)+1;S.selected.clear();S.selectionAnchor=null;S.selectionAnchorMeta=null;S.semantic=null;S.compare=null;S.path=d.path;S.parent=d.parent;S.files=[];S.dirs=d.directories||[];S.virtualGrid.rowReady=new Map();S.virtualGrid.prepGeneration++;S.virtualGrid.archiveWarmCursor=0;S.virtualGrid.scoutDir=0;S.virtualGrid.scoutExtra=0;S.virtualGrid.scoutLastMove=0;if(S.virtualGrid.scoutDecayTimer){clearTimeout(S.virtualGrid.scoutDecayTimer);S.virtualGrid.scoutDecayTimer=0;}if(S.virtualGrid.archiveWarmTimer){(window.cancelIdleCallback||clearTimeout)(S.virtualGrid.archiveWarmTimer);S.virtualGrid.archiveWarmTimer=0;}
 S.scopeRoot=d.path;S.catalogRecursive=!!d.recursive;S.scopeRecursive=!!$('#recursive').checked;S.scopeRootDirs=(d.directories||[]).slice();S.scopeSelections.clear();S.scopeSelectionAnchor=null;
 $('#path').value=S.path;renderScopeFolders();setTree(S.treeOpen);updateScanButton();renderArchiveRoots();
 const grid=$('#grid');if(grid)grid.scrollTop=0;render();
 requestAnimationFrame(()=>{if(generation===browseGeneration)paintRing()});
 if(pagedBrowse()){
  $('#mobilePagingInfo').hidden=false;
  const pager=new MobileArchiveWindow(async index=>{
   const packet=await j(`/api/browse/chunk?tx=${enc(tx)}&index=${index}`,{signal:controller.signal});
   if(packet.browse_tx!==tx)throw new Error('Browse transaction changed');return packet;
  },{windowSize:S.mobile?1500:S.desktopWindowSize,fixedWindow:!S.mobile});mobilePager=pager;S.mobileBrowseTx=tx;
  try{
   const position=S.windowRestorePosition||0;S.windowRestorePosition=0;const snapshot=await (S.mobile?pager.focus(position):pager.initial(position));if(!snapshot||generation!==browseGeneration||mobilePager!==pager)return;
   await applyMobileSnapshot(snapshot,S.windowRestoreAnchor||null,pager);S.windowRestoreAnchor=null;
   // First 500 are mounted before filling the configured desktop metadata zone.
   if(!S.mobile){
    await new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0)));
    if(generation!==browseGeneration||mobilePager!==pager)return;
    const expanded=await pager.focus(position);
    if(generation!==browseGeneration||mobilePager!==pager)return;
    if(expanded?.changed){const anchor=S.virtualGrid.rows[S.virtualGrid.cursor]?.[0]?.f?.path;await applyMobileSnapshot(expanded,anchor,pager)}
   }

   S._rootBrowseComplete=true;gridWork.kick();$('#status').textContent=S.mobile?'Mobile archive ready':'Windowed archive ready';
   const stable=await signalBrowseStable(tx);if(stable)stopBrowseHeartbeat();
  }catch(e){if(e.name!=='AbortError'){$('#status').textContent='Mobile browse failed: '+e.message;console.warn(e)}stopBrowseHeartbeat();if(generation===browseGeneration){S._rootBrowseComplete=true;gridWork.kick()}}
  return;
 }
 let index=0,complete=false;
 try{
  while(!complete&&generation===browseGeneration){
   const packet=await j(`/api/browse/chunk?tx=${enc(tx)}&index=${index}`,{signal:controller.signal});
   if(generation!==browseGeneration)return;if(packet.browse_tx!==tx)continue;
   if(packet.error)throw new Error(`Browse preparation failed: ${packet.error}`);
   if(packet.files?.length){S.files.push(...packet.files);index++;render();renderScopeFolders();if(index===1)requestAnimationFrame(()=>paintRing());await new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0)));if(generation!==browseGeneration)return;}
   complete=!!packet.complete;
   if(complete)noticeCursors.set(rootCatalogKey(S.scopeRoot,S.catalogRecursive),{cursor:packet.notice_cursor,epoch:packet.notice_epoch});
   $('#status').textContent=complete?`Loaded ${S.files.length.toLocaleString()}`:`Loading… ${S.files.length.toLocaleString()} prepared`;
  }
 }catch(e){if(e?.name==='AbortError')return;if(generation===browseGeneration){$('#status').textContent=`Browse interrupted at ${S.files.length.toLocaleString()} files`;console.warn('Chunk browse interrupted',e);stopBrowseHeartbeat();S._rootBrowseComplete=true;gridWork.kick()}return}
 finally{if(generation===browseGeneration&&browseController===controller)browseController=null}
 if(generation!==browseGeneration)return;
 warmArchiveTail();S._rootBrowseComplete=true;gridWork.kick();$('#status').textContent='Ready';rootCatalogs.set(rootCatalogKey(S.scopeRoot,S.catalogRecursive),{path:S.scopeRoot,parent:S.parent,files:S.files,dirs:S.scopeRootDirs,recursive:S.catalogRecursive});console.info(`[N8Vision] Chunk browse complete · tx=${tx} · files=${S.files.length} · bites=${index}`);
 const stable=await signalBrowseStable(tx);if(stable)stopBrowseHeartbeat();if(generation!==browseGeneration)return;if(stable)startQuality()
}
function matchedObservation(f,q,min){if(!q)return true;return(f.observations||[]).some(o=>conceptKey(o.concept).includes(conceptKey(q))&&o.confidence>=min)}
function isSubjectObservation(o){if(!o)return false;let g=o.geometry;try{g=typeof g==='string'?JSON.parse(g):g}catch(_){g=null}if(o.subject_role===false||g?.subject_role===false)return false;return !!(o.subject_role||g?.subject_role||g?.subject_pipeline||o.provider==='subject-intelligence')}
// Derived archive state, never a detector badge or a training confirmation.
function isSubjectified(f){const subjects=(f.observations||[]).filter(o=>Number(o.confidence)>0&&isSubjectObservation(o));return subjects.length>0&&subjects.every(o=>{const label=String(o.concept||'').trim().toLowerCase();let g=o.geometry;try{g=typeof g==='string'?JSON.parse(g):g}catch(_){g=null}return !!label&&!['unknown','unidentified','unidentified subject'].includes(label)&&g?.instance_separation!=='unresolved'&&!(Number(g?.separation_conflict_pixels)>0)})}
const subjectifiedFeature={concept:'subjectified',provider:'archive-status',model:'subjectified',kind:'status'};
function subjectificationTargets(){const filter=[...S.magnets.values()].find(m=>m.key==='archive-status\u001fsubjectified');return S.files.filter(f=>S.selected.has(f.path)&&(!filter||filter.mode==='0'||(filter.mode==='-'?!isSubjectified(f):compareCount(isSubjectified(f)?1:0,filter.op,filter.count)))).map(f=>f.path)}
function recognitionNote(o){const r=geometryOf(o)?.trained_class_review;return !r?'':r.accepted?(r.label===o.concept?' · learned':' → '+r.label+' (learned draft)'):' · learned: uncertain'}
function observationLabel(o){const label=String(o?.concept||'');return isSubjectObservation(o)?'Subject — '+(label.toLowerCase()==='unidentified subject'?'Unidentified':label):label}
function subjectSeparationNote(o){let g=o?.geometry;try{g=typeof g==='string'?JSON.parse(g):g}catch(_){return ''}if(g?.instance_separation==='unresolved')return 'Split unresolved — review mask';if(Number(g?.separation_conflict_pixels)>0)return 'Split masks still overlap — review';if(g?.instance_separation==='sam')return 'YOLAST + SAM split (draft)';return ''}
function observationConfidence(o){let g=o?.geometry;try{g=typeof g==='string'?JSON.parse(g):g}catch(_){g=null}return isSubjectObservation(o)&&g?.name_accepted&&Number.isFinite(Number(g.name_confidence))?Number(g.name_confidence):Number(o?.confidence)||0}
const conceptPlurals={hands:'hand',feet:'foot',arms:'arm',legs:'leg',eyes:'eye',ears:'ear',fingers:'finger',toes:'toe',heads:'head',faces:'face',women:'woman',men:'man',people:'person'};
function conceptKey(value){const key=String(value||'').toLowerCase().trim().replace(/\s+/g,' ');return conceptPlurals[key]||key}
function obsKey(o){if(o.provider==='archive-status'&&o.model==='subjectified')return 'archive-status\u001fsubjectified';return (o.kind==='quality'||(conceptKey(o.concept)==='quality'&&String(o.provider).startsWith('yuan-iqf')))||String(o.provider).startsWith('native-raster-sanity')?`${o.provider}\u001f${o.model}\u001f${conceptKey(o.concept)}`:`feature\u001f${conceptKey(o.concept)}`}
function observationGroups(f,splitSubjects=false){const m=new Map();for(const o of(f.observations||[])){if(o.kind==='receipt'||o.confidence<=0)continue;const k=obsKey(o)+(splitSubjects&&isSubjectObservation(o)?"\u001fsubject":""),g=m.get(k)||{key:k,subject_role:isSubjectObservation(o),concept:conceptKey(o.concept),provider:o.provider,model:o.model,count:0,confidence:0,items:[]};if(o.kind==='bbox'||o.kind==='mask'){if(!o.presentation_hidden)g.count++}else g.nonlocalized=true;const confidence=splitSubjects?observationConfidence(o):Number(o.confidence)||0;if(confidence>=g.confidence){g.provider=o.provider;g.model=o.model;g.confidence=confidence}g.items.push(o);m.set(k,g)}for(const g of m.values())if(!g.count&&g.nonlocalized)g.count=1;return m}
function observationAttribution(g){return [...new Set((g.items||[g]).map(o=>`${o.provider} · ${o.model} (${o.concept})`))].join('\n')}
function groupedDiscovered(){const groups=new Map();for(const t of S.discovered){const key=obsKey(t),g=groups.get(key)||{...t,key,concept:conceptKey(t.concept),items:[]};g.items.push(t);groups.set(key,g)}const statusKey=obsKey(subjectifiedFeature);groups.set(statusKey,{...subjectifiedFeature,key:statusKey,items:[subjectifiedFeature]});return [...groups.values()]}
function compareCount(n,op,v){if(v===''||v===null||v===undefined)return n>0;v=Number(v);if(!Number.isFinite(v))return n>0;return op==='='?n===v:op==='≠'?n!==v:op==='<'?n<v:op==='≤'?n<=v:op==='>'?n>v:n>=v}
function passesMagnets(f){
 const active=[...S.magnets.values()].filter(m=>m.mode!=='0');if(!active.length)return true;const groups=active.every(m=>m.key==='archive-status\u001fsubjectified')?new Map():observationGroups(f);
 // Sanity failure modes are mutually exclusive by design. Multiple positive Sanity magnets therefore mean
 // "show any of these failures", while all unrelated magnets retain the refrigerator's normal AND semantics.
 const sanityWanted=active.filter(m=>m.mode==='+'&&[...groups.values(),...[]]!==null&&String(m.key).startsWith('native-raster-sanity\u001f'));
 if(sanityWanted.length){
  let any=false;
  for(const m of sanityWanted){const g=groups.get(m.key),n=m.key==='archive-status\u001fsubjectified'?(isSubjectified(f)?1:0):(g?g.count:0);if(compareCount(n,m.op,m.count)){any=true;break}}
  if(!any)return false;
 }
 for(const m of active){
  if(sanityWanted.includes(m))continue;
  const g=groups.get(m.key),n=m.key==='archive-status\u001fsubjectified'?(isSubjectified(f)?1:0):(g?g.count:0);
  if(m.mode==='-'&&n>0)return false;
  if(m.mode==='+'&&!compareCount(n,m.op,m.count))return false;
 }
 return true
}
function fileQuality(f){const s=qualityScore(f);return s===''?null:Number(s)}
function applySort(fs){
 if(S.sortKey==='none'){
  // Comparison tools may filter membership, but Filesystem restores catalog order.
  if(S.semantic||S.compare){const position=new Map(S.files.map((f,i)=>[f.path,i]));fs=[...fs].sort((a,b)=>(position.get(a.path)??Infinity)-(position.get(b.path)??Infinity))}
  return S.sortDir==='desc'?[...fs].reverse():fs;
 }
 const dir=S.sortDir==='asc'?1:-1;
 const scores=new Map((S.compare?.results||[]).map(x=>[x.path,Number(x.score)]));
 const val=f=>{
  if(S.sortKey==='quality')return fileQuality(f);
  if(S.sortKey==='filename')return f.name.toLowerCase();
  if(S.sortKey==='uniqueness'&&S.compare&&S.compare.kind==='unique')return scores.get(f.path)??null;
  if(S.sortKey==='similarity'&&S.compare&&S.compare.kind==='similar')return scores.get(f.path)??null;
  return null;
 };
 return [...fs].sort((a,b)=>{
  const av=val(a),bv=val(b);
  if(av===null&&bv===null)return a.name.localeCompare(b.name);
  if(av===null)return 1;if(bv===null)return -1;
  if(typeof av==='string')return dir*av.localeCompare(bv);
  return dir*(av-bv);
 });
}
function visibleFiles({ignoreCompare=false}={}){const q=$('#search').value.trim().toLowerCase(),min=Number($('#minConfidence').value),scope=canonPath(S.scopeRoot),roots=[...(S.scopeSelections||new Set())].map(canonPath);let fs=S.files.filter(f=>{const fp=canonPath(f.path),dir=fp.replace(/\\[^\\]+$/,'');let inFocus=true;if(roots.length)inFocus=roots.some(r=>S.scopeRecursive?(dir===r||dir.startsWith(r+'\\')):dir===r);else if(S.scopeRecursive&&scope)inFocus=fp.startsWith(scope+'\\')||fp===scope;return inFocus&&(!q||f.name.toLowerCase().includes(q)||matchedObservation(f,q,min))&&passesMagnets(f)});if(S.semantic){const rank=new Map(S.semantic.map((x,i)=>[x.path,{i,score:x.score}]));fs=fs.filter(f=>rank.has(f.path)).sort((a,b)=>rank.get(a.path).i-rank.get(b.path).i)}if(S.compare&&!ignoreCompare){const rank=new Map(S.compare.results.map((x,i)=>[x.path,{i,score:x.score}]));if(S.compare.kind==='similar'||S.compare.kind==='duplicates')fs=fs.filter(f=>rank.has(f.path)).sort((a,b)=>rank.get(a.path).i-rank.get(b.path).i);else fs.sort((a,b)=>(rank.get(a.path)?.i??1e9)-(rank.get(b.path)?.i??1e9))}return applySort(fs)}
function detectorColor(provider,model){provider=String(provider||'');model=String(model||'');model=model.replace(/#conf=[0-9.]+$/,'');if(provider==='ultralytics-world')model=model.replace(/#vocab=[^#]+$/,'');let h=2166136261;for(const c of(provider+'|'+model)){h^=c.charCodeAt(0);h=Math.imul(h,16777619)}return `hsl(${Math.abs(h)%360} 78% 62%)`}
function humanObservation(provider){return /^(human|user|manual)(?:$|[-_:])/i.test(String(provider||''))}
function observationTextStyle(provider,model){return humanObservation(provider)?'class="humanObservation"':`style="color:${detectorColor(provider,model)}"`}
function sanityMetricBadges(f){if(S.sanityBadges!=='verbose')return'';const r=(f.observations||[]).find(o=>o.provider==='native-raster-sanity'&&o.kind==='receipt'&&o.geometry);if(!r)return'';let g;try{g=typeof r.geometry==='string'?JSON.parse(r.geometry):r.geometry}catch{return''}const L=g?.levels;if(!Array.isArray(L)||L.length<4)return'';const names=['Raw','Light','Medium','Heavy'],parts=[];for(let i=0;i<4;i++){const x=L[i]||{};parts.push(`<span class="badge sanityMetric" title="Raster Sanity ${names[i]} edge density">RS ${names[i]} ${(Number(x.density||0)*100).toFixed(2)}%</span>`)}const light=L[1]||{};parts.push(`<span class="badge sanityMetric" title="Light-layer occupied grid cells">RS L-occ ${(Number(light.occupancy||0)*100).toFixed(1)}%</span>`);parts.push(`<span class="badge sanityMetric" title="Largest light-layer component as fraction of surviving edges">RS L-max ${(Number(light.largest_fraction||0)*100).toFixed(2)}%</span>`);parts.push(`<span class="badge sanityMetric" title="Light-layer connected components">RS L-comp ${Number(light.components||0)}</span>`);return parts.join('')}
function badges(f){const normal=[...observationGroups(f,true).values()].sort((a,b)=>b.confidence-a.confidence).map(g=>{const value=g.provider==='yuan-iqf-v1'?`${(g.confidence*10).toFixed(1)}/10`:`${(g.confidence*100).toFixed(0)}%`;return `<span class="badge ${humanObservation(g.provider)?'humanObservation':''}" style="${humanObservation(g.provider)?'':`color:${detectorColor(g.provider,g.model)}`}" title="${esc(observationAttribution(g))}">${esc(observationLabel(g))} ${value}${g.count>1?`<span class="mult">×${g.count}</span>`:''}</span>`}).join('');return normal+sanityMetricBadges(f)}
function gridGeometryLayers(f){if(!S.boxes&&!S.masks)return'';const rev=encodeURIComponent(S.obsRevision||0),p=enc(f.path);return `${S.masks?`<img class="gridGeomLayer gridMaskLayer" loading="lazy" src="/api/grid-overlay?path=${p}&kind=masks&rev=${rev}">`:''}${S.boxes?`<img class="gridGeomLayer gridBoxLayer" loading="lazy" src="/api/grid-overlay?path=${p}&kind=boxes&rev=${rev}">`:''}`}
function geometrySvg(f){if(!S.boxes&&!S.masks)return'';const items=(f.observations||[]).filter(o=>(o.kind==='bbox'||o.kind==='mask')&&o.geometry&&!o.presentation_hidden);if(!items.length)return'';let shapes='',source=null;for(const o of items){let g;try{g=typeof o.geometry==='string'?JSON.parse(o.geometry):o.geometry}catch{continue}if(!source&&g.source_size&&g.source_size.length>=2)source=g.source_size.map(Number);const color=detectorColor(o.provider,o.model);if(S.masks&&g.polygon&&g.polygon.length){const pts=g.polygon.map(p=>`${Number(p[0]).toFixed(1)},${Number(p[1]).toFixed(1)}`).join(' ');shapes+=`<polygon class="maskPoly" points="${pts}" fill="${color}" stroke="${color}"></polygon>`}if(S.masks&&g.mask_rle&&g.mask_size&&g.bbox){const mw=Number(g.mask_size[0]),ox=Number(g.bbox[0]),oy=Number(g.bbox[1]);let d='';for(let ri=0;ri<g.mask_rle.length;ri+=2){let s=Number(g.mask_rle[ri]),n=Number(g.mask_rle[ri+1]);while(n>0){const yy=Math.floor(s/mw),xx=s%mw,take=Math.min(n,mw-xx);d+=`M${ox+xx} ${oy+yy}h${take}v1h-${take}z`;s+=take;n-=take}}shapes+=`<path class="maskPoly" d="${d}" fill="${color}" stroke="none"></path>`}if(S.boxes&&g.bbox&&g.bbox.length>=4){const [x1,y1,x2,y2]=g.bbox.map(Number);shapes+=`<rect class="bbox" x="${x1}" y="${y1}" width="${Math.max(0,x2-x1)}" height="${Math.max(0,y2-y1)}" stroke="${color}"></rect><text class="geomLabel" x="${x1+3}" y="${Math.max(12,y1+12)}" style="fill:${color}">${esc(observationLabel(o))} ${Math.round(observationConfidence(o)*100)}%</text>`}}const vb=source?` viewBox="0 0 ${source[0]} ${source[1]}"`:'';return shapes?`<svg class="geomOverlay"${vb} preserveAspectRatio="xMidYMid meet">${shapes}</svg>`:''}
function syncGeometryViews(){document.querySelectorAll('.thumb').forEach(t=>{const img=t.querySelector('img'),svg=t.querySelector('svg');if(!img||!svg||svg.hasAttribute('viewBox'))return;const full=new Image();full.onload=()=>{if(full.naturalWidth&&full.naturalHeight)svg.setAttribute('viewBox',`0 0 ${full.naturalWidth} ${full.naturalHeight}`)};const card=t.closest('.card');if(card)full.src=`/api/file?path=${enc(card.dataset.p)}`})}
function viewerGeometry(f){const oldB=S.boxes,oldM=S.masks;S.boxes=true;S.masks=true;const out=geometrySvg(f);S.boxes=oldB;S.masks=oldM;return out}
function viewerObsId(o,i){return `obs-${i}`}
async function synchronizeRecognitionPaths(paths){
 const unique=[...new Set(paths)];
 for(let start=0;start<unique.length;start+=100){const r=await post('/api/observations',{paths:unique.slice(start,start+100)});syncRecognitionMetadata(r.observations||{},{files:S.files,catalogs:rootCatalogs.values(),pager:mobilePager});}
 if(!S.viewer)paintObservationMetadata();
}
function paintObservationMetadata(){
 const files=new Map(S.files.map(f=>[f.path,f]));
 for(const entry of S.virtualGrid?.rowReady?.values()||[])for(const card of entry.node?.querySelectorAll('.card')||[]){const f=files.get(card.dataset.p);if(!f)continue;const box=card.querySelector('.badges');if(box)box.innerHTML=badges(f)}
 refreshSelectionUI();
}
async function refreshOne(path){const r=await post('/api/observations',{paths:[path]});const f=S.files.find(x=>x.path===path);if(f){f.observations=(r.observations||{})[path]||[];if(pagedBrowse())mobilePager?.remember(f);}S.obsRevision=String(r.revision??S.obsRevision).split('-')[0]+'-'+assetEpoch;if(!S.viewer)render();return f}
function editableObservations(f){return(f.observations||[]).filter(o=>o.kind!=='receipt'&&o.confidence>0&&(o.kind==='bbox'||o.kind==='mask'))}

function maskRleEncode(mask){const out=[];for(let i=0;i<mask.length;){if(!mask[i]){i++;continue}const s=i;while(i<mask.length&&mask[i])i++;out.push(s,i-s)}return out}
function maskRleDecode(rle,n){const a=new Uint8Array(n);for(let i=0;i<(rle||[]).length;i+=2)a.fill(1,rle[i],rle[i]+rle[i+1]);return a}
function modelShortName(value){return String(value||'').replace(/\\/g,'/').split('/').pop().replace(/\.(?:pt|pth|onnx|safetensors|engine)$/i,'')}
function geometryOf(o){try{return typeof o?.geometry==='string'?JSON.parse(o.geometry):o?.geometry}catch{return null}}
// Explicit display size keeps both layers aligned without intrinsic-canvas feedback.
function fitInspectorSurface(surface,stage,width,height){
 const r=stage.getBoundingClientRect();if(!(width>0&&height>0&&r.width>0&&r.height>0))return;
 const scale=Math.min(r.width/width,r.height/height),w=`${Math.max(1,width*scale)}px`,h=`${Math.max(1,height*scale)}px`;
 if(surface.style.width!==w)surface.style.width=w;
 if(surface.style.height!==h)surface.style.height=h;
}
function openMaskEditor({path,concept,bbox,existing=null,origin=null}){
 const viewer=document.querySelector('#imageViewer .viewerPanel');if(!viewer)return;
 const sourceImage=viewer.querySelector('.viewerSource');$('#imageViewer')._viewerResize?.disconnect();$('#imageViewer')._maskDispose?.();$('#imageViewer')._inspectionCamera?.dispose();$('#imageViewer')._maskCamera?.dispose();
 const saved=viewer.innerHTML;viewer.classList.add('maskCardMode');
 viewer.innerHTML=`<div class="maskPanel">
 <div class="maskHead"><b>Paint Mask · ${esc(observationLabel({...origin,concept}))}</b><span class="tiny">${esc(origin?.provider||'Manual')} · ${esc(origin?.model||'New annotation')}</span><div class="maskHeadTools"><button id="maskCopy">Copy to Clipboard</button><button id="maskPaste">Paste from Clipboard</button><button id="maskClose">×</button></div></div>
 <div class="maskBody"><div class="maskStage"><div class="maskCanvasStack"><canvas id="maskSourceCanvas"></canvas><canvas id="maskCanvas"></canvas></div><div id="maskLocked" hidden>Clipboard copy active · paste the edited mask back to continue.</div></div>
 <aside class="maskTools"><div class="maskMode"><button id="maskPaint" class="active">Paint</button><button id="maskErase">Erase</button></div>
 <label>Brush size <input id="maskBrush" type="range" min="1" max="200" value="32"><output id="maskBrushValue">32 px</output></label>
 <label>Mask opacity <input id="maskOpacity" type="range" min="10" max="100" value="58"><output id="maskOpacityValue">58%</output></label>
 <label>Mask view <select id="maskBlend"><option value="normal">Normal</option><option value="screen">Dodge</option><option value="multiply">Multiply</option></select></label>
 <button id="maskUndo">Undo</button><button id="maskClear">Clear</button><div class="tiny">The crop is reference only. Existing segmentation loads automatically; box-only detections start transparent. Any nontransparent pasted pixel becomes mask. Clipboard images must exactly match this crop.</div></aside></div>
 <div class="maskFoot"><span id="maskInfo" class="tiny"></span><button id="maskCancel">Cancel</button><button id="maskSave">Save Mask</button></div></div>`;
 const host=viewer;
 const sourceCanvas=host.querySelector('#maskSourceCanvas'),sourceCtx=sourceCanvas.getContext('2d'),canvas=host.querySelector('#maskCanvas'),ctx=canvas.getContext('2d'),source=sourceImage||new Image();
 const x1=Math.round(bbox[0]),y1=Math.round(bbox[1]),x2=Math.round(bbox[2]),y2=Math.round(bbox[3]),w=x2-x1,h=y2-y1;
 if(w<1||h<1){viewer.innerHTML=saved;viewer.classList.remove('maskCardMode');return alert('Mask crop is empty.')}
 sourceCanvas.width=canvas.width=w;sourceCanvas.height=canvas.height=h;
 const stack=host.querySelector('.maskCanvasStack'),stage=host.querySelector('.maskStage');
 let cropCamera=null;const fitCrop=()=>{fitInspectorSurface(stack,stage,w,h);cropCamera?.refresh()};
 const cropResize=new ResizeObserver(fitCrop);cropResize.observe(stage);$('#imageViewer')._maskResize=cropResize;fitCrop();
 let mask=new Uint8Array(w*h),undo=[],mode='paint',locked=false,down=false,last=null;
 cropCamera=new InspectionCamera({surface:stack,stage,key:path+'|mask|'+bbox.join(','),active:()=>S.viewer===path&&viewer.classList.contains('maskCardMode'),canPan:()=>!down});$('#imageViewer')._maskCamera=cropCamera;
 // Stored geometry is authoritative. A YOLO polygon and a SAM RLE both
 // initialize the same editable crop, even when scope was not set to "mask".
 if(existing?.mask_rle&&existing?.mask_size){
  const mw=Number(existing.mask_size[0]),mh=Number(existing.mask_size[1]);
  const decoded=maskRleDecode(existing.mask_rle,mw*mh);
  const ox=Math.round(Number(existing.bbox?.[0]??x1))-x1,oy=Math.round(Number(existing.bbox?.[1]??y1))-y1;
  if(mw===w&&mh===h&&ox===0&&oy===0)mask=decoded;
  else for(let yy=0;yy<mh;yy++)for(let xx=0;xx<mw;xx++)if(decoded[yy*mw+xx]){
   const dx=xx+ox,dy=yy+oy;if(dx>=0&&dy>=0&&dx<w&&dy<h)mask[dy*w+dx]=1;
  }
 }else if(existing?.polygon?.length){
  const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d');
  x.fillStyle='#fff';x.beginPath();existing.polygon.forEach((pt,i)=>i?x.lineTo(Number(pt[0])-x1,Number(pt[1])-y1):x.moveTo(Number(pt[0])-x1,Number(pt[1])-y1));x.closePath();x.fill();
  const a=x.getImageData(0,0,w,h).data;for(let i=0;i<mask.length;i++)mask[i]=a[i*4+3]>0?1:0;
 }
 const snapshot=()=>{undo.push(mask.slice());if(undo.length>8)undo.shift()};
 const maskImage=ctx.createImageData(w,h);let maskedPixels=mask.reduce((a,b)=>a+b,0),dirty=[0,0,w,h],paintFrame=0;
 function dirtyRect(xa,ya,xb,yb){xa=Math.max(0,Math.min(w,xa));ya=Math.max(0,Math.min(h,ya));xb=Math.max(0,Math.min(w,xb));yb=Math.max(0,Math.min(h,yb));if(xb<=xa||yb<=ya)return;dirty=dirty?[Math.min(dirty[0],xa),Math.min(dirty[1],ya),Math.max(dirty[2],xb),Math.max(dirty[3],yb)]:[xa,ya,xb,yb]}
 function resetMaskDisplay(){maskedPixels=mask.reduce((a,b)=>a+b,0);dirty=[0,0,w,h];renderMask()}
 function renderMask(){
  if(paintFrame)return;paintFrame=requestAnimationFrame(()=>{
   paintFrame=0;if(!canvas.isConnected)return;
   if(dirty){const [xa,ya,xb,yb]=dirty,d=maskImage.data;dirty=null;
    for(let yy=ya;yy<yb;yy++)for(let xx=xa;xx<xb;xx++){const index=yy*w+xx,q=index*4;d[q]=255;d[q+1]=70;d[q+2]=70;d[q+3]=mask[index]?255:0}
    ctx.putImageData(maskImage,0,0,xa,ya,xb-xa,yb-ya);
   }
   canvas.style.opacity=String(Number(host.querySelector('#maskOpacity').value)/100);
   canvas.style.mixBlendMode=host.querySelector('#maskBlend').value;
   host.querySelector('#maskInfo').textContent=`${w} × ${h} crop · ${maskedPixels.toLocaleString()} masked pixels`;
   host.querySelector('#maskLocked').hidden=!locked;host.querySelector('#maskSave').disabled=locked;
  });
 }
 function renderSource(){sourceCtx.clearRect(0,0,w,h);sourceCtx.drawImage(source,x1,y1,w,h,0,0,w,h)}
 function pnt(e){const r=canvas.getBoundingClientRect();return[(e.clientX-r.left)*w/r.width,(e.clientY-r.top)*h/r.height]}
 function dab(x,y){const rad=Number(host.querySelector('#maskBrush').value)/2,xa=Math.max(0,Math.floor(x-rad)),xb=Math.min(w-1,Math.ceil(x+rad)),ya=Math.max(0,Math.floor(y-rad)),yb=Math.min(h-1,Math.ceil(y+rad)),val=mode==='paint'?1:0,rr=rad*rad;for(let yy=ya;yy<=yb;yy++)for(let xx=xa;xx<=xb;xx++)if((xx-x)**2+(yy-y)**2<=rr){const index=yy*w+xx;if(mask[index]!==val){maskedPixels+=val?1:-1;mask[index]=val}}dirtyRect(xa,ya,xb+1,yb+1)}
 function stroke(a,b){const dx=b[0]-a[0],dy=b[1]-a[1],steps=Math.max(1,Math.ceil(Math.hypot(dx,dy)/(Math.max(1,Number(host.querySelector('#maskBrush').value)/4))));for(let i=0;i<=steps;i++)dab(a[0]+dx*i/steps,a[1]+dy*i/steps)}
 canvas.onpointerdown=e=>{if(locked||down||e.button>0)return;down=true;last=pnt(e);snapshot();dab(...last);canvas.setPointerCapture(e.pointerId);renderMask()};
 canvas.onpointermove=e=>{if(!down||locked)return;const q=pnt(e);stroke(last,q);last=q;renderMask()};
 canvas.onpointerup=canvas.onpointercancel=()=>{down=false;last=null};
 function setMode(m){mode=m;host.querySelector('#maskPaint').classList.toggle('active',m==='paint');host.querySelector('#maskErase').classList.toggle('active',m==='erase')}
 host.querySelector('#maskPaint').onclick=()=>setMode('paint');host.querySelector('#maskErase').onclick=()=>setMode('erase');
 const brush=host.querySelector('#maskBrush');brush.oninput=()=>host.querySelector('#maskBrushValue').textContent=brush.value+' px';
 const opacity=host.querySelector('#maskOpacity');opacity.oninput=()=>{host.querySelector('#maskOpacityValue').textContent=opacity.value+'%';renderMask()};
 host.querySelector('#maskBlend').onchange=renderMask;
 host.querySelector('#maskUndo').onclick=()=>{if(locked||!undo.length)return;mask=undo.pop();resetMaskDisplay()};
 host.querySelector('#maskClear').onclick=()=>{if(locked)return;snapshot();mask.fill(0);resetMaskDisplay()};
 async function copyMask(){try{
   const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d'),im=x.createImageData(w,h);
   for(let i=0;i<mask.length;i++)if(mask[i]){const q=i*4;im.data[q]=255;im.data[q+1]=255;im.data[q+2]=255;im.data[q+3]=255}
   x.putImageData(im,0,0);
   const blob=await new Promise(r=>c.toBlob(r,'image/png'));await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);locked=true;renderMask()
  }catch(e){alert('Clipboard copy failed: '+e.message)}}
 async function importBlob(blob){const bm=await createImageBitmap(blob);if(bm.width!==w||bm.height!==h){bm.close();throw new Error(`Clipboard image is ${bm.width}×${bm.height}; this mask crop is ${w}×${h}.`)}
  const c=document.createElement('canvas');c.width=w;c.height=h;const x=c.getContext('2d');x.clearRect(0,0,w,h);x.drawImage(bm,0,0);bm.close();
  const d=x.getImageData(0,0,w,h).data,next=new Uint8Array(w*h);for(let i=0;i<next.length;i++)next[i]=d[i*4+3]>0?1:0;
  mask=next;undo=[];locked=false;resetMaskDisplay()}
 async function pasteMask(){try{const items=await navigator.clipboard.read();let blob=null;for(const item of items){const type=item.types.find(t=>t.startsWith('image/'));if(type){blob=await item.getType(type);break}}if(!blob)throw new Error('Clipboard does not contain an image.');await importBlob(blob)}catch(e){alert('Clipboard paste failed: '+e.message)}}
 host.querySelector('#maskCopy').onclick=copyMask;host.querySelector('#maskPaste').onclick=pasteMask;
 const onPaste=async e=>{if(!viewer.classList.contains('maskCardMode'))return;e.preventDefault();const item=[...e.clipboardData.items].find(x=>x.type.startsWith('image/'));if(!item)return alert('Clipboard does not contain an image.');try{await importBlob(item.getAsFile())}catch(err){alert('Clipboard paste failed: '+err.message)}};document.addEventListener('paste',onPaste);$('#imageViewer')._maskDispose=()=>{document.removeEventListener('paste',onPaste);cropCamera?.dispose()};
 function close(){document.removeEventListener('paste',onPaste);cropCamera?.dispose();viewer.classList.remove('maskCardMode');openViewer(path)}
 host.querySelector('#maskClose').onclick=close;host.querySelector('#maskCancel').onclick=close;
 host.querySelector('#maskSave').onclick=async()=>{if(locked)return;const runs=maskRleEncode(mask);if(!runs.length)return alert('Mask is empty.');
  const save=host.querySelector('#maskSave');save.disabled=true;
  try{
   await refreshOne(path);const subjects=editableObservations(S.files.find(f=>f.path===path)||{}).filter(o=>o.kind==='mask'&&isSubjectObservation(o));
   const choice=await chooseMaskOwner(path,subjects,{existingSubject:isSubjectObservation(origin)});if(!choice)return;
  const taught=await post('/api/observations/teach',{path,concept,scope:'mask',geometry:{bbox:[x1,y1,x2,y2],mask_size:[w,h],mask_rle:runs,method:existing?.method||'manual',...(isSubjectObservation(origin)?{subject_role:true,subject_pipeline:geometryOf(origin)?.subject_pipeline}: {})},provider:origin?.provider||null,model:origin?.model||null,confidence:origin?.confidence||null,replace_observation:origin?.kind==='mask'?{concept:origin.concept,provider:origin.provider,model:origin.model,kind:origin.kind,geometry:origin.geometry}:null});
   await refreshOne(path);
   if(choice.owner){
    const part=editableObservations(S.files.find(f=>f.path===path)||{}).find(o=>o.kind==='mask'&&o.concept===concept&&o.provider===(origin?.provider||'human-teach')&&o.model===(origin?.model||'concept-bank')&&JSON.stringify(geometryOf(o)?.mask_rle)===JSON.stringify(taught.geometry.mask_rle)&&geometryOf(o)?.bbox?.every((n,i)=>n===taught.geometry.bbox[i]));
    try{if(!part)throw Error('Saved mask changed; select it again to attach.');await post('/api/observations/subject-part',{subject:maskObservationRef(path,choice.owner),part:maskObservationRef(path,part)});await refreshOne(path)}catch(error){alert('Mask saved, but ownership was not assigned: '+error.message)}
   }
   document.removeEventListener('paste',onPaste);viewer.classList.remove('maskCardMode');openViewer(path,choice.owner?{selectConcept:choice.owner.concept,selectBox:geometryOf(choice.owner)?.bbox}:{});refreshDiscovered();
  }catch(error){alert(error.message)}finally{if(save.isConnected)save.disabled=locked}
 };
 async function sourceReady(){try{if(source.decode)await source.decode();if(sourceCanvas.isConnected)renderSource()}catch(e){console.warn('Mask source decode failed',e)}}
 if(source.complete&&source.naturalWidth)sourceReady();else{source.addEventListener('load',sourceReady,{once:true});if(!source.src)source.src='/api/file?path='+enc(path)}
 renderMask();host.querySelector('#maskCanvas')?.focus();
}
function chooseMaskOwner(path,subjects,{existingSubject=false}={}){
 return new Promise(resolve=>{
  const dialog=document.createElement('dialog');dialog.className='qualitySeenDialog';dialog.style.maxWidth='min(480px,94vw)';
  dialog.innerHTML=`<h3>Does this mask belong to a subject?</h3><p>Keep it as an ordinary mask, or choose its owner. Attaching a part makes that subject ready for Learn Subject; it does not start training.</p><label>Owner <select class="maskOwnerSelect"><option value="">Choose a subject…</option>${subjects.map((o,i)=>`<option value="${i}">${esc(observationLabel(o))} · subject ${i+1}</option>`).join('')}</select></label><div class="maskOwnerPreview" hidden style="position:relative;margin:12px 0"><img alt="Selected subject in the source image" style="display:block;width:100%;max-height:260px;object-fit:contain"><svg aria-hidden="true" preserveAspectRatio="xMidYMid meet" style="position:absolute;inset:0;width:100%;height:100%"></svg></div><p class="tiny">${existingSubject?'This is already a Subject mask; keep its current identity.':subjects.length?'The highlighted box identifies the selected owner.':'No masked subjects available. Save this as an ordinary mask.'}</p><div class="buttonGrid"><button class="maskOwnerKeep">${existingSubject?'Keep existing Subject':'Keep standalone'}</button><button class="maskOwnerAttach" disabled>Attach to chosen subject</button></div><button class="maskOwnerCancel">Cancel</button>`;
  const select=dialog.querySelector('.maskOwnerSelect'),attach=dialog.querySelector('.maskOwnerAttach'),preview=dialog.querySelector('.maskOwnerPreview');
  select.disabled=existingSubject||!subjects.length;
  select.onchange=()=>{const owner=select.value===''?null:subjects[Number(select.value)];attach.disabled=!owner;preview.hidden=!owner;if(!owner)return;const g=geometryOf(owner),size=g.source_size||[1,1],b=g.bbox;preview.querySelector('img').src='/api/thumb?path='+enc(path);const svg=preview.querySelector('svg');svg.setAttribute('viewBox',`0 0 ${size[0]} ${size[1]}`);svg.innerHTML=`<rect x="${Number(b[0])}" y="${Number(b[1])}" width="${Number(b[2]-b[0])}" height="${Number(b[3]-b[1])}" fill="none" stroke="#ffd45a" stroke-width="${Math.max(size[0],size[1])/100}"/>`;};
  let result=null;
  dialog.querySelector('.maskOwnerKeep').onclick=()=>{result={owner:null};dialog.close()};
  attach.onclick=()=>{if(select.value==='')return;result={owner:subjects[Number(select.value)]};dialog.close()};
  dialog.querySelector('.maskOwnerCancel').onclick=()=>dialog.close();
  dialog.addEventListener('keydown',event=>event.stopPropagation());
  dialog.addEventListener('close',()=>{dialog.remove();resolve(result)},{once:true});document.body.appendChild(dialog);dialog.showModal();dialog.querySelector('.maskOwnerKeep').focus();
 });
}
function maskObservationRef(path,o){return{path,concept:o.concept,provider:o.provider,model:o.model,kind:o.kind,geometry:o.geometry??null}}
function acceptTaughtBox(observations,geometries,taught,geometry){
 const index=observations.findIndex((o,i)=>o.concept===taught.concept&&o.provider===taught.provider&&o.model===taught.model&&o.kind==='bbox'&&JSON.stringify(geometries[i]?.bbox)===JSON.stringify(geometry.bbox));
 if(index>=0){observations[index]=taught;geometries[index]=geometry;return index;}
 observations.push(taught);geometries.push(geometry);return observations.length-1;
}
const inspectorSources=new Map();
function openViewer(path,{selectBox=null,selectConcept=null}={}){observationRefreshController?.abort();for(const e of thumbAssets.values())if(e.state==='loading')e.controller?.abort();gridActivity('inspector-open');const f=S.files.find(x=>x.path===path);if(!f)return;S.viewer=path;let v=$('#imageViewer');if(!v){v=document.createElement('div');v.id='imageViewer';v.className='imageViewer';document.body.appendChild(v)}
 v._maskDispose?.();v._maskDispose=null;v._inspectionCamera?.dispose();v._maskCamera?.dispose();
 const obs=editableObservations(f),geometries=obs.map(geometryOf);v.innerHTML=`<div class="viewerBackdrop"></div><div class="viewerPanel teachViewer" role="dialog" aria-modal="true"><div class="viewerDisplayTools"><button id="viewerStretchBtn" title="Use the available inspection workspace">Stretch</button><button id="viewerCleanBtn" title="Source pixels only; press again to restore the dirt">Clean</button><button id="viewerPrevBtn" title="Previous Multi-Work image">‹</button><button id="viewerNextBtn" title="Next Multi-Work image">›</button></div><button class="viewerClose">×</button><div class="viewerWork"><div class="viewerStage"><div class="viewerImageFrame"><img class="viewerSource" fetchpriority="high" decoding="async"><img class="viewerSavedMasks" alt=""><svg class="teachOverlay" preserveAspectRatio="none"></svg></div></div><aside class="visionTeach"><h3>Correct / Teach</h3><div class="muted">Select a detection to reject or relabel it. Teach a new thing by drawing a box or using the entire image.</div><div class="subhead">Detections</div><div class="teachObs">${obs.map((o,i)=>`<button data-oi="${i}" title="${esc(o.provider)} · ${esc(o.model)}">${esc(observationLabel(o))}${esc(recognitionNote(o))} · ${Math.round(observationConfidence(o)*100)}% <small>(${esc(modelShortName(o.model))})</small></button>`).join('')||'<span class="tiny">No box/mask detections.</span>'}</div><div id="teachSelected" class="tiny">No detection selected.</div><div class="buttonGrid"><button id="rejectObsBtn" disabled>Sorry, that isn't that</button><button id="relabelObsBtn" disabled>That's actually…</button></div><div class="buttonGrid"><button id="confirmLMClassBtn" disabled>Use language-model class</button><button id="confirmLearnedClassBtn" disabled>Use learned class</button><button id="learnSubjectBtn" disabled>Learn Subject</button><button id="addSubjectPartBtn" disabled>Add part to subject</button><button id="guidedSubjectSplitBtn" disabled>Split into multiple subjects…</button></div><div id="subjectLearningStatus" class="tiny"></div><hr><input id="teachConcept" list="teachConceptList" placeholder="type or choose visual concept" autocomplete="off"><datalist id="teachConceptList">${S.discovered.map(x=>`<option value="${esc(x.concept||x)}"></option>`).join('')}</datalist><div class="teachGroundButtons"><button id="teachWholeBtn" title="Record image-level evidence instead of a localized box.">Entire Image</button><button id="paintMaskBtn" title="Paint a binary mask. Uses the selected box as its crop, or edits a selected mask.">Paint Mask</button><button data-capability="inference" id="samMaskBtn" title="Ask SAM for a first-draft mask from the selected box, then edit it here.">SAM Mask</button></div><div id="teachHint" class="tiny" title="Typing or choosing a concept switches the image into bounding mode. Drag directly over the image to teach an instance.">Choose a concept to enter bounding mode.</div></aside></div><div class="viewerCaption">${esc(f.name)}<input class="inspectorPath" aria-label="Absolute image path" readonly value="${esc(path)}" style="display:block;width:100%;user-select:text" onclick="this.select()"></div></div>`;v.classList.add('open');installViewerDisplayControls(v,path);
 v._maskResize?.disconnect();
 const sourceKey=path+'|'+(f.mtime||0)+'|'+(S.gridRedrawEpoch||0);
 let img=v.querySelector('.viewerSource');
 const cached=inspectorSources.get(sourceKey);if(cached?.complete&&cached.naturalWidth)img.replaceWith(img=cached);
 else{img.src='/api/file?path='+enc(path);img.addEventListener('load',()=>{inspectorSources.delete(sourceKey);inspectorSources.set(sourceKey,img);while(inspectorSources.size>2)inspectorSources.delete(inspectorSources.keys().next().value)},{once:true})}
 const svg=v.querySelector('.teachOverlay'),frame=v.querySelector('.viewerImageFrame'),stage=v.querySelector('.viewerStage');let selected=null,drawing=false,startPt=null,temp=null,boxSaving=false;
 frame.dataset.loading='true';frame.dataset.loadingMessage='Loading source image…';
 const knownSize=geometries.find(g=>g?.source_size?.[0]>0&&g?.source_size?.[1]>0)?.source_size;
 const provisional=knownSize||[f.width||1000,f.height||(1000/fileAspect(f))];let inspectorCamera=null;
 function setVB(){const width=img.naturalWidth||provisional[0],height=img.naturalHeight||provisional[1];svg.setAttribute('viewBox',`0 0 ${width} ${height}`);fitInspectorSurface(frame,stage,width,height);inspectorCamera?.refresh();if(img.naturalWidth)frame.dataset.loading='false'}
 img.addEventListener('error',()=>{frame.dataset.loading='true';frame.dataset.loadingMessage='Source image could not load. Refresh to renew the paired session.'},{once:true});
 img.addEventListener('load',setVB);const viewerResize=new ResizeObserver(setVB);viewerResize.observe(stage);v._viewerResize?.disconnect();v._viewerResize=viewerResize;setVB();
 inspectorCamera=new InspectionCamera({surface:frame,stage,key:path+'|inspector',active:()=>S.viewer===path&&!v.querySelector('.viewerPanel')?.classList.contains('maskCardMode'),canPan:()=>!startPt});v._inspectionCamera=inspectorCamera;
 function drawExisting(){if(!img.naturalWidth)return;setVB();svg.innerHTML='';obs.forEach((o,i)=>{const g=geometries[i];if(!g?.bbox||(o.presentation_hidden&&selected!==i))return;const [x1,y1,x2,y2]=g.bbox;const r=document.createElementNS('http://www.w3.org/2000/svg','rect');r.setAttribute('x',x1);r.setAttribute('y',y1);r.setAttribute('width',x2-x1);r.setAttribute('height',y2-y1);r.setAttribute('class',`teachExisting ${selected===i?'active':''}`);r.style.stroke=selected===i?'#ffd45a':detectorColor(o.provider,o.model);r.dataset.oi=i;r.onclick=e=>{e.stopPropagation();choose(i)};svg.appendChild(r)})}
 function sourceReady(){drawExisting();const overlay=v.querySelector('.viewerSavedMasks');if(overlay&&obs.some(o=>o.kind==='mask')){overlay.fetchPriority='low';overlay.src='/api/grid-overlay?path='+enc(path)+'&kind=masks&rev='+S.obsRevision}}
 img.addEventListener('load',sourceReady,{once:true});if(img.complete&&img.naturalWidth)sourceReady();
 function choose(i){selected=Number(i);const o=obs[selected];v.querySelectorAll('.teachObs button').forEach(b=>b.classList.toggle('active',Number(b.dataset.oi)===selected));$('#teachSelected').textContent=`${observationLabel(o)} · ${o.provider} · ${o.model}${subjectSeparationNote(o)?' · '+subjectSeparationNote(o):''}`;const review=geometryOf(o)?.qwen_review;if(review){$('#teachSelected').textContent+='\nLanguage model draft: '+review.label+'\nVisible features: '+(review.visible_features||[]).join(', ')+'\nBelongs to this subject: '+(review.owned_objects||[]).join(', ')+'\nEvidence: '+(review.evidence||[]).join('; ')+'\nUncertain: '+(review.uncertain||[]).join('; ');$('#teachSelected').style.whiteSpace='pre-wrap';}$('#rejectObsBtn').disabled=false;$('#relabelObsBtn').disabled=false;
 const learned=geometryOf(o)?.trained_class_review;if(learned){$('#teachSelected').style.whiteSpace='pre-wrap';$('#teachSelected').textContent+='\nLearned class: '+(learned.accepted?learned.label+' (draft)':'Unidentified — insufficient support')+' · score '+Math.round(learned.score*100)+'%'+(!learned.accepted?'\n'+(learned.rejection_reasons||[]).join('; '):'');}
 const parts=geometryOf(o)?.subject_parts||[];if(parts.length||geometryOf(o)?.ownership_status==='unresolved')$('#teachSelected').style.whiteSpace='pre-wrap';if(geometryOf(o)?.ownership_status==='unresolved')$('#teachSelected').textContent+='\nOwner unresolved. Use Add part to subject to choose its owner.';if(parts.length)$('#teachSelected').textContent+='\nParts: '+parts.map(part=>part.concept+(part.confirmation==='manual'?' (confirmed)':' (draft)')).join(', ');
 $('#guidedSubjectSplitBtn').disabled=!(S.capabilities.subject_intelligence&&isSubjectObservation(o)&&o.kind==='mask'&&geometryOf(o)?.bbox);
 $('#confirmLMClassBtn').disabled=!(S.capabilities.subject_intelligence&&geometryOf(o)?.qwen_review?.label);$('#confirmLearnedClassBtn').disabled=!(S.capabilities.subject_intelligence&&geometryOf(o)?.trained_class_review?.accepted);
 const lesson=geometryOf(o)?.subject_learning;
 $('#learnSubjectBtn').disabled=!(isSubjectObservation(o)&&lesson?.revision&&!lesson.confirmed&&lesson.label===o.concept);
 $('#addSubjectPartBtn').disabled=!(o.kind==='mask'&&!isSubjectObservation(o)&&obs.some(x=>x.kind==='mask'&&isSubjectObservation(x)));
 $('#subjectLearningStatus').textContent=lesson?.confirmed?'Teaching example saved · class training queue':!$('#learnSubjectBtn').disabled?'Manual subject change ready to teach':'';
 gridActivity('inspector-select');drawExisting();svg.querySelectorAll('.teachExisting').forEach(r=>{const index=Number(r.dataset.oi);r.classList.toggle('active',selected===index);r.style.stroke=selected===index?'#ffd45a':detectorColor(obs[index].provider,obs[index].model)})}
 S.refreshRecognitionInspector=async changedPaths=>{
  if(!changedPaths.includes(path)||S.viewer!==path||!v.contains(svg)||startPt||v.querySelector('.maskCanvasStack'))return;
  const prior=selected===null?null:obs[selected];await refreshOne(path);
  if(S.viewer!==path||!v.contains(svg)||startPt||v.querySelector('.maskCanvasStack'))return;
  obs.splice(0,obs.length,...editableObservations(S.files.find(f=>f.path===path)||{}));geometries.splice(0,geometries.length,...obs.map(geometryOf));
  const host=v.querySelector('.teachObs');host.innerHTML=obs.map((o,i)=>`<button data-oi="${i}" title="${esc(o.provider)} · ${esc(o.model)}">${esc(observationLabel(o))}${esc(recognitionNote(o))} · ${Math.round(observationConfidence(o)*100)}% <small>(${esc(modelShortName(o.model))})</small></button>`).join('');
  host.querySelectorAll('button').forEach(b=>b.onclick=()=>choose(b.dataset.oi));
  selected=prior?obs.findIndex(o=>o.provider===prior.provider&&o.model===prior.model&&JSON.stringify(geometryOf(o)?.bbox)===JSON.stringify(geometryOf(prior)?.bbox)):null;
  if(selected!==null&&selected>=0)choose(selected);else{selected=null;drawExisting()}
 };
 v.querySelectorAll('.teachObs button').forEach(b=>b.onclick=()=>choose(b.dataset.oi));
 S.refreshRecognitionInspector([path]).catch(error=>console.warn('Inspector metadata refresh failed',error));
 if(selectBox){const index=obs.findIndex((o,i)=>o.concept===selectConcept&&geometries[i]?.bbox?.every((n,k)=>Math.abs(n-selectBox[k])<.001));if(index>=0)choose(index)}
 async function correct(action){if(selected===null)return;const o=obs[selected];let corrected=null;if(action==='relabel'){corrected=await window.chooseObservationLabel({concept:o.concept,subject:isSubjectObservation(o),suggestion:geometryOf(o)?.trained_class_review?.accepted?geometryOf(o).trained_class_review.label:(geometryOf(o)?.qwen_review?.label||'')});if(!corrected?.trim())return}await post('/api/observations/correct',{path,concept:o.concept,provider:o.provider,model:o.model,kind:o.kind,geometry:o.geometry??null,action,corrected_concept:corrected});await refreshOne(path);openViewer(path,{selectConcept:action==='relabel'?corrected.trim():null,selectBox:geometryOf(o)?.bbox});refreshDiscovered()}
 $('#rejectObsBtn').onclick=()=>correct('reject');$('#relabelObsBtn').onclick=()=>correct('relabel');
 $('#guidedSubjectSplitBtn').onclick=()=>{if(selected===null)return;openGuidedSubjectSplit({path,observation:obs[selected],sourceUrl:img.src,onDone:async()=>{await refreshOne(path);openViewer(path);refreshDiscovered()}})};
 const subjectRef=o=>({path,concept:o.concept,provider:o.provider,model:o.model,kind:o.kind,geometry:o.geometry??null});
 for(const [id,source] of [['#confirmLMClassBtn','language_model'],['#confirmLearnedClassBtn','trained']])$(id).onclick=async()=>{if(selected===null)return;try{const result=await post('/api/subjects/classes/confirm',{...subjectRef(obs[selected]),source});await refreshOne(path);openViewer(path,{selectConcept:result.label,selectBox:geometryOf(obs[selected])?.bbox});$('#status').textContent='Class confirmed; click Learn Subject to save its composite'}catch(error){alert(error.message)}};
 $('#learnSubjectBtn').onclick=async()=>{if(selected===null)return;const button=$('#learnSubjectBtn');button.disabled=true;try{const lesson=await post('/api/observations/learn-subject',subjectRef(obs[selected]));$('#status').textContent=lesson.class_registered?'Composite saved for class training: '+lesson.class_key:'Ownership lesson saved';scheduleJobsPoll(500);await S.refreshSubjectClassStatus?.();await refreshOne(path);openViewer(path,{selectConcept:obs[selected].concept,selectBox:geometryOf(obs[selected])?.bbox})}catch(error){alert(error.message);choose(selected)}};
 $('#addSubjectPartBtn').onclick=async()=>{if(selected===null)return;const part=obs[selected],subjects=obs.filter(o=>o.kind==='mask'&&isSubjectObservation(o));const choice=await chooseMaskOwner(path,subjects);if(!choice?.owner)return;const owner=choice.owner;try{await post('/api/observations/subject-part',{subject:subjectRef(owner),part:subjectRef(part)});await refreshOne(path);openViewer(path,{selectConcept:owner.concept,selectBox:geometryOf(owner)?.bbox})}catch(error){alert(error.message)}};

 $('#teachWholeBtn').onclick=async()=>{const concept=$('#teachConcept').value.trim();if(!concept)return alert('Name the new visual concept first.');await post('/api/observations/teach',{path,concept,scope:'image'});await refreshOne(path);openViewer(path);refreshDiscovered()};
 $('#samMaskBtn').onclick=async()=>{
  const o=selected===null?null:obs[selected],g=geometryOf(o),concept=$('#teachConcept').value.trim()||o?.concept;
  if(!o||!g?.bbox)return alert('Select a boxed detection first. SAM needs the box.');if(!concept)return alert('Name the concept first.');
  $('#status').textContent=`SAM is cutting ${concept} out of the box…`;
  try{const m=await post('/api/learning/sam-mask',{path,bbox:g.bbox});openMaskEditor({path,concept,bbox:m.bbox,existing:m,origin:o});$('#status').textContent='SAM draft ready · paint/erase if needed, then Save Mask.'}catch(e){alert(e.message)}
 };
 $('#paintMaskBtn').onclick=async()=>{
  // Resolve the selected observation against SQLite, not the viewer's pre-job snapshot.
  const selectedOld=selected===null?null:obs[selected];
  let o=selectedOld;
  if(selectedOld){
   try{
    const latest=await post('/api/observations',{paths:[path]});
    const current=(latest.observations||{})[path]||[];
    const exact=current.find(x=>x.concept===selectedOld.concept&&x.provider===selectedOld.provider&&x.model===selectedOld.model&&x.geometry===selectedOld.geometry);
    const oldBox=geometryOf(selectedOld)?.bbox;
    const sameBox=current.filter(x=>x.concept===selectedOld.concept&&x.provider===selectedOld.provider&&x.model===selectedOld.model&&JSON.stringify(geometryOf(x)?.bbox)===JSON.stringify(oldBox));
    o=exact||(sameBox.length===1?sameBox[0]:null);
    if(!o){alert('This observation changed since the viewer opened. Reopen the image and select it again before editing.');return;}
    const fNow=S.files.find(x=>x.path===path);if(fNow)fNow.observations=current;
   }catch(e){alert('Cannot load the current mask. Nothing was changed: '+e.message);return;}
  }
  const g=geometryOf(o),concept=$('#teachConcept').value.trim()||o?.concept;
  if(!concept)return alert('Name a visual concept or select an existing detection first.');
  let box=null,existing=null;
  if(o?.kind==='mask'&&g?.bbox){box=g.bbox;existing=g}
  else if(g?.bbox)box=g.bbox;
  else box=[0,0,img.naturalWidth,img.naturalHeight];
  openMaskEditor({path,concept,bbox:box,existing,origin:o});
 };
 function point(e){const ctm=svg.getScreenCTM();if(!ctm)return[0,0];const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(ctm.inverse()),vb=svg.viewBox.baseVal;return[Math.max(vb.x,Math.min(vb.x+vb.width,p.x)),Math.max(vb.y,Math.min(vb.y+vb.height,p.y))]}
 const conceptInput=$('#teachConcept');function syncBoundingMode(){drawing=!!conceptInput.value.trim();$('#teachHint').textContent=drawing?'Bounding mode · drag over the image.':'Choose a concept to enter bounding mode.';svg.classList.toggle('drawing',drawing)}conceptInput.addEventListener('input',syncBoundingMode);conceptInput.addEventListener('change',syncBoundingMode);syncBoundingMode();
 svg.onpointerdown=e=>{if(!drawing||boxSaving||!img.naturalWidth)return;startPt=point(e);temp=document.createElementNS('http://www.w3.org/2000/svg','rect');temp.setAttribute('class','teachDraft');svg.appendChild(temp);svg.setPointerCapture(e.pointerId)};
 svg.onpointermove=e=>{if(!drawing||!startPt||!temp)return;const q=point(e),x=Math.min(startPt[0],q[0]),y=Math.min(startPt[1],q[1]);temp.setAttribute('x',x);temp.setAttribute('y',y);temp.setAttribute('width',Math.abs(q[0]-startPt[0]));temp.setAttribute('height',Math.abs(q[1]-startPt[1]))};
 svg.onpointerup=async e=>{
  if(!drawing||!startPt||boxSaving)return;
  const q=point(e),box=[Math.min(startPt[0],q[0]),Math.min(startPt[1],q[1]),Math.max(startPt[0],q[0]),Math.max(startPt[1],q[1])],concept=conceptInput.value.trim(),draft=temp;
  startPt=null;temp=null;drawing=false;boxSaving=true;svg.classList.remove('drawing');
  if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);
  $('#teachHint').textContent='Saving box…';
  try{
   if(box[2]-box[0]<1||box[3]-box[1]<1)throw new Error('Box is empty.');
   const result=await post('/api/observations/teach',{path,concept,scope:'bbox',geometry:{bbox:box}});
   const taught={path,concept:result.concept,confidence:1,provider:'human-teach',model:'concept-bank',kind:'bbox',geometry:JSON.stringify(result.geometry)};
   // Use the canonical save receipt: no second query, image reload or viewer rebuild.
   const index=acceptTaughtBox(obs,geometries,taught,result.geometry);
   f.observations=(f.observations||[]).filter(o=>!(o.provider===taught.provider&&o.model===taught.model&&o.kind==='bbox'&&o.concept===taught.concept&&JSON.stringify(geometryOf(o)?.bbox)===JSON.stringify(result.geometry.bbox)));
   f.observations.push(taught);if(pagedBrowse())mobilePager?.remember(f);
   if(S.viewer===path&&v.querySelector('.teachOverlay')===svg){
    const list=v.querySelector('.teachObs');list.querySelector('.tiny')?.remove();
    if(!list.querySelector(`button[data-oi="${index}"]`)){
     const button=document.createElement('button');button.dataset.oi=index;button.textContent=`${taught.concept} · 100% (concept-bank)`;button.title='human-teach · concept-bank';button.onclick=()=>choose(index);list.appendChild(button);
    }
    const existingRect=svg.querySelector(`.teachExisting[data-oi="${index}"]`),rect=existingRect||draft||document.createElementNS('http://www.w3.org/2000/svg','rect');
    if(existingRect&&draft!==existingRect)draft?.remove();
    const [xa,ya,xb,yb]=result.geometry.bbox;rect.setAttribute('x',xa);rect.setAttribute('y',ya);rect.setAttribute('width',xb-xa);rect.setAttribute('height',yb-ya);rect.setAttribute('class','teachExisting');rect.dataset.oi=index;rect.onclick=event=>{event.stopPropagation();choose(index)};if(!rect.parentNode)svg.appendChild(rect);
    choose(index);$('#teachHint').textContent='Box saved · selected for Paint Mask or SAM Mask.';
   }
   S._teachDiscoveryDirty=true;
   if(!S.discovered.some(x=>(x.concept||x)===taught.concept))S.discovered.push({concept:taught.concept,provider:taught.provider,model:taught.model});
  }catch(error){draft?.remove();if(S.viewer===path&&v.querySelector('.teachOverlay')===svg){syncBoundingMode();$('#teachHint').textContent='Box was not saved: '+error.message;}}
  finally{boxSaving=false;}
 };
 v.querySelector('.viewerClose').onclick=closeViewer;v.querySelector('.viewerBackdrop').onclick=closeViewer}
function installViewerDisplayControls(v,path){const panel=v.querySelector('.viewerPanel');if(!panel)return;panel.classList.toggle('viewerStretch',S.viewerStretch);panel.classList.toggle('viewerClean',S.viewerClean);const stretch=v.querySelector('#viewerStretchBtn'),clean=v.querySelector('#viewerCleanBtn'),prev=v.querySelector('#viewerPrevBtn'),next=v.querySelector('#viewerNextBtn');if(stretch){stretch.classList.toggle('active',S.viewerStretch);stretch.onclick=()=>{S.viewerStretch=!S.viewerStretch;panel.classList.toggle('viewerStretch',S.viewerStretch);stretch.classList.toggle('active',S.viewerStretch)}}if(clean){clean.classList.toggle('active',S.viewerClean);clean.onclick=()=>{S.viewerClean=!S.viewerClean;panel.classList.toggle('viewerClean',S.viewerClean);clean.classList.toggle('active',S.viewerClean)}}const multi=S.multiWork.length>1;if(prev){prev.hidden=!multi;prev.onclick=()=>stepMulti(-1)}if(next){next.hidden=!multi;next.onclick=()=>stepMulti(1)}}
function stepMulti(delta){if(!S.multiWork.length)return;S.multiIndex=(S.multiIndex+delta+S.multiWork.length)%S.multiWork.length;openViewer(S.multiWork[S.multiIndex])}
function closeViewer(){const v=$('#imageViewer');if(v){v._viewerResize?.disconnect();v._maskResize?.disconnect();v._maskDispose?.();v._maskDispose=null;v._inspectionCamera?.dispose();v._maskCamera?.dispose();v.classList.remove('open');}S.viewer=null;prepareNeighborhood();pumpRowPrep();scheduleRingPaint();if(S._teachDiscoveryDirty){S._teachDiscoveryDirty=false;refreshDiscovered()}}
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&S.viewer)closeViewer()});
function qualityScore(f){
 const q=(f.observations||[]).filter(o=>o.kind==='quality'&&o.concept==='quality').sort((a,b)=>{
  const av=a.provider==='yuan-iqf-v2'?1:0,bv=b.provider==='yuan-iqf-v2'?1:0;return bv-av;
 })[0];
 if(!q)return '';
 try{
  const g=typeof q.geometry==='string'?JSON.parse(q.geometry):(q.geometry||{});
  const s=Number(g.score);
  if(Number.isFinite(s))return Math.max(0,Math.min(10,s)).toFixed(1);
 }catch(e){}
 const c=Number(q.confidence);
 return Number.isFinite(c)?Math.max(0,Math.min(10,c*10)).toFixed(1):'';
}
// P.38: DOM Ringworld. The archive has ordering, but ordinary browsing has no physical ends.
// A fixed card pool is rebound to logical rows; there is no giant scroll surface to outrun.
S.virtualGrid={files:[],sm:null,cm:null,rows:[],rowH:1,cursor:0,raf:0,wheelCarry:0,poolRows:0,firstLogical:0,rowReady:new Map(),prepGeneration:0,archiveWarmCursor:0,archiveWarmTimer:0,layupEpoch:0,prepDesired:new Set(),prepQueue:[],prepActive:0,layoutCache:null,scoutDir:0,scoutExtra:0,scoutLastMove:0,scoutDecayTimer:0};
function fileAspect(f){
 if(f.width>0&&f.height>0)return Math.max(.18,Math.min(5,f.width/f.height));
 for(const o of(f.observations||[]))try{const g=typeof o.geometry==='string'?JSON.parse(o.geometry):(o.geometry||{}),sz=g.source_size||g.thumbnail_size;if(Array.isArray(sz)&&Number(sz[0])>0&&Number(sz[1])>0)return Math.max(.18,Math.min(5,Number(sz[0])/Number(sz[1])))}catch(e){}
 return 1;
}
function mobileRowHeight(row){return Math.max(1,...(row||[]).map(x=>x.h||1))}
function ringPool(layout,cursor){
 const n=layout.rows.length;if(!S.mobile){const count=Math.min(n,layout.viewRows+4),before=Math.min(2,Math.max(0,count-layout.viewRows));const first=pagedBrowse()?Math.max(0,cursor-before):cursor-before;return {first,count:pagedBrowse()?Math.min(count,n-first):count};}
 const first=Math.max(0,cursor-2);let end=cursor,height=0;
 while(end<n&&height<layout.gh){height+=mobileRowHeight(layout.rows[end])+layout.gap;end++;}
 return {first,count:Math.min(n,end+2)-first};
}
function mobileGridLayout(files,grid,shell){
 const v=S.virtualGrid,gap=Math.max(0,innerWidth*(S.gridGapTenths||0)/1000),columns=mobileColumns(),gw=Math.max(1,grid?.clientWidth||(shell?.clientWidth||innerWidth)-30),gh=Math.max(1,grid?.clientHeight||shell?.clientHeight||innerHeight);
 const cached=v.layoutCache;if(cached?.files===files&&cached.gw===gw&&cached.gap===gap&&cached.columns===columns){cached.gh=gh;return cached;}
 const width=Math.max(1,(gw-gap*2-gap*(columns-1))/columns),rows=[];
 for(let i=0;i<files.length;i+=columns)rows.push(files.slice(i,i+columns).map(f=>({f,w:width,h:Math.max(1,width/(f.width>0&&f.height>0?f.width/f.height:fileAspect(f)))})));
 const rowH=mobileRowHeight(rows[0])+gap,next={g:grid,rows,rowH,viewRows:Math.max(1,Math.ceil(gh/rowH)),files,gw,gh,gap,columns,thumb:width};v.layoutCache=next;return next;
}
function mobileTouchStep(offset,cursor,rows){
 const dir=-Math.sign(offset);let distance=Math.abs(offset),target=cursor;
 while(dir&&target+dir>=0&&target+dir<rows.length){const height=mobileRowHeight(rows[dir>0?target:target-1])+virtualGridLayout(S.virtualGrid.files).gap;if(distance<height/2)break;target+=dir;distance-=height;if(distance<=0)break;}
 return target-cursor;
}
function syncMobileColumnControl(){
 const control=$('#mobileColumns');if(!control)return;control.max=mobileOrientation()==='portrait'?3:8;control.value=mobileColumns();$('#mobileColumnsValue').textContent=String(mobileColumns());
}
async function prepareMobileViewport(anchor){
 const v=S.virtualGrid;v.files=visibleFiles();invalidateRingLayout();const layout=virtualGridLayout(v.files);v.rows=layout.rows;v.rowH=layout.rowH;
 const index=anchor?currentAnchorRow(anchor):-1;v.cursor=index>=0?index:Math.max(0,Math.min(v.cursor,v.rows.length-1));
 v.prepGeneration++;v.rowReady=new Map();v.prepDesired=new Set();v.prepQueue=[];
 const pool=ringPool(layout,v.cursor),required=Array.from({length:pool.count},(_,i)=>pool.first+i);
 for(const ri of required)v.prepDesired.add(rowKey(v.rows[ri]));
 await Promise.all(required.map(prepareRow));
}
async function applyMobileSnapshot(snapshot,anchor,pager){
 if(pager!==mobilePager)return;if(mobileLayoutTask)await mobileLayoutTask;if(pager!==mobilePager)return;
 S.mobileWindowBusy=true;S.touchRingBusy=true;document.body.classList.add('mobileWindowChanging');
 try{
  S.files=snapshot.files;S.mobileNavigationPosition=snapshot.position;await prepareMobileViewport(anchor||S.files[0]?.path);
  if(pager!==mobilePager)return;
  const label=`Images ${snapshot.first+1}–${snapshot.last+1} · ${S.files.length.toLocaleString()} loaded`;
  $('#mobilePagingInfo').textContent=label+' · Search, filters and sort use this window';
  renderScopeFolders();refreshSelectionUI();
  const resident=new Set(S.files.map(f=>canonPath(f.path)));for(const [url,entry] of [...thumbAssets]){
   try{if(resident.has(canonPath(new URL(url,location.href).searchParams.get('path'))))continue;}catch(_){}
   entry.controller?.abort();if(entry.objectUrl)URL.revokeObjectURL(entry.objectUrl);thumbAssets.delete(url);
  }
 }finally{if(pager===mobilePager){S.mobileWindowBusy=false;S.touchRingBusy=false;document.body.classList.remove('mobileWindowChanging');if(S.mobileReflowPending)reflowMobileColumns();else paintRing();}}
}
function maybeRotateMobileWindow(){
 if(!S.mobile&&(S.sortKey!=='none'||S.sortDir!=='asc'||S.semantic||S.compare))return;
 if(!mobilePager||S.viewer||S.mobileWindowBusy||S.touchRingBusy||mobilePageTask)return;
 const v=S.virtualGrid,anchor=v.rows[v.cursor]?.[0]?.f;if(!anchor)return;
 const position=anchor._n8ArchiveIndex,block=Math.floor(position/500),{lo,hi}=mobilePager.range(position);
 if(mobilePager.pages.size===hi-lo+1&&[...mobilePager.pages.keys()].every(k=>k>=lo&&k<=hi))return;
 const pager=mobilePager;mobilePageTask=(async()=>{
  let reversed=false;try{const snapshot=await pager.focus(position);if(!snapshot||pager!==mobilePager)return;
   // Navigation may have reversed while fetching: never install its obsolete window.
   const current=S.virtualGrid.rows[S.virtualGrid.cursor]?.[0]?.f;if(!current)return;
   if(Math.floor(current._n8ArchiveIndex/500)!==block){reversed=true;return;}
   if(snapshot.changed)await applyMobileSnapshot(snapshot,current.path,pager);
  }catch(e){if(e.name!=='AbortError'){$('#status').textContent='Page loading failed: '+e.message;console.warn(e)}}
  finally{mobilePageTask=null;if(reversed&&pager===mobilePager)maybeRotateMobileWindow();}
 })();
}
function reflowMobileColumns(){
 if(!S.mobile)return;syncMobileColumnControl();
 if(S.touchRingBusy||S.mobileWindowBusy||mobileLayoutTask){S.mobileReflowAnchor=S.mobileReflowAnchor||topLeftGridPath();S.mobileReflowPending=true;return;}
 const cached=S.virtualGrid.layoutCache,grid=$('#grid');if(cached?.columns===mobileColumns()&&cached.gw===grid.clientWidth){paintRing();return;}
 const anchor=S.mobileReflowAnchor||topLeftGridPath();S.mobileReflowAnchor=null;S.mobileReflowPending=false;S.touchRingBusy=true;
 mobileLayoutTask=(async()=>{try{await prepareMobileViewport(anchor)}finally{S.touchRingBusy=false;mobileLayoutTask=null;if(S.mobileReflowPending)reflowMobileColumns();else paintRing();}})();
}

function visualRows(fs,usable,thumb,gap){
 const rows=[];let row=[],used=0;
 for(let i=0;i<fs.length;i++){const a=fileAspect(fs[i]),w=Math.max(42,Math.min(usable,thumb*a));if(row.length&&used+gap+w>usable){rows.push(row);row=[];used=0}row.push({f:fs[i],w});used+=w+(row.length>1?gap:0)}
 if(row.length)rows.push(row);return rows;
}
function invalidateRingLayout(){S.virtualGrid.layoutCache=null}
function virtualGridLayout(fs){
 const v=S.virtualGrid,g=$('#grid'),shell=$('#gridShell');if(S.mobile)return mobileGridLayout(fs,g,shell);const thumb=Number($('#thumbSize')?.value)||280,gap=Math.max(0,innerWidth*(S.gridGapTenths||0)/1000);
 const gw=Math.max(g?.clientWidth||0,(shell?.clientWidth||0)-30,280),gh=Math.max(g?.clientHeight||0,shell?.clientHeight||0,thumb),rowH=Math.max(1,thumb+gap),viewRows=Math.max(1,Math.ceil(gh/rowH));
 // P.47: visualRows() walks the entire archive. Doing that on every wheel notch made a
 // 51k-file catalog an O(archive) operation per row step. Cache packing until the actual
 // catalog or geometry changes; Ringworld motion is now O(hot rows), not O(all files).
 const c=v.layoutCache;
 if(c&&c.files===fs&&c.gw===gw&&c.thumb===thumb&&c.gap===gap){c.g=g;c.rowH=rowH;c.viewRows=viewRows;return c}
 const usable=Math.max(1,gw-gap*2),rows=visualRows(fs.filter(f=>!f._n8Tombstone&&!f._n8ForwardTo),usable,thumb,gap),next={g,rows,rowH,viewRows,files:fs,gw,thumb,gap};v.layoutCache=next;return next;
}
function virtualCardParts(f,sm,cm,w){
 const q=qualityScore(f),width=Math.round(w),selected=S.selected.has(f.path);
 if(f._n8ForwardTo){
  const inner=`<div class="thumb tombstoneThumb"><div class="farmMarker"><svg class="movingHandTruck" viewBox="0 0 120 120" width="96" height="96" role="img" aria-label="Laden hand-truck"><title>Moved to a new location</title><g transform="rotate(-16 60 65)"><path d="M85 15h12v65H30" fill="none" stroke="#b9c8d8" stroke-width="7" stroke-linecap="round"/><path d="M35 32h47v43H35z" fill="#d49b52" stroke="#684521" stroke-width="3"/><path d="M45 8h37v24H45z" fill="#edc48b" stroke="#684521" stroke-width="3"/><path d="M61 9v22M59 34v39" stroke="#936932" stroke-width="7"/><circle cx="88" cy="89" r="14" fill="#283748" stroke="#b9c8d8" stroke-width="4"/><circle cx="88" cy="89" r="4" fill="#edc48b"/></g></svg><b>moved to a new location</b><span>left forwarding address</span><span>${esc(f.name)}</span></div></div><div class="detailBadges"><div class="hoverIdentity" title="${esc(f.path)} → ${esc(f._n8ForwardTo)}"><span>${esc(f.name)}</span><span class="qualityScore">forwarded</span></div></div>`;
  return {width,selected:false,inner};
 }
 if(f._n8Tombstone){
  const inner=`<div class="thumb tombstoneThumb"><div class="farmMarker"><b>went to the farm</b><span>${esc(f.name)}</span></div></div><div class="detailBadges"><div class="hoverIdentity" title="${esc(f.path)}"><span>${esc(f.name)}</span><span class="qualityScore">deleted</span></div></div>`;
  return {width,selected:false,inner};
 }
 const inner=`<div class="thumb"><img loading="eager" data-thumb-url="${esc(thumbUrl(f))}">${gridGeometryLayers(f)}</div><div class="detailBadges"><div class="hoverIdentity" title="${esc(f.path)}"><span>${esc(f.name)}</span>${q?`<span class="qualityScore">${q}</span>`:''}</div><div class="badges">${badges(f)}</div></div>${sm?`<div class="semanticScore">semantic ${(sm.get(f.path)*100).toFixed(1)}%</div>`:''}${cm&&cm.has(f.path)?`<div class="semanticScore">${S.compare.kind==='unique'?'unique':'similar'} ${(cm.get(f.path)*100).toFixed(1)}</div>`:''}`;
 return {width,selected,inner};
}
function bindVirtualCard(c){c.onclick=e=>{const f=S.files.find(x=>x.path===c.dataset.p);if(f?._n8ForwardTo){$('#status').textContent=`Moved to ${f._n8ForwardTo} · double-click to follow`;return}select(c.dataset.p,e)};c.ondblclick=e=>{e.preventDefault();const f=S.files.find(x=>x.path===c.dataset.p);if(f?._n8ForwardTo){const dest=f._n8ForwardTo;const parent=dest.slice(0,Math.max(dest.lastIndexOf('\\'),dest.lastIndexOf('/')));navigateTo(parent,false,'forwarding-address');return}inspectRequest(c.dataset.p)}}
function updateVirtualCard(c,f,sm,cm,w){
 const x=virtualCardParts(f,sm,cm,w),cls=`card ${x.selected?'selected':''}`;if(c.className!==cls)c.className=cls;if(c.style.width!==`${x.width}px`)c.style.width=`${x.width}px`;
 if(c._n8Inner!==x.inner){c.innerHTML=x.inner;c._n8Inner=x.inner}c.dataset.p=f.path;if(pendingDeletes.size)paintDeletePending(c,pendingDeletes.has(canonPath(f.path)));return c;
}
function newVirtualCard(){const c=document.createElement('div');bindVirtualCard(c);return c}
function mod(n,m){return ((n%m)+m)%m}
function bindRingRow(row,spec,ri){
 row=row||document.createElement('div');row.className='visualRow';row.dataset.row=ri;
 const existing=[...row.querySelectorAll('.card')],cards=[];
 for(let i=0;i<spec.length;i++){const x=spec[i],c=existing[i]||newVirtualCard();updateVirtualCard(c,x.f,S.virtualGrid.sm,S.virtualGrid.cm,x.w);if(S.mobile)c.style.height=`${x.h}px`;cards.push(c)}
 if(S.mobile)row.style.height=`${mobileRowHeight(spec)}px`;row.replaceChildren(...cards);return row;
}
function thumbUrl(f){return `/api/thumb?path=${enc(f.path)}&v=${encodeURIComponent(f.mtime||0)}&r=${S.gridRedrawEpoch||0}`}
function topLeftGridPath(){if(S.mobile)return S.virtualGrid.rows?.[S.virtualGrid.cursor]?.[0]?.f?.path||null;const c=$('#grid .visualRow .card');return c?.dataset?.p||S.virtualGrid.rows?.[S.virtualGrid.cursor]?.[0]?.f?.path||null}
function tempHomePath(){const fs=visibleFiles(),raw=topLeftGridPath();if(!fs.length)return null;let i=Math.max(0,fs.findIndex(f=>f.path===raw));for(let n=i;n<fs.length;n++)if(!fs[n]._n8Tombstone)return fs[n].path;for(let n=i-1;n>=0;n--)if(!fs[n]._n8Tombstone)return fs[n].path;return null}
function pinTempHome(path){if(!path)return false;const ri=currentAnchorRow(path);if(ri<0)return false;S.virtualGrid.cursor=ri;return true}
function forgetCurrentThumbAssets(paths){const wanted=new Set((paths||[]).map(f=>canonPath(f.path)));for(const [url,e] of [...thumbAssets.entries()]){let hit=false;try{const q=new URL(url,location.href).searchParams.get('path');hit=q&&wanted.has(canonPath(q))}catch(_){}if(!hit)continue;thumbAssets.delete(url);if(e?.objectUrl)URL.revokeObjectURL(e.objectUrl)}}
// P.45 hard brake: a thumbnail URL gets one browser fetch while it remains in the bounded asset rack.
// Prefab reconstruction must not turn into another /api/thumb request storm.
const thumbAssets=new Map(),THUMB_ASSET_LIMIT=S.mobile?96:2048;
function trimThumbAssets(){
 while(thumbAssets.size>THUMB_ASSET_LIMIT){const [url,e]=thumbAssets.entries().next().value;if(!e||e.state==='loading')break;thumbAssets.delete(url);if(e.objectUrl)URL.revokeObjectURL(e.objectUrl)}
}
function thumbnailFetch(url, options={}){
 const token=credential();
 return fetch(url,{...options,headers:{...(options.headers||{}),...(token?{'X-N8Vision-Credential':token}:{})}});
}
function ensureThumbAsset(url){
 let e=thumbAssets.get(url);if(e){e.touched=performance.now();return e.promise}
 e={state:'loading',objectUrl:null,touched:performance.now(),promise:null,controller:new AbortController()};
 e.promise=thumbnailFetch(url,{cache:'force-cache',signal:e.controller.signal}).then(r=>{if(!r.ok)throw new Error(`thumb ${r.status}`);return r.blob()}).then(blob=>{
   e.objectUrl=URL.createObjectURL(blob);e.state='ready';thumbAssets.delete(url);thumbAssets.set(url,e);trimThumbAssets();return e.objectUrl
 }).catch(err=>{if(thumbAssets.get(url)===e)thumbAssets.delete(url);throw err});
 thumbAssets.set(url,e);return e.promise;
}
async function hydratePrefabImage(im){
 const url=im.dataset.thumbUrl;if(!url)return true;
 // Never touch src again once this exact prefab image has been hydrated.
 if(im.dataset.thumbHydrated===url&&im.complete&&im.naturalWidth)return true;
 try{const objectUrl=await ensureThumbAsset(url);if(im.dataset.thumbHydrated!==url){im.src=objectUrl;im.dataset.thumbHydrated=url}
   if(!im.complete)await new Promise(resolve=>{im.addEventListener('load',resolve,{once:true});im.addEventListener('error',resolve,{once:true})});
   if(im.naturalWidth&&im.decode)try{await im.decode()}catch(e){};return !!im.naturalWidth
 }catch(e){im.dataset.thumbFailed=url;if(e.name==='AbortError')im.dataset.thumbAborted='1';return false}
}
function rowKey(spec){return spec.map(x=>`${x.f.path}\u001f${x.f.mtime||0}\u001f${x.f._n8Tombstone?'farm':x.f._n8ForwardTo?'forward':'live'}`).join('\u001e')}
function rowReady(ri){const v=S.virtualGrid,n=v.rows.length;if(!n)return false;const spec=v.rows[mod(ri,n)],e=v.rowReady.get(rowKey(spec));return e?.state==='ready'&&!!e.node}
function prepareRow(ri){
 const v=S.virtualGrid,n=v.rows.length;if(!n)return Promise.resolve(false);ri=mod(ri,n);const spec=v.rows[ri],key=rowKey(spec),old=v.rowReady.get(key);if(old)return old.promise;
 const generation=v.prepGeneration,entry={state:'warming',node:null,promise:null};
 entry.promise=(async()=>{
   // Build once, off-stage. A READY row is thereafter inert: no polling, reconciliation or rebinding.
   const row=bindRingRow(null,spec,ri),imgs=[...row.querySelectorAll('img')];
   await Promise.all(imgs.map(hydratePrefabImage));
   if(generation!==v.prepGeneration||v.rowReady.get(key)!==entry)return false;
   if(S.viewer||imgs.some(im=>im.dataset.thumbAborted==='1')){v.rowReady.delete(key);return false;}
   // If the read head moved away while this row was cooking, release the whole constructed row now.
   if(!v.prepDesired.has(key)){v.rowReady.delete(key);return false}
   entry.node=row;entry.state='ready';scheduleRingPaint();return true;
 })();
 v.rowReady.set(key,entry);return entry.promise;
}
function pumpRowPrep(){
 if(S.viewer||S.touchRingBusy)return;
 const v=S.virtualGrid,limit=3;
 while(v.prepActive<limit&&v.prepQueue.length){
  const ri=v.prepQueue.shift(),n=v.rows.length;if(!n)break;const key=rowKey(v.rows[mod(ri,n)]);
  if(!v.prepDesired.has(key)||rowReady(ri))continue;
  v.prepActive++;prepareRow(ri).finally(()=>{v.prepActive--;pumpRowPrep()});
 }
}
function prepareNeighborhood(){
 if(S.touchRingBusy)return;
 const v=S.virtualGrid,n=v.rows.length;if(!n)return;const flank=S.mobile?4:Math.max(1,S.ringBufferRows||50),bias=Math.max(1,S.ringSouthBias||2),seen=new Set(),q=[];
 const add=ri=>{if(pagedBrowse()&&(ri<0||ri>=n))return;ri=mod(ri,n);if(!seen.has(ri)){seen.add(ri);q.push(ri)}};add(v.cursor);{const pool=ringPool(virtualGridLayout(v.files),v.cursor);for(let i=0;i<pool.count;i++)add(pool.first+i);}
 // P.48 scouts: the neutral rack remains ±flank, but committed motion stretches the runway
 // beyond the read head. One consumed row exposes the normal new edge plus one speculative
 // row, so sustained travel prepares two fresh rows for every row consumed.
 const extra=Math.max(0,v.scoutExtra||0),southMax=flank+(v.scoutDir>0?extra:0),northMax=flank+(v.scoutDir<0?extra:0);
 let south=1,north=1;
 // Active direction gets first claim on the prep queue. Neutral/background fill retains 2S:1N.
 if(v.scoutDir>0){while(south<=southMax)add(v.cursor+south++);while(north<=northMax)add(v.cursor-north++)}
 else if(v.scoutDir<0){while(north<=northMax)add(v.cursor-north++);while(south<=southMax)add(v.cursor+south++)}
 else{while(south<=southMax){for(let k=0;k<bias&&south<=southMax;k++,south++)add(v.cursor+south);if(north<=northMax)add(v.cursor-north++)}while(north<=northMax)add(v.cursor-north++)}
 v.layupEpoch++;v.prepDesired=new Set(q.map(ri=>rowKey(v.rows[ri])));
 for(const [key,e] of [...v.rowReady.entries()])if(!v.prepDesired.has(key)&&e.state==='ready')v.rowReady.delete(key);
 v.prepQueue=q.filter(ri=>!rowReady(ri));pumpRowPrep();
}
function armScoutDecay(){
 const v=S.virtualGrid;if(v.scoutDecayTimer)clearTimeout(v.scoutDecayTimer);
 v.scoutDecayTimer=setTimeout(function decay(){
  v.scoutDecayTimer=0;const idle=performance.now()-(v.scoutLastMove||0);
  if(idle<3000){v.scoutDecayTimer=setTimeout(decay,Math.max(50,3000-idle));return}
  if(v.scoutExtra>0){v.scoutExtra--;prepareNeighborhood();v.scoutDecayTimer=setTimeout(decay,1000)}
  else v.scoutDir=0;
 },3000);
}
function reportRingMovement(dir){
 const v=S.virtualGrid;dir=Math.sign(dir);if(!dir)return;if(pagedBrowse()){S.mobileNavigationDirty=true;S.mobileNavigationPosition=v.rows[v.cursor]?.[0]?.f?._n8ArchiveIndex;}
 if(v.scoutDir!==dir)v.scoutExtra=0;
 v.scoutDir=dir;v.scoutExtra=Math.min(Math.max(1,S.ringBufferRows||50),v.scoutExtra+1);v.scoutLastMove=performance.now();armScoutDecay();
}
async function warmThumbRow(ri){
 const v=S.virtualGrid,n=v.rows.length;if(!n)return;const spec=v.rows[mod(ri,n)];
 // Archive warming fills the HTTP/disk thumbnail drawer only. It never constructs DOM rows.
 await Promise.all(spec.filter(x=>!x.f._n8Tombstone).map(x=>thumbnailFetch(thumbUrl(x.f),{cache:'force-cache'}).then(r=>{if(!r.ok)throw new Error(`thumb ${r.status}`);return r.arrayBuffer()}).catch(()=>null)));
}
function scheduleArchiveWarm(){
 // P.45: disabled in-browser archive sweep. Foreground prefab demand is the only browser thumbnail producer.
 return;
 const v=S.virtualGrid;if(!S.thumbWarmEnabled||v.archiveWarmTimer||!v.rows.length)return;
 const generation=v.prepGeneration,idle=window.requestIdleCallback||((fn)=>setTimeout(()=>fn({timeRemaining:()=>8}),80));
 v.archiveWarmTimer=idle(()=>{v.archiveWarmTimer=0;if(generation!==v.prepGeneration)return;const n=v.rows.length;if(!n)return;const ri=mod(v.archiveWarmCursor++,n);warmThumbRow(ri).finally(()=>{if(generation===v.prepGeneration)scheduleArchiveWarm()})});
}
function warmArchiveTail(){scheduleArchiveWarm()}
function positionRingPool(){
 const v=S.virtualGrid,g=$('#grid'),rows=[...g.querySelectorAll('.visualRow')];for(const r of rows)r.style.marginTop='';
 if(S.mobile){if(rows.length){let height=0;for(let i=v.firstLogical;i<v.cursor;i++)height+=mobileRowHeight(v.rows[i])+virtualGridLayout(v.files).gap;rows[0].style.marginTop=`${-height}px`;}return;}
 if(rows.length){const l=virtualGridLayout(v.files||[]),before=v.cursor-v.firstLogical;rows[0].style.marginTop=`${-before*l.rowH}px`}
}
// I.2t-d: placeholders belong to the cached layout. Scrolling and buffer
// eviction never retire records or repack rows; ordinary layout rebuilds do.
function readyRingPool(pool,cursor,isReady){
 if(!pool.count||!isReady(cursor))return null;
 let first=cursor,end=cursor+1;
 while(first>pool.first&&isReady(first-1))first--;
 while(end<pool.first+pool.count&&isReady(end))end++;
 return {first,count:end-first};
}
function paintRing(){
 if(S.viewer||S.touchRingBusy)return;
 // Reconcile a renamed filename only after its old card has left the hot DOM.
 // Never restart the archive browse or resort while the user is looking at it.
 if(S._n8LazyRenames?.size){
  const hot=new Set([...document.querySelectorAll('#grid .card')].map(c=>canonPath(c.dataset.p)));
  if([...S._n8LazyRenames].every(p=>!hot.has(p))){
   // Reorder the cached records, not the application. No render(), load(),
   // temp_home, or DOM replacement on behalf of the rename.
   const v=S.virtualGrid,anchor=$('#grid .visualRow .card')?.dataset.p;
   const pending=new Set(S._n8LazyRenames);S._n8LazyRenames.clear();
   if(S.sortKey==='filename'||S.sortKey==='none'){
    const compare=(a,b)=>S.sortKey==='filename'?(S.sortDir==='desc'?-1:1)*a.name.localeCompare(b.name,undefined,{sensitivity:'base'}):0;
    // The browse-order (none) does not need reshuffling.
    if(S.sortKey==='filename')for(const path of pending){
     const old=v.files.findIndex(f=>canonPath(f.path)===path);
     if(old<0)continue;
     const [file]=v.files.splice(old,1);
     let lo=0,hi=v.files.length;
     while(lo<hi){const mid=(lo+hi)>>1;if(compare(v.files[mid],file)<=0)lo=mid+1;else hi=mid}
     v.files.splice(lo,0,file);
    }
    // Existing DOM nodes stay mounted. Only the row descriptions change.
    // The next ordinary scroll will request the newly indexed offstage rows.
    if(S.sortKey==='filename'){
     invalidateRingLayout();const layout=virtualGridLayout(v.files);v.rows=layout.rows;
     if(anchor){const ri=v.rows.findIndex(row=>row.some(x=>canonPath(x.f.path)===canonPath(anchor)));if(ri>=0)v.cursor=ri;}
    }
   }
  }
 }
 const v=S.virtualGrid,l=virtualGridLayout(v.files||[]),g=l.g;v.rows=l.rows;v.rowH=l.rowH;
 if(!l.rows.length){g.replaceChildren();updateArchiveNavigator();return}
 v.cursor=pagedBrowse()?Math.max(0,Math.min(v.cursor,l.rows.length-1)):mod(v.cursor,l.rows.length);prepareNeighborhood();
 // Hot DOM is deliberately tiny. The ±50 layup lives in the READY drawer, not on stage.
 const requested=ringPool(l,v.cursor);
 // A completed focal row can appear immediately; offscreen buffer rows cannot gate it.
 const ready=readyRingPool(requested,v.cursor,rowReady);
 if(!ready){prepareRow(v.cursor);return}
 const poolRows=ready.count,first=ready.first;
 const wanted=[];
 for(let k=0;k<poolRows;k++){const ri=mod(first+k,l.rows.length),spec=l.rows[ri],entry=v.rowReady.get(rowKey(spec));if(!entry?.node)return;wanted.push(entry.node)}
 // The viewport receives already-constructed rows. No thumbnail assignment occurs here.
 g.replaceChildren(...wanted);gridFirstPaint();v.poolRows=poolRows;v.firstLogical=first;positionRingPool();syncGeometryViews();updateArchiveNavigator();scheduleArchiveWarm();if(pagedBrowse()&&S.mobileNavigationDirty){S.mobileNavigationDirty=false;maybeRotateMobileWindow();}
}
function scheduleRingPaint(){const v=S.virtualGrid;if(v.raf)return;v.raf=requestAnimationFrame(()=>{v.raf=0;paintRing()})}
function moveRingRows(delta){
 gridActivity('ring-row');
 const v=S.virtualGrid,n=v.rows.length;if(!n||!delta)return;const dir=Math.sign(delta),target=pagedBrowse()?Math.max(0,Math.min(n-1,v.cursor+dir)):mod(v.cursor+dir,n);
 // Row-at-a-time on purpose. If the next completed prefab is not in the drawer, stop at the frontier.
 if(!rowReady(target)){prepareRow(target);prepareNeighborhood();return}
 recordSelectionRingMove(v.cursor,dir);v.cursor=target;reportRingMovement(dir);paintRing();
}
function renderVirtualGrid(){paintRing()}
function render(){
 const fs=visibleFiles(),g=$('#grid');if(!S.imageGridEnabled){g.replaceChildren();S.virtualGrid.files=[];$('#selCount').textContent=S.selected.size;$('#counts').textContent=`Selected ${S.selected.size.toLocaleString()} · Shown ${fs.length.toLocaleString()} · ${pagedBrowse()?'Loaded':'Total'} ${S.files.length.toLocaleString()}`;updateFilterButton();updateArchiveNavigator();return}
 const old=S.virtualGrid.files;S.virtualGrid.files=fs;if(old!==fs)invalidateRingLayout();S.virtualGrid.sm=S.semantic?new Map(S.semantic.map(x=>[x.path,x.score])):null;S.virtualGrid.cm=S.compare?new Map(S.compare.results.map(x=>[x.path,x.score])):null;
 const structural=old.length!==fs.length||old.some((f,i)=>fs[i]?.path!==f.path);
 if(structural&&old.length===0)S.virtualGrid.cursor=0;
 paintRing();
 $('#selCount').textContent=S.selected.size;$('#counts').textContent=`Selected ${S.selected.size.toLocaleString()} · Shown ${fs.length.toLocaleString()} · ${pagedBrowse()?'Loaded':'Total'} ${S.files.length.toLocaleString()}`;updateFilterButton()
}
function scheduleVirtualGrid(){const v=S.virtualGrid;if(v.raf)return;v.raf=requestAnimationFrame(()=>{v.raf=0;paintRing()})}

// Archive navigator: center-resting vector control plus absolute teleport rail and filtered anchors.
S.archiveAnchors=new Set(JSON.parse(localStorage.getItem('n8vision.archiveAnchors')||'[]'));
S.archiveNavZoom=null;
function saveArchiveAnchors(){localStorage.setItem('n8vision.archiveAnchors',JSON.stringify([...S.archiveAnchors]))}
function currentAnchorRow(path){
 const rows=S.virtualGrid.rows;for(let i=0;i<rows.length;i++)if(rows[i].some(x=>x.f.path===path))return i;return -1;
}
function archiveNavRange(){const n=S.virtualGrid.rows.length;if(!n)return [0,0];if(!S.archiveNavZoom)return [0,n-1];return [Math.max(0,Math.min(n-1,S.archiveNavZoom[0])),Math.max(0,Math.min(n-1,S.archiveNavZoom[1]))]}
function autoZoomAnchors(focusPath){
 const n=S.virtualGrid.rows.length,track=$('#archiveTrack'),focus=currentAnchorRow(focusPath);if(!n||!track||focus<0){S.archiveNavZoom=null;return}
 const pts=[...S.archiveAnchors].map(currentAnchorRow).filter(x=>x>=0).sort((a,b)=>a-b);let lo=0,hi=n-1,h=Math.max(80,track.clientHeight);
 for(let pass=0;pass<12;pass++){const q=pts.filter(x=>x>=lo&&x<=hi),span=Math.max(1,hi-lo),crowded=q.some((x,i)=>i&&((x-q[i-1])*h/span)<8);if(!crowded)break;const half=Math.max(8,Math.floor(span/4));lo=Math.max(0,focus-half);hi=Math.min(n-1,focus+half)}
 S.archiveNavZoom=(lo===0&&hi===n-1)?null:[lo,hi];
}
function updateArchiveNavigator(){
 const track=$('#archiveTrack'),marks=$('#archiveMarks');if(!track||!marks)return;const n=S.virtualGrid.rows.length;marks.replaceChildren();if(!n)return;const [lo,hi]=archiveNavRange(),span=Math.max(1,hi-lo);
 const visible=[...S.archiveAnchors].map(p=>({p,row:currentAnchorRow(p)})).filter(x=>x.row>=lo&&x.row<=hi);
 const last=rootLastLook.get(rootCatalogKey(S.scopeRoot,S.catalogRecursive));
 const lastRow=last?currentAnchorRow(last):-1;
 if(lastRow>=lo&&lastRow<=hi){const marker=document.createElement('button');marker.type='button';marker.className='archiveMark n8LastLook';marker.style.top=`${100*(lastRow-lo)/span}%`;marker.style.background='#e6aa4a';marker.style.borderColor='#fff0bf';marker.style.zIndex='2';marker.title='Last Look · '+last;marker.setAttribute('aria-label','Return to last look');marker.onclick=e=>{e.stopPropagation();prepareRow(lastRow).then(()=>{S.virtualGrid.selectionRing=null;S.virtualGrid.cursor=lastRow;paintRing()})};marks.appendChild(marker)}
 for(const a of visible){const b=document.createElement('button');b.type='button';b.className='archiveMark';b.style.top=`${100*(a.row-lo)/span}%`;b.title=a.p;b.onclick=e=>{e.stopPropagation();gridActivity('anchor-teleport');prepareRow(a.row).then(()=>{S.virtualGrid.selectionRing=null;S.virtualGrid.cursor=a.row;paintRing()})};b.onmouseenter=()=>showArchivePreview(a.p,b);b.onmouseleave=hideArchivePreview;marks.appendChild(b)}
 track.classList.toggle('zoomed',!!S.archiveNavZoom);
}
function showArchivePreview(path,mark){
 const p=$('#archivePreview'),img=p?.querySelector('img'),lab=p?.querySelector('span'),f=S.virtualGrid.files.find(x=>x.path===path);if(!p||!f)return;img.src=`/api/thumb?path=${enc(path)}&v=${encodeURIComponent(f.mtime||0)}`;lab.textContent=f.name;p.hidden=false;p.style.top=`${Math.max(0,Math.min(90,parseFloat(mark.style.top)||0))}%`;
}
function hideArchivePreview(){const p=$('#archivePreview');if(p)p.hidden=true}
function teleportArchive(frac){gridActivity('ring-teleport');
 const rows=S.virtualGrid.rows;if(!rows.length)return;const [lo,hi]=archiveNavRange(),target=Math.max(lo,Math.min(hi,Math.round(lo+frac*(hi-lo))));prepareRow(target).then(()=>{S.virtualGrid.selectionRing=null;S.virtualGrid.cursor=target;if(pagedBrowse()){S.mobileNavigationDirty=true;S.mobileNavigationPosition=S.virtualGrid.rows[S.virtualGrid.cursor]?.[0]?.f?._n8ArchiveIndex;}paintRing()});
}
function setupArchiveNavigator(){
 const grid=$('#grid'),track=$('#archiveTrack'),vector=$('#archiveVector'),add=$('#archiveAnchorAdd'),whole=$('#archiveWhole');if(!grid||!track||!vector)return;
 grid.addEventListener('wheel',e=>{e.preventDefault();if(e.deltaY)moveRingRows(Math.sign(e.deltaY))},{passive:false});
 track.addEventListener('click',e=>{if(e.target===vector||e.target.classList.contains('archiveMark'))return;const r=track.getBoundingClientRect();teleportArchive((e.clientY-r.top)/Math.max(1,r.height))});
 add.onclick=()=>{const p=S.selectionAnchor;if(!p)return;if(S.archiveAnchors.has(p)){S.archiveAnchors.delete(p);S.archiveNavZoom=null}else{S.archiveAnchors.add(p);autoZoomAnchors(p)}saveArchiveAnchors();updateArchiveNavigator()};
 whole.onclick=()=>{S.archiveNavZoom=null;updateArchiveNavigator()};
 let dragging=false,velocity=0,frame=0,last=0;
 const tick=t=>{if(!dragging)return;if(!last)last=t;if(t-last>45&&Math.abs(velocity)>.05){moveRingRows(Math.sign(velocity));last=t}frame=requestAnimationFrame(tick)};
 vector.addEventListener('pointerdown',e=>{dragging=true;velocity=0;last=0;vector.setPointerCapture(e.pointerId);frame=requestAnimationFrame(tick);e.preventDefault()});
 vector.addEventListener('pointermove',e=>{if(!dragging)return;const r=track.getBoundingClientRect(),mid=r.top+r.height/2,half=Math.max(1,r.height/2-12);velocity=Math.max(-1,Math.min(1,(e.clientY-mid)/half));vector.style.top=`${50+velocity*45}%`});
 const stop=()=>{dragging=false;velocity=0;last=0;cancelAnimationFrame(frame);vector.style.top='50%'};
 vector.addEventListener('pointerup',stop);vector.addEventListener('pointercancel',stop);
}
function refreshSelectionUI(changed=null){const cards=changed?Array.from(changed,p=>document.querySelector(`#grid .card[data-p=\"${CSS.escape(p)}\"]`)).filter(Boolean):document.querySelectorAll('#grid .card');cards.forEach(c=>c.classList.toggle('selected',S.selected.has(c.dataset.p)));$('#selCount').textContent=S.selected.size;const clear=$('#clearSelectedBtn');if(clear)clear.disabled=!S.selected.size;const shown=S.virtualGrid.files.length;$('#counts').textContent=`Selected ${S.selected.size.toLocaleString()} · Shown ${shown.toLocaleString()} · ${pagedBrowse()?'Loaded':'Total'} ${S.files.length.toLocaleString()}`}
function ringSelectionPosition(path){
 if(pagedBrowse())return null;
 const v=S.virtualGrid,n=v.rows.length,index=v.files.findIndex(f=>f.path===path);
 if(!n||index<0)return null;
 if(v.selectionRing?.rows!==v.rows)v.selectionRing={rows:v.rows,turn:0};
 const row=v.rows.findIndex(spec=>spec.some(x=>x.f.path===path));
 const logical=v.firstLogical+mod(row-v.firstLogical,n);
 return {ring:v.selectionRing,position:index+(v.selectionRing.turn+Math.floor(logical/n))*v.files.length};
}
function recordSelectionRingMove(from,step){
 const v=S.virtualGrid,n=v.rows.length;
 if(pagedBrowse()||!n)return;
 if(v.selectionRing?.rows!==v.rows)v.selectionRing={rows:v.rows,turn:0};
 v.selectionRing.turn+=Math.floor((from+step)/n);
}
function selectionViewKey(){return JSON.stringify([S.path,S.scopeRoot,S.scopeRecursive,[...S.scopeSelections||[]],S.sortKey,S.sortDir,$('#search').value,$('#minConfidence').value,[...S.magnets.values()].map(m=>[m.key,m.mode,m.op,m.count])])}
function select(p,e={}){
 if(S.suppressClickUntil&&performance.now()<S.suppressClickUntil)return;
 if(moveQueue.has(p)){$('#status').textContent='This image is already queued for moving';return;}
 observationRefreshController?.abort();const request=S.selectionRequest=(S.selectionRequest||0)+1,shift=!!(e.shiftKey||S.softShift),changed=new Set();
 if(shift){e.preventDefault?.();window.getSelection()?.removeAllRanges()}
 if(shift&&S.selectionAnchor){
  const anchorRing=S.selectionAnchorMeta?.ringPosition,targetRing=ringSelectionPosition(p);
  const positions=anchorRing&&targetRing&&anchorRing.ring===targetRing.ring&&S.selectionAnchorMeta.key===selectionViewKey()?{anchor:anchorRing.position,target:targetRing.position}:null;
  const range=inclusiveCatalogRange(S.virtualGrid.files,S.selectionAnchor,p,positions);
  if(range){for(const path of range){if(moveQueue.has(path))continue;S.selected.add(path);changed.add(path)}}
  else{
   const anchor=S.selectionAnchorMeta,target=S.files.find(f=>f.path===p),key=selectionViewKey();
   const plain=S.sortKey==='none'&&!S.semantic&&!S.compare&&!$('#search').value.trim()&&![...S.magnets.values()].some(m=>m.mode!=='0')&&!(S.scopeSelections?.size);
   if(plain&&mobilePager&&anchor?.tx===S.mobileBrowseTx&&anchor.key===key&&Number.isInteger(anchor.index)&&Number.isInteger(target?._n8ArchiveIndex)){
    const pager=mobilePager,tx=S.mobileBrowseTx,lo=Math.min(anchor.index,target._n8ArchiveIndex),hi=Math.max(anchor.index,target._n8ArchiveIndex);
    $('#status').textContent='Selecting inclusive range…';
    j(`/api/browse/range?tx=${enc(tx)}&first=${lo}&last=${hi}`).then(result=>{
     if(S.selectionRequest!==request||mobilePager!==pager||S.mobileBrowseTx!==tx||S.semantic||S.compare||selectionViewKey()!==key)return;
     for(const item of result.paths){const file=pager.restore({path:item.path,_n8ArchiveIndex:item.index});if(!file._n8Tombstone&&!file._n8ForwardTo&&!moveQueue.has(file.path))S.selected.add(file.path)}
     refreshSelectionUI();$('#status').textContent='Inclusive range selected · '+result.paths.length.toLocaleString()+' archive positions';
    }).catch(error=>{if(S.selectionRequest===request)$('#status').textContent='Range selection failed: '+error.message});
   }else $('#status').textContent='Selection anchor is outside this view. Clear selection or choose the anchor again; no range guessed.';
  }
 }else{
  S.selected.has(p)?S.selected.delete(p):S.selected.add(p);changed.add(p);S.selectionAnchor=p;
  const file=S.files.find(f=>f.path===p);S.selectionAnchorMeta={tx:S.mobileBrowseTx,index:file?._n8ArchiveIndex,key:selectionViewKey(),ringPosition:ringSelectionPosition(p)};
 }
 consumeSoftModifiers();refreshSelectionUI(changed);
}
installGridSelectionGuard($('#grid'));

function consumeSoftModifiers(){if(S.softCtrl||S.softShift){S.softCtrl=false;S.softShift=false;updateSoftModifiers()}}
function inspectRequest(path){if(S.selected.size<=1)return openViewer(path);const old=$('#multiChoice');if(old)old.remove();const d=document.createElement('div');d.id='multiChoice';d.className='multiChoice';d.innerHTML=`<div class="multiChoiceCard"><b>Inspect selection</b><div>${S.selected.size} images selected.</div><div class="buttonGrid"><button id="inspectSingle">Single</button><button id="inspectMulti" title="Yeah, all the images I selected. I want to look at them all a bit closer for whatever reason.">Multi-Work</button></div></div>`;document.body.appendChild(d);$('#inspectSingle').onclick=()=>{d.remove();openViewer(path)};$('#inspectMulti').onclick=()=>{d.remove();const q=S.virtualGrid.files.filter(f=>S.selected.has(f.path)).map(f=>f.path),i=Math.max(0,q.indexOf(path));S.multiWork=q;S.multiIndex=i;openViewer(q[i])}}
async function post(url,obj){try{return await j(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)})}catch(e){alert(e.message);throw e}}
async function stopAnalysis(){try{const r=await post('/api/jobs/stop-analysis',{});$('#status').textContent=r.requested?`Stop requested for ${r.requested} analysis job${r.requested===1?'':'s'}; current image will finish first.`:'No active analysis jobs.';await refreshJobs()}catch(e){alert(e.message)}}
const stopA=$('#stopAnalysisBtn'),stopB=$('#orderingStopAnalysisBtn');if(stopA)stopA.onclick=stopAnalysis;if(stopB)stopB.onclick=stopAnalysis;

function labels(){return $('#classLabels').value.split(/[\n,]+/).map(x=>x.trim()).filter(Boolean)}async function job(kind,paths,extra={}){if(!paths.length)return alert('No images in this view.');const r=await post('/api/jobs',{kind,paths,...extra});$('#status').textContent=`${kind} job ${r.id} started`;refreshJobs()}

async function startQuality(){
 // First-pass inspection is now native Sanity. Yuan remains available as an explicit quality tool.
 if(!S.files.length)return;
 S.qualityPath=S.path;
 try{
  const r=await post('/api/native/raster-sanity-v4',{paths:S.files.map(x=>x.path),thumbnail:256,edge_threshold:24,light_blur:1,medium_blur:2.5,heavy_blur:4,force:false});
  if(r.state!=='done')$('#status').textContent=`Sanity ${r.id}: inspecting ${r.total||S.files.length} image${(r.total||S.files.length)===1?'':'s'}`;
 }catch(e){console.warn('Sanity start failed',e)}
}
let observationRefreshController=null;
async function refreshObservations(preserveLayout=false){
 if(!S.files.length||S.viewer)return;
 const controller=new AbortController();observationRefreshController?.abort();observationRefreshController=controller;
 try{
  // Observation refresh is background telemetry. Never route a transient/empty response
  // through post(), whose alert is appropriate for explicit user actions.
  const files=S.files,targets=new Map();let revision=null;
  for(const f of files)targets.set(f.path,new Set([f]));
  for(const catalog of rootCatalogs.values())for(const f of catalog.files||[])if(targets.has(f.path))targets.get(f.path).add(f);
  for(let start=0;start<files.length;start+=50){
   if(controller.signal.aborted||S.viewer||files!==S.files)return;
   const packet=await j('/api/observations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths:files.slice(start,start+50).map(x=>x.path)}),signal:controller.signal});
   if(controller.signal.aborted||S.viewer||files!==S.files)return;
   // Only certify the first revision observed: later writes may affect prior batches.
   revision??=packet.revision;
   for(const [path,observations] of Object.entries(packet.observations||{})){for(const f of targets.get(path)||[])f.observations=observations;mobilePager?.rememberObservations(path,observations)}
   await new Promise(resolve=>setTimeout(resolve,0));
  }
  const r={revision};
  S.obsRevision=String(r.revision??S.obsRevision).split('-')[0]+'-'+assetEpoch;if(preserveLayout){
   const files=new Map(S.files.map(f=>[f.path,f]));
   for(const entry of S.virtualGrid.rowReady.values()){
    if(controller.signal.aborted||S.viewer)return;
    for(const card of entry.node?.querySelectorAll('.card')||[]){
     const f=files.get(card.dataset.p);if(!f)continue;
     const box=card.querySelector('.badges');if(box)box.innerHTML=badges(f);
     const identity=card.querySelector('.hoverIdentity'),q=qualityScore(f);
     if(identity)identity.innerHTML=`<span>${esc(f.name)}</span>${q?`<span class="qualityScore">${q}</span>`:''}`;
    }
    await new Promise(resolve=>setTimeout(resolve,0));
   }
   refreshSelectionUI();
  }else render();S.catalogObsRevision=Number(r.revision??S.catalogObsRevision??0);refreshDiscovered();
 }catch(e){if(e.name!=='AbortError')console.warn('Observation refresh failed',e)}finally{if(observationRefreshController===controller)observationRefreshController=null}
}
function fmtEta(sec){if(sec==null||!isFinite(sec))return'';sec=Math.max(0,Math.round(sec));const h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),q=sec%60;return h?`${h}h ${m}m ETA`:m?`${m}m ${q}s ETA`:`${q}s ETA`}
async function refreshJobsCore(){const r=await j('/api/jobs');for(const job of r.jobs){if(job.kind!=='subject-class-recognition'||job.state!=='done'||!job.result?.summary)continue;S.seenRecognitionJobs??=new Set();if(S.seenRecognitionJobs.has(job.id))continue;await synchronizeRecognitionPaths(job.result.paths||[]);await S.refreshRecognitionInspector?.(job.result.paths||[]);S.seenRecognitionJobs.add(job.id);$('#status').textContent=job.result.summary;if(job.result.applied)refreshDiscovered()}const active=r.jobs.some(x=>x.state==='queued'||x.state==='running'||x.state==='recovering');const jobHost=(S.mode==='ordering'?$('#orderingJobs'):$('#jobs'));const jobHTML=r.jobs.length?r.jobs.slice(0,6).map(x=>{const verifying=x.phase==='verifying';const rate=!verifying&&x.items_per_second!=null?` · ${Number(x.items_per_second).toFixed(Number(x.items_per_second)>=10?1:2)} p/s`:'';const eta=!verifying&&x.state==='running'&&x.eta_seconds!=null?` · ${fmtEta(x.eta_seconds)}`:'';const phase=(x.kind==='subject-class-training'||x.kind==='subject-class-recognition')?` · ${esc(x.result?.summary||x.phase||x.state)}`:verifying?' · verifying…':x.phase==='recovering'?' · recovering…':'';const tel=x.telemetry?`<br><span class="tiny">${esc(x.telemetry.device||'')} ${x.telemetry.model_device?`· model ${esc(x.telemetry.model_device)}`:''} ${x.telemetry.model_dtype?`· ${esc(x.telemetry.model_dtype)}`:''}${x.telemetry.batch_size?` · batch ${x.telemetry.batch_size}`:''}${x.telemetry.inference_batch?` · infer ${x.telemetry.inference_batch}`:''}${x.telemetry.tuning?' · tuning':''}${x.telemetry.target_pps?` · target ${Number(x.telemetry.target_pps).toFixed(2)} p/s`:''}${x.telemetry.stage_seconds?`<br>stages ${Object.entries(x.telemetry.stage_seconds).map(([k,v])=>`${esc(k)} ${Number(v).toFixed(2)}s`).join(' · ')}`:''}</span>`:'';return `<div class="job"><b>${esc(x.kind)}</b> · ${esc(x.state)} · ${x.done}/${x.total}${phase}${rate}${eta}${tel}${x.current_model?`<br>${esc(x.current_model)} · model ${x.model_index}/${x.model_total} · ${x.model_done}/${x.model_images} images · ${x.detections||0} detections${x.last_image?`<br><span class="tiny">${esc(x.last_image)} · returned ${x.last_returned??0} · stored ${x.last_stored??0}</span>`:''}`:''}${x.error?`<br><span class="err">${esc(x.error)}</span>`:''}<div class="jobbar"><i style="width:${x.total?100*x.done/x.total:0}%"></i></div></div>`}).join(''):'None';if(jobHost&&jobHost._n8HTML!==jobHTML){jobHost.innerHTML=jobHTML;jobHost._n8HTML=jobHTML}/* Keep telemetry polling cheap while analysis is active. Observation refresh can be much heavier than /api/jobs and used to hold this poll open long enough to make chunk progress appear frozen. */if(!active&&!S.viewer&&Number(r.observation_revision||0)>Number(S.catalogObsRevision??-1)){invalidateVisibleAssets();await refreshObservations(true);S.obsRevision=String(r.observation_revision||S.obsRevision).split('-')[0]+'-'+assetEpoch}if(S.refreshSubjectClassStatus){const stamp=r.jobs.filter(job=>job.kind==='subject-class-training').map(job=>job.id+':'+job.state+':'+job.phase).join('|');if(stamp!==S.lastClassTrainingJob||S.classTrainingBusy){S.lastClassTrainingJob=stamp;await S.refreshSubjectClassStatus()}}return active||!!S.classTrainingBusy}

// P.47: the job seeker is unemployed until there is work. One settling read is allowed;
// polling exists only while queued/running jobs exist. Creating/stopping/dispatching work calls
// refreshJobs(), which wakes it. No idle timer survives a terminal queue.
let jobsPollTimer=0,jobsPollBusy=false,jobsPollFailures=0,jobsLastActive=false;
function scheduleJobsPoll(ms=1000){clearTimeout(jobsPollTimer);jobsPollTimer=setTimeout(()=>{jobsPollTimer=0;refreshJobs()},Math.max(250,ms))}
async function refreshJobs(){
 if(jobsPollBusy)return;
 clearTimeout(jobsPollTimer);jobsPollTimer=0;jobsPollBusy=true;
 try{jobsLastActive=!!(await refreshJobsCore());jobsPollFailures=0}
 catch(e){jobsPollFailures++;if(jobsPollFailures===1)console.warn('Jobs refresh failed; poller sleeping until explicitly awakened',e)}
 finally{jobsPollBusy=false;if(jobsLastActive)scheduleJobsPoll(document.hidden?5000:1000)}
}
document.addEventListener('visibilitychange',()=>{if(jobsLastActive)scheduleJobsPoll(document.hidden?5000:250)});

function modelLensColor(m){
 const provider=m.path==='builtin:oiv7'?'ultralytics-oiv7':m.path==='builtin:world'?'ultralytics-world':'ultralytics';
 const identity=m.path==='builtin:oiv7'?'yolov8n-oiv7.pt':m.path==='builtin:world'?'yolov8s-worldv2.pt':m.path;
 return detectorColor(provider,identity);
}
async function refreshModels(probe=true){
 if(!S.capabilities.inference)return;
 try{
  $('#modelList').textContent=probe?'Scanning models…':'Refreshing…';
  const r=await j(`/api/models?probe=${probe?'true':'false'}`); S.models=r.models;
  if(Array.isArray(r.world_classes))$('#worldClasses').value=r.world_classes.join(', ');
  const known=new Set(S.models.map(m=>m.path));
  S.enabledModels=new Set(S.models.filter(m=>m.ok!==false&&m.enabled!==false).map(m=>m.path));
  $('#modelList').innerHTML=S.models.length?S.models.map((m,i)=>`<label class="modelRow" title="${esc(m.path)}" style="--lens:${modelLensColor(m)}"><input type="checkbox" data-model="${esc(m.path)}" ${S.enabledModels.has(m.path)?'checked':''}> <b style="color:${modelLensColor(m)}">${esc(m.name)}</b> <label class="lensConf" title="Persistent confidence threshold">conf <input type="number" min="0" max="1" step="0.01" value="${Number(m.confidence??.25).toFixed(2)}" data-threshold="${esc(m.path)}"></label> <button type="button" class="lensForget" data-forget="${esc(m.path)}" title="Delete this lens’s findings for currently shown images; next normal sweep re-examines them.">forget shown</button> <span>${esc(m.task||m.family)} · ${m.classes.length} classes ${m.ok===false?'· ERROR':''}</span>${m.error?`<small>${esc(m.error)}</small>`:''}</label>`).join(''):'No local Ultralytics models found.';
  document.querySelectorAll('[data-model]').forEach(x=>x.onchange=async()=>{x.checked?S.enabledModels.add(x.dataset.model):S.enabledModels.delete(x.dataset.model);try{await j(`/api/models/lens-config?path=${encodeURIComponent(x.dataset.model)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:x.checked})})}catch(e){alert(e.message)}});
  document.querySelectorAll('[data-threshold]').forEach(x=>x.onchange=async()=>{
   let v=Math.max(0,Math.min(1,Number(x.value)));if(!Number.isFinite(v))v=.25;x.value=v.toFixed(2);
   try{await j(`/api/models/lens-config?path=${encodeURIComponent(x.dataset.threshold)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({confidence:v})});const m=S.models.find(m=>m.path===x.dataset.threshold);if(m)m.confidence=v;$('#status').textContent=`${m?.name||x.dataset.threshold} confidence saved at ${v.toFixed(2)}`}catch(e){alert(e.message)}
  });
  document.querySelectorAll('[data-forget]').forEach(b=>b.onclick=async e=>{
   e.preventDefault();e.stopPropagation();
   const lens=b.dataset.forget,m=S.models.find(x=>x.path===lens),paths=visibleFiles().map(x=>x.path);
   if(!paths.length)return alert('Nothing is currently shown.');
   if(!confirm(`Forget ${m?.name||lens}'s findings for ${paths.length} currently shown image${paths.length===1?'':'s'}?\n\nOnly this lens is affected. The next normal sweep will re-examine these files using its current threshold.`))return;
   try{
    const r=await post('/api/models/delete-findings',{lens,paths});
    if(S.path)await load(S.path);
    $('#status').textContent=`Forgot ${r.deleted} findings from ${m?.name||lens} across ${r.files} shown files. Ready for normal resample.`;
   }catch(err){alert(err.message)}
  });
 }catch(e){$('#modelList').textContent='Model scan failed: '+e.message}
}
async function sweepShown(){
 const paths=visibleFiles().map(x=>x.path),models=[...S.enabledModels];
 if(!paths.length)return alert('No images in this view.');
 if(!models.length)return alert('No Ultralytics models enabled.');
 const thresholds=Object.fromEntries(S.models.filter(m=>models.includes(m.path)).map(m=>[m.path,Number(m.confidence??.25)]));const world_classes=$('#worldClasses').value.split(/[\n,]+/).map(x=>x.trim()).filter(Boolean);await j('/api/models/yolo-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({world_classes,batch_size:16})});const r=await post('/api/models/sweep',{engine:'ultralytics',paths,models,world_classes,thresholds,confidence:.25,batch_size:16});
 $('#status').textContent=`YOLO sweep ${r.id} started: ${models.length} models × ${paths.length} images`;refreshJobs();
}
async function refreshDiscovered(){try{const r=await j('/api/tags/discovered');S.discovered=r.tags||[];renderTagResults()}catch(e){console.warn('Tag discovery failed',e)}}
function renderTagResults(){const box=$('#tagResults');if(!box)return;const q=conceptKey($('#tagSearch').value);const rows=groupedDiscovered().filter(t=>!q||t.concept.includes(q)).filter(t=>!S.magnets.has(t.key)).slice(0,80);box.innerHTML=rows.map(t=>`<button class="tagResult" data-key="${encodeURIComponent(t.key)}" title="${esc(observationAttribution(t))}" style="color:${detectorColor(t.provider,t.model)}">${esc(observationLabel(t))}</button>`).join('');box.querySelectorAll('.tagResult').forEach(b=>b.onclick=()=>addMagnet(decodeURIComponent(b.dataset.key)))}
function addMagnet(key){const t=groupedDiscovered().find(x=>x.key===key);if(!t||S.magnets.has(key))return;const n=S.magnetSeq++,x=10+(n%3)*112,y=10+(Math.floor(n/3)%9)*46;S.magnets.set(key,{key,concept:t.concept,provider:t.provider,model:t.model,mode:'0',op:'≥',count:'',x,y});renderMagnets();renderTagResults();render()}
function renderMagnets(){const board=$('#magnetBoard');if(!board)return;const hint='<div class="boardHint">Search above, then add a discovered feature.</div>';board.innerHTML=S.magnets.size?'':hint;for(const m of S.magnets.values()){const el=document.createElement('div');el.className=`magnet ${m.mode==='+'?'plus':m.mode==='-'?'minus':'zero'}`;el.dataset.key=m.key;el.style.left=m.x+'px';el.style.top=m.y+'px';el.innerHTML=`<button class="removeMagnet" title="Remove filter">×</button><button class="tagBody ${humanObservation(m.provider)?'humanObservation':''}" style="${humanObservation(m.provider)?'':`color:${detectorColor(m.provider,m.model)}`}" title="Drag this magnet · ${esc(m.provider)} · ${esc(m.model)}">${esc(observationLabel(m))}</button><button class="modeBtn" title="0 inactive, + require, − forbid">${m.mode}</button><select class="countOp" title="Count comparison"><option>=</option><option>≠</option><option>&lt;</option><option>≤</option><option>&gt;</option><option>≥</option></select><input class="countValue" type="number" min="0" step="1" inputmode="numeric" placeholder="#" title="Detection count">`;el.querySelector('.countOp').value=m.op;el.querySelector('.countValue').value=m.count;el.querySelector('.removeMagnet').onclick=e=>{e.stopPropagation();S.magnets.delete(m.key);renderMagnets();renderTagResults();render()};el.querySelector('.modeBtn').onclick=e=>{e.stopPropagation();m.mode=m.mode==='0'?'+':m.mode==='+'?'-':'0';renderMagnets();render()};el.querySelector('.countOp').onchange=e=>{m.op=e.target.value;render()};el.querySelector('.countValue').oninput=e=>{m.count=e.target.value;render()};makeDraggable(el,m);board.appendChild(el)}}
function makeDraggable(el,m){let drag=null;const start=e=>{if(e.target.closest('button,select,input')&&!e.target.classList.contains('tagBody'))return;const r=el.getBoundingClientRect();drag={id:e.pointerId,dx:e.clientX-r.left,dy:e.clientY-r.top};el.setPointerCapture(e.pointerId);el.classList.add('dragging')};el.addEventListener('pointerdown',start);el.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;const b=$('#magnetBoard').getBoundingClientRect();m.x=Math.max(0,Math.min(b.width-el.offsetWidth,e.clientX-b.left-drag.dx));m.y=Math.max(0,Math.min(b.height-el.offsetHeight,e.clientY-b.top-drag.dy));el.style.left=m.x+'px';el.style.top=m.y+'px'});el.addEventListener('pointerup',e=>{if(drag&&drag.id===e.pointerId){drag=null;el.classList.remove('dragging')}})}
function presetState(){return {magnets:[...S.magnets.values()].map(m=>({...m})),sortKey:S.sortKey,sortDir:S.sortDir}}
function refreshPresetSelect(){const el=$('#filterPresetSelect');if(!el)return;const old=el.value;el.innerHTML='<option value="">Filter preset…</option>'+Object.keys(S.filterPresets||{}).sort((a,b)=>a.localeCompare(b)).map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('');if(S.filterPresets?.[old])el.value=old}
function applyFilterPreset(state){if(!state)return;S.magnets.clear();for(const m of(state.magnets||[]))if(m?.key){const key=obsKey(m);if(!S.magnets.has(key))S.magnets.set(key,{...m,key,concept:conceptKey(m.concept)})}S.magnetSeq=S.magnets.size;S.sortKey=state.sortKey||'none';S.sortDir=state.sortDir==='desc'?'desc':'asc';$('#sortKey').value=S.sortKey;$('#sortDir').textContent=S.sortDir==='asc'?'↑':'↓';renderMagnets();renderTagResults();render()}
async function refreshFilterPresets(){try{const r=await j('/api/filter-presets');S.filterPresets=r.presets||{};refreshPresetSelect()}catch(e){console.warn('Preset refresh failed',e)}}
function compactControls(){return S.mobile||matchMedia('(max-width:850px)').matches}
function setControlMenu(open){if(open){setDrawer(false);$('#settingsDrawer')?.classList.remove('open');$('#settingsDrawer')?.setAttribute('aria-hidden','true')}$('#rail')?.classList.toggle('railOpen',open);$('#railToggle')?.setAttribute('aria-expanded',String(open));if($('#railBackdrop'))$('#railBackdrop').hidden=!open}
function setDrawer(open){S.drawer=open;if(open&&compactControls()){$('#rail')?.classList.remove('railOpen');$('#railToggle')?.setAttribute('aria-expanded','false');$('#settingsDrawer')?.classList.remove('open');$('#settingsDrawer')?.setAttribute('aria-hidden','true')}$('#filterDrawer').classList.toggle('open',open);$('#filterDrawer').setAttribute('aria-hidden',String(!open));$('#filtersBtn').setAttribute('aria-expanded',String(open));if(compactControls()&&$('#railBackdrop'))$('#railBackdrop').hidden=!open&&!$('#rail')?.classList.contains('railOpen');if(open){refreshDiscovered();if(!compactControls())setTimeout(()=>$('#tagSearch').focus(),0)}}
function clearSelected(){S.selectionRequest=(S.selectionRequest||0)+1;S.selected.clear();S.selectionAnchor=null;S.selectionAnchorMeta=null;consumeSoftModifiers();refreshSelectionUI();$('#status').textContent='Selection cleared'}
$('#clearSelectedBtn').onclick=event=>{event.stopPropagation();clearSelected()};$('#filterCloseBtn').onclick=()=>setDrawer(false);$('#filterBackBtn').onclick=()=>setControlMenu(true);

function updateFilterButton(){const active=[...S.magnets.values()].filter(m=>m.mode!=='0').length;$('#filtersBtn').textContent=active?`Filters (${active})`:'Filters'}
function toggleGeometry(which){S[which]=!S[which];const b=$(which==='boxes'?'#boxesBtn':'#masksBtn');b.setAttribute('aria-pressed',String(S[which]));b.textContent=`${which==='boxes'?'Boxes':'Masks'} ${S[which]?'●':'○'}`;const cls=which==='boxes'?'gridBoxLayer':'gridMaskLayer';if(!S[which]){document.querySelectorAll('.'+cls).forEach(x=>x.remove());return}const rev=encodeURIComponent(S.obsRevision||0);document.querySelectorAll('#grid .card').forEach(c=>{const t=c.querySelector('.thumb');if(!t||t.querySelector('.'+cls))return;const im=document.createElement('img');im.className='gridGeomLayer '+cls;im.loading='lazy';im.src=`/api/grid-overlay?path=${enc(c.dataset.p)}&kind=${which}&rev=${rev}`;t.appendChild(im)})}

function applyUiScale(v){v=Math.max(70,Math.min(140,Number(v)||100));const k=v/100,r=document.documentElement.style;r.setProperty('--rail',Math.round(300*k)+'px');r.setProperty('--rail-pad',Math.round(12*k)+'px');r.setProperty('--rail-section-pad',Math.round(10*k)+'px');r.setProperty('--control-py',Math.max(3,Math.round(6*k))+'px');r.setProperty('--control-px',Math.max(5,Math.round(9*k))+'px');r.setProperty('--input-pad',Math.max(4,Math.round(7*k))+'px');r.setProperty('--rail-font',Math.max(10,Math.round(14*k))+'px');const out=$('#uiScaleValue'),slider=$('#uiScale');if(out)out.textContent=v+'%';if(slider&&Number(slider.value)!==v)slider.value=v;localStorage.setItem('n8visionUiScale',String(v))}
async function openSettings(){setDrawer(false);document.getElementById('rail')?.classList.remove('railOpen');document.getElementById('railBackdrop')?.setAttribute('hidden','');document.getElementById('railToggle')?.setAttribute('aria-expanded','false');refreshCheckpointLibraryStatus();
 $('#settingsDrawer').classList.add('open');$('#settingsDrawer').setAttribute('aria-hidden','false');updateDefaultRootLabel();updateThumbnailCacheLabel();const gd=$('#gridDetailSetting');if(gd)gd.value=S.gridDetail;const gg=$('#gridGapSetting');if(gg){gg.value=S.gridGapTenths;$('#gridGapValue').textContent=(S.gridGapTenths/10).toFixed(1)+'vw';}applyBadgeVisibility();const sb=$('#sanityBadgeSetting');if(sb)sb.value=S.sanityBadges;const ig=$('#imageGridEnabled');if(ig)ig.checked=S.imageGridEnabled;const uu=$('#uncappedUnsanity');if(uu)uu.checked=S.uncappedUnsanity;if(S.path)refreshStorageClass();refreshPromptTranslatorChoices();
 try{const n=await j('/api/network/status');$('#enableLan').checked=n.enable_lan;$('#persistentCredentials').checked=n.persistent_credentials;$('#networkRestart').textContent=`LAN address: ${n.lan_ip}:${n.port}`;}catch(e){$('#networkRestart').textContent=e.message};refreshPairedDevices();refreshPublicPortal();refreshAdminStatus()
}
async function refreshPromptTranslatorChoices(){
 const sel=$('#promptTranslatorModel');if(!sel)return;let choices=[];
 try{const envs=await refineEnvironments();if(envs.length){const shelf=await j('/api/comfy/tool-shelf/'+enc(envs[0].id));const loader=(shelf.tools||[]).find(t=>t.type==='CLIPLoader');choices=schemaChoices(loader,'clip').filter(x=>/qwen|gemma|llama|text/i.test(x));}}
 catch(e){}
 const current=S.promptTranslator?.model||'';if(current&&!choices.includes(current))choices.unshift(current);
 sel.innerHTML='<option value="">Not selected</option>'+[...new Set(choices)].map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');sel.value=current;
}
async function refreshCheckpointLibraryStatus(){try{const r=await j('/api/comfy/checkpoint-library');S.checkpointLibrary=r;const el=$('#checkpointLibraryStatus');if(el){const n=Object.keys(r.checkpoints||{}).length;el.textContent=n?`${n} checkpoints interrogated · ${new Date((r.updated||0)*1000).toLocaleString()}`:'Not interrogated yet.'}}catch(e){const el=$('#checkpointLibraryStatus');if(el)el.textContent='Checkpoint library unavailable: '+e.message}}
async function interrogateCheckpoints(){const b=$('#refreshCheckpointLibraryBtn');try{const envs=await j('/api/environments');const env=(envs.environments||[]).find(x=>x.kind==='comfy'&&x.online)||(envs.environments||[]).find(x=>x.kind==='comfy');if(!env)return alert('No Comfy environment found.');if(b){b.disabled=true;b.textContent='Interrogating…'}$('#checkpointLibraryStatus').textContent='Comfy is lining up the suspects. Large checkpoint pools can take a while; each model is classified by Comfy itself.';const r=await j(`/api/comfy/checkpoint-library/${encodeURIComponent(env.id)}/refresh`,{method:'POST'});S.checkpointLibrary=r;const rows=Object.values(r.checkpoints||{}),bad=rows.filter(x=>!x.ok).length;$('#checkpointLibraryStatus').textContent=`${rows.length} checkpoints interrogated${bad?` · ${bad} failed`:''} · library saved`;$('#status').textContent=`Who dis? complete · ${rows.length} checkpoints catalogued`;}catch(e){alert(e.message);await refreshCheckpointLibraryStatus()}finally{if(b){b.disabled=false;b.textContent='Interrogate Checkpoints'}}}
async function savePromptTranslator(){const model=$('#promptTranslatorModel')?.value||'';try{const r=await j('/api/config/prompt-translator',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({model,type:'stable_diffusion',device:'default'})});S.promptTranslator=r.prompt_translator;$('#status').textContent=model?`Prompt translator set globally: ${model}`:'Prompt translator cleared.'}catch(e){alert(e.message)}}
function promptDialect(text){const t=String(text||'').trim();if(!t)return 'tags';const parts=t.split(',').map(x=>x.trim()).filter(Boolean);const booru=(t.match(/\b(?:\d+(?:girl|boy)s?|looking_at_\w+|[a-z0-9]+_[a-z0-9_]+)\b/gi)||[]).length;const ends=(t.match(/[.!?](?:\s|$)/g)||[]).length;const prose=(t.match(/\b(?:the|a|an|with|wearing|standing|sitting|while|which|who|under|behind|beside)\b/gi)||[]).length;if(parts.length>=3&&ends<2)return 'tags';if(booru>=2)return 'tags';if(ends>=2||(parts.length<=2&&t.split(/\s+/).length>=8&&prose>=2))return 'natural';return 'hybrid'}
function checkpointLibraryRow(name){const rows=S.checkpointLibrary?.checkpoints||{};const norm=x=>String(x||'').replaceAll('\\','/').toLowerCase(),n=norm(name),nb=n.split('/').pop();return Object.entries(rows).find(([k])=>norm(k)===n||norm(k).split('/').pop()===nb)?.[1]||null}
function selectedCheckpointDialect(){const name=$('#refineModel')?.value||'';const row=checkpointLibraryRow(name),d=row?.dialect?.preferred;if(d==='tags'||d==='natural'||d==='hybrid')return d;return /flux|kontext|qwen|klein|hunyuan|lumina|wan/i.test(name)?'natural':'tags'}
function selectedCheckpointCompatibility(){const name=$('#refineModel')?.value||'',row=checkpointLibraryRow(name),raw=row?.dialect?.compatible;if(Array.isArray(raw)){const out=[...new Set(raw.map(x=>String(x||'').toLowerCase()).filter(x=>['tags','natural','hybrid'].includes(x)))];if(out.length)return out;}const preferred=selectedCheckpointDialect();return preferred==='natural'?['natural','hybrid']:preferred==='hybrid'?['hybrid','tags','natural']:['tags','hybrid']}
function refineryPromptRows(){return (S.refineMetadata||[]).map((x,i)=>{const m=x.metadata||{};return {path:x.path||S.refinePaths?.[i]||'',positive:i===0?($('#refinePositive')?.value||m.positive||''):(m.positive||$('#refinePositive')?.value||''),negative:i===0?($('#refineNegative')?.value||m.negative||''):(m.negative||$('#refineNegative')?.value||'')}})}
function refineryTranslationNeeds(){const target=selectedCheckpointDialect(),compatible=selectedCheckpointCompatibility(),done=S.refineTranslations||{};const needs=[];for(const row of refineryPromptRows())for(const side of ['positive','negative']){const text=row[side]||'',d=promptDialect(text);if(text&&!compatible.includes(d)&&!done[row.path]?.[side])needs.push({path:row.path,side,text,source:d,target})}return needs}
function refineryNeedsTranslation(){return refineryTranslationNeeds().length>0}
function updateRefineDialectUI(){const p=$('#refinePositive'),n=$('#refineNegative'),pd=promptDialect(p?.value||''),nd=promptDialect(n?.value||''),target=selectedCheckpointDialect(),compatible=selectedCheckpointCompatibility();if($('#refinePositiveDialect'))$('#refinePositiveDialect').textContent=pd.toUpperCase();if($('#refineNegativeDialect'))$('#refineNegativeDialect').textContent=nd.toUpperCase();const needs=refineryTranslationNeeds(),gate=$('#refineTranslationGate');if(gate){gate.hidden=!needs.length;$('#refineTranslationNeed').textContent=needs.length?`${needs.length} prompt field${needs.length===1?'':'s'} incompatible with this checkpoint · translate to ${target.toUpperCase()} before launch.`:`Compatible: ${compatible.map(x=>x.toUpperCase()).join(' / ')}`;}refineRunValidity()}
async function pretranslateRefinery(){const needs=refineryTranslationNeeds();if(!needs.length)return updateRefineDialectUI();if(!S.promptTranslator?.model){openSettings();await refreshPromptTranslatorChoices();return alert('Choose the global Prompt Translator in Settings first.');}const paths=[...new Set(needs.map(x=>x.path))],rows=refineryPromptRows().filter(x=>paths.includes(x.path));const b=$('#refineTranslateBtn');try{b.disabled=true;b.textContent='Translating…';const r=await post('/api/refinement/pretranslate',{environment_id:S.refineRecipe.environment_id,target_dialect:selectedCheckpointDialect(),items:rows});S.refineTranslations=S.refineTranslations||{};for(const x of r.items||[]){S.refineTranslations[x.path]={positive:x.positive||'',negative:x.negative||''};}updateRefineDialectUI();$('#refineWizardFoot').textContent='Translation preflight complete. Execute will submit image jobs only.';}catch(e){alert(e.message)}finally{b.disabled=false;b.textContent='Translate This Shit'}}
let textStreamTimer=null;
function watchPromptAdapter(){clearInterval(textStreamTimer);const box=$('#refinePromptAdapter');if(!box)return;box.hidden=false;S.textStreamSeen=new Set();$('#refinePositiveSend').value='';$('#refineNegativeSend').value='';$('#refineTranslateStatus').textContent='Waiting';textStreamTimer=setInterval(async()=>{if($('#refineWizard').hidden){clearInterval(textStreamTimer);return}try{const r=await j('/api/comfy/text-streams');const rows=(r.streams||[]).filter(x=>!S.textStreamSeen.has(x.request_id));const active=(r.streams||[]).filter(x=>String(x.stream_key||'').includes(':positive')||String(x.stream_key||'').includes(':negative'));for(const x of active){const out=String(x.stream_key||'').endsWith(':negative')?$('#refineNegativeSend'):$('#refinePositiveSend');if(out&&x.text)out.value=x.text;if(x.status==='complete')S.textStreamSeen.add(x.request_id)}if(active.length){const last=active[active.length-1];$('#refineTranslateStatus').textContent=last.status==='complete'?'Complete':last.status==='receiving'?`Receiving · ${String(last.text||'').length} chars`:'Waiting'}}catch(e){}},250)}
function closeSettings(){$('#settingsDrawer').classList.remove('open');$('#settingsDrawer').setAttribute('aria-hidden','true')}
function setImageGridEnabled(enabled){S.imageGridEnabled=!!enabled;const ctl=$('#imageGridEnabled');if(ctl)ctl.checked=S.imageGridEnabled;if(S.imageGridEnabled)render();else{$('#grid').replaceChildren();refreshSelectionUI()}$('#status').textContent=S.imageGridEnabled?'Image grid enabled.':'Image grid suppressed.'}
function toggleImageGrid(){setImageGridEnabled(!S.imageGridEnabled)}
// Settings controls are optional from the point of view of app bootstrap.
// A stale/cached index must never be able to kill the entire UI because one new control is absent.
const exploreSettingsBtn=$('#exploreSettingsBtn'),orderingSettingsBtn=$('#orderingSettingsBtn'),settingsClose=$('#settingsClose'),uiScale=$('#uiScale');
if(exploreSettingsBtn)exploreSettingsBtn.onclick=openSettings;const ckl=$('#refreshCheckpointLibraryBtn');if(ckl)ckl.onclick=interrogateCheckpoints;const spt=$('#savePromptTranslatorBtn');if(spt)spt.onclick=savePromptTranslator;if(orderingSettingsBtn)orderingSettingsBtn.onclick=openSettings;if(settingsClose)settingsClose.onclick=closeSettings;const imageGridEnabled=$('#imageGridEnabled');if(imageGridEnabled)imageGridEnabled.onchange=e=>setImageGridEnabled(e.target.checked);const uncappedUnsanity=$('#uncappedUnsanity');if(uncappedUnsanity)uncappedUnsanity.onchange=async e=>{S.uncappedUnsanity=!!e.target.checked;await saveRasterSettings();$('#status').textContent=S.uncappedUnsanity?'Uncapped UnSanity enabled. Sanity may use all physical cores when p/s improves.':'Normal Sanity courtesy limit restored.';};
if(uiScale){uiScale.value=localStorage.getItem('n8visionUiScale')||100;applyUiScale(uiScale.value);uiScale.oninput=e=>applyUiScale(e.target.value)}else applyUiScale(localStorage.getItem('n8visionUiScale')||100);
async function refreshPairedDevices(){const box=$('#pairedDeviceList');if(!box)return;try{const r=await j('/api/network/devices');box.innerHTML=r.devices.length?r.devices.map(d=>`<div>${esc(d.name)} · ${esc(d.role||'device')} <button type="button" class="revokeOneDevice" data-id="${esc(d.id)}">Revoke</button>${d.role==='admin'?'':` <button type="button" class="grantAdminDevice" data-id="${esc(d.id)}">Make Admin</button>`}</div>`).join(''):'No persistent paired devices.';box.querySelectorAll('.revokeOneDevice').forEach(b=>b.onclick=async()=>{if(!confirm('Revoke this device credential?'))return;await post('/api/network/revoke-device',{device_id:b.dataset.id});refreshPairedDevices()});box.querySelectorAll('.grantAdminDevice').forEach(b=>b.onclick=async()=>{if(!confirm('Grant this device permanent Admin access?'))return;await post('/api/network/admin/grant',{device_id:b.dataset.id});refreshPairedDevices()})}catch(e){box.textContent='Device registry requires Admin: '+e.message}}
async function refreshAdminStatus(){const el=$('#adminCredentialStatus');if(!el)return;try{await j('/api/network/admin/me');el.textContent='This browser is an Administrator.'}catch(_){el.textContent='This browser is not an Administrator. Host authorization is required.'}}
const adminPromoteBtn=$('#adminPromoteThisBtn');if(adminPromoteBtn)adminPromoteBtn.onclick=async()=>{const field=$('#adminHostCode'),code=field?.value.trim();if(!code)return alert('Generate a code using python run.py --admin-code on the host.');try{const r=await post('/api/network/admin/bootstrap',{code,device_name:(navigator.platform||'Browser')+' · Administrator'});localStorage.setItem('n8visionCredential',r.credential);field.value='';await refreshAdminStatus();await refreshPairedDevices();alert('This browser now holds a persistent Admin credential.')}catch(e){alert(e.message)}};

const saveNetworkBtn=$('#saveNetworkBtn');if(saveNetworkBtn)saveNetworkBtn.onclick=async()=>{try{const r=await j('/api/network/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enable_lan:$('#enableLan')?.checked||false,persistent_credentials:$('#persistentCredentials')?.checked||false})});const n=$('#networkRestart');if(n)n.textContent=r.restart_required?'Saved. Restart N8Vision for the LAN binding change to take effect.':'Saved.'}catch(e){alert(e.message)}};
const connectDeviceBtn=$('#connectDeviceBtn');if(connectDeviceBtn)connectDeviceBtn.onclick=async()=>{try{const r=await post('/api/network/pairing',{}),box=$('#pairingBox'),qr=$('#pairingQr'),url=$('#pairingUrl');if(box)box.hidden=false;if(qr)qr.innerHTML=r.svg;if(url)url.textContent=r.url+'  · QR handshake expires in 10 minutes.'}catch(e){}};
const revokeDevicesBtn=$('#revokeDevicesBtn');if(revokeDevicesBtn)revokeDevicesBtn.onclick=async()=>{if(!confirm('Revoke all paired-device credentials?'))return;try{await post('/api/network/revoke-all',{});localStorage.removeItem('n8visionCredential');const box=$('#pairingBox'),n=$('#networkRestart');if(box)box.hidden=true;if(n)n.textContent='Paired-device credentials revoked.';refreshPairedDevices()}catch(e){}};
async function refreshPublicPortal(){const out=$('#publicStatus');try{const r=await j('/api/network/public/status');if($('#enablePublic'))$('#enablePublic').checked=!!r.enabled;if($('#publicAutoStart'))$('#publicAutoStart').checked=!!r.auto_start;if($('#publicTunnelMode'))$('#publicTunnelMode').value=r.mode||'quick';if($('#publicExternalManaged'))$('#publicExternalManaged').checked=!!r.external_managed;if($('#publicNamedHostname')&&!$('#publicNamedHostname').matches(':focus'))$('#publicNamedHostname').value=r.named_hostname||'';if($('#publicTokenFile')&&!$('#publicTokenFile').matches(':focus'))$('#publicTokenFile').value=r.token_file||'';if($('#cloudflaredPath')&&!$('#cloudflaredPath').matches(':focus'))$('#cloudflaredPath').value=r.cloudflared||'';if(out)out.textContent=r.state==='external'?`External connector · ${r.url} (health managed by Cloudflare)`:r.state==='online'?`Online · ${r.url}`:r.state==='starting'?'Starting public tunnel…':r.error?`Stopped · ${r.error}`:`Stopped${r.cloudflared?'':' · cloudflared not found'}`;return r}catch(e){if(out)out.textContent=e.message;return null}}
const savePublicBtn=$('#savePublicBtn');if(savePublicBtn)savePublicBtn.onclick=async()=>{try{await j('/api/network/public/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enable_public:!!$('#enablePublic')?.checked,auto_start:!!$('#publicAutoStart')?.checked,cloudflared_path:$('#cloudflaredPath')?.value||'',tunnel_mode:$('#publicTunnelMode')?.value||'quick',named_hostname:$('#publicNamedHostname')?.value||'',token_file:$('#publicTokenFile')?.value||'',external_managed:!!$('#publicExternalManaged')?.checked})});await refreshPublicPortal()}catch(e){alert(e.message)}};
const startPublicBtn=$('#startPublicBtn');if(startPublicBtn)startPublicBtn.onclick=async()=>{try{if(savePublicBtn)await j('/api/network/public/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({enable_public:!!$('#enablePublic')?.checked,auto_start:!!$('#publicAutoStart')?.checked,cloudflared_path:$('#cloudflaredPath')?.value||'',tunnel_mode:$('#publicTunnelMode')?.value||'quick',named_hostname:$('#publicNamedHostname')?.value||'',token_file:$('#publicTokenFile')?.value||'',external_managed:!!$('#publicExternalManaged')?.checked})});if($('#publicTunnelMode')?.value==='named'&&$('#publicExternalManaged')?.checked){await refreshPublicPortal();return;}await post('/api/network/public/start',{});for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,500));const st=await refreshPublicPortal();if(st?.state==='online'||st?.state==='error'||(st?.state==='stopped'&&st?.error))break}}catch(e){alert(e.message);refreshPublicPortal()}};
const stopPublicBtn=$('#stopPublicBtn');if(stopPublicBtn)stopPublicBtn.onclick=async()=>{try{await post('/api/network/public/stop',{});refreshPublicPortal()}catch(e){alert(e.message)}};
const publicPairBtn=$('#publicPairBtn');if(publicPairBtn)publicPairBtn.onclick=async()=>{try{const st=await refreshPublicPortal();if(!['online','external'].includes(st?.state))throw new Error('Start the Public Portal first.');const r=await post('/api/network/pairing',{}),box=$('#publicPairingBox'),qr=$('#publicPairingQr'),url=$('#publicPairingUrl');if(box)box.hidden=false;if(qr)qr.innerHTML=r.svg;if(url)url.textContent=r.url+'  · QR handshake expires in 10 minutes.'}catch(e){alert(e.message)}};

function setControlPlane(v){v=v==='touch'?'touch':'desktop';localStorage.setItem('n8visionControlPlane',v);const t=$('#touchModifiers'),c=$('#controlPlane');if(t)t.hidden=v!=='touch';if(c)c.value=v;document.body.classList.toggle('touchGridEnabled',v==='touch');updateTicker()}
function updateSoftModifiers(){const c=$('#softCtrl'),s=$('#softShift');if(c)c.classList.toggle('active',S.softCtrl);if(s)s.classList.toggle('active',S.softShift)}
function updateTicker(){const t=$('#interactionTickerText');if(!t)return;t.textContent=(localStorage.getItem('n8visionControlPlane')==='touch')?'Tap — Toggle Selection • Shift + Tap — Sequential Inclusive Select • Ctrl + Touch-Drag — Lasso • Double-Tap — Inspect • Esc — Clear Selection':'Ctrl-A — Select All • Click — Toggle Selection • Shift-Click — Sequential Inclusive Select • Ctrl-Click-Drag — Lasso • Double-Click — Inspect • Esc — Clear Selection'}
const controlPlane=$('#controlPlane');if(controlPlane){controlPlane.onchange=e=>setControlPlane(e.target.value);setControlPlane(S.mobile?'touch':(localStorage.getItem('n8visionControlPlane')||'desktop'))}
const softCtrl=$('#softCtrl'),softShift=$('#softShift');if(softCtrl)softCtrl.onclick=()=>{S.softCtrl=!S.softCtrl;updateSoftModifiers()};if(softShift)softShift.onclick=()=>{S.softShift=!S.softShift;updateSoftModifiers()};
const ticker=$('#interactionTicker'),help=$('#interactionHelp'),helpClose=$('#interactionHelpClose');if(ticker)ticker.onclick=()=>{help.hidden=!help.hidden};if(helpClose)helpClose.onclick=()=>help.hidden=true;
document.addEventListener('keydown',e=>{const editable=e.target?.matches?.('input,textarea,select,[contenteditable=true]');if(e.ctrlKey&&e.shiftKey&&e.key.toLowerCase()==='h'){e.preventDefault();toggleImageGrid();return}if(e.key==='Escape'&&!S.viewer)clearSelected();if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'&&!S.viewer&&!editable){e.preventDefault();comparisonPaths().filter(p=>!moveQueue.has(p)).forEach(p=>S.selected.add(p));refreshSelectionUI()}if(e.key==='Delete'&&!S.viewer&&!editable&&S.selected.size){e.preventDefault();deleteSelected().catch(err=>alert(err.message))}});
(function installLasso(){const grid=$('#grid');if(!grid)return;let drag=null,box=null,startSelection=null;grid.addEventListener('pointerdown',e=>{const ctrl=e.ctrlKey||e.metaKey||S.softCtrl;if(!ctrl||e.button!==0)return;e.preventDefault();const r=grid.getBoundingClientRect();drag={id:e.pointerId,x:e.clientX,y:e.clientY,grid:r,moved:false};startSelection=new Set(S.selected);box=document.createElement('div');box.className='selectionLasso';document.body.appendChild(box);grid.setPointerCapture(e.pointerId)});grid.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>4)drag.moved=true;const x1=Math.min(drag.x,e.clientX),y1=Math.min(drag.y,e.clientY),x2=Math.max(drag.x,e.clientX),y2=Math.max(drag.y,e.clientY);Object.assign(box.style,{left:x1+'px',top:y1+'px',width:(x2-x1)+'px',height:(y2-y1)+'px'});S.selected=new Set(startSelection);document.querySelectorAll('#grid .card').forEach(c=>{const r=c.getBoundingClientRect();if(r.right>=x1&&r.left<=x2&&r.bottom>=y1&&r.top<=y2)S.selected.add(c.dataset.p)});document.querySelectorAll('#grid .card').forEach(c=>c.classList.toggle('selected',S.selected.has(c.dataset.p)));$('#selCount').textContent=S.selected.size});const end=e=>{if(!drag||drag.id!==e.pointerId)return;const wasMoved=drag.moved;if(wasMoved)S.suppressClickUntil=performance.now()+250;drag=null;if(box)box.remove();box=null;consumeSoftModifiers();render()};grid.addEventListener('pointerup',end);grid.addEventListener('pointercancel',end)})();
$('#regenerateBtn').oncontextmenu=e=>{e.preventDefault();deleteRefineRecipe()};$('#locationBar').onclick=()=>setTree(!S.treeOpen);$('#boxesBtn').onclick=()=>toggleGeometry('boxes');$('#masksBtn').onclick=()=>toggleGeometry('masks');$('#filtersBtn').onclick=()=>setDrawer(!S.drawer);$('#sortKey').onchange=async e=>{const key=e.target.value;if(key==='similarity'&&S.compare?.kind!=='similar'){e.target.value=S.sortKey;return $('#similarBtn').onclick()}if(key==='uniqueness'&&S.compare?.kind!=='unique'){e.target.value=S.sortKey;return $('#uniqueBtn').onclick()}S.sortKey=key;render()};$('#sortDir').onclick=()=>{S.sortDir=S.sortDir==='asc'?'desc':'asc';$('#sortDir').textContent=S.sortDir==='asc'?'↑':'↓';render()};$('#tagSearch').oninput=renderTagResults;$('#clearFiltersBtn').onclick=()=>{S.magnets.clear();S.magnetSeq=0;$('#tagSearch').value='';renderMagnets();renderTagResults();render()};$('#goBtn').onclick=()=>scanCurrent();$('#path').oninput=updateScanButton;$('#path').onkeydown=e=>{if(e.key==='Enter')browseOnly($('#path').value,'path-enter')};$('#upBtn').onclick=()=>S.parent&&navigateTo(S.parent,false,'parent-focus');$('#recursive').onchange=async()=>{if(!S.scopeRoot)return;const want=$('#recursive').checked,registered=(S.archiveRoots||[]).some(r=>canonPath(r)===canonPath(S.scopeRoot));if(want&&!registered){$('#recursive').checked=false;$('#status').textContent='Recursive archival begins with Scan.';return}if(want&&!S.catalogRecursive){const keep=[...S.scopeSelections];await load(S.scopeRoot,false,'recursive-toggle');S.scopeSelections=new Set(keep);S.scopeRecursive=true;renderFolderSelection();render();return}S.scopeRecursive=want;render();$('#status').textContent=`${want?'Recursive':'Direct'} view · ${visibleFiles().length.toLocaleString()} shown`};$('#search').oninput=render;$('#minConfidence').oninput=e=>{$('#minConfidenceValue').textContent=Math.round(e.target.value*100)+'%';render()};$('#thumbSize').oninput=e=>{document.documentElement.style.setProperty('--thumb',e.target.value+'px');S.virtualGrid.start=S.virtualGrid.end=-1;invalidateRingLayout();scheduleVirtualGrid()};$('#thumbSize').onchange=()=>render();$('#selectShownBtn').onclick=()=>{comparisonPaths().filter(p=>!moveQueue.has(p)).forEach(p=>S.selected.add(p));refreshSelectionUI()};
function evictPaths(paths){const gone=new Set(paths);S.files=S.files.filter(f=>!gone.has(f.path));for(const p of gone)S.selected.delete(p);S.multiWork=S.multiWork.filter(p=>!gone.has(p));if(S.selectionAnchor&&gone.has(S.selectionAnchor))S.selectionAnchor=null;if(S.viewer&&gone.has(S.viewer))closeViewer();render()}
// A filesystem move is not a browse transaction. Apply the journal's exact path
// mapping locally so the ringworld, filters, and navigation stay where they are.
function moveRoot(path){
 const p=canonPath(path),roots=[...(S.archiveRoots||[])];
 if(S.scopeRoot&&!roots.some(r=>canonPath(r)===canonPath(S.scopeRoot)))roots.push(S.scopeRoot);
 return roots.map(canonPath).filter(r=>p===r||p.startsWith(r+'\\')).sort((a,b)=>b.length-a.length)[0]||null;
}
function patchMovedFiles(items,{leavePlaceholder=false}={}){
 if(!items?.length)return;
 const changes=new Map(items.filter(x=>x?.from&&x?.to).map(x=>[canonPath(x.from),x.to]));
 const translate=p=>changes.get(canonPath(p))||p,v=S.virtualGrid;
 const retained=v.rows.map(spec=>({spec,key:rowKey(spec)}));
 const catalogs=[...rootCatalogs.values()];
 const arrays=[...new Set([S.files,v.files,...catalogs.map(c=>c.files)])];
 const processed=new Set(),inPlace=new Set();
 for(const files of arrays)for(const f of files){
  if(processed.has(f)||f._n8ForwardTo)continue;processed.add(f);
  const from=f.path,to=changes.get(canonPath(from));if(!to)continue;
  const sourceRoot=moveRoot(from),targetRoot=moveRoot(to);
  const metadata=(f.observations||[]).map(o=>({...o,path:to}));
  if(!leavePlaceholder&&sourceRoot&&sourceRoot===targetRoot){
   // Shared catalog and row references retain exactly the same slot and pixels.
   f.path=to;f.name=to.split(/[\\/]/).pop();f.observations=metadata;
   inPlace.add(canonPath(from));
  }else{
   f._n8ForwardTo=to;
   const destination={...f,path:to,name:to.split(/[\\/]/).pop(),observations:metadata};
   delete destination._n8ForwardTo;delete destination._n8Tombstone;
   for(const catalog of catalogs){
    const root=canonPath(catalog.path),cp=canonPath(to),parent=cp.slice(0,cp.lastIndexOf('\\'));
    if(catalog.recursive?cp.startsWith(root+'\\'):parent===root){
     const existing=catalog.files.find(x=>canonPath(x.path)===cp);
     if(!existing)catalog.files.push({...destination});
     else if(existing._n8ForwardTo||existing._n8Tombstone){
      Object.assign(existing,destination);delete existing._n8ForwardTo;delete existing._n8Tombstone;
     }
    }
   }
  }
 }
 // Retain the ready row itself as its path/state cache identity changes.
 for(const {spec,key} of retained){
  const next=rowKey(spec),entry=v.rowReady.get(key);
  if(next!==key&&entry?.state==='ready'){
   v.rowReady.delete(key);v.rowReady.set(next,entry);
   if(v.prepDesired.delete(key))v.prepDesired.add(next);
  }
 }
 const cards=new Set(document.querySelectorAll('#grid .card'));
 for(const entry of v.rowReady.values())if(entry.node)for(const card of entry.node.querySelectorAll('.card'))cards.add(card);
 for(const card of cards){
  const from=card.dataset.p,to=changes.get(canonPath(from));if(!to)continue;
  if(inPlace.has(canonPath(from))){
   card.dataset.p=to;
   const label=card.querySelector('.hoverIdentity');
   if(label){label.title=to;const name=label.querySelector('span');if(name)name.textContent=to.split(/[\\/]/).pop()}
   // Already mounted pixels stay mounted; fresh prefabs use the new filepath.
   for(const img of card.querySelectorAll('img[data-thumb-url]'))img.dataset.thumbUrl=`/api/thumb?path=${enc(to)}`;
  }else{
   const f=S.files.find(x=>canonPath(x.path)===canonPath(from));if(!f)continue;
   const part=virtualCardParts(f,v.sm,v.cm,parseFloat(card.style.width)||280);
   card.innerHTML=part.inner;card._n8Inner=part.inner;card.classList.remove('selected');
  }
 }
 S.selected=new Set([...S.selected].map(translate).filter(p=>S.mobile||S.files.some(f=>canonPath(f.path)===canonPath(p)&&!f._n8ForwardTo)));
 if(pagedBrowse()){mobilePager?.movePaths(items,moveRoot,{leavePlaceholder});const destinations=new Set(items.map(item=>canonPath(item.to)));for(const f of S.files)if(changes.has(canonPath(f.path))||destinations.has(canonPath(f.path)))mobilePager?.remember(f);}
 S.multiWork=S.multiWork.map(translate);if(S.selectionAnchor)S.selectionAnchor=translate(S.selectionAnchor);
 if(S.viewer&&changes.has(canonPath(S.viewer))){
  if(inPlace.has(canonPath(S.viewer)))openViewer(translate(S.viewer));
  else closeViewer();
 }
 for(const f of S.semantic||[])f.path=translate(f.path);
 for(const f of S.compare?.results||[])f.path=translate(f.path);
 if(S.archiveAnchors){S.archiveAnchors=new Set([...S.archiveAnchors].map(translate));saveArchiveAnchors()}
 for(const from of changes.keys())S._n8LazyRenames?.delete(from);
 renderScopeFolders();refreshSelectionUI();
 $('#status').textContent=`File action complete · ${changes.size} path${changes.size===1?'':'s'} updated · grid position preserved`;
}
function releaseMovedSelection(items){
 S.selectionRequest=(S.selectionRequest||0)+1;
 const moved=new Set(items.flatMap(item=>[canonPath(item.from),canonPath(item.to)]));
 for(const path of S.selected)if(moved.has(canonPath(path)))S.selected.delete(path);
 if(S.selectionAnchor&&moved.has(canonPath(S.selectionAnchor)))S.selectionAnchor=null;
 refreshSelectionUI();
}
async function optimisticFileAction(paths,work){
 try{const r=await work();const completed=r.moved||[];patchMovedFiles(completed,{leavePlaceholder:true});releaseMovedSelection(completed);return r}
 catch(e){const completed=e.response?.detail?.completed;if(completed?.length){patchMovedFiles(completed,{leavePlaceholder:true});releaseMovedSelection(completed)}throw e}
}
function tombstonePaths(paths){
 S.selectionRequest=(S.selectionRequest||0)+1;
 const gone=new Set(paths.map(canonPath)),v=S.virtualGrid;if(pagedBrowse())mobilePager?.deletePaths(paths);
 // Record cache identities before flags change; the row objects stay in place.
 const retained=v.rows.map(spec=>({spec,key:rowKey(spec)}));
 for(const f of S.files)if(gone.has(canonPath(f.path)))f._n8Tombstone=true;
 for(const {spec,key} of retained){
  const next=rowKey(spec),entry=v.rowReady.get(key);
  if(next!==key&&entry?.state==='ready'){
   v.rowReady.delete(key);v.rowReady.set(next,entry);
   if(v.prepDesired.delete(key))v.prepDesired.add(next);
  }
 }
 for(const p of [...S.selected])if(gone.has(canonPath(p)))S.selected.delete(p);
 if(S.viewer&&gone.has(canonPath(S.viewer)))closeViewer();
 // Update mounted and prepared cards in place. No render(), no rehome.
 const deletedFiles=new Map(S.files.filter(f=>gone.has(canonPath(f.path))).map(f=>[canonPath(f.path),f]));const patch=c=>{const f=deletedFiles.get(canonPath(c.dataset.p));if(!f||!f._n8Tombstone)return;const x=virtualCardParts(f,S.virtualGrid.sm,S.virtualGrid.cm,parseFloat(c.style.width)||280);c.innerHTML=x.inner;c._n8Inner=x.inner;c.classList.remove('selected')};
 document.querySelectorAll('#grid .card').forEach(patch);
 for(const entry of S.virtualGrid.rowReady.values())if(entry.node)entry.node.querySelectorAll('.card').forEach(patch);
 refreshSelectionUI();
}
const pendingDeletes=new Set();
function paintDeletePending(card,pending){
 card.querySelector('.fileActionPending')?.remove();if(!pending)return;
 const badge=document.createElement('div');badge.className='fileActionPending';badge.textContent='Deleting…';badge.style.cssText='position:absolute;inset:0;display:grid;place-items:center;background:#0008;color:white;z-index:5;pointer-events:none';card.append(badge);
}
function showDeletePending(paths,pending){
 const keys=new Set(paths.map(canonPath)),cards=new Set(document.querySelectorAll('#grid .card'));
 for(const entry of S.virtualGrid.rowReady.values())if(entry.node)for(const card of entry.node.querySelectorAll('.card'))cards.add(card);
 for(const card of cards)if(keys.has(canonPath(card.dataset.p)))paintDeletePending(card,pending);
}

async function deleteSelected(){
 const paths=[...S.selected].filter(p=>!pendingDeletes.has(canonPath(p))&&!moveQueue.has(p));if(!paths.length)return;
 if(!confirm(`Send ${paths.length} selected file(s) to Recycle Bin?`))return;
 observationRefreshController?.abort();paths.forEach(p=>pendingDeletes.add(canonPath(p)));showDeletePending(paths,true);$('#status').textContent='Deleting '+paths.length+' file(s)…';
 // Paint acknowledgement before any response handling or filesystem bookkeeping.
 await new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0)));
 try{const r=await post('/api/files/delete',{paths}),done=r.deleted||[];if(done.length)tombstonePaths(done);if(r.failed?.length)alert(`${r.failed.length} file(s) could not be deleted.`);$('#status').textContent=done.length+' file(s) deleted'+(r.failed?.length?' · '+r.failed.length+' failed':'')}
 catch(error){alert(error.message)}finally{paths.forEach(p=>pendingDeletes.delete(canonPath(p)));showDeletePending(paths,false)}
}$('#deleteBtn').onclick=deleteSelected;
let moveParent=null,moveBrowseVersion=0,lastMoveDestination=null;
const moveDirectoryCache=createMoveDirectoryCache({fetch:path=>j(`/api/directories?path=${enc(path)}`),key:canonPath});
function displayMoveDirectory(d){
 moveParent=d.parent;$('#movePath').value=d.path;
 $('#moveFolders').innerHTML=d.directories.map(x=>`<div class="moveFolder" data-p="${esc(x.path)}">${esc(x.name)}</div>`).join('');
 document.querySelectorAll('.moveFolder').forEach(x=>x.ondblclick=()=>moveBrowse(x.dataset.p));$('#moveConfirm').disabled=false;
}
async function moveBrowse(path){
 const version=++moveBrowseVersion,cached=moveDirectoryCache.peek(path);
 $('#moveConfirm').disabled=true;
 if(cached)displayMoveDirectory(cached);else $('#moveFolders').textContent='Loading folders…';
 try{const d=await moveDirectoryCache.refresh(path);if(version!==moveBrowseVersion)return false;
  if(!cached||JSON.stringify(cached)!==JSON.stringify(d))displayMoveDirectory(d);return true;
 }catch(error){if(version===moveBrowseVersion){$('#moveConfirm').disabled=true;$('#moveFolders').textContent='Folder unavailable: '+error.message}return false}
}
const moveQueue=createMoveQueue({key:canonPath,
 queued(paths,destination){
  for(const p of paths)S.selected.delete(p);
  S.selectionRequest=(S.selectionRequest||0)+1;S.selectionAnchor=null;S.selectionAnchorMeta=null;
  refreshSelectionUI();$('#status').textContent=`Move queued · ${paths.length} file(s) → ${destination}`;
 },
 run:(paths,destination)=>optimisticFileAction(paths,()=>post('/api/files/move',{paths,destination})),
 failed(error){$('#status').textContent='Move failed: '+error.message;alert('Move failed: '+error.message+'\nCompleted files were retained. Remaining source files can be selected and retried.');},
 settled(){refreshSelectionUI()}
});

async function refreshFileHistory(show=false){try{const r=await j('/api/files/history?limit=20'),box=$('#fileHistory');if(!box)return;if(show)box.hidden=!box.hidden;box.innerHTML=(r.history||[]).map(h=>{const p=h.payload||{},detail=h.op==='mkdir'?p.path:(p.items||[]).map(x=>typeof x==='string'?x:(x.from+' → '+x.to)).join('<br>');return `<div><b>${esc(h.op)}</b>${h.undone?' · undone':''}${h.error?' · '+esc(h.error):''}<br>${esc(detail||'')}</div>`}).join('')||'No filesystem history.'}catch(e){alert(e.message)}}
$('#undoFileBtn').onclick=async()=>{try{await post('/api/files/undo',{});await load(S.path);await refreshFileHistory()}catch(e){alert(e.message)}};$('#fileHistoryBtn').onclick=()=>refreshFileHistory(true);
$('#moveBtn').onclick=async()=>{const paths=[...S.selected].filter(p=>!moveQueue.has(p));if(!paths.length)return;$('#moveCount').textContent=`${paths.length.toLocaleString()} file(s) selected`;$('#moveDialog').showModal();await moveBrowse(lastMoveDestination||S.path||S.scopeRoot||'C:\\')};
$('#moveUp').onclick=()=>moveParent&&moveBrowse(moveParent);$('#moveGo').onclick=()=>moveBrowse($('#movePath').value);$('#movePath').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();moveBrowse(e.target.value)}};
$('#moveConfirm').onclick=()=>{if($('#moveConfirm').disabled)return;const destination=$('#movePath').value;if(!destination)return;lastMoveDestination=destination;moveBrowseVersion++;$('#moveDialog').close();moveQueue.enqueue([...S.selected],destination)};$('#renameBtn').onclick=async()=>{if(S.selected.size!==1)return alert('Select exactly one file.');const p=[...S.selected][0];if(moveQueue.has(p))return alert('This image is queued for moving.');const old=p.split(/[\\/]/).pop(),input=prompt('New filename:',old);if(!input||input===old)return;const ext=old.match(/\.[^.]+$/)?.[0]||'';const n=ext&&!input.includes('.')?input+ext:input;const r=await post('/api/files/rename',{path:p,name:n});patchMovedFiles([r])};$('#mkdirBtn').onclick=async()=>{if(!S.path)return;const n=prompt('New folder name:');if(!n)return;await post('/api/files/mkdir',{parent:S.path,name:n});await refreshExploreTree()};
$('#rescanModelsBtn').onclick=()=>refreshModels(true);$('#sweepShownBtn').onclick=sweepShown;
async function qualitySeenChoice(paths){
 const k=await post('/api/mv/quality-known',{paths,batch_size:16,force:false});
 if(!k.seen)return 'skip';
 return await new Promise(resolve=>{
  const d=document.createElement('dialog');d.className='qualitySeenDialog';
  d.innerHTML=`<form method="dialog"><h3>I've Seen This One Before</h3><p>Quality data is current for <b>${k.seen.toLocaleString()}</b> of <b>${k.requested.toLocaleString()}</b> requested image${k.requested===1?'':'s'}.</p><p class="muted">Current images do not need to get in line unless you explicitly rescan them.</p><div class="buttonGrid"><button value="rescan">Rescan</button><button value="skip" autofocus>Skip Seen</button></div><button value="cancel" class="qualityCancel">Cancel</button></form>`;
  document.body.appendChild(d);d.addEventListener('close',()=>{const v=d.returnValue||'cancel';d.remove();resolve(v)},{once:true});d.showModal();
 });
}
async function manualQuality(paths){if(!paths.length)return alert('No images selected/shown.');try{const choice=await qualitySeenChoice(paths);if(choice==='cancel')return;const r=await post('/api/mv/quality',{paths,batch_size:16,force:choice==='rescan'});$('#status').textContent=r.state==='done'?'Quality scan complete/cached':`Quality ${r.id}: ${r.total} queued`;refreshJobs()}catch(e){console.warn('Manual quality failed',e)}}
$('#qualitySelectedBtn').onclick=()=>manualQuality([...S.selected]);
$('#qualityShownBtn').onclick=()=>manualQuality(visibleFiles().map(x=>x.path));
$('#classifyBtn').onclick=()=>{const l=labels();if(!l.length)return alert('Give at least one label.');job('classify',[...S.selected],{labels:l})};$('#classifyShownBtn').onclick=()=>{const l=labels();if(!l.length)return alert('Give at least one label.');job('classify',visibleFiles().map(x=>x.path),{labels:l})};$('#detectShownBtn').onclick=()=>job('detect',visibleFiles().map(x=>x.path),{model:$('#detectorModel').value.trim()||'yolo11n.pt'});$('#segmentShownBtn').onclick=()=>job('segment',visibleFiles().map(x=>x.path));
$('#neighborCount').oninput=e=>$('#neighborValue').textContent=e.target.value+' neighbors';
function comparisonPaths(){return visibleFiles({ignoreCompare:true}).filter(f=>!f._n8Tombstone&&!f._n8ForwardTo).map(f=>f.path)}
function commitComparison(kind,results){
 S.compare=kind?{kind,results}:null;
 S.sortKey=kind==='similar'?'similarity':kind==='unique'?'uniqueness':'none';S.sortDir='desc';
 $('#sortKey').value=S.sortKey;$('#sortDir').textContent='↓';
 // Comparison is an explicit new view: discard stale score prefabs, retain
 // thumbnail assets, and present the highest-ranked result first.
 const v=S.virtualGrid;v.prepGeneration++;v.rowReady=new Map();v.prepDesired=new Set();v.prepQueue=[];v.cursor=0;
 render();
}
$('#similarBtn').onclick=async()=>{if(S.selected.size!==1)return alert('Select exactly one image.');const path=[...S.selected][0];$('#status').textContent='Finding similar images…';try{const r=await post('/api/compare/similar',{path,paths:comparisonPaths(),limit:Math.min(5000,S.files.length)});if(!r.results.length){$('#compareInfo').textContent='No embedded neighbors in this scope.';$('#status').textContent='No similarity results';return}commitComparison('similar',r.results);$('#compareInfo').textContent=`${r.results.length} neighbors ranked from ${r.searched} embedded images`;$('#status').textContent='Similarity ready'}catch(e){alert(e.message);$('#status').textContent='Similarity failed'}};
$('#uniqueBtn').onclick=async()=>{$('#status').textContent='Building uniqueness neighborhood…';try{const r=await post('/api/compare/unique',{paths:comparisonPaths(),neighbors:Number($('#neighborCount').value)});if(!r.results.length){$('#compareInfo').textContent='Uniqueness needs at least two embedded images in this scope.';$('#status').textContent='Not enough embeddings';return}commitComparison('unique',r.results);$('#compareInfo').textContent=`Uniqueness: ${r.searched} images, ${r.neighbors} nearest neighbors`;$('#status').textContent='Uniqueness ready'}catch(e){alert(e.message);$('#status').textContent='Uniqueness failed'}};
$('#duplicatesBtn').onclick=async()=>{$('#status').textContent='Checking similarity near-hits for identical pixels…';try{const r=await post('/api/compare/duplicates',{paths:comparisonPaths(),neighbors:Number($('#neighborCount').value)});commitComparison('duplicates',r.results);$('#compareInfo').textContent=`Duplicates: ${r.results.length} files in ${r.groups} exact visual groups; ${r.candidates} near-hit pairs checked`;$('#status').textContent='Duplicate filter ready'}catch(e){alert(e.message);$('#status').textContent='Duplicate check failed'}};
$('#clearCompareBtn').onclick=()=>{commitComparison(null,[]);$('#compareInfo').textContent='Uses stored CLIP embeddings. The neighbor knob drives uniqueness and duplicate candidate search.'};
$('#semanticBtn').onclick=async()=>{const q=$('#semantic').value.trim();if(!q)return;$('#status').textContent='Semantic search…';const r=await post('/api/search/semantic',{query:q,paths:S.files.map(x=>x.path),limit:Math.min(5000,S.files.length)});S.semantic=r.results;render();$('#status').textContent=`Semantic search: ${r.results.length} results from ${r.searched} embeddings`};$('#clearSemanticBtn').onclick=()=>{S.semantic=null;render()};
$('#discardShownAnalysisBtn').onclick=async()=>{
 const shown=visibleFiles(),paths=shown.map(x=>x.path);
 if(!paths.length){alert('Nothing is currently shown.');return}
 if(!confirm(`Discard N8Vision analysis for the ${paths.length} currently shown image${paths.length===1?'':'s'}?\n\nThis removes observations, receipts, quality scores and embeddings for only this filtered population. Source images are untouched.`))return;
 try{
  const r=await post('/api/dev/analysis/shown',{paths});
  S.semantic=null;S.compare=null;S.selected.clear();
  if(S.path)await load(S.path);
  $('#status').textContent=`Reset ${r.discarded.files} shown files: ${r.discarded.observations} observations, ${r.discarded.embeddings} embeddings`;
 }catch(e){alert(e.message)}
};
$('#discardAnalysisBtn').onclick=async()=>{
 if(!confirm('Discard ALL N8Vision analysis data?\n\nThis wipes classifications, detections, masks, embeddings and job history. Source images are untouched.'))return;
 try{
  const r=await j('/api/dev/analysis',{method:'DELETE'});
  S.semantic=null; S.selected.clear();
  if(S.path) await load(S.path);
  await refreshJobs();
  $('#status').textContent=`Whiteboard wiped: ${r.discarded.observations} observations, ${r.discarded.embeddings} embeddings, ${r.discarded.jobs} jobs`;
 }catch(e){alert(e.message)}
};
const gridEl=$('#grid');
setupArchiveNavigator();
window.addEventListener('resize',()=>{if(S.mobile){reflowMobileColumns();return;}invalidateRingLayout();renderVirtualGrid()});
 if(S.mobile){document.body.classList.add('mobileArchive');$('#thumbSize').closest('label').hidden=true;$('#mobileColumnsLabel').hidden=false;$('#mobilePagingInfo').hidden=false;syncMobileColumnControl();$('#mobileColumns').oninput=e=>{const o=mobileOrientation();mobileColumnPrefs[o]=Number(e.target.value);localStorage.setItem('n8vision.columns.'+o,e.target.value);reflowMobileColumns()};window.visualViewport?.addEventListener('resize',reflowMobileColumns)}
init().catch(e=>{$('#status').textContent=e.message});

// --- 0.9.0 Ordering workspace ---
S.mode='explore';S.orderPaths=[];S.trainingProject=null;S.trainingOptions=null;
function setMode(mode){if(mode==='ordering'&&!S.capabilities.processing)mode='explore';S.mode=mode;const ordering=mode==='ordering';$('#explorePanel').hidden=ordering;$('#orderingPanel').hidden=!ordering;$('#exploreModeBtn').classList.toggle('active',!ordering);$('#orderingModeBtn').classList.toggle('active',ordering);refreshJobs();if(ordering){refreshTrainingOptions();refreshLearningOptions();refreshEnvironments()}}
$('#exploreModeBtn').onclick=()=>setMode('explore');$('#orderingModeBtn').onclick=()=>setMode('ordering');
function stageOrder(paths,label){S.orderPaths=[...new Set(paths)];$('#orderPopulation').innerHTML=`<span class="orderCurrent">${S.orderPaths.length.toLocaleString()}</span> images staged from ${esc(label)}.`}
$('#orderUseShown').onclick=()=>stageOrder(visibleFiles().map(x=>x.path),'shown population');
$('#orderUseSelected').onclick=()=>stageOrder([...S.selected],'selection');
async function refreshTrainingOptions(){if(!S.capabilities.processing)return;
 try{const r=await j('/api/training/options');S.trainingOptions=r;if(!$('#trainingRoot').value)$('#trainingRoot').value=r.default_root;$('#modelProfile').innerHTML=Object.entries(r.model_profiles).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name)}</option>`).join('');$('#trainerTarget').innerHTML=Object.entries(r.trainers).map(([k,v])=>`<option value="${esc(k)}">${esc(v.name)}</option>`).join('')}catch(e){console.warn(e)}
}
function renderTrainingProject(){const d=S.trainingProject;if(!d){$('#trainingProjectInfo').textContent='No project open.';$('#trainingTerms').innerHTML='';const td=$('#trainingDiagnostics');if(td)td.textContent='Open a project for bucket/review diagnostics.';return}$('#trainingProjectPath').value=d.folder;$('#trainingName').value=d.name;$('#modelProfile').value=d.model_profile;$('#trainerTarget').value=d.working_target;const targets=Object.entries(d.targets||{}).map(([k,v])=>`${k}: ${v.status}`).join(' · ');$('#trainingProjectInfo').innerHTML=`<b>${esc(d.name)}</b><br>${(d.items||[]).length} images · revision ${d.revision}${targets?`<br>${esc(targets)}`:''}`;$('#trainingTerms').innerHTML=Object.entries(d.batch_terms||{}).map(([term,state])=>`<span class="trainingTerm ${state>0?'pos':state<0?'neg':''}">${state>0?'+':state<0?'−':'0'} ${esc(term)}</span>`).join('')||'<span class="tiny">No batch terms yet.</span>';refreshTrainingDiagnostics()}
async function refreshTrainingDiagnostics(){if(!S.trainingProject)return;try{const r=await j(`/api/training/diagnostics?path=${enc(S.trainingProject.folder)}`),top=Object.entries(r.buckets||{}).slice(0,5).map(([k,v])=>`${k} ×${v}`).join(' · ');$('#trainingDiagnostics').textContent=`Included ${r.included} · Excluded ${r.excluded} · Reviewed ${r.reviewed}/${r.included}${top?' · Buckets: '+top:''}`}catch(e){$('#trainingDiagnostics').textContent=e.message}}
async function trainingReview(include,reviewed){if(!S.trainingProject)return alert('Open or create a training project first.');const paths=[...S.selected];if(!paths.length)return alert('Select project/source images first.');try{const r=await post('/api/training/review',{project:S.trainingProject.folder,paths,include,reviewed});S.trainingProject=r.project;renderTrainingProject();$('#status').textContent=`Updated ${r.changed} training item${r.changed===1?'':'s'}.`}catch(e){alert(e.message)}}
$('#createTrainingBtn').onclick=async()=>{if(!S.orderPaths.length)return alert('Stage shown or selected images first.');const name=$('#trainingName').value.trim();if(!name)return alert('Give the training project a name.');try{const r=await post('/api/training/create',{name,paths:S.orderPaths,root:$('#trainingRoot').value.trim()||null,model_profile:$('#modelProfile').value,trainer:$('#trainerTarget').value});S.trainingProject=r.project;renderTrainingProject();$('#status').textContent=`Training project created: ${r.project.folder}`}catch(e){}}
$('#openTrainingBtn').onclick=async()=>{const path=$('#trainingProjectPath').value.trim();if(!path)return;try{const r=await j(`/api/training/project?path=${enc(path)}`);S.trainingProject=r.project;renderTrainingProject()}catch(e){alert(e.message)}};
async function addToTrainingProject(paths,label){if(!S.trainingProject)return alert('Open or create a training project first.');paths=[...new Set(paths)].filter(Boolean);if(!paths.length)return alert(`No ${label} images to add.`);try{const r=await post('/api/training/add',{project:S.trainingProject.folder,paths});S.trainingProject=r.project;renderTrainingProject();$('#status').textContent=`Project basket: added ${r.added} · already present ${r.duplicates} · skipped ${r.skipped}. Still browsing ${S.path}.`}catch(e){alert(e.message)}}
$('#addShownProjectBtn').onclick=()=>addToTrainingProject(visibleFiles().map(x=>x.path),'visible');
$('#addSelectedProjectBtn').onclick=()=>addToTrainingProject([...S.selected],'selected');
$('#reviewTrainingBtn').onclick=async()=>{if(!S.trainingProject)return alert('Open or create a training project first.');$('#recursive').checked=false;await load(S.trainingProject.folder,true);$('#status').textContent=`Reviewing project: ${S.trainingProject.name} · ${(S.trainingProject.items||[]).length} images`;};
$('#includeSelectedBtn').onclick=()=>trainingReview(true,null);$('#excludeSelectedBtn').onclick=()=>trainingReview(false,null);$('#reviewedSelectedBtn').onclick=()=>trainingReview(null,true);$('#findNeighborsBtn').onclick=async()=>{if(!S.trainingProject)return alert('Open or create a training project first.');const seed=[...S.selected][0];if(!seed)return alert('Select one embedded image as the seed.');try{const r=await post('/api/training/neighbors',{project:S.trainingProject.folder,path:seed,limit:96});const wanted=new Set(r.neighbors.map(x=>x.path));S.similarityRef=seed;commitComparison('similar',r.neighbors.map(x=>({path:x.path,score:x.similarity})));$('#status').textContent=`Found ${r.neighbors.length} embedding neighbors for ${seed.split(/[\\/]/).pop()}. Similarity sort is ready.`}catch(e){alert(e.message)}};
async function applyTrainingTerm(selectedOnly){if(!S.trainingProject)return alert('Open or create a training project first.');const term=$('#trainingTerm').value.trim();if(!term)return;let paths=null;if(selectedOnly){paths=[...S.selected];if(!paths.length)return alert('Select one or more source images in the grid first.')}try{const r=await post('/api/training/policy',{project:S.trainingProject.folder,term,state:Number($('#trainingTermState').value),paths});S.trainingProject=r.project;renderTrainingProject();$('#trainingTerm').value=''}catch(e){}}
$('#termBatchBtn').onclick=()=>applyTrainingTerm(false);$('#termSelectedBtn').onclick=()=>applyTrainingTerm(true);
$('#assembleTrainingBtn').onclick=async()=>{if(!S.trainingProject)return alert('Open or create a training project first.');try{const r=await post('/api/training/assemble',{project:S.trainingProject.folder,trainer:$('#trainerTarget').value,model_profile:$('#modelProfile').value});S.trainingProject=r.project;renderTrainingProject();$('#status').textContent=`Assembled ${r.files} images → ${r.output}`}catch(e){}}
$('#prepareComfyTrainingBtn').onclick=async()=>{if(!S.trainingProject)return alert('Open or create a training project first.');try{const r=await post('/api/training/prepare-comfy',{project:S.trainingProject.folder});S.trainingProject=r.project;renderTrainingProject();const staged=!!r.stage?.staged;$('#status').textContent=staged?`Prepared and staged in Comfy: ${r.workspace} — inspect it, then queue manually.`:`Prepared for Comfy: ${r.workspace} — bridge staging unavailable; File > Open the workflow.`;alert(staged?`Prepared and loaded onto the Comfy canvas — NOT queued.\n\nDataset: ${r.dataset}\nWorkflow: ${r.workflow}\n\nTweak whatever deserves tweaking, then hit Queue Prompt yourself.`:`Prepared, not queued.\n\nDataset: ${r.dataset}\nWorkflow: ${r.workflow}\n\nComfy bridge staging was unavailable (${r.stage?.error||'unknown reason'}). Use File > Open on the workflow.`)}catch(e){alert(e.message)}};
$('#archiveTrainingBtn').onclick=async()=>{if(!S.trainingProject)return alert('Open or create a training project first.');if(!confirm(`Archive ${S.trainingProject.name}?\n\nThis packs the prepared Comfy workspace, verifies the ZIP, then removes the expanded workspace. The archive remains resumable.`))return;try{const r=await post('/api/training/archive',{project:S.trainingProject.folder});S.trainingProject=r.project;renderTrainingProject();$('#status').textContent=`Archived training project → ${r.archive}`;alert(`Packed away.\n\n${r.archive}\n\nThe expanded Comfy workspace was removed after verification.`)}catch(e){alert(e.message)}};
function populateEvolutionModels(){const r=S.learningOptions;if(!r)return;const base=$('#evolveBaseModel'),mode=$('#evolveMode')?.value||'new';if(!base)return;const eligible=mode==='add_segmentation'?r.models.filter(m=>!m.segmentation):r.models;base.innerHTML='<option value="">— none / new model —</option>'+eligible.map(m=>`<option value="${esc(m.path)}">${esc(m.name)} · ${m.segmentation?'SEG':'BBOX'} · ${(m.classes||[]).length} classes</option>`).join('');base.disabled=mode==='new';if(mode==='new')base.value=''}
async function refreshLearningOptions(){if(!S.capabilities.inference)return;try{const r=await j('/api/learning/options');S.learningOptions=r;populateEvolutionModels();const c=$('#evolveClasses');if(c&&!c.value)c.value='';const st=r.settings||{};if($('#maintenanceEnabled'))$('#maintenanceEnabled').checked=!!st.maintenance_enabled;if($('#maintenanceTime'))$('#maintenanceTime').value=st.maintenance_time||'03:00';if($('#maintenanceThreshold'))$('#maintenanceThreshold').value=st.correction_threshold||25;const q=$('#learningStatus');if(q)q.textContent=`${r.manual_observations||0} manual observations archived · ${r.bbox_only.length} bbox-only model/classes eligible for segmentation.`}catch(e){console.warn(e)}}
$('#evolveMode').onchange=populateEvolutionModels;
function evolvePayload(){return {mode:$('#evolveMode').value,name:$('#evolveName').value.trim()||'n8vision-seg',base_model:$('#evolveBaseModel').value||null,classes:$('#evolveClasses').value.split(',').map(x=>x.trim()).filter(Boolean),epochs:Number($('#evolveEpochs').value)||100,imgsz:Number($('#evolveImgsz').value)||640,batch:-1}}
$('#evolveYoloBtn').onclick=async()=>{const p=evolvePayload();if(p.mode!=='new'&&!p.base_model)return alert('Choose the extant YOLO to evolve.');if(!confirm(`Start ${p.mode.replaceAll('_',' ')} training for ${p.name}?\n\nMasked observations are the training truth. Existing model: ${p.base_model||'new model'}`))return;try{const r=await post('/api/learning/evolve',p);$('#status').textContent=`YOLO evolution ${r.id} queued · ${p.name}`;refreshJobs()}catch(e){alert(e.message)}};
$('#saveLearningMaintenance').onclick=async()=>{try{const r=await j('/api/learning/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({maintenance_enabled:$('#maintenanceEnabled').checked,maintenance_time:$('#maintenanceTime').value,correction_threshold:Number($('#maintenanceThreshold').value)||25})});$('#status').textContent=`Learning maintenance ${r.maintenance_enabled?'armed':'disabled'} · ${r.maintenance_time} · ${r.correction_threshold} corrections`;refreshLearningOptions()}catch(e){alert(e.message)}};
async function refreshEnvironments(){if(!S.capabilities.processing)return;try{const r=await j('/api/environments');let h=`<div class="envGroup"><div class="envHead"><b>Internal</b><span>${r.internal.length} workflow${r.internal.length===1?'':'s'}</span></div><div class="envWorkflows">${r.internal.length?r.internal.map(w=>`<div class="envWorkflow">${esc(w.name)}</div>`).join(''):'N8Vision workflow shelf is empty.'}</div></div>`;h+=`<div class="subhead">Their Stuff</div>`;h+=(r.environments.length?r.environments.map(e=>`<div class="envGroup"><div class="envHead"><b>${esc(e.name)}</b><span class="${e.online?'online':'offline'}">${e.online?'● online':'○ offline'}</span></div>${!e.online&&e.start_command?`<button class="envStart" data-env="${esc(e.id)}">Start server</button>`:''}<div class="envWorkflows">${(e.workflows||[]).length?e.workflows.map(w=>`<button class="envWorkflow sendWorkflow" data-env="${esc(e.id)}" data-kind="${esc(e.kind||'')}" data-workflow="${esc(w.path)}" title="${esc(w.path)}">${esc(w.name)}</button>`).join(''):'No workflows discovered.'}</div></div>`).join(''):'<div class="tiny">No environments have proclaimed themselves yet.</div>');$('#environmentShelf').innerHTML=h;document.querySelectorAll('.envStart').forEach(b=>b.onclick=async()=>{try{await post(`/api/environments/start/${enc(b.dataset.env)}`,{});b.textContent='Starting…';setTimeout(refreshEnvironments,1500)}catch(e){}});document.querySelectorAll('.sendWorkflow').forEach(b=>b.onclick=()=>prepareExternalJob(b))}catch(e){$('#environmentShelf').textContent=e.message}}
$('#refreshEnvironmentsBtn').onclick=refreshEnvironments;
const nativeUnlock=$('#unlockNativeToolsBtn'),nativeShelf=$('#nativeToolsShelf');
nativeUnlock.onclick=()=>{const opening=nativeShelf.hidden;nativeShelf.hidden=!opening;nativeUnlock.textContent=opening?'Lock Native Tools':'Unlock Native Tools'};
function rasterPaths(which){return which==='selected'?[...S.selected]:visibleFiles().map(f=>f.path)}
function rasterSettings(){return {thumbnail:Number($('#rasterThumb').value)||256,edge_threshold:Number($('#rasterThreshold').value)||24,light_blur:Number($('#rasterLight').value),medium_blur:Number($('#rasterMedium').value),heavy_blur:Number($('#rasterHeavy').value),grade_b_largest_fraction:Number($('#rasterGradeB').value),uncapped_unsanity:!!S.uncappedUnsanity}}
async function saveRasterSettings(){try{await j('/api/config/sanity',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(rasterSettings())})}catch(e){}}
['#rasterThumb','#rasterThreshold','#rasterLight','#rasterMedium','#rasterHeavy','#rasterGradeB'].forEach(sel=>{const el=$(sel);if(el)el.addEventListener('change',saveRasterSettings)});
async function runRasterSanity(which,forceOverride=null){
 const paths=rasterPaths(which);if(!paths.length)return alert('No images to scan.');
 const {thumbnail,edge_threshold,light_blur,medium_blur,heavy_blur,grade_b_largest_fraction}=rasterSettings(),force=forceOverride===null?$('#rasterForce').checked:!!forceOverride;
 await saveRasterSettings();
 try{const r=await post('/api/native/raster-sanity-v4',{paths,thumbnail,edge_threshold,light_blur,medium_blur,heavy_blur,grade_b_largest_fraction,force,manual:true});$('#rasterStatus').textContent=`Sanity v4 ${r.id} started · ${paths.length} candidate${paths.length===1?'':'s'}`;refreshJobs()}catch(e){}
}
$('#rasterSelectedBtn').onclick=()=>runRasterSanity('selected');
$('#rasterShownBtn').onclick=()=>runRasterSanity('shown');
const resanityShownBtn=$('#resanityShownBtn');if(resanityShownBtn)resanityShownBtn.onclick=()=>runRasterSanity('shown',true);
async function runYuan(which){
 const paths=rasterPaths(which);if(!paths.length)return alert('No images to score.');
 try{const choice=await qualitySeenChoice(paths);if(choice==='cancel')return;const r=await post('/api/mv/quality',{paths,batch_size:16,force:choice==='rescan'});$('#yuanStatus').textContent=r.state==='done'?`Yuan: ${r.cached||paths.length} already scored`:`Yuan ${r.id} started · ${r.total} queued`;refreshJobs()}catch(e){}
}
$('#yuanSelectedBtn').onclick=()=>runYuan('selected');
$('#yuanShownBtn').onclick=()=>runYuan('shown');

function updateThumbnailCacheLabel(){const e=$('#thumbnailCachePath');if(e)e.value=S.thumbnailCache?.path||''}
async function saveThumbnailCache(path){try{const r=await j('/api/config/thumbnail-cache',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path||null})});S.thumbnailCache=r;updateThumbnailCacheLabel();$('#status').textContent=`Thumbnail cache: ${r.path} · max axis ${r.max_axis}px.`}catch(e){alert(e.message)}}
const saveThumbnailCacheBtn=$('#saveThumbnailCacheBtn');if(saveThumbnailCacheBtn)saveThumbnailCacheBtn.onclick=()=>{const p=$('#thumbnailCachePath').value.trim();if(!p)return alert('Enter a cache directory, or choose Use Automatic.');saveThumbnailCache(p)};
const autoThumbnailCacheBtn=$('#autoThumbnailCacheBtn');if(autoThumbnailCacheBtn)autoThumbnailCacheBtn.onclick=()=>saveThumbnailCache(null);
const deleteOrphanThumbs=$('#deleteOrphanThumbs');if(deleteOrphanThumbs)deleteOrphanThumbs.onchange=async e=>{try{await j('/api/config/thumbnail-maintenance',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({delete_orphans_on_maintenance:!!e.target.checked})});if(S.thumbnailCache)S.thumbnailCache.delete_orphans_on_maintenance=!!e.target.checked}catch(err){alert(err.message)}};
async function refreshStorageClass(){if(!S.path)return;try{const r=await j('/api/storage-class?path='+enc(S.path));S.storageClass=r;const sel=$('#storageClass');if(sel)sel.value=r.configured||'auto';const st=$('#storageClassStatus');if(st)st.textContent=`${r.root} · detected ${r.detected} · effective ${r.effective} · ${r.volume_key}`}catch(e){}}
const saveStorageClassBtn=$('#saveStorageClassBtn');if(saveStorageClassBtn)saveStorageClassBtn.onclick=async()=>{if(!S.path)return alert('Open a library location first.');try{const r=await j('/api/storage-class',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:S.path,storage_class:$('#storageClass').value})});S.storageClass=r;refreshStorageClass();$('#status').textContent=`Storage class: ${r.effective}.`}catch(e){alert(e.message)}};
const driveExportBtn=$('#driveExportBtn');if(driveExportBtn)driveExportBtn.onclick=async()=>{if(!S.path)return alert('Open a library location on the drive to export.');if(!confirm('Create a portable N8Vision archive snapshot at this drive root?'))return;const st=$('#driveExportStatus');st.textContent='Exporting observations, geometry, receipts and selected portable assets…';try{const r=await post('/api/drive-export',{path:S.path,include_thumbnails:!!$('#exportThumbs')?.checked,include_projects:!!$('#exportProjects')?.checked});st.textContent=`Snapshot ready: ${r.archive} · ${r.counts.tracked_files} files · ${r.counts.observations} observations · ${(r.bytes/1048576).toFixed(1)} MB`;$('#status').textContent='Drive snapshot export complete.'}catch(e){st.textContent='Export failed: '+e.message}};
function updateDefaultRootLabel(){const e=$('#defaultRootValue');if(e)e.textContent=S.defaultRoot||'Not set'}
const gridDetailSetting=$('#gridDetailSetting');if(gridDetailSetting)gridDetailSetting.onchange=async e=>{const mode=e.target.value;try{const r=await j('/api/config/display',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({grid_detail:mode})});S.gridDetail=r.grid_detail;document.body.dataset.gridDetail=S.gridDetail;render();$('#status').textContent=`Observation badges: ${S.gridDetail}.`}catch(err){alert(err.message)}};
const gridGapSetting=$('#gridGapSetting');if(gridGapSetting)gridGapSetting.oninput=e=>{S.gridGapTenths=Number(e.target.value)||0;document.documentElement.style.setProperty('--grid-gap-tenths',S.gridGapTenths);$('#gridGapValue').textContent=(S.gridGapTenths/10).toFixed(1)+'vw';invalidateRingLayout();render()};if(gridGapSetting)gridGapSetting.onchange=async()=>{try{await j('/api/config/display',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({grid_detail:S.gridDetail,grid_gap_tenths:S.gridGapTenths})})}catch(err){alert(err.message)}};
const sanityBadgeSetting=$('#sanityBadgeSetting');if(sanityBadgeSetting)sanityBadgeSetting.onchange=async e=>{const mode=e.target.value;try{const r=await j('/api/config/sanity-display',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({sanity_badges:mode})});S.sanityBadges=r.sanity_badges;render();$('#status').textContent=`Sanity badges: ${S.sanityBadges}.`}catch(err){alert(err.message)}};
const setDefaultRootBtn=$('#setDefaultRootBtn');if(setDefaultRootBtn)setDefaultRootBtn.onclick=async()=>{if(!S.path)return alert('Open a library root first.');try{const r=await j('/api/config/default-root',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:S.path})});S.defaultRoot=r.default_root;updateDefaultRootLabel();$('#status').textContent='Current root saved as startup default.'}catch(e){alert(e.message)}};
const clearDefaultRootBtn=$('#clearDefaultRootBtn');if(clearDefaultRootBtn)clearDefaultRootBtn.onclick=async()=>{try{await j('/api/config/default-root',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:null})});S.defaultRoot=null;updateDefaultRootLabel();$('#status').textContent='Default root cleared.'}catch(e){alert(e.message)}};
const saveFilterPresetBtn=$('#saveFilterPresetBtn');if(saveFilterPresetBtn)saveFilterPresetBtn.onclick=async()=>{const suggested=$('#filterPresetSelect')?.value||'',name=prompt('Filter preset name:',suggested);if(!name)return;try{const r=await j('/api/filter-presets',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,state:presetState()})});S.filterPresets=r.presets||{};refreshPresetSelect();$('#filterPresetSelect').value=name.trim();$('#status').textContent=`Saved filter preset: ${name.trim()}`}catch(e){alert(e.message)}};
const loadFilterPresetBtn=$('#loadFilterPresetBtn');if(loadFilterPresetBtn)loadFilterPresetBtn.onclick=()=>{const n=$('#filterPresetSelect')?.value;if(n&&S.filterPresets[n])applyFilterPreset(S.filterPresets[n])};
const deleteFilterPresetBtn=$('#deleteFilterPresetBtn');if(deleteFilterPresetBtn)deleteFilterPresetBtn.onclick=async()=>{const n=$('#filterPresetSelect')?.value;if(!n)return;if(!confirm(`Delete filter preset “${n}”?`))return;try{const r=await j('/api/filter-presets/'+encodeURIComponent(n),{method:'DELETE'});S.filterPresets=r.presets||{};refreshPresetSelect()}catch(e){alert(e.message)}};
refreshPresetSelect();

// Mirror the existing job queue into Ordering without creating a second queue.
// P.33: job telemetry is rendered only into the active panel by refreshJobs().
// Do not clone the Jobs DOM into the hidden mode every 1.1s; that manufactured detached nodes forever.


// --- 0.9.2 Prepare Job: visual instance masks + provenance ---
S.jobPrep=null;S.jobPrepImage=0;S.jobPrepRegion=null;
function closeJobPrep(){S.jobPrep=null;S.jobPrepRegion=null;$('#jobPrep').hidden=true}
$('#jobPrepClose').onclick=closeJobPrep;$('.jobPrepBackdrop').onclick=closeJobPrep;
function prepQueued(){return [...document.querySelectorAll('.jobRegionCheck:checked')].length}
function updatePrepCount(){if(!S.jobPrep)return;const needsMask=!!S.jobPrep.requires_mask;const n=prepQueued();$('#jobPrepCount').textContent=needsMask?`${n} region${n===1?'':'s'} queued → ${n} job${n===1?'':'s'}`:`${S.jobPrep.paths.length} image${S.jobPrep.paths.length===1?'':'s'} queued`;$('#jobExecute').disabled=needsMask&&!n}
function prepGeom(reg){try{return typeof reg.geometry==='string'?JSON.parse(reg.geometry):reg.geometry}catch{return{}}}
function prepSourceSize(item){for(const r of item.regions){const g=prepGeom(r);if(g.source_size?.length>=2)return g.source_size.map(Number);if(g.size?.length>=2)return [Number(g.size[1]),Number(g.size[0])]};return null}
function prepShape(reg){const g=prepGeom(reg),color=detectorColor(reg.provider,reg.model),cl=`prepGeom ${document.querySelector(`.jobRegionCheck[data-ridx="${reg._idx}"]`)?.checked?'queued':'off'} ${S.jobPrepRegion===reg._idx?'active':''}`;if(g.polygon?.length){const pts=g.polygon.map(p=>`${Number(p[0])},${Number(p[1])}`).join(' ');return `<polygon class="${cl}" data-ridx="${reg._idx}" points="${pts}" stroke="${color}"></polygon>`}if(g.bbox?.length>=4){const[x1,y1,x2,y2]=g.bbox.map(Number);return `<rect class="${cl}" data-ridx="${reg._idx}" x="${x1}" y="${y1}" width="${Math.max(0,x2-x1)}" height="${Math.max(0,y2-y1)}" stroke="${color}"></rect>`}if(g.source_bbox?.length>=4){const[x1,y1,x2,y2]=g.source_bbox.map(Number);return `<rect class="${cl}" data-ridx="${reg._idx}" x="${x1}" y="${y1}" width="${Math.max(0,x2-x1)}" height="${Math.max(0,y2-y1)}" stroke="${color}"></rect>`}return''}
function paintMask(reg,item){const cv=$('#jobMaskPreview'),ctx=cv.getContext('2d'),img=$('#jobSourceImage'),g=prepGeom(reg),sz=prepSourceSize(item)||[img.naturalWidth||512,img.naturalHeight||512],w=Math.max(1,sz[0]),h=Math.max(1,sz[1]);cv.width=w;cv.height=h;ctx.fillStyle='#000';ctx.fillRect(0,0,w,h);ctx.fillStyle='#fff';if(g.polygon?.length){ctx.beginPath();g.polygon.forEach((p,i)=>i?ctx.lineTo(+p[0],+p[1]):ctx.moveTo(+p[0],+p[1]));ctx.closePath();ctx.fill()}else if(g.rle?.length&&g.size?.length>=2){const mh=+g.size[0],mw=+g.size[1],tmp=document.createElement('canvas');tmp.width=mw;tmp.height=mh;const tc=tmp.getContext('2d'),im=tc.createImageData(mw,mh);for(const[a,b]of g.rle)for(let q=+a;q<+b;q++)im.data[q*4+3]=255,im.data[q*4]=im.data[q*4+1]=im.data[q*4+2]=255;tc.putImageData(im,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(tmp,0,0,w,h)}else{const b=g.bbox||g.source_bbox;if(b?.length>=4)ctx.fillRect(+b[0],+b[1],Math.max(0,+b[2]-+b[0]),Math.max(0,+b[3]-+b[1]))}$('#jobMaskCaption').textContent=`${observationLabel(reg)} · ${reg.kind.toUpperCase()} · ${Math.round(observationConfidence(reg)*100)}% · ${reg.provider}`}
function selectPrepRegion(idx){idx=Number(idx);S.jobPrepRegion=idx;const item=S.jobPrep.items[S.jobPrepImage],reg=item?.regions.find(r=>r._idx===idx);document.querySelectorAll('.jobRegion').forEach(x=>x.classList.toggle('active',Number(x.dataset.ridx)===idx));renderPrepImage();if(reg)paintMask(reg,item)}
function renderPrepImage(){const p=S.jobPrep,item=p?.items[S.jobPrepImage];if(!item)return;const img=$('#jobSourceImage'),svg=$('#jobSourceOverlay'),sz=prepSourceSize(item);img.src=`/api/file?path=${enc(item.path)}`;if(sz)svg.setAttribute('viewBox',`0 0 ${sz[0]} ${sz[1]}`);else img.onload=()=>{if(img.naturalWidth)svg.setAttribute('viewBox',`0 0 ${img.naturalWidth} ${img.naturalHeight}`)};svg.innerHTML=item.regions.map(prepShape).join('');svg.querySelectorAll('.prepGeom').forEach(x=>x.onclick=e=>{e.stopPropagation();selectPrepRegion(x.dataset.ridx)});document.querySelectorAll('.jobRegion').forEach(x=>x.dataset.hidden=String(x.dataset.path!==item.path));document.querySelectorAll('.jobImageTab').forEach((x,i)=>x.classList.toggle('active',i===S.jobPrepImage))}
async function prepareExternalJob(b){
 const paths=S.selected.size?[...S.selected]:visibleFiles().map(x=>x.path);if(!paths.length)return alert('No images staged. Select images or leave selection empty to use shown.');
 try{
  const r=await post('/api/environments/prepare',{environment_id:b.dataset.env,workflow:b.dataset.workflow,paths});S.jobPrep={...r,environment_id:b.dataset.env,workflow:b.dataset.workflow,paths};S.jobPrepImage=0;S.jobPrepRegion=null;
  $('#jobPrepTitle').textContent=`${r.workflow} · ${paths.length} image${paths.length===1?'':'s'}`;
  $('#jobPrepNeeds').innerHTML=(r.format==='ui'?'<span class="jobNeed" title="Vision converts the saved Comfy graph to API prompt format at dispatch">UI JSON → API</span>':'')+(r.tokens.length?r.tokens.map(t=>`<span class="jobNeed">${esc(t.replace('{{N8VISION_','').replace('}}',''))}</span>`).join(''):'<span class="tiny">No N8Vision placeholders found.</span>');
  let rows='',idx=0;for(const item of r.items){for(const reg of item.regions){const id=idx++;reg._path=item.path;reg._idx=id;rows+=`<label class="jobRegion" data-path="${esc(item.path)}" data-ridx="${id}"><input class="jobRegionCheck" data-ridx="${id}" type="checkbox" checked><span><b>${esc(observationLabel(reg))}</b><br><span class="tiny">${esc(reg.provider)} · ${Math.round(observationConfidence(reg)*100)}%</span></span><span class="geomKind">${esc(reg.kind.toUpperCase())}</span></label>`}}
  $('#jobRegionList').innerHTML=rows||'<div class="tiny">No geometry in staged images.</div>';$('#jobImageTabs').innerHTML=r.items.map((x,i)=>`<button class="jobImageTab" data-i="${i}" title="${esc(x.path)}">${esc(x.name)}</button>`).join('');
  const first=r.items[0]?.metadata||{};$('#jobPositive').value=first.positive||'';$('#jobNegative').value=first.negative||'';
  const differing=r.items.some(x=>(x.metadata?.positive||'')!==(first.positive||'')||(x.metadata?.negative||'')!==(first.negative||''));
  $('#jobMetaInfo').textContent=`Scraped from ${r.items[0]?.name||'image'}${differing?' · staged images contain differing prompts; this edit applies to this dispatch':''}${first.model?' · model: '+first.model:''}${first.seed!=null?' · seed: '+first.seed:''}`;
  $('#jobLoras').innerHTML=(first.loras||[]).length?'<div class="tiny">LoRAs found in provenance</div>'+first.loras.map(x=>`<span class="jobLora">${esc(x.name)}${x.weight?' @ '+esc(x.weight):''}</span>`).join(''):'';
  document.querySelectorAll('.jobRegionCheck').forEach(c=>c.onchange=e=>{e.stopPropagation();c.closest('.jobRegion').classList.toggle('off',!c.checked);renderPrepImage();updatePrepCount()});document.querySelectorAll('.jobRegion').forEach(x=>x.onclick=e=>{if(e.target.matches('input'))return;selectPrepRegion(x.dataset.ridx)});document.querySelectorAll('.jobImageTab').forEach(x=>x.onclick=()=>{S.jobPrepImage=Number(x.dataset.i);S.jobPrepRegion=null;renderPrepImage();const firstReg=S.jobPrep.items[S.jobPrepImage]?.regions[0];if(firstReg)selectPrepRegion(firstReg._idx)});
  $('#jobQueueAll').onclick=()=>{document.querySelectorAll('.jobRegionCheck').forEach(c=>{c.checked=true;c.closest('.jobRegion').classList.remove('off')});renderPrepImage();updatePrepCount()};$('#jobClearAll').onclick=()=>{document.querySelectorAll('.jobRegionCheck').forEach(c=>{c.checked=false;c.closest('.jobRegion').classList.add('off')});renderPrepImage();updatePrepCount()};
  $('#jobPrep').hidden=false;renderPrepImage();const firstReg=r.items[0]?.regions[0];if(firstReg)selectPrepRegion(firstReg._idx);updatePrepCount();
 }catch(e){alert(e.message)}
}
$('#jobExecute').onclick=async()=>{
 const p=S.jobPrep;if(!p)return;const regions=[];for(const item of p.items)for(const reg of item.regions){const c=document.querySelector(`.jobRegionCheck[data-ridx="${reg._idx}"]`);regions.push({path:item.path,geometry:reg.geometry,queued:!!c?.checked})}
 try{const r=await post('/api/environments/dispatch',{environment_id:p.environment_id,workflow:p.workflow,paths:p.paths,regions,positive:$('#jobPositive').value,negative:$('#jobNegative').value});$('#status').textContent=`External job ${r.id} queued`;closeJobPrep();refreshJobs()}catch(e){alert(e.message)}
};

// --- I.2r: launch discrepancies are notices, never blocking dialogs or implicit purges. ---
let launchOfferShown=false,staleJobReportShown=false,launchVerifyTimer=0,launchVerifyBusy=false,launchVerifyAttempts=0,launchVerifyArmed=false;
let liteIntroductionShown=false;
function showLiteIntroduction(){
 if(S.edition!=='lite'||liteIntroductionShown)return;
 liteIntroductionShown=true;
 try{
  if(localStorage.getItem('n8vision.liteIntroductionSeen')==='1')return;
  localStorage.setItem('n8vision.liteIntroductionSeen','1');
 }catch(_){return} // Browsing stays quiet if this browser cannot remember dismissal.
 startupNotice('liteIntroduction','Lite is ready','Browsing, archive maintenance and filesystem tools are available. SAM and inference are disabled in Lite. If those tools are already installed, use the Blurred or Full launcher. Otherwise run install.cmd to add them to the same environment.');
}
function startupNotice(id,heading,body){
 let tray=document.getElementById('startupNoticeTray');
 if(!tray){
  tray=document.createElement('div');tray.id='startupNoticeTray';
  Object.assign(tray.style,{position:'fixed',right:'16px',bottom:'16px',zIndex:'9000',width:'min(440px, calc(100vw - 32px))',maxHeight:'55vh',overflowY:'auto',pointerEvents:'none'});
  document.body.appendChild(tray);
 }
 let card=document.getElementById(id);
 if(!card){
  card=document.createElement('aside');card.id=id;card.setAttribute('role','status');
  Object.assign(card.style,{background:'var(--panel, #25252c)',color:'var(--text, #f0f0f0)',border:'1px solid #b78b42',borderRadius:'9px',boxShadow:'0 4px 22px #0008',padding:'12px',marginTop:'8px',pointerEvents:'auto'});
  const title=document.createElement('strong'),close=document.createElement('button'),detail=document.createElement('div');
  title.className='startupNoticeTitle';detail.className='startupNoticeDetail';
  Object.assign(close.style,{float:'right',marginLeft:'12px'});close.type='button';close.textContent='Dismiss';close.onclick=()=>card.remove();
  Object.assign(detail.style,{whiteSpace:'pre-wrap',overflowWrap:'anywhere',marginTop:'8px',fontSize:'.9em'});
  card.append(title,close,detail);tray.appendChild(card);
 }
 card.querySelector('.startupNoticeTitle').textContent=heading;
 card.querySelector('.startupNoticeDetail').textContent=body;
}
function scheduleLaunchVerification(ms){clearTimeout(launchVerifyTimer);launchVerifyTimer=setTimeout(()=>{launchVerifyTimer=0;checkLaunchVerification()},ms)}
async function checkLaunchVerification(){
 if(launchVerifyBusy)return;
 launchVerifyBusy=true;
 try{
  const r=await j('/api/launch-verification');
  launchVerifyAttempts++;
  if(!r.ready){if(r.deferred){launchVerifyArmed=false;return}launchVerifyArmed=true;scheduleLaunchVerification(5000);return}
  if(r.error){startupNotice('launchVerifyError','Archive verification warning',String(r.error)+'\nBrowsing remains available; no analysis was discarded.');return}
  if(r.abandoned_jobs?.count && !staleJobReportShown){
   staleJobReportShown=true;
   const js=(r.abandoned_jobs.jobs||[]).slice(0,6).map(x=>`${x.kind} · ${x.state} · ${x.done||0}/${x.total||0}`).join('\n');
   startupNotice('launchStaleJobs',`${r.abandoned_jobs.count} unfinished job(s) from the previous session`,`${js}${r.abandoned_jobs.count>6?'\n…':''}\nThe stale queue was purged before launch. Completed archive results were preserved.`);
  }
  if(r.missing && !launchOfferShown){
   launchOfferShown=true;
   const leaders=(r.groups||[]).slice(0,6).map(x=>`${x.missing} · ${x.folder}`).join('\n');
   startupNotice('launchMissingFiles',`${r.missing} previously indexed file(s) missing`,`${r.missing} of ${r.known} known files could not be found.\n${leaders}${(r.groups||[]).length>6?'\n…':''}\n\nThe catalog and observations are preserved. Discovery and browsing continue. Review orphaned files in maintenance when convenient.`);
   $('#status').textContent=`Archive verification: ${r.missing} missing file(s); catalog retained.`;
  }
 }catch(e){launchVerifyAttempts++;if(launchVerifyArmed)scheduleLaunchVerification(10000)}
 finally{launchVerifyBusy=false}
}
async function cleanShutdown(){
 if(!confirm('Cleanly shut down N8Vision?\n\nNew processing will stop, this working session will be verified and sealed, master will be updated, then the server will exit.'))return;
 const a=$('#cleanShutdownBtn'),b=$('#orderingShutdownBtn');if(a)a.disabled=true;if(b)b.disabled=true;$('#status').textContent='Putting away the loupe… sealing session.';
 try{
  await post('/api/clean-shutdown',{discard_invalids:false});
  $('#status').textContent='Session sealed. Closing viewer before console.';
  let acked=false;
  const closeAck=()=>{if(acked)return;acked=true;try{navigator.sendBeacon('/api/clean-shutdown/browser-closing',new Blob([], {type:'application/octet-stream'}))}catch(e){fetch('/api/clean-shutdown/browser-closing',{method:'POST',keepalive:true}).catch(()=>{})}};
  window.addEventListener('pagehide',closeAck,{once:true});
  window.addEventListener('beforeunload',closeAck,{once:true});
  window.close();
  setTimeout(()=>{if(document.visibilityState!=='hidden'){document.body.innerHTML='<main class="shutdownDone"><h1>N8Vision shut down successfully.</h1><p>This browser refused automatic tab close. You can close it now.</p></main>';closeAck()}},350);
 }
 catch(e){const a=$('#cleanShutdownBtn'),b=$('#orderingShutdownBtn');if(a)a.disabled=false;if(b)b.disabled=false;alert(e.message)}
}
const shutdownA=$('#cleanShutdownBtn'),shutdownB=$('#orderingShutdownBtn');if(shutdownA)shutdownA.onclick=cleanShutdown;if(shutdownB)shutdownB.onclick=cleanShutdown;

function pathDirectlyInRoot(path,root){const p=String(path||'').replace(/\//g,'\\'),r=String(root||'').replace(/\//g,'\\').replace(/\\+$/,'');if(!p.toLowerCase().startsWith(r.toLowerCase()+'\\'))return false;return !p.slice(r.length+1).includes('\\')}
function pathInRoot(path,root,recursive){const p=canonPath(path),r=canonPath(root);return recursive?(p===r||p.startsWith(r+'\\')):pathDirectlyInRoot(path,root)}
function currentViewRoots(){const selected=[...S.scopeSelections];return selected.length?selected:[S.scopeRoot].filter(Boolean)}
function batchIntersectsCurrentView(batch){const roots=currentViewRoots();if(!roots.length)return false;return [...(batch.sources||[]),...(batch.targets||[])].some(p=>roots.some(r=>pathInRoot(p,r,!!S.scopeRecursive)))}
async function refreshCurrentViewData(){const roots=currentViewRoots();if(!roots.length)return;const home=tempHomePath(),recursive=!!S.scopeRecursive,r=await post('/api/view-refresh',{roots,recursive}),fresh=r.files||[],under=p=>roots.some(root=>pathInRoot(p,root,recursive));S.files=S.files.filter(f=>!under(f.path));const have=new Set(S.files.map(f=>canonPath(f.path)));for(const f of fresh)if(!have.has(canonPath(f.path))){S.files.push(f);have.add(canonPath(f.path))}S.virtualGrid.rowReady=new Map();S.virtualGrid.prepGeneration++;invalidateRingLayout();renderScopeFolders();render();requestAnimationFrame(()=>{pinTempHome(home);paintRing()})}
function gridRefreshNotice(){let d=$('#gridRefreshNotice');if(!d){d=document.createElement('div');d.id='gridRefreshNotice';d.className='gridRefreshNotice';document.body.appendChild(d)}d.textContent='Hold for grid refresh — 2s';d.classList.add('show');return d}
async function automaticGridRefresh(){const d=gridRefreshNotice();await new Promise(r=>setTimeout(r,2000));d.classList.remove('show');await refreshCurrentViewData();$('#status').textContent=`Grid refreshed · ${visibleFiles().length.toLocaleString()} shown`}
const watchedComfyBatches=new Set();
async function watchComfyBatch(id){if(!id||watchedComfyBatches.has(id))return;watchedComfyBatches.add(id);try{for(;;){await new Promise(r=>setTimeout(r,1000));let b;try{b=await j(`/api/comfy/recovery-batch/${enc(id)}`)}catch(e){if(String(e.message).includes('404'))return;continue}if(!b.complete)continue;if(batchIntersectsCurrentView(b))await automaticGridRefresh();return}}finally{watchedComfyBatches.delete(id)}}

async function returnToOrigin(){
 if(pagedBrowse()&&mobilePager){S.mobileNavigationPosition=0;S.mobileNavigationDirty=false;const pager=mobilePager,snapshot=await pager.focus(0);if(snapshot&&pager===mobilePager)await applyMobileSnapshot(snapshot,snapshot.files[0]?.path,pager);return;}
 const v=S.virtualGrid;if(!v.rows.length)return;
 gridActivity('return-to-origin');v.selectionRing=null;v.cursor=0;v.scoutDir=0;v.scoutExtra=0;
 prepareNeighborhood();await prepareRow(0);paintRing();
 $('#status').textContent='Returned to origin';
}
const originButton=$('#returnToOriginBtn');if(originButton)originButton.onclick=returnToOrigin;
let redrawGeneration=0;
async function reconcileRedrawAssets(generation,files,root){
 const valid=()=>generation===redrawGeneration&&S.files===files&&S.scopeRoot===root;
 const wanted=new Set();
 for(let i=0;i<files.length;i+=1000){
  if(!valid())return;
  for(const f of files.slice(i,i+1000))if(!f._n8Tombstone&&!f._n8ForwardTo)wanted.add(thumbUrl(f));
  await new Promise(resolve=>setTimeout(resolve,0));
 }
 let count=0;
 for(const [url,entry] of thumbAssets){
  if(!valid())return;
  if(!wanted.has(url)&&entry.state!=='loading'){
   thumbAssets.delete(url);if(entry.objectUrl)URL.revokeObjectURL(entry.objectUrl);
  }
  if(++count%100===0)await new Promise(resolve=>setTimeout(resolve,0));
 }
 if(valid())renderScopeFolders();
}
async function redrawGrid(){
 const a=$('#redrawGridBtn'),b=$('#orderingRedrawGridBtn'),home=tempHomePath(),generation=++redrawGeneration;
 if(a)a.disabled=true;if(b)b.disabled=true;
 try{
  // Compact only on explicit redraw; preserve valid prefabs and decoded thumbnails.
  S.files=S.files.filter(f=>!f._n8Tombstone);
  const files=S.files,root=S.scopeRoot;
  invalidateRingLayout();render();pinTempHome(home);paintRing();
  const v=S.virtualGrid,pool=ringPool(virtualGridLayout(v.files),v.cursor),ready=[];
  for(let i=0;i<pool.count;i++)ready.push(prepareRow(pool.first+i));
  await Promise.all(ready);
  if(generation!==redrawGeneration||S.files!==files||S.scopeRoot!==root)return;
  paintRing();
  $('#status').textContent=`Grid redrawn · ${v.files.length.toLocaleString()} shown`;
  // Give mounted cards a paint before any archive-wide browser bookkeeping.
  requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(()=>{
   reconcileRedrawAssets(generation,files,root).catch(e=>console.warn('[N8Vision] Redraw cleanup:',e));
  },0)));
 }catch(e){alert(e.message)}finally{if(a)a.disabled=false;if(b)b.disabled=false}
}
const redrawA=$('#redrawGridBtn'),redrawB=$('#orderingRedrawGridBtn');if(redrawA)redrawA.onclick=redrawGrid;if(redrawB)redrawB.onclick=redrawGrid;

async function restartServer(){
 if(!confirm('Restart the N8Vision server?\n\nThe current grid will stay pinned in this browser while the backend restarts.'))return;
 const buttons=[$('#restartServerBtn'),$('#orderingRestartServerBtn'),$('#cleanShutdownBtn'),$('#orderingShutdownBtn')].filter(Boolean);buttons.forEach(x=>x.disabled=true);
 const tempHome=tempHomePath();
 $('#status').textContent='Restarting N8Vision server… current grid pinned.';
 try{await post('/api/restart-server',{});}catch(e){}
 let sawDown=false;
 for(let i=0;i<120;i++){
  await new Promise(r=>setTimeout(r,500));
  try{await j('/api/health');if(sawDown||i>2){pinTempHome(tempHome);paintRing();buttons.forEach(x=>x.disabled=false);$('#status').textContent=`Server reconnected · ${visibleFiles().length.toLocaleString()} shown · view preserved`;return}}catch(e){sawDown=true}
 }
 buttons.forEach(x=>x.disabled=false);$('#status').textContent='Server restart timed out; current grid preserved.';
}
const restartA=$('#restartServerBtn'),restartB=$('#orderingRestartServerBtn');if(restartA)restartA.onclick=restartServer;if(restartB)restartB.onclick=restartServer;
checkLaunchVerification();

// --- 0.9.5 orphan reconciliation controls ---
async function refreshOrphans(){
 try{const r=await j('/api/orphans');$('#orphanStatus').textContent=`${r.files} orphaned file${r.files===1?'':'s'} · ${r.observations} observations · ${r.embeddings} embeddings`;$('#purgeOrphansBtn').disabled=!r.files}
 catch(e){$('#orphanStatus').textContent='Orphan status unavailable'}
}
$('#purgeOrphansBtn').onclick=async()=>{
 const r=await j('/api/orphans');
 if(!r.files)return refreshOrphans();
 if(!confirm(`Permanently purge analysis for ${r.files} orphaned file${r.files===1?'':'s'}?\n\nThis deletes ${r.observations} observations and ${r.embeddings} embeddings whose image files are currently missing. It does not delete any images.`))return;
 try{const x=await post('/api/orphans/purge',{});$('#status').textContent=`Purged orphaned analysis for ${x.purged_files} file${x.purged_files===1?'':'s'}.`;await refreshOrphans()}catch(e){alert(e.message)}
};
refreshOrphans();

// --- P.56 Refinement bridge: remembered graph grammar + per-run variadic LoRA stack ---
S.refineRecipe=null;S.refineShelf=null;S.refineMode='run';S.refineMetadata=[];
function toolIO(t){
 const ins=t?.inputs||{},all={...(ins.required||{}),...(ins.optional||{})};
 const it=Object.entries(all).map(([name,spec])=>({name,type:Array.isArray(spec)?spec[0]:spec}));
 return {ins:it,outs:(t?.outputs||[]).map((x,i)=>({name:(t.output_names||[])[i]||String(x),type:String(x)}))};
}
function hasIn(t,type){return toolIO(t).ins.some(x=>String(x.type)===type)}function hasOut(t,type){return toolIO(t).outs.some(x=>x.type===type)}
function candidates(role,tools){const preferred={source:['LoadImage'],checkpoint:['CheckpointLoaderSimple','CheckpointLoader'],lora:['LoraLoader'],encode:['VAEEncode'],text:['CLIPTextEncode'],sampler:['KSampler','KSamplerAdvanced'],decode:['VAEDecode'],output:['SaveImage']};const found=tools.filter(t=>{
  if(role==='source')return hasOut(t,'IMAGE');
  if(role==='checkpoint')return hasOut(t,'MODEL')&&hasOut(t,'CLIP')&&hasOut(t,'VAE');
  if(role==='lora')return hasIn(t,'MODEL')&&hasIn(t,'CLIP')&&hasOut(t,'MODEL')&&hasOut(t,'CLIP');
  if(role==='encode')return hasIn(t,'IMAGE')&&hasIn(t,'VAE')&&hasOut(t,'LATENT');
  if(role==='text')return hasIn(t,'CLIP')&&hasOut(t,'CONDITIONING');
  if(role==='sampler')return hasIn(t,'MODEL')&&hasIn(t,'CONDITIONING')&&hasIn(t,'LATENT')&&hasOut(t,'LATENT');
  if(role==='decode')return hasIn(t,'LATENT')&&hasIn(t,'VAE')&&hasOut(t,'IMAGE');
  if(role==='output')return hasIn(t,'IMAGE')&&!!t.output_node;return false
 });return found.sort((a,b)=>{const pa=preferred[role]?.indexOf(a.type)??-1,pb=preferred[role]?.indexOf(b.type)??-1;return (pa<0?999:pa)-(pb<0?999:pb)||String(a.display_name||a.type).localeCompare(String(b.display_name||b.type))})}
const refineRoles=[['source','Image source'],['checkpoint','Checkpoint / foundation'],['lora','LoRA loader (repeatable 0..N)'],['encode','VAE encode'],['text','Text conditioning'],['sampler','Sampler'],['decode','VAE decode'],['output','Image output']];
function schemaChoices(tool,needle){
 const all={...(tool?.inputs?.required||{}),...(tool?.inputs?.optional||{})};for(const [name,spec] of Object.entries(all)){if(!name.toLowerCase().includes(needle))continue;const typ=Array.isArray(spec)?spec[0]:null;if(Array.isArray(typ))return typ.map(String)}return []
}
async function loadRefineRecipe(){if(!S.capabilities.processing)return;try{const r=await j('/api/refinement/recipe');S.refineRecipe=r.recipe||{};$('#refinerStatus').textContent=S.refineRecipe?.roles?`Recipe ready · ${S.refineRecipe.name||'Refine SDXL'} · LoRA chain 0..N`:'No refinement recipe configured.'}catch(e){$('#refinerStatus').textContent='Refinement recipe unavailable.'}}
async function deleteRefineRecipe(){const name=S.refineRecipe?.name||'Refine SDXL';if(!S.refineRecipe?.roles)return;if(!confirm(`Delete refinement graph \"${name}\"?\n\nThis removes the remembered graph. It does not delete Comfy workflows, models, or images.`))return;try{await j('/api/refinement/recipe',{method:'DELETE'});S.refineRecipe={};await loadRefineRecipe();$('#status').textContent=`Deleted graph · ${name}`;}catch(e){alert(e.message)}}
async function refineEnvironments(){const r=await j('/api/environments');return (r.environments||[]).filter(x=>x.kind==='comfy'&&x.online)}
async function inspectShelf(env){const r=await j('/api/comfy/tool-shelf/'+enc(env));S.refineShelf=r;return r}
function renderRolePickers(){const tools=S.refineShelf?.tools||[],old=S.refineRecipe?.roles||{};$('#refineRoles').innerHTML=refineRoles.map(([key,label])=>{const cs=candidates(key,tools);return `<label class="refineRole"><span>${esc(label)}</span><select data-role="${key}">${cs.map(t=>`<option value="${esc(t.type)}" ${old[key]?.type===t.type?'selected':''}>${esc(t.display_name||t.type)} · ${esc(t.category||'uncategorized')}</option>`).join('')}</select><small>${cs.length}</small></label>`}).join('')||'<div class="tiny">No compatible tools reported.</div>'}
async function openGraphWizard(){
 S.refineMode='graph';$('#refineWizardTitle').textContent='Set Up Refine SDXL';$('#refineGraphStage').hidden=false;$('#refineRunStage').hidden=true;$('#refineWizardNext').textContent='Save Graph';$('#refineWizard').hidden=false;
 try{const envs=await refineEnvironments();if(!envs.length)throw new Error('No online Comfy environment. Start Comfy with Comfy-Finder P.06.');$('#refineEnvironment').innerHTML=envs.map(x=>`<option value="${esc(x.id)}">${esc(x.name)} · ${esc(x.bridge||'bridge')}</option>`).join('');const preferred=S.refineRecipe?.environment_id;if(preferred&&envs.some(x=>x.id===preferred))$('#refineEnvironment').value=preferred;await inspectShelf($('#refineEnvironment').value);renderRolePickers();$('#refineWizardSub').textContent=`${S.refineShelf.tools.length} installed tools inspected · nothing will be installed`;$('#refineWizardFoot').textContent='Topology is fixed except the declared repeatable LoRA chain.'}catch(e){$('#refineWizardSub').textContent=e.message;$('#refineRoles').innerHTML=''}
}
$('#refineEnvironment').onchange=async()=>{try{await inspectShelf($('#refineEnvironment').value);renderRolePickers()}catch(e){alert(e.message)}};
function historicalChoiceMatch(opts,name){if(!name)return '';const norm=x=>String(x||'').replaceAll('\\','/').toLowerCase();const n=norm(name),nb=n.split('/').pop();return opts.find(x=>norm(x)===n)||opts.find(x=>norm(x).split('/').pop()===nb)||opts.find(x=>norm(x).includes(n)||n.includes(norm(x)))||''}
function refineRunValidity(){
 const missing=[];const model=$('#refineModel');if(model?.classList.contains('historicalMissing'))missing.push(`checkpoint: ${model.value}`);
 document.querySelectorAll('.refineLoraName.historicalMissing').forEach(x=>missing.push(`LoRA: ${x.value}`));
 const runMode=S.refineMode==='run',btn=$('#refineWizardNext');if(runMode&&btn)btn.disabled=missing.length>0;
 if(runMode){const tn=(typeof refineryTranslationNeeds==='function'?refineryTranslationNeeds():[]);if(btn)btn.disabled=missing.length>0||tn.length>0;$('#refineWizardFoot').textContent=missing.length?`Cannot execute · unresolved ${missing.join(' · ')}`:tn.length?`Translation required before Execute · ${tn.length} prompt field${tn.length===1?'':'s'}`:'Ready · graph dependencies and prompt dialect resolve.'}
 return missing
}
function setHistoricalState(sel,missing){sel.classList.toggle('historicalMissing',!!missing);sel.title=missing?'Recorded in image metadata; not currently resolved in this Comfy environment.':'';sel.onchange=()=>{const valid=[...sel.options].some(o=>o.value===sel.value&&!o.dataset.historical);sel.classList.toggle('historicalMissing',!valid&&!!sel.value);sel.title=sel.classList.contains('historicalMissing')?'Recorded in image metadata; not currently resolved in this Comfy environment.':'';refineRunValidity();if(sel.id==='refineModel'){S.refineTranslations={};updateRefineDialectUI();}}}
function addLoraRow(name='',model=1,clip=1){const opts=schemaChoices((S.refineShelf?.tools||[]).find(t=>t.type===S.refineRecipe?.roles?.lora?.type),'lora');const match=historicalChoiceMatch(opts,name),missing=!!name&&!match;const historical=missing?`<option value="${esc(name)}" data-historical="1" selected>${esc(name)}</option>`:'';const row=document.createElement('div');row.className='refineLoraRow';row.innerHTML=`<select class="refineLoraName"><option value="">Choose LoRA…</option>${historical}${opts.map(x=>`<option ${x===match?'selected':''}>${esc(x)}</option>`).join('')}</select><span><input class="refineLoraModel" type="number" step=".05" value="${esc(model)}" title="Model strength"><input class="refineLoraClip" type="number" step=".05" value="${esc(clip)}" title="CLIP strength"></span><button type="button">×</button>`;const sel=row.querySelector('.refineLoraName');setHistoricalState(sel,missing);row.querySelector('button').onclick=()=>{row.remove();refineRunValidity()};$('#refineLoras').appendChild(row);refineRunValidity()}
async function openRunWizard(){
 if(!S.refineRecipe?.roles)return openGraphWizard();const paths=S.selected.size?[...S.selected]:visibleFiles().map(x=>x.path);if(!paths.length)return alert('Select images, or leave selection empty to refine the shown set.');S.refineMode='run';S.refinePaths=paths;S.refineTranslations={};$('#refineWizardTitle').textContent='Refine SDXL';$('#refineGraphStage').hidden=true;$('#refineRunStage').hidden=false;$('#refineWizardNext').textContent='Refine SDXL';$('#refineWizard').hidden=false;$('#refinePromptAdapter').hidden=true;
 try{await inspectShelf(S.refineRecipe.environment_id);try{S.checkpointLibrary=await j('/api/comfy/checkpoint-library')}catch(_e){}const mr=await post('/api/refinement/metadata',{paths});S.refineMetadata=mr.items||[];const m=S.refineMetadata[0]?.metadata||{};const cp=(S.refineShelf.tools||[]).find(t=>t.type===S.refineRecipe.roles.checkpoint.type);const models=[...new Set([...schemaChoices(cp,'ckpt'),...schemaChoices(cp,'model')])];const modelMatch=historicalChoiceMatch(models,m.model),modelMissing=!!m.model&&!modelMatch;$('#refineModel').innerHTML=(modelMissing?`<option value="${esc(m.model)}" data-historical="1" selected>${esc(m.model)}</option>`:'')+models.map(x=>`<option ${x===modelMatch?'selected':''}>${esc(x)}</option>`).join('');setHistoricalState($('#refineModel'),modelMissing);$('#refinePositive').value=m.positive||'';$('#refineNegative').value=m.negative||'';$('#refineSeed').value=m.seed??0;$('#refineSourceSteps').value=Math.max(0,Number(m.steps??0));$('#refineSteps').value=10;$('#refineCfg').value=m.cfg??8;const st=(S.refineShelf.tools||[]).find(t=>t.type===S.refineRecipe.roles.sampler.type);const samplers=schemaChoices(st,'sampler'),schedulers=schemaChoices(st,'scheduler');$('#refineSampler').innerHTML=samplers.map(x=>`<option ${m.sampler===x?'selected':''}>${esc(x)}</option>`).join('');$('#refineScheduler').innerHTML=schedulers.map(x=>`<option ${m.scheduler===x?'selected':''}>${esc(x)}</option>`).join('');$('#refineLoras').innerHTML='';(m.loras||[]).forEach(x=>addLoraRow(x.name,x.weight||1,x.weight||1));$('#refineWizardSub').textContent=`${paths.length} image${paths.length===1?'':'s'} · ${S.refineRecipe.name||'Refine SDXL'}${paths.length>1?' · one setup, per-image recovered prompts':''}`;updateRefineDialectUI()}catch(e){alert(e.message)}
}
$('#refineAddLora').onclick=()=>addLoraRow();$('#createRefinerGraphBtn').onclick=openWorkshop;$('#regenerateBtn').onclick=openRunWizard;$('#refineWizardClose').onclick=()=>$('#refineWizard').hidden=true;$('#refineWizard .jobPrepBackdrop').onclick=()=>$('#refineWizard').hidden=true;
$('#refineWizardNext').onclick=async()=>{
 if(S.refineMode==='graph'){
  const roles={};document.querySelectorAll('#refineRoles select[data-role]').forEach(x=>{const t=(S.refineShelf.tools||[]).find(q=>q.type===x.value);if(t)roles[x.dataset.role]={type:t.type,display_name:t.display_name,inputs:t.inputs,outputs:t.outputs,output_names:t.output_names}});if(Object.keys(roles).length!==refineRoles.length)return alert('Every graph role needs an installed tool.');
  const recipe={version:1,name:'Refine SDXL',environment_id:$('#refineEnvironment').value,roles,grammar:{fixed:['source','checkpoint','encode','text_positive','text_negative','sampler','decode','output'],repeatable:{lora:{min:0,max:null,between:'checkpoint→conditioning/model'}}}};try{const r=await j('/api/refinement/recipe',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipe})});S.refineRecipe=r.recipe;$('#refineWizard').hidden=true;loadRefineRecipe();$('#status').textContent='Refine SDXL graph saved. The button now points to this graph.'}catch(e){alert(e.message)};return
 }
 const unresolved=refineRunValidity();if(unresolved.length)return alert('Resolve missing checkpoint / LoRA dependencies before sending this graph to Comfy.');
 const needsTranslation=refineryNeedsTranslation();if(needsTranslation)return alert('Translate the incompatible prompt fields before Execute. Execute never launches the translator.');
 const loras=[...document.querySelectorAll('.refineLoraRow')].map(r=>({name:r.querySelector('.refineLoraName').value,model_strength:Number(r.querySelector('.refineLoraModel').value),clip_strength:Number(r.querySelector('.refineLoraClip').value)})).filter(x=>x.name);
 const run={environment_id:S.refineRecipe.environment_id,recipe:S.refineRecipe,paths:S.refinePaths,model:$('#refineModel').value,positive:$('#refinePositive').value,negative:$('#refineNegative').value,seed:Number($('#refineSeed').value||0),source_steps:Number($('#refineSourceSteps').value||0),refinement_steps:Number($('#refineSteps').value||10),cfg:Number($('#refineCfg').value||8),sampler:$('#refineSampler').value,scheduler:$('#refineScheduler').value,loras,destination:$('#refineDestination').value,prompt_mode:'per_image_metadata',translated_prompts:S.refineTranslations||{}};
 try{const r=await post('/api/refinement/dispatch',run);$('#refineWizard').hidden=true;$('#status').textContent=`Refinement ${r.id} queued · ${run.paths.length} image${run.paths.length===1?'':'s'} · one setup · per-image prompts · ${run.destination}`;refreshJobs();if(run.destination!=='comfy')watchComfyBatch(r.id)}catch(e){alert(e.message)}
};
$('#refineTranslateBtn').onclick=pretranslateRefinery;for(const id of ['refinePositive','refineNegative']){const el=$('#'+id);if(el)el.addEventListener('input',()=>{S.refineTranslations={};updateRefineDialectUI()})}
loadRefineRecipe();


// P.65 — Thunderclese the Flabulous: Graph Workshop.
// The Workshop composes reusable I2I functions. Raw generation remains Comfy's job.
const WORKSHOP_TEMPLATES={
 refine:{name:'Refine / Restore',desc:'Keep the picture. Clean it up, restore it, or continue cooking it.',engines:['SD / SDXL diffusion','FLUX / edit model','Custom'],roles:['encode','conditioning','sampler','decode'],controls:['Prompt','Negative prompt','Strength / refinement','Steps','CFG','Seed']},
 repair:{name:'Repair / Inpaint',desc:'Change masked regions while preserving the rest.',engines:['Generic inpaint','Dedicated inpaint checkpoint','FLUX Fill','Custom'],roles:['mask','mask_process','encode_inpaint','conditioning','sampler','decode'],controls:['Mask source','Prompt','Negative prompt','Mask grow / feather','Steps','CFG','Seed']},
 extend:{name:'Extend / Outpaint',desc:'Make the canvas larger and synthesize what belongs outside it.',engines:['Generic inpaint','FLUX Fill','Custom'],roles:['pad','mask_process','encode_inpaint','conditioning','sampler','decode'],controls:['Frame / extension','Prompt','Negative prompt','Seam blending','Steps','CFG','Seed']},
 upscale:{name:'Upscale / Enhance',desc:'Increase resolution, optionally adding a diffusion detail pass.',engines:['Pixel upscaler','Diffusion detail pass','Tiled diffusion','Custom'],roles:['upscale','encode_optional','conditioning_optional','sampler_optional','decode_optional'],controls:['Scale / target size','Upscale model','Detail strength','Tile size','Steps']},
 background:{name:'Background',desc:'Remove, replace, generate, extend, or composite a background.',engines:['Segmentation + composite','Generic diffusion','FLUX Fill / edit','Custom'],roles:['segment','mask_process','composite_or_condition','sampler_optional','decode_optional'],controls:['Mode','Background source','Prompt','Mask grow / feather','Blend']},
 relight:{name:'Relight / Regrade',desc:'Change illumination or grade while retaining the scene.',engines:['IC-Light foreground','IC-Light foreground + background','Deterministic relight','Custom'],roles:['mask_optional','relight','detail_transfer_optional'],controls:['Light direction / source','Background source','Strength','Detail transfer']},
 transform:{name:'Transform / Restyle',desc:'Deliberately reinterpret the source while retaining its identity or composition.',engines:['SD / SDXL img2img','FLUX / instruction edit','Custom'],roles:['encode','conditioning','sampler','decode'],controls:['Prompt','Negative prompt','Transformation strength','Steps','CFG','Seed']},
 recompose:{name:'Recompose / Repose',desc:'Change pose, structure, framing, or composition under explicit control.',engines:['ControlNet / structural control','Reference-conditioned edit','Custom'],roles:['preprocess','control','encode','conditioning','sampler','decode'],controls:['Control source','Control strength','Prompt','Steps','CFG','Seed']}
};
const WORKSHOP_ROLE_HINTS={
 pad:['pad','outpaint'],mask:['mask'],mask_process:['mask','grow','feather','blur'],encode:['vae encode','vaeencode'],encode_inpaint:['inpaint','vae encode'],conditioning:['clip text','conditioning','prompt'],sampler:['ksampler','sampler'],decode:['vae decode','vaedecode'],upscale:['upscale','super resolution','esrgan'],encode_optional:['vae encode','vaeencode'],conditioning_optional:['conditioning','clip text'],sampler_optional:['ksampler','sampler'],decode_optional:['vae decode','vaedecode'],segment:['segment','rembg','background','sam'],composite_or_condition:['composite','conditioning'],mask_optional:['mask'],relight:['relight','ic-light','ic light'],detail_transfer_optional:['detail transfer','detailtransfer'],preprocess:['preprocessor','depth','canny','pose'],control:['controlnet','control'],decode_optional:['vae decode','vaedecode']
};
S.workshop={step:0,template:null,engine:null,environment_id:null,target:null,roles:{},controls:{},name:''};S.workshopFunctions=[];
function workshopTarget(){if(S.viewer?.path)return S.viewer.path;if(S.selected?.size)return [...S.selected][0];return visibleFiles()[0]?.path||null}
function workshopToolCandidates(role){const tools=S.refineShelf?.tools||[],h=WORKSHOP_ROLE_HINTS[role]||[role.replaceAll('_',' ')];const scored=tools.map(t=>{const q=`${t.type} ${t.display_name||''} ${t.category||''}`.toLowerCase();let score=0;h.forEach((x,i)=>{if(q.includes(x))score+=20-i});return {t,score}}).filter(x=>x.score>0).sort((a,b)=>b.score-a.score).map(x=>x.t);return scored.slice(0,30)}
function workshopChoiceHtml(key,t){return `<button type="button" class="workshopChoice ${S.workshop.template===key?'selected':''}" data-template="${key}"><b>${esc(t.name)}</b><small>${esc(t.desc)}</small></button>`}
async function openWorkshop(){
 const target=workshopTarget();S.workshop={step:0,template:null,engine:null,environment_id:null,target,roles:{},controls:{},name:''};$('#workshopTargetName').textContent=target||'No image pinned — template construction is still allowed';$('#workshopWizard').hidden=false;renderWorkshop()
}
async function renderWorkshop(){const w=S.workshop,b=$('#workshopBody');$('#workshopBack').hidden=w.step===0;$('#workshopNext').textContent=w.step===3?'Bind Spell':'Next';
 if(w.step===0){$('#workshopSub').textContent='Choose the intended change, not the plumbing.';$('#workshopFoot').textContent='Load_Image and Save_Image are givens. Thunderclese concerns himself with the middle.';b.innerHTML=`<h3>What shall I do to this picture?</h3><div class="workshopChoices">${Object.entries(WORKSHOP_TEMPLATES).map(([k,t])=>workshopChoiceHtml(k,t)).join('')}</div>`;b.querySelectorAll('[data-template]').forEach(x=>x.onclick=()=>{w.template=x.dataset.template;renderWorkshop()});return}
 const t=WORKSHOP_TEMPLATES[w.template];if(!t){w.step=0;return renderWorkshop()}
 if(w.step===1){$('#workshopSub').textContent=t.name;$('#workshopFoot').textContent='The engine changes the plumbing; the human operation stays the same.';let envs=[];try{envs=await refineEnvironments()}catch(e){};b.innerHTML=`<h3>How shall I accomplish this sorcery?</h3><label>Comfy environment<select id="workshopEnvironment">${envs.map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('')}</select></label><div class="workshopChoices">${t.engines.map(x=>`<button type="button" class="workshopChoice ${w.engine===x?'selected':''}" data-engine="${esc(x)}"><b>${esc(x)}</b></button>`).join('')}</div>`;if(envs.length&&!w.environment_id)w.environment_id=envs[0].id;const es=$('#workshopEnvironment');if(es){es.value=w.environment_id||'';es.onchange=()=>w.environment_id=es.value}b.querySelectorAll('[data-engine]').forEach(x=>x.onclick=()=>{w.engine=x.dataset.engine;renderWorkshop()});return}
 if(w.step===2){$('#workshopSub').textContent=`${t.name} · ${w.engine}`;$('#workshopFoot').textContent='Recommended matches come from the installed Tool Shelf. Optional stages may be left empty.';try{if(w.environment_id)await inspectShelf(w.environment_id)}catch(e){b.innerHTML=`<div class="muted">${esc(e.message)}</div>`;return}const roles=t.roles;const chain=['Load Image',...roles.map(x=>x.replaceAll('_optional','').replaceAll('_',' ')),'Save Image'];b.innerHTML=`<h3>Choose the nodes between Load_Image and Save_Image</h3><div class="workshopChain">${chain.map((x,i)=>`${i?'<span class="workshopArrow">→</span>':''}<span class="workshopNode">${esc(x)}</span>`).join('')}</div><div>${roles.map(role=>{const optional=role.endsWith('_optional'),cs=workshopToolCandidates(role);return `<label class="workshopRole"><span>${esc(role.replaceAll('_optional','').replaceAll('_',' '))}${optional?' <small>(optional)</small>':''}</span><select data-wrole="${role}"><option value="">${optional?'Skip stage':'Choose installed node…'}</option>${cs.map(q=>`<option value="${esc(q.type)}" ${(w.roles[role]?.type===q.type)?'selected':''}>${esc(q.display_name||q.type)} · ${esc(q.category||'uncategorized')}</option>`).join('')}</select></label>`}).join('')}</div>`;b.querySelectorAll('[data-wrole]').forEach(sel=>sel.onchange=()=>{const q=(S.refineShelf?.tools||[]).find(x=>x.type===sel.value);if(q)w.roles[sel.dataset.wrole]={type:q.type,display_name:q.display_name,inputs:q.inputs,outputs:q.outputs,output_names:q.output_names};else delete w.roles[sel.dataset.wrole]});return}
 if(w.step===3){$('#workshopSub').textContent='Decide what the mortal sees when this function runs.';$('#workshopFoot').textContent='Fixed values stay in the recipe. Recovered values prefer source metadata. Automatic values come from image/task context.';if(!w.name)w.name=`${t.name.split(' / ')[0]} ${w.engine==='Custom'?'Custom':w.engine.replace(' / ',' ')}`;b.innerHTML=`<h3>Which knobs shall the mortals be permitted to touch?</h3><label class="workshopName">Function name<input id="workshopName" value="${esc(w.name)}"></label>${t.controls.map(c=>`<label class="workshopControl"><span>${esc(c)}</span><select data-wcontrol="${esc(c)}"><option value="exposed">Exposed</option><option value="fixed">Fixed</option><option value="recovered">Recovered</option><option value="automatic">Automatic</option><option value="advanced">Advanced</option></select></label>`).join('')}<hr><div class="workshopSummary"><b>Operation</b><span>${esc(t.name)}</span><b>Engine</b><span>${esc(w.engine)}</span><b>Target</b><span>${esc(w.target||'none pinned')}</span><b>Chain</b><span>Load Image → ${esc(t.roles.join(' → ').replaceAll('_optional','?').replaceAll('_',' '))} → Save Image</span></div>`;$('#workshopName').oninput=e=>w.name=e.target.value;b.querySelectorAll('[data-wcontrol]').forEach(sel=>{const k=sel.dataset.wcontrol;sel.value=w.controls[k]||'exposed';sel.onchange=()=>w.controls[k]=sel.value});return}
}
$('#workshopBack').onclick=()=>{if(S.workshop.step>0){S.workshop.step--;renderWorkshop()}};
$('#workshopNext').onclick=async()=>{const w=S.workshop;if(w.step===0&&!w.template)return alert('Thunderclese requires an intention. Choose what happens to the image.');if(w.step===1&&(!w.engine||!w.environment_id))return alert('Choose an engine and an online Comfy environment.');if(w.step===2){const t=WORKSHOP_TEMPLATES[w.template],required=t.roles.filter(x=>!x.endsWith('_optional'));const miss=required.filter(x=>!w.roles[x]);if(miss.length)return alert('Choose installed nodes for: '+miss.join(', '))}if(w.step<3){w.step++;return renderWorkshop()}const name=($('#workshopName').value||'Unnamed Spell').trim();document.querySelectorAll('[data-wcontrol]').forEach(x=>w.controls[x.dataset.wcontrol]=x.value);const fn={version:1,name,operation:w.template,engine:w.engine,environment_id:w.environment_id,roles:w.roles,controls:w.controls,grammar:{source:'Load_Image',sink:'Save_Image',ordered:WORKSHOP_TEMPLATES[w.template].roles},created_at:new Date().toISOString()};try{const r=await j('/api/workshop/functions',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({function:fn})});S.workshopFunctions=r.functions||[];renderWorkshopFunctions();$('#workshopWizard').hidden=true;$('#status').textContent=`Thunderclese bound ${name} to the Workshop.`}catch(e){alert(e.message)}};
$('#workshopClose').onclick=()=>$('#workshopWizard').hidden=true;$('#workshopWizard .jobPrepBackdrop').onclick=()=>$('#workshopWizard').hidden=true;
async function loadWorkshopFunctions(){if(!S.capabilities.processing)return;try{const r=await j('/api/workshop/functions');S.workshopFunctions=r.functions||[];renderWorkshopFunctions()}catch(e){}}
function renderWorkshopFunctions(){const box=$('#workshopFunctions');if(!box)return;box.innerHTML=(S.workshopFunctions||[]).map(fn=>`<button type="button" data-workshop-fn="${esc(fn.id)}" title="${esc((WORKSHOP_TEMPLATES[fn.operation]?.name||fn.operation)+' · '+(fn.engine||''))}">${esc(fn.name)}</button>`).join('');box.querySelectorAll('[data-workshop-fn]').forEach(x=>{x.oncontextmenu=async e=>{e.preventDefault();const fn=S.workshopFunctions.find(q=>q.id===x.dataset.workshopFn);if(!fn)return;if(!confirm(`Delete refinement graph \"${fn.name}\"?\n\nThis removes the remembered graph and its button. It does not delete Comfy workflows, models, or images.`))return;try{const r=await j(`/api/workshop/functions/${enc(fn.id)}`,{method:'DELETE'});S.workshopFunctions=r.functions||[];renderWorkshopFunctions();$('#status').textContent=`Deleted graph · ${fn.name}`;}catch(err){alert(err.message)}};x.onclick=async()=>{const fn=S.workshopFunctions.find(q=>q.id===x.dataset.workshopFn);if(!fn)return;const paths=S.selected?.size?[...S.selected]:(workshopTarget()?[workshopTarget()]:[]);if(!paths.length)return alert('Choose or open an image first.');let lib={checkpoints:{}};try{lib=await j('/api/comfy/checkpoint-library')}catch(e){}const models=Object.keys(lib.checkpoints||{});if(!models.length)return alert('Checkpoint Library is empty. Run Interrogate Checkpoints in Settings first.');const meta=await post('/api/refinement/metadata',{paths:[paths[0]]});const recovered=meta.items?.[0]?.metadata||{};const guess=historicalChoiceMatch(models,recovered.model)||models[0];const model=prompt(`Run ${fn.name} on ${paths.length} image${paths.length===1?'':'s'}.\n\nTarget checkpoint:`,guess);if(model===null)return;if(!models.includes(model))return alert('Use an exact checkpoint name from the Checkpoint Library.');const positive=prompt('Prompt fallback (image metadata wins when present):',recovered.positive||'');if(positive===null)return;const negative=prompt('Negative prompt fallback:',recovered.negative||'');if(negative===null)return;const destination=prompt('Output: beside, replace, or comfy','beside');if(destination===null)return;if(!['beside','replace','comfy'].includes(destination))return alert('Output must be beside, replace, or comfy.');try{const r=await post('/api/workshop/dispatch',{function_id:fn.id,paths,model,positive,negative,destination});$('#status').textContent=`Workshop ${r.id} queued · ${fn.name} · ${paths.length} image${paths.length===1?'':'s'}`;refreshJobs();if(destination!=='comfy')watchComfyBatch(r.id)}catch(e){alert(e.message)}}})}
loadWorkshopFunctions();

// I.2e: same controls, drawer presentation at narrow viewports.
(()=>{const rail=document.getElementById('rail'),toggle=document.getElementById('railToggle'),close=document.getElementById('railClose'),backdrop=document.getElementById('railBackdrop');if(!rail||!toggle)return;const setOpen=setControlMenu;toggle.addEventListener('click',()=>setOpen(!rail.classList.contains('railOpen')));close?.addEventListener('click',()=>setOpen(false));backdrop?.addEventListener('click',()=>{setDrawer(false);setOpen(false)});document.addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false)});})();

// M1: keep the dragged viewport until the complete destination pool is ready.
function touchRingStep(offset,rowHeight){return -Math.sign(offset)*Math.round(Math.abs(offset)/Math.max(1,rowHeight))}
(()=>{
 const grid=document.getElementById('grid');if(!grid)return;
 let gesture=null,settleVersion=0;
 const enabled=()=>S.mobile||localStorage.getItem('n8visionControlPlane')==='touch';
 const reset=()=>{grid.querySelectorAll('.visualRow').forEach(r=>r.style.removeProperty('transform'));grid.classList.remove('touchDragging')};
 const cancel=()=>{settleVersion++;gesture=null;S.touchRingBusy=false;reset();scheduleRingPaint()};
 grid.addEventListener('touchstart',e=>{
  if(!enabled()||S.mobileWindowBusy||e.touches.length!==1||S.softCtrl||S.softShift||!S.virtualGrid.rows?.length)return;
  settleVersion++;reset();S.touchRingBusy=true;
  const t=e.touches[0];gesture={id:t.identifier,y:t.clientY,offset:0,moved:false};
 },{passive:true});
 grid.addEventListener('touchmove',e=>{
  if(!gesture||!enabled())return;if(e.touches.length!==1){cancel();return;}
  const t=[...e.changedTouches].find(x=>x.identifier===gesture.id);if(!t)return;
  const d=t.clientY-gesture.y;if(!gesture.moved&&Math.abs(d)<6)return;
  gesture.moved=true;gesture.offset=d;e.preventDefault();grid.classList.add('touchDragging');
  grid.querySelectorAll('.visualRow').forEach(r=>r.style.transform=`translateY(${d}px)`);
 },{passive:false});
 grid.addEventListener('touchend',async e=>{
  if(!gesture||![...e.changedTouches].some(t=>t.identifier===gesture.id))return;
  const {moved,offset}=gesture;gesture=null;
  const version=settleVersion,v=S.virtualGrid,n=v.rows?.length||0,step=S.mobile?mobileTouchStep(offset,v.cursor,v.rows):touchRingStep(offset,v.rowH||1);
  if(!moved){S.touchRingBusy=false;reset();if(S.mobileReflowPending)setTimeout(reflowMobileColumns,0);return;}
  S.suppressClickUntil=performance.now()+450;
  if(!n||!step){S.touchRingBusy=false;reset();scheduleRingPaint();return;}
  const target=pagedBrowse()?Math.max(0,Math.min(n-1,v.cursor+step)):mod(v.cursor+step,n),rows=v.rows,files=v.files,generation=v.prepGeneration;
  const layout=virtualGridLayout(files),pool=ringPool(layout,target);
  const required=Array.from({length:pool.count},(_,k)=>S.mobile?pool.first+k:mod(pool.first+k,n));
  for(const ri of required)v.prepDesired.add(rowKey(rows[ri]));
  gridActivity('touch-drag');
  try{
   const ready=await Promise.all(required.map(prepareRow));
   if(version!==settleVersion)return;
   if(!enabled()||S.viewer||generation!==v.prepGeneration||files!==v.files||virtualGridLayout(v.files).rows!==rows)return;
   if(!ready.every(Boolean)||!required.every(rowReady))throw new Error('Destination rows not ready');
   recordSelectionRingMove(v.cursor,step);v.cursor=target;reportRingMovement(Math.sign(step));
  }catch(err){console.warn('[N8Vision] touch row preparation',err)}
  finally{
   if(version===settleVersion){S.touchRingBusy=false;reset();if(S.mobileReflowPending)reflowMobileColumns();else paintRing();}
  }
 },{passive:true});
 grid.addEventListener('touchcancel',cancel,{passive:true});
})();

// Filesystem collision policy is host-persistent, not a browser preference.
(async()=>{const el=document.getElementById('collisionsAlwaysRename');if(!el)return;try{const r=await j('/api/files/collision-settings');el.checked=!!r.always_rename}catch(e){console.warn('Collision settings unavailable',e)}el.addEventListener('change',async()=>{try{await j('/api/files/collision-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({always_rename:el.checked})})}catch(e){el.checked=!el.checked;alert(e.message)}})})();

// Find only signals browsers opened through loopback on this host.
if(['127.0.0.1','localhost','[::1]'].includes(location.hostname)){
 let attentionSequence=null,attentionBusy=false;
 setInterval(async()=>{if(attentionBusy)return;attentionBusy=true;try{
  const state=await j('/api/instance/attention');
  if(attentionSequence!==null&&state.sequence>attentionSequence){
   const previousTitle=document.title;document.title='N8Vision · already running';document.body.classList.add('visionAttention');
   setTimeout(()=>{document.body.classList.remove('visionAttention');document.title=previousTitle},3000);
  }attentionSequence=state.sequence;
 }catch(_){}finally{attentionBusy=false}},3000);
}

const removedDetectorCleanupBtn=$('#removedDetectorCleanupBtn');if(removedDetectorCleanupBtn)removedDetectorCleanupBtn.onclick=async()=>{try{const include_reviewed=!!$('#cleanupReviewedDetectors')?.checked;const preview=await j('/api/maintenance/removed-detectors?include_reviewed='+include_reviewed);if(!preview.observations)return alert(`No removable observations found. ${preview.protected} reviewed or owned records preserved.`);const names=preview.models.map(m=>`${m.model}: ${m.observations}`).join('\n');if(!confirm(`Delete ${preview.observations} observations from missing local detectors?\n\n${names}\n\n${preview.protected} reviewed or owned records will be preserved. ${include_reviewed?'Reviewed/owned detector records will also be deleted, and live ownership links detached. ':''}Disabled detectors and unavailable drives are preserved. Images and committed teaching lessons are untouched.`))return;const result=await post('/api/maintenance/removed-detectors',{token:preview.token,include_reviewed});invalidateVisibleAssets();S.obsRevision=String(result.revision);await refreshObservations(true);await refreshDiscovered();$('#status').textContent=`Removed ${result.deleted} observations from uninstalled detectors`;}catch(error){alert(error.message)}};

// Desktop can use the mobile-style bounded metadata window without mobile layout.
if(!S.mobile){
 const settings=$('#settingsDrawer'),section=document.createElement('section'),heading=document.createElement('h3');heading.textContent='Library loading';
 const enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=!!S.desktopWindowed;
 const enabledLabel=document.createElement('label');enabledLabel.className='check';enabledLabel.append(enabled,document.createTextNode(' Load desktop library in windows'));
 const size=document.createElement('input');size.type='number';size.min='1000';size.max='100000';size.step='1000';size.value=String(S.desktopWindowSize);
 const sizeLabel=document.createElement('label');sizeLabel.textContent='Pre-cached image zone (steps of 1,000)';sizeLabel.append(size);
 const note=document.createElement('p');note.className='tiny';note.textContent='Loads this many images around your position and shifts by 500 after crossing the midpoint. Search, filters, sorting and shown-image actions use only this window. Automatic shifts follow Filesystem ascending; other sorts use the 500-image controls. Off loads the whole catalog. This browser remembers the setting.';
 const apply=document.createElement('button');apply.textContent='Apply library loading';
 apply.onclick=async()=>{const value=Number(size.value);if(!Number.isInteger(value)||value<1000||value>100000||value%1000)return alert('Choose a multiple of 1,000 between 1,000 and 100,000.');
  const anchor=S.virtualGrid.rows[S.virtualGrid.cursor]?.[0]?.f;S.windowRestorePosition=anchor?anchor._n8ArchiveIndex??Math.max(0,S.files.findIndex(f=>f.path===anchor.path)):0;S.windowRestoreAnchor=anchor?.path||null;
  S.desktopWindowed=enabled.checked;S.desktopWindowSize=value;localStorage.setItem('n8vision.desktopWindowed',enabled.checked?'1':'0');localStorage.setItem('n8vision.desktopWindowSize',String(value));$('#mobilePagingInfo').hidden=!enabled.checked;windowSteps.hidden=!enabled.checked;apply.disabled=true;
  try{if(S.scopeRoot)await load(S.scopeRoot,true,'window-setting')}finally{apply.disabled=false}
 };
 section.append(heading,enabledLabel,sizeLabel,note,apply);
 const library=[...(settings?.querySelectorAll(':scope > section')||[])].find(el=>el.querySelector('h3')?.textContent.trim()==='Library');
 if(library){const title=library.querySelector('h3');title.after(enabledLabel,sizeLabel,note,apply);settings.querySelector('.settingsHead')?.after(library)}else settings?.querySelector('.settingsHead')?.after(section);

 const windowSteps=document.createElement('div');windowSteps.className='buttonGrid';windowSteps.hidden=!S.desktopWindowed;
 for(const delta of [-500,500]){const button=document.createElement('button');button.textContent=delta<0?'Previous 500':'Next 500';button.onclick=async()=>{if(!mobilePager||S.viewer||S.mobileWindowBusy)return;const pager=mobilePager,position=Math.max(0,(S.mobileNavigationPosition??pager.position)+delta);button.disabled=true;try{const snapshot=await pager.focus(position);if(snapshot&&pager===mobilePager){const anchor=snapshot.files.find(f=>f._n8ArchiveIndex>=position)||snapshot.files.at(-1);S.mobileNavigationPosition=anchor?._n8ArchiveIndex??position;await applyMobileSnapshot(snapshot,anchor?.path,pager)}}catch(error){alert(error.message)}finally{button.disabled=false}};windowSteps.append(button)}
 $('#mobilePagingInfo')?.after(windowSteps);if(S.desktopWindowed)$('#mobilePagingInfo').hidden=false;
}

(function installContentIgnore(){
 const section=document.createElement('section');section.innerHTML='<h3>Ignore contents</h3><p class="tiny">One filename or wildcard per line. Full path rules also work. Matching files stay on disk but are excluded from the browser and selection. Other file types are not blanket-ignored.</p><textarea id="contentIgnoreRules" rows="4" style="width:100%" placeholder="log.html"></textarea><button id="saveContentIgnore">Save and reload library</button><span id="contentIgnoreStatus" class="tiny"></span>';
 const settings=$('#settingsDrawer');if(!settings)return;settings.append(section);
 const input=section.querySelector('textarea'),status=section.querySelector('span'),button=section.querySelector('button');
 let loaded=false;
 new MutationObserver(async()=>{if(loaded||!settings.classList.contains('open'))return;loaded=true;try{const r=await j('/api/config/content-ignore');input.value=r.rules.join('\n')}catch(error){loaded=false;status.textContent=error.message}}).observe(settings,{attributes:true,attributeFilter:['class']});
 button.onclick=async()=>{button.disabled=true;try{
  if(!loaded)throw Error('Wait for ignore rules to load');
  const rules=input.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  await j('/api/config/content-ignore',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules})});
  rootCatalogs.clear();S.selectionRequest=(S.selectionRequest||0)+1;S.selected.clear();S.selectionAnchor=null;S.selectionAnchorMeta=null;
  status.textContent='Saved. Ignored files were left on disk.';
  if(S.scopeRoot)await load(S.scopeRoot,true,'ignore-rules');
 }catch(error){status.textContent=error.message}finally{button.disabled=false}};
})();
