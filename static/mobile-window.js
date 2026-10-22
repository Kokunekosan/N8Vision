/* Metadata paging is independent of rendered rows and thumbnail preparation. */
class MobileArchiveWindow {
 constructor(fetchPage,{windowSize=1500,fixedWindow=false}={}){this.fetchPage=fetchPage;this.fixedWindow=fixedWindow;this.pageCount=Math.max(2,Math.round(windowSize/500));this.pages=new Map();this.pending=new Map();this.edits=new Map();this.pathEdits=new Map();this.observationEdits=new Map();this.endPage=null;this.version=0;this.closed=false;this.position=0;}
 range(position){const page=Math.floor(Math.max(0,position)/500);if(!this.fixedWindow)return {lo:Math.max(0,page-1),hi:this.endPage===null?page+1:Math.min(page+1,this.endPage)};const before=Math.floor((this.pageCount-1)/2);let lo=Math.max(0,page-before);if(this.endPage!==null)lo=Math.min(lo,Math.max(0,this.endPage-this.pageCount+1));return {lo,hi:this.endPage===null?lo+this.pageCount-1:Math.min(lo+this.pageCount-1,this.endPage)};}
 close(){this.closed=true;this.version++;this.pages.clear();this.pending.clear();this.edits.clear();this.pathEdits.clear();this.observationEdits.clear();}
 rememberObservations(path,observations){this.observationEdits.set(path,observations);}
 remember(file){if(Number.isInteger(file?._n8ArchiveIndex))this.edits.set(file._n8ArchiveIndex,{...file});if(file?.path&&file.observations)this.observationEdits.set(file.path,file.observations);}
 acceptVerified(files){
  const key=p=>String(p).replace(/\//g,'\\').toLowerCase(),verified=new Map(files.map(f=>[key(f.path),f]));
  for(const path of this.pathEdits.keys())if(verified.has(key(path)))this.pathEdits.delete(path);
  for(const [index,file] of this.edits){const fresh=verified.get(key(file.path));if(fresh){const next={...file,...fresh};delete next._n8Tombstone;delete next._n8ForwardTo;this.edits.set(index,next)}}
  for(const file of files)this.remember(file);
 }
 deletePaths(paths){for(const path of paths)this.pathEdits.set(path,{deleted:true});}
 movePaths(items,rootOf,{leavePlaceholder=false}={}){for(const item of items){const a=rootOf(item.from),b=rootOf(item.to);this.pathEdits.set(item.from,!leavePlaceholder&&a&&a===b?{to:item.to}:{forward:item.to});}}
 restore(file){
  let f=this.edits.get(file._n8ArchiveIndex)||file,seen=new Set();
  while(!seen.has(f.path)){seen.add(f.path);const edit=this.pathEdits.get(f.path);if(!edit)break;
   if(edit.deleted){f={...f,_n8Tombstone:true};break;}
   if(edit.forward){f={...f,_n8ForwardTo:edit.forward};break;}
   f={...f,path:edit.to,name:edit.to.split(/[\\/]/).pop(),observations:(f.observations||[]).map(o=>({...o,path:edit.to}))};
  }if(this.observationEdits.has(f.path))f={...f,observations:this.observationEdits.get(f.path)};return f;
 }
 async page(index){
  if(this.pages.has(index))return this.pages.get(index);
  if(this.pending.has(index))return this.pending.get(index);
  const promise=(async()=>{
   for(;;){if(this.closed)return null;const packet=await this.fetchPage(index);if(this.closed)return null;
    if(packet.waiting)continue;if(packet.error)throw new Error(packet.error);
    if(packet.complete)this.endPage=Number.isInteger(packet.prepared)?Math.ceil(packet.prepared/500)-1:(packet.files||[]).length?index:index-1;
    return (packet.files||[]).map((f,i)=>({...f,_n8ArchiveIndex:index*500+i}));
   }
  })();this.pending.set(index,promise);
  try{return await promise;}finally{if(this.pending.get(index)===promise)this.pending.delete(index);}
 }
 async initial(position=0){
  const version=++this.version,index=Math.floor(Math.max(0,position)/500),files=await this.page(index);
  if(this.closed||version!==this.version)return null;
  if(!files?.length)return this.focus(position);
  this.pages=new Map([[index,files]]);this.position=Math.min(position,files.at(-1)._n8ArchiveIndex);
  const restored=files.map(file=>this.restore(file));
  return {files:restored,changed:true,position:this.position,first:restored[0]._n8ArchiveIndex,last:restored.at(-1)._n8ArchiveIndex};
 }
 async focus(position){
  const version=++this.version;position=Math.max(0,Math.floor(position));
  if(this.endPage!==null)position=Math.min(position,Math.max(0,(this.endPage+1)*500-1));
  const {lo,hi}=this.range(position),next=new Map();
  for(let index=lo;index<=hi;index++){
   if(this.endPage!==null&&index>this.endPage)break;
   const files=await this.page(index);if(this.closed||version!==this.version)return null;
   if(files?.length)next.set(index,files);
  }
  if(this.closed||version!==this.version)return null;
  if(!next.size&&this.endPage!==null&&this.endPage>=0&&lo>this.endPage)return this.focus((this.endPage+1)*500-1);
  const changed=next.size!==this.pages.size||[...next.keys()].some(k=>!this.pages.has(k));
  this.pages=next;this.position=position;
  const files=[...next.values()].flat().map(f=>this.restore(f));
  if(files.length)this.position=Math.min(position,files.at(-1)._n8ArchiveIndex);
  return {files,changed,position:this.position,first:files[0]?._n8ArchiveIndex??0,last:files.at(-1)?._n8ArchiveIndex??0};
 }
}
if(typeof module!=='undefined')module.exports=MobileArchiveWindow;
