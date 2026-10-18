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
