/* Deterministic turn detection and call lifecycle checks; no devices or models. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),wait=ms=>new Promise(r=>setTimeout(r,ms));
const scope={window:{},setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync(path.join(root,'web/live-call.js'),'utf8'),scope);
const {LiveCall,wakeCommand,command}=scope.window.RaphaelLiveCall;
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};}
function harness(){
  const counts={starts:0,stops:0,cancels:0,turns:[],acks:0,errors:[]},texts=[];
  const mic={start:async options=>{assert.equal(options.automatic,true);counts.starts++;return true;},stop:()=>counts.stops++,finish:async()=>{const next=texts.shift();if(next instanceof Error)throw next;return next;}};
  const options={microphone:mic,prepare:async()=>{},language:()=> 'en',cancelTurn:()=>counts.cancels++,onChange:()=>{},onTranscript:()=>{},
    onError:e=>counts.errors.push(e.message),onTurn:async text=>{counts.turns.push(text);return true;},acknowledge:async()=>counts.acks++};
  return{call:new LiveCall(options),counts,texts,options,mic};
}
function recorder(automatic=true){
  const events=[];let Processor;
  const context={Float32Array,sampleRate:16000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:m=>events.push(m)};}},registerProcessor:(_,ctor)=>Processor=ctor};
  vm.runInNewContext(fs.readFileSync(path.join(root,'web/recorder-worklet.js'),'utf8'),context);
  const instance=new Processor({processorOptions:{automatic,pauseSeconds:1.2}});
  const feed=(seconds,volume)=>{for(let frame=0;frame<Math.ceil(seconds*16000/128);frame++){const input=new Float32Array(128);for(let n=0;n<128;n++)input[n]=Math.sin((frame*128+n)*.15)*volume;instance.process([[input]]);}};
  return{events,instance,feed};
}
(async()=>{
  assert.equal(wakeCommand('I was talking about Raphael.'),null);
  assert.equal(wakeCommand('Raphael painted many works of art.'),null);
  assert.equal(wakeCommand('hey Rafael, what is two plus three?').text,'what is two plus three?');
  assert.equal(wakeCommand('Hey Raphael.').text,'');
  assert.equal(wakeCommand('Raphaelite paintings are interesting.'),null);
  assert.equal(command('Please end the call.'),'end');assert.equal(command('Explain what end call means'),null);
  const quiet=recorder();quiet.feed(60,0);
  assert.equal(quiet.events.filter(e=>['samples','utterance','limit'].includes(e.type)).length,0);
  assert.ok(quiet.instance.preCount<=8000);assert.equal(quiet.instance.active,true);
  const noise=recorder();noise.feed(.1,.1);noise.feed(2,0);
  assert.equal(noise.events.filter(e=>['samples','utterance'].includes(e.type)).length,0);
  const turn=recorder();turn.feed(2,0);turn.feed(.9,.1);turn.feed(1.3,0);
  assert.equal(turn.events.filter(e=>e.type==='utterance').length,1);
  const samples=turn.events.filter(e=>e.type==='samples').reduce((n,e)=>n+e.samples.length,0);
  assert.ok(samples>16000&&samples<480000);
  const long=recorder();long.feed(31,.1);
  assert.equal(long.events.filter(e=>e.type==='limit').length,1);
  assert.equal(long.events.filter(e=>e.type==='samples').reduce((n,e)=>n+e.samples.length,0),480000);
  const manual=recorder(false);manual.feed(1,.1);manual.feed(2,0);
  assert.ok(!manual.events.some(e=>e.type==='utterance'));
  const h=harness();await h.call.start();assert.equal(h.call.state,'listening');
  const reply=deferred();h.options.onTurn=async text=>{h.counts.turns.push(text);return reply.promise;};h.texts.push('Hello');
  const finishing=h.call.finish();await wait(0);assert.equal(h.call.state,'replying');assert.equal(h.counts.starts,1);
  reply.resolve(true);await finishing;await wait(500);assert.equal(h.counts.starts,2);assert.equal(h.call.state,'listening');
  h.call.pause();const starts=h.counts.starts;await wait(500);assert.equal(h.counts.starts,starts);assert.equal(h.call.state,'paused');
  await h.call.resume();assert.equal(h.call.state,'listening');
  const recognition=deferred();h.mic.finish=()=>recognition.promise;const cancelled=h.call.finish();h.call.stop();recognition.resolve('Must never reach the AI');await cancelled;
  assert.equal(h.counts.turns.length,1);assert.equal(h.call.state,'off');
  const wake=harness();await wake.call.start(true);assert.equal(wake.call.state,'armed');
  wake.texts.push('A background conversation about dinner.');await wake.call.finish();await wait(150);
  assert.equal(wake.call.mode,'wake');assert.equal(wake.counts.turns.length,0);
  wake.texts.push('Hey Raphael.');await wake.call.finish();assert.equal(wake.counts.acks,1);await wait(500);
  assert.equal(wake.call.mode,'call');assert.equal(wake.call.state,'listening');
  wake.texts.push('go to sleep');await wake.call.finish();await wait(500);assert.equal(wake.call.state,'armed');
  wake.texts.push('Hey Raphael, tell me a joke.');await wake.call.finish();await wait(500);
  assert.deepEqual(wake.counts.turns,['tell me a joke.']);
  wake.texts.push('End call.');await wake.call.finish();assert.equal(wake.call.active,false);
  const interruption=harness();await interruption.call.start();
  const pending=deferred();interruption.options.onTurn=()=>pending.promise;interruption.texts.push('Old turn');
  const old=interruption.call.finish();await wait(0);await interruption.call.interrupt();
  const count=interruption.counts.starts;pending.resolve(true);await old;await wait(500);
  assert.equal(interruption.counts.starts,count);assert.equal(interruption.call.state,'listening');
  const silence=Error('No speech');silence.code='no_speech';interruption.texts.push(silence);await interruption.call.finish();await wait(300);
  assert.equal(interruption.call.state,'listening');assert.equal(interruption.counts.errors.length,0);interruption.call.stop();
  const permission=harness(),grant=deferred();permission.mic.start=()=>grant.promise;
  const opening=permission.call.start();await wait(0);permission.call.stop();grant.resolve(true);await opening;
  assert.equal(permission.call.state,'off');
  const natural=harness(),oldSpeech=deferred();natural.options.bargeIn=()=>true;
  natural.options.onTurn=()=>oldSpeech.promise;await natural.call.start();natural.texts.push('Explain an idea.');
  const naturalTurn=natural.call.finish();await wait(0);assert.equal(natural.call.state,'barge-listening');
  const oldStops=natural.counts.stops,oldCancels=natural.counts.cancels;
  natural.call.speechStarted();assert.equal(natural.call.state,'listening');assert.equal(natural.counts.cancels,oldCancels+1);
  assert.equal(natural.counts.stops,oldStops,'The new utterance must not be discarded');
  const startsAfterInterrupt=natural.counts.starts;oldSpeech.resolve(true);await naturalTurn;await wait(200);
  assert.equal(natural.counts.starts,startsAfterInterrupt,'Late completion must not restart an old turn');natural.call.stop();
  console.log('Passed: bounded silence, automatic endpoints, 30-second cap, manual capture, wake gating, repeat turns, pause/resume, end-call races, interruption, silence retry and late permission.');
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
