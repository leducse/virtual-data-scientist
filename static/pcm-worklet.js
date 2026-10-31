class Recorder extends AudioWorkletProcessor {
  constructor(){super();this.buffer=new Float32Array(2048);this.offset=0;this.total=0;}
  process(inputs){
    const channel=inputs[0]?.[0];if(!channel)return true;
    for(const sample of channel){
      if(this.total++>=sampleRate*20){this.port.postMessage({limit:true});return false;}
      this.buffer[this.offset++]=sample;
      if(this.offset===this.buffer.length){this.port.postMessage(this.buffer,[this.buffer.buffer]);this.buffer=new Float32Array(2048);this.offset=0;}
    }
    return true;
  }
}
registerProcessor('vds-recorder',Recorder);
