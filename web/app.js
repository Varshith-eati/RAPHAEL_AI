(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  const media=window.matchMedia('(prefers-reduced-motion: reduce)');
  const settings={palette:'sage',glow:.7,speed:1,particles:true,reduced:media.matches};
  const voice=window.RaphaelVoice;
  const microphone=window.RaphaelMicrophone;
  const stateCopy={
    idle:{label:'RAPHAEL IS READY',title:'How can I help you?',subtitle:'A thought, a question, a possibility. Start anywhere.',caption:'AWAITING YOUR INTENT'},
    listening:{label:'MICROPHONE IS ON',title:'You have my attention.',subtitle:'Speak, then choose Finish & send.',caption:'LISTENING ON THIS COMPUTER'},
    thinking:{label:'RAPHAEL IS THINKING',title:'Connecting the possibilities.',subtitle:'Thinking here, on your computer.',caption:'THOUGHT TAKING SHAPE'},
    speaking:{label:'RAPHAEL IS SPEAKING',title:'A little clarity.',subtitle:'The light follows the sound of the voice.',caption:'RESONANCE IN MOTION'}
  };
  let currentState='idle',dirty=true,busy=false,serial=0,chatJob=null,activeAssistant=null,activeUser=null,toastTimer,openPanel=null,dialogOpener=null;
  let messages=[],service=null,liveCall=null,interaction={},turnStarted=0,firstAudioRecorded=false;
  const prefKey='raphael-local-stage2';
  let profileReady=false,memoryBusy=false;
  let prefs={name:'',notes:[],voice:'heart',speed:1,volume:.65,autoSpeak:true,model:'qwen3.5:4b'};
  try{const saved=JSON.parse(localStorage.getItem(prefKey)||'{}');prefs={...prefs,...saved};}catch{}
  if(typeof prefs.name!=='string')prefs.name='';prefs.name=prefs.name.slice(0,60);
  if(!Array.isArray(prefs.notes))prefs.notes=[];prefs.notes=prefs.notes.filter(n=>typeof n==='string').slice(0,12).map(n=>n.slice(0,500));
  if(!['heart','bella','sarah'].includes(prefs.voice))prefs.voice='heart';
  prefs.speed=Math.min(1.2,Math.max(.8,Number(prefs.speed)||1));prefs.volume=Math.min(1,Math.max(0,Number.isFinite(prefs.volume)?prefs.volume:.65));prefs.autoSpeak=prefs.autoSpeak!==false;
  if(!['text','spoken','conversation'].includes(prefs.mode))prefs.mode=prefs.autoSpeak?'spoken':'text';
  if(!['en','hi','auto'].includes(prefs.inputLanguage))prefs.inputLanguage='en';
  if(![1.2,2].includes(prefs.callPause))prefs.callPause=1.2;
  prefs.autoSpeak=prefs.mode!=='text';
  let bootstrap=null;
  try{const parameters=new URLSearchParams(location.hash.slice(1));bootstrap=parameters.get('session')||sessionStorage.getItem('raphael-session');if(parameters.has('session')){sessionStorage.setItem('raphael-session',bootstrap);history.replaceState(null,'',location.pathname+location.search);}}catch{}
  window.RaphaelConnection={token:bootstrap};
  const laptop=new window.RaphaelLaptop({api,notify:showToast,
    onResult:text=>{addMessage('assistant',text);showToast(text.length>180?'Results added to Conversation.':text);},
    onPending:()=>{if(liveCall?.active)liveCall.pause('Review the laptop request. Resume when ready.');showPanel('laptop');}});
  function savePrefs(){try{const {name,notes,...browserSettings}=prefs;localStorage.setItem(prefKey,JSON.stringify(browserSettings));}catch{showToast('Browser storage is unavailable. Voice settings will last only for this tab.');}}
  function showToast(text){$('toast').textContent=text;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),4500);}
  function setState(state){
    if(!stateCopy[state])return;currentState=state;document.body.dataset.state=state;const copy=stateCopy[state];
    $('statusLabel').textContent=copy.label;$('greeting').textContent=copy.title;$('subtitle').textContent=copy.subtitle;$('coreCaption').textContent=copy.caption;
    document.querySelectorAll('[data-state-option]').forEach(button=>{const selected=button.dataset.stateOption===state;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});dirty=true;
  }
  function setBusy(value){busy=value;$('stopButton').hidden=!value||!!liveCall?.active;$('suggestions').hidden=value;$('demoButton').querySelector('span').textContent=value?'Stop':'Hear Raphael';$('demoButton').querySelector('use').setAttribute('href',value?'#i-stop':'#i-play');$('demoButton').querySelector('.duration').textContent=value?'ACTIVE':'SOFT VOICE';}
  async function api(path,body){
    const response=await fetch(path,{headers:{'Content-Type':'application/json','X-Raphael-Token':window.RaphaelConnection.token||''},...(body?{method:'POST',body:JSON.stringify(body)}:{}),cache:'no-store',signal:AbortSignal.timeout(path==='/api/laptop/system'?20000:12000)});
    const data=await response.json();if(!response.ok)throw Error(data.error||'The local connection was interrupted.');return data;
  }
  function showReply(text){$('replyPreview').textContent=text;$('replyPreview').hidden=!text;}
  function updateMessage(message,text,status){
    message.content=text;message.status=status;
    message.paragraph.textContent=text||'Thinking…';message.badge.textContent=status==='complete'?message.model||'LOCAL':status==='streaming'?'WRITING…':status==='cancelled'?'STOPPED · PARTIAL':status==='error'?'COULD NOT FINISH':status==='pending'?'THIS TURN':'YOU';
    if(message.readButton)message.readButton.disabled=status!=='complete';
    message.element.classList.toggle('pending',status==='streaming');
    if(openPanel==='conversation')message.element.scrollIntoView({block:'nearest'});
  }
  function addMessage(role,text,status='complete'){
    if(messages.length===0)$('conversationList').replaceChildren();
    const element=document.createElement('article');element.className='chat-message '+role;
    const header=document.createElement('header');header.append(document.createTextNode(role==='user'?'YOU':'RAPHAEL'));
    const badge=document.createElement('span');header.append(badge);const paragraph=document.createElement('p');element.append(header,paragraph);
    const message={role,content:text,status,element,paragraph,badge,model:role==='assistant'?prefs.model:''};
    if(role==='assistant'){
      const actions=document.createElement('div');actions.className='message-actions';
      const read=document.createElement('button');read.textContent='Read aloud';read.addEventListener('click',()=>speakManually(message.content));
      const copy=document.createElement('button');copy.textContent='Copy';copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(message.content);showToast('Reply copied.');}catch{showToast('Select the reply text to copy it.');}});
      actions.append(read,copy);element.append(actions);message.readButton=read;
    }
    messages.push(message);$('conversationList').append(element);updateMessage(message,text,status);$('conversationCount').hidden=false;$('conversationCount').textContent=String(messages.length);return message;
  }
  const emptyConversation=$('conversationList').innerHTML;
  function stopWork(notify=false,keepCall=false,keepMicrophone=false){
    if(service?.desktop)api('/api/desktop',{action:'text_end'}).catch(()=>{});
    if(!keepCall&&liveCall?.active)liveCall.stop(false);
    serial++;if(!keepMicrophone)microphone.stop();voice.stop();
    if(chatJob){api('/api/cancel/'+chatJob,{}).catch(()=>{});chatJob=null;}
    if(activeAssistant&&activeAssistant.status==='streaming')updateMessage(activeAssistant,activeAssistant.content||'Reply stopped.', 'cancelled');
    if(activeUser&&activeUser.status==='pending')activeUser.status='cancelled';
    activeAssistant=null;activeUser=null;setBusy(false);setState('idle');$('voiceProgress').textContent='Stopped. No pending voice will play.';
    if(notify)showToast('Stopped.');
  }
  async function speakForTurn(text,token){
    if(token!==serial)return;
    if(service?.voice!=='ready')throw Error('Voice is not ready yet. Your text reply is available; check Voice settings.');
    setState('thinking');$('statusLabel').textContent='PREPARING HER VOICE';
    const spoken=text.length>2400?text.slice(0,2350)+' The rest of the reply is shown in the conversation.':text;
    await voice.speak(spoken,prefs.voice,prefs.speed);
  }
  async function speakManually(text){
    if(!text.trim())return;
    stopWork();const token=serial;setBusy(true);showReply(text);
    try{await voice.prepare();if(service?.voice!=='ready')throw Error('Start Launch-Raphael.cmd and wait for the voice to be ready.');await speakForTurn(text,token);}
    catch(error){if(token===serial){$('voiceProgress').textContent=error.message;showToast(error.message);}}
    finally{if(token===serial){setBusy(false);setState('idle');}}
  }
  function historyForRequest(text){
    const history=messages.filter(m=>m.status==='complete'||(m.status==='cancelled'&&m.content&&m.content!=='Reply stopped.'))
      .map(m=>({role:m.role,content:(m.role==='assistant'&&m.status==='cancelled'?'[Interrupted response; incomplete] '+m.content:m.content).slice(0,6000)}));
    const before=history.length;
    let characters=history.reduce((n,m)=>n+m.content.length,0)+text.length;
    while(history.length&&(history.length>24||characters>8000)){
      characters-=history.shift().content.length;
      if(history[0]?.role==='assistant')characters-=history.shift().content.length;
    }
    while(history[0]?.role==='assistant')history.shift();
    const trimmed=history.length<before;
    if(trimmed&&$('contextNotice').hidden)showToast('This chat is getting longer. Raphael will use the latest messages; save lasting preferences in Memory.');
    $('contextNotice').hidden=!trimmed;
    return [...history,{role:'user',content:text}];
  }
  async function sendMessage(text,{live=false,inputStarted=0}={}){
    text=text.trim();if(!text)return;
    if(text.length>6000){showToast('Please shorten this message to 6,000 characters or fewer.');return;}
    if(service?.chat!=='ready'){showToast('Open Launch-Raphael.cmd and wait for the local model connection.');showPanel('connection');return;}
    stopWork(false,live);const token=serial;const history=historyForRequest(text);setBusy(true);setState('thinking');showReply('');$('messageInput').value='';
    turnStarted=inputStarted||performance.now();firstAudioRecorded=false;let firstText=false;
    if(service?.desktop)api('/api/desktop',{action:'text_start'}).catch(()=>{});
    const speech=(prefs.autoSpeak||live)&&interaction.speech_streaming!==false&&service?.voice==='ready'&&voice.createStream?voice.createStream(prefs.voice,prefs.speed):null;
    const userMessage=addMessage('user',text,'pending');const reply=addMessage('assistant','','streaming');activeUser=userMessage;activeAssistant=reply;
    if(prefs.autoSpeak||live){try{voice.prepare().catch(()=>{});}catch{}}
    try{
      const job=await api('/api/chat',{model:prefs.model,messages:history});
      if(token!==serial){api('/api/cancel/'+job.id,{}).catch(()=>{});return;}chatJob=job.id;
      const deadline=Date.now()+300000;
      while(token===serial&&Date.now()<deadline){
        const status=await api('/api/jobs/'+job.id);if(token!==serial)return;
        if(status.details?.progress&&!voice.playing)$('statusLabel').textContent=status.details.progress;
        if(status.text!==reply.content){
          if(!firstText&&status.text){firstText=true;api('/api/performance',{stage:'input_to_first_text',seconds:(performance.now()-turnStarted)/1000,kind:'browser'}).catch(()=>{});}
          updateMessage(reply,status.text,'streaming');showReply(status.text);if(!voice.playing)$('statusLabel').textContent='RAPHAEL IS REPLYING';speech?.push(status.text);
        }
        if(status.state==='error')throw Error(status.error||'The model could not finish this reply.');
        if(status.state==='cancelled'){stopWork();return;}
        if(status.state==='ready'){
          chatJob=null;updateMessage(reply,status.text,'complete');userMessage.status='complete';userMessage.badge.textContent='YOU';activeAssistant=null;activeUser=null;
          if(status.details?.truncated)showToast('This reply reached its length limit. Ask “continue” for more.');
          if(status.details?.approvals?.length){speech?.cancel();setBusy(false);setState('idle');await laptop.receive();return false;}
          let completed=true;
          if(prefs.autoSpeak||live){try{if(speech)await speech.finish(status.text);else await speakForTurn(status.text,token);}catch(error){completed=false;if(token===serial){$('voiceProgress').textContent=error.message;showToast('Your text reply is ready. '+error.message);}}}
          api('/api/performance',{stage:'input_to_complete',seconds:(performance.now()-turnStarted)/1000,kind:'browser'}).catch(()=>{});
          if(service?.desktop)api('/api/desktop',{action:'text_end'}).catch(()=>{});
          if(token===serial){setBusy(live&&!!liveCall?.active);setState('idle');}return completed&&token===serial;
        }
        await new Promise(resolve=>setTimeout(resolve,160));
      }
      if(token===serial)throw Error('The model took too long. Try a shorter question or choose the other local model.');
    }catch(error){
      if(token!==serial)return;
      speech?.cancel();
      if(chatJob){api('/api/cancel/'+chatJob,{}).catch(()=>{});chatJob=null;}
      updateMessage(reply,reply.content||error.message,'error');userMessage.status='error';activeAssistant=null;activeUser=null;setBusy(false);setState('idle');showReply(reply.content);showToast(error.message);
      return false;
    }
  }
  function showPanel(panel,opener){
    if(!['appearance','conversation','memory','voice','connection','laptop'].includes(panel))return;openPanel=panel;dialogOpener=opener||document.activeElement;
    for(const name of ['appearance','conversation','memory','voice','connection','laptop'])$(name+'Panel').hidden=name!==panel;
    $('drawerTitle').textContent={appearance:'Appearance',conversation:'Conversation',memory:'Memory & preferences',voice:'Voice & sound',connection:'Connection',laptop:'Laptop access'}[panel];
    $('drawerEyebrow').textContent={appearance:'YOUR RAPHAEL',conversation:'A SPACE FOR YOUR THOUGHTS',memory:'ONLY WHAT YOU CHOOSE TO KEEP',voice:'A VOICE FOR RAPHAEL',connection:'LOCAL BY CHOICE',laptop:'YOU STAY IN CONTROL'}[panel];
    if(panel==='laptop')laptop.refresh();
    if(!$('detailDialog').open)$('detailDialog').showModal();$('closeDrawer').focus();
  }
  function closePanel(){if($('detailDialog').open)$('detailDialog').close();}
  $('detailDialog').addEventListener('close',()=>{openPanel=null;if(dialogOpener?.isConnected)dialogOpener.focus();});
  $('detailDialog').addEventListener('cancel',()=>{if(busy)stopWork();});
  $('detailDialog').addEventListener('click',event=>{if(event.target===$('detailDialog')){const r=$('detailDialog').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closePanel();}});
  document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>showPanel(button.dataset.panel,button)));
  $('closeDrawer').addEventListener('click',closePanel);$('backToComposer').addEventListener('click',()=>{closePanel();$('messageInput').focus();});
  $('homeButton').addEventListener('click',event=>{event.preventDefault();stopWork();showReply('');closePanel();});$('coreNav').addEventListener('click',()=>{closePanel();});
  $('commandForm').addEventListener('submit',event=>{event.preventDefault();sendMessage($('messageInput').value);});
  document.querySelectorAll('[data-prompt]').forEach(button=>button.addEventListener('click',()=>sendMessage(button.dataset.prompt)));
  $('clearConversation').addEventListener('click',()=>{stopWork();messages=[];$('conversationList').innerHTML=emptyConversation;$('conversationCount').hidden=true;$('contextNotice').hidden=true;$('heardText').hidden=true;$('heardText').textContent='';showReply('');showToast('Conversation cleared. Saved preferences are unchanged.');});
  $('stopButton').addEventListener('click',()=>stopWork(true));$('stopVoice').addEventListener('click',()=>stopWork(true));
  const greeting="Hello. I'm here with you. What would you like to talk about today?";
  $('demoButton').addEventListener('click',()=>{closePanel();if(busy)stopWork(true);else speakManually(greeting);});
  function renderMode(){
    $('autoSpeak').checked=prefs.autoSpeak;
    $('replyVoiceToggle').setAttribute('aria-pressed',String(prefs.autoSpeak));
    $('replyVoiceValue').textContent=prefs.autoSpeak?'On':'Off';
    $('messageInput').placeholder='Ask Raphael anything…';
  }
  function setMode(mode){stopWork();prefs.mode=mode;prefs.autoSpeak=mode!=='text';savePrefs();renderMode();}
  $('replyVoiceToggle').addEventListener('click',()=>setMode(prefs.autoSpeak?'text':'spoken'));
  function micDisplay(){
    const recording=microphone.state==='recording',requesting=microphone.state==='requesting',transcribing=microphone.state==='transcribing';
    const active=recording||requesting||transcribing;
    $('microphoneControls').hidden=!active||!!liveCall?.active;
    const label=recording?'Finish & send':requesting?'Waiting for permission…':transcribing?'Recognizing speech…':'Start microphone';
    $('micToggle').querySelector('span').textContent=label;$('micToggle').disabled=requesting||transcribing;
    $('startMicFromSettings').textContent=label;$('startMicFromSettings').disabled=requesting||transcribing;
    $('voiceButton').disabled=requesting||transcribing;$('voiceButton').setAttribute('aria-pressed',String(recording));
    $('voiceButton').setAttribute('aria-label',recording?'Finish recording and send':'Start microphone');$('voiceButton').title=recording?'Finish recording and send':'Start microphone';
    $('micConnection').textContent=recording?(liveCall?.mode==='wake'?'On · wake listening':'On · listening'):requesting?'Permission needed':transcribing?'Off · recognizing':liveCall?.active?(liveCall.muted?'Muted':'Off · during reply'):'Off · tap mic to start';
    if(recording)$('microphoneStatus').textContent='Listening · '+Math.floor(microphone.seconds)+' / 30 seconds';
    else if(requesting)$('microphoneStatus').textContent='Allow microphone access in your browser.';
    else if(transcribing)$('microphoneStatus').textContent='Microphone off · recognizing on this computer…';
    else $('microphoneStatus').textContent='Microphone is off. Start it when you are ready.';
    document.body.classList.toggle('microphone-active',recording);
  }
  function microphoneError(message){$('microphoneControls').hidden=false;$('microphoneStatus').textContent=message;showToast(message);}
  async function finishMicrophone(){
    if(microphone.state!=='recording')return;
    const token=serial;setState('thinking');$('statusLabel').textContent='RECOGNIZING YOUR SPEECH';
    try{
      const text=await microphone.finish(prefs.inputLanguage);if(token!==serial||!text)return;
      $('heardText').textContent='You said: '+text;$('heardText').hidden=false;
      // The physical microphone is already off before the AI or voice starts.
      await sendMessage(text);
    }catch(error){if(token===serial){stopWork();microphoneError(error.message);}}
  }
  async function toggleMicrophone(){
    if(liveCall?.active){if(microphone.state==='recording')await liveCall.finish();else if(liveCall.muted)await liveCall.resume();else await liveCall.interrupt();return;}
    if(microphone.state==='recording'){await finishMicrophone();return;}
    if(microphone.state!=='idle')return;
    if(service?.transcription!=='ready'){showToast(service?.transcription_error||'Local speech recognition is still loading. Check Voice settings.');showPanel('voice');return;}
    if(service?.chat!=='ready'){showToast('Wait for the local AI to be ready, then try the microphone.');return;}
    if(prefs.mode!=='conversation')setMode('conversation');else stopWork();
    const token=serial;setBusy(true);$('heardText').hidden=true;showReply('');
    // Unlock output audio inside the user gesture for the later spoken reply.
    try{voice.prepare().catch(()=>{});}catch{}
    try{const ready=await microphone.start();if(token===serial&&ready)setState('listening');}
    catch(error){if(token===serial){stopWork();microphoneError(error.message);}}
  }
  $('voiceButton').addEventListener('click',toggleMicrophone);$('micToggle').addEventListener('click',toggleMicrophone);
  $('startMicFromSettings').addEventListener('click',()=>{closePanel();toggleMicrophone();});
  $('inputLanguage').value=prefs.inputLanguage;$('inputLanguage').addEventListener('change',event=>{stopWork();prefs.inputLanguage=event.target.value;savePrefs();});
  $('readTypedText').addEventListener('click',()=>{const text=$('messageInput').value.trim();if(text)speakManually(text);else{$('messageInput').focus();showToast('Type something in the message box to read it aloud.');}});
  window.addEventListener('raphael:mic-state',micDisplay);
  window.addEventListener('raphael:mic-level',event=>{$('microphoneMeter').style.transform=`scaleX(${event.detail.level})`;if(microphone.state==='recording')micDisplay();});
  window.addEventListener('raphael:mic-limit',()=>liveCall?.active?liveCall.finish():finishMicrophone());
  window.addEventListener('raphael:mic-utterance',()=>{if(liveCall?.active)liveCall.finish();});
  window.addEventListener('raphael:mic-speech',()=>liveCall?.speechStarted());
  window.addEventListener('raphael:mic-transcript',event=>{if(liveCall?.mode==='wake')return;$('heardText').hidden=false;$('heardText').textContent=(event.detail.complete?'You said: ':'Hearing: ')+event.detail.text;});
  window.addEventListener('raphael:mic-error',event=>{stopWork();microphoneError(event.detail.message);});
  document.querySelectorAll('[data-state-option]').forEach(button=>button.addEventListener('click',()=>{closePanel();if(button.dataset.stateOption==='listening'){toggleMicrophone();return;}if(button.dataset.stateOption==='speaking'){speakManually(greeting);return;}stopWork();setState(button.dataset.stateOption);}));
  $('speakText').addEventListener('click',()=>speakManually($('speakInput').value));
  $('referenceSelect').value=prefs.voice;$('referenceSelect').addEventListener('change',event=>{voice.stop();prefs.voice=event.target.value;savePrefs();});
  $('autoSpeak').checked=prefs.autoSpeak;$('autoSpeak').addEventListener('change',event=>setMode(event.target.checked?(prefs.mode==='conversation'?'conversation':'spoken'):'text'));
  renderMode();micDisplay();
  function callDisplay({state,mode,muted,wakeEnabled,message}){
    const active=mode!=='off';
    $('callControls').hidden=!active;$('enableWake').checked=wakeEnabled;
    $('callButton').hidden=mode==='call';
    $('callButton').setAttribute('aria-pressed',String(mode==='call'));
    $('callButton').querySelector('span').textContent=mode==='call'?'End call':'Call Raphael';
    $('callButton').setAttribute('aria-label',mode==='call'?'End voice call':'Start a voice call');
    $('startCallFromSettings').textContent=mode==='call'?'End call':'Call Raphael';
    $('callTitle').textContent=mode==='wake'?'Wake listening · local':'Voice call · local';
    $('callStatus').textContent=message||({connecting:'Opening your microphone…',armed:'Say “Hey Raphael” to wake me.',listening:'Speak naturally. Pause when you are done.',checking:'Checking the wake phrase locally…',recognizing:'Understanding your words…',replying:'Microphone off during the reply.',paused:'Microphone off. Resume when ready.',off:''}[state]||'');
    $('muteCall').textContent=muted?'Resume':'Mute';$('muteCall').setAttribute('aria-pressed',String(muted));
    $('endCall').textContent=mode==='wake'?'Turn off':'End call';
    $('interruptCall').hidden=!['replying','recognizing','barge-listening'].includes(state);
    document.body.dataset.callState=state;micDisplay();
    if(active){
      setBusy(true);
      if(['armed','listening'].includes(state)){
        setState('listening');$('statusLabel').textContent=state==='armed'?'WAKE LISTENING IS ON':'RAPHAEL IS LISTENING';
        $('subtitle').textContent=state==='armed'?'Say “Hey Raphael” when you need me.':'Speak naturally. I will answer when you pause.';
      }else if(state==='paused'){setState('idle');$('statusLabel').textContent='CALL PAUSED · MICROPHONE OFF';}
      else if(['checking','recognizing'].includes(state)){setState('thinking');$('statusLabel').textContent=state==='checking'?'CHECKING THE WAKE PHRASE':'RECOGNIZING YOUR SPEECH';}
    }else{setBusy(false);setState('idle');}
  }
  async function prepareCall(){
    if(!service||['chat','voice','transcription'].some(key=>service[key]!=='ready'))throw Error('Wait for the local AI, voice, and speech recognition to be ready. Check Voice settings.');
    if(prefs.volume===0)throw Error('Raise the voice volume in Voice settings before starting a call.');
    prefs.mode='conversation';prefs.autoSpeak=true;savePrefs();renderMode();
    await voice.prepare();
    if(service?.desktop)await api('/api/desktop',{action:'mute'});
  }
  liveCall=new window.RaphaelLiveCall.LiveCall({microphone,prepare:prepareCall,language:()=>prefs.inputLanguage,pauseSeconds:()=>interaction.silence_seconds??prefs.callPause,
    sensitivity:()=>interaction.vad_sensitivity??.55,bargeIn:()=>interaction.barge_in===true,
    cancelTurn:keepMic=>stopWork(false,true,keepMic===true),onChange:callDisplay,onError:error=>showToast(error.message),
    onTranscript:text=>{$('heardText').textContent='You said: '+text;$('heardText').hidden=false;},
    onTurn:(text,timing)=>sendMessage(text,{live:true,...timing}),
    acknowledge:async()=>{setBusy(true);showReply("I'm here. What would you like to talk about?");await speakForTurn("I'm here. What would you like to talk about?",serial);}
  });
  function toggleCall(){closePanel();if(liveCall.mode==='call')stopWork();else{stopWork();showReply('');$('heardText').hidden=true;liveCall.start();}}
  $('callButton').addEventListener('click',toggleCall);$('startCallFromSettings').addEventListener('click',toggleCall);
  $('muteCall').addEventListener('click',()=>liveCall.muted?liveCall.resume():liveCall.pause());
  $('endCall').addEventListener('click',()=>stopWork(true));$('interruptCall').addEventListener('click',()=>liveCall.interrupt());
  $('enableWake').addEventListener('change',event=>{const enabled=event.target.checked;stopWork();if(enabled){closePanel();showReply('');liveCall.start(true);}});
  $('callPause').value=String(prefs.callPause);$('callPause').addEventListener('change',async event=>{prefs.callPause=Number(event.target.value);savePrefs();try{interaction=await api('/api/interaction',{silence_seconds:prefs.callPause});$('endpointSilence').value=String(prefs.callPause);}catch(error){showToast(error.message);}});
  window.addEventListener('pagehide',()=>liveCall.stop());
  $('voiceSpeed').value=Math.round(prefs.speed*100);$('voiceSpeedValue').value=prefs.speed.toFixed(2)+'×';
  $('voiceSpeed').addEventListener('input',event=>{prefs.speed=Number(event.target.value)/100;$('voiceSpeedValue').value=prefs.speed.toFixed(2)+'×';savePrefs();});
  $('voiceVolume').value=Math.round(prefs.volume*100);$('voiceVolumeValue').value=Math.round(prefs.volume*100)+'%';voice.setVolume(prefs.volume);
  $('voiceVolume').addEventListener('input',event=>{prefs.volume=Number(event.target.value)/100;voice.setVolume(prefs.volume);$('voiceVolumeValue').value=event.target.value+'%';savePrefs();});
  window.addEventListener('raphael:voice-start',event=>{if(!busy)return;setState('speaking');$('voiceProgress').textContent=`Speaking · ${event.detail.generation_seconds.toFixed(1)}s to prepare · generated locally`;if(turnStarted&&!firstAudioRecorded){firstAudioRecorded=true;api('/api/performance',{stage:'input_to_first_audio',seconds:(performance.now()-turnStarted)/1000,kind:'browser'}).catch(()=>{});}});
  window.addEventListener('raphael:voice-progress',event=>{$('voiceProgress').textContent=event.detail.message;});
  window.addEventListener('raphael:voice-level',event=>{$('audioMeterFill').style.transform=`scaleX(${event.detail.level})`;$('playbackLevel').textContent=Math.round(event.detail.level*100)+'%';});
  function renderNotes(){
    $('memoryEmpty').hidden=prefs.notes.length>0;$('memoryList').replaceChildren();
    prefs.notes.forEach((text,index)=>{const card=document.createElement('div');card.className='memory-item';const p=document.createElement('p');p.textContent=text;const button=document.createElement('button');button.className='icon-button';button.textContent='×';button.setAttribute('aria-label','Forget preference: '+text.slice(0,60));button.addEventListener('click',async()=>{if(await saveProfile({name:prefs.name,notes:prefs.notes.filter((_,i)=>i!==index)})){ $('memoryInput').focus();showToast('Preference forgotten.');}});card.append(p,button);$('memoryList').append(card);});
  }
  function memoryControls(){document.querySelectorAll('#memoryPanel input,#memoryPanel textarea,#memoryPanel button').forEach(el=>el.disabled=!profileReady||memoryBusy);}
  async function saveProfile(profile){
    if(!profileReady||memoryBusy){showToast('Wait for the local memory connection.');return false;}
    memoryBusy=true;memoryControls();
    try{const saved=await api('/api/profile',profile);prefs.name=saved.name;prefs.notes=saved.notes;$('preferredName').value=prefs.name;renderNotes();return true;}
    catch(error){showToast('Could not save your preference. '+error.message);return false;}
    finally{memoryBusy=false;memoryControls();}
  }
  $('preferredName').value=prefs.name;$('saveName').addEventListener('click',async()=>{if(await saveProfile({name:$('preferredName').value.trim(),notes:prefs.notes}))showToast(prefs.name?'Preferred name saved.':'Preferred name removed.');});
  $('memoryForm').addEventListener('submit',async event=>{event.preventDefault();const value=$('memoryInput').value.trim();if(!value)return;if(prefs.notes.length>=12){showToast('Remove a preference before adding another.');return;}if(await saveProfile({name:prefs.name,notes:[...prefs.notes,value]})){$('memoryInput').value='';showToast('Preference saved on this computer.');}});renderNotes();memoryControls();
  $('modelSelect').addEventListener('change',event=>{stopWork();prefs.model=event.target.value;savePrefs();$('chatConnection').textContent=prefs.model;showToast('Local model changed. Conversation context is kept.');});
  const interactionFields={streamReplies:'response_streaming',streamSpeech:'speech_streaming',bargeIn:'barge_in',routeModels:'model_routing',performanceLogs:'diagnostics'};
  let interactionLoaded=false;
  function renderInteraction(){
    for(const [id,key] of Object.entries(interactionFields))$(id).checked=!!interaction[key];
    $('endpointSilence').value=String(interaction.silence_seconds||.9);
    $('activateDesktop').hidden=!service?.desktop;
  }
  $('realtimeSettings').addEventListener('submit',async event=>{
    event.preventDefault();stopWork();
    const values=Object.fromEntries(Object.entries(interactionFields).map(([id,key])=>[key,$(id).checked]));
    values.silence_seconds=Number($('endpointSilence').value);
    try{interaction=await api('/api/interaction',values);renderInteraction();$('realtimeStatus').textContent='Saved. Start a new call to use the updated voice settings.';}
    catch(error){$('realtimeStatus').textContent=error.message;}
  });
  $('desktopSettings').addEventListener('click',async()=>{try{await api('/api/desktop',{action:'settings'});}catch(error){showToast(error.message);}});
  $('activateDesktop').addEventListener('click',async()=>{stopWork();try{await api('/api/desktop',{action:'activate'});}catch(error){showToast(error.message);}});
  setInterval(()=>{if(service?.desktop)api('/api/desktop',{action:'web_heartbeat'}).catch(()=>{});},10000);
  window.addEventListener('pagehide',()=>{if(service?.desktop)fetch('/api/desktop',{method:'POST',headers:{'Content-Type':'application/json','X-Raphael-Token':window.RaphaelConnection.token},body:JSON.stringify({action:'web_closed'}),keepalive:true}).catch(()=>{});});
  let refreshInProgress=false;
  async function refreshConnection(){
    if(refreshInProgress)return;refreshInProgress=true;
    try{
      if(!/^https?:$/.test(location.protocol))throw Error('Double-click Launch-Raphael.cmd to start real conversation and voice.');
      service=await api('/api/status');if(window.RaphaelConnection.token!==service.token)profileReady=false;window.RaphaelConnection.token=service.token;
      if(service.interaction)interaction=service.interaction;
      if(!interactionLoaded&&service.interaction){renderInteraction();interactionLoaded=true;}
      laptop.status(service.laptop);if(service.laptop)laptop.refresh();
      if(!prefs.laptopModelVersion&&service.laptop?.enabled&&service.models.includes('llama3.2:latest')){
        prefs.model='llama3.2:latest';prefs.laptopModelVersion=1;savePrefs();
        showToast('Llama is selected for faster local laptop actions. You can change it in Connection.');
      }
      if(!profileReady){try{const saved=await api('/api/profile');prefs.name=saved.name;prefs.notes=saved.notes;$('preferredName').value=prefs.name;profileReady=true;renderNotes();}catch(error){showToast('Saved memory could not load. '+error.message);}memoryControls();}
      $('chatConnection').textContent=service.chat==='ready'?prefs.model:service.chat==='loading'?'Loading local AI…':'Connection needed';
      $('voiceConnection').textContent=service.voice==='ready'?'Soft voice · ready':service.voice==='loading'?'Voice is loading…':'Voice unavailable';
      $('voiceServiceStatus').textContent=service.voice==='ready'?'Local voice ready · Kokoro':service.voice==='loading'?'Loading your voice…':'Text chat is available while voice is unavailable.';
      $('transcriptionStatus').textContent=service.transcription==='ready'?'Local speech recognition ready':service.transcription==='loading'?'Loading local speech recognition…':service.transcription_error||'Local speech recognition is unavailable.';
      $('connectionStatus').textContent=service.chat==='ready'?'Local conversation ready':service.chat==='loading'?'Starting the local model service…':'Local model connection needs attention';
      $('footerConnection').textContent=service.chat==='ready'?'CHAT & VOICE · LOCAL':'CONNECTING LOCALLY';
      const options=service.models.map(name=>({value:name,label:({'qwen3.5:4b':'Qwen 3.5 · 4B','llama3.2:latest':'Llama 3.2 · 3B'})[name]||name}));
      if(options.length)options.unshift({value:'auto',label:'Automatic · use saved routing preferences'});
      if(options.length){
        if(!options.some(o=>o.value===prefs.model)){prefs.model=service.default_model;savePrefs();}
        if(Array.from($('modelSelect').options).map(o=>o.value).join()!==options.map(o=>o.value).join()){$('modelSelect').replaceChildren(...options.map(o=>new Option(o.label,o.value)));}
        $('modelSelect').value=prefs.model;$('chatConnection').textContent=prefs.model;
      }
      $('connectionDetails').textContent=[service.chat_error,service.voice_error,service.transcription_error].filter(Boolean).join(' ')||'The first answer may take longer while the model loads. Speech, microphone recognition, and conversation run here.';
    }catch(error){service=null;window.RaphaelConnection.token=null;profileReady=false;memoryControls();$('chatConnection').textContent='Start Raphael';$('voiceConnection').textContent='Not connected';$('connectionStatus').textContent='Open Launch-Raphael.cmd';$('connectionDetails').textContent=error.message;$('voiceServiceStatus').textContent='Start Raphael to connect the voice.';$('footerConnection').textContent='SERVICE IS OFF';}
    finally{refreshInProgress=false;}
  }
  $('retryConnection').addEventListener('click',refreshConnection);
  if(/^https?:$/.test(location.protocol))document.querySelector('.original-link').href='/original';
  refreshConnection();setInterval(refreshConnection,8000);
  window.addEventListener('pagehide',()=>{if(chatJob)fetch('/api/cancel/'+chatJob,{method:'POST',headers:{'Content-Type':'application/json','X-Raphael-Token':window.RaphaelConnection.token||''},body:'{}',keepalive:true}).catch(()=>{});});

  function setPalette(name) {
    settings.palette=name;document.body.dataset.palette=name;
    document.querySelectorAll('[data-palette-option]').forEach(button=>{const active=button.dataset.paletteOption===name;button.classList.toggle('selected',active);button.setAttribute('aria-pressed',String(active));});dirty=true;
  }
  document.querySelectorAll('[data-palette-option]').forEach(button=>button.addEventListener('click',()=>setPalette(button.dataset.paletteOption)));
  $('glowRange').addEventListener('input',event=>{settings.glow=Number(event.target.value)/100;$('glowValue').value=event.target.value+'%';dirty=true;});
  $('motionRange').addEventListener('input',event=>{settings.speed=Number(event.target.value)/10;$('speedValue').value=settings.speed.toFixed(1)+'×';dirty=true;});
  $('particlesToggle').addEventListener('change',event=>{settings.particles=event.target.checked;dirty=true;});
  function setReduced(value){settings.reduced=value;$('reduceToggle').checked=value;$('motionButton').setAttribute('aria-pressed',String(value));$('motionLabel').textContent=value?'Motion paused':'Motion on';document.body.classList.toggle('reduced-motion',value);dirty=true;}
  $('reduceToggle').addEventListener('change',event=>setReduced(event.target.checked));
  $('motionButton').addEventListener('click',()=>setReduced(!settings.reduced));
  media.addEventListener('change',event=>setReduced(event.matches));
  $('resetAppearance').addEventListener('click',()=>{setPalette('sage');settings.glow=.7;settings.speed=1;settings.particles=true;$('glowRange').value=70;$('glowValue').value='70%';$('motionRange').value=10;$('speedValue').value='1.0×';$('particlesToggle').checked=true;setReduced(media.matches);showToast('Original Sage appearance restored.');});
  function setFocus(value){document.body.classList.toggle('focus-mode',value);$('focusButton').setAttribute('aria-pressed',String(value));$('focusButton').setAttribute('aria-label',value?'Exit focus view':'Enter focus view');if(value)$('exitFocus').focus();else $('focusButton').focus();dirty=true;}
  $('focusButton').addEventListener('click',()=>setFocus(!document.body.classList.contains('focus-mode')));
  $('exitFocus').addEventListener('click',()=>setFocus(false));
  document.addEventListener('keydown',event=>{
    const isInput=/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
    if(event.key==='/'&&!isInput&&!$('detailDialog').open){event.preventDefault();$('messageInput').focus();}
    if(event.key==='Escape'&&!$('detailDialog').open){if(busy)stopWork();else if(document.body.classList.contains('focus-mode'))setFocus(false);}
  });
  setReduced(settings.reduced);

  // Renderer: projected 3D rings and wireframes on a dependency-free 2D canvas.
  const canvas=$('coreCanvas'), ctx=canvas.getContext('2d',{alpha:false});
  let width=0,height=0,dpr=1,sceneTime=0,lastTime=0,lastDraw=0,burst=0;
  let pointer={x:0,y:0},smoothed={x:0,y:0};
  const TAU=Math.PI*2;
  let seed=21703;
  function rand(){seed=(seed*16807)%2147483647;return(seed-1)/2147483646;}
  const motes=Array.from({length:175},()=>({a:rand()*TAU,r:rand(),s:rand()*3.7+.8,speed:rand()*.012+.006,phase:rand()*TAU,z:rand(),rotation:rand()*TAU}));
  const rays=Array.from({length:92},()=>({a:rand()*TAU,len:.45+rand()*.65,alpha:rand()*.12+.018,start:rand()*.35+.12}));
  const stars=Array.from({length:90},()=>({x:rand(),y:rand(),r:rand()*.8+.25,phase:rand()*TAU}));
  const PHI=(1+Math.sqrt(5))/2;
  const vertices=[];
  for(const a of [-1,1])for(const b of [-PHI,PHI]){vertices.push([0,a,b],[a,b,0],[b,0,a]);}
  const length=Math.sqrt(1+PHI*PHI);vertices.forEach(v=>{v[0]/=length;v[1]/=length;v[2]/=length;});
  const edges=[];
  for(let i=0;i<vertices.length;i++)for(let j=i+1;j<vertices.length;j++){const a=vertices[i],b=vertices[j];if(Math.hypot(a[0]-b[0],a[1]-b[1],a[2]-b[2])<1.1)edges.push([i,j]);}
  const palettes={sage:{main:[214,237,209],white:[249,251,225],halo:[185,205,34],aqua:[19,165,155],third:[95,137,52]},azure:{main:[174,220,255],white:[228,249,255],halo:[73,119,255],aqua:[40,179,212],third:[86,114,182]},gold:{main:[241,215,167],white:[255,244,211],halo:[229,166,52],aqua:[186,105,75],third:[174,92,103]}};
  function rgba(rgb,a){return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${Math.max(0,Math.min(1,a))})`;}
  function rotate(v,rx,ry,rz){
    let [x,y,z]=v;
    const cy=Math.cos(rx),sy=Math.sin(rx);[y,z]=[y*cy-z*sy,y*sy+z*cy];
    const cx=Math.cos(ry),sx=Math.sin(ry);[x,z]=[x*cx+z*sx,-x*sx+z*cx];
    const cz=Math.cos(rz),sz=Math.sin(rz);return[x*cz-y*sz,x*sz+y*cz,z];
  }
  function project(v,cx,cy,r){const perspective=3.8/(3.8-v[2]);return[cx+v[0]*r*perspective,cy+v[1]*r*perspective,v[2]];}
  function glow(x,y,r,color,alpha,center=0){const gradient=ctx.createRadialGradient(x,y,center,x,y,r);gradient.addColorStop(0,rgba(color,alpha));gradient.addColorStop(.28,rgba(color,alpha*.45));gradient.addColorStop(1,rgba(color,0));ctx.fillStyle=gradient;ctx.fillRect(x-r,y-r,r*2,r*2);}
  function line(a,b,color,alpha,lineWidth=.6){ctx.strokeStyle=rgba(color,alpha);ctx.lineWidth=lineWidth;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}
  function ring(cx,cy,r,rx,ry,rz,color,alpha,phase,dash=false){
    const count=128, points=[];
    for(let i=0;i<=count;i++){const a=i/count*TAU;points.push(project(rotate([Math.cos(a),Math.sin(a),0],rx,ry,rz),cx,cy,r));}
    for(let i=1;i<points.length;i++){
      if(dash&&i%5===0)continue;
      const depth=(points[i][2]+1)*.5;line(points[i-1],points[i],color,alpha*(.3+.7*depth),depth>.85?1.05:.65);
    }
    for(let i=0;i<5;i++){
      const a=phase+i/5*TAU;const p=project(rotate([Math.cos(a),Math.sin(a),0],rx,ry,rz),cx,cy,r);
      if(p[2]>-.6){glow(p[0],p[1],8,color,.16);ctx.fillStyle=rgba(color,.8);ctx.fillRect(p[0]-1,p[1]-1,2,2);}
    }
  }
  function polyhedron(cx,cy,r,rx,ry,rz,color,alpha){
    const p=vertices.map(v=>project(rotate(v,rx,ry,rz),cx,cy,r));
    edges.forEach(([a,b])=>line(p[a],p[b],color,alpha*(.35+(p[a][2]+p[b][2]+2)*.21),.65));
    p.forEach(v=>{ctx.fillStyle=rgba(color,alpha*1.5);ctx.beginPath();ctx.arc(v[0],v[1],v[2]>.2?1.7:1,0,TAU);ctx.fill();if(v[2]>.4)glow(v[0],v[1],9,color,alpha*.15);});
  }
  function resize(){if(!ctx)return;const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;dpr=Math.min(window.devicePixelRatio||1,1.7);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);dirty=true;}
  new ResizeObserver(resize).observe(canvas);
  // Reserve space for the actual composer, including recording and reply states.
  const experience=document.querySelector('.experience');
  new ResizeObserver(entries=>{experience.style.setProperty('--composer-height',Math.ceil(entries[0].borderBoxSize?.[0]?.blockSize||entries[0].target.getBoundingClientRect().height)+'px');}).observe(document.querySelector('.command-area'));
  $('stage').addEventListener('pointermove',event=>{const rect=canvas.getBoundingClientRect();pointer.x=(event.clientX-rect.left-width/2)/width;pointer.y=(event.clientY-rect.top-height/2)/height;if(!settings.reduced)dirty=true;});
  $('stage').addEventListener('pointerleave',()=>{pointer={x:0,y:0};});
  $('stage').addEventListener('pointerdown',()=>{if(!settings.reduced){burst=1;dirty=true;}});
  function render(time){
    const c=palettes[settings.palette], g=settings.glow;
    const speaking=currentState==='speaking', thinking=currentState==='thinking', listening=currentState==='listening';
    const activity=thinking?1.85:listening?1.1:speaking?1.3:1;
    const voiceLevel=settings.reduced?0:listening?microphone.level:voice.level;
    const pulse=settings.reduced?0:(speaking||listening)?voiceLevel:Math.sin(time*1.1);
    const breath=1+(speaking?voiceLevel*.14:pulse*(listening?.037:.012))+burst*.065;
    const radius=Math.min(height*.30,width*.245,220)*breath;
    if(!settings.reduced){smoothed.x+=(pointer.x*19-smoothed.x)*.045;smoothed.y+=(pointer.y*15-smoothed.y)*.045;}
    const cx=width*.5+smoothed.x,cy=height*.46+smoothed.y;
    ctx.globalCompositeOperation='source-over';ctx.fillStyle='#070b0c';ctx.fillRect(0,0,width,height);
    ctx.globalCompositeOperation='screen';
    glow(cx,cy,radius*2.9,c.third,.045+g*.018);
    stars.forEach(s=>{ctx.fillStyle=rgba(c.main,(.15+Math.sin(time*.35+s.phase)*.1)*g);ctx.fillRect(s.x*width,s.y*height,s.r,s.r);});
    // Loosely orbiting clouds recreate the reference's cyan and yellow-green halo.
    for(let i=0;i<7;i++){
      const a=i/7*TAU+time*.055;
      const x=cx+Math.cos(a)*radius*1.12,y=cy+Math.sin(a)*radius*.92;
      const color=i<3?c.halo:i<5?c.aqua:c.third;
      glow(x,y,radius*(i%2?.75:.55),color,g*(i===1?.37:.23));
    }
    glow(cx-radius*.72,cy-radius*.08,radius*.55,c.aqua,g*.44);
    glow(cx+radius*.2,cy+radius*.88,radius*.43,c.halo,g*.43);
    const spread=Math.max(width*.7,height*.8);
    rays.forEach((ray,i)=>{
      const a=ray.a+time*.009;
      const cos=Math.cos(a),sin=Math.sin(a);
      const begin=radius*ray.start,end=spread*ray.len;
      const grad=ctx.createLinearGradient(cx+cos*begin,cy+sin*begin,cx+cos*end,cy+sin*end);
      grad.addColorStop(0,rgba(c.white,0));grad.addColorStop(.13,rgba(c.main,ray.alpha*.75*g));grad.addColorStop(.55,rgba(c.main,ray.alpha*g));grad.addColorStop(1,rgba(c.main,0));
      ctx.strokeStyle=grad;ctx.lineWidth=i%7===0?.8:.5;ctx.beginPath();ctx.moveTo(cx+cos*begin,cy+sin*begin);ctx.lineTo(cx+cos*end,cy+sin*end);ctx.stroke();
    });
    if(settings.particles)motes.forEach((m,i)=>{
      const travel=(m.r+time*m.speed*.18)%1;
      const distance=radius*.35+Math.pow(travel,.68)*spread;
      const a=m.a+time*.008;
      const x=cx+Math.cos(a)*distance,y=cy+Math.sin(a)*distance*.68;
      if(x<0||x>width||y<0||y>height)return;
      const opacity=Math.sin(travel*Math.PI)*(.14+m.z*.38)*g;
      const size=m.s*(.5+travel*.8);
      ctx.save();ctx.translate(x,y);ctx.rotate(m.rotation+time*.035);ctx.fillStyle=rgba(i%7===0?c.halo:c.main,opacity);
      ctx.fillRect(-size/2,-size/2,size,size*(i%5===0?1.6:1));ctx.restore();
      if(i%17===0)glow(x,y,size*5,c.main,opacity*.15);
    });
    const t=time*.12*activity;
    // Fine satellite orbit with divided measurement marks.
    ctx.save();ctx.translate(cx,cy);ctx.rotate(t*.11);ctx.scale(1,.90);
    for(let i=0;i<96;i++){
      const angle=i/96*TAU;const radiusA=radius*1.41,radiusB=radiusA+(i%8===0?5:2);
      line([Math.cos(angle)*radiusA,Math.sin(angle)*radiusA],[Math.cos(angle)*radiusB,Math.sin(angle)*radiusB],c.main,i%8===0?.23:.07,.6);
    }ctx.restore();
    ring(cx,cy,radius*1.22,.82+Math.sin(t*.2)*.13,.35,t*.17,c.main,.54,t*.2,true);
    ring(cx,cy,radius*1.11,.20,1.1,t*.30+.8,c.white,.65,-t*.28);
    ring(cx,cy,radius*1.01,1.22,.16,-t*.41+.3,c.white,.63,t*.47);
    polyhedron(cx,cy,radius*1.12,t*.53+.4,t*.44+.7,t*.17,c.main,.50);
    polyhedron(cx,cy,radius*.83,-t*.32+.2,t*.63+1.8,-t*.28,c.white,.51);
    ring(cx,cy,radius*.85,.55+t*.21,.6,-.6+t*.2,c.main,.40,t);
    ring(cx,cy,radius*.96,.16,.12,t*.3,c.white,.79,t*.35);
    ring(cx,cy,radius*.92,.14,.14,t*.3,c.white,.21,t*.35,true);
    // Inner lattice gives the light a geometric structure rather than a flat disc.
    polyhedron(cx,cy,radius*.51,t*.61,.6-t*.39,t*.5,c.white,.41);
    for(let i=0;i<3;i++)ring(cx,cy,radius*(.37+i*.09),i*.9+t*.12,.8+i*.2,t*.6+i*.9,c.white,.29,-t);
    if(listening||speaking){
      for(let i=0;i<3;i++){
        const p=(time*(speaking?.4:.22)+i/3)%1;
        ring(cx,cy,radius*(.75+p*.95),.18,.13,.2,c.main,(1-p)*.15*(speaking?voiceLevel*1.5:1),t,false);
      }
    }
    glow(cx,cy,radius*.69,c.halo,g*.10);
    glow(cx,cy,radius*.38,c.white,g*.46);
    glow(cx,cy,radius*(.24+voiceLevel*.16),c.white,(.82+voiceLevel*.58)*g);
    glow(cx,cy,radius*(.13+voiceLevel*.09),c.white,.97);
    // Irregular luminous rays radiate out of the white-hot center.
    for(let i=0;i<42;i++){
      const a=i/42*TAU+time*.017;
      const len=radius*(.12+.15*(.5+.5*Math.sin(i*14.36)))+Math.sin(time+i)*2;
      const grad=ctx.createLinearGradient(cx,cy,cx+Math.cos(a)*len,cy+Math.sin(a)*len);
      grad.addColorStop(0,rgba(c.white,.55*g));grad.addColorStop(1,rgba(c.white,0));
      ctx.strokeStyle=grad;ctx.lineWidth=i%4===0?1.1:.5;ctx.beginPath();ctx.moveTo(cx,cy);ctx.lineTo(cx+Math.cos(a)*len,cy+Math.sin(a)*len);ctx.stroke();
    }
    const coreSize=radius*(.079+(speaking?voiceLevel*.095:0));
    const core=ctx.createRadialGradient(cx,cy,0,cx,cy,coreSize*2.7);
    core.addColorStop(0,'rgba(255,255,246,1)');core.addColorStop(.25,'rgba(255,255,241,.98)');core.addColorStop(.48,rgba(c.white,.68));core.addColorStop(1,rgba(c.white,0));
    ctx.fillStyle=core;ctx.beginPath();ctx.arc(cx,cy,coreSize*2.7,0,TAU);ctx.fill();
    // Long, soft cross flare.
    ctx.save();ctx.translate(cx,cy);ctx.scale(1,.05);glow(0,0,radius*.65,c.white,g*.15);ctx.restore();
    ctx.globalCompositeOperation='source-over';
  }
  function frame(now){
    requestAnimationFrame(frame);
    const delta=lastTime?Math.min((now-lastTime)/1000,.06):0;lastTime=now;
    voice.update(delta);
    if(document.hidden)return;
    if(!settings.reduced){sceneTime+=delta*settings.speed;burst*=Math.pow(.045,delta);}
    if(now-lastDraw<1000/30&&!dirty)return;
    if(settings.reduced&&!dirty)return;
    lastDraw=now;dirty=false;
    if(width>0&&height>0)render(sceneTime);
  }
  if(ctx){resize();requestAnimationFrame(frame);}else{canvas.setAttribute('aria-label','Your browser does not support the animated canvas. All interface controls remain available.');}
window.RaphaelUI=Object.freeze({sendMessage,stop:stopWork,getState:()=>currentState,getMessages:()=>messages.map(({role,content,status})=>({role,content,status}))});})();
