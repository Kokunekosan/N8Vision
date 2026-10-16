/* Native disclosures keep the controls mounted and start expanded every load. */
(() => {
 const rail=document.getElementById('rail');if(!rail)return;
 function enhance(section){
  const headings=[...section.children].filter(node=>node.tagName==='H3');
  for(const heading of headings){
   const details=document.createElement('details'),summary=document.createElement('summary'),body=document.createElement('div');
   details.className='menuSection';details.open=true;body.className='menuSectionContents';
   // Some generated sections place controls before their first heading.
   const prefix=[];if(heading===headings[0])for(let node=section.firstChild;node&&node!==heading;node=node.nextSibling){if(node.nodeType===1&&node.classList.contains('menuSection'))prefix.length=0;else prefix.push(node)}
   let node=heading.nextSibling;const content=[];
   while(node&&!(node.nodeType===1&&(node.tagName==='H3'||node.classList.contains('menuSection')))){content.push(node);node=node.nextSibling}
   section.insertBefore(details,heading);summary.append(heading);body.append(...prefix,...content);details.append(summary,body);
  }
 }
 rail.querySelectorAll('section').forEach(enhance);
 new MutationObserver(records=>{
  const sections=new Set();
  for(const record of records)for(const node of record.addedNodes){
   if(node.nodeType!==1)continue;
   if(node.tagName==='SECTION')sections.add(node);
   node.querySelectorAll('section').forEach(section=>sections.add(section));
   const parent=node.closest('section');if(parent)sections.add(parent);
  }
  for(const section of sections)if(rail.contains(section))enhance(section);
 }).observe(rail,{childList:true,subtree:true});
})();
