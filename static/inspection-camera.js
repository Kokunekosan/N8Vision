/* Framing changes display transforms only; source pixels and masks stay intact. */
(() => {
 'use strict';
 const positions=new Map();
 const editable=node=>!!node?.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"])');
 const clamp=(value,lo,hi)=>Math.max(lo,Math.min(hi,value));
 class InspectionCamera {
  constructor({surface,stage,key='',active=()=>true,canPan=()=>true}){
   this.surface=surface;this.stage=stage;this.key=key;this.active=active;this.canPan=canPan;this.zoom=1;this.x=0;this.y=0;this.width=0;this.height=0;this.frame=0;this.lastTime=0;this.keys=new Set();this.stick=[0,0];this.disposed=false;
   this.saved=positions.get(key);this.controls=document.createElement('div');this.controls.className='inspectionFrameControls';this.controls.setAttribute('aria-label','Image framing');
   this.controls.innerHTML='<div class="inspectionZoomRocker"><button type="button" data-frame="minus" aria-label="Zoom out">−</button><output aria-live="polite" title="Zoom relative to fitted view">100%</output><button type="button" data-frame="plus" aria-label="Zoom in">+</button><button type="button" data-frame="fit" title="Reset zoom and center">Fit</button></div><div class="inspectionPanStick" role="group" aria-label="Touch pan stick"><span class="inspectionStickKnob"></span></div><span class="inspectionPanHint">WASD · pan</span>';
   stage.appendChild(this.controls);this.output=this.controls.querySelector('output');this.pad=this.controls.querySelector('.inspectionPanStick');this.knob=this.controls.querySelector('.inspectionStickKnob');
   this.previousTabIndex=stage.getAttribute('tabindex');stage.tabIndex=0;
   this.stageFocus=event=>{if(!this.controls.contains(event.target))stage.focus({preventScroll:true})};stage.addEventListener('pointerdown',this.stageFocus);
   for(const button of this.controls.querySelectorAll('[data-frame]'))button.onclick=event=>{event.stopPropagation();if(!this.usable()||!this.canPan())return;if(button.dataset.frame==='fit')this.fit();else this.setZoom(this.zoom*(button.dataset.frame==='plus'?1.25:1/1.25))};
   this.controls.addEventListener('pointerdown',event=>event.stopPropagation());
   this.keydown=event=>{
    if(!this.usable()||editable(event.target)||event.ctrlKey||event.metaKey||event.altKey||document.querySelector('dialog[open]'))return;
    const key=event.key.toLowerCase();if(!['w','a','s','d','+','=','-'].includes(key))return;
    event.preventDefault();
    if(['+','=','-'].includes(key)){if(this.canPan())this.setZoom(this.zoom*(key==='-'?1/1.25:1.25));return}
    this.keys.add(key);this.start();
   };
   this.keyup=event=>this.keys.delete(event.key.toLowerCase());this.blur=()=>this.stopInput();this.focus=event=>{if(editable(event.target))this.stopInput()};
   document.addEventListener('keydown',this.keydown);document.addEventListener('keyup',this.keyup);document.addEventListener('focusin',this.focus);window.addEventListener('blur',this.blur);
   this.pad.onpointerdown=event=>{if(!this.usable()||this.pointerId!==undefined)return;event.preventDefault();stage.focus({preventScroll:true});this.pointerId=event.pointerId;this.pad.setPointerCapture(event.pointerId);this.updateStick(event);this.start()};
   this.pad.onpointermove=event=>{if(event.pointerId===this.pointerId)this.updateStick(event)};
   const end=event=>{if(event.pointerId!==this.pointerId)return;this.pointerId=undefined;this.stick=[0,0];this.knob.style.transform='translate(0px,0px)'};
   this.pad.onpointerup=this.pad.onpointercancel=this.pad.onlostpointercapture=end;
   this.refresh();
  }
  usable(){return !this.disposed&&this.surface.isConnected&&this.stage.isConnected&&this.active()}
  refresh(){
   const width=parseFloat(this.surface.style.width),height=parseFloat(this.surface.style.height);
   if(!(width>0&&height>0))return;
   if(this.saved){this.zoom=this.saved.zoom;this.x=this.saved.x*width;this.y=this.saved.y*height;this.saved=null}
   else if(this.width&&this.height){this.x*=width/this.width;this.y*=height/this.height}
   this.width=width;this.height=height;this.apply();
  }
  apply(){
   const rect=this.stage.getBoundingClientRect(),w=this.width*this.zoom,h=this.height*this.zoom;
   const maxX=Math.max(0,(rect.width+w)/2-Math.min(64,w/2)),maxY=Math.max(0,(rect.height+h)/2-Math.min(64,h/2));
   this.x=clamp(this.x,-maxX,maxX);this.y=clamp(this.y,-maxY,maxY);
   this.surface.style.transform=`translate(${this.x}px,${this.y}px) scale(${this.zoom})`;this.surface.style.transformOrigin='center center';this.output.textContent=Math.round(this.zoom*100)+'%';
   if(this.key&&this.width&&this.height){positions.delete(this.key);positions.set(this.key,{zoom:this.zoom,x:this.x/this.width,y:this.y/this.height});while(positions.size>40)positions.delete(positions.keys().next().value)}
  }
  setZoom(value){const next=clamp(value,.25,16),ratio=next/this.zoom;this.x*=ratio;this.y*=ratio;this.zoom=next;this.apply()}
  pan(dx,dy){this.x+=dx;this.y+=dy;this.apply()}
  fit(){this.zoom=1;this.x=this.y=0;this.apply()}
  updateStick(event){const rect=this.pad.getBoundingClientRect(),radius=Math.max(1,rect.width*.3);let x=(event.clientX-rect.left-rect.width/2)/radius,y=(event.clientY-rect.top-rect.height/2)/radius;const distance=Math.hypot(x,y);if(distance>1){x/=distance;y/=distance}this.stick=distance<.12?[0,0]:[x,y];this.knob.style.transform=`translate(${x*radius}px,${y*radius}px)`}
  start(){if(!this.frame){this.lastTime=0;this.frame=requestAnimationFrame(time=>this.tick(time))}}
  tick(time){
   this.frame=0;if(!this.usable()){this.stopInput();return}
   let x=(this.keys.has('d')?1:0)-(this.keys.has('a')?1:0)+this.stick[0],y=(this.keys.has('s')?1:0)-(this.keys.has('w')?1:0)+this.stick[1];
   if(!x&&!y){this.lastTime=0;return}
   const length=Math.hypot(x,y);if(length>1){x/=length;y/=length}const elapsed=this.lastTime?Math.min(.05,(time-this.lastTime)/1000):1/60;this.lastTime=time;
   if(this.canPan()&&!editable(document.activeElement)&&!document.querySelector('dialog[open]'))this.pan(x*360*elapsed,y*360*elapsed);
   this.frame=requestAnimationFrame(next=>this.tick(next));
  }
  stopInput(){this.keys.clear();this.stick=[0,0];this.pointerId=undefined;this.knob.style.transform='translate(0px,0px)';if(this.frame)cancelAnimationFrame(this.frame);this.frame=0;this.lastTime=0}
  dispose(){if(this.disposed)return;this.stopInput();this.disposed=true;document.removeEventListener('keydown',this.keydown);document.removeEventListener('keyup',this.keyup);document.removeEventListener('focusin',this.focus);window.removeEventListener('blur',this.blur);this.stage.removeEventListener('pointerdown',this.stageFocus);if(this.previousTabIndex===null)this.stage.removeAttribute('tabindex');else this.stage.setAttribute('tabindex',this.previousTabIndex);this.controls.remove()}
 }
 window.InspectionCamera=InspectionCamera;
})();
