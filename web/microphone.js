(() => {
  'use strict';
  let stream, context, input, recorder, silent, frames=[], sampleCount=0, serial=0;
  let state='idle', level=0, seconds=0, jobId=null, flushed=null,inputCompleted=0;
  const emit=(name,detail)=>window.dispatchEvent(new CustomEvent('raphael:mic-'+name,{detail}));
  const setState=value=>{state=value;emit('state',{state:value});};
  const headers=()=>({'X-Raphael-Token':window.RaphaelConnection?.token||''});
  async function json(path,body){
    const response=await fetch(path,{headers:{...headers(),'Content-Type':'application/json'},
      ...(body?{method:'POST',body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'The local microphone connection failed.');return result;
  }
  function release(){
    stream?.getTracks().forEach(track=>track.stop());stream=null;
    if(recorder){recorder.port.onmessage=null;recorder.disconnect();recorder=null;}
    input?.disconnect();input=null;silent?.disconnect();silent=null;
    if(context){context.close().catch(()=>{});context=null;}
    if(flushed){flushed();flushed=null;}
    level=0;emit('level',{level:0,seconds});
  }
  function stop(){
    serial++;release();frames=[];sampleCount=0;seconds=0;
    if(jobId){json('/api/cancel/'+jobId,{}).catch(()=>{});jobId=null;}
    setState('idle');
  }
  function messageFor(error){
    if(error.name==='NotAllowedError'||error.name==='SecurityError')return 'Microphone permission is blocked. Allow the microphone in your browser’s site settings, then try again.';
    if(error.name==='NotFoundError')return 'No microphone was found. Connect one or enable your built-in microphone.';
    if(error.name==='NotReadableError')return 'The microphone could not open. Check Windows microphone privacy settings and whether another app is using it.';
    return error.message||'The microphone could not start.';
  }
  async function start(options={}){
    stop();const token=serial;
    inputCompleted=0;
    if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia)throw Error('Open Raphael at http://127.0.0.1:8768 in Chrome or Edge to use the microphone.');
    setState('requesting');
    try{
      const granted=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
      if(token!==serial){granted.getTracks().forEach(track=>track.stop());return false;}
      stream=granted;
      const Audio=window.AudioContext||window.webkitAudioContext;
      if(!Audio)throw Error('This browser does not support audio recording. Use Chrome or Edge.');
      try{context=new Audio({sampleRate:16000});}catch{context=new Audio();}
      const ownedContext=context;
      await ownedContext.resume();if(token!==serial)return false;
      if(!ownedContext.audioWorklet)throw Error('This browser cannot record audio locally. Use a current Chrome or Edge browser.');
      await ownedContext.audioWorklet.addModule('/recorder-worklet.js');if(token!==serial)return false;
      input=ownedContext.createMediaStreamSource(granted);
      recorder=new AudioWorkletNode(ownedContext,'raphael-recorder',{processorOptions:{automatic:!!options.automatic,pauseSeconds:options.pauseSeconds||.9,sensitivity:options.sensitivity??.55}});
      silent=ownedContext.createGain();silent.gain.value=0;
      recorder.port.onmessage=event=>{
        if(token!==serial)return;
        const data=event.data;
        if(data.type==='samples'){
          frames.push(data.samples);sampleCount+=data.samples.length;
          let power=0;for(const value of data.samples)power+=value*value;
          level=Math.min(1,Math.sqrt(power/data.samples.length)*7);seconds=sampleCount/ownedContext.sampleRate;
          emit('level',{level,seconds});
        }else if(data.type==='meter'){level=data.level;seconds=data.seconds;emit('level',{level,seconds});}
        else if(data.type==='discard'){frames=[];sampleCount=0;seconds=0;}
        else if(data.type==='utterance'){inputCompleted=performance.now()-(data.endpoint_seconds||0)*1000;json('/api/performance',{stage:'vad_endpoint',seconds:data.endpoint_seconds||0,kind:'browser'}).catch(()=>{});emit('utterance',{});}
        else if(data.type==='speech')emit('speech',{});
        else if(data.type==='flushed'){if(flushed){flushed();flushed=null;}}
        else if(data.type==='limit')emit('limit',{});
      };
      input.connect(recorder);recorder.connect(silent);silent.connect(ownedContext.destination);
      granted.getAudioTracks()[0].onended=()=>{if(token===serial&&state==='recording'){stop();emit('error',{message:'The microphone disconnected. Reconnect it and try again.'});}};
      setState('recording');return true;
    }catch(error){if(token!==serial)return false;stop();throw Error(messageFor(error));}
  }
  function wav(rate){
    const all=new Float32Array(sampleCount);let offset=0;
    for(const frame of frames){all.set(frame,offset);offset+=frame.length;}
    const count=Math.min(480000,Math.floor(all.length*16000/rate));
    if(count<4000)throw Error('Speak for at least a moment before choosing Finish & send.');
    const buffer=new ArrayBuffer(44+count*2),view=new DataView(buffer);
    const ascii=(at,text)=>{for(let i=0;i<text.length;i++)view.setUint8(at+i,text.charCodeAt(i));};
    ascii(0,'RIFF');view.setUint32(4,36+count*2,true);ascii(8,'WAVE');ascii(12,'fmt ');
    view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
    view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
    ascii(36,'data');view.setUint32(40,count*2,true);
    for(let i=0;i<count;i++){
      const begin=Math.floor(i*rate/16000),end=Math.max(begin+1,Math.floor((i+1)*rate/16000));
      let value=0;for(let j=begin;j<end&&j<all.length;j++)value+=all[j];
      value=Math.max(-1,Math.min(1,value/(end-begin)));
      view.setInt16(44+i*2,value<0?Math.round(value*32768):Math.round(value*32767),true);
    }
    return new Blob([buffer],{type:'audio/wav'});
  }
  async function finish(language='en'){
    if(state!=='recording')return null;
    if(!inputCompleted)inputCompleted=performance.now();
    const token=serial,rate=context.sampleRate;setState('transcribing');
    // Release the physical microphone immediately, before recognition starts.
    stream?.getTracks().forEach(track=>track.stop());
    try{
      await new Promise(resolve=>{flushed=resolve;recorder.port.postMessage('flush');setTimeout(resolve,400);});
      if(token!==serial)return null;
      const audio=wav(rate);release();frames=[];sampleCount=0;
      const response=await fetch('/api/transcribe',{method:'POST',headers:{...headers(),'Content-Type':'audio/wav','X-Raphael-Language':language},body:audio,signal:AbortSignal.timeout(15000)});
      const job=await response.json();
      if(!response.ok)throw Error(job.error||'The recording could not be read.');
      if(token!==serial){json('/api/cancel/'+job.id,{}).catch(()=>{});return null;}
      jobId=job.id;const deadline=Date.now()+240000;
      while(token===serial&&Date.now()<deadline){
        const result=await json('/api/jobs/'+job.id);if(token!==serial)return null;
        if(result.text)emit('transcript',{text:result.text,complete:result.state==='ready'});
        if(result.state==='error'){const error=Error(result.error);error.code=result.code;throw error;}
        if(result.state==='cancelled'){stop();return null;}
        if(result.state==='ready'){jobId=null;setState('idle');return result.text;}
        await new Promise(resolve=>setTimeout(resolve,80));
      }
      if(token===serial)throw Error('Speech recognition took too long. Try a shorter recording.');
      return null;
    }catch(error){if(token!==serial)return null;stop();throw error;}
  }
  window.RaphaelMicrophone=Object.freeze({start,finish,stop,get inputCompleted(){return inputCompleted;},get state(){return state;},get level(){return level;},get seconds(){return seconds;}});
  window.addEventListener('pagehide',stop);
})();
