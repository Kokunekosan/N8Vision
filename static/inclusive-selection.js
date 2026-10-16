/* Selection endpoints are catalog positions, never native text/DOM positions. */
window.installGridSelectionGuard=function(grid){
 if(!grid)return;
 grid.addEventListener('pointerdown',event=>{if(event.button===0&&event.shiftKey&&event.target.closest('.card')){event.preventDefault();window.getSelection()?.removeAllRanges()}},{capture:true});
 grid.addEventListener('dragstart',event=>{if(event.target.closest('.card'))event.preventDefault()});
};
window.inclusiveCatalogRange=function(files,anchor,target){
 const a=files.findIndex(file=>file.path===anchor),b=files.findIndex(file=>file.path===target);
 if(a<0||b<0)return null;
 return files.slice(Math.min(a,b),Math.max(a,b)+1).filter(file=>!file._n8Tombstone&&!file._n8ForwardTo).map(file=>file.path);
};
