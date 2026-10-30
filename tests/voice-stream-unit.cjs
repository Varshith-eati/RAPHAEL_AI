/* Exercise actual voice.js orchestration with simulated WebAudio and localhost replies. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let id=0,played=[],requests=[],cancelled=[],delayed=null,pendingRelease=null;
const data=new Map();
class Audio {
  constructor(){this.currentTime=0;this.destination={};}
  resume(){return Promise.resolve();}
  createGain(){return{gain:{value:1,setTargetAtTime(){}},connect(){}};}
  createAnalyser(){return{fftSize:2048,connect(){},getFloatTimeDomainData(array){array.fill(.1);}};}
  decodeAudioData(buffer){return Promise.resolve({duration:.02,id:buffer.id});}
  createBufferSource(){const source={connect(){},disconnect(){},stop(){clearTimeout(source.timer);},start(){played.push(source.buffer.id);source.timer=setTimeout(()=>source.onended?.(),20);}};return source;}
}
const response=value=>({ok:true,json:async()=>value});
async function fetch(url,options={}){
  if(url==='/api/speak'){
    const key=String(++id),payload=JSON.parse(options.body);requests.push(payload.text);data.set(key,payload.text);
    if(delayed){delayed=false;return new Promise(resolve=>{pendingRelease=()=>resolve(response({id:key}));});}
    return response({id:key});
  }
  if(url.startsWith('/api/jobs/'))return response({state:'ready',audio:'/api/audio/'+url.split('/').at(-1),details:{generation_seconds:.01}});
  if(url.startsWith('/api/audio/'))return{ok:true,arrayBuffer:async()=>({id:url.split('/').at(-1)})};
  if(url.startsWith('/api/cancel/')){cancelled.push(url.split('/').at(-1));return response({state:'cancelled'});}
  throw Error(url);
}
const window={AudioContext:Audio,RaphaelConnection:{token:'test'},dispatchEvent(){},addEventListener(){}};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../web/voice.js'),'utf8'),{window,fetch,AbortSignal,performance,setTimeout,clearTimeout,Float32Array,CustomEvent:class{constructor(name,detail){this.type=name;this.detail=detail;}}});
(async()=>{
  const voice=window.RaphaelVoice;
  const stream=voice.createStream();stream.push('This is the first sentence. ');
  await wait(50);assert.equal(played.length,1,'Speech must start before final text arrives');
  await stream.finish('This is the first sentence. This is the next complete sentence.');
  assert.equal(requests.join(' '),'This is the first sentence. This is the next complete sentence.');
  assert.deepEqual(played,['1','2'],'Phrases play in source order exactly once');
  delayed=true;const late=voice.createStream();late.push('This old reply should never play. ');await wait(0);
  const previous=played.length;voice.stop();pendingRelease();await wait(50);
  assert.equal(played.length,previous);assert.ok(cancelled.includes('3'),'Cancel a late-created speech job');
  const limit=voice.createStream();const before=requests.length;await limit.finish('word '.repeat(900));
  assert.ok(requests.slice(before).reduce((n,text)=>n+text.length,0)<=2400);
  voice.stop();console.log('Passed: early phrase playback, ordered speech, late-job cancellation and bounded text buffering.');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
