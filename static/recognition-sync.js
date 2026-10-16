/* Patch metadata in every loaded view without rebuilding the scroll ring. */
window.syncRecognitionMetadata=function(map,{files=[],catalogs=[],pager=null}={}){
 const visited=new Set();
 function update(file){if(!file||visited.has(file))return;visited.add(file);if(Object.prototype.hasOwnProperty.call(map,file.path)){file.observations=map[file.path];pager?.remember(file)}}
 files.forEach(update);for(const entry of catalogs)(entry.files||[]).forEach(update);
 for(const [path,observations] of Object.entries(map))pager?.rememberObservations(path,observations);
 return visited.size;
};
