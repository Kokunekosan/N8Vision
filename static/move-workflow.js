window.createFolderArchitecture=function({key}){
 const nodes=new Map(),authoritative=new Set(),completeParents=new Set();let children=new Map();
 const clean=p=>{p=String(p||'').replace(/\//g,'\\').replace(/\\+$/,'');return /^[a-z]:$/i.test(p)?p+'\\':p};
 function parent(p){const q=clean(p).replace(/\\+$/,'');if(/^[a-z]:$/i.test(q)||(/^\\\\/.test(q)&&q.split('\\').filter(Boolean).length<=2))return null;const i=q.lastIndexOf('\\');return i<0?null:clean(q.slice(0,i))}
 function add(p){p=clean(p);while(p&&!nodes.has(key(p))){nodes.set(key(p),p);p=parent(p)}}
 function rebuild(){children=new Map();for(const p of nodes.values()){const up=parent(p);if(up){const k=key(up);if(!children.has(k))children.set(k,[]);children.get(k).push({path:p,name:p.replace(/\\+$/,'').split('\\').pop()})}}}
 return {
  seed(paths){for(const p of paths)if(![...authoritative].some(root=>key(p)===root||key(p).startsWith(root+'\\')))add(p);rebuild()},
  replaceRoot(root,paths){const r=key(root);for(const k of nodes.keys())if(k===r||k.startsWith(r+'\\'))nodes.delete(k);add(root);paths.forEach(add);authoritative.add(r);rebuild()},
  replaceChildren(data){const r=key(data.path),keep=new Set(data.directories.map(d=>key(d.path)));for(const p of nodes.values())if(key(parent(p)||'')===r&&!keep.has(key(p))){const gone=key(p);for(const k of nodes.keys())if(k===gone||k.startsWith(gone+'\\'))nodes.delete(k)}add(data.path);data.directories.forEach(d=>add(d.path));completeParents.add(r);rebuild()},
  read(path){const p=nodes.get(key(path));if(!p)return null;return {path:p,parent:parent(p),directories:[...(children.get(key(p))||[])].sort((a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'}))}},
  covered(path){return [...authoritative].some(r=>key(path)===r||key(path).startsWith(r+'\\'))},
  complete(path){return completeParents.has(key(path))||this.covered(path)}
 };
};
window.createMoveDirectoryCache=function({fetch,key}){
 const entries=new Map(),pending=new Map();
 return {peek:path=>entries.get(key(path)),refresh(path){
  const k=key(path);if(pending.has(k))return pending.get(k);
  const request=Promise.resolve().then(()=>fetch(path)).then(data=>{entries.set(k,data);return data}).catch(error=>{entries.delete(k);throw error}).finally(()=>pending.delete(k));
  pending.set(k,request);return request;
 }};
};
window.createMoveQueue=function({key,run,queued,failed,settled}){
 const pending=new Set();let tail=Promise.resolve();
 return {has:path=>pending.has(key(path)),enqueue(paths,destination){
  const batch=[...new Map(paths.filter(p=>!pending.has(key(p))).map(p=>[key(p),p])).values()];
  if(!batch.length)return false;
  batch.forEach(p=>pending.add(key(p)));queued(batch,destination);
  tail=tail.then(()=>run(batch,destination)).catch(error=>failed(error,batch,destination)).finally(()=>{
   batch.forEach(p=>pending.delete(key(p)));settled(batch,destination);
  });
  return true;
 },idle:()=>tail};
};
