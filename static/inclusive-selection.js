/* Selection endpoints are catalog positions, never native text/DOM positions. */
window.installGridSelectionGuard=function(grid){
 if(!grid)return;
 grid.addEventListener('pointerdown',event=>{if(event.button===0&&event.shiftKey&&event.target.closest('.card')){event.preventDefault();window.getSelection()?.removeAllRanges()}},{capture:true});
 grid.addEventListener('dragstart',event=>{if(event.target.closest('.card'))event.preventDefault()});
};
window.inclusiveCatalogRange=function(files,anchor,target,positions=null){
 const a=files.findIndex(file=>file.path===anchor),b=files.findIndex(file=>file.path===target);
 if(a<0||b<0)return null;
 let range;
 if(positions&&Number.isInteger(positions.anchor)&&Number.isInteger(positions.target)){
  const n=files.length,mod=i=>((i%n)+n)%n;
  if(mod(positions.anchor)!==a||mod(positions.target)!==b)return null;
  const step=positions.target>=positions.anchor?1:-1,count=Math.min(n,Math.abs(positions.target-positions.anchor)+1);
  range=Array.from({length:count},(_,i)=>files[mod(positions.anchor+i*step)]);
 }else range=files.slice(Math.min(a,b),Math.max(a,b)+1);
 return range.filter(file=>!file._n8Tombstone&&!file._n8ForwardTo).map(file=>file.path);
};
