(() => {
  'use strict';
  let context,analyser,gain,source,wave,resolvePlayback,serial=0,level=0,playing=false,volume=.65,wakeWaiter;
  const jobs=new Set();
  const emit=(name,detail)=>window.dispatchEvent(new CustomEvent('raphael:voice-'+name,{detail}));
  async function request(path,body){
    const response=await fetch(path,{headers:{'Content-Type':'application/json','X-Raphael-Token':window.RaphaelConnection?.token||''},...(body?{method:'POST',body:JSON.stringify(body)}:{}),cache:'no-store',signal:AbortSignal.timeout(15000)});
    const data=await response.json();if(!response.ok)throw Error(data.error||'The local voice connection was interrupted.');return data;
  }
  function prepare(){
    if(!context){const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw Error('Audio is not supported in this browser. Text chat is available.');context=new Audio();gain=context.createGain();gain.gain.value=volume;analyser=context.createAnalyser();analyser.fftSize=2048;gain.connect(analyser);analyser.connect(context.destination);wave=new Float32Array(analyser.fftSize);}
    return context.resume();
  }
  function stop(){
    serial++;playing=false;level=0;
    if(source){source.onended=null;try{source.stop();}catch{}source.disconnect();source=null;}
    if(resolvePlayback){resolvePlayback({stopped:true});resolvePlayback=null;}
    for(const id of jobs)request('/api/cancel/'+id,{}).catch(()=>{});jobs.clear();
    if(wakeWaiter){wakeWaiter();wakeWaiter=null;}
    emit('level',{level:0});emit('end',{stopped:true});
  }
  async function synthesize(text,voice,speed,token){
    if(token!==serial)return null;
    const job=await request('/api/speak',{text,voice,speed});
    if(token!==serial){request('/api/cancel/'+job.id,{}).catch(()=>{});return null;}
    jobs.add(job.id);
    try{
      const deadline=performance.now()+180000;
      while(token===serial&&performance.now()<deadline){
        const status=await request('/api/jobs/'+job.id);
        if(token!==serial)return null;
        if(status.state==='error')throw Error(status.error);
        if(status.state==='cancelled')return null;
        if(status.state==='ready'){
          const response=await fetch(status.audio,{headers:{'X-Raphael-Token':window.RaphaelConnection?.token||''},signal:AbortSignal.timeout(10000)});
          if(!response.ok)throw Error('The audio could not be loaded.');
          const buffer=await context.decodeAudioData(await response.arrayBuffer());
          return token===serial?{buffer,details:status.details}:null;
        }
        await new Promise(resolve=>setTimeout(resolve,80));
      }
      if(token===serial)throw Error('Voice generation timed out. Text chat remains available.');
      return null;
    }finally{jobs.delete(job.id);}
  }
  async function play(prepared,token){
    if(!prepared||token!==serial)return {stopped:true};
    source=context.createBufferSource();source.buffer=prepared.buffer;source.connect(gain);playing=true;
    return await new Promise((resolve,reject)=>{
      resolvePlayback=resolve;
      source.onended=()=>{if(token!==serial)return;playing=false;level=0;source.disconnect();source=null;resolvePlayback=null;emit('end',{stopped:false});resolve({stopped:false,...prepared.details});};
      try{source.start();emit('start',{generation_seconds:0,...prepared.details,duration:prepared.buffer.duration});}
      catch(error){playing=false;source.disconnect();source=null;resolvePlayback=null;reject(error);}
    });
  }
  async function speak(text,voice='heart',speed=1){
    stop();const token=serial;await prepare();
    if(token!==serial)return {stopped:true};
    emit('progress',{message:'Preparing the voice on your computer…'});
    try{return await play(await synthesize(text,voice,speed,token),token);}
    catch(error){if(token===serial)stop();throw error;}
  }
  function createStream(voice='heart',speed=1){
    stop();const token=serial;let pending='',offset=0,emitted=0,finished=false,first=true,audioReady=false,capped=false;
    const chunks=[],prepared=[];let next=0;
    function signal(){if(wakeWaiter){const resolve=wakeWaiter;wakeWaiter=null;resolve();}}
    function fill(){
      if(!audioReady||token!==serial)return;
      while(prepared.length<2&&next<chunks.length){
        const task=synthesize(chunks[next++],voice,speed,token);task.catch(()=>{});prepared.push(task);
      }
    }
    function push(text,final=false){
      if(token!==serial)return;
      if(text.length<offset)throw Error('The response stream changed.');
      const addition=text.slice(offset),remaining=Math.max(0,2400-emitted-pending.length);offset=text.length;
      if(!capped){pending+=addition.slice(0,remaining);if(addition.length>remaining){capped=true;const last=pending.lastIndexOf(' ');pending=last<0?'':pending.slice(0,last);}}
      while(pending){
        let boundary=null,limit=first?72:220;
        for(const match of pending.matchAll(/[.!?](?:["”’]*)\s+|\n+/g)){
          const prefix=pending.slice(0,match.index+match[0].length).trim();
          if(/\b(?:Dr|Mr|Mrs|Ms|Prof|St|vs|e\.g|i\.e)\.$/i.test(prefix))continue;
          if(prefix.length>=12||final){boundary=match.index+match[0].length;break;}
        }
        if((boundary===null||boundary>limit)&&pending.length>limit){boundary=pending.lastIndexOf(' ',limit);if(boundary<=0){boundary=pending.indexOf(' ',limit);if(boundary<0)boundary=null;}}
        if(boundary===null&&final)boundary=pending.length;
        if(boundary===null)break;
        const piece=pending.slice(0,boundary);pending=pending.slice(boundary);emitted+=piece.length;
        if(piece.trim()){chunks.push(piece.trim());first=false;}
      }
      if(final)finished=true;fill();signal();
    }
    const completion=(async()=>{
      await prepare();audioReady=true;
      while(token===serial){
        fill();
        if(!prepared.length){if(finished)break;await new Promise(resolve=>{wakeWaiter=resolve;});continue;}
        const ready=await prepared.shift();fill();
        if(!ready||token!==serial)return {stopped:true};
        await play(ready,token);
      }
      return {stopped:token!==serial};
    })().catch(error=>{if(token===serial)stop();throw error;});
    completion.catch(()=>{});
    return Object.freeze({push,finish(text){push(text,true);return completion;},cancel(){if(token===serial)stop();}});
  }
  function update(delta){
    let target=0;
    if(playing){analyser.getFloatTimeDomainData(wave);let sum=0;for(const n of wave)sum+=n*n;target=Math.min(1,Math.max(0,(Math.sqrt(sum/wave.length)-.003)*7));}
    level+=(target-level)*(1-Math.exp(-Math.max(0,delta)/(target>level?.035:.17)));if(level<.001)level=0;emit('level',{level});return level;
  }
  window.RaphaelVoice=Object.freeze({prepare,speak,createStream,stop,update,setVolume(value){volume=Math.max(0,Math.min(1,value));if(gain)gain.gain.setTargetAtTime(volume,context.currentTime,.02);},get level(){return level;},get playing(){return playing;}});
  window.addEventListener('pagehide',stop);
})();

