window.createRefineSettingsStore=function(storage){
 const key='n8vision.refineSettings.v1';let profiles={};
 try{
  const saved=JSON.parse(storage.getItem(key)||'null');
  if(saved?.version===2&&saved.profiles&&typeof saved.profiles==='object')profiles=saved.profiles;
  else if(saved){
   for(const [signature,settings] of Object.entries(saved.profiles||{}))profiles[signature]={enabled:!!saved.enabled,settings};
   if(saved.signature&&saved.settings)profiles[saved.signature]={enabled:!!saved.enabled,settings:saved.settings};
  }
 }catch(_){}
 function persist(){try{storage.setItem(key,JSON.stringify({version:2,profiles}))}catch(error){console.warn('Refiner settings could not be saved',error)}}
 return {
  enabled:signature=>profiles[signature]?.enabled===true,
  enable(signature,enabled){profiles[signature]={...(profiles[signature]||{}),enabled:!!enabled};persist()},
  save(signature,settings){if(!profiles[signature]?.enabled)return;profiles[signature]={enabled:true,settings:JSON.parse(JSON.stringify(settings))};persist()},
  read(signature){const profile=profiles[signature],settings=profile?.settings;return profile?.enabled&&settings&&Array.isArray(settings.loras)?JSON.parse(JSON.stringify(settings)):null}
 };
};
