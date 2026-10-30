/* Local call orchestration. Capture and inference are supplied as adapters. */
(() => {
  'use strict';
  function wakeCommand(text){
    const value=text.trim();
    if(/^(?:raphael|rafael|rapha[eë]l)[.!?,\s]*$/iu.test(value))return {heard:true,text:''};
    const match=value.match(/^(?:hey|hi|hello)[,\s]+(?:raphael|rafael|rapha[eë]l)\b[.!?,:\s]*(.*)$/iu);
    return match?{heard:true,text:match[1].trim()}:null;
  }
  function command(text){
    const clean=text.toLowerCase().replace(/[.!?,]/g,'').trim();
    if(/^(?:please )?(?:end (?:the )?call|hang up|stop listening)(?: please)?$/.test(clean))return 'end';
    if(/^(?:please )?(?:go to sleep|sleep raphael)(?: please)?$/.test(clean))return 'sleep';
    return null;
  }
  class LiveCall {
    constructor(options){this.options=options;this.mode='off';this.state='off';this.epoch=0;this.wakeEnabled=false;this.timer=null;this.muted=false;}
    get active(){return this.mode!=='off';}
    change(state,message=''){this.state=state;this.options.onChange?.({state,mode:this.mode,muted:this.muted,wakeEnabled:this.wakeEnabled,message});}
    stop(cancel=true){
      this.epoch++;clearTimeout(this.timer);this.timer=null;
      this.mode='off';this.wakeEnabled=false;this.muted=false;
      this.options.microphone.stop();if(cancel)this.options.cancelTurn();this.change('off');
    }
    async start(wake=false){
      this.stop();this.mode=wake?'wake':'call';this.wakeEnabled=wake;
      const token=++this.epoch;this.change('connecting');
      try{await this.options.prepare();if(token!==this.epoch)return;await this.listen(token);}
      catch(error){if(token===this.epoch){this.stop();this.options.onError(error);}}
    }
    async listen(token=this.epoch){
      if(token!==this.epoch||!this.active||this.muted)return;
      this.change('connecting');
      try{
        const ready=await this.options.microphone.start({automatic:true,pauseSeconds:this.options.pauseSeconds?.()||.9,sensitivity:this.options.sensitivity?.()??.55});
        if(token!==this.epoch)return;
        if(ready)this.change(this.mode==='wake'?'armed':'listening');
      }catch(error){if(token===this.epoch){this.stop();this.options.onError(error);}}
    }
    schedule(token,delay=120){
      clearTimeout(this.timer);
      this.timer=setTimeout(()=>{this.timer=null;if(token===this.epoch)this.listen(token);},delay);
    }
    async finish(){
      if(!['listening','armed'].includes(this.state))return;
      const token=this.epoch,wasWake=this.mode==='wake';this.change(wasWake?'checking':'recognizing');
      try{
        let text=await this.options.microphone.finish(wasWake?'en':this.options.language());
        if(token!==this.epoch||!this.active||this.muted)return;
        if(!text){this.schedule(token);return;}
        if(wasWake){
          const wake=wakeCommand(text);
          // Unrelated speech never enters the AI conversation.
          if(!wake){this.schedule(token,100);return;}
          this.mode='call';text=wake.text;
          if(!text){
            this.change('replying');await this.options.acknowledge();
            if(token===this.epoch)this.schedule(token);return;
          }
        }
        const intent=command(text);
        if(intent==='end'){this.stop();return;}
        if(intent==='sleep'){
          if(this.wakeEnabled){this.mode='wake';this.change('armed');this.schedule(token);}
          else this.stop();return;
        }
        this.options.onTranscript(text);this.change('replying');
        const turn=this.options.onTurn(text,{inputStarted:this.options.microphone.inputCompleted});
        if(this.options.bargeIn?.())await this.listenDuringReply(token);
        const completed=await turn;
        if(token!==this.epoch)return;
        if(this.options.bargeIn?.())this.options.microphone.stop();
        if(completed===false){this.pause('The reply stopped. Resume when you are ready.');return;}
        this.schedule(token);
      }catch(error){
        if(token!==this.epoch)return;
        if(error.code==='no_speech'){this.schedule(token,250);return;}
        this.pause(error.message||'The call needs attention.');this.options.onError(error);
      }
    }
    async listenDuringReply(token){
      try{
        const ready=await this.options.microphone.start({automatic:true,pauseSeconds:this.options.pauseSeconds?.()||.9,sensitivity:this.options.sensitivity?.()??.55});
        if(token===this.epoch&&ready)this.change('barge-listening','Microphone on · speak to interrupt.');
      }catch(error){if(token===this.epoch)this.options.onError(error);}
    }
    speechStarted(){
      if(this.state!=='barge-listening'||!this.options.bargeIn?.())return;
      // Keep this recording: cancellation stops the model and speaker, not the new utterance.
      this.epoch++;clearTimeout(this.timer);this.timer=null;
      this.options.cancelTurn(true);this.change('listening','Listening to your interruption…');
    }
    pause(message='Microphone off. Resume when you are ready.'){
      if(!this.active)return;this.epoch++;clearTimeout(this.timer);this.timer=null;this.muted=true;
      this.options.microphone.stop();this.options.cancelTurn();this.change('paused',message);
    }
    async resume(){
      if(!this.active||!this.muted)return;this.muted=false;
      const token=++this.epoch;
      try{await this.options.prepare();if(token===this.epoch)await this.listen(token);}
      catch(error){if(token===this.epoch){this.pause(error.message);this.options.onError(error);}}
    }
    async interrupt(){
      if(!this.active)return;
      const token=++this.epoch;clearTimeout(this.timer);this.timer=null;
      this.muted=false;this.options.microphone.stop();this.options.cancelTurn();await this.listen(token);
    }
  }
  window.RaphaelLiveCall=Object.freeze({LiveCall,wakeCommand,command});
})();
