/* Bounded PCM capture with optional local energy-based turn detection. */
class RaphaelRecorder extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.buffer = new Float32Array(2048); this.offset = 0; this.total = 0;
    this.active = true; this.limit = Math.floor(sampleRate * 30);
    this.auto=!!options?.processorOptions?.automatic;
    this.silenceLimit=sampleRate*(options?.processorOptions?.pauseSeconds||1.2);
    this.sensitivity=Math.max(0,Math.min(1,options?.processorOptions?.sensitivity??.55));
    this.preRoll=[];this.preCount=0;this.meter=0;
    this.triggered=false;this.speechFrames=0;this.quietFrames=0;this.noise=.002;
    this.port.onmessage = event => {
      if (event.data === 'flush') {
        this.active = false; this.flush(); this.port.postMessage({ type: 'flushed' });
      }
    };
  }
  flush() {
    if (!this.offset) return;
    const samples = this.buffer.slice(0, this.offset);
    this.port.postMessage({ type: 'samples', samples, total: this.total }, [samples.buffer]);
    this.offset = 0;
  }
  append(input) {
    for (const sample of input) {
      if (this.total >= this.limit) {
        this.finish('limit'); return;
      }
      this.buffer[this.offset++] = sample; this.total++;
      if (this.offset === this.buffer.length) this.flush();
    }
  }
  finish(type){if(!this.active)return;this.active=false;this.flush();this.port.postMessage({type,endpoint_seconds:this.quietFrames/sampleRate});}
  process(inputs) {
    const input=inputs[0]?.[0];if(!this.active||!input)return true;
    if(!this.auto){this.append(input);return true;}
    let power=0;for(const value of input)power+=value*value;
    const rms=Math.sqrt(power/input.length);
    // Quiet input adapts the floor; speaking cannot raise its own threshold.
    if(!this.triggered&&rms<Math.max(.012,this.noise*2))this.noise=this.noise*.995+rms*.005;
    const voiced=rms>Math.max(.004+(1-this.sensitivity)*.016,Math.min(.04,this.noise*3.2));
    this.meter+=input.length;
    if(this.meter>=sampleRate*.08){this.port.postMessage({type:'meter',level:Math.min(1,rms*7),seconds:this.total/sampleRate});this.meter=0;}
    if(!this.triggered){
      this.preRoll.push(input.slice());this.preCount+=input.length;
      while(this.preCount>sampleRate*.5&&this.preRoll.length>1)this.preCount-=this.preRoll.shift().length;
      this.speechFrames=voiced?this.speechFrames+input.length:Math.max(0,this.speechFrames-input.length*2);
      if(this.speechFrames>=sampleRate*.16){
        this.triggered=true;this.quietFrames=0;
        for(const frame of this.preRoll)this.append(frame);
        this.preRoll=[];this.preCount=0;this.port.postMessage({type:'speech'});
      }
      return true;
    }
    this.append(input);
    this.speechFrames+=voiced?input.length:0;this.quietFrames=voiced?0:this.quietFrames+input.length;
    if(this.quietFrames>=this.silenceLimit){
      if(this.speechFrames>=sampleRate*.25)this.finish('utterance');
      else{this.triggered=false;this.speechFrames=0;this.quietFrames=0;this.total=0;this.offset=0;this.port.postMessage({type:'discard'});}
    }
    return true;
  }
}
registerProcessor('raphael-recorder', RaphaelRecorder);
