window.placeBesideOutputs=function(files,links,key){
 const byPath=new Map(files.map(f=>[key(f.path),f])),children=new Map(),childKeys=new Set();
 for(const link of links){
  if(link.destination!=='beside')continue;
  const source=key(link.source),target=key(link.target);
  if(source===target||!byPath.has(source)||!byPath.has(target))continue;
  if(!children.has(source))children.set(source,[]);
  if(!children.get(source).includes(target))children.get(source).push(target);
  childKeys.add(target);
 }
 const result=[],emitted=new Set();
 function emit(k){if(emitted.has(k))return;emitted.add(k);result.push(byPath.get(k));for(const child of children.get(k)||[])emit(child)}
 for(const f of files)if(!childKeys.has(key(f.path)))emit(key(f.path));
 for(const f of files)emit(key(f.path));
 return result;
};
