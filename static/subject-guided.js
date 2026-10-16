window.openGuidedSubjectSplit=async function({path,observation,sourceUrl,onDone}){
 const parent=typeof observation.geometry==='string'?JSON.parse(observation.geometry):observation.geometry;
 const [ox,oy,x2,y2]=parent.bbox.map(Math.round),w=x2-ox,h=y2-oy;
 const dialog=document.createElement('dialog');dialog.style.cssText='width:min(1000px,96vw);max-height:94dvh;overflow:auto;box-sizing:border-box';
 const heading=document.createElement('h3');heading.textContent='Split a composite subject';
 const help=document.createElement('p');help.textContent='Draw one hint box around each sub-subject (2–16). Boxes prompt the segmenter; masks may extend beyond them within this parent subject. Review before replacing the composite.';
 const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;canvas.style.cssText='display:block;width:100%;height:auto;touch-action:none;background:#111';
 const ctx=canvas.getContext('2d'),source=new Image(),hints=[];let start=null,pending=null,busy=false,timer=null,review=null,token=null;
 const status=document.createElement('p');status.setAttribute('role','status');
 const labels=document.createElement('div');
 const passLabel=document.createElement('label'),limit=document.createElement('input');limit.type='number';limit.min='0';limit.max='100';limit.value='17';limit.style.width='75px';passLabel.append(document.createTextNode('Maximum YOLAST naming passes per crop (0 skips naming) '),limit);
 const undo=document.createElement('button');undo.textContent='Undo hint';
 const run=document.createElement('button');run.textContent='Segment marked subjects';run.disabled=true;
 const accept=document.createElement('button');accept.textContent='Accept split';accept.hidden=true;
 const close=document.createElement('button');close.textContent='Cancel';
 const resume=document.createElement('button');resume.textContent='Review last completed split';resume.hidden=true;
 const colors=['#46ddff','#ff63d6','#ffe15a','#70ff97','#ff915c','#a3a0ff'];
 let layers=[];
 function draw(){
  if(!source.naturalWidth)return;ctx.clearRect(0,0,w,h);ctx.drawImage(source,ox,oy,w,h,0,0,w,h);
  if(review){for(let i=0;i<layers.length;i++){ctx.drawImage(layers[i],0,0);const b=review.candidates[i].geometry.bbox;ctx.fillStyle=colors[i%colors.length];ctx.font=Math.max(12,w/55)+'px sans-serif';ctx.fillText(String(i+1),b[0]-ox+4,b[1]-oy+20)}}
  else for(const [i,b] of [...hints,...(pending?[pending]:[])].entries()){ctx.strokeStyle=colors[i%colors.length];ctx.lineWidth=Math.max(2,w/350);ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);ctx.fillStyle=ctx.strokeStyle;ctx.font=Math.max(12,w/55)+'px sans-serif';ctx.fillText(String(i+1),b[0]+4,b[1]+20)}
 }
 function point(event){const r=canvas.getBoundingClientRect();return [Math.max(0,Math.min(w,(event.clientX-r.left)*w/r.width)),Math.max(0,Math.min(h,(event.clientY-r.top)*h/r.height))]}
 canvas.onpointerdown=event=>{if(busy||review||hints.length>=16||!source.naturalWidth)return;event.preventDefault();start=point(event);canvas.setPointerCapture(event.pointerId)};
 canvas.onpointermove=event=>{if(!start)return;const p=point(event);pending=[Math.min(start[0],p[0]),Math.min(start[1],p[1]),Math.max(start[0],p[0]),Math.max(start[1],p[1])];draw()};
 canvas.onpointerup=()=>{if(pending&&pending[2]-pending[0]>=2&&pending[3]-pending[1]>=2)hints.push(pending);start=pending=null;run.disabled=hints.length<2;status.textContent=hints.length+' hints';draw()};
 canvas.onpointercancel=()=>{start=pending=null;draw()};
 undo.onclick=()=>{if(busy||review)return;hints.pop();run.disabled=hints.length<2;draw()};
 function showReview(result){
  review=result;layers=result.candidates.map((candidate,i)=>{
   const g=candidate.geometry,layer=document.createElement('canvas');layer.width=w;layer.height=h;const c=layer.getContext('2d');c.fillStyle=colors[i%colors.length];c.globalAlpha=.38;
   const mw=g.mask_size[0],dx=g.bbox[0]-ox,dy=g.bbox[1]-oy;
   for(let ri=0;ri<g.mask_rle.length;ri+=2){let s=g.mask_rle[ri],n=g.mask_rle[ri+1];while(n>0){const yy=Math.floor(s/mw),xx=s%mw,take=Math.min(n,mw-xx);c.fillRect(dx+xx,dy+yy,take,1);s+=take;n-=take}}
   const label=document.createElement('label'),input=document.createElement('input');label.textContent=(i+1)+'. ';label.style.cssText='display:block;color:'+colors[i%colors.length];input.value=candidate.concept;input.maxLength=200;label.append(input);labels.append(label);return layer;
  });
  status.textContent=result.candidates.length+' masks · '+result.naming_passes+' naming passes. '+(result.overlap_review_required?'Masks still overlap—review carefully; cancel and adjust hints if these are wrong.':'Review outlines and labels, then accept or cancel.');
  accept.hidden=false;run.hidden=true;undo.disabled=true;limit.disabled=true;draw();
 }
 async function poll(id){
  if(!dialog.isConnected)return;
  try{const response=await j('/api/jobs'),job=response.jobs.find(x=>x.id===id);if(!job)throw Error('Split job is no longer available.');
   status.textContent=job.phase||'Segmenting subjects…';
   if(job.state==='error'||job.state==='stopped')throw Error(job.error||'Split stopped; original retained.');
   if(job.state==='done'){token=job.result.review_id;showReview(await j('/api/subjects/guided-split/'+token));busy=false;close.textContent='Cancel';return}
   timer=setTimeout(()=>poll(id),1500);
  }catch(error){busy=false;run.disabled=false;undo.disabled=false;status.textContent=error.message;close.textContent='Cancel'}
 }
 run.onclick=async()=>{
  const max_passes=Number(limit.value);if(!Number.isInteger(max_passes)||max_passes<0||max_passes>100){status.textContent='Choose 0–100 naming passes.';return}
  busy=true;run.disabled=true;undo.disabled=true;status.textContent='Queuing guided split…';
  try{const job=await post('/api/subjects/guided-split',{path,concept:observation.concept,provider:observation.provider,model:observation.model,kind:observation.kind,geometry:observation.geometry,hints:hints.map(b=>[b[0]+ox,b[1]+oy,b[2]+ox,b[3]+oy]),max_passes});close.textContent='Close (job continues)';poll(job.id)}catch(error){busy=false;run.disabled=false;undo.disabled=false;status.textContent=error.message}
 };
 accept.onclick=async()=>{accept.disabled=true;try{await post('/api/subjects/guided-split/'+token+'/accept',{labels:[...labels.querySelectorAll('input')].map(x=>x.value)});dialog.close();await onDone()}catch(error){status.textContent=error.message;accept.disabled=false}};
 close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>{clearTimeout(timer);dialog.remove()},{once:true});
 dialog.append(heading,help,canvas,status,passLabel,labels,undo,run,accept,resume,close);document.body.append(dialog);dialog.showModal();
 j('/api/jobs').then(response=>{if(!dialog.isConnected||review||busy)return;const job=response.jobs.find(x=>x.kind==='subject-guided-split'&&x.state==='done'&&x.result?.path===path&&JSON.stringify(x.result.parent_bbox)===JSON.stringify(parent.bbox));if(job){resume.hidden=false;resume.onclick=async()=>{try{token=job.result.review_id;showReview(await j('/api/subjects/guided-split/'+token));resume.hidden=true}catch(error){status.textContent=error.message}}}}).catch(()=>{});
 source.onload=draw;source.onerror=()=>status.textContent='Source image could not be loaded.';source.src=sourceUrl;
};
