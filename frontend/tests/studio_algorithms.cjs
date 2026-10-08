const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const messages=[];
let outputPixels;
const context={console,
  self:{postMessage:m=>messages.push(m)},
  ImageData:class {constructor(data,width,height){this.data=data;this.width=width;this.height=height;}},
  OffscreenCanvas:class {getContext(){return {putImageData:v=>{outputPixels=v;}};} async convertToBlob(){return {type:'image/jpeg'};}}
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../public/bracketingWorker.js'),'utf8'),context);
const w=768,h=384;
const data=(factor,dx=0,dy=0)=>{
  const pixels=new Uint8ClampedArray(w*h*4);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const sx=Math.max(0,Math.min(w-1,x-dx)),sy=Math.max(0,Math.min(h-1,y-dy));
    const v=Math.round(factor*(110+28*Math.sin(sx*.037)+22*Math.cos(sy*.061)+18*Math.sin((sx+sy)*.023)));
    const i=(y*w+x)*4;pixels[i]=pixels[i+1]=pixels[i+2]=v;pixels[i+3]=255;
  }
  return {data:pixels.buffer,width:w,height:h};
};
context.self.onmessage({data:{groupIndex:0,groupImageDatas:[data(1),data(.8,16,21),data(1.2)]}});
setImmediate(()=>{
  const done=messages.find(m=>m.type==='done');
  assert.ok(done,JSON.stringify(messages));
  assert.ok(Math.abs(done.alignment[1].dx+16)<=1,JSON.stringify(done.alignment));
  assert.ok(Math.abs(done.alignment[1].dy+21)<=1,JSON.stringify(done.alignment));
  assert.equal(outputPixels.width,w);
  assert.equal(outputPixels.height,h);
  for(let i=(w*30+30)*4;i<outputPixels.data.length-30*w*4;i+=4){
    assert.equal(outputPixels.data[i],outputPixels.data[i+1],'neutral colours preserved');
    assert.equal(outputPixels.data[i+1],outputPixels.data[i+2],'neutral colours preserved');
    assert.equal(outputPixels.data[i+3],255);
  }
  console.log('HDR algorithm checks passed: rectangular alignment, dimensions, neutral colours.');
});
