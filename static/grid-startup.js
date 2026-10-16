/* Optional UI work must not own the first image paint. */
window.createGridWorkQueue=function({ready,idle,report=console.warn}){
 const pending=new Map();let scheduled=false;
 function flush(){scheduled=false;if(!ready())return;const jobs=[...pending.values()];pending.clear();for(const job of jobs)Promise.resolve().then(job).catch(report)}
 function kick(){if(scheduled||!pending.size||!ready())return;scheduled=true;idle(flush)}
 return {enqueue(key,job){pending.set(key,job);kick()},kick};
};
