/* Metadata paging is independent of rendered rows and thumbnail preparation. */
class MobileArchiveWindow {
 constructor(fetchPage){this.fetchPage=fetchPage;this.pages=new Map();this.pending=new Map();this.edits=new Map();this.pathEdits=new Map();this.endPage=null;this.version=0;this.closed=false;this.position=0;}
 close(){this.closed=true;this.version++;this.pages.clear();this.pending.clear();this.edits.clear();this.pathEdits.clear();}
 remember(file){if(Number.isInteger(file?._n8ArchiveIndex))this.edits.set(file._n8ArchiveIndex,{...file});}
 deletePaths(paths){for(const path of paths)this.pathEdits.set(path,{deleted:true});}
 movePaths(items,rootOf){for(const item of items){const a=rootOf(item.from),b=rootOf(item.to);this.pathEdits.set(item.from,a&&a===b?{to:item.to}:{forward:item.to});}}
 restore(file){
  let f=this.edits.get(file._n8ArchiveIndex)||file,seen=new Set();
  while(!seen.has(f.path)){seen.add(f.path);const edit=this.pathEdits.get(f.path);if(!edit)break;
   if(edit.deleted){f={...f,_n8Tombstone:true};break;}
   if(edit.forward){f={...f,_n8ForwardTo:edit.forward};break;}
   f={...f,path:edit.to,name:edit.to.split(/[\\/]/).pop(),observations:(f.observations||[]).map(o=>({...o,path:edit.to}))};
  }return f;
 }
 async page(index){
  if(this.pages.has(index))return this.pages.get(index);
  if(this.pending.has(index))return this.pending.get(index);
  const promise=(async()=>{
   for(;;){if(this.closed)return null;const packet=await this.fetchPage(index);if(this.closed)return null;
    if(packet.waiting)continue;if(packet.error)throw new Error(packet.error);
    if(packet.complete)this.endPage=(packet.files||[]).length?index:index-1;
    return (packet.files||[]).map((f,i)=>({...f,_n8ArchiveIndex:index*500+i}));
   }
  })();this.pending.set(index,promise);
  try{return await promise;}finally{if(this.pending.get(index)===promise)this.pending.delete(index);}
 }
 async focus(position){
  const version=++this.version;position=Math.max(0,Math.floor(position));
  if(this.endPage!==null)position=Math.min(position,Math.max(0,(this.endPage+1)*500-1));
  const page=Math.floor(position/500),lo=Math.max(0,page-1),hi=page+1,next=new Map();
  for(let index=lo;index<=hi;index++){
   if(this.endPage!==null&&index>this.endPage)break;
   const files=await this.page(index);if(this.closed||version!==this.version)return null;
   if(files?.length)next.set(index,files);
  }
  if(this.closed||version!==this.version)return null;
  const changed=next.size!==this.pages.size||[...next.keys()].some(k=>!this.pages.has(k));
  this.pages=next;this.position=position;
  const files=[...next.values()].flat().map(f=>this.restore(f));
  return {files,changed,position,first:files[0]?._n8ArchiveIndex??0,last:files.at(-1)?._n8ArchiveIndex??0};
 }
}
if(typeof module!=='undefined')module.exports=MobileArchiveWindow;
